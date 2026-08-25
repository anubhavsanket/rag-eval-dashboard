from datetime import datetime
from pydantic import BaseModel, Field


# Dataset schemas
class TestCaseCreate(BaseModel):
    query: str
    expected_answer: str
    context_chunks: list[str] = []
    metadata: dict = {}


class DatasetCreate(BaseModel):
    name: str
    description: str | None = None
    tags: list[str] = []
    test_cases: list[TestCaseCreate] = []


class TestCaseResponse(BaseModel):
    id: int
    query: str
    expected_answer: str
    context_chunks: list[str]
    metadata: dict

    model_config = {"from_attributes": True}


class DatasetResponse(BaseModel):
    id: int
    name: str
    description: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    test_case_count: int = 0

    model_config = {"from_attributes": True}


class DatasetDetailResponse(DatasetResponse):
    test_cases: list[TestCaseResponse] = []


# RAG Config schemas
class RAGConfigCreate(BaseModel):
    name: str
    description: str | None = None
    config: dict


class RAGConfigResponse(BaseModel):
    id: int
    name: str
    description: str | None
    config: dict
    created_at: datetime

    model_config = {"from_attributes": True}


# Eval Run schemas
class EvaluateRequest(BaseModel):
    dataset_id: int
    config_id: int


class EvalRunResponse(BaseModel):
    id: int
    dataset_id: int
    config_id: int
    status: str
    summary: dict
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvalResultResponse(BaseModel):
    id: int
    run_id: int
    test_case_id: int
    query: str
    answer: str
    retrieved_chunks: list[dict]
    scores: dict
    latency_ms: int | None
    tokens_used: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# Comparison schemas
class CompareResponse(BaseModel):
    runs: list[EvalRunResponse]
    per_query_comparison: list[dict]
