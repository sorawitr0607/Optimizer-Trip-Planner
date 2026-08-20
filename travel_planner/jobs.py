"""A job table, because the work does not fit in a request.

Discovery takes 30-90 seconds of Overpass and a full proposal takes about 52; a
measured end-to-end flow took 210. A serverless function is cut off long before
any of that, so on a hosted deployment the request cannot be the thing that does
the work. It enqueues, and something else runs it.

**Deliberately outside `SCHEMA_VERSION`.** That number gates whether stored
*planning* data can still be read, and bumping it makes `store.py` refuse to
migrate until the database has been copied — a rule `PostgresStore` enforces by
refusing outright, since a hosted database is not a file. A queue holds no
planning truth: it can be dropped and rebuilt at any time and no plan becomes
unreadable. So it carries its own idempotent DDL and leaves the version alone.

**Local runs do not need any of this.** The desktop app is a long-lived process
that can simply block for 52 seconds, and it always could. This exists for the
hosted case; `actions.py` is untouched.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .wire import jsonable

#: Only these may be enqueued. The same reasoning as the API's literal method
#: allowlist: a queue that will run any named function is a remote code path, and
#: `dir()`-style dispatch is how one gets built by accident.
HANDLERS: dict[str, str] = {
    "discover_places": "discover_places",
    "generate_plan_preview": "generate_plan_preview",
    "refresh_routes": "refresh_routes",
}

#: The payload keys each operation will accept, because `method(**payload)` on an
#: unchecked dict is a way to reach arguments the caller was never offered. The
#: same reasoning as the API's literal method allowlist: name what is permitted
#: rather than filtering what is not.
PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "discover_places": frozenset({"force_refresh"}),
    "generate_plan_preview": frozenset({"time_limit_seconds", "allow_paid"}),
    "refresh_routes": frozenset({"limit"}),
}

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"

#: A job still `running` after this long is assumed to belong to a worker that
#: died. Comfortably longer than the slowest real operation (~210s measured), or
#: reaping would kill work that is merely slow.
STALE_AFTER_SECONDS = 900

DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    trip_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    claimed_by TEXT,
    claimed_at TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    result_json TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS jobs_claimable ON jobs (status, created_at);
CREATE INDEX IF NOT EXISTS jobs_by_trip ON jobs (trip_id, created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobQueue:
    def __init__(self, store: Any) -> None:
        self.store = store
        # `PostgresStore` subclasses `SQLiteStore`, so the test is on the class
        # name rather than on isinstance, which would be true for both.
        self.is_postgres = type(store).__name__ == "PostgresStore"
        with self.store.connect() as connection:
            # Same reason as PostgresStore._initialize: a serverless deployment
            # builds a queue on every cold start, and re-running the DDL each time
            # is a round trip and a catalogue lock for a table that is almost
            # always already there. One cheap existence check instead.
            present = connection.execute(
                "SELECT to_regclass('public.jobs') IS NOT NULL AS present"
                if self.is_postgres
                else "SELECT COUNT(*) AS present FROM sqlite_master "
                "WHERE type = 'table' AND name = 'jobs'"
            ).fetchone()
            if present and present["present"]:
                return
            for statement in DDL.strip().split(";"):
                if statement.strip():
                    connection.execute(statement)

    def enqueue(self, kind: str, trip_id: str, payload: dict | None = None,
                max_attempts: int = 3) -> str:
        """Queue the work, or return the job already doing it.

        Discovery is 30-90 seconds of a free public service and an optimize is
        about 52 of solver time. Two presses of a button, or a retry after a slow
        response, would otherwise buy the same answer twice — and this app's own
        rule is that `Find places` is a one-press control for exactly that reason.
        An identical operation already queued or running for the same trip is
        returned rather than duplicated.
        """
        if kind not in HANDLERS:
            raise ValueError(f"{kind} is not an enqueueable operation")
        payload = payload or {}
        unexpected = set(payload) - PAYLOAD_KEYS[kind]
        if unexpected:
            raise ValueError(f"{kind} does not take {sorted(unexpected)}")

        with self.store.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM jobs WHERE trip_id = ? AND kind = ? AND payload_json = ?"
                " AND status IN (?, ?) ORDER BY created_at LIMIT 1",
                (trip_id, kind, json.dumps(payload), QUEUED, RUNNING),
            ).fetchone()
            if existing is not None:
                return existing["id"]

        job_id = "job_" + uuid.uuid4().hex
        with self.store.connect() as connection:
            connection.execute(
                "INSERT INTO jobs (id, kind, trip_id, payload_json, status, attempts,"
                " max_attempts, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (job_id, kind, trip_id, json.dumps(payload), QUEUED, 0,
                 max_attempts, _now()),
            )
        return job_id

    def claim(self, worker_id: str) -> dict | None:
        """Take one queued job, or return None.

        On Postgres this is `FOR UPDATE SKIP LOCKED`, which is the whole reason
        more than one worker is safe: the row is locked as it is selected and any
        other worker steps over it rather than blocking on it. SQLite has no such
        clause and does not need one — it serialises writers, and the local app is
        a single process — so there the update is simply guarded on the status it
        expected to find, which fails harmlessly if another writer got there.
        """
        with self.store.connect() as connection:
            if self.is_postgres:
                row = connection.execute(
                    "UPDATE jobs SET status = ?, claimed_by = ?, claimed_at = ?,"
                    " attempts = attempts + 1 WHERE id = ("
                    "  SELECT id FROM jobs WHERE status = ? ORDER BY created_at"
                    "  FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *",
                    (RUNNING, worker_id, _now(), QUEUED),
                ).fetchone()
                return dict(row) if row else None

            candidate = connection.execute(
                "SELECT id FROM jobs WHERE status = ? ORDER BY created_at LIMIT 1",
                (QUEUED,),
            ).fetchone()
            if candidate is None:
                return None
            job_id = candidate["id"]
            connection.execute(
                "UPDATE jobs SET status = ?, claimed_by = ?, claimed_at = ?,"
                " attempts = attempts + 1 WHERE id = ? AND status = ?",
                (RUNNING, worker_id, _now(), job_id, QUEUED),
            )
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row and row["status"] == RUNNING else None

    def complete(self, job_id: str, result: Any) -> None:
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, result_json = ?, finished_at = ?,"
                " error = NULL WHERE id = ?",
                (DONE, json.dumps(result, default=str), _now(), job_id),
            )

    def fail(self, job_id: str, error: str) -> str:
        """Back to the queue while attempts remain, otherwise finished and failed.

        The message is kept either way. A job that vanishes on its last failure
        leaves the caller polling something that will never change.
        """
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT attempts, max_attempts FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return FAILED
            retry = row["attempts"] < row["max_attempts"]
            status = QUEUED if retry else FAILED
            connection.execute(
                "UPDATE jobs SET status = ?, error = ?, claimed_by = NULL,"
                " finished_at = ? WHERE id = ?",
                (status, error[:2000], None if retry else _now(), job_id),
            )
            return status

    def reap_stale(self) -> int:
        """Return jobs whose worker died to the queue.

        Without this a process killed mid-job leaves the row `running` for ever
        and the caller polls a job nobody is working on.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALE_AFTER_SECONDS)).isoformat()
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM jobs WHERE status = ? AND claimed_at < ?", (RUNNING, cutoff)
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE jobs SET status = ?, claimed_by = NULL,"
                    " error = 'worker did not finish' WHERE id = ?",
                    (QUEUED, row["id"]),
                )
            return len(rows)

    def get(self, job_id: str) -> dict | None:
        with self.store.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None


def run_one(queue: JobQueue, actions: Any, worker_id: str) -> dict | None:
    """Claim a job, run it, record the outcome. Returns the job, or None if idle."""
    job = queue.claim(worker_id)
    if job is None:
        return None
    try:
        method: Callable = getattr(actions, HANDLERS[job["kind"]])
        payload = json.loads(job["payload_json"])
        result = method(trip_id=job["trip_id"], **payload)
        # The same conversion the HTTP path applies. Without it the action's return
        # went through `json.dumps(..., default=str)`, so a dataclass reached the
        # browser as its own Python repr inside a string -- and the screen looking
        # for `.candidates.data` on that said "Cannot read properties of undefined
        # (reading 'data')". The work had succeeded every time; only its shape was
        # wrong, which is why the worker logged `done in 33.6s` and the page broke.
        queue.complete(job["id"], jsonable(result))
    except Exception as error:  # noqa: BLE001 - the message is the product here
        queue.fail(job["id"], f"{type(error).__name__}: {error}")
    return queue.get(job["id"])
