import asyncio
import logging
import threading
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.models.eval_run import EvalRun
from app.models.eval_result import EvalResult
from app.schemas import EvaluateRequest, EvalRunResponse, EvalResultResponse
from app.services.evaluation_engine import EvaluationEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/evaluate", tags=["evaluate"])


def _run_eval_sync(run_id: int, dataset_id: int, config_id: int):
    """Synchronous helper that creates its own event loop and runs the evaluation.

    Each thread gets its own event loop, engine, and session so there is no
    cross-loop connection pool contention.  This is the only reliable approach
    for running background async work from FastAPI when using uvicorn with
    --reload (which uses a subprocess-based reloader that kills threads).
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as _AS
        from app.config import get_settings

        settings = get_settings()
        thread_engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_size=2,
        )
        thread_session_factory = async_sessionmaker(
            thread_engine, class_=_AS, expire_on_commit=False
        )

        async def _inner():
            async with thread_session_factory() as db:
                eval_engine = EvaluationEngine()
                await eval_engine.run_evaluation(run_id, dataset_id, config_id, db)

        loop.run_until_complete(_inner())
        loop.close()
        thread_engine.sync_engine.dispose()

    except Exception as e:
        logger.error("Background evaluation failed for run %d: %s", run_id, e, exc_info=True)
        # Mark run as failed so it doesn't stay stuck in pending/running
        try:
            loop2 = asyncio.new_event_loop()
            asyncio.set_event_loop(loop2)
            from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as _AS
            from app.config import get_settings

            settings = get_settings()
            err_engine = create_async_engine(settings.DATABASE_URL, echo=False)
            err_factory = async_sessionmaker(err_engine, class_=_AS, expire_on_commit=False)

            async def _mark_failed():
                async with err_factory() as db:
                    result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
                    run = result.scalar_one_or_none()
                    if run:
                        run.status = "failed"
                        run.completed_at = datetime.now()
                        run.summary = {"error": str(e), "total_queries": 0}
                        await db.commit()

            loop2.run_until_complete(_mark_failed())
            loop2.close()
            err_engine.sync_engine.dispose()
        except Exception as ce:
            logger.error("Failed to mark run %d as failed: %s", run_id, ce)


@router.post("", response_model=EvalRunResponse, status_code=201)
async def start_evaluation(
    data: EvaluateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Start a new evaluation run."""
    run = EvalRun(
        dataset_id=data.dataset_id,
        config_id=data.config_id,
        status="pending",
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)

    # Commit immediately so the background thread can reliably fetch the run
    await db.commit()

    logger.info("Created evaluation run #%d, starting background thread", run.id)

    # Use a plain daemon thread.  Each thread gets its own engine/session/loop
    # so there is no cross-loop pool contention.
    thread = threading.Thread(
        target=_run_eval_sync,
        args=(run.id, data.dataset_id, data.config_id),
        daemon=True,
    )
    thread.start()

    return EvalRunResponse.model_validate(run)


@router.get("/{run_id}", response_model=EvalRunResponse)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    """Get evaluation run status and summary."""
    result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return EvalRunResponse.model_validate(run)


@router.get("/{run_id}/results", response_model=list[EvalResultResponse])
async def get_run_results(run_id: int, db: AsyncSession = Depends(get_db)):
    """Get per-query results for a run."""
    result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Run not found")
    result = await db.execute(
        select(EvalResult).where(EvalResult.run_id == run_id).order_by(EvalResult.id)
    )
    return [EvalResultResponse.model_validate(r) for r in result.scalars().all()]
