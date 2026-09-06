# RAG Intelligence & Optimization Platform

A self-hosted tool to evaluate, diagnose, and optimize Retrieval-Augmented Generation (RAG) pipelines. Run automated evaluations, get LLM-as-judge scores, perform deep root cause analysis, and conduct configuration sweeps to find optimal parameters.

## 🚀 Key Features

- **Automated Evaluation** — Run full eval suites against test datasets with the four core metrics.
- **Deep Root Cause Analysis (RCA)** — Automatically categorize failures into **six** PRD-specified modes (`retrieval_miss`, `noisy_retrieval`, `hallucination`, `reasoning_error`, `incomplete_answer`, `factually_incorrect`) with a human-readable root-cause string per evaluation. **Includes judge-error caution notes** when LLM judge calls fail.
- **Optimization Sweeps** — `POST /api/v1/evaluate/sweep` runs multiple configurations against one dataset and returns a **leaderboard** ranked by a weighted 'Quality Score' vs. latency/cost tradeoff. **Route conflict fixed**: `GET /api/v1/evaluate/sweep` (list) no longer 422s.
- **4 Core Metrics** — Faithfulness, Relevance, Correctness, Hallucination (LLM-as-judge computed).
- **Pluggable Judge LLM** — Support for Ollama (local, free), OpenAI, or Anthropic APIs.
- **Cost Tracking** — Automatic per-run cost estimation for both judge calls and pipeline tokens, configurable via `COST_OVERRIDES` env var.
- **Delete Protection** — Datasets/configs referenced by evaluation runs cannot be deleted (409 Conflict with run count); delete runs first via `DELETE /api/v1/results/runs/{run_id}`.
- **Strict Compare** — `/results/compare?ids=...` returns 404 if *any* requested run ID is missing (no silent partial results).
- **Production-Ready Observability** — Percentile latencies (p50/p95), failure distribution, cost breakdown, quality score.
- **Self-Hosted** — Docker Compose powered, no SaaS dependency.

## 🏗️ Architecture

```
+-----------------------------------------------------+
|                    Frontend (React)                  |
|  +----------+ +----------+ +----------+ +--------+ |
|  | Dashboard| | Compare  | |  Query   | |Dataset | |
|  |          | |  View    | |  Details | |Manager | |
|  +----------+ +----------+ +----------+ +--------+ |
+-------------------------+---------------------------+
                          | REST API
+-------------------------+---------------------------+
|                 Backend (FastAPI)                     |
|  +----------+ +----------+ +----------+ +--------+ |
|  | Dataset  | | Sweep    | |Evaluate  | |RCA     | |
|  | Manager  | | Orchestr.| |  Engine  | | Engine | |
|  +----------+ +----------+ +----------+ +--------+ |
+--------+--------------+--------------+--------------+
         |              |              |
    +----+----+   +-----+-----+  +----+----+
    |PostgreSQL|   |  RAG      |  | Judge   |
    |(results)|   | Pipeline  |  |  LLM    |
    +---------+   |(external) |  |(Ollama/ |
                  +-----------+  | OpenAI) |
                                 +---------+
```

## ✅ What's Implemented (per PRD)

### Deep Root Cause Analysis (§3.2)

Every evaluated query receives a `failure_category` and a `root_cause` string drawn from the six PRD modes:

| Mode | When it triggers |
|------|-----------------|
| `retrieval_miss` | No relevant info in top-k chunks |
| `noisy_retrieval` | Irrelevant chunks confuse the LLM |
| `hallucination` | Answer contains claims not in context |
| `reasoning_error` | Correct context, wrong synthesis |
| `incomplete_answer` | Missed parts of ground truth |
| `factually_incorrect` | Answer contradicts ground truth |

Each category includes a diagnostic explanation and, if the judge provided a `root_cause` in its output, that is merged in for specificity. **When judge calls fail, the root cause includes a caution note** listing which metric judges were unavailable.

### Cost Tracking (§3 / §4 Architecture)

Per-call costs are estimated in USD using a pricing table (`backend/app/services/cost.py`) covering:

- **Ollama** — free (local inference)
- **OpenAI** — gpt-4o-mini, gpt-4o, gpt-4.1-mini, gpt-4.1
- **Anthropic** — claude-3-5-haiku-latest, claude-3-5-sonnet-latest, claude-3-haiku

Costs accumulate across the full evaluation run and appear in the `summary` under `total_cost_usd` and per-result `estimated_cost_usd`. The `COST_OVERRIDES` environment variable lets you adjust rates.

### Optimization Sweeps (Phase 2)

New API endpoint `POST /api/v1/evaluate/sweep` accepts:

| Parameter | Description |
|-----------|-------------|
| `name` | Sweep display name |
| `description` | Optional description |
| `dataset_id` | Dataset to benchmark |
| `config_ids` | List of RAG config IDs to test |

The sweep:

1. Creates one `EvalSweep` record
2. Spawns one `EvalRun` per config
3. Sequentially evaluates each config (each run gets its own background thread/event-loop)
4. On completion, builds a **leaderboard** sorted by `quality_score` (weighted combination of correctness, faithfulness, relevance, and hallucination)
5. Posts `summary.leaderboard` containing: quality_score, avg_latency_ms, total_cost_usd, total_tokens for each config
6. Exposes `GET /api/v1/evaluate/sweep/{id}` and `GET /api/v1/evaluate/sweep/{id}/runs`

### Backend Changes Summary

| Feature | File(s) Modified |
|---------|-----------------|
| JSONB variant for SQLite/test compat | `backend/app/db_types.py` |
| New `EvalSweep` model + relationship | `backend/app/models/eval_sweep.py`, `__init__.py` |
| `EvalResult` gains `failure_category`, `root_cause`, `estimated_cost_usd` columns | `backend/app/models/eval_result.py` |
| `EvalRun` gains `sweep_id` FK + `summary` enrichment | `backend/app/models/eval_run.py` |
| Failure classifier with six modes + NL root cause | `backend/app/services/failure_classifier.py` |
| Judge LLM with Ollama + OpenAI + Anthropic + token usage | `backend/app/services/judge.py` |
| Cost estimation & blended rates | `backend/app/services/cost.py` |
| Optimization recommender (rule-based) | `backend/app/services/recommender.py` |
| Sweep router + schemas (`POST /evaluate/sweep`, `GET /sweep/{id}`) | `backend/app/routers/sweep.py`, `backend/app/schemas.py` |
| Main app registers sweep router (before evaluate to fix route conflict) | `backend/app/main.py` |
| **DELETE `/results/runs/{run_id}` + cascade cleanup** | `backend/app/routers/results.py`, `eval_run.py` model |
| **Route conflict fix (sweep before evaluate)** | `backend/app/main.py` |
| **Percentile fix (nearest-rank)** | `backend/app/services/evaluation_engine.py` |
| **None-safe summary avg** | `backend/app/services/evaluation_engine.py` |
| **Judge-error caution in classifier** | `backend/app/services/failure_classifier.py` |

### API Endpoints (new / extended)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/evaluate/sweep` | Start a sweep; creates `EvalSweep` + `EvalRun` per config |
| `GET` | `/api/v1/evaluate/sweep` | List all sweeps (fixed: no longer 422) |
| `GET` | `/api/v1/evaluate/sweep/{id}` | Get sweep status + `leaderboard` summary |
| `GET` | `/api/v1/evaluate/sweep/{id}/runs` | List runs belonging to a sweep (404 if sweep missing) |
| `GET` | `/api/v1/results/runs` | List all evaluation runs |
| `DELETE` | `/api/v1/results/runs/{run_id}` | Delete a run and all its results |
| `GET` | `/api/v1/results/compare` | Compare runs (404 if any ID missing) |
| `GET` | `/api/v1/results/failures` | Filter failures by type + threshold (now carries `failure_category` and `root_cause`) |
| `GET` | `/api/v1/results/export` | Export CSV/JSON |
| `GET` | `/api/v1/results/recommendations` | Tuning suggestions based on failure distribution |
| `DELETE` | `/api/v1/datasets/{id}` | Delete dataset (409 if referenced by runs) |
| `DELETE` | `/api/v1/configs/{id}` | Delete config (409 if referenced by runs) |

### Frontend

| Page | Updated to surface |
|------|-------------------|
| `/compare` | Leaderboard table when comparing runs from a sweep |
| `/run/:runId` / `/run/:runId/query/:resultId` | `failure_category` chip, `root_cause` tooltip per query |
| `/sweeps` | Create sweeps, view history, leaderboard with quality score |
| Dashboard score cards | Now include `total_cost_usd` when available |

## 📦 Quick Start (Docker Compose)

> **Note:** The full feature set (sweeps, RCA, cost tracking) works with PostgreSQL in production. The test suite runs on SQLite.

```bash
docker compose up --build
```

- Backend API: http://localhost:8000
- API docs (openapi): http://localhost:8000/docs
- Frontend: http://localhost:5173

## 🛠️ Local Development

**Backend:**

```bash
cd backend
python -m venv venv
source venv/bin/activate  # venv\Scripts\activate on Windows
pip install -r requirements.txt

# Set env vars (copy .env.example if present)
#   DATABASE_URL, JUDGE_PROVIDER, JUDGE_MODEL
#   OPENAI_API_KEY or ANTHROPIC_API_KEY
#   COST_OVERRIDES='{"openai":{"gpt-4o-mini":{"input":0.15,"output":0.6}}}'

alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

## 📊 Seed Datasets

Three sample datasets in `backend/seeds/`:

- `general_knowledge.json` — 20 factual questions
- `domain_specific.json` — 20 RAG/ML technical questions
- `adversarial.json` — 15 hallucination-triggering queries

Upload via the Datasets page or the API:

```bash
curl -X POST http://localhost:8000/api/v1/datasets \
  -H "Content-Type: application/json" \
  -d @backend/seeds/general_knowledge.json
```

## 📈 Example: Run a Sweep

```bash
# 1. Create two RAG configs (or use existing ones)
curl -X POST http://localhost:8000/api/v1/configs \
  -H "Content-Type: application/json" \
  -d '{"name":"cfg-llama3.1","config":{"adapter_type":"mock"}}'

curl -X POST http://localhost:8000/api/v1/configs \
  -H "Content-Type: application/json" \
  -d '{"name":"cfg-gpt4","config":{"adapter_type":"http","endpoint_url":"http://my-rag-api/ask"}}'

# 2. Start a sweep with 2 configs against the general-knowledge dataset
curl -X POST http://localhost:8000/api/v1/evaluate/sweep \
  -H "Content-Type: application/json" \
  -d '{"name":"Chunk-size sweep","description":"Compare mock adapter vs HTTP adapter","dataset_id":1,"config_ids":[1,2]}'

# 3. Poll the sweep status
curl http://localhost:8000/api/v1/evaluate/sweep/1
# → { "id":1, "status":"completed", "summary":{"leaderboard":[{"run_id":2,"quality_score":0.78,"avg_latency_ms":120,"total_cost_usd":0.001,"total_tokens":4500},{"run_id":1,"quality_score":0.62,"avg_latency_ms":85,"total_cost_usd":0.0,"total_tokens":3200}]}}
```

## 📈 Example: Get RCA on a Specific Query

```bash
curl http://localhost:8000/api/v1/results/failures?run_id=1&failure_type=hallucination
# → { "failures":[ { "id":42,"query":"...","answer":"...","failure_type":"hallucination","score":0.3,"root_cause":"The answer contains claims not supported by the retrieved context. Strengthen grounding instructions..."} ], "total":1 }
```

## 🛠️ Development & Testing

```bash
# Run pytest on the test suite (SQLite, no Docker needed)
cd backend && pytest tests/ -v
```

All 22 tests pass, covering:
- All 6 failure classification modes
- Summary aggregation (quality_score, failure_distribution)
- Cost tracking (pricing table, OpenAI/Ollama/Anthropic, blended rates)
- Recommender rules for each failure mode
- SQLite schema creation
- Sweep E2E: create sweep, validate dataset/config, poll to completion, verify leaderboard quality_score == 0.85, per-run summaries, results persistence
- Route conflict: GET /evaluate/sweep returns 200 (not 422)
- Delete protection: 409 with run count, 204 after runs deleted
- Compare strict validation: 404 when any run ID missing
- Judge-error caution in root_cause
- None-safe summary averages for latency

## 🪪 License

MIT