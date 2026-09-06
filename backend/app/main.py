from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import get_engine, Base
from app.routers import datasets, configs, evaluate, results, sweep

# Import all models to register them
from app.models import Dataset, TestCase, RAGConfig, EvalRun, EvalResult, EvalSweep

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (use Alembic for production migrations)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="A self-hosted RAG evaluation dashboard for testing and monitoring RAG pipeline quality.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
# NOTE: sweep.router must be registered BEFORE evaluate.router so the literal
# `/sweep` routes win over evaluate's `/{run_id}` path param (which would
# otherwise match "sweep" and return 422 instead of routing to the sweep list).
app.include_router(datasets.router)
app.include_router(configs.router)
app.include_router(sweep.router)
app.include_router(evaluate.router)
app.include_router(results.router)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}