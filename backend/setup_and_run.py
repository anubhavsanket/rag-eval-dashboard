import httpx
import json
import time
import os

BASE = "http://localhost:8000/api/v1"
SEED_PATH = os.path.join(os.path.dirname(__file__), "seeds", "general_knowledge.json")

# 1. Upload general knowledge dataset
with open(SEED_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

r = httpx.post(f"{BASE}/datasets", json=data)
ds = r.json()
print(f"Dataset uploaded: ID={ds['id']}, Name={ds['name']}, TestCases={ds['test_case_count']}")

# 2. Create a Mock adapter config
r = httpx.post(f"{BASE}/configs", json={
    "name": "Mock Adapter (Testing)",
    "description": "Uses mock responses to test the evaluation pipeline",
    "config": {"adapter_type": "mock"}
})
cfg = r.json()
print(f"Config created: ID={cfg['id']}, Name={cfg['name']}")

# 3. Start evaluation
r = httpx.post(f"{BASE}/evaluate", json={
    "dataset_id": ds["id"],
    "config_id": cfg["id"]
})
run = r.json()
print(f"Evaluation started: RunID={run['id']}, Status={run['status']}")

# 4. Poll until completed
print("Waiting for evaluation to complete...")
for i in range(60):
    time.sleep(2)
    r = httpx.get(f"{BASE}/evaluate/{run['id']}")
    status = r.json()["status"]
    print(f"  Poll {i+1}: status={status}")
    if status in ("completed", "failed"):
        break

# 5. Show results
r = httpx.get(f"{BASE}/evaluate/{run['id']}")
run_data = r.json()
print(f"\nFinal status: {run_data['status']}")
if run_data.get("summary"):
    s = run_data["summary"]
    print(f"  Avg Faithfulness:   {s.get('avg_faithfulness', 0):.1%}")
    print(f"  Avg Relevance:      {s.get('avg_relevance', 0):.1%}")
    print(f"  Avg Correctness:    {s.get('avg_correctness', 0):.1%}")
    print(f"  Avg Hallucination:  {s.get('avg_hallucination', 0):.1%}")
    print(f"  Total Queries:      {s.get('total_queries', 0)}")
    print(f"  Avg Latency:        {s.get('avg_latency_ms', 0):.0f}ms")
