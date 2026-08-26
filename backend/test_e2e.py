"""Full end-to-end test: upload dataset, create config, run evaluation, show results."""
import httpx
import json
import time
import os

BASE = "http://localhost:8000/api/v1"
SEED_PATH = os.path.join(os.path.dirname(__file__), "seeds", "general_knowledge.json")


def main():
    # Clean slate - delete any existing datasets
    existing = httpx.get(f"{BASE}/datasets").json()
    for ds in existing:
        httpx.delete(f"{BASE}/datasets/{ds['id']}")
    print("Cleaned existing datasets.\n")

    # 1. Upload dataset
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    ds = httpx.post(f"{BASE}/datasets", json=data).json()
    print(f"1. Dataset: ID={ds['id']}, Name={ds['name']}, TestCases={len(ds.get('test_cases', []))}")

    # 2. Create config
    cfg = httpx.post(f"{BASE}/configs", json={
        "name": "Mock Adapter",
        "description": "Test adapter",
        "config": {"adapter_type": "mock"}
    }).json()
    print(f"2. Config:  ID={cfg['id']}, Name={cfg['name']}")

    # 3. Start evaluation
    run = httpx.post(f"{BASE}/evaluate", json={
        "dataset_id": ds["id"],
        "config_id": cfg["id"]
    }).json()
    run_id = run["id"]
    print(f"3. Run:     ID={run_id}, Status={run['status']}")

    # 4. Poll
    print("\nWaiting for evaluation...")
    for i in range(60):
        time.sleep(1)
        r = httpx.get(f"{BASE}/evaluate/{run_id}").json()
        status = r["status"]
        print(f"   [{i+1}s] status={status}", end="\r")
        if status in ("completed", "failed"):
            print()
            break
    else:
        print("\n   Timeout! Run did not complete.")

    # 5. Results
    r = httpx.get(f"{BASE}/evaluate/{run_id}").json()
    s = r.get("summary", {})
    print(f"\n=== Results ===")
    print(f"  Status:        {r['status']}")
    print(f"  Faithfulness:  {s.get('avg_faithfulness', 0):.1%}")
    print(f"  Relevance:     {s.get('avg_relevance', 0):.1%}")
    print(f"  Correctness:   {s.get('avg_correctness', 0):.1%}")
    print(f"  Hallucination: {s.get('avg_hallucination', 0):.1%}")
    print(f"  Queries:       {s.get('total_queries', 0)}")
    print(f"  Avg Latency:   {s.get('avg_latency_ms', 0):.0f}ms")


if __name__ == "__main__":
    main()
