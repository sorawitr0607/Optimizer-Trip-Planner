#!/usr/bin/env python3
"""Dump the live Supabase application schema without data or credentials."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import parse_qs, unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / ".env"
DEFAULT_OUTPUT = (
    ROOT
    / "supabase"
    / "backups"
    / f"supabase-public-schema-{datetime.now(timezone.utc):%Y-%m-%d}.sql"
)
REQUIRED_OBJECTS = (
    "CREATE TABLE public.trips",
    "CREATE TABLE public.jobs",
    "CREATE TABLE public.paid_usage",
    "CREATE TABLE public.schema_meta",
    "CREATE FUNCTION public.refuse_write()",
)


def read_database_url(path: Path) -> str:
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("POSTGRES_URL_NON_POOLING="):
            return raw.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"POSTGRES_URL_NON_POOLING is missing from {path}")


def connection_environment(url: str) -> dict[str, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError("POSTGRES_URL_NON_POOLING is not a PostgreSQL URL")
    if parsed.username is None or parsed.password is None:
        raise RuntimeError("The PostgreSQL URL is missing its user or password")
    database = parsed.path.removeprefix("/")
    if not database:
        raise RuntimeError("The PostgreSQL URL is missing its database name")
    query = parse_qs(parsed.query)
    return {
        "PGHOST": parsed.hostname,
        "PGPORT": str(parsed.port or 5432),
        "PGDATABASE": unquote(database),
        "PGUSER": unquote(parsed.username),
        "PGPASSWORD": unquote(parsed.password),
        "PGSSLMODE": query.get("sslmode", ["require"])[0],
        "PGCONNECT_TIMEOUT": "15",
    }


def pg_dump_path() -> str:
    candidates = (
        shutil.which("pg_dump"),
        "/opt/homebrew/opt/libpq/bin/pg_dump",
        "/usr/local/opt/libpq/bin/pg_dump",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError("pg_dump is missing; install PostgreSQL client tools or Homebrew libpq")


def backup(*, env_file: Path, output: Path) -> tuple[Path, str]:
    url = read_database_url(env_file)
    connection = connection_environment(url)
    password = connection["PGPASSWORD"]
    environment = {**os.environ, **connection}
    for key in ("TOURIST_DB_URL", "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE"):
        environment.pop(key, None)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        subprocess.run(
            [
                pg_dump_path(),
                "--schema-only",
                "--schema=public",
                "--no-owner",
                "--no-privileges",
                "--no-security-labels",
                "--no-tablespaces",
                f"--file={temporary}",
            ],
            check=True,
            env=environment,
        )
        text = temporary.read_text(encoding="utf-8")
        missing = [name for name in REQUIRED_OBJECTS if name not in text]
        if missing:
            raise RuntimeError(f"Dump is missing required objects: {', '.join(missing)}")
        if password and password in text:
            raise RuntimeError("Refusing to save a dump containing the database password")
        header = (
            "-- Optimizer Trip Planner live Supabase structure backup.\n"
            f"-- Captured: {datetime.now(timezone.utc).isoformat()}\n"
            "-- Scope: public schema only; no rows, owners, grants, or credentials.\n"
            "-- Restore into an empty PostgreSQL database with psql --set ON_ERROR_STOP=1 --file FILE.\n\n"
        )
        temporary.write_text(header + text, encoding="utf-8")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return output, digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    path, digest = backup(env_file=arguments.env_file, output=arguments.output)
    print(f"Wrote {path.relative_to(ROOT)}")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
