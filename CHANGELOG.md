# Changelog

All notable changes to GMEE are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); semver for releases.

## [Unreleased]

### Added
- Dashboard redesign: Hermes-style brutalist theme (crimson #C1121F rationed to 4 hero placements, ink/paper base), marquee status ticker, terminal-chrome audit feed, animated graph topology with risk halos
- DEMO TELEMETRY mode: auto-activates when backend unreachable, clearly labeled, gentle metric drift, auto-yields to live data; `everConnected` latch prevents live→demo flip mid-session
- Skeleton shimmer loading states and error-state escape hatches
- Accessibility: focus-visible rings, aria-hidden ticker duplicates, prefers-reduced-motion support

### Fixed
- Tailwind config silently ignored as `.ts` by Vite dev server → renamed to `tailwind.config.js`
- Malformed timestamp in audit feed seed data
- Stability: health polling disabled while backend unreachable; calmed feed/ticker cadence

## [0.1.0] — Initial backend (2026-07)

- FastAPI async service: auth (Argon2id + JWT + Redis JTI revocation), collection orchestrator with RSS/Reddit/NewsAPI collectors, NLP pipeline (spaCy entities, sentence-transformers embeddings, Anthropic claim extraction), evolution engine v1 (clustering, mutation detection, Neo4j graph writes)
- PostgreSQL+pgvector / Neo4j / Redis infrastructure via Docker Compose with healthchecks
- Alembic migrations (6), ~50 backend tests, Ruff+mypy+pytest CI
