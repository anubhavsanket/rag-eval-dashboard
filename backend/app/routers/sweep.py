import asyncio
import logging
import threading
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.models.dataset import Dataset
from app.models.eval_run import EvalRun
from app.models.eval_sweep import EvalSweep
from app.models.rag_config import RAGConfig
from app.routers.evaluate import _run_eval_sync
from app.schemas import SweepCreate, SweepResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/evaluate", tags=["evaluate"])


def _run_sweep_thread(sweep_id: int, dataset_id: int, config_ids: list[int]):
    """Entry point for the sweep background thread.

    Creates its own event loop, runs the sweep logic, handles errors.
    """
    asyncio.run(_run_sweep_inner(sweep_id, dataset_id, config_ids))


async def _run_sweep_inner(sweep_id: int, dataset_id: int, config_ids: list[int]):
    """Run the sweep logic inside a single event loop (called via asyncio.run)."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as _AS
    from app.config import get_settings
    from sqlalchemy import select

    settings = get_settings()
    thread_engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=2)
    thread_session_factory = async_sessionmaker(thread_engine, class_=_AS, expire_on_commit=False)

    try:
        async with thread_session_factory() as db:
            # Load sweep
            result = await db.execute(select(EvalSweep).where(EvalSweep.id == sweep_id))
            sweep = result.scalar_one()
            sweep.status = "running"
            await db.commit()

            run_ids = []
            for config_id in config_ids:
                # Create a run for this config. COMMIT before the worker
                # thread starts so the row is visible to its own session.
                run = EvalRun(dataset_id=dataset_id, config_id=config_id, sweep_id=sweep_id, status="pending")
                db.add(run)
                await db.flush()
                await db.commit()
                await db.refresh(run)
                run_ids.append(run.id)
                logger.info("Created run #%d for sweep %d", run.id, sweep_id)

                # Run evaluation in a background thread (re-uses the same helper)
                await asyncio.to_thread(_run_eval_sync, run.id, dataset_id, config_id)

            # Sweep complete — build leaderboard
            await _finalize_sweep(sweep_id, run_ids, db)

    except Exception as e:
        logger.error("Background sweep %d failed: %s", sweep_id, e, exc_info=True)
        # Mark sweep as failed in a new session
        async with thread_session_factory() as db:
            result = await db.execute(select(EvalSweep).where(EvalSweep.id == sweep_id))
            sweep = result.scalar_one_or_none()
            if sweep:
                sweep.status = "failed"
                sweep.completed_at = datetime.now()
                sweep.summary = {"error": str(e)}
                await db.commit()
    finally:
        await thread_engine.dispose()
async def _finalize_sweep(sweep_id: int, run_ids: list[int], db: AsyncSession):
    """Compute leaderboard and mark sweep completed.

    ``populate_existing`` is required: the sweep's session created these runs
    and would otherwise return its own stale identity-map instances instead of
    the summaries committed by the worker threads.
    """
    result = await db.execute(
        select(EvalSweep).where(EvalSweep.id == sweep_id).execution_options(populate_existing=True)
    )
    sweep = result.scalar_one()

    leaderboard = []
    for run_id in run_ids:
        result = await db.execute(
            select(EvalRun).where(EvalRun.id == run_id).execution_options(populate_existing=True)
        )
        run = result.scalar_one()
        summary = run.summary or {}
        # Pull config name for display
        result = await db.execute(
            select(RAGConfig).where(RAGConfig.id == run.config_id).execution_options(populate_existing=True)
        )
        config = result.scalar_one()

        leaderboard.append({
            "run_id": run.id,
            "config_id": run.config_id,
            "config_name": config.name,
            "status": run.status,
            "quality_score": summary.get("quality_score", 0),
            "avg_correctness": summary.get("avg_correctness", 0),
            "avg_faithfulness": summary.get("avg_faithfulness", 0),
            "avg_relevance": summary.get("avg_relevance", 0),
            "avg_hallucination": summary.get("avg_hallucination", 0),
            "avg_latency_ms": summary.get("avg_latency_ms", 0),
            "total_cost_usd": summary.get("total_cost_usd", 0),
            "total_tokens": summary.get("total_tokens", 0),
        })

    # Sort by quality_score desc (stable — keeps insertion order for ties)
    leaderboard.sort(key=lambda x: x["quality_score"], reverse=True)

    sweep.run_ids = run_ids
    sweep.summary = {"leaderboard": leaderboard}
    sweep.status = "completed"
    sweep.completed_at = datetime.now()
    await db.commit()


@router.post("/sweep", response_model=SweepResponse, status_code=201)
async def start_sweep(
    data: SweepCreate,
    db: AsyncSession = Depends(get_db),
):
    """Start a sweep: run multiple configs against one dataset."""
    # Validate dataset exists
    result = await db.execute(select(Dataset).where(Dataset.id == data.dataset_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Validate configs exist
    result = await db.execute(select(RAGConfig).where(RAGConfig.id.in_(data.config_ids)))
    configs = list(result.scalars().all())
    if len(configs) != len(data.config_ids):
        raise HTTPException(status_code=404, detail="One or more config IDs not found")

    sweep = EvalSweep(
        name=data.name,
        description=data.description,
        dataset_id=data.dataset_id,
        status="pending",
    )
    db.add(sweep)
    await db.flush()
    await db.refresh(sweep)
    await db.commit()

    logger.info("Created sweep #%d (%d configs), starting background thread", sweep.id, len(data.config_ids))

    thread = threading.Thread(
        target=_run_sweep_thread,
        args=(sweep.id, data.dataset_id, data.config_ids),
        daemon=True,
    )
    thread.start()

    return SweepResponse.model_validate(sweep)


@router.get("/sweep", response_model=list[SweepResponse])
async def list_sweeps(db: AsyncSession = Depends(get_db)):
    """List all sweeps, newest first."""
    result = await db.execute(select(EvalSweep).order_by(EvalSweep.created_at.desc()))
    return [SweepResponse.model_validate(s) for s in result.scalars().all()]


@router.get("/sweep/{sweep_id}", response_model=SweepResponse)
async def get_sweep(sweep_id: int, db: AsyncSession = Depends(get_db)):
    """Get sweep status and leaderboard summary."""
    result = await db.execute(select(EvalSweep).where(EvalSweep.id == sweep_id))
    sweep = result.scalar_one_or_none()
    if not sweep:
        raise HTTPException(status_code=404, detail="Sweep not found")
    return SweepResponse.model_validate(sweep)


@router.get("/sweep/{sweep_id}/runs", response_model=list)
async def get_sweep_runs(sweep_id: int, db: AsyncSession = Depends(get_db)):
    """List all runs belonging to a sweep."""
    result = await db.execute(select(EvalSweep).where(EvalSweep.id == sweep_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Sweep not found")
    result = await db.execute(select(EvalRun).where(EvalRun.sweep_id == sweep_id).order_by(EvalRun.id))
    runs = result.scalars().all()
    # Return lightweight run summaries
    return [
        {
            "id": r.id,
            "dataset_id": r.dataset_id,
            "config_id": r.config_id,
            "status": r.status,
            "summary": r.summary,
            "created_at": r.created_at,
            "completed_at": r.completed_at,
        }
        for r in runs
    ]