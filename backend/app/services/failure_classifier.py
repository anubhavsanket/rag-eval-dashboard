"""Root cause analysis: classify every incorrect response into one of the six
failure modes and produce a single, human-readable root cause string.

Failure modes:

- ``retrieval_miss``:      Relevant info was not in the top-k chunks.
- ``noisy_retrieval``:     Irrelevant chunks confused the LLM.
- ``hallucination``:       Answer contains facts not present in context.
- ``reasoning_error``:     Context was correct, but LLM logic failed.
- ``incomplete_answer``:   LLM missed parts of the ground truth.
- ``factually_incorrect``: LLM contradicted the ground truth.
"""

CORRECTNESS_THRESHOLD = 0.7
RELEVANCE_THRESHOLD = 0.5
FAITHFULNESS_THRESHOLD = 0.7

# Human-readable explanations attached to each failure mode.
ROOT_CAUSES = {
    "retrieval_miss": (
        "The relevant information was not present in the retrieved top-k chunks, "
        "so the answer could not be grounded in evidence. Consider raising top_k, "
        "improving the embedding model, or verifying document coverage."
    ),
    "noisy_retrieval": (
        "Irrelevant chunks were retrieved alongside useful ones and confused the "
        "model. Consider lowering top_k, tightening the similarity threshold, or "
        "adding a re-ranking step."
    ),
    "hallucination": (
        "The answer contains claims not supported by the retrieved context. "
        "Strengthen grounding instructions, improve retrieved context quality, "
        "or lower the generation temperature."
    ),
    "reasoning_error": (
        "The retrieved context contained the needed information, but the model "
        "failed to synthesize the correct answer. Try a more capable model, "
        "chain-of-thought prompting, or clearer instruction formatting."
    ),
    "incomplete_answer": (
        "The model's answer missed parts of the ground truth even though relevant "
        "context was retrieved. Prompt for exhaustive answers or expand the "
        "context window."
    ),
    "factually_incorrect": (
        "The answer contradicts the ground truth despite relevant context being "
        "available. Consider a stronger model or an explicit verification step."
    ),
}


def _merge_detail(default: str, detail: dict | None) -> str:
    """Append the judge's specific root cause when one was provided."""
    if not detail:
        return default
    judge_rc = detail.get("root_cause")
    if judge_rc and judge_rc != "none":
        return f"{default} Judge detail: {judge_rc}"
    return default


def _judge_errors(details: dict) -> list[str]:
    """Metric names whose LLM judge call failed (error recorded instead of a score).

    When a judge call raises (network outage, bad model, parse error) the
    engine records ``{"error": ...}`` in that metric's detail slot. The root
    cause must warn the developer that the classification is based on
    incomplete evidence for those metrics.
    """
    failed = []
    for metric in ("faithfulness", "relevance", "correctness", "hallucination"):
        detail = details.get(metric)
        if isinstance(detail, dict) and detail.get("error"):
            failed.append(metric)
    return failed


def _append_judge_caution(root_cause: str, details: dict) -> str:
    """Append a caution note when one or more judge calls failed."""
    failed = _judge_errors(details)
    if not failed:
        return root_cause
    note = (
        "[Caution: LLM judge call(s) failed for "
        + ", ".join(failed)
        + "; scores for those metrics are unreliable]"
    )
    return f"{root_cause} {note}"


def classify_failure(scores: dict, details: dict) -> tuple[str, str]:
    """Return ``(failure_category, root_cause)`` for one evaluated query.

    ``scores``   : metric scores dict (faithfulness, relevance, correctness, ...)
    ``details``  : per-metric judge output, including ``num_chunks_retrieved``
                   and any ``failure_category`` / ``root_cause`` reported by the
                   individual metric judges.
    """
    correctness = scores.get("correctness", 1.0)
    relevance = scores.get("relevance", 1.0)
    faithfulness = scores.get("faithfulness", 1.0)

    # Healthy answer — no failure.
    if correctness >= CORRECTNESS_THRESHOLD:
        return "none", "none"

    rel_detail = details.get("relevance") or {}
    faith_detail = details.get("faithfulness") or {}
    corr_detail = details.get("correctness") or {}
    num_chunks = details.get("num_chunks_retrieved", 0)

    # 1. Retrieval stage — the root cause for most downstream failures.
    if num_chunks == 0:
        return (
            "retrieval_miss",
            _append_judge_caution(
                "No context chunks were retrieved for this query, so the model had no "
                "evidence to answer from. Check the retriever/index and increase top_k.",
                details,
            ),
        )
    rel_cat = rel_detail.get("failure_category")
    if rel_cat == "noisy_retrieval":
        return "noisy_retrieval", _append_judge_caution(
            _merge_detail(ROOT_CAUSES["noisy_retrieval"], rel_detail), details
        )
    if relevance < RELEVANCE_THRESHOLD or rel_cat == "retrieval_miss":
        return "retrieval_miss", _append_judge_caution(
            _merge_detail(ROOT_CAUSES["retrieval_miss"], rel_detail), details
        )

    # 2. Grounding stage — the answer drifted from the evidence.
    faith_cat = faith_detail.get("failure_category")
    if faithfulness < FAITHFULNESS_THRESHOLD or faith_cat == "hallucination":
        return "hallucination", _append_judge_caution(
            _merge_detail(ROOT_CAUSES["hallucination"], faith_detail), details
        )

    # 3. Correctness stage — retrieval and grounding were fine; the mismatch is
    #    between the generated answer and the ground truth.
    corr_cat = corr_detail.get("failure_category")
    if corr_cat == "incomplete_answer":
        return "incomplete_answer", _append_judge_caution(
            _merge_detail(ROOT_CAUSES["incomplete_answer"], corr_detail), details
        )
    if corr_cat == "factually_incorrect":
        return "factually_incorrect", _append_judge_caution(
            _merge_detail(ROOT_CAUSES["factually_incorrect"], corr_detail), details
        )

    # 4. Fallback — everything looked right, the model still got it wrong.
    return "reasoning_error", _append_judge_caution(
        ROOT_CAUSES["reasoning_error"], details
    )