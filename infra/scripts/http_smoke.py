"""Bounded HTTP end-to-end smoke for docker-compose.smoke.yml, not browser E2E.

Only a fresh disposable fixture may be used. This registers a temporary ordinary
user, but never labels evaluation pairs, submits verdict feedback, seeds articles,
or invokes an authorized pipeline trigger. No credentials or response bodies are
printed. The parent process enforces a hard wall-clock deadline.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Protocol
from urllib.parse import urlsplit

API = "/api/v1"
MAX_RESPONSE_BYTES = 2_000_000
ADMIN_TRIGGERS = (
    "/collection/trigger",
    "/preprocessing/trigger",
    "/nlp/trigger",
    "/evolution/trigger",
    "/alerts/evaluate",
)


class SmokeError(RuntimeError):
    """A smoke failure that does not include tokens, credentials or payloads."""


class Client(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        token: str | None = None,
        json_body: bool = True,
    ) -> tuple[int, Any, dict[str, str]]: ...


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def fixture_base_url(base: str, fixture_only: bool) -> str:
    if not fixture_only or os.environ.get("GMEE_SMOKE_FIXTURE") != "1":
        raise SmokeError("Both --fixture-only and GMEE_SMOKE_FIXTURE=1 are required.")
    try:
        url = urlsplit(base)
        port = url.port
    except ValueError:
        raise SmokeError("Fixture base URL is invalid.") from None
    if (
        url.scheme != "http"
        or url.hostname not in {"frontend", "127.0.0.1", "localhost", "::1"}
        or url.username is not None
        or url.password is not None
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise SmokeError("Only an HTTP fixture origin without credentials is allowed.")
    return base.rstrip("/")


class HttpClient:
    def __init__(self, base: str, request_timeout: float, deadline: float) -> None:
        self.base = base
        self.request_timeout = request_timeout
        self.deadline = deadline
        # An inherited HTTP proxy must not receive fixture credentials.
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            NoRedirect(),
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        token: str | None = None,
        json_body: bool = True,
    ) -> tuple[int, Any, dict[str, str]]:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise SmokeError("HTTP smoke deadline exceeded.")
        headers = {"Accept": "application/json", "User-Agent": "gmee-fixture-smoke/1"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            self.base + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            response = self.opener.open(
                request,
                timeout=min(self.request_timeout, remaining),
            )
        except urllib.error.HTTPError as exc:
            response = exc
        except (OSError, urllib.error.URLError):
            raise SmokeError(f"{method} {path}: transport failed.") from None
        with response:
            status = response.code
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            response_headers = {k.lower(): v for k, v in response.headers.items()}
        if len(raw) > MAX_RESPONSE_BYTES:
            raise SmokeError(f"{method} {path}: response exceeded the byte limit.")
        if not json_body:
            return status, None, response_headers
        try:
            payload = json.loads(raw) if raw else None
        except (ValueError, UnicodeError):
            raise SmokeError(
                f"{method} {path}: response is not JSON (HTTP {status})."
            ) from None
        return status, payload, response_headers


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def object_response(payload: Any, label: str) -> dict[str, Any]:
    require(isinstance(payload, dict), f"{label}: expected a JSON object.")
    return dict(payload)


def expect(
    client: Client,
    method: str,
    path: str,
    statuses: tuple[int, ...],
    *,
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    status, payload, _ = client.request(method, API + path, body=body, token=token)
    require(status in statuses, f"{method} {path}: HTTP {status}, expected {statuses}.")
    print(f"PASS {method} {path} HTTP {status}", flush=True)
    return object_response(payload, path)


def wait_ready(client: Client, readiness_seconds: float = 90) -> None:
    end = time.monotonic() + readiness_seconds
    while time.monotonic() < end:
        try:
            status, payload, _ = client.request("GET", API + "/health/ready")
            if (
                status == 200
                and isinstance(payload, dict)
                and payload.get("status") == "ready"
                and all(
                    payload.get(store) == "ok"
                    for store in ("postgres", "neo4j", "redis")
                )
            ):
                print("PASS readiness: all three stores ready", flush=True)
                return
        except SmokeError:
            pass
        time.sleep(1)
    raise SmokeError("All-store readiness was not reached before the startup deadline.")


def empty_corpus(client: Client) -> None:
    stats = expect(client, "GET", "/corpus/stats", (200,))
    require(
        stats.get("total") == 0 and stats.get("embedded") == 0,
        "Fixture corpus is not empty; refusing fixture writes.",
    )
    nlp = stats.get("nlp_counts")
    require(
        isinstance(nlp, dict) and all(value == 0 for value in nlp.values()),
        "Fixture contains pending articles; refusing fixture writes.",
    )
    claims = expect(client, "GET", "/verdicts/stats", (200,))
    require(
        claims.get("total_claims") == 0,
        "Fixture contains scientific claims; refusing fixture writes.",
    )


def check_analysis(
    payload: dict[str, Any],
    body: dict[str, Any],
    *,
    numeric: bool,
) -> None:
    analysis = object_response(payload.get("analysis"), "mutation analysis")
    types = analysis.get("mutation_types")
    if not isinstance(types, list) or not all(isinstance(value, str) for value in types):
        raise SmokeError("Mutation comparison must return typed changes.")
    require(
        analysis.get("observed_propagation") is False,
        "Text comparison must not claim observed or causal propagation.",
    )
    require(
        bool(analysis.get("algorithm_version")) and bool(analysis.get("limitations")),
        "Mutation analysis must disclose its method and limitations.",
    )
    if numeric:
        require(
            "NUMERIC_DRIFT" in types and analysis.get("meaningful_change") is True,
            "The real comparison API did not identify the numeric fixture change.",
        )
        require(
            analysis.get("temporal_order") == "strictly_older"
            and analysis.get("lag_seconds") == 3600,
            "Comparison lost the supplied timestamp ordering.",
        )
    else:
        require(
            types == ["NEAR_DUPLICATE"] and analysis.get("meaningful_change") is False,
            "Identical text must not be reported as meaningful mutation.",
        )
    spans = analysis.get("changed_spans")
    if not isinstance(spans, list) or (numeric and not spans):
        raise SmokeError("Mutation analysis must expose changed spans.")
    for span in spans:
        require(isinstance(span, dict), "Changed span is malformed.")
        for side in ("older", "newer"):
            change = object_response(span.get(f"{side}_span"), "changed text span")
            start, end = change.get("start"), change.get("end")
            text = body[f"{side}_text"]
            require(
                isinstance(start, int)
                and isinstance(end, int)
                and 0 <= start <= end <= len(text),
                "Changed span offsets are invalid.",
            )
            require(
                text[start:end] == change.get("text"),
                "Changed spans do not point into the submitted fixture text.",
            )


def run_smoke(client: Client) -> None:
    wait_ready(client)
    # This is a second guard, not a substitute for the dedicated tmpfs Compose file.
    empty_corpus(client)
    articles = expect(client, "GET", "/corpus/articles?limit=5&offset=0", (200,))
    require(
        articles.get("total") == 0 and articles.get("items") == [],
        "An empty corpus listing is a valid response, not a skipped smoke case.",
    )

    status, _, headers = client.request("GET", "/", json_body=False)
    require(status == 200, "The production SPA was not served through nginx.")
    csp = headers.get("content-security-policy", "")
    require(
        headers.get("x-frame-options", "").upper() == "DENY"
        and "frame-ancestors 'none'" in csp
        and "connect-src 'self'" in csp
        and "https://fonts.googleapis.com" in csp
        and "https://fonts.gstatic.com" in csp,
        "SPA proxy headers do not match the deployment contract.",
    )
    print(
        "PASS SPA response security headers (not a browser rendering test)", flush=True
    )

    expect(client, "GET", "/auth/me", (401, 403))
    for path in ADMIN_TRIGGERS:
        expect(client, "POST", path, (401, 403), body={})
    evidence = {"claim_text": "The fixture agency reported 10 cases.", "limit": 1}
    expect(client, "POST", "/verdicts/check", (401, 403), body=evidence)
    comparison = {
        "older_text": "The agency reportedly found 10 survivors.",
        "newer_text": "The agency found 12 survivors.",
        "older_timestamp": "2026-09-20T12:00:00Z",
        "newer_timestamp": "2026-09-20T13:00:00Z",
    }
    expect(client, "POST", "/graph/mutation/compare", (401, 403), body=comparison)
    expect(client, "GET", "/eval/next", (401, 403))

    credentials = {
        "email": f"smoke-{uuid.uuid4().hex}@example.com",
        "password": "Fixture-" + secrets.token_urlsafe(24),
        "full_name": "Disposable HTTP smoke",
    }
    registered = expect(client, "POST", "/auth/register", (201,), body=credentials)
    require(
        isinstance(registered.get("access_token"), str),
        "Registration did not return the existing token-pair contract.",
    )
    logged_in = expect(
        client,
        "POST",
        "/auth/login",
        (200,),
        body={
            "email": credentials["email"],
            "password": credentials["password"],
        },
    )
    token = logged_in.get("access_token")
    require(isinstance(token, str) and bool(token), "Login returned no access token.")
    require(
        logged_in.get("token_type", "").lower() == "bearer",
        "Login token type is not bearer.",
    )
    me = expect(client, "GET", "/auth/me", (200,), token=token)
    require(
        me.get("email") == credentials["email"] and me.get("role") == "user",
        "The fixture account must be an ordinary, server-assigned user.",
    )
    for path in ADMIN_TRIGGERS:
        expect(client, "POST", path, (403,), body={}, token=token)

    identical = {
        "older_text": "The agency found 10 survivors.",
        "newer_text": "The agency found 10 survivors.",
    }
    same = expect(
        client, "POST", "/graph/mutation/compare", (200,), body=identical, token=token
    )
    check_analysis(same, identical, numeric=False)
    changed = expect(
        client, "POST", "/graph/mutation/compare", (200,), body=comparison, token=token
    )
    check_analysis(changed, comparison, numeric=True)
    next_pair = expect(client, "GET", "/eval/next", (200,), token=token)
    require(
        next_pair.get("done") is True,
        "Fresh fixture unexpectedly has evaluation pairs.",
    )
    progress = expect(client, "GET", "/eval/progress", (200,), token=token)
    require(progress.get("total_pairs") == 0, "Smoke must not create evaluation pairs.")
    # No /eval/label or /verdicts/feedback write exists anywhere in this smoke flow.
    empty_corpus(client)
    print(
        "PASS HTTP end-to-end smoke; no scientific labels or corpus records written",
        flush=True,
    )


def _worker(base: str, deadline_seconds: int, request_timeout: int) -> None:
    try:
        run_smoke(
            HttpClient(base, request_timeout, time.monotonic() + deadline_seconds)
        )
    except SmokeError as exc:
        print(f"FAIL HTTP smoke: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from None
    except Exception as exc:
        # Transport/read errors must not print response bodies or generated tokens.
        print(
            f"FAIL HTTP smoke: unexpected {type(exc).__name__}",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1) from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://frontend")
    parser.add_argument("--fixture-only", action="store_true")
    parser.add_argument("--deadline-seconds", type=int, default=240)
    parser.add_argument("--request-timeout", type=int, default=8)
    args = parser.parse_args()
    try:
        base = fixture_base_url(args.base_url, args.fixture_only)
        require(30 <= args.deadline_seconds <= 300, "Deadline must be 30–300 seconds.")
        require(
            1 <= args.request_timeout <= 15, "Request timeout must be 1–15 seconds."
        )
    except SmokeError as exc:
        print(f"Smoke refused: {exc}", file=sys.stderr)
        return 2
    worker = multiprocessing.Process(
        target=_worker,
        args=(base, args.deadline_seconds, args.request_timeout),
        daemon=True,
    )
    worker.start()
    worker.join(args.deadline_seconds)
    if worker.is_alive():
        worker.terminate()
        worker.join(5)
        if worker.is_alive():
            worker.kill()
            worker.join(1)
        print("FAIL HTTP smoke: hard wall-clock deadline exceeded", file=sys.stderr)
        return 1
    return 0 if worker.exitcode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
