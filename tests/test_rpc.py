"""The serverless entry point, driven over real HTTP.

`api/rpc.py` had no tests: it cannot run without `TOURIST_DB_URL`, and pointing
that at the hosted database is what wrote test rows into production twice. So the
store is SQLite and the module-level singletons are filled in directly, which is
the one thing `_planner()` exists to do.

Serving the class through `http.server` rather than calling its methods is
deliberate. Two of the three defects these tests cover -- `do_GET` missing
entirely, and every error collapsing to 500 -- are invisible when you call
`handle()` directly, because they live in the part `BaseHTTPRequestHandler`
drives rather than the part we wrote.
"""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from api import rpc
from travel_planner.actions import PlannerActions
from travel_planner.jobs import JobQueue


class RpcOverHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = TemporaryDirectory()
        actions = PlannerActions(str(Path(cls._directory.name) / "test.sqlite3"))
        rpc._actions, rpc._queue = actions, JobQueue(actions.store)
        cls.actions = actions
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), rpc.handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        rpc._actions = rpc._queue = None
        cls._directory.cleanup()

    def call(self, method, payload=None, *, headers=None, path=None):
        request = urllib.request.Request(
            f"{self.base}{path or f'/api/{method}'}",
            data=json.dumps(payload or {}).encode(),
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")

    def test_a_normal_call_runs_inline(self):
        status, body = self.call("list_trips")
        self.assertEqual(status, 200)
        self.assertIsInstance(body, list)

    def test_slow_work_is_queued_rather_than_run(self):
        _, trip = self.call("create_trip", {"name": "Q", "destination": "Kyoto"})
        status, body = self.call("discover_places", {"trip_id": trip["trip_id"]})
        self.assertEqual(status, 202)
        self.assertIn("job_id", body)
        # The client polls this; without it a 202 is a dead end.
        status, job = self.call("job_status", {"job_id": body["job_id"]})
        self.assertEqual(status, 200)
        self.assertEqual(job["status"], "queued")

    def test_unknown_job_is_404_not_500(self):
        status, body = self.call("job_status", {"job_id": "nope"})
        self.assertEqual(status, 404)
        self.assertEqual(body["code"], "unknown_job")

    def test_unknown_action_is_404(self):
        status, body = self.call("no_such_method")
        self.assertEqual(status, 404)
        self.assertEqual(body["code"], "unknown_action")

    def test_a_refusal_keeps_its_own_status_and_code(self):
        # Not 500, and not a bare 409 either: the code is what the screen reads.
        status, body = self.call("delete_trip", {"trip_id": "trip_missing"})
        self.assertNotEqual(status, 500)
        self.assertIsInstance(body.get("code"), str)
        self.assertNotEqual(body["code"], "internal_error")

    def test_non_json_content_type_is_refused(self):
        # CORS-safelisted content types must not reach this. Carried from the
        # local server, and the reason a cross-site form cannot call the planner.
        request = urllib.request.Request(
            f"{self.base}/api/list_trips", data=b"{}",
            headers={"Content-Type": "text/plain"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 415)

    def test_method_falls_back_to_the_header_when_the_path_is_rewritten(self):
        # What a platform rewrite of /api/* onto one function looks like if it
        # forwards the rewritten path. Without the header every call would ask
        # for the method "rpc".
        status, body = self.call(
            "list_trips", headers={"X-Planner-Method": "list_trips"}, path="/api/rpc")
        self.assertEqual(status, 200)
        self.assertIsInstance(body, list)

    def test_the_path_still_wins_when_it_names_a_method(self):
        status, _ = self.call(
            "list_trips", headers={"X-Planner-Method": "no_such_method"})
        self.assertEqual(status, 200)

    def test_exports_are_reachable_over_GET(self):
        # The regression: BaseHTTPRequestHandler answers 501 for an unimplemented
        # verb, so all three download links died on the hosted deployment while
        # working locally. Any answer but 501 means do_GET is wired.
        try:
            with urllib.request.urlopen(f"{self.base}/api/export/trip_x/workbook.xlsx") as r:
                status = r.status
        except urllib.error.HTTPError as error:
            status = error.code
        self.assertNotEqual(status, 501)

    def test_an_unknown_download_is_404(self):
        try:
            with urllib.request.urlopen(f"{self.base}/api/export/trip_x/nope.txt") as r:
                status, body = r.status, json.loads(r.read())
        except urllib.error.HTTPError as error:
            status, body = error.code, json.loads(error.read())
        self.assertEqual(status, 404)
        self.assertEqual(body["code"], "unknown_download")


if __name__ == "__main__":
    unittest.main()
