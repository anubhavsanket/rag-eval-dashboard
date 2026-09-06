# RAG Intelligence & Optimization Platform

A self-hosted tool to evaluate, diagnose, and optimize Retrieval-Augmented Generation (RAG) pipelines. Run automated evaluations, get LLM-as-judge scores, perform deep root cause analysis, and run configuration sweeps to find what works best for your data.

---

## What This Does

You've got a RAG pipeline. Maybe it's decent, maybe it's a black box. This tool helps you answer two questions:

1. **"Which config actually works best?"** — Run sweeps across models, chunk sizes, top-k values, whatever. Get a ranked leaderboard with quality scores, latency, and cost.
2. **"When it fails, why?"** — Every eval gets a failure category (retrieval miss, hallucination, reasoning error, etc.) and a plain-English root cause. No more guessing.

---

## Key Features

| Feature | What It Gives You |
|---------|-------------------|
| **Automated Evaluation** | Run full test suites against your datasets — faithfulness, relevance, correctness, hallucination |
| **Root Cause Analysis** | 6 failure modes with readable explanations. When the judge errors out, you get a warning note so you know the analysis is incomplete |
| **Optimization Sweeps** | POST `/api/v1/evaluate/sweep` with multiple configs → get a leaderboard sorted by quality score vs. latency/cost |
| **Pluggable Judges** | Ollama (free, local), OpenAI, or Anthropic — swap without code changes |
| **Cost Tracking** | Per-run and per-query cost estimates. Override rates via `COST_OVERRIDES` env var |
| **Delete Protection** | Can't accidentally delete a dataset or config that has run history — 409 with the run count |
| **Strict Compare** | `/results/compare?ids=1,2,3` returns 404 if any ID is missing — no silent partial results |
| **Production Observability** | p50/p95 latency, failure distribution, cost breakdown, quality score |
| **Self-Hosted** | Docker Compose, your data, your infra |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React + TypeScript + Tailwind)               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │Dashboard │ │ Compare  │ │  Query   │ │  Dataset   │ │
│  │          │ │  View    │ │  Details │ │  Manager   │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
└─────────────────────────┬───────────────────────────────┘
                          │ REST API
┌─────────────────────────┴───────────────────────────────┐
│  Backend (FastAPI + SQLAlchemy Async)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │ Dataset  │ │ Sweep    │ │ Evaluate │ │  RCA       │ │
│  │ Manager  │ │Orchestrat│ │  Engine  │ │  Engine    │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
└──────────┬────────────┬────────────┬────────────────────┘
           │            │            │
      ┌────┴────┐ ┌─────┴─────┐ ┌────┴─────┐
      │PostgreSQL│ │  RAG      │ │  Judge   │
      │(results) │ │ Pipeline  │ │  LLM     │
      └─────────┘ │(external) │ │(Ollama/   │
                   └───────────┘ │ OpenAI/   │
                                  │Anthropic) │
                                  └───────────┘
```

---

## Failure Categories

Every evaluated query gets a `failure_category` and `root_cause`:

| Category | What It Means | Typical Fix |
|----------|---------------|-------------|
| `retrieval_miss` | The answer wasn't in the top-k chunks | Increase top-k, better embeddings, check coverage |
| `noisy_retrieval` | Irrelevant chunks confused the LLM | Lower top-k, add re-ranking, tighten threshold |
| `hallucination` | Claims not backed by retrieved context | Stronger grounding, better context, lower temperature |
| `reasoning_error` | Context was right, LLM got the logic wrong | Better model, chain-of-thought, clearer prompts |
| `incomplete_answer` | Missed parts of the ground truth | Prompt for exhaustive answers, increase token budget |
| `factually_incorrect` | Contradicts ground truth | Add verification step, stronger model |

When judge calls fail, the root cause includes a note like:  
`[Caution: LLM judge call(s) failed for faithfulness, correctness; scores for those metrics are unreliable]`

---

## Cost Tracking

Costs are estimated in USD per 1M tokens:

| Provider | Models | Rate |
|----------|--------|------|
| **Ollama** | Any local model | Free |
| **OpenAI** | gpt-4o-mini, gpt-4o, gpt-4.1-mini, gpt-4.1 | ~$0.15–$10/M |
| **Anthropic** | claude-3-5-haiku, claude-3-5-sonnet, claude-3-haiku | ~$0.25–$15/M |

Add to `summary.total_cost_usd` and each result's `estimated_cost_usd`. Override via env:

```bash
COST_OVERRIDES='{"openai":{"gpt-4o-mini":{"input":0.15,"output":0.6}}}'
```

---

## Sweeps — Finding the Best Config

```bash
# 1. Create configs to test
curl -X POST localhost:8000/api/v1/configs \
  -H "Content-Type: application/json" \
  -d '{"name":"small-chunks","config":{"adapter_type":"mock","chunk_size":256}}'

curl -X POST localhost:8000/api/v1/configs \
  -H "Content-Type: application/json" \
  -d '{"name":"large-chunks","config":{"adapter_type":"mock","chunk_size":1024}}'

# 2. Run the sweep
curl -X POST localhost:8000/api/v1/evaluate/sweep \
  -H "Content-Type: application/json" \
  -d '{"name":"chunk-size test","dataset_id":1,"config_ids":[1,2]}'

# 3. Poll for results
curl localhost:8000/api/v1/evaluate/sweep/1
# → { "status":"completed", "summary":{"leaderboard":[
#      {"config_name":"large-chunks","quality_score":0.82,"avg_latency_ms":120,"total_cost_usd":0.001},
#      {"config_name":"small-chunks","quality_score":0.76,"avg_latency_ms":85,"total_cost_usd":0.0}
# ]}}
```

The leaderboard is sorted by **quality score** (weighted: 40% correctness, 25% faithfulness, 20% relevance, 15% hallucination) — but you can see latency and cost right there to make the tradeoff call.

---

## Quick Start (Docker)

```bash
docker compose up --build
```

- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Frontend: http://localhost:5173

> **Note:** Production uses PostgreSQL. The test suite runs on SQLite for speed.

---

## Local Development

**Backend:**

```bash
cd backend
python -m venv venv
source venv/bin/activate  # .\venv\Scripts\activate on Windows
pip install -r requirements.txt

# Set env vars (copy .env.example if you have one)
# DATABASE_URL, JUDGE_PROVIDER, JUDGE_MODEL
# OPENAI_API_KEY or ANTHROPIC_API_KEY
# COST_OVERRIDES='{"openai":{"gpt-4o-mini":{"input":0.15,"output":0.6}}}'

alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

---

## Seed Datasets

Three ready-to-use datasets in `backend/seeds/`:

- `general_knowledge.json` — 20 factual questions
- `domain_specific.json` — 20 RAG/ML technical questions  
- `adversarial.json` — 15 hallucination-triggering queries

Upload via the Datasets page or:

```bash
curl -X POST localhost:8000/api/v1/datasets \
  -H "Content-Type: application/json" \
  -d @backend/seeds/general_knowledge.json
```

---

## API Endpoints

| Method | Endpoint | What It Does |
|--------|----------|--------------|
| `POST` | `/api/v1/evaluate/sweep` | Start a sweep (creates runs per config) |
| `GET` | `/api/v1/evaluate/sweep` | List all sweeps |
| `GET` | `/api/v1/evaluate/sweep/{id}` | Get sweep + leaderboard |
| `GET` | `/api/v1/evaluate/sweep/{id}/runs` | List runs in a sweep |
| `POST` | `/api/v1/evaluate` | Start single evaluation run |
| `GET` | `/api/v1/evaluate/{id}` | Get run status + summary |
| `GET` | `/api/v1/evaluate/{id}/results` | Per-query results for a run |
| `GET` | `/api/v1/results/runs` | List all runs |
| `DELETE` | `/api/v1/results/runs/{id}` | Delete run + all its results |
| `GET` | `/api/v1/results/compare` | Compare runs (404 if any ID missing) |
| `GET` | `/api/v1/results/failures` | Filter by failure type + threshold |
| `GET` | `/api/v1/results/export` | Export CSV/JSON |
| `GET` | `/api/v1/results/recommendations` | Tuning suggestions from failure patterns |
| `DELETE` | `/api/v1/datasets/{id}` | Delete dataset (409 if referenced) |
| `DELETE` | `/api/v1/configs/{id}` | Delete config (409 if referenced) |

---

## Frontend Pages

| Route | What You'll See |
|-------|-----------------|
| `/` | Dashboard with run summaries, cost cards |
| `/evaluate` | Start single runs, watch progress |
| `/sweeps` | Create sweeps, view history, leaderboard |
| `/compare` | Side-by-side run comparison |
| `/run/:id` / `/run/:id/query/:resultId` | Query details with failure chip + root cause |
| `/datasets` | Manage datasets + upload JSON |
| `/configs` | Manage RAG pipeline configs |

---

## Testing

```bash
cd backend && pytest tests/ -v
```

**22 tests covering:**
- All 6 failure modes + healthy answers
- Summary aggregation (quality score, failure distribution)
- Cost tracking (all providers, blended rates)
- Recommender rules for each failure mode
- SQLite schema creation
- Sweep E2E: create → validate → poll → verify leaderboard
- Route conflict fix: `GET /evaluate/sweep` returns 200 (not 422)
- Delete protection: 409 with run count, 204 after cleanup
- Strict compare: 404 when any run ID missing
- Judge-error caution notes in root cause
- None-safe averages + correct percentiles (nearest-rank)

---

## License

MIT — use it, fork it, build on it.