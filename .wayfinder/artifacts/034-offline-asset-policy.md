# Offline asset policy for the webapp

Resolves `Decide the offline asset policy for the webapp` (WF-034).

Decided 2026-08-03 through the offline-assets interview. Measured against the checkout at `bfd86e0`.
Paths are repo-relative.

## The finding that shrinks the ticket: there is no map to make offline

The ticket calls map tiles "the third remote dependency, and the largest." Measured, they are not a
dependency of anything that survives:

- **The exports contain no map.** `exporters.py` prints numbered stops with coordinates as text under a
  "Day overview" heading (`:347`, `:356`–`364`), and the poster draws a stop *number* (`:187`–`188`). No
  tiles, no basemap, no rendered geography anywhere.
- **The only tile dependency is `st.map`** (`views/itinerary.py:115`), which dies with Streamlit.

So tiles would be a **new** dependency, not a migrated one — introduced into an app whose stated premise is
a plane and a Taipei hotel with no usable network.

## The six decisions

| # | Question | Decided |
|---|---|---|
| 1 | Fonts | **Self-hosted `woff2`** for the browser; a **merged Noto TTF** shipped for exports |
| 2 | Bold monospace | **A real 700 ships.** No more faux bold |
| 3 | Map tiles | **None.** The numbered stop list *is* the map |
| 4 | `flagcdn.com` | **A local SVG sprite**, scoped to the picker's 32 countries |
| 5 | Offline contract | **Everything local works**; network actions are labelled before use |
| 6 | Token file format | **`tokens.css` is truth.** Tailwind imports it; Python parses it |

## 1. Fonts

```
web/public/fonts/   PlusJakartaSans  400 500 600 700     (woff2)
                    JetBrainsMono    400 500 600 700     (woff2)
assets/fonts/       NotoMerged-Regular.ttf               (Latin + Thai + CJK)
                    LICENSE  +  the fonttools recipe that built it
```

**The browser side removes a real user-visible bug.** Auto-Bill's Google Fonts `@import` at `index.css:1` is
render-blocking and unreachable offline, so the app degrades to Segoe UI for text and **Courier New for every
numeral** — the worst possible fallback for an app about money. Self-hosting ends that. The never-used `300`
weight is dropped.

**The export side removes a hidden machine dependency.** `exporters.resolve_font()` needs *one* `.ttf` that
Pillow can use, covering Latin + Thai + CJK, and Pillow cannot fall back between files. Measured on this
machine:

| Candidate | Present |
|---|---|
| `/Library/Fonts/Arial Unicode.ttf` | **yes** |
| `/System/Library/Fonts/Supplemental/Arial Unicode.ttf` | **yes** |
| `/System/Library/Fonts/Supplemental/Ayuthaya.ttf` | yes (Thai only) |
| `/usr/share/fonts/.../NotoSansThai-Regular.ttf` | no |
| `/usr/share/fonts/.../DejaVuSans.ttf` | no |

So exports work **only because this Mac happens to have Arial Unicode**, which is proprietary and not
redistributable. On any other machine `resolve_font()` **raises rather than rendering tofu**, so the PDF and
poster fail outright — and those are the pilot artifact.

Shipping a merged Noto TTF makes exports work from a clean clone on any machine. Noto is OFL, so
redistribution is legal and the licence record is simply a file.

> **Why merged, and not just "ship Noto":** no single Noto file covers both Thai and CJK. Noto Sans Thai has
> no CJK; Noto Sans CJK has no Thai. Since Pillow takes one file and cannot fall back, the file has to be
> built by merging — a one-off `fonttools` step whose recipe is checked in beside the output so it can be
> re-run.

Accepted costs: a multi-megabyte binary in the repository; a build recipe someone must be able to re-run; and
two ways to get a font, since `TOURIST_EXPORT_FONT` stays as the override.

## 2. Bold monospace becomes real

`.font-mono` is used at weight 700/800 in six places while only 400/500/600 are loaded, so **every bold
monospace numeral today is browser-synthesised faux bold**. This resolves `WF-020`'s AMBIGUITY 4, which
`WF-025` explicitly deferred here.

Numerals are the money surface, and faux bold smears digit shapes at exactly the size where a `3` and an `8`
must stay distinguishable. Shipping a real 700 costs one small `woff2` subset, and dropping the unused 300
keeps the weight count unchanged.

This is a small deliberate deviation from the donor, which renders faux bold — so it needs a register entry
(§Deviations).

## 3. No tile map

What ships is what the exports already ship:

```
Day overview
  1  Longshan Temple           25.03654, 121.49992    locked
  2  Bopiliao Historic Block   …                      flexible
  ⚑  Hotel anchor              …
```

Three reasons, in order of weight:

1. **Screen and export agree by construction** rather than by effort. `build_export_snapshot()` exists so
   outputs cannot diverge; a screen-only map would diverge by design.
2. It removes the largest remote dependency **before it is introduced**, in an app whose premise is no
   network.
3. `WF-021` found the numbered map is the **one** planner element Auto-Bill's visual language cannot reach —
   and that the donut **legend** is structurally the stop list. So this ships the half the language can
   reach and skips the half it cannot.

**This is a product loss, not just a dependency saved**, and it should be recorded as one: coordinates are
not spatial reasoning, you cannot see that two stops are adjacent, and the owner will use a phone map app
instead — so the plan and the map live in different places. That is accepted, not overlooked.

It is **not** a parity deviation: Auto-Bill has no spatial element at all, so there is nothing to deviate
from.

## 4. Flags: a local sprite, and the scope settles itself

`utils.js` fetches ~50 flags from `flagcdn.com`. That becomes a **self-hosted SVG sprite**, with the country
name always beside it as `WF-027` requires.

The ticket's hard part — which of Auto-Bill's three divergent country lists to cover (13 accents, ~30 emoji,
~50 URLs) — dissolves against our own data:

- `destinations.COUNTRIES` holds **32** countries, and it is a **picker convenience, not a restriction**:
  both dropdowns accept a typed value so any worldwide destination stays reachable.
- **`nationality` is free text** (`setup.py`, 60 characters, unconstrained).

So **no fixed sprite can ever be complete**, and it does not need to be:

> **Flag present → show flag + name. Flag absent → show the name alone.** No placeholder glyph, no fallback
> flag.

The sprite therefore caches the picker's 32 rather than curating a world list. That also answers the
"politically fraught" concern mechanically: it makes no statement about which places count, because it is an
**enhancement layer over a name that is always there anyway**.

Emoji flags were rejected on two measured grounds: the export path strips pictographs, so every flag would
become an **empty cell** in the PDF — exactly the failure `WF-027` named — and Windows renders
regional-indicator pairs as letter pairs rather than flags.

Accepted: another asset set and its licence, and the export shows only the name, so screen and export differ
in character even though they agree in content.

## 5. The offline contract

| Works offline | Requires network |
|---|---|
| View the active plan and every day | Discovery (Overpass) |
| Non-AI quick actions and re-optimize | Geocoding (Nominatim) |
| Propose, apply and restore revisions | Opening-hours refresh |
| Record split rows and cost rows | Route refresh |
| Readiness board and packing | Timezone refresh |
| Every export — PDF, poster, workbook, ICS | Place enrichment (paid) |
| | Free-text GenAI revision (paid) |

**Most of this is already true and simply unstated.** The optimizer is deterministic and local, `revision.py`
is pure, and the exporters are snapshot-in/bytes-out — so **re-optimizing and revising work offline today.**
That is a far stronger offline story than the ticket assumes.

The decision is to state it *and* to surface it:

> **A control whose action requires network says so before it is pressed** — the same move the app already
> makes for money, where every paid action states its cost immediately before the spending button. `WF-021`
> listed that behaviour as must-survive; this extends the same courtesy to reachability.

It turns a silent 34-second failure on hotel wifi into a decision made knowingly.

Accepted: ~7 action types need a network affordance; "needs network" states a *requirement* rather than live
status, since reachability is only truly knowable by trying; and telling offline apart from a provider being
down is its own problem — though `WF-019`'s error taxonomy already separates `offline` from `api_error`.

## 6. `tokens.css` is the single colour source

`WF-025` decided one machine-readable colour source both renderers read, and deferred its format here.

```
tokens.css      --bg-card-border: #1A1A1A;  --shadow-sm: 1px 1px 0 0 …
   ├── @theme         imports it directly — no transformation, no build step
   └── exporters.py   parses the `--name: value;` pairs
```

CSS is chosen as **truth** rather than as an output because `WF-025` picked Tailwind v4 precisely *because*
the tokens already are CSS custom properties. Generating CSS from JSON would transform them away from the
form Tailwind wants, add a build step, and produce a **generated artifact that can go stale** — the same
failure class `WF-026` had to add a staleness check for with `web/dist`.

Python parsing `--name: value;` needs no dependency.

> **The repo therefore has two shared-data formats for two different reasons, and that is deliberate:** copy
> is **JSON**, because neither consumer has a native preference and TypeScript gets compile-time key checking
> from it; tokens are **CSS**, because one consumer does have a native preference and it is the source form.

Accepted: Python parsing CSS is unusual and a naive regex could be confused by comments or nesting; values
arrive as strings, so anything numeric is parsed at the point of use.

## Deviations this ticket adds to the register

`WF-025` requires every deliberate difference from the donor to be numbered, because an unregistered
deviation is indistinguishable from drift.

| ID | Deviation | Why |
|---|---|---|
| **D8** | **JetBrains Mono 700 is real**, not synthesised | Faux bold smears digits on the money surface (§2) |
| **D9** | **Flags are a local sprite with a mandatory country name**, not `flagcdn.com` images alone | Removes a remote dependency; the name is required by `WF-027` regardless (§4) |

Not deviations: no tile map (the donor has no spatial element), and the export palette convergence, which is
already **D7** and was recorded on this ticket earlier.

## Already settled, inherited rather than re-decided

- **The export palette converges with the UI tokens** — `WF-025` D7, recorded in this ticket's 2026-08-03
  note. The caution in the Context above ("must not recolour the exports") was overridden deliberately.
- `assets/hero.png`, `public/icons.svg` and `lucide-react` are already local and bundled. Nothing to do.

## Explicitly not decided here

- Which subset ranges the merged Noto build covers, and how large the result is allowed to be.
- Whether the browser `woff2` files are subset per script or shipped whole.
- Where the sprite lives relative to `web/public/` and how it is referenced.
- Whether "needs network" is a badge, a tooltip, or inline text — that is `Design the feedback, confirm, and
  disabled elements Auto-Bill never had`.

## What this hands downstream

| Ticket | Consequence |
|---|---|
| `Design the feedback, confirm, and disabled elements Auto-Bill never had` | Gains a third state family beside disabled and confirming: **requires network**, on ~7 action types |
| `Define the visual parity gate for the Tailwind rebuild` | Gains **D8** and **D9**, and its token target is now concretely `tokens.css` |
| `Prototype the itinerary day screen in the new design` | **No map to prototype.** The day screen's spatial element is the numbered stop list, derived from the donut legend |
| `Extract the Auto-Bill design token contract` | Its output format is settled: CSS custom properties in `tokens.css`, not the drafted JS config |
| `Lock the Phase 2 slice plan and validation scorecard` | The merged-font build is a one-off prerequisite with a licence record, and shipping it makes exports work from a clean clone for the first time |
