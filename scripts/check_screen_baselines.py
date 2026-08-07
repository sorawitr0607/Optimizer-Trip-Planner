#!/usr/bin/env python3
"""Compare the current screen captures against the approved baselines.

`WF-025` §2b: 4 baselines per route, light/dark x en/th, approved once and then
diffed on every change. This catches **drift over time**. It does not prove parity
with Auto-Bill and is not described as if it does.

The tolerance is the one agreed with the owner on 2026-08-04, and it is two
conditions rather than one:

    fail when  more than 0.1% of pixels differ  AND  a differing pixel is off
               by more than 8/255 on any channel

Both must hold. A handful of antialiasing pixels never fails a build, and a real
layout shift always does. Zero tolerance was rejected because it would be flaky
regardless of care, and artifact 025 records the consequence: a flaky gate gets
switched off.

Skips cleanly when there is nothing to compare, so it is safe as a `check.py`
stage on a machine that has never captured anything.

**It refuses a capture older than the code it claims to have photographed.**
Capturing is manual — it needs a running server and headless Chrome — so this stage
compares whatever was last written to `screen-current`. Three times on 2026-08-07 that
was an image taken before the frontend changed, and the stage printed PASS having
compared nothing relevant. A green gate that tested nothing is worse than a red one,
so a stale capture now fails and names the command that fixes it.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BASELINES = ROOT / "artifacts" / "parity" / "screen-baselines"
CURRENT = ROOT / "artifacts" / "parity" / "screen-current"

# Agreed 2026-08-04. Both conditions must hold for a failure.
MAX_DIFFERING_FRACTION = 0.001  # 0.1% of pixels
MIN_CHANNEL_DELTA = 8  # out of 255


SOURCE = ROOT / "web" / "src"
SOURCE_SUFFIXES = (".tsx", ".ts", ".css")


def stale_sources() -> list[str]:
    """Frontend files modified after the oldest current capture.

    Compared against the **oldest** capture, not the newest: the 36 images are written
    over about a minute, and an edit landing mid-run would otherwise be judged against
    whichever screens happened to be photographed after it.
    """

    captures = list(CURRENT.glob("*.png"))
    if not captures or not SOURCE.is_dir():
        return []
    oldest = min(path.stat().st_mtime for path in captures)
    return sorted(
        str(path.relative_to(ROOT))
        for path in SOURCE.rglob("*")
        if path.suffix in SOURCE_SUFFIXES and path.stat().st_mtime > oldest
    )


def main() -> int:
    if not BASELINES.is_dir() or not any(BASELINES.glob("*.png")):
        print("SKIP: no approved baselines yet — run capture_screen_baselines.py --approve",
              flush=True)
        return 0
    if not CURRENT.is_dir() or not any(CURRENT.glob("*.png")):
        print("SKIP: no current captures to compare — run capture_screen_baselines.py", flush=True)
        return 0

    stale = stale_sources()
    if stale:
        print(
            f"FAILED: the capture predates {len(stale)} frontend file(s), so this compares "
            "images that do not show the current code",
            file=sys.stderr,
        )
        for name in stale[:5]:
            print(f"  - {name}", file=sys.stderr)
        if len(stale) > 5:
            print(f"  - ...and {len(stale) - 5} more", file=sys.stderr)
        print(
            "  run: uv run --locked python scripts/capture_screen_baselines.py --trip <id>",
            file=sys.stderr,
        )
        return 1

    try:
        from PIL import Image, ImageChops
    except ModuleNotFoundError:
        print("FAILED: pillow is needed to read the baselines; it is in the dev group",
              file=sys.stderr)
        return 1

    approved = sorted(BASELINES.glob("*.png"))
    failures: list[str] = []
    notes: list[str] = []
    compared = 0

    for baseline in approved:
        current = CURRENT / baseline.name
        if not current.is_file():
            notes.append(f"{baseline.name} has no current capture")
            continue
        with Image.open(baseline) as left, Image.open(current) as right:
            if left.size != right.size:
                failures.append(
                    f"{baseline.name}: size changed {left.size} -> {right.size}; a different "
                    "viewport invalidates the baseline rather than failing it"
                )
                continue
            a, b = left.convert("RGB"), right.convert("RGB")
            compared += 1
            difference = ImageChops.difference(a, b)
            # The channel that moved most, so a big change confined to one
            # channel is not averaged away into nothing.
            worst = max(difference.split(), key=lambda band: band.getextrema()[1])
            peak = worst.getextrema()[1]
            if peak <= MIN_CHANNEL_DELTA:
                continue  # Every difference is within antialiasing range.
            mask = worst.point(lambda value: 255 if value > MIN_CHANNEL_DELTA else 0)
            differing = mask.histogram()[255]
            fraction = differing / (a.size[0] * a.size[1])
            if fraction > MAX_DIFFERING_FRACTION:
                failures.append(
                    f"{baseline.name}: {fraction * 100:.3f}% of pixels differ by more than "
                    f"{MIN_CHANNEL_DELTA}/255 (peak {peak}); above the agreed 0.1%"
                )

    orphans = [path.name for path in sorted(CURRENT.glob("*.png"))
               if not (BASELINES / path.name).is_file()]
    for orphan in orphans:
        notes.append(f"{orphan} is captured but not approved; re-run with --approve to accept it")

    print(f"  baselines approved: {len(approved)} · compared: {compared}", flush=True)
    for note in notes:
        print(f"NOTE: {note}", flush=True)
    if failures:
        print(f"FAILED: {len(failures)} screen(s) drifted beyond the agreed tolerance",
              file=sys.stderr)
        for problem in failures:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    manifest = BASELINES / "manifest.json"
    if manifest.is_file():
        expected = json.loads(manifest.read_text(encoding="utf-8")).get("expected")
        if expected and len(approved) < expected:
            print(f"NOTE: {len(approved)} of {expected} baselines approved", flush=True)
    print("PASS: every approved screen is within the agreed tolerance", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
