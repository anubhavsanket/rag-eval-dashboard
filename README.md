# RAG Evaluation Dashboard

A self-hosted tool to evaluate and monitor Retrieval-Augmented Generation (RAG) pipelines. Run automated evaluations against test datasets, get LLM-as-judge scores for faithfulness, relevance, correctness, and hallucination, and compare configurations side-by-side.

## Architecture

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
|  | Dataset  | | Pipeline | |Evaluate  | |Results | |
|  | Manager  | | Adapter  | |  Engine  | | Store  |
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

## Features

- **Automated evaluation** — run full eval suites against test datasets
- **4 evaluation metrics** — faithfulness, relevance, correctness, hallucination
- **Pluggable judge LLM** — Ollama (local) or OpenAI API
- **Pipeline adapters** — connect any RAG pipeline via HTTP
- **Side-by-side comparison** — compare 2-3 configurations
- **Failure analysis** — filter by failure type, export results
- **Self-hosted** — Docker Compose, no SaaS dependency

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Ollama running locally (or OpenAI API key)

### Run with Docker Compose

```bash
docker-compose up --build
```

- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Frontend: http://localhost:5173

### Local Development

**Backend:**

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Set up Postgres and run migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

## Configuration

Backend reads from environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/rag_eval` | Postgres connection |
| `JUDGE_PROVIDER` | `ollama` | `ollama` or `openai` |
| `JUDGE_MODEL` | `llama3.1` | Ollama model name |
| `OPENAI_API_KEY` | - | Required if using OpenAI |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |

## Pipeline Adapters

The dashboard connects to your RAG pipeline via adapters. Configure a config in the dashboard with the appropriate `adapter_type`:

### Mock Adapter (for testing)

```json
{
  "adapter_type": "mock"
}
```

### HTTP Adapter (any RAG API)

```json
{
  "adapter_type": "http",
  "endpoint_url": "http://your-rag-api/ask"
}
```

Your endpoint should accept `{"query": "..."}` and return:

```json
{
  "answer": "...",
  "retrieved_chunks": [{"chunk_id": 1, "text": "...", "score": 0.9}],
  "tokens_used": 100
}
```

### LocalBrainNotes Adapter

```json
{
  "adapter_type": "local_brain_notes",
  "base_url": "http://localhost:8000"
}
```

## Evaluation Metrics

### Faithfulness
Is the answer supported by the retrieved context? LLM judge extracts claims and verifies each against context.

### Relevance
Are the retrieved chunks relevant to the query? Each chunk scored 0-3 by judge.

### Correctness
Does the answer match the expected ground truth? Semantic similarity (not exact match).

### Hallucination
Does the answer contain claims not supported by context? Inverse of unsupported claim ratio.

## API Endpoints

See the interactive docs at `/docs` for full API reference.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/datasets` | List datasets |
| POST | `/api/v1/datasets` | Create dataset |
| GET | `/api/v1/datasets/{id}` | Get dataset with test cases |
| POST | `/api/v1/evaluate` | Start evaluation run |
| GET | `/api/v1/evaluate/{id}` | Get run status |
| GET | `/api/v1/evaluate/{id}/results` | Get per-query results |
| GET | `/api/v1/results/runs` | List runs |
| GET | `/api/v1/results/compare?ids=1,2` | Compare runs |
| GET | `/api/v1/results/failures` | Get failures |
| GET | `/api/v1/results/export` | Export CSV/JSON |

## Seed Datasets

Three sample datasets in `backend/seeds/`:

- `general_knowledge.json` — 20 factual questions
- `domain_specific.json` — 20 RAG/ML technical questions
- `adversarial.json` — 15 hallucination-triggering queries

Upload via the Datasets page or via API:

```bash
curl -X POST http://localhost:8000/api/v1/datasets \
  -H "Content-Type: application/json" \
  -d @backend/seeds/general_knowledge.json
```

## Project Structure

```
rag-eval-dashboard/
  backend/
    app/
      main.py
      config.py
      db.py
      schemas.py
      models/          # SQLAlchemy models
      routers/         # API routes
      services/        # Business logic
    alembic/           # Migrations
    seeds/             # Sample datasets
    Dockerfile
  frontend/
    src/
      pages/           # Page components
      components/      # Shared components
      api/             # API client
    Dockerfile
  docker-compose.yml
```

## Development

```bash
# Backend tests
cd backend && pytest

# Frontend type check
cd frontend && npm run build
```

## License

MIT