"""Offline safety regressions; no containers, sockets or live DB connections."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str, relative: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


backup = load_script("gmee_infra_backup", "backend/scripts/backup_database.py")
smoke = load_script("gmee_infra_smoke", "infra/scripts/http_smoke.py")
junit = load_script("gmee_infra_junit", "infra/scripts/require_integration_results.py")


class BackupSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="gmee-backup-unit-")
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "fixture.dump"
        self.environment = patch.dict(
            os.environ,
            {
                "POSTGRES_URL": "postgresql+asyncpg://fixture:pa%3Ass%40word@localhost:5432/fixture_db?sslmode=require",
            },
            clear=True,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_credentials_are_libpq_env_not_process_arguments(self) -> None:
        env = backup.dump_environment("POSTGRES_URL", 300)
        self.assertEqual(env["PGPASSWORD"], "pa:ss@word")
        self.assertEqual(env["PGDATABASE"], "fixture_db")
        self.assertEqual(env["PGSSLMODE"], "require")
        self.assertNotIn("POSTGRES_URL", env)

    def test_success_uses_exclusive_output_and_bounded_pg_dump(self) -> None:
        def fake_dump(
            command: list[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            self.assertEqual(command[0], "pg_dump")
            self.assertIn("--no-password", command)
            self.assertNotIn("pa:ss@word", " ".join(command))
            self.assertNotIn("postgresql", " ".join(command))
            self.assertEqual(kwargs["timeout"], 12)
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            kwargs["stdout"].write(b"PGDMPfixture-unit-data")
            return subprocess.CompletedProcess(command, 0)

        with patch.object(backup.subprocess, "run", side_effect=fake_dump):
            backup.backup_database(self.output, timeout_seconds=12)
        self.assertEqual(self.output.read_bytes(), b"PGDMPfixture-unit-data")
        if os.name != "nt":
            self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_existing_archive_is_never_overwritten(self) -> None:
        self.output.write_bytes(b"user-owned-archive")
        with patch.object(backup.subprocess, "run") as run:
            with self.assertRaisesRegex(backup.BackupError, "refusing to overwrite"):
                backup.backup_database(self.output)
            run.assert_not_called()
        self.assertEqual(self.output.read_bytes(), b"user-owned-archive")

    def test_timeout_discards_partial_and_redacts_exception(self) -> None:
        failure = subprocess.TimeoutExpired("postgresql://secret-value", 12)
        with (
            patch.object(backup.subprocess, "run", side_effect=failure),
            self.assertRaises(backup.BackupError) as raised,
        ):
            backup.backup_database(self.output, timeout_seconds=12)
        self.assertFalse(self.output.exists())
        self.assertNotIn("secret-value", str(raised.exception))

    def test_dump_failure_discards_partial_and_never_logs_stderr(self) -> None:
        failure = subprocess.CalledProcessError(2, "pg_dump", stderr=b"secret-password")
        with (
            patch.object(backup.subprocess, "run", side_effect=failure),
            self.assertRaises(backup.BackupError) as raised,
        ):
            backup.backup_database(self.output)
        self.assertFalse(self.output.exists())
        self.assertNotIn("secret-password", str(raised.exception))

    def test_empty_or_non_dump_success_is_rejected(self) -> None:
        with (
            patch.object(backup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)),
            self.assertRaisesRegex(backup.BackupError, "custom-format"),
        ):
            backup.backup_database(self.output)
        self.assertFalse(self.output.exists())

    def test_missing_pg_dump_is_actionable_without_path_details(self) -> None:
        with (
            patch.object(backup.subprocess, "run", side_effect=FileNotFoundError("secret-path")),
            self.assertRaisesRegex(backup.BackupError, "compatible client") as raised,
        ):
            backup.backup_database(self.output)
        self.assertFalse(self.output.exists())
        self.assertNotIn("secret-path", str(raised.exception))

    def test_missing_env_and_bad_timeouts_do_not_create_archive(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(backup.BackupError):
            backup.backup_database(self.output)
        for timeout in (0, -1, 3601):
            with self.assertRaises(backup.BackupError):
                backup.backup_database(self.output, timeout_seconds=timeout)
        self.assertFalse(self.output.exists())

    def test_unsupported_dsn_options_fail_without_disclosing_values(self) -> None:
        with (
            patch.dict(os.environ, {"POSTGRES_URL": "postgresql://fixture:secret@localhost/fixture?password=secret"}),
            self.assertRaises(backup.BackupError) as raised,
        ):
            backup.dump_environment("POSTGRES_URL", 300)
        self.assertNotIn("secret", str(raised.exception))

    def test_explicit_libpq_mode_requires_target(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(backup.BackupError):
            backup.dump_environment(None, 300)
        with patch.dict(
            os.environ, {"PGHOST": "localhost", "PGDATABASE": "fixture_db"}, clear=True
        ):
            self.assertEqual(
                backup.dump_environment(None, 300)["PGDATABASE"], "fixture_db"
            )


class RequiredIntegrationGateTests(unittest.TestCase):
    def check(self, xml: str) -> int:
        with tempfile.TemporaryDirectory(prefix="gmee-junit-unit-") as directory:
            report = Path(directory) / "results.xml"
            report.write_text(xml, encoding="utf-8")
            return int(junit.check_report(report))

    def test_passing_tests_are_counted_without_duplicate_suite_totals(self) -> None:
        self.assertEqual(
            self.check(
                '<testsuites><testsuite tests="2"><testcase name="a"/><testcase name="b"/></testsuite></testsuites>'
            ),
            2,
        )

    def test_skipped_failed_and_errored_cases_all_fail(self) -> None:
        for outcome in ("skipped", "failure", "error"):
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                self.check(
                    f"<testsuites><testsuite><testcase><{outcome}/></testcase></testsuite></testsuites>"
                )

    def test_empty_malformed_and_missing_reports_fail(self) -> None:
        for xml in ("<testsuites/>", "not xml"):
            with self.assertRaises(ValueError):
                self.check(xml)
        with self.assertRaises(ValueError):
            junit.check_report(ROOT / "infra/nonexistent-unit-fixture.xml")


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None, str | None]] = []
        self.email = ""
        self.nonempty = False
        self.pending = False
        self.claim_propagation = False
        self.hide_numeric_type = False

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        token: str | None = None,
        json_body: bool = True,
    ) -> tuple[int, Any, dict[str, str]]:
        self.calls.append((method, path, body, token))
        prefix = "/api/v1"
        status = 200
        payload: dict[str, Any] = {}
        headers: dict[str, str] = {}
        if path == "/":
            headers = {
                "x-frame-options": "DENY",
                "content-security-policy": "connect-src 'self'; frame-ancestors 'none'; https://fonts.googleapis.com https://fonts.gstatic.com",
            }
        elif path == prefix + "/health/ready":
            payload = {
                "status": "ready",
                "postgres": "ok",
                "neo4j": "ok",
                "redis": "ok",
            }
        elif path == prefix + "/corpus/stats":
            payload = {
                "total": 1 if self.nonempty else 0,
                "embedded": 0,
                "nlp_counts": {"pending": 1} if self.pending else {},
            }
        elif path == prefix + "/verdicts/stats":
            payload = {"total_claims": 0}
        elif path.startswith(prefix + "/corpus/articles"):
            payload = {"total": 0, "items": []}
        elif path == prefix + "/auth/register":
            assert body is not None
            self.email = body["email"]
            status, payload = 201, {"access_token": "fixture-register-token"}
        elif path == prefix + "/auth/login":
            payload = {"access_token": "fixture-login-token", "token_type": "bearer"}
        elif path == prefix + "/auth/me":
            if token is None:
                status, payload = 401, {"detail": "Not authenticated"}
            else:
                payload = {"email": self.email, "role": "user"}
        elif any(path == prefix + trigger for trigger in smoke.ADMIN_TRIGGERS):
            status, payload = (401 if token is None else 403), {"detail": "Forbidden"}
        elif path == prefix + "/verdicts/check":
            status, payload = 401, {"detail": "Not authenticated"}
        elif path == prefix + "/eval/next":
            status, payload = (
                (401, {"detail": "Not authenticated"})
                if token is None
                else (200, {"done": True})
            )
        elif path == prefix + "/eval/progress":
            payload = {"total_pairs": 0}
        elif path == prefix + "/graph/mutation/compare":
            if token is None:
                status, payload = 401, {"detail": "Not authenticated"}
            else:
                assert body is not None
                numeric = body["older_text"] != body["newer_text"]
                spans = []
                if numeric:
                    start_a, start_b = (
                        body["older_text"].index("10"),
                        body["newer_text"].index("12"),
                    )
                    spans = [
                        {
                            "older_span": {
                                "start": start_a,
                                "end": start_a + 2,
                                "text": "10",
                            },
                            "newer_span": {
                                "start": start_b,
                                "end": start_b + 2,
                                "text": "12",
                            },
                        }
                    ]
                payload = {
                    "analysis": {
                        "mutation_types": (
                            ["WORDING_DRIFT"]
                            if self.hide_numeric_type
                            else ["NUMERIC_DRIFT"]
                        )
                        if numeric
                        else ["NEAR_DUPLICATE"],
                        "meaningful_change": numeric,
                        "observed_propagation": self.claim_propagation,
                        "algorithm_version": "unit-fixture",
                        "limitations": ["Heuristic"],
                        "temporal_order": "strictly_older" if numeric else "unknown",
                        "lag_seconds": 3600 if numeric else None,
                        "changed_spans": spans,
                    }
                }
        else:
            raise AssertionError(f"Unexpected smoke request: {method} {path}")
        return status, payload, headers


class HttpSmokeSafetyTests(unittest.TestCase):
    def test_fixture_acknowledgement_and_origin_are_required(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(smoke.SmokeError):
            smoke.fixture_base_url("http://frontend", True)
        with patch.dict(os.environ, {"GMEE_SMOKE_FIXTURE": "1"}, clear=True):
            self.assertEqual(
                smoke.fixture_base_url("http://frontend/", True), "http://frontend"
            )
            for base in (
                "https://live.example.com",
                "http://user:secret@localhost",
                "http://localhost/api/v1",
                "http://localhost?x=1",
            ):
                with self.assertRaises(smoke.SmokeError):
                    smoke.fixture_base_url(base, True)
            with self.assertRaises(smoke.SmokeError):
                smoke.fixture_base_url("http://frontend", False)

    def test_http_flow_checks_real_comparison_contract_without_labels(self) -> None:
        client = FakeHttpClient()
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            smoke.run_smoke(client)
        paths = [call[1] for call in client.calls]
        self.assertNotIn("/api/v1/eval/label", paths)
        self.assertNotIn("/api/v1/verdicts/feedback", paths)
        self.assertEqual(sum(path == "/api/v1/auth/register" for path in paths), 1)
        comparisons = [
            call
            for call in client.calls
            if call[1] == "/api/v1/graph/mutation/compare" and call[3]
        ]
        self.assertEqual(len(comparisons), 2)
        self.assertNotIn("fixture-login-token", stream.getvalue())
        self.assertNotIn(client.email, stream.getvalue())

    def test_nonempty_or_pending_corpus_refuses_account_writes(self) -> None:
        for field in ("nonempty", "pending"):
            client = FakeHttpClient()
            setattr(client, field, True)
            with (
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaises(smoke.SmokeError),
            ):
                smoke.run_smoke(client)
            self.assertFalse(any(call[0] == "POST" for call in client.calls))

    def test_fabricated_propagation_or_missing_numeric_type_fails(self) -> None:
        for field in ("claim_propagation", "hide_numeric_type"):
            client = FakeHttpClient()
            setattr(client, field, True)
            with (
                contextlib.redirect_stdout(io.StringIO()),
                self.assertRaises(smoke.SmokeError),
            ):
                smoke.run_smoke(client)

    def test_redirects_are_not_followed(self) -> None:
        self.assertIsNone(
            smoke.NoRedirect().redirect_request(
                None, None, 302, "redirect", {}, "http://live.example.com"
            )
        )

    def test_http_deadline_is_checked_before_network_io(self) -> None:
        client = smoke.HttpClient("http://frontend", 8, 0)
        with patch.object(client.opener, "open") as open_request:
            with self.assertRaises(smoke.SmokeError):
                client.request("GET", "/api/v1/health/ready")
            open_request.assert_not_called()


class StaticComposeSafetyTests(unittest.TestCase):
    def test_config_resolution_uses_only_a_temporary_nonsecret_env_file(self) -> None:
        validator = load_script(
            "gmee_infra_validator", "infra/scripts/validate_deployment.py"
        )

        def fake_config(
            command: list[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            self.assertIn("--no-env-resolution", command)
            self.assertIn("--no-interpolate", command)
            env = Path(command[command.index("--env-file") + 1])
            self.assertNotEqual(env, ROOT / ".env")
            self.assertEqual(
                env.read_text(encoding="utf-8"), "GMEE_STATIC_VALIDATION=1\n"
            )
            self.assertEqual(kwargs["timeout"], 30)
            self.assertNotIn("up", command)
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps({"services": {}})
            )

        with (
            patch.object(validator.subprocess, "run", side_effect=fake_config),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                validator.compose_model(["infra/docker-compose.yml"]), {"services": {}}
            )


if __name__ == "__main__":
    unittest.main()
