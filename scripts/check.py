#!/usr/bin/env python3
"""Run every free pre-commit gate with one exit code."""

from __future__ import annotations

from pathlib import Path
# No stage of this gate may touch a hosted database. `open_store` selects Postgres
# from `TOURIST_DB_URL` and ignores the path it was handed, so a shell that
# happens to export it silently redirects every stage that builds a store. That is
# not hypothetical: it put a "Coverage probe" trip into the owner's hosted database
# on the run that found this. The suite has the same guard in `tests/__init__.py`;
# this covers the stages that are plain scripts and never import that package.
import os as _os

_os.environ.pop("TOURIST_DB_URL", None)

import errno
import os
import subprocess
import sys
from contextlib import contextmanager
from time import monotonic


ROOT = Path(__file__).resolve().parents[1]

#: One run at a time, because two of them corrupt each other's answer.
#:
#: The stages are not independent of the working tree: the screen-baseline stage compares
#: `screen-current` against the approved set, and the capture that fills `screen-current`
#: is shared state on disk. Two runs interleaving there produced `approved: 2 · compared:
#: 1` and a stage that failed exactly like real drift — on unchanged code, which is the
#: one failure mode this suite cannot afford, since a gate that cries wolf is a gate
#: everyone learns to re-run rather than read.
#:
#: The tool that runs these commands issues parallel Bash calls in one shell, so this is
#: reachable by accident rather than by anyone deciding to do it. Refuse rather than
#: queue: a second run is nearly always a mistake, and waiting silently for ninety
#: seconds looks exactly like a hang.
LOCK = ROOT / ".check.lock"


@contextmanager
def only_one_run():
    """Hold `LOCK`, or explain who has it and refuse.

    `O_EXCL` rather than a check-then-create, which has the same race it is guarding
    against. A stale lock after a crash is removed by hand and says so — automatic
    staleness detection needs a liveness check this does not deserve.
    """

    try:
        handle = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError as error:
        if error.errno != errno.EEXIST:
            raise
        held = ""
        try:
            held = LOCK.read_text().strip()
        except OSError:
            pass
        print(
            f"FAILED: another check.py is running{f' (pid {held})' if held else ''}."
            f" Wait for it, or remove {LOCK.name} if it crashed.",
            file=sys.stderr,
        )
        yield False
        return
    try:
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        yield True
    finally:
        LOCK.unlink(missing_ok=True)


def main() -> int:
    python = sys.executable
    stages = [
        # First on purpose. Hosted egress can disable the entire deployment, and these
        # focused tests finish in under a second: fail before spending time elsewhere.
        (
            "Hosted egress boundaries",
            [python, "-m", "unittest", "tests.test_discovery_egress"],
        ),
        ("Python unit tests", [python, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]),
        ("Historic optimizer regressions", [python, "scripts/run_optimizer_regressions.py"]),
        ("Regression fixture structure", [python, "scripts/validate_regression_fixtures.py"]),
        ("Project graph integrity", [python, "scripts/build_project_graph.py", "--check"]),
        ("Provider redaction self-test", [python, "scripts/check_provider_access.py", "--self-test"]),
        ("Design token gate", [python, "scripts/check_design_tokens.py"]),
        ("Element parity", [python, "scripts/check_element_parity.py"]),
        # Comparison only. Capturing needs a running server and headless Chrome,
        # so it is not a gate step; this stage skips cleanly when there is
        # nothing captured, and fails when a capture drifted.
        ("Screen baselines", [python, "scripts/check_screen_baselines.py"]),
        # Reads the four hand-made reference workbooks: free, offline, and the
        # only gate that validates the merge against real trips rather than
        # against fixtures.
        ("Reference workbook coverage", [python, "scripts/check_reference_coverage.py"]),
    ]
    if (ROOT / "web" / "package.json").is_file():
        stages.extend(
            (label, ["npm", "--prefix", "web", "run", command])
            for label, command in (
                ("Web typecheck", "typecheck"),
                ("Web lint", "lint"),
                ("Web unit tests", "test"),
            )
        )

    started = monotonic()
    skipped: list[str] = []
    for number, (label, command) in enumerate(stages, 1):
        stage_started = monotonic()
        print(f"[{number}/{len(stages)}] {label}", flush=True)
        try:
            result = subprocess.run(command, cwd=ROOT, check=False)
        except FileNotFoundError as error:
            print(f"FAILED: {error}", file=sys.stderr)
            return 1
        # 2 is a stage reporting that it could not run — currently only the screen
        # baselines, which need a captured set to compare against. It is not a failure
        # and must not be a `PASS`: a gate that compared nothing claiming to have passed
        # is how two mobile layout defects shipped under a green suite.
        if result.returncode == 2:
            skipped.append(label)
            print(f"DID NOT RUN: {label} ({monotonic() - stage_started:.1f}s)", flush=True)
            continue
        if result.returncode:
            print(f"FAILED: {label} ({result.returncode})", file=sys.stderr)
            return result.returncode
        print(f"PASS: {label} ({monotonic() - stage_started:.1f}s)", flush=True)

    ran = len(stages) - len(skipped)
    print(f"{ran} of {len(stages)} stages passed in {monotonic() - started:.1f}s.")
    for label in skipped:
        print(f"  DID NOT RUN: {label}")
    return 0


if __name__ == "__main__":
    with only_one_run() as held:
        raise SystemExit(main() if held else 1)
