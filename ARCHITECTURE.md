# GMEE Architecture

Global Misinformation Evolution Engine — system design and data flow.

## 30-second overview

```
┌──────────┐   ┌─────────────┐   ┌────────────────┐   ┌───────────────┐
│ Collectors│──▶│ Preprocess  │──▶│ NLP extraction │──▶│ Evolution     │
│ rss/reddit│   │ clean/dedupe│   │ claims/embed/  │   │ cluster/mutate│
│ newsapi   │   │ lang detect │   │ entities       │   │ graph sync    │
└──────────┘   └─────────────┘   └────────────────┘   └───────────────┘
      │              │                  │                    │
      ▼              ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PostgreSQL (pgvector)      Neo4j graph          Redis              │
│  articles·claims·embeddings claim mutation map   cache·ratelimit·   │
│  users·audit·cluster runs   EVOLVED_FROM/SIMILAR_TO  leader·blocklist│
└─────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ /api/v1
                   ┌────────────────────┐        ┌──────────────────┐
                   │ FastAPI backend    │◀──────▶│ React dashboard  │
                   │ auth·triggers·snap │  poll  │ vitals·graph·feed│
                   └────────────────────┘        └──────────────────┘
```

## Pipelines

The four pipeline stages run inside the backend process, scheduled by
`app/core/scheduler.py` (asyncios loop, started in the app lifespan) and can
also be triggered manually via authenticated `POST …/trigger` endpoints.

### 1. Collection (`services/collectors/`, `collection_orchestrator.py`)

- `rss.py`, `reddit.py`, `news_api.py` fetch raw items into `articles`.
- Each collector subclasses `base.py`; missing API keys disable a source.
- A Redis **leader lock** (`core/leader_lock.py`) guarantees a single runner
  when multiple backend replicas are up: `SET NX EX` with TTL = 75 % of the
  interval, released only by the owner.

### 2. Preprocessing (`services/preprocessing/`)

- `cleaner.py` strips boilerplate; `language_detector.py` filters non-target
  languages; `near_duplicate_detector.py` drops simhash near-duplicates;
  `metadata_extractor.py` normalizes authors/publishers and repairs
  `published_at` (ISO strings → unix timestamps → fallbacks), tz-aware UTC.

### 3. NLP (`services/nlp/`, `nlp_orchestrator.py`)

- `llm_client.py` extracts atomic factual claims from article text.
- `embedding_service.py` embeds each claim (all-mpnet-base-v2, 768-d) into pgvector.
- `entity_extractor.py` runs spaCy `en_core_web_sm` NER per claim.

### 4. Evolution (`services/evolution/`, `orchestrator.py`)

One cycle (`run_evolution_cycle`) with guards first:

1. **Corpus guard** — skip unless ≥ `MIN_CORPUS_SIZE_FOR_CLUSTERING` claims.
2. **Debounce** — skip unless ≥ `MIN_NEW_CLAIMS_TO_RECLUSTER` new claims since
   the last `ClaimClusterRun` (bypassable with `force=true`).
3. **Clustering** — `cluster_service.py` (BERTopic) assigns claims to topics,
   persisted as `ClaimClusterAssignment` rows under a `ClaimClusterRun`.
4. **Mutation detection** — `mutation_detector.py` compares each claim's
   embedding against earlier-cluster predecessors:
   - cosine ≥ `EVOLUTION_SIMILARITY_THRESHOLD` → best predecessor gets an
     `EVOLVED_FROM` edge (one per claim — the mutation chain),
   - similarity in `[SIMILAR_TO_THRESHOLD, EVOLUTION_…)` → `SIMILAR_TO`.
5. **Durable commit** to Postgres, then **Neo4j sync** (`neo4j_writer.py`)
   mirrors claims/articles/sources and relationship edges; a sync failure is
   logged but does not fail the cycle.

## Data stores

| Store | Role |
|-------|------|
| PostgreSQL + pgvector | System of record: users/sessions, sources, articles, claims (+ embedding vector), entity mentions, cluster runs & assignments, claim relationships, audit log. HNSW index on `claims.embedding`. |
| Neo4j | Read-optimized propagation graph: `(Claim)-[:EVOLVED_FROM|SIMILAR_TO]->(Claim)` plus source/actor nodes for path queries the dashboard visualizes. |
| Redis | JWT blocklist, sliding-window rate-limit counters, scheduler leader lock, hot caches. |

## API surface

FastAPI app factory in `app/main.py`; all routers under `/api/v1`
(`health`, `dashboard`, `auth`, `collection`, `preprocessing`, `nlp`,
`evolution`). Full reference: [`docs/API.md`](docs/API.md); machine spec:
[`docs/openapi.json`](docs/openapi.json).

Cross-cutting hardening lives in `app/core/ops_security.py`:

- Sliding-window rate limits (login 10/min, register 5/300 s, trigger
  endpoints ≈4/min, default 120/min). Fail-open: if Redis is unreachable,
  requests are not blocked.
- Security headers on every response: CSP, X-Frame-Options DENY,
  X-Content-Type-Options nosniff, COOP, Referrer-Policy, Permissions-Policy.
- `record_audit()` writes best-effort audit rows (register/login events).

Auth = JWT access+refresh (`core/security.py`), role-gated dependencies
(`api/deps.py` — admin-only for trigger endpoints).

## Frontend

React 18 + Vite + Tailwind, single-page dashboard (`src/pages/SystemHealth.tsx`):

- React Query polls `/api/v1/health/ready` + `/api/v1/dashboard` at a
  user-selected interval (2 s/5 s/15 s/paused; ≥5 s defaults — calm UI).
- **Demo Telemetry mode:** if the backend has never answered this session,
  the page renders clearly-labeled simulated metrics and suspends polling
  entirely; the first successful response latches live mode (`everConnected`).
- Design language: brutalist ink-on-paper — flat cards, 1 px borders, offset
  shadows, Instrument Serif display + Courier Prime mono, marquee ticker,
  brand red rationed to hero placements (claim nodes, active-tab underline,
  icon tile, demo banner).

## Environments & config

All configuration flows through pydantic `Settings` (`core/config.py`) loaded
from `.env` (see `.env.example`). Required: `POSTGRES_URL`, `NEO4J_URI`,
`NEO4J_USER`, `NEO4J_PASSWORD`, `REDIS_URL`, `CORS_ORIGINS`,
`JWT_SECRET` (≥32 chars). Optional ingestion keys: Reddit, NewsAPI, Anthropic.

## Testing strategy

- Backend: pytest + asyncio against SQLite (JSONB/pgvector compilers
  registered in `tests/conftest.py`); pipelines tested with mocked DB sessions
  and mocked Neo4j writers; coverage gate 70 %. Integration against real
  Postgres/Neo4j happens via Docker Compose.
- Frontend: Vitest + Testing Library — MetricCard contract, demo-mode
  activation, App smoke. Strict lint (`--max-warnings 0`) gates CI.
