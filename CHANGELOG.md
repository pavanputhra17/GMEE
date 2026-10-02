# Changelog

All notable changes to GMEE are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); semver for releases.

## [Unreleased]

### Added
- Graph → focused timeline drill-down: "View in Timeline" in either graph view
  opens the time tunnel for that story only (`/graph/timeline?article_id=` BFS
  ≤3 SIMILAR hops, `focused: true`). Rings always run newest→oldest so the
  wheel/click dive reads back through the coverage to the original first
  report; focused mode shows the followed story chip, an "All stories" exit
  and a dedicated empty state. Backend Cypher fixed for Neo4j (the old
  `ASC NULLS LAST` focused query was invalid Cypher and the focused path had
  never actually executed); `tests/TimelineTunnel.test.tsx` (5 tests) +
  `tests/ClusterDossier.test.tsx` (3 tests)
- Cluster dossier redesign: outlet color dots, similarity meter bars,
  publish-time lag vs the hub (+ "scoop … before" when a member beat the hub),
  coverage span, match-range and link-count stat chips, "your selection"
  badge when inspecting the story focused from the graph
- Eval Lab tab for the golden set: blinded pair labeling (texts + outlets
  only — the judge never sees scores, buckets or verdicts) with keyboard
  shortcuts (1/2/3), annotator handle persisted in localStorage, per-bucket
  coverage grid and Cohen's-kappa chips; typed client `src/api/eval.ts`;
  `tests/EvalLab.test.tsx` (5 tests, incl. a payload-shape blind assertion)
- Dashboard redesign: Hermes-style brutalist theme (crimson #C1121F rationed to 4 hero placements, ink/paper base), marquee status ticker, terminal-chrome audit feed, animated graph topology with risk halos
- DEMO TELEMETRY mode: auto-activates when backend unreachable, clearly labeled, gentle metric drift, auto-yields to live data; `everConnected` latch prevents live→demo flip mid-session
- Skeleton shimmer loading states and error-state escape hatches
- Accessibility: focus-visible rings, aria-hidden ticker duplicates, prefers-reduced-motion support
- `/api/v1/dashboard` aggregate endpoint (services health, corpus counts, NLP status distribution, latest cluster run, Neo4j counts, Redis memory) + typed frontend client wired into SystemHealth cards once live
- Redis sliding-window rate limiting (login 10/min, register 5/300s, triggers ~4/min, default 120/min, fail-open), security headers middleware (CSP/XFO/nosniff/COOP/Referrer-Policy/Permissions-Policy), best-effort audit log (migration `a7f2c91d4e10`)
- Redis leader lock for the scheduler so replicated backends don't double-run collection cycles
- Coverage gates in CI (`pytest --cov-fail-under=70`, vitest coverage); `pytest-cov`, `@vitest/coverage-v8`
- Docs: rewritten README, new ARCHITECTURE.md, API reference generated from OpenAPI (`docs/API.md`, `docs/openapi.json`)
- Frontend: CacheTelemetry extraction; MetricCard contract tests; demo-mode activation test
- Persisted early-warning API — `GET /alerts/feed` (deduplicated rows from the
  `alerts` table with kind/severity/acknowledged filters and unacknowledged
  tallies), `POST /alerts/evaluate` (admin trigger for one evaluation pass),
  `POST /alerts/{alert_id}/acknowledge` (admin, idempotent). The persistent
  alert engine (`evaluate_alerts` + `alerts` table) existed but was unreachable
  from any endpoint, scheduler or script
- Dashboard **Early Warning** board on the Overview tab: persisted alerts,
  stateless 24h spike snapshot and 24h article/disputed/mutation counters;
  typed client `src/api/alerts.ts`; 3 component tests
- SQLite-safe endpoint tests for the alert feed, the acknowledge path, the
  admin gate and `evaluate_alerts` dedup semantics (`tests/test_alerts_feed.py`)
- LICENSE (MIT) — required before any artifact/dataset release
- Verdict-engine contract tests (`tests/test_verdict_engine.py`): every band
  `band_for()` can emit must appear in the disclosed `/verdicts/summary` config,
  the reported similarity window must equal the settings-overridable window, and
  track-record smoothing must stay Laplace-bounded
- Mutation-edge lifecycle tests: a re-run upserts stored edges (never inserts a
  duplicate) and prunes EVOLVED_FROM edges an evaluated claim no longer
  reproduces (`tests/test_evolution.py`)
- `scripts/run_verdicts.py --rescore` flag: re-runs the verdict engine over
  already-verdicted claims as well as unscored ones — required after engine
  changes (the live 62%-UNSUPPORTED / 0-DISPUTED distribution predates the
  contradiction-recentering and strong-similarity corroboration fixes and
  would otherwise never be recomputed)
- `.dockerignore` for both image builds (host `.venv` / `node_modules` /
  coverage / logs no longer enter the build context)

### Fixed
- Neo4j sync ran 4+ Bolt round-trips per claim (~40k statements for the live
  corpus) and never removed stale `EVOLVED_FROM` edges: `Neo4jWriter` now
  issues batched `UNWIND` writes (sources/claims/edges grouped, relationship
  types allow-listed) — a handful of statements per cycle — and prunes
  `EVOLVED_FROM` edges the authoritative Postgres run no longer reproduces,
  scoped to the claims the cycle actually evaluated
  (`test_neo4j_writer_prunes_stale_evolved_edges`)
- `frontend/Dockerfile` ran `npm run dev` as its "production" CMD and compose
  bind-mounted host source over it: now a multi-stage build (`npm ci` →
  `vite build` → nginx serving `dist` with a same-origin `/api` proxy,
  `VITE_API_BASE_URL` overridable at build time); compose maps `3000:80` and
  the frontend service no longer mounts dev volumes
- Vertical scroll overshoot: pages could scroll past their content into blank
  space. Fixes: `AsciiEqualizer` glyph strip is now self-clipping (it added
  ~640px of overflow at phone widths); the dashboard root clips horizontal
  overflow (`overflow-x-clip`); inner scroll areas use `overscroll-behavior:
  contain` so list scroll never chains into the page; timeline/fullgraph
  canvases no longer intercept page wheel events outside their plot area.
  Verified with a headless CDP probe (`_scroll_probe.mjs`) across all 10 tabs
  at 1440x900 / 1920x1080 / 390x844: 0px blank-below-content, 0px overflow-X
  everywhere. The probe now caps its metrics at the *real* scrollable overflow
  (`scrollHeight − clientHeight`), so a tab shorter than one viewport
  (`min-h-screen` filler) no longer reports a phantom gap.
- `run_eval.py` crashed on every run: `load_labeled` joined `articles` for
  embeddings (they live on `claims.embedding`), `consensus` raised `KeyError`
  on the first row (`by_pair[r["pid"]].append` on a missing key), and
  `sbert_scores` fed asyncpg's pgvector string form straight into numpy. All
  three fixed — the script prints AUROC + best-F1 from the 8 consensus labels
- `GET /eval/progress` silently discarded all but one vote per annotator: the
  `_per_annotator` helper flattened `(annotator, label, n)` rows into a single
  `{label, count}`. Now returns nested `{labels: {...}, total}` per annotator

### Changed
- Color discipline pass: brand red rationed to claim nodes / active-tab underline / icon tile / demo banner; metric values ink-first; selected graph edges, selection rings and risk halos moved off crimson to ink/rose-800; claim inspector chip red→ink
- Flat-border consistency: stray inset shadows removed; audit terminal bar `bg-black`→ink; audit feed entrance animation fires only on the newest row

- `models/__init__` now exports `Alert` and `FeedbackVerdict` alongside the
  other ORM models
- `/api/v1/alerts/evaluate` added to the sensitive rate-limit table (4/min)
- `docs/API.md` documents the corpus / verdicts / graph / alerts / eval route
  groups; `docs/openapi.json` regenerated from the running backend (45 paths)
- `run_mutation_detection` now returns the run's current edge set (refreshed
  rows included) instead of only newly created rows, so the Neo4j mirror also
  receives score updates; `claim_relationships` gained
  `uq_claim_relationships_edge` (migration `a4c7e1f9b2d6`, which dedupes
  pre-existing duplicate rows before creating the constraint)

### Fixed
- Backend boot blockers: evolution router imported nonexistent `get_db` and was mounted with a doubled `/evolution` prefix (real routes lived at `/api/v1/evolution/evolution/*`)
- Admin 403 on trigger endpoints: nested-list role argument in `require_role`
- `metadata_extractor.extract_or_repair_published_at`: function-level datetime import shadowed module import — unix-timestamp path always raised UnboundLocalError; now tz-aware UTC
- Scheduler naive datetimes → UTC
- Test suite restored from 60/60 errors: sqlite compilers for JSONB + pgvector `Vector`, corrected health paths, rebuilt evolution-endpoint tests, orchestrator service mocks are `AsyncMock` (orchestrator awaits them)
- Health Score card now shows the honest share of services OK (was hardcoded 66%)
- Frontend client BASE_URL missing `/api/v1`
- Tailwind config silently ignored as `.ts` by Vite dev server → renamed to `tailwind.config.js`
- Malformed timestamp in audit feed seed data
- Stability: health polling disabled while backend unreachable; calmed feed/ticker cadence

- `/graph/claims` no longer runs a claims×claims cosine cross join (~20M
  distance computations, ~105 s per request while the UI polls it every 60 s).
  Edges now come from the persisted `claim_relationships` rows with a bounded
  HNSW KNN (`LATERAL`) fallback when a node set has none; the response reports
  which path served it (`edge_source`) — warm latency ~0.09 s
- Outlet track-record signal was effectively dead: `scripts/run_verdicts.py`
  counted bands (`LEAN_SUPPORTED`, `LEAN_DISPUTED`) the engine no longer emits,
  so every outlet scored 0/0 and its prior never moved off 0.5. The query now
  takes its vocabulary from the engine itself (`SUPPORTED_BANDS` /
  `DISPUTED_BANDS`) via expanding bind parameters
- `/verdicts/summary` advertised a `PENDING_DISPUTE` band `band_for()` never
  returns, and reported the hard-coded similarity window rather than the
  settings-overridable one actually in use; `engine_config()` now mirrors the
  scorer (bands + `when` for the DISPUTED override) and reads `near_window()`
- Stale docs/user-facing copy claimed BGE-M3 1024-d embeddings while the code,
  the `Vector(768)` column and the live corpus all use all-mpnet-base-v2
  768-d (README, ARCHITECTURE, docs/API.md, Landing hero copy)

## [0.1.0] — Initial backend (2026-07)

- FastAPI async service: auth (Argon2id + JWT + Redis JTI revocation), collection orchestrator with RSS/Reddit/NewsAPI collectors, NLP pipeline (spaCy entities, sentence-transformers embeddings, Anthropic claim extraction), evolution engine v1 (clustering, mutation detection, Neo4j graph writes)
- PostgreSQL+pgvector / Neo4j / Redis infrastructure via Docker Compose with healthchecks
- Alembic migrations (6), ~50 backend tests, Ruff+mypy+pytest CI
