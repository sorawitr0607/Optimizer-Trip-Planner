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
    # `http_504` from a phone, reported with a screenshot. `recommend_areas` asks
    # Overpass for amenity counts around every candidate station neighbourhood --
    # tens of seconds of work -- and it was running inline in a function capped at
    # 60. The gateway gave up before the answer arrived, so the stage was
    # unreachable on the deployment while working locally, where nothing caps it.
    # Queued now, like the other three operations that outlast a request.
    "recommend_areas": "recommend_areas",
}

#: The payload keys each operation will accept, because `method(**payload)` on an
#: unchecked dict is a way to reach arguments the caller was never offered. The
#: same reasoning as the API's literal method allowlist: name what is permitted
#: rather than filtering what is not.
PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "discover_places": frozenset({"force_refresh"}),
    "generate_plan_preview": frozenset({"time_limit_seconds"}),
    "refresh_routes": frozenset({"max_passes"}),
    "recommend_areas": frozenset(),
}

#: Operations that describe their own wait, and are therefore handed a progress
#: sink by `run_one`.
#:
#: What the number *means* belongs to the operation, because the screen that asked
#: for it is the screen that reads it. `discover_places` counts stages it has
#: finished — geocode, two Overpass blocks, catalogue — and `/places` draws them as
#: a list. `refresh_routes` counts route pairs it has stored, and `/optimize` prints
#: it beside its routes stage, which is the number that screen was already showing
#: back when the browser made the passes itself and could count them.
#:
#: What both have in common is the only rule that matters: the number moves because
#: a call came back, never because time passed. An operation with nothing of that
#: kind to report is left out — an ignored `progress` argument would be a claim it
#: can say where it is.
REPORTS_PROGRESS: frozenset[str] = frozenset(
    {"discover_places", "refresh_routes", "generate_plan_preview"}
)

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"


def _claim_guard(worker_id: str | None) -> str:
    """The SQL that narrows a terminal write to the attempt still holding it."""

    return " AND claimed_by = ?" if worker_id else ""

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
    progress INTEGER,
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
            #
            # The check is on `progress` rather than on the table, because a queue
            # created before that column existed passes a table check and then
            # fails every write to it. A column implies its table, so this is the
            # same single read it always was.
            ready = connection.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns"
                " WHERE table_schema = 'public' AND table_name = 'jobs'"
                " AND column_name = 'progress') AS ready"
                if self.is_postgres
                else "SELECT COUNT(*) AS ready FROM pragma_table_info('jobs')"
                " WHERE name = 'progress'"
            ).fetchone()
            if ready and ready["ready"]:
                return
            for statement in DDL.strip().split(";"):
                if statement.strip():
                    connection.execute(statement)
            # `CREATE TABLE IF NOT EXISTS` does nothing to a queue that predates
            # `progress`, so that one case is migrated explicitly. Reached at most
            # once per database. Postgres gets `IF NOT EXISTS` because a failed
            # statement there aborts the surrounding transaction -- the hazard
            # `PostgresStore._stored_version` documents -- while SQLite, which has
            # no such clause, is asked first instead.
            if self.is_postgres:
                connection.execute(
                    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress INTEGER"
                )
            elif not connection.execute(
                "SELECT COUNT(*) AS present FROM pragma_table_info('jobs')"
                " WHERE name = 'progress'"
            ).fetchone()["present"]:
                connection.execute("ALTER TABLE jobs ADD COLUMN progress INTEGER")

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
        expected to find, and its rowcount is what decides: zero rows means another
        writer got there first, and this worker steps over the job.
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
            claimed = connection.execute(
                "UPDATE jobs SET status = ?, claimed_by = ?, claimed_at = ?,"
                " attempts = attempts + 1 WHERE id = ? AND status = ?",
                (RUNNING, worker_id, _now(), job_id, QUEUED),
            )
            # The guarded update is the whole race check, so its rowcount is the
            # answer — not a re-read. Zero rows means another worker claimed
            # between the select and the update, and re-reading the row would find
            # `running` *because they set it*: returning it here handed the same
            # job to both workers, duplicate paid work included. This worker steps
            # over it and comes back around.
            if claimed.rowcount != 1:
                return None
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row and row["status"] == RUNNING else None

    def report_progress(self, job_id: str, reached: int) -> None:
        """Record how far this job has got, as a number it defines itself.

        A count, not a label. The browser owns the words and already knows what it
        asked for, so sending one number keeps the two descriptions of the same wait
        from drifting apart in different languages. `REPORTS_PROGRESS` says which
        operations write here and what each one is counting.
        """
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE jobs SET progress = ? WHERE id = ?", (reached, job_id)
            )

    def complete(
        self, job_id: str, result: Any, *, worker_id: str | None = None
    ) -> None:
        # Fenced on the claim. A job that ran past STALE_AFTER_SECONDS was reaped
        # and re-claimed while its first worker was still going; that worker's
        # eventual result must not overwrite the newer attempt -- or, via a late
        # `fail`, flip a `done` job back to queued. The claim is (job, worker):
        # status alone cannot tell a zombie from the legitimate runner, because
        # the row reads `running` for both. A stale write is dropped.
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, result_json = ?, finished_at = ?,"
                " error = NULL WHERE id = ? AND status = ?" + _claim_guard(worker_id),
                [DONE, json.dumps(result, default=str), _now(), job_id, RUNNING]
                + ([worker_id] if worker_id else []),
            )

    def fail(
        self, job_id: str, error: str, *, worker_id: str | None = None
    ) -> str:
        """Back to the queue while attempts remain, otherwise finished and failed.

        The message is kept either way. A job that vanishes on its last failure
        leaves the caller polling something that will never change.

        Fenced on the claim, for the same reason `complete` is. The returned
        status is the outcome this failure *wanted*; a row reaped mid-failure,
        or held by a newer attempt, keeps its own.
        """
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT attempts, max_attempts FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return FAILED
            retry = row["attempts"] < row["max_attempts"]
            status = QUEUED if retry else FAILED
            # `progress` goes with it. A retry starts the operation over, and a
            # stage list still reading "3 of 5 done" describes work the new
            # attempt has not done yet.
            connection.execute(
                "UPDATE jobs SET status = ?, error = ?, claimed_by = NULL,"
                " progress = NULL, finished_at = ? WHERE id = ? AND status = ?"
                + _claim_guard(worker_id),
                [status, error[:2000], None if retry else _now(), job_id, RUNNING]
                + ([worker_id] if worker_id else []),
            )
            return status

    def reap_stale(self) -> int:
        """Return jobs whose worker died to the queue.

        Without this a process killed mid-job leaves the row `running` for ever
        and the caller polls a job nobody is working on.

        `max_attempts` is consulted here because a crash is the one failure that
        never reaches `fail`: a payload that kills its worker on every attempt
        would otherwise cycle claim -> die -> reap for ever, each cycle buying
        the same work. Attempts are counted on claim, so the count survives the
        crash that made reaping necessary.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALE_AFTER_SECONDS)).isoformat()
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT id, attempts, max_attempts FROM jobs"
                " WHERE status = ? AND claimed_at < ?",
                (RUNNING, cutoff),
            ).fetchall()
            for row in rows:
                exhausted = row["attempts"] >= row["max_attempts"]
                connection.execute(
                    "UPDATE jobs SET status = ?, claimed_by = NULL, progress = NULL,"
                    " error = 'worker did not finish', finished_at = ? WHERE id = ?",
                    (FAILED if exhausted else QUEUED,
                     _now() if exhausted else None,
                     row["id"]),
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
        if job["kind"] in REPORTS_PROGRESS:
            # Not from the payload, so `PAYLOAD_KEYS` is untouched: this is the
            # worker handing the operation somewhere to write, not a caller
            # reaching a keyword it was never offered.
            payload["progress"] = lambda reached: queue.report_progress(
                job["id"], reached
            )
            # Zero before the work starts, which is what separates "queued, and
            # nothing is running this" from "a worker has it". Until this lands
            # the screen has no reason to believe anyone is listening, and says
            # so by showing the rotating line instead of a stage list.
            payload["progress"](0)
        result = method(trip_id=job["trip_id"], **payload)
        # The same conversion the HTTP path applies. Without it the action's return
        # went through `json.dumps(..., default=str)`, so a dataclass reached the
        # browser as its own Python repr inside a string -- and the screen looking
        # for `.candidates.data` on that said "Cannot read properties of undefined
        # (reading 'data')". The work had succeeded every time; only its shape was
        # wrong, which is why the worker logged `done in 33.6s` and the page broke.
        queue.complete(job["id"], jsonable(result), worker_id=worker_id)
    except Exception as error:  # noqa: BLE001 - the message is the product here
        queue.fail(job["id"], f"{type(error).__name__}: {error}", worker_id=worker_id)
    return queue.get(job["id"])
