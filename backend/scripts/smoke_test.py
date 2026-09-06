"""Live-server smoke test: exercises the whole public API surface against a
running uvicorn instance (SQLite backend) and asserts expected behavior.

Run:  python scripts/smoke_test.py [base_url]
"""
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8899"
B = f"{BASE}/api/v1"

passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name} {detail}")


def main():
    client = httpx.Client(base_url=BASE, timeout=30.0)

    # ── Health & docs ──────────────────────────────────────────────────────
    r = client.get("/health")
    check("GET /health", r.status_code == 200 and r.json()["status"] == "ok")
    r = client.get("/")
    check("GET / root", r.status_code == 200 and "docs" in r.json())
    r = client.get("/docs")
    check("GET /docs (openapi UI)", r.status_code == 200)

    # ── Datasets CRUD ──────────────────────────────────────────────────────
    r = client.post(
        f"{B}/datasets",
        json={
            "name": "smoke-ds",
            "description": "live smoke dataset",
            "tags": ["smoke"],
            "test_cases": [
                {"query": "What is RAG?", "expected_answer": "Retrieval-Augmented Generation",
                 "context_chunks": ["RAG = Retrieval-Augmented Generation"]},
                {"query": "What is top-k?", "expected_answer": "Number of chunks retrieved",
                 "context_chunks": ["top-k is the number of chunks retrieved"]},
            ],
        },
    )
    check("POST /datasets", r.status_code == 201, r.text)
    ds = r.json()
    ds_id = ds["id"]
    check("dataset has 2 test cases", len(ds["test_cases"]) == 2)

    r = client.get(f"{B}/datasets")
    check("GET /datasets lists 1", r.status_code == 200 and len(r.json()) == 1)

    r = client.get(f"{B}/datasets/{ds_id}")
    check("GET /datasets/{id}", r.status_code == 200 and len(r.json()["test_cases"]) == 2)

    r = client.get(f"{B}/datasets/99999")
    check("GET /datasets/99999 -> 404", r.status_code == 404)

    r = client.post(
        f"{B}/datasets",
        json={"name": "empty-ds", "test_cases": []},
    )
    check("POST /datasets empty cases", r.status_code == 201)
    empty_id = r.json()["id"]

    # ── Configs CRUD ───────────────────────────────────────────────────────
    r = client.post(f"{B}/configs", json={"name": "mock-cfg", "config": {"adapter_type": "mock"}})
    check("POST /configs", r.status_code == 201, r.text)
    cfg_id = r.json()["id"]

    r = client.get(f"{B}/configs")
    check("GET /configs lists 1", r.status_code == 200 and len(r.json()) == 1)

    r = client.get(f"{B}/configs/{cfg_id}")
    check("GET /configs/{id}", r.status_code == 200)

    r = client.get(f"{B}/configs/99999")
    check("GET /configs/99999 -> 404", r.status_code == 404)

    # ── Evaluate (single run) ──────────────────────────────────────────────
    r = client.post(f"{B}/evaluate", json={"dataset_id": ds_id, "config_id": cfg_id})
    check("POST /evaluate", r.status_code == 201, r.text)
    run_id = r.json()["id"]
    check("run starts pending", r.json()["status"] == "pending")

    status = None
    for _ in range(100):
        r = client.get(f"{B}/evaluate/{run_id}")
        status = r.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.2)
    check("run completes", status == "completed", f"status={status}")
    run = r.json()

    summary = run["summary"]
    check("summary has 4 metric avgs",
          all(k in summary for k in ("avg_faithfulness", "avg_relevance", "avg_correctness", "avg_hallucination")))
    check("summary has quality_score", "quality_score" in summary)
    check("summary has failure_distribution", "failure_distribution" in summary)
    check("summary has cost", "total_cost_usd" in summary)
    check("summary has latency percentiles", "p50_latency_ms" in summary and "p95_latency_ms" in summary)
    check("quality_score == 0.85 (mock judge)", abs(summary["quality_score"] - 0.85) < 1e-6,
          f"got {summary.get('quality_score')}")
    check("avg_latency_ms == 50 (mock)", summary["avg_latency_ms"] == 50,
          f"got {summary.get('avg_latency_ms')}")
    check("total_queries == 2", summary["total_queries"] == 2)

    # ── Per-query results ──────────────────────────────────────────────────
    r = client.get(f"{B}/evaluate/{run_id}/results")
    check("GET run results", r.status_code == 200 and len(r.json()) == 2, r.text)
    res = r.json()[0]
    check("result has failure_category + root_cause",
          "failure_category" in res and "root_cause" in res)
    check("result has cost/tokens", "estimated_cost_usd" in res and "tokens_used" in res)
    check("result scores complete", all(k in res["scores"] for k in
                                        ("faithfulness", "relevance", "correctness", "hallucination")))

    r = client.get(f"{B}/evaluate/99999")
    check("GET /evaluate/99999 -> 404", r.status_code == 404)
    r = client.get(f"{B}/evaluate/99999/results")
    check("GET /evaluate/99999/results -> 404", r.status_code == 404)

    # ── Results: runs / compare / failures / export / recommendations ─────
    r = client.get(f"{B}/results/runs")
    check("GET /results/runs lists 1", r.status_code == 200 and len(r.json()) == 1)

    r = client.get(f"{B}/results/compare", params={"ids": f"{run_id}"})
    check("compare <2 ids -> 400", r.status_code == 400)

    # Second run for a real comparison
    r = client.post(f"{B}/evaluate", json={"dataset_id": ds_id, "config_id": cfg_id})
    run2_id = r.json()["id"]
    for _ in range(100):
        r = client.get(f"{B}/evaluate/{run2_id}")
        if r.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.2)
    r = client.get(f"{B}/results/compare", params={"ids": f"{run_id},{run2_id}"})
    check("compare 2 runs -> 200", r.status_code == 200, r.text)
    body = r.json()
    check("compare returns 2 runs + per-query", len(body["runs"]) == 2 and len(body["per_query_comparison"]) == 2)

    r = client.get(f"{B}/results/compare", params={"ids": f"{run_id},99999"})
    check("compare with missing id -> 404", r.status_code == 404)

    r = client.get(f"{B}/results/failures", params={"run_id": run_id})
    check("failures endpoint works (0 findings for healthy)", r.status_code == 200 and r.json()["total"] == 0)

    r = client.get(f"{B}/results/failures", params={"run_id": run_id, "failure_type": "low_correctness", "threshold": 0.9})
    check("failures threshold filter", r.status_code == 200 and r.json()["total"] == 2,
          f"got {r.json()['total']}")

    r = client.get(f"{B}/results/export", params={"run_id": run_id, "format": "json"})
    check("export json", r.status_code == 200 and "query" in r.text)

    r = client.get(f"{B}/results/export", params={"run_id": run_id, "format": "csv"})
    check("export csv", r.status_code == 200 and r.text.startswith("id,query"))

    r = client.get(f"{B}/results/recommendations", params={"run_id": run_id})
    check("recommendations (healthy -> generic)", r.status_code == 200 and len(r.json()["recommendations"]) >= 1)

    r = client.get(f"{B}/results/recommendations", params={"run_id": 99999})
    check("recommendations missing run -> 404", r.status_code == 404)

    # ── Sweeps ─────────────────────────────────────────────────────────────
    # Validation
    r = client.post(f"{B}/evaluate/sweep", json={"name": "x", "dataset_id": 99999, "config_ids": [cfg_id]})
    check("sweep missing dataset -> 404", r.status_code == 404)
    r = client.post(f"{B}/evaluate/sweep", json={"name": "x", "dataset_id": ds_id, "config_ids": [99999]})
    check("sweep missing config -> 404", r.status_code == 404)

    # Real sweep with 2 configs
    r = client.post(f"{B}/configs", json={"name": "mock-cfg2", "config": {"adapter_type": "mock"}})
    cfg2_id = r.json()["id"]
    r = client.post(f"{B}/evaluate/sweep", json={
        "name": "smoke-sweep", "description": "live", "dataset_id": ds_id, "config_ids": [cfg_id, cfg2_id],
    })
    check("POST /evaluate/sweep", r.status_code == 201, r.text)
    sweep_id = r.json()["id"]

    status = None
    for _ in range(150):
        r = client.get(f"{B}/evaluate/sweep/{sweep_id}")
        status = r.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.2)
    check("sweep completes", status == "completed", f"status={status}, body={r.text[:300]}")
    sweep = r.json()
    check("sweep has 2 run_ids", len(sweep["run_ids"]) == 2)
    lb = sweep["summary"]["leaderboard"]
    check("leaderboard has 2 entries", len(lb) == 2)
    if lb:
        scores = [e["quality_score"] for e in lb]
        check("leaderboard sorted desc", scores == sorted(scores, reverse=True), str(scores))
        check("leaderboard entries real (0.85)", all(abs(e["quality_score"] - 0.85) < 1e-6 for e in lb), str(scores))
        check("leaderboard has config_name + cost + tokens",
              all("config_name" in e and "total_cost_usd" in e and "total_tokens" in e for e in lb))

    r = client.get(f"{B}/evaluate/sweep")
    check("GET /evaluate/sweep list (no 422 shadowing)", r.status_code == 200 and len(r.json()) == 1, r.text)

    r = client.get(f"{B}/evaluate/sweep/{sweep_id}/runs")
    check("GET sweep runs", r.status_code == 200 and len(r.json()) == 2, r.text)

    r = client.get(f"{B}/evaluate/sweep/99999/runs")
    check("GET sweep runs missing sweep -> 404", r.status_code == 404)

    # ── Delete protection ──────────────────────────────────────────────────
    r = client.delete(f"{B}/datasets/{ds_id}")
    check("delete referenced dataset -> 409", r.status_code == 409, r.text)
    r = client.delete(f"{B}/configs/{cfg_id}")
    check("delete referenced config -> 409", r.status_code == 409)

    r = client.delete(f"{B}/results/runs/{run_id}")
    check("delete run -> 204", r.status_code == 204)
    r = client.delete(f"{B}/results/runs/{run2_id}")
    check("delete run2 -> 204", r.status_code == 204)

    # Sweep runs are still referenced; deleting sweep dataset still blocked
    r = client.delete(f"{B}/datasets/{ds_id}")
    check("dataset still blocked (sweep runs reference it)", r.status_code == 409)

    # Cleanup: delete sweep runs via sweep runs endpoint ids
    r = client.get(f"{B}/evaluate/sweep/{sweep_id}/runs")
    for run in r.json():
        client.delete(f"{B}/results/runs/{run['id']}")

    r = client.delete(f"{B}/datasets/{ds_id}")
    check("dataset deletable after runs removed", r.status_code == 204)
    r = client.delete(f"{B}/configs/{cfg_id}")
    check("config deletable after runs removed", r.status_code == 204)
    r = client.delete(f"{B}/configs/{cfg2_id}")
    check("config2 deletable", r.status_code == 204)

    r = client.delete(f"{B}/datasets/{empty_id}")
    check("delete unreferenced dataset -> 204", r.status_code == 204)

    # ── 404s on already-deleted rows ───────────────────────────────────────
    r = client.delete(f"{B}/datasets/{ds_id}")
    check("re-delete dataset -> 404", r.status_code == 404)
    r = client.delete(f"{B}/results/runs/{run_id}")
    check("re-delete run -> 404", r.status_code == 404)

    print(f"\n===== SMOKE: {passed} passed, {failed} failed =====")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()