import json
import logging
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

from app.config import get_settings

logger = logging.getLogger(__name__)

# Models with a known max output token budget are limited explicitly so the
# judge returns complete JSON.
MAX_OUTPUT_TOKENS = 2048


@dataclass
class JudgeResponse:
    score: float
    reasoning: str
    details: dict | None = None


class JudgeLLM:
    """Wrapper for LLM-as-judge evaluations.

    Supports three providers:
      - ``ollama``    local/private evaluation (free)
      - ``openai``    high-accuracy judging (GPT models)
      - ``anthropic`` high-accuracy judging (Claude models)

    Every call reports token usage (``usage`` key) so the evaluation engine
    can estimate cost per provider/model.
    """

    def __init__(self, provider: str | None = None, model: str | None = None):
        settings = get_settings()
        self.provider = provider or settings.JUDGE_PROVIDER
        if model:
            self.model = model
        elif self.provider == "openai":
            self.model = settings.OPENAI_MODEL
        elif self.provider == "anthropic":
            self.model = settings.ANTHROPIC_MODEL
        else:
            self.model = settings.JUDGE_MODEL
        self.openai_client = None
        self.anthropic_client = None
        if self.provider == "openai":
            self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        elif self.provider == "anthropic":
            self.anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def judge(self, system_prompt: str, user_prompt: str) -> dict:
        """Send a prompt to the judge LLM and parse JSON response."""
        if self.provider == "ollama":
            return await self._judge_ollama(system_prompt, user_prompt)
        elif self.provider == "anthropic":
            return await self._judge_anthropic(system_prompt, user_prompt)
        else:
            return await self._judge_openai(system_prompt, user_prompt)

    async def _judge_ollama(self, system_prompt: str, user_prompt: str) -> dict:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "format": "json",
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]
            result = json.loads(content)
        # Ollama reports prompt_eval_count / eval_count per chat completion.
        usage = {
            "prompt_tokens": int(data.get("prompt_eval_count") or 0),
            "completion_tokens": int(data.get("eval_count") or 0),
        }
        if isinstance(result, dict):
            result.setdefault("usage", usage)
        return result

    async def _judge_openai(self, system_prompt: str, user_prompt: str) -> dict:
        response = await self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=MAX_OUTPUT_TOKENS,
        )
        content = response.choices[0].message.content
        result = json.loads(content)
        if response.usage and isinstance(result, dict):
            result.setdefault(
                "usage",
                {
                    "prompt_tokens": response.usage.prompt_tokens or 0,
                    "completion_tokens": response.usage.completion_tokens or 0,
                },
            )
        return result

    async def _judge_anthropic(self, system_prompt: str, user_prompt: str) -> dict:
        response = await self.anthropic_client.messages.create(
            model=self.model,
            system=system_prompt,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": user_prompt}],
        )
        # Assemble the text from content blocks (Anthropic returns blocks).
        text_parts = [
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ]
        content = "".join(text_parts)
        result = json.loads(content)
        if response.usage and isinstance(result, dict):
            result.setdefault(
                "usage",
                {
                    "prompt_tokens": response.usage.input_tokens or 0,
                    "completion_tokens": response.usage.output_tokens or 0,
                },
            )
        return result


class MockJudge(JudgeLLM):
    """Mock judge for testing without LLM calls.

    Produces deterministic, well-formed output and a tiny fixed usage figure so
    cost tracking can be exercised end-to-end in tests.
    """

    async def judge(self, system_prompt: str, user_prompt: str) -> dict:
        return {
            "score": 0.85,
            "normalized_score": 0.85,
            "reasoning": "Mock evaluation: consistently high score for testing.",
            "usage": {"prompt_tokens": 120, "completion_tokens": 40},
        }