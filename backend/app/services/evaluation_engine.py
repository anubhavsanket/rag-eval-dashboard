import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.dataset import Dataset
from app.models.test_case import TestCase
from app.models.rag_config import RAGConfig
from app.models.eval_run import EvalRun
from app.models.eval_result import EvalResult
from app.services.pipeline_adapter import get_adapter, PipelineResponse
from app.services.judge import JudgeLLM, MockJudge
from app.config import get_settings
from datetime import datetime

logger = logging.getLogger(__name__)

# Evaluation prompts
FAITHFULNESS_SYSTEM = """You are an expert evaluator for Retrieval-Augmented Generation (RAG) systems.
Your task is to evaluate whether an answer is faithful to (supported by) the provided context.

For each claim in the answer, determine if it is:
- "supported": the claim is directly backed by the context
- "refuted": the claim contradicts the context
- "unverifiable": the claim cannot be verified from the context

Return a JSON object with:
{
    "claims": [{"claim": "...", "verdict": "supported|refuted|unverifiable", "evidence": "quote from context or null"}],
    "score": 0.0-1.0 (ratio of supported claims to total claims)
}"""

RELEVANCE_SYSTEM = """You are an expert evaluator for Retrieval-Augmented Generation (RAG) systems.
Your task is to evaluate whether retrieved chunks are relevant to the given query.

Score each chunk on a 0-3 scale:
- 0: Irrelevant
- 1: Partially relevant
- 2: Relevant
- 3: Highly relevant

Return a JSON object with:
{
    "chunk_scores": [{"chunk_id": "id", "score": 0-3, "reasoning": "..."}],
    "average_score": 0.0-3.0,
    "normalized_score": 0.0-1.0 (average / 3)
}"""

CORRECTNESS_SYSTEM = """You are an expert evaluator for Retrieval-Augmented Generation (RAG) systems.
Your task is to evaluate whether the generated answer matches the expected ground truth answer.

Consider:
- Semantic equivalence (different phrasings that mean the same thing)
- Completeness (missing important information)
- Partial correctness (some parts correct, some wrong)
- Not exact match — focus on meaning

Return a JSON object with:
{
    "score": 0.0-1.0,
    "reasoning": "explanation of the score",
    "differences": ["list of key differences or notes"]
}"""

HALLUCINATION_SYSTEM = """You are an expert evaluator for Retrieval-Augmented Generation (RAG) systems.
Your task is to detect hallucinations — claims in the answer that are NOT supported by the retrieved context.

Extract factual claims from the answer, then check each against the context.
A hallucination is a factual claim that cannot be traced to any retrieved chunk.

Return a JSON object with:
{
    "total_claims": N,
    "supported_claims": N,
    "hallucinated_claims": [{"claim": "...", "reasoning": "..."}],
    "score": 0.0-1.0 (1 - hallucinated/total, or 1.0 if no claims)
}"""


@dataclass
class EvalMetrics:
    faithfulness: float = 0.0
    relevance: float = 0.0
    correctness: float = 0.0
    hallucination: float = 0.0
    latency_ms: int = 0
    tokens_used: int = 0
    details: dict = field(default_factory=dict)


class EvaluationEngine:
    def __init__(self, judge: JudgeLLM | None = None):
        if judge:
            self.judge = judge
        else:
            settings = get_settings()
            if settings.JUDGE_PROVIDER == "mock":
                self.judge = MockJudge()
            else:
                self.judge = JudgeLLM()

    async def evaluate_single(
        self, query: str, expected_answer: str, pipeline_response: PipelineResponse
    ) -> EvalMetrics:
        """Evaluate a single query response against all metrics."""
        metrics = EvalMetrics(
            latency_ms=pipeline_response.latency_ms,
            tokens_used=pipeline_response.tokens_used,
        )

        # Format context for prompts
        context_text = "\n\n".join(
            f"[Chunk {i+1}] {chunk.get('text', str(chunk))}"
            for i, chunk in enumerate(pipeline_response.retrieved_chunks)
        )
        if not context_text:
            context_text = "(No context chunks retrieved)"

        # 1. Faithfulness
        try:
            faith_prompt = f"""Query: {query}

Answer: {pipeline_response.answer}

Context:
{context_text}"""
            faith_result = await self.judge.judge(FAITHFULNESS_SYSTEM, faith_prompt)
            metrics.faithfulness = faith_result.get("score", 0.0)
            metrics.details["faithfulness"] = faith_result
        except Exception as e:
            logger.error(f"Faithfulness evaluation failed: {e}")
            metrics.details["faithfulness"] = {"error": str(e)}

        # 2. Relevance
        try:
            rel_prompt = f"""Query: {query}

Retrieved Chunks:
{context_text}"""
            rel_result = await self.judge.judge(RELEVANCE_SYSTEM, rel_prompt)
            metrics.relevance = rel_result.get("normalized_score", 0.0)
            metrics.details["relevance"] = rel_result
        except Exception as e:
            logger.error(f"Relevance evaluation failed: {e}")
            metrics.details["relevance"] = {"error": str(e)}

        # 3. Correctness
        try:
            corr_prompt = f"""Query: {query}

Generated Answer: {pipeline_response.answer}

Expected Answer: {expected_answer}"""
            corr_result = await self.judge.judge(CORRECTNESS_SYSTEM, corr_prompt)
            metrics.correctness = corr_result.get("score", 0.0)
            metrics.details["correctness"] = corr_result
        except Exception as e:
            logger.error(f"Correctness evaluation failed: {e}")
            metrics.details["correctness"] = {"error": str(e)}

        # 4. Hallucination Detection
        try:
            hall_prompt = f"""Query: {query}

Answer: {pipeline_response.answer}

Context:
{context_text}"""
            hall_result = await self.judge.judge(HALLUCINATION_SYSTEM, hall_prompt)
            metrics.hallucination = hall_result.get("score", 1.0)
            metrics.details["hallucination"] = hall_result
        except Exception as e:
            logger.error(f"Hallucination evaluation failed: {e}")
            metrics.details["hallucination"] = {"error": str(e)}

        return metrics

    async def run_evaluation(
        self, run_id: int, dataset_id: int, config_id: int, db: AsyncSession
    ):
        """Run a full evaluation."""
        logger.info(f"--- RUN {run_id} STARTING ---")
        
        # Load run
        result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
        run = result.scalar_one()
        run.status = "running"
        run.started_at = datetime.now()
        await db.commit()
        logger.info(f"Run {run_id} status: running")

        try:
            # Load dataset
            result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
            dataset = result.scalar_one()
            logger.info(f"Run {run_id}: Loaded dataset '{dataset.name}'")

            result = await db.execute(select(TestCase).where(TestCase.dataset_id == dataset_id))
            test_cases = result.scalars().all()
            logger.info(f"Run {run_id}: Loaded {len(test_cases)} test cases")

            # Load config
            result = await db.execute(select(RAGConfig).where(RAGConfig.id == config_id))
            rag_config = result.scalar_one()
            logger.info(f"Run {run_id}: Loaded config '{rag_config.name}'")

            # Create adapter
            adapter = get_adapter(rag_config.config)
            logger.info(f"Run {run_id}: Adapter created")

            # Evaluate
            all_metrics = []
            for i, tc in enumerate(test_cases):
                logger.info(f"Run {run_id}: Query {i+1}/{len(test_cases)} - {tc.query[:30]}...")
                
                pipeline_response = await adapter.query(tc.query)
                logger.info(f"Run {run_id}: Query {i+1} - Pipeline response received")

                metrics = await self.evaluate_single(tc.query, tc.expected_answer, pipeline_response)
                logger.info(f"Run {run_id}: Query {i+1} - Evaluation metrics computed")

                eval_result = EvalResult(
                    run_id=run_id,
                    test_case_id=tc.id,
                    query=tc.query,
                    answer=pipeline_response.answer,
                    retrieved_chunks=pipeline_response.retrieved_chunks,
                    scores={
                        "faithfulness": metrics.faithfulness,
                        "relevance": metrics.relevance,
                        "correctness": metrics.correctness,
                        "hallucination": metrics.hallucination,
                        "details": metrics.details,
                    },
                    latency_ms=metrics.latency_ms,
                    tokens_used=metrics.tokens_used,
                )
                db.add(eval_result)
                all_metrics.append(metrics)
                logger.info(f"Run {run_id}: Query {i+1} - Result saved")

            # Compute summary
            n = len(all_metrics)
            if n > 0:
                summary = {
                    "avg_faithfulness": sum(m.faithfulness for m in all_metrics) / n,
                    "avg_relevance": sum(m.relevance for m in all_metrics) / n,
                    "avg_correctness": sum(m.correctness for m in all_metrics) / n,
                    "avg_hallucination": sum(m.hallucination for m in all_metrics) / n,
                    "total_queries": n,
                    "avg_latency_ms": sum(m.latency_ms for m in all_metrics) / n,
                    "total_tokens": sum(m.tokens_used for m in all_metrics),
                }
            else:
                summary = {"total_queries": 0}

            run.summary = summary
            run.status = "completed"
            run.completed_at = datetime.now()
            logger.info(f"Run {run_id} status: completed")

        except Exception as e:
            logger.error(f"Run {run_id} failed: {e}", exc_info=True)
            run.status = "failed"
            run.completed_at = datetime.now()
            run.summary = {"error": str(e), "total_queries": 0}
        
        await db.commit()
        logger.info(f"--- RUN {run_id} FINISHED ---")
