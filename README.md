# RAG Evaluation Dashboard

A self-hosted dashboard to evaluate, diagnose, and optimize Retrieval-Augmented Generation (RAG) pipelines. Run automated evaluations with LLM-as-judge scoring, perform deep root cause analysis across 6 failure modes, and run configuration sweeps to find what works best for your data. Full-stack: FastAPI backend + React frontend, Docker Compose deployment.

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
| **Pluggable Pipeline Adapters** | Mock (testing), HTTP (generic API), or LocalBrainNotes (Ollama + ChromaDB) — swap via config |
| **Cost Tracking** | Per-run and per-query cost estimates. Override rates via `COST_OVERRIDES` env var |
| **Delete Protection** | Can't accidentally delete a dataset or config that has run history — 409 with the run count |
| **Strict Compare** | `/results/compare?ids=1,2,3` returns 404 if any ID is missing — no silent partial results |
| **A/B Comparison** | Compare baseline vs candidate runs for immediate regression/improvement detection |
| **Production Observability** | p50/p95 latency, failure distribution, cost breakdown, quality score |
| **Score Clamping** | Judge scores outside [0, 1] are clamped to the valid range so no metric ever distorts your dashboard |
| **Recommendation Engine** | Deterministic rule-based recommender inspects failure patterns and emits concrete config tweaks — no LLM needed, same inputs always yield the same suggestions |
| **Self-Hosted** | Docker Compose, your data, your infra |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2.0 (async) |
| **Database** | PostgreSQL 16 (production) / SQLite (testing) |
| **Migrations** | Alembic (async, with asyncpg) |
| **Judge LLMs** | Ollama (local), OpenAI, Anthropic — or MockJudge for testing |
| **Frontend** | React 18, TypeScript, Vite 5, Tailwind CSS 3.4 |
| **Charts** | Recharts 2.13 (line charts, bar charts) |
| **Containerization** | Docker Compose (3 services: PostgreSQL, Backend, Frontend) |
| **Testing** | pytest 8.3, pytest-asyncio, TestClient, isolated SQLite per test |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React + TypeScript + Tailwind)               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │Dashboard │ │ Compare  │ │  Query   │ │  Dataset   │ │
│  │          │ │  View    │ │  Details │ │  Manager   │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│  │  Sweeps  │ │ Evaluate │ │ Configs  │                │
│  │ (Leader- │ │ (Start + │ │ (Adapter │                │
│  │  board)  │ │  Poll)   │ │Templates)│                │
│  └──────────┘ └──────────┘ └──────────┘                │
│  Components: ScoreCard, MetricChart, QueryTable,        │
│  ChunkViewer — with regression highlighting in compare  │
└─────────────────────────┬───────────────────────────────┘
                          │ REST API (Vite proxy: /api → backend)
                          │
┌─────────────────────────┴───────────────────────────────┐
│  Backend (FastAPI + SQLAlchemy Async)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │ Dataset  │ │ Sweep    │ │ Evaluate │ │  RCA       │ │
│  │ Manager  │ │Orchestrat│ │  Engine  │ │  Engine    │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
│  ┌──────────┐ ┌──────────┐                               │
│  │ Cost     │ │ Recommen-│                               │
│  │ Tracker  │ │ dations  │                               │
│  └──────────┘ └──────────┘                               │
└──────────┬────────────┬────────────┬────────────────────┘
           │            │            │
      ┌────┴────┐ ┌─────┴─────┐ ┌────┴─────┐
      │PostgreSQL│ │  RAG      │ │  Judge   │
      │(results) │ │ Pipeline  │ │  LLM     │
      └─────────┘ │(external) │ │(Ollama/   │
                   └───────────┘ │ OpenAI/  │
                                  │Anthropic)│
                                  └──────────┘
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

## Pipeline Adapters

The evaluation engine connects to your RAG pipeline through a pluggable adapter interface. Swap without code changes via the config JSON:

| Adapter | Config | Use Case |
|---------|--------|----------|
| **Mock** | `{"adapter_type": "mock"}` | Testing the evaluation pipeline without a real RAG system |
| **HTTP** | `{"adapter_type": "http", "endpoint_url": "..."}` | Generic external RAG API (POST JSON, expects `answer`, `retrieved_chunks`, `tokens_used`) |
| **LocalBrainNotes** | `{"adapter_type": "local_brain_notes", "base_url": "..."}` | Local Ollama + ChromaDB pipeline |

The Configs page provides one-click templates for all three adapters so you don't need to remember the JSON schema.

---

## Cost Tracking

Costs are estimated in USD per 1M tokens:

| Provider | Models | Rate |
|----------|--------|------|
| **Ollama** | Any local model | Free |
| **OpenAI** | gpt-4o-mini, gpt-4o, gpt-4.1-mini, gpt-4.1 | ~$0.15–$10/M |
| **Anthropic** | claude-3-5-haiku-latest, claude-3-5-sonnet-latest, claude-3-haiku | ~$0.25–$15/M |

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

The leaderboard is sorted by **quality score** (weighted: 40% correctness, 25% faithfulness, 20% relevance, 15% hallucination) — but you can see latency and cost right there to make the tradeoff call. The sweep runs each config in its own daemon thread with an isolated database session and event loop, so they never interfere with each other or the main API.

---

## Quick Start (Docker)

```bash
docker compose up --build
```

- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Frontend: http://localhost:5173

> **Note:** The backend runs with `--reload` for hot-reload during development. The `./backend` directory is mounted as a volume so code changes take effect immediately.
>
> **Note:** Production uses PostgreSQL. The test suite runs on SQLite for speed (each test gets its own temp database via the `isolated_db` fixture). Database tables are auto-created on startup (FastAPI's `lifespan` event calls `Base.metadata.create_all`). For production schema management, use Alembic migrations (`alembic upgrade head`).

---

## Local Development

**Backend:**

```bash
cd backend
python -m venv venv
source venv/bin/activate  # .\venv\Scripts\activate on Windows
pip install -r requirements.txt

# Set env vars (JUDGE_PROVIDER defaults to "mock" for dev without LLM)
# DATABASE_URL, JUDGE_PROVIDER, JUDGE_MODEL
# OPENAI_API_KEY or ANTHROPIC_API_KEY
# COST_OVERRIDES='{"openai":{"gpt-4o-mini":{"input":0.15,"output":0.6}}}'

# Tables are auto-created on startup. For production migrations:
# alembic upgrade head

uvicorn app.main:app --reload
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server proxies `/api` requests to the backend (default: `http://localhost:8000`), configurable via `VITE_API_URL`.

---

## Seed Datasets

Three ready-to-use datasets in `backend/seeds/`:

- `general_knowledge.json` — 20 factual questions
- `domain_specific.json` — 20 RAG/ML technical questions  
- `adversarial.json` — 15 hallucination-triggering queries

Upload via the Datasets page using the Upload button, or:

```bash
# Via POST /api/v1/datasets (specify test cases inline)
curl -X POST localhost:8000/api/v1/datasets \
  -H "Content-Type: application/json" \
  -d @backend/seeds/general_knowledge.json

# Via POST /api/v1/datasets/upload (file upload — supports both
# wrapped {"name": "...", "test_cases": [...]} and raw array formats)
curl -X POST localhost:8000/api/v1/datasets/upload \
  -F "file=@backend/seeds/general_knowledge.json" \
  -F "name=General Knowledge"
```

---

## API Endpoints

| Method | Endpoint | What It Does |
|--------|----------|--------------|
| `GET` | `/` | Root — app name, version, docs link |
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/evaluate/sweep` | Start a sweep (creates runs per config) |
| `GET` | `/api/v1/evaluate/sweep` | List all sweeps |
| `GET` | `/api/v1/evaluate/sweep/{id}` | Get sweep + leaderboard |
| `GET` | `/api/v1/evaluate/sweep/{id}/runs` | List runs in a sweep |
| `POST` | `/api/v1/evaluate` | Start single evaluation run |
| `GET` | `/api/v1/evaluate/{id}` | Get run status + summary |
| `GET` | `/api/v1/evaluate/{id}/results` | Per-query results for a run |
| `GET` | `/api/v1/results/runs` | List all runs (optional `?status=` filter) |
| `DELETE` | `/api/v1/results/runs/{id}` | Delete run + all its results |
| `GET` | `/api/v1/results/compare` | Compare runs (404 if any ID missing) |
| `GET` | `/api/v1/results/compare-baseline` | Run-level A/B comparison (delta metrics) |
| `GET` | `/api/v1/results/failures` | Filter by failure type + threshold |
| `GET` | `/api/v1/results/export` | Export CSV/JSON |
| `GET` | `/api/v1/results/recommendations` | Tuning suggestions from failure patterns |
| `POST` | `/api/v1/datasets` | Create a dataset with test cases |
| `POST` | `/api/v1/datasets/upload` | Upload dataset from JSON file |
| `GET` | `/api/v1/datasets` | List all datasets |
| `GET` | `/api/v1/datasets/{id}` | Get dataset details |
| `DELETE` | `/api/v1/datasets/{id}` | Delete dataset (409 if referenced) |
| `POST` | `/api/v1/configs` | Create a new RAG config |
| `GET` | `/api/v1/configs` | List all configs |
| `GET` | `/api/v1/configs/{id}` | Get config details |
| `DELETE` | `/api/v1/configs/{id}` | Delete config (409 if referenced) |

---

## Frontend Pages

| Route | What You'll See |
|-------|-----------------|
| `/` | Dashboard with run summaries, metric trend charts, and cost cards |
| `/evaluate` | Start single runs, watch progress with live polling |
| `/sweeps` | Create sweeps, view history, ranked leaderboard with medals |
| `/compare` | Side-by-side run comparison (bar chart + per-query table with regression highlighting) |
| `/compare-baseline` | A/B baseline vs candidate run comparison with delta table |
| `/run/:id` / `/run/:id/query/:resultId` | Query details with failure chip, root cause, score breakdown, and chunk viewer |
| `/datasets` | Manage datasets + upload JSON |
| `/configs` | Manage RAG pipeline configs with one-click adapter templates |

## Frontend Components

| Component | Purpose |
|-----------|---------|
| **ScoreCard** | Displays a single metric as a colored card (percent, decimal, or integer format) |
| **MetricChart** | Recharts wrapper for line and bar charts with configurable series |
| **QueryTable** | Tabular view of per-query results with color-coded scores and optional regression highlighting |
| **ChunkViewer** | Collapsible list of retrieved chunks with relevance scores |

---

## Implementation Details

### Background Evaluation

Evaluation runs execute in **daemon threads** with per-thread database engines, sessions, and event loops. This avoids cross-loop connection pool contention in uvicorn's `--reload` mode (which uses a subprocess-based reloader). Each thread:

1. Creates its own `AsyncEngine` and `async_sessionmaker`
2. Runs the evaluation engine in a fresh event loop
3. Disposes the engine pool before closing the loop
4. Catches exceptions and marks the run as `failed` with error details

### Sweep Finalization

Sweeps use SQLAlchemy's `populate_existing` execution option to refresh stale identity-map instances. Without this, the sweep's session would return its own cached (empty) summary objects instead of the summaries committed by the worker threads.

### Judge Score Clamping

All judge scores are clamped to `[0.0, 1.0]` via `_clamp_score()`. Judge LLMs occasionally return out-of-range values (e.g. 1.15 or a 0-100 scale) — clamping prevents distorted metrics and failure classification.

### Database Compatibility

The `JSONVariant` type in `db_types.py` uses PostgreSQL JSONB in production with a SQLite-compatible JSON fallback, so the same models work with both backends.

### Recommendation Engine

The `recommender` module is a **deterministic rule engine** — no LLM calls, no randomness. It inspects the dominant failure categories in a run and emits prioritized, concrete configuration suggestions. The same inputs always yield the same output, making it auditable.

---

## Testing

```bash
cd backend && pytest tests/ -v
```

**22 tests covering:**
- All 6 failure modes + healthy answers
- Summary aggregation (quality score, failure distribution, p50/p95 latency)
- Cost tracking (all providers, blended rates)
- Recommender rules for each failure mode
- SQLite schema creation (all 6 tables)
- Sweep E2E: create → validate → poll → verify leaderboard
- Route conflict fix: `GET /evaluate/sweep` returns 200 (not 422)
- Delete protection: 409 with run count, 204 after cleanup
- Strict compare: 404 when any run ID missing
- Judge-error caution notes in root cause
- None-safe averages + correct percentiles (nearest-rank)
- Deterministic MockJudge (0.85 fixed score) for tests without LLM calls

Each test gets its own isolated SQLite database via the `isolated_db` fixture — no state leaks between tests.

---

## License

MIT — use it, fork it, build on it.