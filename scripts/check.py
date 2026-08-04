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
    for number, (label, command) in enumerate(stages, 1):
        stage_started = monotonic()
        print(f"[{number}/{len(stages)}] {label}", flush=True)
        try:
            result = subprocess.run(command, cwd=ROOT, check=False)
        except FileNotFoundError as error:
            print(f"FAILED: {error}", file=sys.stderr)
            return 1
        if result.returncode:
            print(f"FAILED: {label} ({result.returncode})", file=sys.stderr)
            return result.returncode
        print(f"PASS: {label} ({monotonic() - stage_started:.1f}s)", flush=True)

    print(f"All {len(stages)} stages passed in {monotonic() - started:.1f}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
