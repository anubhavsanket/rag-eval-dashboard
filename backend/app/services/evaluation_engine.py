import logging
import math
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.models.dataset import Dataset
from app.models.test_case import TestCase
from app.models.rag_config import RAGConfig
from app.models.eval_run import EvalRun
from app.models.eval_result import EvalResult
from app.services.pipeline_adapter import get_adapter, PipelineResponse
from app.services.judge import JudgeLLM, MockJudge
from app.services.failure_classifier import classify_failure
from app.services import cost as cost_service
from app.config import get_settings

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
    "score": 0.0-1.0 (ratio of supported claims to total claims),
    "failure_category": "none" | "hallucination" | "reasoning_error",
    "root_cause": "brief explanation of why it failed or 'none'"
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
    "normalized_score": 0.0-1.0,
    "failure_category": "none" | "retrieval_miss" | "noisy_retrieval",
    "root_cause": "brief explanation of why retrieval was poor or 'none'"
}"""

CORRECTNESS_SYSTEM = """You are an expert evaluator for Retrieval-Augmented Generation (RAG) systems.
Your task is to evaluate whether the generated answer matches the expected ground truth answer.

Consider:
- Semantic equivalence
- Completeness
- Partial correctness

Return a JSON object with:
{
    "score": 0.0-1.0,
    "reasoning": "explanation of the score",
    "failure_category": "none" | "factually_incorrect" | "incomplete_answer",
    "root_cause": "detailed explanation of discrepancy"
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
    failure_category: str = "none"
    root_cause: str = "none"
    cost_usd: float = 0.0
    details: dict = field(default_factory=dict)


class EvaluationEngine:
    def __init__(self, judge: JudgeLLM | None = None, cost_provider: str = "ollama", cost_model: str = "*"):
        if judge:
            self.judge = judge
        else:
            settings = get_settings()
            if settings.JUDGE_PROVIDER == "mock":
                self.judge = MockJudge()
            else:
                self.judge = JudgeLLM()
        self.judge_provider = self.judge.provider
        self.judge_model = self.judge.model
        self.cost_provider = cost_provider
        self.cost_model = cost_model

    async def _judge_and_cost(self, system_prompt: str, user_prompt: str) -> tuple[dict, float, int, int]:
        """Call the judge, record usage, and return the result plus cost."""
        result = await self.judge.judge(system_prompt, user_prompt)
        usage = result.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        cost = cost_service.estimate_cost_usd(
            self.judge_provider, self.judge_model, prompt_tokens, completion_tokens
        )
        return result, cost, prompt_tokens, completion_tokens

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

        judge_cost = 0.0
        judge_tokens = 0

        # 1. Faithfulness
        try:
            faith_prompt = f"""Query: {query}

Answer: {pipeline_response.answer}

Context:
{context_text}"""
            faith_result, cost, p, c = await self._judge_and_cost(FAITHFULNESS_SYSTEM, faith_prompt)
            metrics.faithfulness = faith_result.get("score", 0.0)
            faith_result["cost_usd"] = cost
            metrics.details["faithfulness"] = faith_result
            judge_cost += cost
            judge_tokens += p + c
        except Exception as e:
            logger.error(f"Faithfulness evaluation failed: {e}")
            metrics.details["faithfulness"] = {"error": str(e)}

        # 2. Relevance
        try:
            rel_prompt = f"""Query: {query}

Retrieved Chunks:
{context_text}"""
            rel_result, cost, p, c = await self._judge_and_cost(RELEVANCE_SYSTEM, rel_prompt)
            metrics.relevance = rel_result.get("normalized_score", 0.0)
            rel_result["cost_usd"] = cost
            metrics.details["relevance"] = rel_result
            judge_cost += cost
            judge_tokens += p + c
        except Exception as e:
            logger.error(f"Relevance evaluation failed: {e}")
            metrics.details["relevance"] = {"error": str(e)}

        # 3. Correctness
        try:
            corr_prompt = f"""Query: {query}

Generated Answer: {pipeline_response.answer}

Expected Answer: {expected_answer}"""
            corr_result, cost, p, c = await self._judge_and_cost(CORRECTNESS_SYSTEM, corr_prompt)
            metrics.correctness = corr_result.get("score", 0.0)
            corr_result["cost_usd"] = cost
            metrics.details["correctness"] = corr_result
            judge_cost += cost
            judge_tokens += p + c
        except Exception as e:
            logger.error(f"Correctness evaluation failed: {e}")
            metrics.details["correctness"] = {"error": str(e)}

        # 4. Hallucination Detection
        try:
            hall_prompt = f"""Query: {query}

Answer: {pipeline_response.answer}

Context:
{context_text}"""
            hall_result, cost, p, c = await self._judge_and_cost(HALLUCINATION_SYSTEM, hall_prompt)
            metrics.hallucination = hall_result.get("score", 1.0)
            hall_result["cost_usd"] = cost
            metrics.details["hallucination"] = hall_result
            judge_cost += cost
            judge_tokens += p + c
        except Exception as e:
            logger.error(f"Hallucination evaluation failed: {e}")
            metrics.details["hallucination"] = {"error": str(e)}

        # Root Cause Analysis: classify the failure and synthesize a single
        # human-readable root cause (see failure_classifier).
        metrics.details["num_chunks_retrieved"] = len(pipeline_response.retrieved_chunks)
        metrics.details["judge_cost_usd"] = judge_cost
        metrics.details["judge_tokens"] = judge_tokens
        scores_for_classification = {
            "faithfulness": metrics.faithfulness,
            "relevance": metrics.relevance,
            "correctness": metrics.correctness,
            "hallucination": metrics.hallucination,
        }
        category, root_cause = classify_failure(
            scores_for_classification, metrics.details
        )
        metrics.failure_category = category
        metrics.root_cause = root_cause

        # Pipeline cost (blended estimate — no prompt/completion split available).
        pipeline_cost = cost_service.estimate_cost_blended(
            self.cost_provider, self.cost_model, pipeline_response.tokens_used
        )
        metrics.cost_usd = round(judge_cost + pipeline_cost, 6)
        metrics.details["pipeline_cost_usd"] = pipeline_cost

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

            # Cost basis for the pipeline itself (not the judge).
            self.cost_provider = rag_config.config.get("provider", "ollama")
            self.cost_model = rag_config.config.get("model", "*")

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
                        "failure_category": metrics.failure_category,
                        "root_cause": metrics.root_cause,
                        "cost_usd": metrics.cost_usd,
                        "details": metrics.details,
                    },
                    failure_category=metrics.failure_category,
                    root_cause=metrics.root_cause,
                    estimated_cost_usd=metrics.cost_usd,
                    latency_ms=metrics.latency_ms,
                    tokens_used=metrics.tokens_used,
                )
                db.add(eval_result)
                all_metrics.append(metrics)
                logger.info(f"Run {run_id}: Query {i+1} - Result saved")

            # Compute summary
            summary = self._compute_summary(all_metrics)
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

    @staticmethod
    def _compute_summary(all_metrics: list[EvalMetrics]) -> dict:
        n = len(all_metrics)
        if n == 0:
            return {"total_queries": 0}

        def avg(key):
            # Skip metrics whose value is None (e.g. a pipeline that never
            # reported latency) — averaging must neither crash on a None
            # operand nor pretend a missing reading is 0.0.
            values = [
                getattr(m, key, 0) for m in all_metrics if getattr(m, key, None) is not None
            ]
            if not values:
                return 0.0
            return sum(values) / len(values)

        latencies = sorted(m.latency_ms for m in all_metrics if m.latency_ms is not None)

        def percentile(p):
            if not latencies:
                return None
            # Nearest-rank method: ceil(p*n)-1 (clamped). For small samples
            # this is the correct percentile (median of [100, 300] is 100,
            # not 300 as the old int(p*n) formula reported).
            idx = max(0, min(len(latencies) - 1, math.ceil(p * len(latencies)) - 1))
            return latencies[idx]

        failure_counts: dict[str, int] = {}
        for m in all_metrics:
            cat = m.failure_category
            failure_counts[cat] = failure_counts.get(cat, 0) + 1

        quality_score = (
            0.40 * avg("correctness")
            + 0.25 * avg("faithfulness")
            + 0.20 * avg("relevance")
            + 0.15 * avg("hallucination")
        )

        return {
            "avg_faithfulness": avg("faithfulness"),
            "avg_relevance": avg("relevance"),
            "avg_correctness": avg("correctness"),
            "avg_hallucination": avg("hallucination"),
            "total_queries": n,
            "avg_latency_ms": avg("latency_ms"),
            "p50_latency_ms": percentile(0.5),
            "p95_latency_ms": percentile(0.95),
            "total_tokens": sum(m.tokens_used for m in all_metrics),
            "total_judge_tokens": sum(m.details.get("judge_tokens", 0) for m in all_metrics),
            "total_cost_usd": round(sum(m.cost_usd for m in all_metrics), 6),
            "quality_score": round(quality_score, 4),
            "failure_distribution": failure_counts,
        }