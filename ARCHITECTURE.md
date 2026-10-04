# GMEE Architecture

Global Misinformation Evolution Engine — system design and data flow.

**Interpretation boundary:** typed changes are observable text differences, graph
lineage is inferred, and local-corpus support is not a probability of truth.
Research comparisons are **UNPERFORMED**. Deployment hardening is not a
production-readiness or causal-propagation claim. See [Audit](docs/AUDIT.md),
[Operations](docs/OPERATIONS.md) and [Research](docs/RESEARCH.md).

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
- Redis leader election coordinates scheduled work; a finite TTL by itself
  does not guarantee single execution when a job outlives its lease or a worker
  crashes. The main upgrade adds durable PostgreSQL ownership/job records
  (`gmee03`); lease renewal, stale-owner fencing and recovery require isolated
  concurrency tests before high-availability claims.
- Infrastructure starts with `ENABLE_SCHEDULER=false`. Operators enable actual
  collection explicitly after migration/readiness and provider-policy review.

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
4. **Mutation detection** — vector proximity retrieves candidates; typed text
   analysis checks numeric/entity/hedging/polarity/framing/wording changes with
   changed spans and method/temporal metadata. A eligible earlier different-article
   predecessor with meaningful change may receive an `EVOLVED_FROM` candidate
   edge; similarity alone is not propagation or mutation proof. One parent per
   child is enforced by `gmee01`, which fails on historical multi-parent conflicts
   rather than deleting history. `SIMILAR_TO` remains a similarity relationship.
   Stored/returned analysis explicitly disclaims observed propagation.
5. **Durable commit** to Postgres, then **Neo4j sync** (`neo4j_writer.py`)
   mirrors claims/articles/sources and relationship edges; a sync failure is
   logged but does not fail the cycle.

## Data stores

| Store | Role |
|-------|------|
| PostgreSQL + pgvector | System of record: users/sessions, sources, articles, claims (+ 768-d embedding), entities, cluster runs, typed claim relationships, audit/feedback, label origins/history and frozen split/event identity; durable pipeline ownership/jobs in the main upgrade. HNSW on `claims.embedding`. |
| Neo4j | Read-optimized graph projection of candidate lineage/similarity plus source/entity nodes. An `EVOLVED_FROM` edge is inferred text/temporal association, not observed copying. Sync can lag the authoritative PostgreSQL transaction. |
| Redis | JWT blocklist, sliding-window rate-limit counters, scheduler leader lock, hot caches. |

## API surface

FastAPI app factory in `app/main.py`; all routers under `/api/v1`
(`health`, `dashboard`, `auth`, pipeline controls, `corpus`, `verdicts`, `graph`,
`alerts`, `eval`, and admin operations in the main upgrade). Full reference: [`docs/API.md`](docs/API.md); machine spec:
[`docs/openapi.json`](docs/openapi.json).

Cross-cutting hardening lives in `app/core/ops_security.py`:

- Sliding-window rate limits (login 10/min, register 5/300 s, trigger
  endpoints ≈4/min, default 120/min). Fail-open: if Redis is unreachable,
  requests are not blocked.
- Security headers on every response: CSP, X-Frame-Options DENY,
  X-Content-Type-Options nosniff, COOP, Referrer-Policy, Permissions-Policy.
- `record_audit()` writes best-effort audit rows (register/login events).

Auth = JWT access+refresh (`core/security.py`), role-gated dependencies
(`api/deps.py` — admin-only triggers, research export and durable operations).
Public registration creates a normal user, not an admin. `/verdicts/check` and
`/graph/mutation/compare` require a current user. Evaluation next/label/progress
are authenticated; the server sets annotator identity, preserves revisions and
separates human/automatic/legacy/test origins (`gmee02`).

## Feature rationales and epistemic contracts

| Feature | Why it exists | Boundary |
|---------|---------------|----------|
| Collection + preprocessing | Retain attributable source/time/content while normalizing markup and duplicates | Coverage is incomplete; feed access does not grant redistribution rights |
| Semantic corpus search | Retrieve a bounded local candidate set for inspection | Raw cosine is relatedness, not calibrated probability |
| Authenticated corpus checking | Return traceable article/claim citations and passage stance, with explicit insufficient evidence | No web fetch/independent fact verification; syndication and model warnings disclosed |
| Typed mutation comparison | Explain concrete changes and spans without inventing lineage | Read-only comparison; chronology and textual change are not causal proof |
| Blinded Eval Lab | Collect server-attributed human judgments separately from weak diagnostics | Human independence, event curation and legal dataset freeze still need review |
| Durable jobs/metrics/recovery | Make ownership and interrupted work inspectable | Admin-only; leases/recovery must be concurrency-tested, not assumed exactly-once |
| Demo telemetry | Show an explicitly simulated UI when chosen/available | Never scientific evidence or a successful readiness check |

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

Application configuration uses pydantic `Settings` (`core/config.py`). Runtime
Compose explicitly requires a private root `.env`, with the non-secret template
at `infra/runtime.env.example`. It supplies private datastore URLs and requires
unique PostgreSQL/Neo4j credentials and JWT secret (≥32 chars); optional ingestion
keys are Reddit, NewsAPI and Anthropic. Host-local URLs differ from service-name
URLs inside containers. Never log resolved Compose configuration or secret files.

Production CMD runs migrations before Uvicorn and defaults to **one worker**;
main application startup owns lazy model loading. Production source is immutable,
model cache is writable by the non-root user, and datastores/API have no host
ports. The development override exposes only loopback. PostgreSQL/Neo4j/Redis
share an internal datastore network; nginx reaches only the backend proxy network.

nginx replaces forwarding headers and denies framing, permits current Google
Fonts and self-origin `/api` in CSP, hides server version and bounds body/API
waits. Uvicorn trusts the known nginx peer only; raw app XFF trust defaults off
in the main upgrade. An external TLS gateway/provider chain needs an explicit
trusted-address/scheme review; no wildcard trust is required or allowed here.
Render's static frontend uses a separately declared HTTPS API origin in CSP/CORS.

## Performance and failure behavior

- One worker avoids duplicate per-process ML weights; lazy loading reduces boot
  work but shifts model download/load latency to first use. Measure cold/warm RAM,
  latency and provider/model availability before selecting a deployment tier.
- Bounded retrieval/graph limits and persisted typed edges avoid presenting an
  unbounded cross-join as an interactive operation. Request budgets are not a
  benchmark or a promised p95; long pipelines belong in inspectable jobs.
- PostgreSQL is authoritative; Neo4j synchronization can fail/lag and needs
  observable recovery. Redis loss affects revocation, limiting and coordination;
  its behavior must be validated rather than advertised as fail-safe.
- Empty corpus is a valid state. Missing evidence/models/dependencies must be
  exposed as abstention/unavailability, never silently simulated scientific data.
- Capacity/load, high-availability failure and restore experiments are
  **UNPERFORMED** for this upgrade. See [Limitations](docs/LIMITATIONS.md).

## Testing strategy

- Backend: pytest + asyncio unit tests with SQLite dialect shims/mocks (70%
  coverage gate). Required CI integration migrates a disposable PostgreSQL+
  pgvector service and rejects empty/skipped JUnit results. SQLite cannot prove
  vector SQL/index, migration or durable ownership semantics.
- Frontend: locked `npm ci`, strict ESLint/types/build and Vitest/Testing Library
  with component coverage. Docker tests use a Node target, never nginx runtime.
- Deployment: static secret-free Compose/policy validation and PowerShell parsing;
  offline backup/HTTP safety tests; bounded tmpfs-only real HTTP smoke through
  production nginx/API images. It checks auth/readiness/empty corpus/evidence
  gate/typed comparison but writes no scientific labels and is not browser E2E.
- Release gates still include native nginx/Render validation, browser interaction
  and accessibility, isolated restore, measured capacity and the frozen human
  research protocol. See [Acceptance checklist](docs/AUDIT.md).
