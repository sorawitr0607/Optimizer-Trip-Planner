---
id: WF-034
title: Decide the offline asset policy for the webapp
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
blocked_by: []
---

# Decide the offline asset policy for the webapp

## Question

Which fonts, flags, and artwork ship inside the repository, in which formats and weights, and what does the
webapp look like on a plane or in a Taipei hotel with no usable network?

## Context

Graduated from the map's fog by the token contract, which found three separate network dependencies in an
app whose whole premise is local-first.

- The Google Fonts `@import` at `index.css:1` is render-blocking and unreachable offline, so Auto-Bill
  currently degrades to `Segoe UI` for text and **Courier New for every numeral** — the worst possible
  fallback for a money app. It requests Plus Jakarta Sans `300;400;500;600;700;800` (300 never used) and
  JetBrains Mono `400;500;600`, while `.font-mono` is used at weight 700/800 in six places, so every bold
  monospace numeral in the app today is browser-synthesised faux bold. Decide whether that bold becomes real.
- The export font is a **separate asset that cannot be the same file**. `exporters.resolve_font()` needs a
  `.ttf` for Pillow covering Latin + Thai + CJK; the only entry in its candidate list covering all three is
  macOS `Arial Unicode.ttf`, which does not exist on this Windows machine, and Plus Jakarta Sans has neither
  Thai nor CJK. With no font it raises rather than rendering tofu, so the PDF and poster simply fail. So the
  repo needs both webfonts for the browser and a Unicode TTF for Pillow, and `TOURIST_EXPORT_FONT` points at
  the latter.
- `utils.js` fetches country flags from `flagcdn.com` for a ~50-country list — a second remote dependency,
  and a country can have a flag with no accent because three divergent country lists exist (13-entry accent
  table, ~30-entry emoji flags, ~50-entry flag URLs). Emoji flags are the offline-safe alternative, but the
  export path already strips pictographs (`_labels()`) because no Unicode font carries them.
- The poster and Excel palette (`#101820`, `#F2F5F7`, `#8FB8D8`, `#2A3B49`, `#A9BECD`, `#F2C14E`, `#6C8598`,
  `#E8EEF3`) shares nothing with the splitter tokens. A well-meaning "unify the tokens" pass must not
  recolour the exports; decide explicitly whether the two palettes converge or stay separate.
- `assets/hero.png` and `public/icons.svg` are local already; `lucide-react` bundles. Those are fine.
- **Map tiles are the third remote dependency, and the largest.** The element inventory found the numbered map
  to be the only planner element Auto-Bill's visual language cannot reach — it has no spatial primitive and no
  map dependency at all. Whatever draws it fetches tiles, which is exactly what a Taipei hotel with no network
  cannot do. Decide whether tiles are cached ahead of the trip, whether a static rendered map image suffices
  offline, or whether the numbered list is the offline fallback for the map.

Decide at least: self-host or CDN, and if self-hosted where the files live and under what licence record;
which families and weights ship, in `woff2` for the browser and `.ttf` for Pillow; whether bold monospace
becomes a real weight; what replaces `flagcdn.com`; ~~whether the export palette and the UI tokens
converge~~ (**decided elsewhere — see below**); and what the app is contractually allowed to do when
offline during a trip.

### 2026-07-31 — Unblocked, and one item removed from scope

**Unblocked.** `Extract the Auto-Bill design token contract` was reopened the same day because it is
incomplete for 39 inline-only classes and 114 inline `style={{…}}` sites — but **none of that is asset
work.** Everything this ticket needs from the contract is already extracted and is quoted in the Context
above: the font families and weights, the faux-bold-monospace ambiguity, the `flagcdn.com` dependency and
the three divergent country lists, and the export palette. The missing 39 classes are layout and
interaction styling. So the `blocked_by` edge was dropped rather than waiting on work this ticket does not
depend on.

**One "decide at least" item is already decided, and it went the way this ticket's Context warned against.**
[Define the visual parity gate for the Tailwind rebuild](025-define-the-visual-parity-gate-for-the-tailwind-rebuild.md)
decided that **colour gets one machine-readable source that both renderers read**, recorded as deviation
**D7** — so the export palette and the UI tokens **converge**, and the exports are recoloured. The Context
above cautions that "a well-meaning 'unify the tokens' pass must not recolour the exports"; the owner
overrode that caution deliberately, on this reasoning:

- `WF-022` made the exports a **pilot-ready gate**, compared against the four reference workbooks. They are
  already a checked surface — just not for colour — and they are what the owner physically carries in Taipei.
- `exporters.py` hardcodes 8 hexes across 17 occurrences in a cool blue-grey palette that matches nothing in
  Auto-Bill, so the poster, PDF and workbook currently look like a different product.
- The precedent is this repo's own: `WF-018` put split math in one implementation so "the screen, the
  workbook and the PDF cannot disagree by a satang."

**Two consequences for what remains in scope here.** First, the `.ttf` for Pillow and the `woff2` files for
the browser are still separate assets and that does not change — convergence is about *colour*, not fonts.
Second, `Decide which exporter survives, Python or JavaScript` should be answered **before** the
re-tokenisation work starts, because if the Python exporters are retired, part of D7 is wasted; that
sequencing note belongs with the asset policy since it decides which renderer needs which files.

**Still this ticket's to decide:** whether bold monospace becomes a real loaded weight (`WF-025` explicitly
deferred AMBIGUITY 4 here), what replaces `flagcdn.com`, whether the token source ships as JSON or CSS, the
map-tile question, and the offline contract itself.

## Resolution comments

### 2026-08-03 — Decided through the offline-assets interview

The measured font survey, the deviations added and what is left open are in
[`034-offline-asset-policy.md`](../artifacts/034-offline-asset-policy.md).

**The largest item in the Context turned out not to exist.** Map tiles are called "the third remote
dependency, and the largest" — but the **exports contain no map at all**: `exporters.py` prints numbered stops
with coordinates as text under a "Day overview" heading (`:347`, `:356`–`364`) and the poster draws a stop
*number* (`:187`–`188`). The only tile dependency is `st.map` (`views/itinerary.py:115`), which dies with
Streamlit. So tiles would be a **new** dependency, not a migrated one.

- **Fonts self-host as `woff2`** (Plus Jakarta Sans and JetBrains Mono, 400/500/600/700, dropping the
  never-used 300), and a **merged Noto TTF ships for the exports** with its OFL licence and the `fonttools`
  recipe beside it. This removes a hidden machine dependency: measured, exports work **only because this Mac
  has `Arial Unicode.ttf`** in two places — proprietary and not redistributable — while both Linux candidates
  are missing, and `resolve_font()` raises rather than rendering tofu, so on any other machine the PDF and
  poster fail outright. It has to be *merged* because no single Noto file covers both Thai and CJK and Pillow
  cannot fall back between files. Shipping it makes exports work from a clean clone for the first time.
- **Bold monospace becomes real.** `.font-mono` is used at 700/800 in six places while only 400/500/600 load,
  so every bold numeral today is synthesised — and faux bold smears digit shapes at exactly the size where a
  `3` and an `8` must stay apart. Resolves `WF-020`'s AMBIGUITY 4.
- **No tile map. The numbered stop list is the map**, which is what the exports already do — so screen and
  export agree by construction rather than by effort, and the largest remote dependency is never introduced.
  `WF-021` found the numbered map is the one element the visual language cannot reach, and that the donut
  legend is structurally the stop list, so this ships the reachable half. **Recorded as a genuine product
  loss**, not just a dependency saved: coordinates are not spatial reasoning, and the owner will use a phone
  map instead.
- **`flagcdn.com` becomes a local SVG sprite** with the country name always beside it. The ticket's hard part
  — which of three divergent country lists to cover — dissolves against our own data: `destinations.COUNTRIES`
  holds 32 and is a picker convenience rather than a restriction, and `nationality` is free text. **No fixed
  sprite can ever be complete, and it does not need to be**: flag present shows flag plus name, flag absent
  shows the name alone. That also answers the curation concern mechanically — the sprite is an enhancement
  layer over a name that is always there. Emoji flags were rejected because the export path strips
  pictographs, so each would become an empty cell in the PDF.
- **Offline contract: everything local works; network actions say so before they are pressed.** Most of it is
  already true and merely unstated — the optimizer is deterministic and local and `revision.py` is pure, so
  **re-optimizing and revising work offline today**. Only discovery, geocoding, opening hours, routes,
  timezone, enrichment and GenAI need network. Labelling that need mirrors a rule the app already follows for
  money, where every paid action states its cost immediately before the spending button.
- **`tokens.css` is the single colour source, in CSS rather than JSON.** `WF-025` chose Tailwind v4 precisely
  because the tokens already *are* custom properties, so CSS is the source form; generating it from JSON would
  add a build step and a generated artifact that can go stale, the same failure class as `web/dist`. The repo
  therefore has two shared-data formats deliberately: copy is JSON for compile-time key checking, tokens are
  CSS because one consumer has a native preference.

Adds two entries to `WF-025`'s deviation register: **D8** real JetBrains Mono 700, and **D9** local flag
sprite with a mandatory country name. No tile map is *not* a deviation, since the donor has no spatial
element to deviate from.
