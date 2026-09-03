#!/usr/bin/env python3
"""The token half of the visual parity gate. Free, no browser, no network.

`WF-025` asks for four things this can check without a screenshot harness:

- **All 13 country accent triples resolve** (§2c). The accent is one custom
  property, so it can recolour a pixel but never move one; imaging it 13 times
  tests nothing an assertion cannot.
- **The token allowlist is clean** — the rebuild's stylesheets carry no raw
  colour literals. `tokens.css` is the single colour source and the only file
  allowed to hold them.
- **Every new element declares an ancestor.** An element with no Auto-Bill
  counterpart passes on token conformance plus a declared ancestor, so a
  `derives-from:` note is required rather than optional.
- **No bare `var(--x)` without a definition** (an undefined custom property
  silently falls back instead of erroring).

It also reports the contrast of every accent against both theme backgrounds,
because an accent chosen on a light background is not automatically legible on
`#121212` and nothing else in the gate would notice.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "tokens.css"
WEB_CSS = sorted((ROOT / "web" / "src").rglob("*.css"))
WEB_TSX = sorted(
    path
    for folder in ("stages", "shared")
    for path in (ROOT / "web" / "src" / folder).rglob("*.tsx")
)

# tokens.css owns every literal. Everything else must go through var().
COLOUR_LITERAL = re.compile(
    r"(?<![\w-])(#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\()"
)
# Tailwind's own at-rules and the theme block legitimately name colours.
ALLOWED_LITERAL_CONTEXT = re.compile(r"^\s*(/\*|\*|@import|@theme|@custom-variant)")

# A var() carrying a fallback never goes guaranteed-invalid: `var(--x, fallback)`
# resolves to the fallback when --x is undefined. Only the bare form is a silent
# no-op under a misspelt name, so only it is checked.
VAR_USE_BARE = re.compile(r"var\(\s*(--[\w-]+)\s*\)")
VAR_DEFINED = re.compile(r"(--[\w-]+)\s*:")
# A component may set a property at runtime through a style object
# (`style={{ "--map-zoom": view.zoom }}`), which no stylesheet declares.
TSX_SET_PROPERTY = re.compile(r"""["'](--[\w-]+)["']\s*:""")
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)

REQUIRED_TRIPLE = ("--color-accent", "--color-accent-hover", "--color-accent-light")


def declarations(body: str) -> dict[str, str]:
    return {
        name.strip(): value.strip()
        for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body)
    }


def country_blocks(text: str) -> dict[str, dict[str, str]]:
    """Every `:root[data-country="x"]` rule and the properties it sets."""

    found: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r':root\[data-country="([^"]+)"\]\s*\{([^}]*)\}', text, re.S
    ):
        found[match.group(1)] = declarations(match.group(2))
    return found


def dark_country_blocks(text: str) -> dict[str, dict[str, str]]:
    """The `:root.dark[data-country="x"]` half of each accent pair."""

    found: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r':root\.dark\[data-country="([^"]+)"\][^{]*\{([^}]*)\}', text, re.S
    ):
        found[match.group(1)] = declarations(match.group(2))
    return found


def theme_tokens(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """(light, dark). Every `:root` declaration, with the dark block over it."""

    light: dict[str, str] = {}
    for match in re.finditer(r"(?m)^:root\s*\{(.*?)^\}", text, re.S):
        light.update(declarations(match.group(1)))
    dark = dict(light)
    match = re.search(
        r'(?m)^:root\.dark,\s*\n:root\[data-theme="dark"\]\s*\{(.*?)^\}', text, re.S
    )
    if match:
        dark.update(declarations(match.group(1)))
    return light, dark


def channels(value: str) -> tuple[float, float, float] | None:
    value = value.strip()
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        if len(digits) < 6:
            return None
        return tuple(int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]
    numbers = re.findall(r"[\d.]+", value)
    if len(numbers) >= 3:
        return tuple(min(float(n), 255) / 255 for n in numbers[:3])  # type: ignore[return-value]
    return None


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(foreground: str, background: str) -> float | None:
    left, right = channels(foreground), channels(background)
    if not left or not right:
        return None
    a, b = relative_luminance(left), relative_luminance(right)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


# --------------------------------------------------------------------------
# Contrast, as a gate rather than a report.
#
# This used to print the accent's contrast against the two page backgrounds and
# fail only below 3:1, which is the floor for a large graphic — not for the words
# in a button. A UX audit on 2026-08-10 found what that left through: dark muted
# text at 3.74:1, dark error text at 4.30:1, four semantic colours illegible on
# their own tints, and six of the thirteen destination accents between 2.94:1 and
# 4.10:1 against the white text printed on them. Every one of those is normal
# body text, so the bar is 4.5:1 and it is checked here.
#
# Three things this knows that the old report did not.
#
# **The tint is the binding background.** A semantic colour is written on the
# page, on the recessed surface, on a card, and on its own `-light` tint — and the
# tint is the lightest of those in the dark theme, so it decides. Checking only
# the page background passed colours that were unreadable everywhere they were
# actually used.
#
# **The accent is both a fill and a link.** Contrast is symmetric, so an accent
# legible as text on the theme's lightest surface necessarily takes the opposite
# ink as a fill. One rule covers both roles, which is why there is no separate
# text-accent token.
#
# **A translucent value cannot be judged.** `rgb(... / 12%)` composites over
# whatever is behind it, so its contrast is unknowable from this file alone and it
# is skipped rather than measured wrongly against its own opaque channels.
# --------------------------------------------------------------------------

AA_NORMAL = 4.5
SURFACES = ("--bg-primary", "--bg-secondary", "--bg-card")
BODY_TEXT = ("--text-primary", "--text-secondary", "--text-muted")
SEMANTIC = ("--color-accent", "--color-success", "--color-danger", "--color-warning")


def opaque(value: str) -> bool:
    """False for anything carrying an alpha channel, which cannot be judged here."""

    if "/" in value or value.lower().startswith(("rgba", "hsla")):
        return False
    if value.startswith("#"):
        return len(value.lstrip("#")) in (3, 6)
    return channels(value) is not None


def check_pair(
    failures: list[str], theme: str, where: str, fg: str, fg_value: str, bg: str, bg_value: str
) -> None:
    if not (opaque(fg_value) and opaque(bg_value)):
        return
    ratio = contrast(fg_value, bg_value)
    if ratio is not None and ratio < AA_NORMAL:
        failures.append(
            f"{theme} {where}: {fg} {fg_value} on {bg} {bg_value} is {ratio:.2f}:1, "
            f"below the {AA_NORMAL}:1 AA floor for normal text"
        )


def check_contrast(text: str) -> list[str]:
    """Every foreground/background pair the stylesheet can actually produce."""

    failures: list[str] = []
    light, dark = theme_tokens(text)
    countries = country_blocks(text)
    dark_countries = dark_country_blocks(text)

    for theme, base, overrides in (
        ("light", light, countries),
        ("dark", dark, dark_countries),
    ):
        for name in BODY_TEXT + SEMANTIC:
            value = base.get(name)
            if not value:
                continue
            for surface in SURFACES:
                check_pair(failures, theme, "text", name, value, surface, base.get(surface, ""))
            tint = base.get(f"{name}-light")
            if tint:
                check_pair(failures, theme, "on its own tint", name, value, f"{name}-light", tint)

        # Every destination accent, in both of its roles.
        for country in sorted(countries):
            accent = overrides.get(country, {}).get("--color-accent")
            hover = overrides.get(country, {}).get("--color-accent-hover")
            if accent is None:
                failures.append(
                    f"{theme}: {country} has no --color-accent for this theme. An accent "
                    "chosen on one background is not legible on the other; write both halves"
                )
                continue
            ink = base.get("--color-on-accent", "")
            for surface in SURFACES:
                check_pair(
                    failures, theme, f"{country} accent as link text",
                    "--color-accent", accent, surface, base.get(surface, ""),
                )
            for role, fill in (("accent", accent), ("accent-hover", hover)):
                if fill:
                    check_pair(
                        failures, theme, f"{country} text on the {role} fill",
                        "--color-on-accent", ink, f"--color-{role}", fill,
                    )
    return failures


DONOR = ROOT / "artifacts" / "parity" / "2026-08-04-auto-bill-donor"
DERIVES = re.compile(
    r"derives-from:\s*(?:element\s+(\d+)|inline|(A\d+))\s+([.\w-]+)"
    r"(?:\s+as\s+\.([\w-]+))?",
    re.I,
)


def validate_ancestors() -> list[str]:
    """A declared ancestor has to be the *right* one.

    Requiring the note without checking it let eight wrong element numbers
    accumulate across S2-S6: the class names were real Auto-Bill classes but
    belonged to other catalogue entries, and one came from misreading "6 of the
    23 classes with no CSS rule" as "element 6". A parity harness keyed on those
    numbers would have diffed against the wrong donor element and called the
    result parity.
    """

    selectors = DONOR / "element-selectors.json"
    inline = DONOR / "inline-styles.json"
    if not selectors.is_file():
        return []  # No donor capture in this checkout; nothing to validate against.

    catalogue = json.loads(selectors.read_text(encoding="utf-8"))
    owner: dict[str, set[int]] = {}
    for number, entry in catalogue.items():
        for selector in entry["selectors"]:
            owner.setdefault(selector, set()).add(int(number))
    inline_classes: set[str] = set()
    if inline.is_file():
        for key in json.loads(inline.read_text(encoding="utf-8")):
            for token in key.split("|", 1)[-1].split("."):
                if token:
                    inline_classes.add("." + token)

    problems: list[str] = []
    for path in WEB_TSX:
        if path.name.endswith(".test.tsx"):
            continue
        for match in DERIVES.finditer(path.read_text(encoding="utf-8")):
            number, absent, selector, planner = (
                match.group(1), match.group(2), match.group(3).rstrip(",."), match.group(4)
            )
            where = path.relative_to(ROOT)
            if absent:
                continue  # An absent element has no donor counterpart to diff.
            if not planner:
                problems.append(
                    f"{where} declares {selector} without naming the planner class it pairs "
                    "with; write `as .planner-class` so the parity diff cannot guess wrong"
                )
                continue
            if number is None:
                # `inline` — the class is inline-styled in the donor, so it has
                # no CSS rule and therefore no catalogue entry.
                if selector not in inline_classes:
                    problems.append(
                        f"{where} declares `inline {selector}` but that class is not in the "
                        "donor's inline capture"
                    )
                continue
            owners = owner.get(selector)
            if owners is None:
                problems.append(
                    f"{where} cites element {number} for {selector}, which is not in the donor "
                    "catalogue at all — use `inline <class>` if it carries no CSS rule"
                )
            elif int(number) not in owners:
                problems.append(
                    f"{where} cites element {number} for {selector}, but that class belongs to "
                    f"element {'/'.join(str(n) for n in sorted(owners))} "
                    f"({catalogue[str(sorted(owners)[0])]['name']})"
                )
    return problems


# --------------------------------------------------------------------------
# The D1-D10 deviation register, as a live scoreboard rather than a document.
#
# `WF-025` requires the register "complete" before the parity gate can run, and
# an unregistered deviation is indistinguishable from drift. So each one is
# either ENFORCED -- satisfied now, and this script fails if it regresses -- or
# OUTSTANDING, or NOT_APPLICABLE because the surface it governs does not exist
# yet. S6 closes when nothing is OUTSTANDING.
# --------------------------------------------------------------------------

ENFORCED, OUTSTANDING, NOT_APPLICABLE = "enforced", "outstanding", "n/a"


def audit_deviations(tokens_text: str) -> list[tuple[str, str, str, str]]:
    """(id, state, requirement, detail) for D1 through D10."""

    shell = (ROOT / "web" / "src" / "shell.css")
    shell_text = shell.read_text(encoding="utf-8") if shell.is_file() else ""
    exporters = (ROOT / "travel_planner" / "exporters.py")
    exporters_text = exporters.read_text(encoding="utf-8") if exporters.is_file() else ""
    web_text = "\n".join(
        path.read_text(encoding="utf-8") for path in WEB_TSX if path.is_file()
    )
    results: list[tuple[str, str, str, str]] = []

    # D1 -- the dark accent triple is implemented, not dead code.
    dark_accent = re.search(
        r":root\.dark[^{]*\{[^}]*?--color-accent:\s*([^;]+);", tokens_text, re.S
    )
    results.append((
        "D1", ENFORCED if dark_accent else OUTSTANDING,
        "the dark accent triple is implemented",
        f"dark :root accent = {dark_accent.group(1).strip() if dark_accent else 'missing'}; "
        "a set country overrides it in both themes by D6, which is the mapping working, "
        "not the donor's dead-code bug",
    ))

    # D2 -- radius unified on 2px, pills exempt.
    radii = set(re.findall(r"border-radius:\s*([^;]+);", shell_text))
    stray = {value.strip() for value in radii} - {
        "var(--radius)", "var(--radius-house)", "var(--radius-pill)"
    }
    results.append((
        "D2", ENFORCED if not stray else OUTSTANDING,
        "radius unified on 2px; pills exempt",
        f"{len(radii)} distinct radius values, all tokenised" if not stray
        else f"untokenised: {sorted(stray)}",
    ))

    # D3 -- the no-country fallback is the house red, not blue.
    root_accent = re.search(r":root\s*\{[^}]*?--color-accent:\s*([^;]+);", tokens_text, re.S)
    fallback = root_accent.group(1).strip() if root_accent else ""
    results.append((
        "D3", ENFORCED if fallback.lower() == "#a30000" else OUTSTANDING,
        "the fallback accent is the house red, not #2563eb",
        f"no-country fallback = {fallback or 'missing'}",
    ))

    # D4 -- stale blue removed. #2563eb survives only as South Korea's accent.
    blue_lines = [
        line for line in tokens_text.splitlines()
        if "#2563eb" in line.lower() and "south-korea" not in line
    ]
    results.append((
        "D4", ENFORCED if not blue_lines else OUTSTANDING,
        "stale blue removed",
        "#2563eb appears only as South Korea's destination accent" if not blue_lines
        else f"{len(blue_lines)} stale use(s)",
    ))

    # D5 -- the violet is a tokenised fifth semantic colour.
    tokenised = "--color-purple" in tokens_text
    leaked = "8b5cf6" in shell_text.lower() or "8b5cf6" in web_text.lower()
    results.append((
        "D5", ENFORCED if tokenised and not leaked else OUTSTANDING,
        "#8b5cf6 tokenised as a fifth semantic colour",
        "--color-purple defined and no raw use outside tokens.css" if tokenised and not leaked
        else "raw hex leaked" if leaked else "--color-purple missing",
    ))

    # D6 -- exactly one country->accent mapping.
    tables = len(re.findall(r':root\[data-country="', tokens_text))
    elsewhere = re.findall(r'data-country="', web_text)
    results.append((
        "D6", ENFORCED if tables == 13 else OUTSTANDING,
        "one country-to-accent mapping",
        f"{tables} rules in tokens.css and no second table "
        f"({len(elsewhere)} literal data-country use(s) in components)",
    ))

    # D7 -- the export palette reads the single colour source.
    reads_tokens = "tokens.css" in exporters_text
    export_hexes = re.findall(r"#[0-9a-fA-F]{6}", exporters_text)
    results.append((
        "D7", ENFORCED if reads_tokens and not export_hexes else OUTSTANDING,
        "the export palette is re-tokenised",
        "exporters.py reads tokens.css and holds no hex literal" if reads_tokens and not export_hexes
        else f"{len(export_hexes)} hex literal(s) remain" if export_hexes else "does not read tokens.css",
    ))

    # D8 -- JetBrains Mono 700 is a real loaded weight, not synthesised.
    self_hosted = "@font-face" in tokens_text or bool(list(ROOT.glob("web/public/**/*.woff2")))
    results.append((
        "D8", ENFORCED if self_hosted else OUTSTANDING,
        "JetBrains Mono 700 is a real loaded weight",
        "no @font-face and no woff2 in web/public, so bold numerals are still "
        "browser-synthesised and a 3 can smear into an 8" if not self_hosted
        else "self-hosted",
    ))

    # D9 -- flags are a local sprite with a mandatory country name.
    # The probe reads *rendered* code, not prose: the word "flag" turns up in
    # comments about capture flags and feature flags, and one of those flipped this
    # entry from "no flag is rendered" to "local sprite in use" — a register line
    # asserting a sprite that does not exist. Comments are stripped before asking.
    renders_flag = bool(
        re.search(r"flag", re.sub(r"/\*.*?\*/|//[^\n]*", "", web_text, flags=re.S), re.I)
    )
    uses_cdn = "flagcdn" in web_text.lower() or "flagcdn" in shell_text.lower()
    results.append((
        "D9", OUTSTANDING if uses_cdn else (NOT_APPLICABLE if not renders_flag else ENFORCED),
        "flags are a local sprite with a mandatory country name",
        "no flag is rendered anywhere in the webapp, so there is no surface to "
        "convert; the rule binds whenever one is added" if not renders_flag and not uses_cdn
        else "flagcdn still referenced" if uses_cdn else "local sprite in use",
    ))

    # D10 -- the day-summary header is 3/1, not a locked 260px.
    ratio = "aspect-ratio: 3 / 1" in shell_text or "aspect-ratio:3/1" in shell_text.replace(" ", "")
    results.append((
        "D10", ENFORCED if ratio else OUTSTANDING,
        "the day-summary header is aspect-ratio 3/1",
        "artifact 032's .dayhead two-column header is not built; the itinerary "
        "has a totals block instead, so no ratio is declared" if not ratio
        else "3/1 declared",
    ))
    return results


def without_comments(text: str) -> str:
    """Strip block comments, keeping line numbers for failure messages."""

    return CSS_COMMENT.sub(
        lambda match: "\n" * match.group(0).count("\n"), text
    )


def undefined_var_uses() -> list[str]:
    """Every bare `var(--x)` whose property is declared nowhere.

    An undefined custom property is not an error: the declaration using it
    becomes guaranteed-invalid and silently falls back. That is how
    `--weight-primary` made a button lighter than its neighbours while claiming
    to make it heavier, with the token gate green throughout. Definitions are
    collected from tokens.css and the stylesheets, plus the properties
    components set at runtime, so the component-set pattern this file already
    requires (the pin number dividing by `var(--map-zoom)`) is not flagged as
    the bug it guards against.
    """

    defined: set[str] = set()
    scoped: dict[Path, list[tuple[int, str]]] = {}
    for path in (TOKENS, *WEB_CSS):
        lines = without_comments(path.read_text(encoding="utf-8")).splitlines()
        scoped[path] = list(enumerate(lines, 1))
        for _, line in scoped[path]:
            defined.update(VAR_DEFINED.findall(line))
    for path in WEB_TSX:
        defined.update(TSX_SET_PROPERTY.findall(path.read_text(encoding="utf-8")))
    problems: list[str] = []
    for path, lines in scoped.items():
        for number, line in lines:
            for name in VAR_USE_BARE.findall(line):
                if name not in defined:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{number} uses var({name}) with no "
                        "definition in tokens.css, the stylesheets, or a component "
                        "style object; a misspelt property silently falls back"
                    )
    return problems


def main() -> int:
    failures: list[str] = []
    notes: list[str] = []

    if not TOKENS.is_file():
        print("FAILED: tokens.css is missing", file=sys.stderr)
        return 1
    tokens_text = TOKENS.read_text(encoding="utf-8")

    # 1. All 13 country accent triples resolve.
    blocks = country_blocks(tokens_text)
    if len(blocks) != 13:
        failures.append(f"expected 13 country accent rules, found {len(blocks)}")
    for country, properties in sorted(blocks.items()):
        missing = [name for name in REQUIRED_TRIPLE if name not in properties]
        if missing:
            failures.append(f"{country} is missing {', '.join(missing)}")
        for name in REQUIRED_TRIPLE:
            value = properties.get(name)
            if value and channels(value) is None:
                failures.append(f"{country}.{name} does not resolve to a colour: {value!r}")
    print(f"PASS: 13 country accent triples resolve ({len(blocks)} rules)"
          if not failures else "checking country accents", flush=True)

    # 2. No raw colour literal outside tokens.css.
    for path in WEB_CSS:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ALLOWED_LITERAL_CONTEXT.match(line):
                continue
            if COLOUR_LITERAL.search(line):
                failures.append(
                    f"{path.relative_to(ROOT)}:{number} holds a colour literal; "
                    f"use a token from tokens.css: {line.strip()[:70]}"
                )

    # 2b. No bare var(--x) without a definition.
    failures.extend(undefined_var_uses())

    # 3a. Every declared ancestor is the right one.
    failures.extend(validate_ancestors())

    # 3. Every stage/shared component that renders an element declares an ancestor.
    #    A provider renders only its own context and puts nothing on the page, so it
    #    has no counterpart in the donor to derive from and no styling to conform to.
    #    Requiring the note there would be answered with a fictional one.
    #    Detected by what a styled element must have — an intrinsic tag or a class —
    #    rather than by trying to tell JSX from a generic, which `useState<Theme>`
    #    loses. A false positive here only asks for the note that was already
    #    required, so the ambiguous direction is the safe one.
    renders_markup = re.compile(r"className=|<[a-z][a-zA-Z0-9]*[\s/>]")
    for path in WEB_TSX:
        if path.name.endswith(".test.tsx"):
            continue
        text = path.read_text(encoding="utf-8")
        if not renders_markup.search(re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)):
            continue
        if "derives-from:" not in text:
            failures.append(
                f"{path.relative_to(ROOT)} declares no `derives-from:` ancestor; "
                "a new element passes on token conformance plus a declared ancestor"
            )

    # 4. Contrast, at the AA floor for normal text, in both themes.
    contrast_problems = check_contrast(tokens_text)
    failures.extend(contrast_problems)
    if not contrast_problems:
        notes.append(
            f"every text token and all {len(blocks)} destination accents clear "
            f"{AA_NORMAL}:1 in both themes, as link text and as a fill"
        )

    register = audit_deviations(tokens_text)
    outstanding = [row for row in register if row[1] == OUTSTANDING]
    print(f"  deviation register: {len(register)} entries", flush=True)
    for did, state, requirement, detail in register:
        mark = {ENFORCED: "ok ", OUTSTANDING: "TODO", NOT_APPLICABLE: "n/a"}[state]
        print(f"    [{mark}] {did}: {requirement} — {detail}", flush=True)
    if outstanding:
        notes.append(
            f"{len(outstanding)} deviation(s) outstanding, so the register is not yet "
            f"complete: {', '.join(row[0] for row in outstanding)}. S6 closes when this is zero"
        )

    # Sizes inside the map's viewBox are multiplied by the zoom, so anything drawn there
    # has to opt out of that scaling or it grows with the magnification. Neither the unit
    # tests nor the screen baselines can see this: the markup and the tokens are
    # unchanged, and the baselines photograph the default view, which is the one zoom
    # where it looks right. It has broken twice -- once as a ~100px label halo, once as a
    # ~440px pin number that covered the whole map -- so it is checked here, where the
    # stylesheet is already being read.
    stylesheet = "\n".join(path.read_text(encoding="utf-8") for path in WEB_CSS)
    counter_scaled = re.search(
        r"\.places-map \.plan-map-point text \{[^}]*\}", stylesheet
    )
    if not counter_scaled or "--map-zoom" not in counter_scaled.group(0):
        failures.append(
            "the pin's number must divide by var(--map-zoom): inside the map's viewBox a "
            "fixed size grows with the zoom"
        )
    # Found, not listed. This was a hand-written tuple of six selectors and it missed
    # `.plan-map-route` — the itinerary's day line, drawn at `stroke-width: 2` in map
    # units, which at the map's 178x ceiling is a band hundreds of pixels wide. A gate
    # whose coverage is a literal list silently stops covering the thing added after it
    # was written, which is the failure it exists to prevent. Every map rule declaring a
    # stroke width is now required to opt out of scaling, so a new layer is covered on
    # the day it lands.
    stroked = re.findall(
        r"(?m)^((?:\.[\w-]*(?:places-map|plan-map)[\w-]*[^{]*?))\{([^}]*stroke-width[^}]*)\}",
        stylesheet,
    )
    if not stroked:
        failures.append("no stroked map layer found to check — has the map been renamed?")
    for selector, body in stroked:
        name = selector.strip().splitlines()[0]
        if "non-scaling-stroke" in body or "--map-zoom" in body:
            continue
        # A deliberate exception, which must say so in the rule itself. The one-way
        # arrows ride a carrier line whose *stroke width is the marker's unit*
        # (`markerUnits: strokeWidth`), so a screen-unit stroke there would resize every
        # arrow — the 170px arrows that once hid the whole map are what the small
        # literal is for. Opting out in the stylesheet keeps the reason next to the rule.
        if "map-units-deliberate" in body:
            continue
        failures.append(
            f"{name} needs vector-effect: non-scaling-stroke, or "
            "its stroke is measured in map units and thickens as the map is zoomed"
        )
    if not failures:
        print("PASS: every map layer is measured in screen units, not map units", flush=True)

    for note in notes:
        print(f"NOTE: {note}", flush=True)
    if failures:
        print(f"FAILED: {len(failures)} token-gate problems", file=sys.stderr)
        for problem in failures:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(
        f"PASS: token allowlist clean across {len(WEB_CSS)} stylesheet(s) and "
        f"{len(WEB_TSX)} component(s)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
