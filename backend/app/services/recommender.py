"""Optimization recommender: turn a failure distribution into suggested config tweaks.

The recommender inspects the dominant failure categories in a run/sweep and
emits a prioritized list of concrete configuration changes the user can try.
It is intentionally a deterministic rule engine so it works without an LLM and
the same inputs always yield the same suggestions (important for a "Phase 3
advanced intelligence" feature that is meant to be auditable).
"""

from collections import Counter

# Each rule is ``(predicate, suggestion)``. ``predicate`` receives a Counter of
# failure categories for a run/sweep and returns True when the suggestion should fire.
# The Counter includes ``"none"`` for healthy answers, so non-"none" entries are failures.

_RULES = [
    (
        lambda c: c.get("retrieval_miss", 0) > 0
        and c.get("retrieval_miss", 0) >= c.get("noisy_retrieval", 0)
        and c.get("retrieval_miss", 0) >= max(sum(c.values()) * 0.15, 1),
        "Increase top_k on the retriever (relevant docs are not making it into the top-k).",
    ),
    (
        lambda c: c.get("noisy_retrieval", 0) > c.get("retrieval_miss", 0)
        and c.get("noisy_retrieval", 0) >= max(sum(c.values()) * 0.10, 1),
        "Lower top_k or add a re-ranking stage — irrelevant chunks are diluting the prompt.",
    ),
    (
        lambda c: c.get("hallucination", 0) >= max(sum(c.values()) * 0.20, 1),
        "Reduce generation temperature and add explicit grounding instructions in the prompt.",
    ),
    (
        lambda c: c.get("reasoning_error", 0) >= max(sum(c.values()) * 0.20, 1),
        "Try a larger/better model, or use chain-of-thought prompting for multi-hop questions.",
    ),
    (
        lambda c: c.get("incomplete_answer", 0) >= max(sum(c.values()) * 0.15, 1),
        "Encourage exhaustive answers ('List all...') and increase the max output token budget.",
    ),
    (
        lambda c: c.get("factually_incorrect", 0) >= max(sum(c.values()) * 0.15, 1),
        "Add an explicit verification step: have the model double-check the answer against the context before responding.",
    ),
    (
        lambda c: sum(1 for k in c if k != "none" and c.get(k, 0) > 0) == 0,
        "No failures detected — try expanding the dataset or testing edge cases before tuning further.",
    ),
]


def recommend(failure_distribution: dict) -> list[str]:
    """Return a deduplicated list of suggestions for a given failure distribution.

    ``failure_distribution`` is a mapping of category → count.
    """
    counter = Counter(failure_distribution or {})
    seen: set[str] = set()
    recommendations: list[str] = []
    for predicate, suggestion in _RULES:
        try:
            if predicate(counter) and suggestion not in seen:
                recommendations.append(suggestion)
                seen.add(suggestion)
        except Exception:
            # Never let the recommender crash the API.
            continue
    if not recommendations:
        recommendations.append(
            "No specific action recommended. Continue monitoring and collecting more eval data."
        )
    return recommendations