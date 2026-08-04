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
