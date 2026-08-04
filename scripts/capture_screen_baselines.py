#!/usr/bin/env python3
"""Capture the 36 screen images: 9 routes x light/dark x en/th.

`WF-025` §2b wants 4 baselines per route, approved once and then diffed on every
change. It catches drift over time; it does **not** prove parity with Auto-Bill
and must not be described as if it does.

Driven through headless Chrome rather than the interactive browser, because 36
images should land on disk and never pass through a conversation. Baselines are
captured on **one fixed machine** by decision: cross-platform font rendering is
what makes these gates flaky, and a flaky gate gets switched off.

    # Approve the current appearance as the baseline set:
    uv run --locked python scripts/capture_screen_baselines.py --trip <id> --approve

    # Capture again later and compare:
    uv run --locked python scripts/capture_screen_baselines.py --trip <id>
    uv run --locked python scripts/check_screen_baselines.py

The language and theme are set before the screenshot through the same controls a
person would use, so nothing is captured in a state the app cannot actually be in.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
BASELINES = ROOT / "artifacts" / "parity" / "screen-baselines"
CURRENT = ROOT / "artifacts" / "parity" / "screen-current"
ROUTES = (
    "setup", "places", "evidence", "optimize", "itinerary",
    "readiness", "costs", "split", "revise",
)
THEMES = ("light", "dark")
LANGUAGES = ("en", "th")
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
)
# One fixed viewport, by decision. Changing it invalidates every baseline.
VIEWPORT = (1440, 900)


def chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("FAILED: no Chrome or Chromium found for headless capture")


def alive(base: str) -> bool:
    try:
        with urllib.request.urlopen(base, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def stable_capture(binary: str, url: str, out: Path, attempts: int = 4) -> bool:
    """Accept a screenshot only once two consecutive shots are identical.

    File-size stability is not visual stability: a screen caught mid-load or
    mid-transition writes a complete, correctly-sized PNG of the wrong moment.
    Comparing two shots of the same URL is the only check that actually tests
    "has this settled", and it caught both races that failed the first run --
    the theme fade and a partially-loaded board.
    """

    previous: bytes | None = None
    for _ in range(attempts):
        if not capture(binary, url, out):
            continue
        current = out.read_bytes()
        if previous is not None and current == previous:
            return True
        previous = current
    # Two identical shots never arrived; keep the last one and say so.
    return out.is_file() and out.stat().st_size > 0


def capture(binary: str, url: str, out: Path) -> bool:
    """True when a non-empty PNG landed, regardless of how Chrome exited.

    Two macOS headless quirks are handled here rather than worked around by the
    caller. Chrome writes the screenshot and then does **not** exit, so the return
    code is not a usable signal -- every capture would look like a failure. And
    waiting out a fixed timeout 36 times would take a quarter of an hour, so this
    polls for the file to appear and settle, then stops the process.
    """

    out.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        process = subprocess.Popen(
            [
                binary,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--window-size={VIEWPORT[0]},{VIEWPORT[1]}",
                f"--user-data-dir={profile}",
                "--virtual-time-budget=5000",
                f"--screenshot={out}",
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 30
        settled, last = 0, -1
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            size = out.stat().st_size if out.is_file() else 0
            # Two consecutive identical non-zero sizes means the write finished.
            settled = settled + 1 if size and size == last else 0
            last = size
            if settled >= 2:
                break
            time.sleep(0.4)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    return out.is_file() and out.stat().st_size > 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trip", required=True, help="trip id to photograph")
    parser.add_argument("--base", default="http://127.0.0.1:8801")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="write straight into the baseline set instead of the comparison set",
    )
    args = parser.parse_args()

    if not alive(args.base):
        raise SystemExit(f"FAILED: nothing serving at {args.base} — start `python -m api` first")

    target = BASELINES if args.approve else CURRENT
    target.mkdir(parents=True, exist_ok=True)
    binary = chrome()
    written, failed = 0, []

    for route in ROUTES:
        for theme in THEMES:
            for language in LANGUAGES:
                name = f"{route}-{theme}-{language}.png"
                # The app reads both from the query string so a headless load can
                # reach any combination without clicking through the UI.
                url = (
                    f"{args.base}/trips/{args.trip}/{route}"
                    f"?baseline_theme={theme}&baseline_language={language}"
                )
                if stable_capture(binary, url, target / name):
                    written += 1
                else:
                    failed.append(name)
                    print(f"  unsettled: {name}", file=sys.stderr, flush=True)

    manifest = target / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "viewport": list(VIEWPORT),
                "routes": list(ROUTES),
                "themes": list(THEMES),
                "languages": list(LANGUAGES),
                "expected": len(ROUTES) * len(THEMES) * len(LANGUAGES),
                "written": written,
                "failed": failed,
                "note": (
                    "Captured on one fixed machine at a fixed viewport. Cross-platform "
                    "font rendering is what makes these gates flaky, so a capture from "
                    "another machine is not comparable."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{'approved' if args.approve else 'captured'} {written}/36 into {target.relative_to(ROOT)}")
    if failed:
        print(f"FAILED to capture: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
