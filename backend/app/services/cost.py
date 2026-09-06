"""Token cost tracking across judge providers.

Pricing is expressed in USD per 1M tokens. Local providers (Ollama) are free.
Rates are approximate public list prices and are configurable via env vars:
``COST_OVERRIDES`` may carry a JSON object matching this module's shape to
override any entry, e.g. ``{"openai": {"gpt-4o-mini": {"input": 0.15, "output": 0.6}}}``.
"""

import json
import os

# USD per 1M tokens.
PRICING: dict[str, dict[str, dict[str, float]]] = {
    "openai": {
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
        "gpt-4.1": {"input": 2.00, "output": 8.00},
    },
    "anthropic": {
        "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.00},
        "claude-3-5-sonnet-latest": {"input": 3.00, "output": 15.00},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
    },
    "ollama": {
        # Local inference — no direct token cost.
        "*": {"input": 0.0, "output": 0.0},
    },
}

_override_raw = os.getenv("COST_OVERRIDES", "")
if _override_raw:
    try:
        _overrides = json.loads(_override_raw)
        for provider, models in _overrides.items():
            PRICING.setdefault(provider, {}).update(models or {})
    except json.JSONDecodeError:
        pass


def get_rates(provider: str, model: str) -> tuple[float, float]:
    """Return (input, output) USD-per-1M-token rates for a provider/model.

    Falls back to a 0 rate when the provider/model is unknown so cost
    tracking never crashes on new models.
    """
    provider_pricing = PRICING.get(provider.lower(), {})
    model_pricing = provider_pricing.get(model, provider_pricing.get("*"))
    if not model_pricing:
        return 0.0, 0.0
    return model_pricing.get("input", 0.0), model_pricing.get("output", 0.0)


def estimate_cost_usd(
    provider: str, model: str, prompt_tokens: int, completion_tokens: int
) -> float:
    """Estimate cost of a single LLM call using exact token split when known."""
    in_rate, out_rate = get_rates(provider, model)
    return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000


def estimate_cost_blended(
    provider: str, model: str, total_tokens: int
) -> float:
    """Estimate cost from total tokens using the blended (average) rate.

    Used when the pipeline only reports an aggregate token count without a
    prompt/completion split.
    """
    if total_tokens <= 0:
        return 0.0
    in_rate, out_rate = get_rates(provider, model)
    blended = (in_rate + out_rate) / 2
    return total_tokens * blended / 1_000_000