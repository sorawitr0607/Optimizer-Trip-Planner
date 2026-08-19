"""The RPC surface as a serverless function.

`api/__init__.py` is the local server: a long-lived `ThreadingHTTPServer` holding
one `PlannerActions`. A serverless platform gives neither, so this is the same
contract expressed for a platform that builds a process per request and destroys
it afterwards.

**Almost nothing is re-implemented.** `dispatch()` and the 91-method literal
allowlist come from `api/__init__.py` unchanged — a second copy of an allowlist is
how the two come to disagree about what may be called, and this one guards
`save_plan_version` and `record_paid_call`, which write immutable history and forge
ledger rows respectively.

Two things genuinely differ:

*Long work is enqueued, not run.* Discovery is 30-90s and a proposal ~52s, against
a function that is killed at 10s on Vercel's Hobby plan and 60s on Pro. Those three
methods return a job id and the client polls; `travel_planner/worker.py` does the
work somewhere that stays running.

*State comes from Postgres.* `PlannerActions` holds no session state — it assembles
snapshots, calls the core and persists — which is the property that makes
per-request construction viable at all. It needs `TOURIST_DB_URL`; without it a
function would build a SQLite file on an ephemeral disk and lose it.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from typing import Any

from urllib.parse import urlsplit

# `_download` is private to the package, and this is the package. Importing it
# beats a second copy of the export route regex.
from localserver import ACTIONS, _download, dispatch, error_response
from travel_planner.actions import PlannerActions
from travel_planner.jobs import HANDLERS, JobQueue

#: Enqueued rather than run. Exactly the operations the queue knows how to run,
#: derived from it rather than restated, so the two cannot drift.
DEFERRED = frozenset(HANDLERS)

#: Reused across invocations when the platform keeps the process warm, which it
#: usually does. A cold start pays one connection; a warm one pays none.
_actions: PlannerActions | None = None
_queue: JobQueue | None = None


def _planner() -> tuple[PlannerActions, JobQueue]:
    global _actions, _queue
    if _actions is None:
        if not os.environ.get("TOURIST_DB_URL", "").strip():
            # Failing loudly beats writing a trip to a disk that is about to be
            # discarded, which looks like success and loses the data.
            raise RuntimeError(
                "TOURIST_DB_URL is required: a serverless function has no durable disk"
            )
        _actions = PlannerActions(os.environ.get("TOURIST_DB_PATH", "unused-on-postgres"))
        _queue = JobQueue(_actions.store)
    assert _queue is not None
    return _actions, _queue


def _method(handler: BaseHTTPRequestHandler) -> str:
    """Which RPC this is, from the path, with the header as the fallback.

    The path is the source of truth and matches the local server exactly. The
    header exists because a platform rewrite points every `/api/*` at this one
    function, and if a platform ever forwards the *rewritten* path rather than the
    requested one, every call would arrive asking for the method named "rpc". The
    client sends both, so that failure is recoverable instead of total. A custom
    header is also not CORS-safelisted, so it carries the same cross-site property
    the Content-Type check relies on.
    """

    path = urlsplit(handler.path).path
    tail = path.rsplit("/", 1)[-1] if path.startswith("/api/") else ""
    if tail and tail not in ("rpc", "rpc.py"):
        return tail
    return handler.headers.get("X-Planner-Method", "").strip()


def handle(method: str, payload: dict[str, Any]) -> tuple[int, Any]:
    """Run or enqueue one call. Returns the status and the body."""
    actions, queue = _planner()

    if method == "job_status":
        job = queue.get(str(payload.get("job_id", "")))
        if job is None:
            return 404, {"code": "unknown_job"}
        return 200, {
            "job_id": job["id"], "status": job["status"], "kind": job["kind"],
            "attempts": job["attempts"], "error": job["error"],
            "result": json.loads(job["result_json"]) if job["result_json"] else None,
        }

    if method in DEFERRED:
        trip_id = payload.get("trip_id")
        if not isinstance(trip_id, str) or not trip_id:
            return 400, {"code": "trip_id_required"}
        rest = {k: v for k, v in payload.items() if k != "trip_id"}
        # Already queued or running for this trip returns that job rather than
        # buying the same 30-90s answer twice.
        return 202, {"job_id": queue.enqueue(method, trip_id, rest), "status": "queued"}

    if method not in ACTIONS:
        return 404, {"code": "unknown_action"}
    return 200, dispatch(actions, method, payload)


class handler(BaseHTTPRequestHandler):
    """Vercel's Python runtime entry point."""

    def _send(self, status: int, body: Any) -> None:
        encoded = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        # Nothing here is cacheable: every response is either trip state or a job.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802 - the runtime requires this name
        # SECURITY CONTROL, carried over from the local server: application/json
        # is not CORS-safelisted, so requiring it keeps a cross-site form from
        # reaching this. Do not relax it.
        if self.headers.get("Content-Type") != "application/json":
            self._send(415, {"code": "unsupported_media_type"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                self._send(400, {"code": "body_must_be_an_object"})
                return
            status, body = handle(_method(self), payload)
            self._send(status, body)
        except Exception as error:  # transport boundary
            # The same mapping the local server uses. Collapsing everything to 500
            # here once hid `paid_cap_reached` behind "internal_error".
            self._send(*error_response(error))

    def do_GET(self) -> None:  # noqa: N802 - the runtime requires this name
        """The three export downloads, which are links rather than RPC calls.

        `<a download href="/api/export/.../workbook.xlsx">` is an ordinary browser
        navigation: no JSON body, no custom header, and no way to add one. Without
        this method BaseHTTPRequestHandler answers 501 and all three downloads are
        dead on the hosted deployment while working locally.
        """

        try:
            actions, _ = _planner()
            body, content_type, filename = _download(actions, self.path)
        except Exception as error:  # transport boundary
            self._send(*error_response(error))
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
