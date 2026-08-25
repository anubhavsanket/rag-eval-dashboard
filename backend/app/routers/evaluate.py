import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db, async_session
from app.models.eval_run import EvalRun
from app.models.eval_result import EvalResult
from app.schemas import EvaluateRequest, EvalRunResponse, EvalResultResponse
from app.services.evaluation_engine import EvaluationEngine

router = APIRouter(prefix="/api/v1/evaluate", tags=["evaluate"])


@router.post("", response_model=EvalRunResponse, status_code=201)
async def start_evaluation(data: EvaluateRequest, db: AsyncSession = Depends(get_db)):
    """Start a new evaluation run."""
    run = EvalRun(
        dataset_id=data.dataset_id,
        config_id=data.config_id,
        status="pending",
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)

    # Run evaluation in background
    engine = EvaluationEngine()

    async def _run_background():
        async with async_session() as background_db:
            await engine.run_evaluation(run.id, data.dataset_id, data.config_id, background_db)

    asyncio.create_task(_run_background())

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
