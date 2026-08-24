"""Distributed rate limiting and audit logging backed by Redis.

Uses the existing Redis dependency — no new packages. The limiter is a
sliding-window counter keyed per client IP; the audit log records
mutating admin actions (logins, pipeline triggers) for later review.

Both fail OPEN with a warning: availability is preferred over strictness
for this internal tool. Flip ``RATE_LIMIT_ENABLED`` to enforce hard.
"""

import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.redis_client import redis_client as _redis_singleton

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

DEFAULT_RATE_LIMIT = 120          # requests...
DEFAULT_WINDOW_SECONDS = 60       # ...per sliding window, per client
SENSITIVE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/auth/login": (10, 60),        # brute-force guard
    "/api/v1/auth/register": (5, 300),     # account-spam guard
    "/api/v1/nlp/trigger": (4, 60),
    "/api/v1/evolution/trigger": (4, 60),
    "/api/v1/collection/trigger": (6, 60),
}


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _limit_for(path: str) -> tuple[int, int]:
    for prefix, limit in SENSITIVE_LIMITS.items():
        if path.startswith(prefix):
            return limit
    return (DEFAULT_RATE_LIMIT, DEFAULT_WINDOW_SECONDS)


async def _check_rate_limit(redis_client: Redis, key: str, limit: int, window: int) -> bool:
    """Sliding-window counter. Returns True when allowed."""
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.incr(key, 1)
        pipe.expire(key, window, nx=True)
        results = await pipe.execute()
    current = int(results[0])
    return current <= limit


async def rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response | JSONResponse:
    limit, window = _limit_for(request.url.path)
    ip_hash = hashlib.sha256(_client_ip(request).encode()).hexdigest()[:16]
    bucket = f"ratelimit:{ip_hash}:{request.url.path}:{int(time.time() // window)}"

    try:
        client: Redis = await _redis_singleton.get_client()
        allowed = await _check_rate_limit(client, bucket, limit, window)
    except Exception as exc:  # fail open — never take the API down over limiter errors
        logger.warning("rate limiter unavailable (%s) — allowing request", exc)
        return await call_next(request)

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Slow down.",
            headers={"Retry-After": str(window)},
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    return response


def install_rate_limiter(app: FastAPI) -> None:
    """Register the limiter as an HTTP middleware."""

    @app.middleware("http")
    async def _rl(request: Request, call_next):
        return await rate_limit_middleware(request, call_next)


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    # Minimal CSP; relaxed where the SPA needs it. Tune per deployment.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
        "img-src 'self' data:; connect-src 'self'"
    ),
}


def install_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def _headers(request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response


# ---------------------------------------------------------------------------
# Audit log (admin/pipeline actions)
# ---------------------------------------------------------------------------

async def record_audit(
    db: AsyncSession,
    *,
    actor: str | None,
    action: str,
    target: str | None = None,
    detail: dict | None = None,
    request: Request | None = None,
) -> None:
    """Best-effort audit insert — never breaks the caller's transaction flow."""
    try:
        payload = json.dumps(detail or {}, default=str)
        ip = _client_ip(request) if request else None
        await db.execute(
            text(
                "INSERT INTO audit_log (actor, action, target, detail, client_ip) "
                "VALUES (:actor, :action, :target, :detail, :client_ip)"
            ),
            {
                "actor": actor,
                "action": action,
                "target": target,
                "detail": payload,
                "client_ip": ip,
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning("audit log write failed: %s", exc)
