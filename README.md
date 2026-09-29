# GMEE — Global Misinformation Evolution Engine

GMEE ingests news and social content, extracts factual claims with LLMs,
embeds them for semantic search, tracks how claims **mutate** as they spread,
and maps that propagation in a graph database.

| Layer      | Stack |
|------------|-------|
| Backend    | Python 3.12 · FastAPI (async) · SQLAlchemy 2 · Alembic |
| Frontend   | React 18 · TypeScript · Vite · Tailwind CSS |
| Storage    | PostgreSQL 16 + pgvector · Neo4j 5 · Redis 7 |
| Ingestion  | Reddit · NewsAPI · RSS collectors |
| NLP        | all-mpnet-base-v2 embeddings · spaCy NER · BERTopic clustering |

## Quick Start

### Prerequisites

- Docker Desktop (the whole stack runs in Compose)
- For local (non-containerized) backend/frontend dev: Python 3.12+, Node 18+

### 1. Clone & configure

```bash
git clone <repo-url> && cd GMEE
cp .env.example .env        # defaults work out of the box for dev
```

Optional keys in `.env` unlock more ingestion sources: `REDDIT_CLIENT_ID` /
`REDDIT_CLIENT_SECRET`, `NEWS_API_KEY`, `ANTHROPIC_API_KEY`.

### 2. Bring up the stack

```bash
docker compose -f infra/docker-compose.yml up --build
```

### 3. Run migrations

```bash
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
```

The API is now at http://localhost:8000 (OpenAPI docs at `/docs`) and the UI at
http://localhost:3000.

> **Demo Telemetry:** if the frontend cannot reach the backend it automatically
> switches to a clearly-labeled simulated telemetry mode so the dashboard stays
> presentable during development. Exit anytime from the yellow banner; polling
> is fully suspended while simulated.

## Development (without Docker)

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:create_app --factory --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev                        # add -- --port 5175 to pin a port
```

## Port Mappings (host : container)

| Service    | Host : Container |
|------------|------------------|
| PostgreSQL | `55432 : 5432`   |
| Neo4j HTTP | `7474 : 7474`    |
| Neo4j Bolt | `7687 : 7687`    |
| Redis      | `6379 : 6379`    |
| Backend API| `8000 : 8000`    |
| Frontend   | `3000 : 3000`    |

## Testing

Locally (backend):

```bash
cd backend
./.venv/Scripts/python.exe -m pytest tests/ -q     # POSIX: python -m pytest tests/ -q
pytest --cov=app --cov-fail-under=70               # what CI enforces
```

Locally (frontend):

```bash
cd frontend
npm run lint        # eslint, zero warnings allowed
npm run test        # vitest
npm run build       # type-check + production bundle
```

In containers:

```bash
docker compose -f infra/docker-compose.yml exec backend pytest
docker compose -f infra/docker-compose.yml exec frontend npm run test
```

CI (GitHub Actions) runs lint + tests + coverage gates for both sides on every
push; see `.github/workflows/`.

## Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system design, data flow, service map
- [`docs/API.md`](docs/API.md) — REST endpoint reference
- [`docs/DATASET.md`](docs/DATASET.md) — dataset schemas, volumes, and ingestion pipelines
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) — algorithmic boundaries, heuristics, and hardware constraints
- [`backend/README.md`](backend/README.md) — backend local setup, testing, and evaluation guide
- [`docs/openapi.json`](docs/openapi.json) — machine-generated OpenAPI 3.1 spec
- [`CHANGELOG.md`](CHANGELOG.md) — notable changes

## Repository Layout

```
├── backend/
│   ├── app/
│   │   ├── ai/                    # model integrations
│   │   ├── api/v1/                # REST routers (auth, collection, dashboard, …)
│   │   ├── core/                  # config, security, scheduler, leader lock, ops hardening
│   │   ├── db/                    # postgres/neo4j/redis clients
│   │   ├── models/                # SQLAlchemy models
│   │   ├── repositories/          # data access
│   │   ├── schemas/               # pydantic schemas
│   │   └── services/              # collectors, preprocessing, nlp, evolution pipelines
│   ├── alembic/                   # migrations
│   └── tests/
├── frontend/
│   ├── src/components/            # dashboard UI
│   ├── src/api/                   # typed clients
│   └── tests/
├── infra/                         # docker-compose + images
└── docs/                          # API reference + OpenAPI spec
```
