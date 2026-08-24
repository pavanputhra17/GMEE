# GMEE REST API Reference

Base URL: `http://localhost:8000/api/v1`

- **Auth:** JWT bearer. `POST /auth/login` and `POST /auth/refresh` issue
  access + refresh tokens; send `Authorization: Bearer <access_token>`.
- **Roles:** `user` and `admin`. All `*/trigger` endpoints require `admin`.
- **Rate limits:** login 10/min · register 5 per 5 min · triggers ≈4/min ·
  other endpoints 120/min (sliding window; fail-open if the limiter store is
  down). 429 is returned with `Retry-After`.
- Machine-readable spec: [`docs/openapi.json`](openapi.json) — also served
  live at `/docs` (Swagger UI) and `/openapi.json`.

---

## Health — `health.py`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | public | Liveness: process up, no external checks. |
| GET | `/health/ready` | public | Readiness: pings Postgres, Neo4j, Redis; returns per-service status. Powers the dashboard's connection state. |

## Dashboard — `dashboard.py`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/dashboard` | public | Aggregate snapshot for the dashboard UI: services health, corpus counts (articles / claims / embedded claims / entities), NLP claim-status distribution, latest clustering run, Neo4j node & relationship counts, Redis memory stats. Read-only; safe to poll. |

## Auth — `auth.py`

| Method | Path | Auth | Body | Description |
|--------|------|------|------|-------------|
| POST | `/auth/register` | public | `UserCreate` | Create account `{email, password, full_name?}` → `UserResponse`. Audited. Rate-limited. |
| POST | `/auth/login` | public | `LoginRequest` | `{email, password}` → `TokenResponse {access_token, refresh_token, token_type}`. Audited. Rate-limited. |
| POST | `/auth/refresh` | public | `RefreshRequest` | Exchange a valid refresh token for a new token pair. |
| POST | `/auth/logout` | bearer | `LogoutRequest` | Revokes the supplied refresh token (added to the Redis JWT blocklist). |
| GET | `/auth/me` | bearer | — | Current user as `UserResponse {id, email, role, full_name?, is_active, created_at}`. |

## Collection — `collection.py`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/collection/status` | bearer | Collector states, article counts, last-run info. |
| POST | `/collection/trigger` | admin | Kick off a collection cycle across enabled sources (RSS / Reddit / NewsAPI). |

## Preprocessing — `preprocessing.py`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/preprocessing/status` | bearer | Pending/processed article counts and pipeline health. |
| POST | `/preprocessing/trigger` | admin | Run cleaning, language filtering, near-duplicate removal, metadata extraction over pending articles. |

## NLP — `nlp.py`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/nlp/status` | bearer | Claim extraction/embedding progress and model availability. |
| POST | `/nlp/trigger` | admin | Extract claims (LLM), embed them (BGE-M3 → pgvector), extract entities (spaCy). |

## Evolution — `evolution.py`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/evolution/status` | bearer | Last clustering run, cluster count, relationship totals. |
| GET | `/evolution/clusters` | bearer | Cluster listing with member claims for graph exploration. |
| POST | `/evolution/trigger` | admin | Force an evolution cycle (`force=true` bypasses the debounce guard). Clusters topics, detects `EVOLVED_FROM` / `SIMILAR_TO` relationships, syncs to Neo4j. |

---

## Typical flow

```
1. POST /auth/register        # once, to create an admin
2. POST /auth/login           # get tokens
3. POST /collection/trigger   # ingest articles            (admin)
4. POST /preprocessing/trigger# clean + dedupe             (admin)
5. POST /nlp/trigger          # claims + embeddings        (admin)
6. POST /evolution/trigger    # clusters + mutation graph  (admin)
7. GET  /dashboard            # snapshot for the UI
```

Steps 3–6 also run automatically on the scheduler; triggers exist for
on-demand control.

## Error shape

Validation errors return FastAPI's standard 422 envelope:

```json
{ "detail": [ { "loc": ["body", "email"], "msg": "...", "type": "..." } ] }
```

Auth failures return `401 {"detail": "..."}`, insufficient role `403`,
rate limit `429` (+ `Retry-After`).
