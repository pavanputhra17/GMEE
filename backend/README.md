# GMEE Backend Service & Pipeline Engine

The backend for the **Global Misinformation Early-Warning Engine (GMEE)** is a high-performance FastAPI service delivering real-time factual claim extraction, Bayesian credibility scoring, temporal narrative mutation tracking, and graph topology streaming.

---

## Architecture & Technology Stack

- **Framework:** FastAPI / Starlette / Uvicorn (Python 3.11+)
- **Primary Database:** PostgreSQL 16 + `pgvector` (Vector similarity search via HNSW cosine index)
- **Graph Database:** Neo4j 5.20+ Community / Enterprise (Propagation topologies, scoop races, timeline cascades)
- **In-Memory Cache & Lock:** Redis 7 (Distributed scheduler leader locks, rate limiting, token blocklists)
- **NLP & Inference:**
  - `sentence-transformers/all-mpnet-base-v2` (768-D normalized embeddings)
  - `google/flan-t5-base` (Cross-domain NLI entailment / contradiction stance scoring)
  - `spaCy` `en_core_web_sm` (Named Entity Recognition for epistemic grounding)
  - Anthropic Claude / OpenAI GPT / HuggingFace local fallback for LLM claim extraction

---

## Directory Structure

```
backend/
├── alembic/                 # Database migrations (PostgreSQL + pgvector)
├── app/
│   ├── ai/                  # LLM and embedding client abstractions
│   ├── api/                 # REST endpoints under /api/v1
│   │   ├── alerts.py        # Early-warning surge and spike notifications
│   │   ├── auth.py          # JWT authentication, session handling
│   │   ├── collection.py    # Multi-source ingest management
│   │   ├── corpus.py        # Searchable corpus and semantic queries
│   │   ├── dashboard.py     # Aggregated operational telemetry
│   │   ├── eval.py          # Gold-standard evaluation & active labeling
│   │   ├── evolution.py     # Topic clustering & mutation runs
│   │   ├── graph.py         # Subgraphs, scoops, simulations
│   │   ├── health.py        # Liveness & multi-service readiness
│   │   ├── lineage.py       # Claim evolutionary mutation chains & diffs
│   │   ├── nlp.py           # NLP extraction triggers
│   │   ├── preprocessing.py # Text cleanup & language filtering
│   │   └── verdicts.py      # Probabilistic fact checking & feedback
│   ├── core/                # Config, security, scheduler, rate limits
│   ├── db/                  # Async session factories (Postgres, Neo4j, Redis)
│   ├── models/              # SQLAlchemy 2.0 async ORM models
│   ├── repositories/        # Database access patterns
│   ├── schemas/             # Pydantic v2 validation contracts
│   └── services/            # Domain logic (verdicts, nlp, evolution, eval)
├── pyproject.toml           # Dependencies and tool configurations
├── scripts/                 # Maintenance, batch inference & eval scripts
└── tests/                   # Pytest test suite (unit and integration)
```


---

## Local Setup & Development

### 1. Python Environment
Requires Python 3.11+.

```bash
cd backend
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate

pip install -e ".[dev]"
```

### 2. Environment Variables
Create a local `.env` file or export variables:

```ini
POSTGRES_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/gmee
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=supersecretjwtstringwithatleast32chars
ENVIRONMENT=development
ENABLE_SCHEDULER=true
```

### 3. Database Migrations (Alembic)
Apply all PostgreSQL schema migrations:

```bash
alembic upgrade head
```

To verify the current migration head:

```bash
alembic current
```

---

## Running the Service

Start the local FastAPI development server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- Health readiness: `http://localhost:8000/api/v1/health/ready`

---

## Testing & Quality Gates

The backend enforces strict type checking (`mypy`), linting (`ruff`), unit test suites, integration tests on `pgvector`, and test coverage gates ($\ge 70\%$).

### Run Unit Tests
```bash
pytest
```

### Run Integration Tests (Requires live PostgreSQL + pgvector)
```bash
pytest -m integration tests/integration/
```

### Run Coverage Checks
```bash
pytest --cov=app --cov-report=term-missing --cov-fail-under=70
```

### Run Static Analysis
```bash
ruff check app tests
mypy app tests
```

---

## Evaluation Harness Execution

GMEE ships a scientifically grounded benchmarking harness comparing SBERT vector retrieval against TF-IDF:

1. **Sample Stratified Pairs for Labeling:**
   ```bash
   python scripts/sample_eval_pairs.py 50 1500
   ```
2. **Label Pairs in Dashboard:**
   Open the **Eval Lab** tab (`#/dashboard/eval`) and label pairs blinded.
3. **Execute Evaluation Runner:**
   ```bash
   python scripts/run_eval.py
   ```
   Outputs metric tables (AUROC, 95% bootstrap CI, best-F1, Brier score, ECE, McNemar p-value) and persists results to `eval_report.json`.

