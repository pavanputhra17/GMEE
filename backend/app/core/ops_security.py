"""Distributed rate limiting and audit logging backed by Redis.

Uses the existing Redis dependency — no new packages. The limiter is a
fixed-window counter keyed per canonical client identity; the audit log
records mutating admin actions (logins, pipeline triggers) for later review.

Client identity: the raw ``X-Forwarded-For`` header is attacker-controlled and
is ignored unless the immediate socket peer belongs to ``TRUSTED_PROXY_CIDRS``.
In the default deployment Uvicorn's ``--forwarded-allow-ips`` already rewrites
the socket peer for the single trusted nginx hop, so the app trusts nothing
extra.

Failure policy: ordinary endpoints fail OPEN when Redis is unreachable (the
dashboard stays available); sensitive endpoints (login, registration, admin
triggers) fail CLOSED with 503 unless ``RATE_LIMIT_FAIL_CLOSED_SENSITIVE`` is
disabled. The audit log is best-effort.
"""

import hashlib
import ipaddress
import json
import logging
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, Request, status
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
    "/api/v1/auth/refresh": (30, 60),
    "/api/v1/nlp/trigger": (4, 60),
    "/api/v1/evolution/trigger": (4, 60),
    "/api/v1/collection/trigger": (6, 60),
    "/api/v1/preprocessing/trigger": (6, 60),
    "/api/v1/alerts/evaluate": (4, 60),
    "/api/v1/operations/recover": (4, 60),
}

# Mounted router prefixes (see app/main.py). Anything else shares "other".
_ROUTER_FAMILIES = frozenset({
    "alerts", "auth", "collection", "corpus", "dashboard", "eval", "evolution",
    "graph", "health", "nlp", "operations", "preprocessing", "verdicts",
})


@lru_cache(maxsize=8)
def _trusted_networks(
    cidrs: tuple[str, ...],
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    return tuple(ipaddress.ip_network(c, strict=False) for c in cidrs)


def _parse_ip(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    """Canonical client identity for rate limits, audit rows and vote hashing.

    The socket peer is authoritative. ``X-Forwarded-For`` is consulted only
    when that peer is inside ``TRUSTED_PROXY_CIDRS``; the chain is then walked
    right-to-left and the first address that is NOT a trusted proxy is used,
    so a client cannot prepend a forged hop.
    """
    peer = request.client.host if request.client else None
    peer_ip = _parse_ip(peer)
    if peer_ip is None:
        return "unknown"
    cidrs = get_settings().TRUSTED_PROXY_CIDRS
    networks = _trusted_networks(tuple(cidrs if isinstance(cidrs, list) else [cidrs]))
    if not networks or not any(peer_ip in net for net in networks):
        return str(peer_ip)
    forwarded = request.headers.get("x-forwarded-for", "")
    for hop in reversed([h for h in forwarded.split(",") if h.strip()]):
        hop_ip = _parse_ip(hop)
        if hop_ip is None:
            # A malformed hop means the chain cannot be trusted past this point.
            break
        if not any(hop_ip in net for net in networks):
            return str(hop_ip)
    return str(peer_ip)


# Backwards-compatible private alias for older imports.
_client_ip = client_ip


def _limit_for(path: str) -> tuple[str, int, int, bool]:
    """Return (canonical bucket, limit, window, is_sensitive) for a path.

    Non-sensitive paths are bucketed per router family (``/api/v1/<router>``),
    a small fixed set, so varying IDs or path suffixes cannot mint unlimited
    fresh buckets.
    """
    for prefix, (limit, window) in SENSITIVE_LIMITS.items():
        if path == prefix or path.startswith(prefix + "/"):
            return prefix, limit, window, True
    parts = path.split("/")
    if len(parts) >= 4 and parts[1] == "api" and parts[2] == "v1" and parts[3] in _ROUTER_FAMILIES:
        family = "/api/v1/" + parts[3]
    else:
        family = "other"
    return family, DEFAULT_RATE_LIMIT, DEFAULT_WINDOW_SECONDS, False


async def _check_rate_limit(redis_client: Redis, key: str, limit: int, window: int) -> bool:
    """Fixed-window counter. Returns True when allowed."""
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
    settings = get_settings()
    if not settings.RATE_LIMIT_ENABLED or request.method == "OPTIONS":
        return await call_next(request)
    bucket_name, limit, window, sensitive = _limit_for(request.url.path)
    ip_hash = hashlib.sha256(client_ip(request).encode()).hexdigest()[:16]
    bucket = f"ratelimit:{ip_hash}:{bucket_name}:{int(time.time() // window)}"

    try:
        client: Redis = await _redis_singleton.get_client()
        allowed = await _check_rate_limit(client, bucket, limit, window)
    except Exception as exc:
        if sensitive and settings.RATE_LIMIT_FAIL_CLOSED_SENSITIVE:
            logger.error(
                "rate limiter unavailable for sensitive route %s (%s) — refusing",
                bucket_name,
                type(exc).__name__,
            )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Temporarily unavailable; retry shortly."},
                headers={"Retry-After": "30"},
            )
        # Fail open for ordinary reads — never take the dashboard down.
        logger.warning("rate limiter unavailable (%s) — allowing request", type(exc).__name__)
        return await call_next(request)

    if not allowed:
        # IMPORTANT: return the response, do NOT raise HTTPException here.
        # This runs inside @app.middleware("http"), which sits OUTSIDE the
        # exception-handling middleware — a raised HTTPException would bubble
        # up as an unhandled 500 instead of a 429.
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded. Slow down."},
            headers={"Retry-After": str(window)},
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    return response


def install_rate_limiter(app: FastAPI) -> None:
    """Register the limiter as an HTTP middleware."""

    @app.middleware("http")
    async def _rl(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response | JSONResponse:
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
    async def _headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
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
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Best-effort audit insert — never breaks the caller's transaction flow."""
    try:
        payload = json.dumps(detail or {}, default=str)
        ip = client_ip(request) if request else None
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
