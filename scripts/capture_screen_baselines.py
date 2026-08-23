#!/usr/bin/env python3
"""Capture the screen images: ten routes at three viewports.

`WF-025` §2b wants 4 baselines per route, approved once and then diffed on every
change. It catches drift over time; it does **not** prove parity with Auto-Bill
and must not be described as if it does.

**A second viewport landed on 2026-08-10, and the reason is that the first one
was hiding things.** The gate only ever photographed 1440x900, so every
responsive rule in the stylesheet was unguarded — and a UX audit then found a
real regression living in exactly that gap: at 390px the mobile grid dropped the
column "Open in Maps" sat in, and the link rendered 10px wide on every stop of
every day. Nothing failed, because nothing was looking.

The phone set began as four screens and is now every stage route, because the
bottom tab bar and the 44px touch floor apply to all of them and seven had no
image at all. `t900-` is the third viewport: 500 and 1440 leave everything between
them untested, which made consolidating this stylesheet's breakpoints a change no
gate could have caught going wrong. The tour is the one overlay a desktop capture
can never show, so it is asked for explicitly.

Driven through headless Chrome rather than the interactive browser, because the
images should land on disk and never pass through a conversation. Baselines are
captured on **one fixed machine** by decision: cross-platform font rendering is
what makes these gates flaky, and a flaky gate gets switched off.

    # The owner token the trip is keyed to, which the capture must present or it
    # photographs "Trip not found" on every stage route:
    OWNER=$(sqlite3 data/tourist.sqlite3 \
      "select owner_token from trips where id = '<id>'")

    # Approve the current appearance as the baseline set:
    uv run --locked python scripts/capture_screen_baselines.py \
      --trip <id> --owner "$OWNER" --approve

    # Capture again later and compare:
    uv run --locked python scripts/capture_screen_baselines.py --trip <id> --owner "$OWNER"
    uv run --locked python scripts/check_screen_baselines.py

Check the images before trusting a pass. A set where every stage route rendered the
same recovery screen compares clean against another such set, which is how these
baselines sat green while covering nothing.

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
from typing import NamedTuple
import urllib.error
from urllib.parse import quote
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
BASELINES = ROOT / "artifacts" / "parity" / "screen-baselines"
CURRENT = ROOT / "artifacts" / "parity" / "screen-current"
# All ten stage routes. `stay` was missing, so `/stay` — a route since 2026-08-14 —
# had no image at any viewport; the desktop set had photographed nine of ten since
# the day the tenth was added.
ROUTES = (
    "setup", "places", "stay", "evidence", "optimize", "itinerary",
    "readiness", "costs", "split", "revise",
)
# `/places` is the one route whose content arrives after the first paint, so it is the
# one that needs a longer virtual-time budget. Both directions of 15000 were measured:
# at 5000 the deck still reads "Looking it up on the map…", and a loading placeholder is
# *stable*, so `stable_capture`'s two-identical-shots rule accepts it — one run caught the
# placeholder, the next caught the card, and the gate called it 2.9% drift on unchanged
# code. At 30000 virtual time outruns the real network, a request aborts, and a "Failed to
# fetch" banner shifts the page 29px for 12% drift. Bigger is not safer.
PLACES_BUDGET = 15_000

THEMES = ("light", "dark")
LANGUAGES = ("en", "th")


class Screen(NamedTuple):
    """One photographable state: a file-name stem and the path that reaches it."""

    name: str
    path: str
    query: str = ""
    #: Virtual-time budget in ms. 5000 settles every screen whose content is already
    #: in the first response; `/places` is the exception and pays for itself below.
    #: Raising this globally tripled a 128-image run to over an hour, so it is per
    #: screen rather than a flag on the whole capture.
    budget: int = 5000


class View(NamedTuple):
    """One viewport and everything photographed at it."""

    prefix: str
    size: tuple[int, int]
    screens: tuple[Screen, ...]


def _stage(route: str) -> "Screen":
    """One stage route, with the longer budget where the screen needs it."""

    return Screen(
        route,
        f"/trips/{{trip}}/{route}",
        budget=PLACES_BUDGET if route == "places" else 5000,
    )


# The desktop set keeps its file names exactly, so the 36 approved images stay
# approved. The phone set is prefixed, so both live in one directory and
# `check_screen_baselines.py` picks them up by glob without knowing about either.
VIEWS = (
    View("", (1440, 900), tuple(_stage(route) for route in ROUTES)),
    # 500 and not 390, and the number is not a preference. Headless Chrome on macOS
    # clamps its window — and with it the layout viewport — to a 500px minimum:
    # `--window-size=320,844` and `--window-size=450,844` both measure 500. A capture
    # named 390 would be a 500px image with a false label, and the next person to
    # "correct" it would get the same 500 back. Every `max-width: 768px` rule is still
    # exercised, which is what this set is for. A true 320-390px reflow check needs
    # device emulation over the DevTools protocol and stays a manual step.
    View(
        "m500-",
        (500, 844),
        (
            # The landing page is not a stage route and has no trip in its path. It
            # is also the screen a first-time owner meets on a phone, so leaving it
            # out would have left the widest surface in the app unguarded.
            Screen("landing", "/trips"),
            # Every stage route, not the four this set began with. The bottom tab bar
            # and the 44px touch floor apply to all of them, and seven had no phone
            # image at all — `stay`, `evidence`, `optimize`, `readiness`, `costs`,
            # `split` and `revise` — so the viewport most of this app's phone-specific
            # CSS is written for was guarded on a third of its screens.
            *(_stage(route) for route in ROUTES),
            # The one state a normal capture suppresses. A fresh profile is always a
            # first visit, so the tour is hidden under `data-capture` or every image
            # would photograph it; this asks for it back, on one screen, on purpose.
            Screen("tour", "/trips/{trip}/places", "baseline_tour=open", PLACES_BUDGET),
        ),
    ),
    # The middle, which nothing covered. 500 and 1440 leave every rule between them
    # untested — and this stylesheet had twelve distinct width breakpoints scattered
    # from 500 to 1100, so "consolidate the breakpoints" was a change no gate could
    # have caught going wrong. 900 sits above the 860 phone cut and below the 1100
    # wide-desktop one, which is exactly the band the old 768/900/992 rules disagreed
    # about.
    View("t900-", (900, 900), tuple(_stage(route) for route in ROUTES)),
)
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
)

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


def stable_capture(
    binary: str,
    url: str,
    out: Path,
    size: tuple[int, int],
    profile: str,
    attempts: int = 4,
    budget: int = 5000,
) -> bool:
    """Accept a screenshot only once two consecutive shots are identical.

    File-size stability is not visual stability: a screen caught mid-load or
    mid-transition writes a complete, correctly-sized PNG of the wrong moment.
    Comparing two shots of the same URL is the only check that actually tests
    "has this settled", and it caught both races that failed the first run --
    the theme fade and a partially-loaded board.
    """

    previous: bytes | None = None
    for _ in range(attempts):
        if not capture(binary, url, out, size, profile, budget):
            continue
        current = out.read_bytes()
        if previous is not None and current == previous:
            return True
        previous = current
    # Two identical shots never arrived; keep the last one and say so.
    return out.is_file() and out.stat().st_size > 0


def capture(binary: str, url: str, out: Path, size: tuple[int, int], profile: str,
            budget: int = 5000) -> bool:
    """True when a non-empty PNG landed, regardless of how Chrome exited.

    Two macOS headless quirks are handled here rather than worked around by the
    caller. Chrome writes the screenshot and then does **not** exit, so the return
    code is not a usable signal -- every capture would look like a failure. And
    waiting out a fixed timeout for every image would take a quarter of an hour, so this
    polls for the file to appear and settle, then stops the process.
    """

    out.unlink(missing_ok=True)
    process = subprocess.Popen(
        [
            binary,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--window-size={size[0]},{size[1]}",
            f"--user-data-dir={profile}",
            f"--virtual-time-budget={budget}",
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
        written = out.stat().st_size if out.is_file() else 0
        # Two consecutive identical non-zero sizes means the write finished.
        settled = settled + 1 if written and written == last else 0
        last = written
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
    # Without this the capture owns no trips and photographs the unknown-trip
    # recovery screen on every stage route -- see the note in `web/src/main.tsx`.
    # Required, because the failure it prevents is silent: the images come out,
    # the gate compares them happily, and every one is the same error page.
    parser.add_argument(
        "--owner",
        required=True,
        help="owner token the trip is keyed to (trips.owner_token)",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="write straight into the baseline set instead of the comparison set",
    )
    args = parser.parse_args()

    if not alive(args.base):
        raise SystemExit(f"FAILED: nothing serving at {args.base} — start `python -m localserver` first")

    target = BASELINES if args.approve else CURRENT
    target.mkdir(parents=True, exist_ok=True)
    binary = chrome()
    written, failed = 0, []

    expected = sum(len(view.screens) * len(THEMES) * len(LANGUAGES) for view in VIEWS)
    # One isolated profile for the run: the app's owner token lives in localStorage.
    # A fresh profile per image made the first one claim the trip and all 55 later ones
    # photograph "Trip not found" under a different token.
    with tempfile.TemporaryDirectory() as profile:
        for view in VIEWS:
            for screen in view.screens:
                for theme in THEMES:
                    for language in LANGUAGES:
                        name = f"{view.prefix}{screen.name}-{theme}-{language}.png"
                        # The app reads theme and language from the query string, so a
                        # headless load can reach any combination without clicking
                        # through a UI it would then be photographing mid-click.
                        query = (
                            f"baseline_theme={theme}&baseline_language={language}"
                            f"&baseline_owner={quote(args.owner)}"
                        )
                        if screen.query:
                            query = f"{query}&{screen.query}"
                        url = f"{args.base}{screen.path.format(trip=args.trip)}?{query}"
                        if stable_capture(
                            binary, url, target / name, view.size, profile,
                            budget=screen.budget,
                        ):
                            written += 1
                        else:
                            failed.append(name)
                            print(f"  unsettled: {name}", file=sys.stderr, flush=True)

    manifest = target / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "views": [
                    {
                        "prefix": view.prefix,
                        "viewport": list(view.size),
                        "screens": [screen.name for screen in view.screens],
                    }
                    for view in VIEWS
                ],
                "themes": list(THEMES),
                "languages": list(LANGUAGES),
                "expected": expected,
                "written": written,
                "failed": failed,
                "note": (
                    "Captured on one fixed machine at fixed viewports. Cross-platform "
                    "font rendering is what makes these gates flaky, so a capture from "
                    "another machine is not comparable."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{'approved' if args.approve else 'captured'} {written}/{expected} "
        f"into {target.relative_to(ROOT)}"
    )
    if failed:
        print(f"FAILED to capture: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
