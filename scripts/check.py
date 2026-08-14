#!/usr/bin/env python3
"""Run every free pre-commit gate with one exit code."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from time import monotonic


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    python = sys.executable
    stages = [
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
    raise SystemExit(main())
