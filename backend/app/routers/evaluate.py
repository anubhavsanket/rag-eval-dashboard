import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db, async_session
from app.models.eval_run import EvalRun
from app.models.eval_result import EvalResult
from app.schemas import EvaluateRequest, EvalRunResponse, EvalResultResponse
from app.services.evaluation_engine import EvaluationEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/evaluate", tags=["evaluate"])


async def _run_evaluation_background(run_id: int, dataset_id: int, config_id: int):
    """Background task to run evaluation."""
    try:
        logger.info(f"Background task starting for run {run_id}")
        async with async_session() as db:
            engine = EvaluationEngine()
            await engine.run_evaluation(run_id, dataset_id, config_id, db)
        logger.info(f"Background task completed for run {run_id}")
    except Exception as e:
        logger.error(f"Background evaluation failed for run {run_id}: {e}", exc_info=True)


def _run_in_thread(run_id: int, dataset_id: int, config_id: int):
    """Run evaluation in a background thread with its own event loop."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run_evaluation_background(run_id, dataset_id, config_id))
    finally:
        loop.close()


@router.post("", response_model=EvalRunResponse, status_code=201)
async def start_evaluation(
    data: EvaluateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Start a new evaluation run."""
    import threading

    run = EvalRun(
        dataset_id=data.dataset_id,
        config_id=data.config_id,
        status="pending",
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)

    # Run evaluation in a background thread (reliable with uvicorn reloader)
    thread = threading.Thread(
        target=_run_in_thread,
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
    result = await db.execute(
        select(EvalResult).where(EvalResult.run_id == run_id).order_by(EvalResult.id)
    )
    return [EvalResultResponse.model_validate(r) for r in result.scalars().all()]
