from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/rag_eval"

    # Judge LLM
    JUDGE_PROVIDER: str = "mock"  # "ollama", "openai", or "mock"
    JUDGE_MODEL: str = "llama3.1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Pipeline
    RAG_PIPELINE_URL: str = ""

    # App
    APP_NAME: str = "RAG Evaluation Dashboard"
    DEBUG: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
