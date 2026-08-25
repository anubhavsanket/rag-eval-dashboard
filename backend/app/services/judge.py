import json
import logging
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class JudgeResponse:
    score: float
    reasoning: str
    details: dict | None = None


class JudgeLLM:
    """Wrapper for LLM-as-judge evaluations. Supports Ollama and OpenAI."""

    def __init__(self, provider: str | None = None, model: str | None = None):
        settings = get_settings()
        self.provider = provider or settings.JUDGE_PROVIDER
        self.model = model or (
            settings.JUDGE_MODEL if self.provider == "ollama" else settings.OPENAI_MODEL
        )
        self.openai_client = None
        if self.provider == "openai":
            self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def judge(self, system_prompt: str, user_prompt: str) -> dict:
        """Send a prompt to the judge LLM and parse JSON response."""
        if self.provider == "ollama":
            return await self._judge_ollama(system_prompt, user_prompt)
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
            return json.loads(content)

    async def _judge_openai(self, system_prompt: str, user_prompt: str) -> dict:
        response = await self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        content = response.choices[0].message.content
        return json.loads(content)
