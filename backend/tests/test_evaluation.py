"""End-to-end tests for the evaluation engine, failure classification,
cost tracking, sweep orchestration, and recommendations.

Tests verify PRD features:
  §3.2  Deep Root Cause Analysis (six failure modes + NL root cause)
  §3.1  Optimization Sweeps (API, leaderboard, summary)
  §3.3  Cost Tracking (judge + pipeline blended estimates)
  §3.3  Optimization Recommender (rule-based config suggestions)
"""
import os
import tempfile
import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.failure_classifier import classify_failure, ROOT_CAUSES
from app.services.cost import estimate_cost_usd, estimate_cost_blended, PRICING
from app.services.recommender import recommend
from app.services.evaluation_engine import EvaluationEngine


# ─── Failure Classification Tests ───────────────────────────────────────────────

def test_classify_retrieval_miss():
    cat, cause = classify_failure(
        {"correctness": 0.3, "relevance": 0.2, "faithfulness": 0.9},
        {"relevance": {"failure_category": "retrieval_miss", "root_cause": "missing"},
         "num_chunks_retrieved": 2},
    )
    assert cat == "retrieval_miss"
    assert "relevant information was not present" in cause


def test_classify_noisy_retrieval():
    """Explicit noisy_retrieval flag must take priority over threshold-based miss."""
    cat, cause = classify_failure(
        {"correctness": 0.4, "relevance": 0.3, "faithfulness": 0.8},
        {"relevance": {"failure_category": "noisy_retrieval", "root_cause": "too much noise"},
         "num_chunks_retrieved": 10},
    )
    assert cat == "noisy_retrieval"
    assert "Irrelevant chunks" in cause


def test_classify_hallucination():
    cat, cause = classify_failure(
        {"correctness": 0.5, "relevance": 0.9, "faithfulness": 0.2},
        {"faithfulness": {"failure_category": "hallucination", "root_cause": "fabricated data"},
         "num_chunks_retrieved": 3},
    )
    assert cat == "hallucination"
    assert ROOT_CAUSES["hallucination"] in cause


def test_classify_reasoning_error():
    cat, cause = classify_failure(
        {"correctness": 0.3, "relevance": 0.8, "faithfulness": 0.9},
        {"num_chunks_retrieved": 5},
    )
    assert cat == "reasoning_error"


def test_classify_incomplete_answer():
    cat, cause = classify_failure(
        {"correctness": 0.5, "relevance": 0.9, "faithfulness": 0.9},
        {"correctness": {"failure_category": "incomplete_answer", "root_cause": "missed detail"},
         "num_chunks_retrieved": 4},
    )
    assert cat == "incomplete_answer"


def test_classify_factually_incorrect():
    cat, cause = classify_failure(
        {"correctness": 0.4, "relevance": 0.9, "faithfulness": 0.9},
        {"correctness": {"failure_category": "factually_incorrect", "root_cause": "contradicts"},
         "num_chunks_retrieved": 3},
    )
    assert cat == "factually_incorrect"


def test_classify_healthy_answer():
    cat, cause = classify_failure(
        {"correctness": 0.85, "relevance": 0.8, "faithfulness": 0.9},
        {"num_chunks_retrieved": 3},
    )
    assert cat == "none"
    assert cause == "none"


# ─── Summary Aggregation Tests ─────────────────────────────────────────────────

def test_summary_includes_quality_score_and_failure_distribution():
    """PRD Phase 1 §5: summary must have quality_score and failure_distribution."""
    from app.services.evaluation_engine import EvaluationEngine

    # Mock EvalMetrics objects
    class FakeMetrics:
        def __init__(self, cat):
            self.faithfulness = 0.85 if cat == "none" else 0.4
            self.relevance = 0.8 if cat == "none" else 0.3
            self.correctness = 0.9 if cat == "none" else 0.5
            self.hallucination = 0.85
            self.latency_ms = 100
            self.tokens_used = 50
            self.cost_usd = 0.001
            self.failure_category = cat
            self.root_cause = "none" if cat == "none" else "test"
            self.details = {"judge_tokens": 10}

    summary = EvaluationEngine._compute_summary([
        FakeMetrics("none"),
        FakeMetrics("retrieval_miss"),
        FakeMetrics("hallucination"),
    ])
    assert "quality_score" in summary
    assert "failure_distribution" in summary
    assert summary["failure_distribution"]["none"] == 1
    assert summary["failure_distribution"]["retrieval_miss"] == 1
    assert summary["failure_distribution"]["hallucination"] == 1
    assert "avg_latency_ms" in summary
    assert "total_cost_usd" in summary


# ─── Cost Tracking Tests ────────────────────────────────────────────────────────

def test_cost_pricing_table_has_all_providers():
    """PRD §4 architecture lists Ollama, OpenAI, Anthropic."""
    assert "ollama" in PRICING
    assert "openai" in PRICING
    assert "anthropic" in PRICING
    # Ollama is free
    assert PRICING["ollama"]["*"]["input"] == 0.0


def test_cost_openai_gpt4o_mini():
    """$0.15/M input + $0.60/M output → 1M input + 2M output = $0.15 + $1.20 = $1.35."""
    cost = estimate_cost_usd("openai", "gpt-4o-mini", 1_000_000, 2_000_000)
    assert abs(cost - 1.35) < 0.01


def test_cost_ollama_free():
    cost = estimate_cost_usd("ollama", "llama3.1", 1_000_000, 500_000)
    assert cost == 0.0


def test_cost_blended():
    """Blended uses average input+output rate."""
    blended = estimate_cost_blended("openai", "gpt-4o-mini", 500)
    # Rate for gpt-4o-mini: (0.15+0.60)/2 = 0.375 per 1M tokens; 500 tokens = 0.0001875
    assert abs(blended - 0.0001875) < 0.00001


# ─── Recommender Tests ─────────────────────────────────────────────────────────

def test_recommender_fires_for_each_mode():
    """Every PRD failure mode must produce at least one suggestion."""
    distributions = [
        {"retrieval_miss": 20, "none": 80},
        {"noisy_retrieval": 15, "none": 85},
        {"hallucination": 20, "none": 80},
        {"reasoning_error": 20, "none": 80},
        {"incomplete_answer": 20, "none": 80},
        {"factually_incorrect": 20, "none": 80},
    ]
    for dist in distributions:
        recs = recommend(dist)
        assert len(recs) >= 1
        assert recs[0] != "No specific action recommended."


def test_recommender_healthy_runs_generic_fallback():
    recs = recommend({"none": 100})
    assert len(recs) == 1


# ─── Integration Tests ─────────────────────────────────────────────────────────

def test_models_schema_creates_on_sqlite():
    """Models must create all tables on SQLite (used by the test suite)."""
    from app.db import Base

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}", echo=False)

    import asyncio
    async def run_test():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return True

    asyncio.run(run_test())

    # Sync inspector works for SQLite
    import asyncio
    from sqlalchemy import create_engine
    from sqlalchemy import inspect as sqlalchemy_inspect

    async def inspect_tables():
        sync_engine = create_engine(f"sqlite:///{path}")
        insp = sqlalchemy_inspect(sync_engine)
        table_names = set(insp.get_table_names() if hasattr(insp, 'get_table_names') else [])
        if not table_names:
            # Fallback: raw PRAGMA
            with sync_engine.connect() as conn:
                result = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                table_names = {row[0] for row in result}
        sync_engine.dispose()
        return table_names

    table_names = asyncio.run(inspect_tables())
    expected = {"datasets", "test_cases", "rag_configs", "eval_runs", "eval_results", "eval_sweeps"}
    assert expected == table_names, f"Missing: {expected - table_names}"

    import asyncio
    async def cleanup():
        await engine.dispose()

    asyncio.run(cleanup())
    # Small delay to release Windows file handle before unlink
    import time
    time.sleep(0.1)
    try:
        os.unlink(path)
    except PermissionError:
        pass  # Windows may hold handle briefly


def test_sweep_api_accepts_valid_payload():
    """Sweep endpoint must accept a valid payload and return a structured response.

    Also verifies dataset/config validation: sweeps with missing references are
    rejected with 404 instead of creating a doomed background sweep.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{path}"
    from app.config import get_settings
    get_settings.cache_clear()

    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200

        # Dataset/config validation: non-existent references → 404
        r = client.post(
            "/api/v1/evaluate/sweep",
            json={"name": "missing", "dataset_id": 999, "config_ids": [1, 2]},
        )
        assert r.status_code == 404

        # Seed a dataset and configs
        r = client.post(
            "/api/v1/datasets",
            json={
                "name": "probe-ds",
                "test_cases": [
                    {"query": "q1", "expected_answer": "a1", "context_chunks": ["c1"]},
                    {"query": "q2", "expected_answer": "a2", "context_chunks": ["c2"]},
                ],
            },
        )
        assert r.status_code == 201
        ds_id = r.json()["id"]

        cfg_ids = []
        for name in ("cfg-a", "cfg-b"):
            r = client.post(
                "/api/v1/configs",
                json={"name": name, "config": {"adapter_type": "mock"}},
            )
            assert r.status_code == 201
            cfg_ids.append(r.json()["id"])

        # Valid sweep should be accepted (returns 201)
        r = client.post(
            "/api/v1/evaluate/sweep",
            json={"name": "test-sweep", "dataset_id": ds_id, "config_ids": cfg_ids},
        )
        assert r.status_code == 201
        data = r.json()
        assert "id" in data
        assert data["status"] in ("pending", "running")

        # Poll until the sweep finishes (background thread), then verify
        # the leaderboard was built with real summaries (not zeros).
        sweep_id = data["id"]
        import time
        for _ in range(100):
            r = client.get(f"/api/v1/evaluate/sweep/{sweep_id}")
            status = r.json()["status"]
            if status in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert status == "completed", f"sweep never completed: {r.json()}"
        final = r.json()
        assert len(final["run_ids"]) == 2
        lb = final["summary"]["leaderboard"]
        assert len(lb) == 2
        # Each run must carry its real quality score (stale-summary regression)
        for entry in lb:
            assert entry["quality_score"] == 0.85, entry
            assert entry["status"] == "completed"
            assert entry["config_name"] in ("cfg-a", "cfg-b")
        # Leaderboard sorted desc (tie → stable, either order ok)
        scores = [e["quality_score"] for e in lb]
        assert scores == sorted(scores, reverse=True)

        # Sweep runs endpoint returns both runs with completed summaries
        r = client.get(f"/api/v1/evaluate/sweep/{sweep_id}/runs")
        assert r.status_code == 200
        runs = r.json()
        assert len(runs) == 2
        for run in runs:
            assert run["status"] == "completed"
            assert run["summary"]["quality_score"] == 0.85

        # Per-run results were persisted
        for run in runs:
            r = client.get(f"/api/v1/evaluate/{run['id']}/results")
            assert r.status_code == 200
            assert len(r.json()) == 2  # one result per test case

    import time
    time.sleep(0.1)
    try:
        os.unlink(path)
    except OSError:
        pass  # Windows may hold handle briefly


@pytest.mark.asyncio
async def test_failure_classification_end_to_end():
    """Simulate a full evaluation pipeline: pipeline response → metrics → classification."""
    from app.services.pipeline_adapter import PipelineResponse
    from app.services.judge import MockJudge

    engine = EvaluationEngine(judge=MockJudge())

    # Good case: MockJudge returns 0.85 score >= 0.7 → "none"
    good_resp = PipelineResponse(
        answer="RAG is retrieval-augmented generation.",
        retrieved_chunks=[{"chunk_id": 1, "text": "RAG = Retrieval-Augmented Generation"}],
        latency_ms=50, tokens_used=100,
    )
    metrics = await engine.evaluate_single(
        "What is RAG?", "Retrieval-Augmented Generation", good_resp
    )
    assert metrics.failure_category == "none"
    assert metrics.root_cause == "none"

    # Engine has no async close method (no DB resources owned by it)
    # Nothing to await — the evaluation was fully synchronous to the engine


# ─── Route Conflict Regression Tests ───────────────────────────────────────────

def test_route_sweep_list_not_shadowed_by_run_id():
    """GET /evaluate/sweep must hit the sweep list route, NOT evaluate's
    /{run_id} path param (which would 422 on the literal string "sweep").

    sweep.router is registered before evaluate.router in main.py so its
    literal /sweep route wins over /{run_id}.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        # Literal /sweep -> 200 (empty list, not 422)
        r = client.get("/api/v1/evaluate/sweep")
        assert r.status_code == 200, r.text
        assert r.json() == []

        # Sweep sub-routes still work
        assert client.get("/api/v1/evaluate/sweep/999").status_code == 404
        assert client.get("/api/v1/evaluate/sweep/999/runs").status_code == 404

        # Plain run routes are NOT shadowed by the sweep router
        assert client.get("/api/v1/evaluate/12345").status_code == 404
        assert client.get("/api/v1/evaluate/12345/results").status_code == 404

        # POST /sweep still routes to the sweep creator
        r = client.post(
            "/api/v1/evaluate/sweep",
            json={"name": "x", "dataset_id": 999, "config_ids": [1]},
        )
        assert r.status_code == 404  # dataset validation, not 422/500


# ─── Delete Protection Tests ───────────────────────────────────────────────────

def test_delete_protection_and_orphan_cleanup():
    """Datasets/configs referenced by runs can't be deleted (409); deleting
    the runs first releases them (204); repeat delete -> 404."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        # Seed dataset + config
        r = client.post(
            "/api/v1/datasets",
            json={
                "name": "dp-ds",
                "test_cases": [{"query": "q", "expected_answer": "a", "context_chunks": ["c"]}],
            },
        )
        assert r.status_code == 201
        ds_id = r.json()["id"]

        r = client.post(
            "/api/v1/configs",
            json={"name": "dp-cfg", "config": {"adapter_type": "mock"}},
        )
        assert r.status_code == 201
        cfg_id = r.json()["id"]

        # Deleting a dataset/config with NO runs works
        assert client.delete(f"/api/v1/datasets/{ds_id}").status_code == 204
        assert client.delete(f"/api/v1/configs/{cfg_id}").status_code == 204
        assert client.delete(f"/api/v1/datasets/{ds_id}").status_code == 404
        assert client.delete(f"/api/v1/configs/{cfg_id}").status_code == 404

        # Re-create and attach an evaluation run
        r = client.post(
            "/api/v1/datasets",
            json={
                "name": "dp-ds2",
                "test_cases": [{"query": "q", "expected_answer": "a", "context_chunks": ["c"]}],
            },
        )
        ds_id = r.json()["id"]
        r = client.post(
            "/api/v1/configs",
            json={"name": "dp-cfg2", "config": {"adapter_type": "mock"}},
        )
        cfg_id = r.json()["id"]

        r = client.post("/api/v1/evaluate", json={"dataset_id": ds_id, "config_id": cfg_id})
        assert r.status_code == 201
        run_id = r.json()["id"]

        # Wait for the run to finish evaluating so its background thread is not
        # mid-write to the SQLite file while we delete rows.
        import time
        for _ in range(100):
            r = client.get(f"/api/v1/evaluate/{run_id}")
            if r.json()["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert r.json()["status"] == "completed"

        # Now deletion must be refused with a helpful 409
        r = client.delete(f"/api/v1/datasets/{ds_id}")
        assert r.status_code == 409, r.text
        assert "evaluation run(s)" in r.json()["detail"]

        r = client.delete(f"/api/v1/configs/{cfg_id}")
        assert r.status_code == 409, r.text
        assert "evaluation run(s)" in r.json()["detail"]

        # Deleting the run releases both references
        assert client.delete(f"/api/v1/results/runs/{run_id}").status_code == 204
        assert client.delete(f"/api/v1/datasets/{ds_id}").status_code == 204
        assert client.delete(f"/api/v1/configs/{cfg_id}").status_code == 204

    import time
    time.sleep(0.1)


# ─── Compare Endpoint Tests ────────────────────────────────────────────────────

def test_compare_missing_run_returns_404():
    """Comparing with a non-existent run ID must 404 instead of silently
    returning partial results for the runs that do exist."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        # Create a real run first so the comparison is partial, not empty
        r = client.post(
            "/api/v1/datasets",
            json={
                "name": "cmp-ds",
                "test_cases": [{"query": "q", "expected_answer": "a", "context_chunks": ["c"]}],
            },
        )
        ds_id = r.json()["id"]
        r = client.post(
            "/api/v1/configs",
            json={"name": "cmp-cfg", "config": {"adapter_type": "mock"}},
        )
        cfg_id = r.json()["id"]
        r = client.post("/api/v1/evaluate", json={"dataset_id": ds_id, "config_id": cfg_id})
        run_id = r.json()["id"]

        # One real + one missing ID -> 404 naming the missing ID
        r = client.get("/api/v1/results/compare", params={"ids": f"{run_id},999"})
        assert r.status_code == 404, r.text
        assert "999" in r.json()["detail"]

        # One missing ID among valid-looking ones is still a 404
        r = client.get("/api/v1/results/compare", params={"ids": f"{run_id},1,999"})
        assert r.status_code == 404

        # All-missing IDs -> 404
        r = client.get("/api/v1/results/compare", params={"ids": "777,888"})
        assert r.status_code == 404

        # <2 IDs is a 400
        r = client.get("/api/v1/results/compare", params={"ids": f"{run_id}"})
        assert r.status_code == 400

        # All-real IDs -> 200 (wait for completion so results are present)
        import time
        for _ in range(100):
            r = client.get(f"/api/v1/evaluate/{run_id}")
            if r.json()["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)
        r = client.get("/api/v1/results/compare", params={"ids": f"{run_id}"})
        assert r.status_code == 400  # still needs 2+ … create sibling run
        r = client.post("/api/v1/evaluate", json={"dataset_id": ds_id, "config_id": cfg_id})
        run2 = r.json()["id"]
        for _ in range(100):
            r = client.get(f"/api/v1/evaluate/{run2}")
            if r.json()["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)
        r = client.get("/api/v1/results/compare", params={"ids": f"{run_id},{run2}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["runs"]) == 2
        assert len(body["per_query_comparison"]) == 2


# ─── Classifier Judge-Error Caution Tests ─────────────────────────────────────

def test_classify_judge_error_adds_caution_to_root_cause():
    """When an LLM judge call fails, the root cause must warn the developer
    that the classification rests on unreliable scores."""
    cat, cause = classify_failure(
        {"correctness": 0.3, "relevance": 0.8, "faithfulness": 0.9},
        {
            "num_chunks_retrieved": 5,
            "faithfulness": {"error": "LLM call timed out"},
        },
    )
    assert cat == "reasoning_error"
    assert "Caution: LLM judge call(s) failed for faithfulness" in cause

    # Multiple failed judges are all listed
    cat, cause = classify_failure(
        {"correctness": 0.4, "relevance": 0.9, "faithfulness": 0.9},
        {
            "num_chunks_retrieved": 5,
            "faithfulness": {"error": "boom"},
            "correctness": {"error": "boom"},
        },
    )
    assert cat == "reasoning_error"
    assert "failed for faithfulness, correctness" in cause

    # No judge errors -> no caution note
    cat, cause = classify_failure(
        {"correctness": 0.3, "relevance": 0.8, "faithfulness": 0.9},
        {"num_chunks_retrieved": 5},
    )
    assert "Caution:" not in cause

    # Healthy answers stay "none" even with judge errors
    cat, cause = classify_failure(
        {"correctness": 0.9, "relevance": 0.8, "faithfulness": 0.9},
        {"faithfulness": {"error": "boom"}, "num_chunks_retrieved": 3},
    )
    assert cat == "none"
    assert cause == "none"


# ─── None-Safe Summary Tests ──────────────────────────────────────────────────

def test_summary_avg_is_none_safe_for_latency():
    """A pipeline that reports no latency (None) must not crash the summary;
    the average is computed over the metrics that have values."""
    from app.services.evaluation_engine import EvaluationEngine

    class FakeMetrics:
        def __init__(self, latency):
            self.faithfulness = 0.8
            self.relevance = 0.8
            self.correctness = 0.8
            self.hallucination = 0.8
            self.latency_ms = latency
            self.tokens_used = 10
            self.cost_usd = 0.0
            self.failure_category = "none"
            self.root_cause = "none"
            self.details = {}

    metrics = [FakeMetrics(100), FakeMetrics(None), FakeMetrics(300)]
    summary = EvaluationEngine._compute_summary(metrics)
    # Avg over the two real values; no TypeError from the None entry
    assert summary["avg_latency_ms"] == 200.0
    assert summary["p50_latency_ms"] == 100
    assert summary["p95_latency_ms"] == 300
    assert summary["total_queries"] == 3

    # All-None latencies: percentiles become None, average is 0
    summary = EvaluationEngine._compute_summary([FakeMetrics(None), FakeMetrics(None)])
    assert summary["avg_latency_ms"] == 0.0
    assert summary["p50_latency_ms"] is None
    assert summary["p95_latency_ms"] is None
