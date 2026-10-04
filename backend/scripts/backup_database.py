"""Create a bounded PostgreSQL custom-format dump without logging credentials.

This utility never loads .env and never restores or migrates a database. Credentials
are passed to pg_dump through libpq environment variables, not command arguments.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit


class BackupError(RuntimeError):
    """An actionable, credential-free backup failure."""


def dump_environment(
    database_url_env: str | None, timeout_seconds: int
) -> dict[str, str]:
    env = os.environ.copy()
    if database_url_env is not None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database_url_env):
            raise BackupError("Use an environment variable name, not a database URL.")
        raw = env.get(database_url_env, "")
        if not raw:
            raise BackupError(
                "Database URL environment variable is unset; configure it explicitly."
            )
        try:
            url = urlsplit(raw)
            port = url.port
        except ValueError:
            raise BackupError("Database URL is malformed.") from None
        if url.scheme not in {
            "postgres",
            "postgresql",
            "postgresql+asyncpg",
            "postgresql+psycopg",
        }:
            raise BackupError("Only PostgreSQL database URLs are supported.")
        if not url.hostname or not url.path.lstrip("/") or url.fragment:
            raise BackupError("Database URL must identify a host and database.")
        env["PGHOST"] = url.hostname
        env["PGPORT"] = str(port or 5432)
        env["PGDATABASE"] = unquote(url.path.lstrip("/"))
        if url.username is not None:
            env["PGUSER"] = unquote(url.username)
        if url.password is not None:
            env["PGPASSWORD"] = unquote(url.password)
        # Do not let a inherited service definition silently select another DB.
        env.pop("PGSERVICE", None)
        allowed_options = {
            "sslmode": "PGSSLMODE",
            "sslrootcert": "PGSSLROOTCERT",
            "sslcert": "PGSSLCERT",
            "sslkey": "PGSSLKEY",
        }
        seen: set[str] = set()
        for key, value in parse_qsl(url.query, keep_blank_values=True):
            if key not in allowed_options or key in seen:
                raise BackupError("Database URL contains unsupported query options.")
            seen.add(key)
            env[allowed_options[key]] = value
        env.pop(database_url_env, None)
    elif not env.get("PGHOST") or not env.get("PGDATABASE"):
        raise BackupError("Explicit libpq mode requires PGHOST and PGDATABASE.")

    for key in ("POSTGRES_URL", "DATABASE_URL"):
        env.pop(key, None)
    if any("\x00" in value for value in env.values()):
        raise BackupError("Environment contains an invalid NUL character.")
    env["PGCONNECT_TIMEOUT"] = str(min(10, timeout_seconds))
    return env


def _remove_partial(output: Path, identity: os.stat_result) -> None:
    try:
        current = output.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
            output.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        raise BackupError(
            "Backup failed and an incomplete archive could not be removed. "
            "Remove it manually before retrying."
        ) from None


def backup_database(
    output: Path,
    *,
    timeout_seconds: int = 300,
    pg_dump: str = "pg_dump",
    database_url_env: str | None = "POSTGRES_URL",
) -> None:
    if not 1 <= timeout_seconds <= 3600:
        raise BackupError("Timeout must be between 1 and 3600 seconds.")
    env = dump_environment(database_url_env, timeout_seconds)
    if not output.parent.is_dir():
        raise BackupError("Output directory must already exist.")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(output, flags, 0o600)
    except FileExistsError:
        raise BackupError("Output already exists; refusing to overwrite it.") from None
    except OSError:
        raise BackupError("Cannot exclusively create the output archive.") from None

    identity = os.fstat(fd)
    complete = False
    try:
        with os.fdopen(fd, "wb") as archive:
            try:
                subprocess.run(
                    [
                        pg_dump,
                        "--format=custom",
                        "--no-owner",
                        "--no-acl",
                        "--no-password",
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=archive,
                    stderr=subprocess.DEVNULL,
                    env=env,
                    check=True,
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                raise BackupError(
                    "pg_dump exceeded the timeout; archive discarded."
                ) from None
            except subprocess.CalledProcessError as exc:
                raise BackupError(
                    f"pg_dump failed (exit {exc.returncode}); check client version, "
                    "credentials and database access. Diagnostic stderr is not logged."
                ) from None
            except OSError:
                raise BackupError(
                    "Cannot execute pg_dump; install a compatible client."
                ) from None
            archive.flush()
            os.fsync(archive.fileno())
        with output.open("rb") as archive:
            if archive.read(5) != b"PGDMP":
                raise BackupError("pg_dump did not produce a custom-format archive.")
        complete = True
    except OSError:
        raise BackupError("Archive I/O failed; incomplete archive discarded.") from None
    finally:
        if not complete:
            _remove_partial(output, identity)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--pg-dump", default="pg_dump", help="pg_dump executable path")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--database-url-env", default="POSTGRES_URL")
    mode.add_argument("--use-libpq-environment", action="store_true")
    args = parser.parse_args()
    try:
        backup_database(
            args.output,
            timeout_seconds=args.timeout_seconds,
            pg_dump=args.pg_dump,
            database_url_env=None
            if args.use_libpq_environment
            else args.database_url_env,
        )
    except BackupError as exc:
        print(f"Backup refused/failed: {exc}", file=sys.stderr)
        return 1
    print("Backup completed. Protect the archive and verify an isolated restore.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
