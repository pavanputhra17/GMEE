# Changelog

All notable changes to GMEE are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); semver for releases.

## [Unreleased]

### Added
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

### Changed
- Color discipline pass: brand red rationed to claim nodes / active-tab underline / icon tile / demo banner; metric values ink-first; selected graph edges, selection rings and risk halos moved off crimson to ink/rose-800; claim inspector chip red→ink
- Flat-border consistency: stray inset shadows removed; audit terminal bar `bg-black`→ink; audit feed entrance animation fires only on the newest row

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

## [0.1.0] — Initial backend (2026-07)

- FastAPI async service: auth (Argon2id + JWT + Redis JTI revocation), collection orchestrator with RSS/Reddit/NewsAPI collectors, NLP pipeline (spaCy entities, sentence-transformers embeddings, Anthropic claim extraction), evolution engine v1 (clustering, mutation detection, Neo4j graph writes)
- PostgreSQL+pgvector / Neo4j / Redis infrastructure via Docker Compose with healthchecks
- Alembic migrations (6), ~50 backend tests, Ruff+mypy+pytest CI
