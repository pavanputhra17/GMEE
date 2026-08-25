# GMEE Session Handoff — Start Here

> **For the next agent/session:** This file captures the full state of an in-progress
> "make GMEE 10/10" campaign. Read it fully before touching anything. Last updated: 2026-08-24.

## Context
- **Project:** GMEE — Global Misinformation Evolution Engine. FastAPI async backend + React 18/TS/Vite/Tailwind frontend, Postgres+pgvector / Neo4j / Redis via Docker Compose.
- **Mission arc:** ① redesign dashboard UI (Hermes-website style, premium red, color discipline) → ② audit project (scored 6.8/10) → ③ campaign to 10/10 (in progress).
- **Design language (locked by user):** brutalist Hermes-site style. Crimson `#C1121F` rationed to exactly **4 placements** (graph claim-nodes, active-tab underline, metric icon tile, demo banner); ink `#0a0a14` / paper `#f5f5f5` base; acid yellow only inside ink blocks; Instrument Serif display + Courier Prime mono; marquee ticker; noise grain; flat cards with hard borders + offset shadows.

## ✅ Committed work (safe)
| Commit | Contents |
|---|---|
| `311354c` | Full dashboard redesign + DEMO TELEMETRY mode (auto-activates when backend down, labeled, gentle drift, `everConnected` latch), skeleton loaders, a11y, tailwind `.ts`→`.js` fix |
| `fec8d9c` | Hygiene: git identity (`pavanputhra17` + noreply email), `.gitignore` += `*.tsbuildinfo`, `.env.example` restored, `CHANGELOG.md` created |

## 🔧 UNCOMMITTED work (P1–P4 of the 10/10 plan) — individually verified, suite run interrupted

### Backend — new files
- `app/api/v1/dashboard.py` — public read-only `/api/v1/dashboard` aggregate endpoint: services health + corpus counts (articles/claims/embedded/entities) + NLP status distribution + latest clustering run + Neo4j node/rel counts + Redis memory. Mounted in `main.py`.
- `app/core/ops_security.py` — Redis sliding-window rate limiter (login 10/min, register 5/300s, triggers ~4/min, default 120/min, fail-open on Redis errors), security headers middleware (CSP, XFO, nosniff, COOP, Referrer-Policy, Permissions-Policy), `record_audit()` best-effort helper.
- `app/core/leader_lock.py` + rewritten `app/core/scheduler.py` — Redis leader election (`SET NX EX`, TTL = 75% of interval, release-if-owner) so replicated backends don't double-run collection cycles.
- `alembic/versions/a7f2c91d4e10_add_audit_log.py` — new head (chain verified).
- Audit calls wired into auth register/login endpoints.

### Production bugs FIXED (all pre-existing; found because the test suite was finally runnable)
1. `app/api/v1/evolution.py` imported nonexistent `get_db` → **backend could not boot** → now `get_db_session`.
2. Double URL prefix: evolution router had inner `/evolution` prefix AND `main.py` mounted with `/evolution` again → real routes lived at `/api/v1/evolution/evolution/*`. Inner prefix removed.
3. `deps.require_role([RoleEnum.admin])` nested-list arg caused 403 **even for real admins** on trigger endpoints → now normalizes lists/tuples in `deps.py`.
4. `metadata_extractor.extract_or_repair_published_at`: function-level `from datetime import datetime` shadowed module import → UnboundLocalError meant the unix-timestamp path ALWAYS crashed → fixed with tz-aware UTC at top.
5. `scheduler.py` naive `datetime.now()` → UTC.

### Test infrastructure fixed
- `tests/conftest.py`: registered sqlite compilers for `JSONB` and pgvector `Vector` — without these the whole suite errored 60/60 (**CI has been silently red since the models gained JSONB**).
- `tests/test_health.py`: paths corrected `/health` → `/api/v1/health`.
- `tests/test_evolution_endpoints.py`: rewritten to use the existing `async_client` fixture + dependency overrides (previously used nonexistent `client` / `get_auth_headers` fixtures).
- Neo4j-writer mock pattern: `driver.session` must be a `MagicMock` returning an async-CM object — a plain `AsyncMock` makes `session()` itself a coroutine and `async with` explodes.
- Orchestrator tests: `mock_db.execute = AsyncMock(side_effect=[claims_res, arts_res, srcs_res])` with `MagicMock()` results exposing `.scalars().all()`; cluster-run result must be `MagicMock` (it's returned, not awaited).
- `test_mutation_detector_logic`: expectations corrected — with embeddings c0=[1,0,0], c1=[0.9,0.1,0], c2=[0.8,0.6,0] the chain c2←c1←c0 legitimately produces **2** EVOLVED_FROM edges (c1→c0 ≈0.995, c2→c1 ≈0.861 ≥0.85 threshold) plus c2→c0 SIMILAR_TO (0.80).

### Frontend
- `src/api/dashboard.ts` — typed snapshot fetch.
- `src/api/client.ts` — BASE_URL default now `http://localhost:8000/api/v1` (was missing `/api/v1`; health path was rewritten to compensate before).
- `SystemHealth.tsx` — added `['dashboard']` react-query (enabled only once `everConnected`) feeding live data into PG/Neo4j/Redis MetricCards.
- New tests: `tests/MetricCard.test.tsx` (2) + `tests/SystemHealth.demo.test.tsx` (1). **FE suite 4/4 green; lint --max-warnings 0 green; build green.**
- Coverage gates added to both CI workflows; `pytest-cov>=5.0.0` added to backend dev extras; `@vitest/coverage-v8@^1.6.0` installed.

## ⚠️ WHERE WE STOPPED — exact state
Backend full-suite verification was interrupted twice mid-run. Last known tally: **46+ passed** after fixes, remaining suspects:
1. `test_orchestrator_guards`, `test_orchestrator_resilience_to_neo4j_failure` — final mock fix applied (cluster_run → MagicMock) but **not re-verified**.
2. `test_evolution_trigger_endpoint_admin` — should pass thanks to require_role fix; unverified.
3. `test_nlp_components::test_entity_extractor` — environmental: spaCy model missing → `".venv/Scripts/python.exe" -m spacy download en_core_web_sm`.

**First action:** `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q` → fix stragglers → commit P1–P4 in logical chunks (suggest: `feat(backend): dashboard aggregate endpoint`, `feat(backend): rate limiting + security headers + audit log`, `feat(backend): leader lock for scheduler`, `fix(backend): boot-blocking route/auth/date bugs`, `test(backend): sqlite dialect compat + fixture corrections`, `feat(frontend): live dashboard wiring + tests`, `ci: coverage gates`).

## ⏳ Remaining roadmap to 10/10
- **P5** (biggest score gap): mutation-detector v2 — embedding-drift scoring, graph propagation paths — plus golden-set eval harness (~100 human-labeled claim pairs; needs the user's input).
- **P6**: README rewrite (remove references to deleted files), ARCHITECTURE.md diagrams, API reference from OpenAPI.
- Push to origin/main — **never authorized; ask first**.

## 🌍 Environment notes
- Backend venv python: `backend/.venv/Scripts/python.exe`. Full `pip install -e ".[dev]"` completed this session (torch/spacy stack included).
- **Docker Desktop NOT running** → cannot boot the stack or integration-test until the user starts it.
- FE dev server running as Hermes bg process `proc_d137820e3f61`: vite strictPort 5175. Use `127.0.0.1` (curl against `localhost` fails in this environment).
- Backend runs via Docker Compose per README (`infra/docker-compose.yml`); ports 8000/55432/7474/7687/6379/3000.
- **User action items:** close Hermes app then run `hermes update` (was 16 commits behind); optionally add Reddit/NewsAPI/Anthropic keys to `.env` for real ingestion.

## 💡 Hard-won pitfalls (save these)
- Vite silently ignores `tailwind.config.ts` in dev — use `tailwind.config.js`.
- Orphaned node servers outlive their bash wrappers and keep serving stale builds: check `netstat -ano | findstr :<port>`, kill by PID.
- Subagents can die to HTTP-524 retry loops claiming completion — always `git diff` to verify claimed work landed.
- `AsyncMock` makes every attribute call a coroutine: session factories / plain-return values need `MagicMock`.
- Giant one-liner shell commands get hard-blocked by the terminal parser — split into steps.
- `taskkill` needs single-slash flags (`/PID n /F`) in this git-bash environment; `//PID` fails.
- Hermes terminal parser hard-blocks oversized inline payloads (heredocs, giant one-liners) — write scripts to files instead.
