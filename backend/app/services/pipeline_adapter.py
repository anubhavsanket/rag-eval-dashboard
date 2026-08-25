from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time

import httpx


@dataclass
class PipelineResponse:
    answer: str
    retrieved_chunks: list[dict] = field(default_factory=list)
    latency_ms: int = 0
    tokens_used: int = 0


class PipelineAdapter(ABC):
    @abstractmethod
    async def query(self, question: str) -> PipelineResponse:
        """Send a query to the RAG pipeline and return the response."""
        ...


class HTTPAdapter(PipelineAdapter):
    """Generic adapter that calls any external RAG API endpoint."""

    def __init__(self, endpoint_url: str):
        self.endpoint_url = endpoint_url

    async def query(self, question: str) -> PipelineResponse:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.endpoint_url,
                json={"query": question},
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = int((time.monotonic() - start) * 1000)
        return PipelineResponse(
            answer=data.get("answer", ""),
            retrieved_chunks=data.get("retrieved_chunks", []),
            latency_ms=latency_ms,
            tokens_used=data.get("tokens_used", 0),
        )


class LocalBrainNotesAdapter(PipelineAdapter):
    """Adapter for LocalBrainNotes (Ollama + ChromaDB)."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    async def query(self, question: str) -> PipelineResponse:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/api/query",
                json={"query": question},
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = int((time.monotonic() - start) * 1000)
        return PipelineResponse(
            answer=data.get("answer", ""),
            retrieved_chunks=data.get("retrieved_chunks", []),
            latency_ms=latency_ms,
            tokens_used=data.get("tokens_used", 0),
        )


class MockAdapter(PipelineAdapter):
    """Mock adapter for testing without a real RAG pipeline."""

    async def query(self, question: str) -> PipelineResponse:
        return PipelineResponse(
            answer=f"This is a mock answer for: {question}",
            retrieved_chunks=[
                {"chunk_id": 1, "text": "Mock context chunk 1", "score": 0.9},
                {"chunk_id": 2, "text": "Mock context chunk 2", "score": 0.7},
            ],
            latency_ms=50,
            tokens_used=100,
        )


def get_adapter(config: dict) -> PipelineAdapter:
    """Factory function to create the appropriate adapter based on config."""
    adapter_type = config.get("adapter_type", "mock")

    if adapter_type == "http":
        return HTTPAdapter(endpoint_url=config.get("endpoint_url", ""))
    elif adapter_type == "local_brain_notes":
        return LocalBrainNotesAdapter(base_url=config.get("base_url", "http://localhost:8000"))
    else:
        return MockAdapter()
