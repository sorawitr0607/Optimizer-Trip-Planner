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
import os
import signal
import sys
import time
import uuid

from .actions import PlannerActions
from .jobs import JobQueue, run_one

#: Long enough that an idle worker is not hammering the database, short enough
#: that a queued job is not left sitting. Every poll is one round trip.
IDLE_SLEEP_SECONDS = 2.0

#: Reaping walks the running jobs, so it runs on a timer rather than every poll.
REAP_EVERY_SECONDS = 60.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drain the planner's job queue.")
    parser.add_argument("--database", default=os.environ.get("TOURIST_DB_PATH", "data/tourist.sqlite3"))
    parser.add_argument("--once", action="store_true",
                        help="run a single job if one is waiting, then exit")
    arguments = parser.parse_args(argv)

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

    print(f"worker {worker_id} draining {type(actions.store).__name__}", flush=True)
    last_reap = 0.0
    while not stopping:
        now = time.monotonic()
        if now - last_reap > REAP_EVERY_SECONDS:
            recovered = queue.reap_stale()
            if recovered:
                print(f"returned {recovered} abandoned job(s) to the queue", flush=True)
            last_reap = now

        started = time.monotonic()
        job = run_one(queue, actions, worker_id)
        if job is None:
            if arguments.once:
                print("nothing queued", flush=True)
                return 0
            time.sleep(IDLE_SLEEP_SECONDS)
            continue

        seconds = time.monotonic() - started
        print(f"{job['kind']} {job['id']} -> {job['status']} in {seconds:.1f}s"
              + (f" ({job['error']})" if job.get("error") else ""), flush=True)
        if arguments.once:
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
