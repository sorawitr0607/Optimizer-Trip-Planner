"""The process that actually does the long work.

    uv run python -m travel_planner.worker

A serverless request cannot run a 52-second optimize or 90 seconds of Overpass,
so on a hosted deployment the request enqueues and this drains the queue. It is
an ordinary long-lived process and wants a host that offers one — a container, a
small VM, a background worker — not a function platform.

Nothing here is needed locally. The desktop app blocks for 52 seconds and always
has; `actions.py` is untouched by any of this.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .actions import PlannerActions
from .credentials import load_local_credentials
from .jobs import JobQueue, run_one

#: How soon after finishing a job the queue is asked again. Every poll is one round
#: trip, and this is the responsive end: a job queued while the worker is busy or
#: recently busy is picked up within two seconds.
IDLE_SLEEP_SECONDS = 2.0

#: Where the interval settles once nothing is arriving.
#:
#: A flat two seconds is 43,200 queries a day whether or not the app is being used, and
#: on a hosted deployment that is billed egress for asking an empty queue if it is still
#: empty. Supabase's free tier allows 5.5 GB and this trip's own reads had already passed
#: it. Backing off to ten seconds cuts an idle day to 8,640 polls -- about 80% less --
#: and costs nothing while the worker is working, because the interval resets the moment
#: a job appears.
#:
#: The trade is the one case it cannot avoid: the *first* job after a quiet spell waits
#: up to ten seconds to be noticed. Against discovery at 30-90s and a full proposal at
#: ~52s that is inside the noise, and it is the owner's decision rather than a default.
MAX_IDLE_SLEEP_SECONDS = 10.0

#: Reaping walks the running jobs, so it runs on a timer rather than every poll.
REAP_EVERY_SECONDS = 60.0


def next_idle_sleep(current: float) -> float:
    """The next wait after an empty poll: double it, up to the ceiling.

    Doubling rather than jumping straight to the ceiling, so a worker that has just
    finished something stays responsive -- 2s, 4s, 8s, then 10s, which is three empty
    polls and about fourteen seconds before it settles. A burst of jobs arriving one
    after another therefore never sees more than a two-second gap.
    """

    return min(MAX_IDLE_SLEEP_SECONDS, current * 2)


def serve_health(port: int, state: dict) -> None:
    """Answer any GET with the worker's state, from a daemon thread.

    A worker needs no HTTP surface, and locally it has none. This exists for one
    situation: a host whose free tier only runs *web services*, which requires
    something listening on `$PORT` or the deploy is judged to have failed. The
    queue is still drained by the loop below; this only proves the process is up,
    and gives a keep-alive ping somewhere to land on a host that idles a service
    out when nothing connects.
    """

    class Health(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - the runtime requires this name
            body = json.dumps(state, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            # A keep-alive ping every few minutes would otherwise be most of the log.
            pass

    ThreadingHTTPServer(("0.0.0.0", port), Health).serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drain the planner's job queue.")
    parser.add_argument("--database", default=os.environ.get("TOURIST_DB_PATH", "data/tourist.sqlite3"))
    parser.add_argument("--once", action="store_true",
                        help="run a single job if one is waiting, then exit")
    # Defaults to $PORT, which is how a host tells a web service where to listen.
    # Unset -- the normal case, including every local run -- means no HTTP at all.
    parser.add_argument("--health-port", type=int,
                        default=int(os.environ.get("PORT", "0") or 0),
                        help="also answer GET on this port, for hosts that only "
                             "keep a listening service alive (default: $PORT)")
    arguments = parser.parse_args(argv)

    # The same thing the local server does at startup, and the worker did not.
    #
    # This is the whole of the "route and travel time are not verified" report. The
    # worker runs the three slowest operations, and two of them call providers -- but
    # it was started with `TOURIST_DB_URL` alone, so `OPENROUTESERVICE_API_KEY` was
    # absent and every `refresh_routes` job raised "not configured". Every leg came
    # back unverified, every place was reconciled out on ROUTE_UNVERIFIED, and the
    # only visible offer was to accept a walking estimate -- for routes that were
    # never asked about.
    #
    # An already-set variable still wins, so an explicit `export` and a hosted
    # deployment's own environment are both untouched by this.
    loaded = load_local_credentials()
    if loaded:
        print(f"loaded {len(loaded)} credential(s) from secrets.local.json", flush=True)

    actions = PlannerActions(arguments.database)
    queue = JobQueue(actions.store)
    worker_id = f"{os.uname().nodename}:{os.getpid()}:{uuid.uuid4().hex[:6]}"

    # A worker killed mid-job leaves that job `running` for ever, so shutdown is
    # cooperative: finish the job in hand, then stop.
    stopping = False

    def request_stop(*_: object) -> None:
        nonlocal stopping
        stopping = True
        print("finishing the current job, then stopping", flush=True)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    state = {"worker": worker_id, "store": type(actions.store).__name__,
             "jobs_run": 0, "last": None, "status": "starting"}
    if arguments.health_port:
        threading.Thread(target=serve_health, args=(arguments.health_port, state),
                         daemon=True).start()
        print(f"health endpoint on :{arguments.health_port}", flush=True)

    print(f"worker {worker_id} draining {type(actions.store).__name__}", flush=True)
    state["status"] = "idle"
    last_reap = 0.0
    idle_sleep = IDLE_SLEEP_SECONDS
    while not stopping:
        # One transient drop — a pooled connection closed under us, a failover —
        # used to raise straight out of this loop and end the process with the
        # job still marked `running`. launchd restarts it, so the visible symptom
        # was a 30-second crash-loop and the job stranded `running` until a reap
        # up to STALE_AFTER_SECONDS later. The loop survives instead: the failure
        # is named in the log, the job stays where it is, and the next iteration
        # retries after the idle backoff. Recording the failure stays inside
        # `run_one`; if `fail` itself cannot reach the database there is nowhere
        # to record it, and the reap is the honest recovery.
        try:
            now = time.monotonic()
            if now - last_reap > REAP_EVERY_SECONDS:
                recovered = queue.reap_stale()
                if recovered:
                    print(f"returned {recovered} abandoned job(s) to the queue", flush=True)
                last_reap = now

            started = time.monotonic()
            job = run_one(queue, actions, worker_id)
        except Exception as error:  # noqa: BLE001 - the queue outlives one bad poll
            print(f"worker loop error: {type(error).__name__}: {error}", flush=True)
            if arguments.once:
                return 1
            time.sleep(idle_sleep)
            idle_sleep = next_idle_sleep(idle_sleep)
            continue
        if job is None:
            if arguments.once:
                print("nothing queued", flush=True)
                return 0
            time.sleep(idle_sleep)
            idle_sleep = next_idle_sleep(idle_sleep)
            continue
        # Work arrived, so stop backing off: the next poll is the responsive one again.
        idle_sleep = IDLE_SLEEP_SECONDS

        seconds = time.monotonic() - started
        state["jobs_run"] += 1
        state["last"] = {"kind": job["kind"], "status": job["status"],
                         "seconds": round(seconds, 1)}
        print(f"{job['kind']} {job['id']} -> {job['status']} in {seconds:.1f}s"
              + (f" ({job['error']})" if job.get("error") else ""), flush=True)
        if arguments.once:
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
