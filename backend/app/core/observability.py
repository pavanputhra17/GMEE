"""Request correlation and sanitized structured access logging.

* Every request gets an ``X-Request-ID``. A client-supplied value is accepted
  only if it matches a strict charset/length (log-injection safe); otherwise
  a fresh one is generated. The ID is echoed on the response and attached to
  every log record emitted while the request is handled.
* One access-log line per request with method, the matched ROUTE TEMPLATE
  (e.g. ``/api/v1/verdicts/{claim_id}``, never raw IDs or query strings,
  which may carry search text), status and duration. Bodies, headers and
  tokens are never logged.
"""

import contextvars
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

access_logger = logging.getLogger("gmee.access")


class RequestIdFilter(logging.Filter):
    """Inject the current request ID into every record as ``request_id``."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def _incoming_request_id(request: Request) -> str:
    candidate = request.headers.get(REQUEST_ID_HEADER, "")
    if _SAFE_REQUEST_ID.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "<unmatched>"


def install_request_context(app: FastAPI) -> None:
    @app.middleware("http")
    async def _request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _incoming_request_id(request)
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            access_logger.info(
                "request method=%s route=%s status=%d duration_ms=%.1f",
                request.method,
                _route_template(request),
                status_code,
                duration_ms,
            )
            request_id_var.reset(token)


def configure_logging(level: int) -> None:
    """Idempotent root logging setup with request IDs on every line."""
    root = logging.getLogger()
    if not any(getattr(h, "_gmee", False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler._gmee = True  # type: ignore[attr-defined]
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s level=%(levelname)s logger=%(name)s request_id=%(request_id)s %(message)s"
            )
        )
        handler.addFilter(RequestIdFilter())
        root.addHandler(handler)
    root.setLevel(level)
