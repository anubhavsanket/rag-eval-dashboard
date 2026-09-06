import csv
import io
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.models.eval_run import EvalRun
from app.models.eval_result import EvalResult
from app.schemas import EvalRunResponse, EvalResultResponse

router = APIRouter(prefix="/api/v1/results", tags=["results"])


@router.get("/runs", response_model=list[EvalRunResponse])
async def list_runs(
    status: str | None = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
):
    """List all evaluation runs."""
    query = select(EvalRun).order_by(EvalRun.created_at.desc())
    if status:
        query = query.where(EvalRun.status == status)
    result = await db.execute(query)
    return [EvalRunResponse.model_validate(r) for r in result.scalars().all()]


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an evaluation run and all its results."""
    result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    await db.delete(run)


@router.get("/compare")
async def compare_runs(
    ids: str = Query(..., description="Comma-separated run IDs"),
    db: AsyncSession = Depends(get_db),
):
    """Compare multiple runs side by side."""
    run_ids = [int(id.strip()) for id in ids.split(",")]
    if len(run_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 run IDs required")

    # Fetch runs
    result = await db.execute(select(EvalRun).where(EvalRun.id.in_(run_ids)))
    runs = result.scalars().all()
    if not runs:
        raise HTTPException(status_code=404, detail="No runs found")
    # Validate ALL requested runs exist — partial comparisons silently hide
    # missing data and are almost always a stale-ID bug on the client side.
    found_ids = {r.id for r in runs}
    missing = [rid for rid in run_ids if rid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Runs not found: {', '.join(str(m) for m in missing)}",
        )

    # Fetch results for each run
    per_query = []
    for run in runs:
        result = await db.execute(
            select(EvalResult)
            .where(EvalResult.run_id == run.id)
            .order_by(EvalResult.test_case_id)
        )
        results = result.scalars().all()
        per_query.append(
            {
                "run_id": run.id,
                "results": [EvalResultResponse.model_validate(r).model_dump() for r in results],
            }
        )

    return {
        "runs": [EvalRunResponse.model_validate(r).model_dump() for r in runs],
        "per_query_comparison": per_query,
    }


@router.get("/failures")
async def get_failures(
    run_id: int = Query(..., description="Run ID to check"),
    failure_type: str = Query("hallucination", description="Type: hallucination, low_faithfulness, low_relevance, low_correctness"),
    threshold: float = Query(0.5, description="Score threshold below which counts as failure"),
    db: AsyncSession = Depends(get_db),
):
    """Get failures filtered by type."""
    result = await db.execute(
        select(EvalResult).where(EvalResult.run_id == run_id)
    )
    results = result.scalars().all()

    failures = []
    score_key_map = {
        "hallucination": "hallucination",
        "low_faithfulness": "faithfulness",
        "low_relevance": "relevance",
        "low_correctness": "correctness",
    }
    score_key = score_key_map.get(failure_type, "hallucination")

    for r in results:
        score = r.scores.get(score_key, 1.0)
        if score < threshold:
            failures.append(
                {
                    "id": r.id,
                    "query": r.query,
                    "answer": r.answer,
                    "failure_type": failure_type,
                    "score": score,
                    "scores": r.scores,
                }
            )

    return {"failures": failures, "total": len(failures)}


@router.get("/export")
async def export_results(
    run_id: int = Query(..., description="Run ID to export"),
    format: str = Query("json", description="Export format: json or csv"),
    db: AsyncSession = Depends(get_db),
):
    """Export results as CSV or JSON."""
    result = await db.execute(
        select(EvalResult).where(EvalResult.run_id == run_id).order_by(EvalResult.id)
    )
    results = result.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["id", "query", "answer", "faithfulness", "relevance", "correctness", "hallucination", "latency_ms"]
        )
        for r in results:
            writer.writerow(
                [
                    r.id,
                    r.query,
                    r.answer,
                    r.scores.get("faithfulness", 0),
                    r.scores.get("relevance", 0),
                    r.scores.get("correctness", 0),
                    r.scores.get("hallucination", 0),
                    r.latency_ms,
                ]
            )
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=eval_run_{run_id}.csv"},
        )
    else:
        data = [EvalResultResponse.model_validate(r).model_dump() for r in results]

        # Helper to make dicts JSON serializable (converts datetimes to ISO strings)
        def json_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError("Type %s not serializable" % type(obj))

        return StreamingResponse(
            iter([json.dumps(data, indent=2, default=json_serializer)]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=eval_run_%d.json" % run_id},
        )


@router.get("/recommendations")
async def get_recommendations(
    run_id: int = Query(..., description="Run ID"),
    db: AsyncSession = Depends(get_db),
):
    """Return configuration tuning recommendations based on failure patterns."""
    from app.services.recommender import recommend

    # Get failure distribution from the run's summary
    result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    failure_dist = run.summary.get("failure_distribution", {}) if run.summary else {}
    recs = recommend(failure_dist)
    return {"run_id": run_id, "recommendations": recs}
