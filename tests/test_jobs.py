"""The job queue's guarantees, tested rather than asserted.

The one that matters is the claim: two workers must never run the same job. The
Postgres path gets that from `FOR UPDATE SKIP LOCKED`; these run on SQLite, so
they prove the ordinary properties and the concurrency test is run separately
against a real Postgres.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from travel_planner.jobs import DONE, FAILED, QUEUED, REPORTS_PROGRESS, RUNNING, JobQueue, run_one
from travel_planner.store import SQLiteStore


class JobQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "jobs.sqlite3")
        self.queue = JobQueue(self.store)

    def test_only_named_operations_may_be_enqueued(self) -> None:
        """A queue that runs any named function is a remote code path."""
        with self.assertRaises(ValueError):
            self.queue.enqueue("os.system", "T1", {})

    def test_a_claimed_job_cannot_be_claimed_again(self) -> None:
        self.queue.enqueue("discover_places", "T1")
        first = self.queue.claim("worker-a")
        second = self.queue.claim("worker-b")
        self.assertIsNotNone(first)
        self.assertIsNone(second, "the same job was handed to two workers")
        self.assertEqual(first["status"], RUNNING)
        self.assertEqual(first["attempts"], 1)

    def test_jobs_are_claimed_oldest_first(self) -> None:
        first = self.queue.enqueue("discover_places", "T1")
        second = self.queue.enqueue("discover_places", "T2")
        self.assertEqual(self.queue.claim("w")["id"], first)
        self.assertEqual(self.queue.claim("w")["id"], second)

    def test_failure_returns_the_job_until_attempts_run_out(self) -> None:
        job = self.queue.enqueue("discover_places", "T1", max_attempts=2)
        self.queue.claim("w")
        self.assertEqual(self.queue.fail(job, "provider down"), QUEUED)
        self.queue.claim("w")
        self.assertEqual(self.queue.fail(job, "provider down"), FAILED)
        # The message survives the last failure: a caller polling a job that
        # simply stopped changing has been told nothing.
        self.assertIn("provider down", self.queue.get(job)["error"])

    def test_completion_records_the_result_and_clears_the_error(self) -> None:
        job = self.queue.enqueue("discover_places", "T1")
        self.queue.claim("w")
        self.queue.fail(job, "first try failed")
        self.queue.claim("w")
        self.queue.complete(job, {"places": 715})
        row = self.queue.get(job)
        self.assertEqual(row["status"], DONE)
        self.assertIn("715", row["result_json"])
        self.assertIsNone(row["error"])

    def test_a_job_whose_worker_died_goes_back_to_the_queue(self) -> None:
        job = self.queue.enqueue("discover_places", "T1")
        self.queue.claim("worker-that-dies")
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE jobs SET claimed_at = ? WHERE id = ?", ("2000-01-01T00:00:00+00:00", job)
            )
        self.assertEqual(self.queue.reap_stale(), 1)
        self.assertEqual(self.queue.get(job)["status"], QUEUED)
        self.assertIsNotNone(self.queue.claim("worker-b"), "the reaped job was not claimable")

    def test_a_running_job_that_is_merely_slow_is_not_reaped(self) -> None:
        self.queue.enqueue("generate_plan_preview", "T1")
        self.queue.claim("w")
        self.assertEqual(self.queue.reap_stale(), 0)

    def test_an_empty_queue_returns_nothing_rather_than_blocking(self) -> None:
        self.assertIsNone(self.queue.claim("w"))


if __name__ == "__main__":
    unittest.main()


class JobQueueGuardsTest(unittest.TestCase):
    """The two guards added after the audit."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.queue = JobQueue(SQLiteStore(Path(self.directory.name) / "g.sqlite3"))

    def test_the_same_work_is_not_queued_twice(self) -> None:
        """30-90s of a free public service, bought once."""
        first = self.queue.enqueue("discover_places", "T1")
        self.assertEqual(self.queue.enqueue("discover_places", "T1"), first)

    def test_a_different_payload_is_different_work(self) -> None:
        plain = self.queue.enqueue("discover_places", "T1")
        forced = self.queue.enqueue("discover_places", "T1", {"force_refresh": True})
        self.assertNotEqual(plain, forced)

    def test_work_that_already_finished_may_be_queued_again(self) -> None:
        first = self.queue.enqueue("discover_places", "T1")
        self.queue.claim("w")
        self.queue.complete(first, {"ok": True})
        self.assertNotEqual(self.queue.enqueue("discover_places", "T1"), first)

    def test_a_payload_may_only_carry_arguments_the_operation_takes(self) -> None:
        with self.assertRaises(ValueError):
            self.queue.enqueue("discover_places", "T1", {"database_path": "/etc/passwd"})

class QueuedResultShapeTest(unittest.TestCase):
    """A queued result must be the shape the HTTP path would have returned.

    `discover_places` returns a dataclass holding a `FrozenSnapshot`. The queue
    stored the return value through `json.dumps(..., default=str)`, so the dataclass
    became its own Python repr inside a JSON string -- and the screen reading
    `.candidates.data` off that reported "Cannot read properties of undefined
    (reading 'data')" while the worker logged the job as done in 33.6 seconds. The
    work was never the problem; only what was written down about it.
    """

    def test_a_dataclass_result_survives_the_queue(self):
        from dataclasses import dataclass

        from travel_planner.core import FrozenSnapshot
        from travel_planner.jobs import HANDLERS, JobQueue, run_one
        from travel_planner.wire import jsonable

        payload = json.dumps({"candidates": [{"place_id": "node_1"}]}, sort_keys=True)
        snapshot = FrozenSnapshot(
            canonical_json=payload,
            sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        )

        @dataclass
        class DiscoveryLike:
            run_id: str
            candidates: FrozenSnapshot

        answer = DiscoveryLike(run_id="run-1", candidates=snapshot)

        class FakeActions:
            def __init__(self, store):
                self.store = store

            def discover_places(self, *, trip_id, progress=None):  # noqa: ARG002 - shape under test
                return answer

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(str(Path(directory) / "jobs.sqlite3"))
            queue = JobQueue(store)
            actions = FakeActions(store)
            self.assertIn("discover_places", HANDLERS)
            queue.enqueue("discover_places", "trip_x", {})
            job = run_one(queue, actions, "worker-1")

        self.assertEqual(job["status"], "done")
        stored = json.loads(job["result_json"])
        # The exact structure the browser indexes into.
        self.assertEqual(stored, jsonable(answer))
        self.assertIsInstance(stored, dict)
        self.assertIn("candidates", stored)
        self.assertIn("data", stored["candidates"])
        self.assertEqual(stored["candidates"]["sha256"], snapshot.sha256)




class PayloadAllowlistTest(unittest.TestCase):
    """A key the allowlist permits must be one its method accepts.

    Found by driving the deployment rather than by reading: enqueueing
    `generate_plan_preview` with `allow_paid` -- which the allowlist permitted --
    failed the job with `got an unexpected keyword argument`. `refresh_routes` had
    the same hole with `limit`. Both were keys that had been thought about and never
    existed, and the only way to hit either was to be a client that trusted the
    allowlist. Which is the whole point of publishing one.
    """

    def test_every_allowed_key_is_accepted_by_its_handler(self):
        import inspect

        from travel_planner.actions import PlannerActions
        from travel_planner.jobs import HANDLERS, PAYLOAD_KEYS

        for kind, method in HANDLERS.items():
            accepted = set(inspect.signature(getattr(PlannerActions, method)).parameters)
            for key in PAYLOAD_KEYS.get(kind, ()):
                with self.subTest(kind=kind, key=key):
                    self.assertIn(key, accepted)

    def test_every_handler_has_an_allowlist_entry(self):
        # A missing entry is not a licence to pass anything; `run_one` splats only what
        # the allowlist names, so an absent key set must mean "trip_id and nothing else".
        from travel_planner.jobs import HANDLERS, PAYLOAD_KEYS

        for kind in HANDLERS:
            self.assertIn(kind, PAYLOAD_KEYS)


class IdlePollBackoffTest(unittest.TestCase):
    """How often an idle worker asks an empty queue whether it is still empty.

    A flat two-second poll is 43,200 queries a day whether or not anyone is using the
    app, and on the hosted deployment that is billed egress. Supabase's free tier allows
    5.5 GB and this trip's reads had already passed it, so the interval backs off to ten
    seconds when nothing is arriving -- about 80% fewer polls on an idle day -- and
    resets the moment a job appears.

    The ramp is the part worth testing: settling too fast makes a burst of jobs wait,
    and not capping makes a quiet worker eventually stop noticing anything.
    """

    def test_the_interval_doubles_and_stops_at_the_ceiling(self) -> None:
        from travel_planner.worker import (
            IDLE_SLEEP_SECONDS,
            MAX_IDLE_SLEEP_SECONDS,
            next_idle_sleep,
        )

        waits = [IDLE_SLEEP_SECONDS]
        for _ in range(6):
            waits.append(next_idle_sleep(waits[-1]))

        self.assertEqual([2.0, 4.0, 8.0, 10.0, 10.0, 10.0, 10.0], waits)
        self.assertEqual(MAX_IDLE_SLEEP_SECONDS, waits[-1])

    def test_a_burst_of_work_never_waits_more_than_the_responsive_interval(self) -> None:
        """The reset is what makes the backoff free while the worker is working.

        Mirrors the loop: every job seen puts the interval back to `IDLE_SLEEP_SECONDS`,
        so consecutive jobs are picked up two seconds apart however long the quiet spell
        before them was.
        """

        from travel_planner.worker import IDLE_SLEEP_SECONDS, next_idle_sleep

        interval = IDLE_SLEEP_SECONDS
        for _ in range(20):            # a long quiet spell
            interval = next_idle_sleep(interval)
        self.assertEqual(10.0, interval)

        interval = IDLE_SLEEP_SECONDS  # a job arrives
        self.assertEqual(IDLE_SLEEP_SECONDS, interval)

    def test_the_ceiling_stays_inside_the_reap_timer(self) -> None:
        """Reaping runs on a timer the loop can only honour when it wakes up.

        `reap_stale` returns jobs abandoned by a dead worker, so a poll interval at or
        above `REAP_EVERY_SECONDS` would let that slip by a whole cycle.
        """

        from travel_planner.worker import MAX_IDLE_SLEEP_SECONDS, REAP_EVERY_SECONDS

        self.assertLess(MAX_IDLE_SLEEP_SECONDS, REAP_EVERY_SECONDS)


class ProgressReportingTest(unittest.TestCase):
    """A queued wait can only be described if the worker writes down where it is.

    `/places` is one `discover_places` job, so the screen holds a job id and a poll
    and nothing else -- which is why it showed a rotating line for 30-90 seconds
    while `/optimize`, which drives its own four calls, could show stages. The
    stages are honest here only because the number below moves when a call returns.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteStore(Path(self.directory.name) / "jobs.sqlite3")
        self.queue = JobQueue(self.store)

    def test_a_reporting_operation_is_handed_a_sink_and_its_counts_are_stored(self) -> None:
        stored: list[int | None] = []

        class FakeActions:
            def discover_places(self, *, trip_id, progress=None):  # noqa: ARG002
                # What the worker already wrote before calling in: a claimed job
                # reads 0, and that is the whole difference between "queued, and
                # nothing is running this" and "a worker has it". The screen draws
                # a stage list for the second and a rotating line for the first.
                stored.append(queue.get(job_id)["progress"])
                # Then what the provider does: geocode, two blocks, the catalogue.
                for reached in (1, 2, 3, 4):
                    progress(reached)
                    stored.append(queue.get(job_id)["progress"])
                return {"ok": True}

        queue = self.queue
        job_id = queue.enqueue("discover_places", "T1")
        # Nothing at all while it waits for a worker.
        self.assertIsNone(queue.get(job_id)["progress"])
        run_one(queue, FakeActions(), "worker-a")
        self.assertEqual(stored, [0, 1, 2, 3, 4])
        self.assertEqual(queue.get(job_id)["progress"], 4)

    def test_an_operation_with_no_milestones_is_not_handed_one(self) -> None:
        """An ignored `progress` argument on the other three would be three lies."""

        class FakeActions:
            def recommend_areas(self, *, trip_id):  # noqa: ARG002
                return {"ok": True}

        self.assertNotIn("recommend_areas", REPORTS_PROGRESS)
        job_id = self.queue.enqueue("recommend_areas", "T1")
        job = run_one(self.queue, FakeActions(), "worker-a")
        self.assertEqual(job["status"], DONE)
        self.assertIsNone(self.queue.get(job_id)["progress"])

    def test_a_retry_starts_its_stage_list_over(self) -> None:
        """Stages left at 3 describe work the next attempt has not done."""
        job_id = self.queue.enqueue("discover_places", "T1", max_attempts=2)
        self.queue.claim("w")
        self.queue.report_progress(job_id, 3)
        self.assertEqual(self.queue.fail(job_id, "overpass 504"), QUEUED)
        self.assertIsNone(self.queue.get(job_id)["progress"])

    def test_a_reaped_job_starts_its_stage_list_over(self) -> None:
        job_id = self.queue.enqueue("discover_places", "T1")
        self.queue.claim("w")
        self.queue.report_progress(job_id, 2)
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE jobs SET claimed_at = ? WHERE id = ?", ("2000-01-01T00:00:00+00:00", job_id)
            )
        self.assertEqual(self.queue.reap_stale(), 1)
        self.assertIsNone(self.queue.get(job_id)["progress"])


class QueuePredatingProgressTest(unittest.TestCase):
    """A queue built before `progress` existed must gain the column, not fail on it.

    The table check that keeps a serverless cold start cheap is exactly what would
    have hidden this: an older `jobs` table passes "does the table exist" and then
    fails every write to a column it has never had.
    """

    def test_an_older_jobs_table_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(str(Path(directory) / "jobs.sqlite3"))
            with store.connect() as connection:
                connection.execute(
                    "CREATE TABLE jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL,"
                    " trip_id TEXT NOT NULL, payload_json TEXT NOT NULL,"
                    " status TEXT NOT NULL, attempts INTEGER NOT NULL,"
                    " max_attempts INTEGER NOT NULL, claimed_by TEXT, claimed_at TEXT,"
                    " created_at TEXT NOT NULL, finished_at TEXT, result_json TEXT,"
                    " error TEXT)"
                )
            queue = JobQueue(store)
            job_id = queue.enqueue("discover_places", "T1")
            queue.report_progress(job_id, 2)
            self.assertEqual(queue.get(job_id)["progress"], 2)
