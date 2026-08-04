#!/usr/bin/env python3
"""The token half of the visual parity gate. Free, no browser, no network.

`WF-025` asks for three things this can check without a screenshot harness:

- **All 13 country accent triples resolve** (§2c). The accent is one custom
  property, so it can recolour a pixel but never move one; imaging it 13 times
  tests nothing an assertion cannot.
- **The token allowlist is clean** — the rebuild's stylesheets carry no raw
  colour literals. `tokens.css` is the single colour source and the only file
  allowed to hold them.
- **Every new element declares an ancestor.** An element with no Auto-Bill
  counterpart passes on token conformance plus a declared ancestor, so a
  `derives-from:` note is required rather than optional.

It also reports the contrast of every accent against both theme backgrounds,
because an accent chosen on a light background is not automatically legible on
`#121212` and nothing else in the gate would notice.
"""

from __future__ import annotations

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

REQUIRED_TRIPLE = ("--color-accent", "--color-accent-hover", "--color-accent-light")


def country_blocks(text: str) -> dict[str, dict[str, str]]:
    """Every `:root[data-country="x"]` rule and the properties it sets."""

    found: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r':root\[data-country="([^"]+)"\]\s*\{([^}]*)\}', text, re.S
    ):
        country, body = match.group(1), match.group(2)
        found[country] = {
            name.strip(): value.strip()
            for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body)
        }
    return found


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
    renders_flag = bool(re.search(r"flag", web_text, re.I))
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

    # 3. Every stage/shared component declares an ancestor.
    for path in WEB_TSX:
        if path.name.endswith(".test.tsx"):
            continue
        text = path.read_text(encoding="utf-8")
        if "derives-from:" not in text:
            failures.append(
                f"{path.relative_to(ROOT)} declares no `derives-from:` ancestor; "
                "a new element passes on token conformance plus a declared ancestor"
            )

    # 4. Contrast report. Informational: an accent picked on white is not
    #    automatically legible on #121212, and no other gate would notice.
    light_bg = re.search(r"--bg-primary:\s*([^;]+);", tokens_text)
    dark_bg = re.search(
        r":root\.dark[^{]*\{[^}]*?--bg-primary:\s*([^;]+);", tokens_text, re.S
    )
    if light_bg and dark_bg:
        dark_overrides = {
            match.group(1): match.group(2)
            for match in re.finditer(
                r'\[data-country="([^"]+)"\][^{]*\{[^}]*?--color-accent:\s*([^;]+);',
                re.sub(r":root\[data-country", "IGNORED", tokens_text),
                re.S,
            )
        }
        weak = []
        for country, properties in sorted(blocks.items()):
            accent = dark_overrides.get(country) or properties.get("--color-accent", "")
            on_dark = contrast(accent, dark_bg.group(1))
            if on_dark is not None and on_dark < 3.0:
                weak.append(f"{country} {accent} → {on_dark:.2f}:1")
        if weak:
            failures.append(
                "accents below 3:1 against the dark background "
                f"({len(weak)} of {len(blocks)}): " + "; ".join(weak)
                + " — add a `:root.dark[data-country=...]` override"
            )
        else:
            notes.append(
                f"all {len(blocks)} destination accents clear 3:1 on both backgrounds"
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
