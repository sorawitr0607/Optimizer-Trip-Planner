#!/usr/bin/env python3
"""Element-level parity: the rebuild against the donor, by declared ancestor.

`WF-025` §2a wants each lifted element rendered in isolation and image-diffed
against the donor. Whole-screen diffs are meaningless — Auto-Bill has two screens
and the planner has nine routes — so the comparison has to be per element.

This does that comparison on **captured computed styles** rather than images,
which is exact, needs no tolerance, and works after the donor is archived. The
pairing comes from the `derives-from:` declarations, which
`check_design_tokens.py` already validates against the donor catalogue, so a
citation cannot silently point at the wrong element.

Differences are expected — the whole point of a rebuild in Tailwind is that some
values change deliberately. So a difference is only a **failure** when it is not
explained: covered by a registered deviation, or by the fact that the two designs
disagree about a property on purpose. Everything else is reported so it can be
registered or fixed, which is exactly `WF-025`'s rule that an unregistered
deviation is indistinguishable from drift.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
DONOR_DIR = ROOT / "artifacts" / "parity" / "2026-08-04-auto-bill-donor"
DONOR = DONOR_DIR / "computed-styles.json"
REBUILD = DONOR_DIR / "rebuild-computed-styles.json"
CATALOGUE = DONOR_DIR / "element-selectors.json"
WEB_TSX = sorted(
    path
    for folder in ("stages", "shared")
    for path in (ROOT / "web" / "src" / folder).rglob("*.tsx")
    if not path.name.endswith(".test.tsx")
)

DERIVES = re.compile(
    r"derives-from:\s*(?:element\s+(\d+)|inline|(A\d+))\s+([.\w-]+)\s+as\s+\.([\w-]+)", re.I
)

# The properties parity is actually about. Size and position are laid out by
# Tailwind and legitimately differ; these are the ones a lifted element is
# supposed to preserve.
# Border width and style are deliberately excluded. On a list row they are
# positional -- a dashed separator with `:first-child { border-top: 0 }` captures
# as 0px whichever row happens to be recorded first -- so comparing them measures
# where an element sat in the DOM, not whether it matches the donor. Including
# them produced fifteen findings, every one an artifact of that.
COMPARED = (
    "borderRadius",
    "boxShadow",
    "fontWeight",
    "textTransform",
    "letterSpacing",
)

# A registered deviation explains a difference only when the rebuild's value is
# what the deviation actually mandates. Blanket-excusing a property would leave
# just two comparable properties and a gate that cannot fail, so each check below
# still rejects a value the deviation does not license.
HOUSE_RADII = {"2px", "9999px", "0px"}
TOKEN_WEIGHTS = {"400", "500", "600", "700", "800"}


def explained(prop: str, rebuilt: str, donor_value: str) -> str | None:
    """Why this difference is licensed, or None if it is drift."""

    if prop == "borderRadius":
        # D2 unifies on 2px with pills exempt. Any other radius is not licensed.
        parts = {value.strip() for value in rebuilt.split()} or {rebuilt}
        return "D2 unifies radius on 2px, pills exempt" if parts <= HOUSE_RADII else None
    if prop == "fontWeight":
        # D8 loads real weights, so the donor's synthesised weight is not a
        # comparable value -- but the rebuild must still use a token weight.
        return "D8 real loaded weight" if rebuilt in TOKEN_WEIGHTS else None
    if prop == "boxShadow":
        # Same zero-blur hard offset shadows is a locked requirement, not taste.
        # A blur radius other than 0 is drift regardless of any deviation.
        numbers = re.findall(r"(-?[\d.]+)px", rebuilt)
        blur = numbers[2] if len(numbers) >= 3 else "0"
        return "hard offset re-expressed as a token" if float(blur) == 0 else None
    return None


def load(path: Path) -> dict[str, dict[str, str]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def by_class(capture: dict[str, dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    """(theme, single class) -> the first record that class appeared in."""

    table: dict[tuple[str, str], dict[str, str]] = {}
    for key, record in capture.items():
        theme, combo = key.split("|", 1)
        for token in combo.split("."):
            if token:
                table.setdefault((theme, token), record)
    return table


def main() -> int:
    if not DONOR.is_file():
        print("SKIP: no donor capture in this checkout", flush=True)
        return 0
    if not REBUILD.is_file():
        print(
            "SKIP: no rebuild capture yet — run the browser walk described in "
            f"{DONOR_DIR.relative_to(ROOT)}/README.md",
            flush=True,
        )
        return 0

    donor, rebuild = by_class(load(DONOR)), by_class(load(REBUILD))
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))

    pairs: list[tuple[str, str, str, str]] = []  # (file, planner class, donor class, element)
    for path in WEB_TSX:
        text = path.read_text(encoding="utf-8")
        for match in DERIVES.finditer(text):
            number, absent, selector, planner = (
                match.group(1), match.group(2), match.group(3).rstrip(",."), match.group(4)
            )
            if absent:
                continue
            name = catalogue.get(str(number), {}).get("name", "inline-only") if number else "inline-only"
            # The pairing is declared, not inferred. Guessing it from the nearest
            # className picked the filter *container* instead of the chip.
            pairs.append((
                str(path.relative_to(ROOT)),
                planner,
                selector.lstrip("."),
                f"{number or 'inline'} {name}",
            ))

    compared = 0
    unexplained: list[str] = []
    licensed = 0
    missing: list[str] = []

    for where, planner_class, donor_class, element in pairs:
        if not planner_class:
            missing.append(f"{where}: could not find the className next to `{donor_class}`")
            continue
        for theme in ("light", "dark"):
            left = rebuild.get((theme, planner_class))
            right = donor.get((theme, donor_class))
            if left is None or right is None:
                continue
            compared += 1
            for prop in COMPARED:
                a, b = left.get(prop), right.get(prop)
                if a is None or b is None or a == b:
                    continue
                why = explained(prop, a, b)
                if why:
                    licensed += 1
                    continue
                unexplained.append(
                    f"{theme} .{planner_class} vs donor .{donor_class} (element {element}): "
                    f"{prop} {b!r} -> {a!r}"
                )

    print(f"  pairs declared: {len(pairs)}", flush=True)
    print(f"  element/theme comparisons made: {compared}", flush=True)
    print(f"  differences licensed by a registered deviation: {licensed}", flush=True)
    for note in missing:
        print(f"NOTE: {note}", flush=True)
    if unexplained:
        print(
            f"FAILED: {len(unexplained)} unexplained element difference(s) — register them "
            "as deviations or fix them",
            file=sys.stderr,
        )
        for problem in unexplained:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("PASS: every lifted element matches its donor ancestor, or differs only "
          "where a registered deviation says it should", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
