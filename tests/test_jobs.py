"""The job queue's guarantees, tested rather than asserted.

The one that matters is the claim: two workers must never run the same job. The
Postgres path gets that from `FOR UPDATE SKIP LOCKED`; these run on SQLite, so
they prove the ordinary properties and the concurrency test is run separately
against a real Postgres.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from travel_planner.jobs import DONE, FAILED, QUEUED, RUNNING, JobQueue
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
