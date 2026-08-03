# Visual parity gate for the Tailwind rebuild

Resolves `Define the visual parity gate for the Tailwind rebuild` (WF-025).

Decided 2026-07-31 through the parity interview. Every count was measured against `Auto-Bill-Splitter`
and the planner checkout at `4c27993`. Paths are repo-relative to each project.

## Counts up front, and a correction

The ticket asked for the inline-only class count to be reconciled against the sources rather than trusting
either prior figure. Measured:

| Measure | `WF-020` said | `WF-021` said | **Measured** |
|---|---|---|---|
| JSX classes with no CSS rule in `index.css` | ~28 styled inline only | 18 with zero rules | **39** |
| Inline `style={{…}}` sites | — | 113 (87 / 16 / 10) | **114** (88 Dashboard / 16 Modal / 10 Wizard) |
| Distinct class selectors in `index.css` | — | ~330 blocks | **250** distinct class names |

Neither earlier figure was wrong for what it measured — `WF-021` counted renderable *elements*, `WF-020`
counted a different slice — but **both undercount, so the contract's blind spot is larger than either
ticket assumed.**

Method: every hyphenated token inside a `className` attribute across `src/**/*.jsx`, minus every `.class`
selector appearing anywhere in `src/index.css`. Reproducible; re-run it if the donor changes.

### The 39, grouped by what they cost

| Group | Classes | Why it matters |
|---|---|---|
| **Filter dimming** | `.active-bar` `.active-cat` `.active-filter` `.dimmed-bar` `.dimmed-cat` `.dimmed-filter` | The entire filter interaction exists nowhere in the stylesheet, exactly as `WF-020` warned |
| **Split allocation modes** | `.split-view-equal-all` `-equal-selected` `-manual` `-single` `.split-workspace` | ~~The three allocation modes' layout~~ — **corrected 2026-08-03**: these carry no styling at all, in CSS *or* inline. They are bare containers, so the mode layout must be **designed**, not recovered |
| **Settlement** | `.settlement-card` `.settlement-grid` `.settlement-item` `.main-cardholder-select` | The settlement surface, also on `/split` |
| **Tab views** | `.overview-tab-view` `.transactions-tab-view` `.settings-tab-view` `.backup-tab-view` | ~~Auto-Bill does have tabs, inline-styled~~ — **corrected 2026-08-03**: they carry no styling at all. The element inventory was right that there is **no tab element to lift**; these are bare containers |
| **Money display** | `.avatar-cost-thb` `.txn-amount-thb` `.txn-share-badge` `.txn-price-insight` `.donut-subvalue` | Numeral rendering, the JetBrains Mono surface |
| **Tailwind-shaped names never written** | `.flex-between` `.flex-column` `.grid-2-columns` `.padding-y-4` `.text-bold` `.text-amber` `.text-purple` | **These 7 dissolve into real Tailwind v4 utilities for free** |
| Remaining | `.chart-card` `.recent-txns-card` `.btn-clear-filter-sm` `.clickable-filter` `.clickable-filter-item` `.hero-stats-info` `.step-badge-indicator` `.wizard-step-content` `.backup-tab-view` … | Card variants and wizard internals |

## The seven decisions

| # | Question | Decided |
|---|---|---|
| 1 | What defines the target | **The token contract — completed first**, absorbing the 39 and the 114 inline sites |
| 2 | How parity is checked | **Screenshot comparison** at two levels (§2), plus token conformance for new elements |
| 3 | Elements with no counterpart | **Token-only conformance plus a declared ancestor** |
| 4 | Auto-Bill's own defects | **Fixed, recorded in a deviation register** (§4) |
| 5 | Screenshot matrix | **4 per screen** — light/dark × en/th — with the 13 accents asserted as tokens |
| 6 | The two radius systems | **Unified on `2px`**, pills exempt |
| 7 | Where colour data lives | **One machine-readable source both renderers read** |

Sign-off is the owner. Single-owner and owner-led is a locked destination decision, so there is nobody
else, and saying so removes a question rather than answering it vaguely.

## 1. The target must be completed before the gate can run

The contract survives the donor being archived, which the running app does not — the map makes
`Auto-Bill-Splitter` a read-only donor that is then archived, so any gate anchored on a live app has an
expiry date built in.

**But the gate is blocked until the contract absorbs what it currently misses:** the 39 inline-only
classes, the 114 inline style sites, the off-token literals in §9d–9e of the contract, and the three
hardcoded pin hexes in `views/itinerary.py:94,104` the inventory flagged. A gate that reads only today's
contract inherits exactly the blind spot the contract had.

## 2. What "screenshot comparison" concretely means

**A resolution, flagged as such:** whole-screen diffs against the donor are impossible. Auto-Bill has two
screens; the planner has nine routes. Diffing `/itinerary` against Auto-Bill's dashboard is meaningless.
So the mechanism operates at two levels, and only one of them is parity:

### 2a. Element-level parity, against the donor — and it has a deadline

For the **41 lifted elements**: render each in isolation in a component gallery, in both projects, and diff
those images. The same element should render identically regardless of the screen it sits on, so this is a
meaningful comparison where a whole-screen diff is not.

> **This must happen while `Auto-Bill-Splitter` is still runnable, before it is archived.** Capturing the
> donor is a dated prerequisite, not a step that can be deferred — the same shape of mistake as trying to
> produce a reference after the source is gone.

### 2b. Screen-level regression baselines, against the rebuild

For the **9 routes**: 4 baselines each — light/dark × en/th — approved once, then diffed on every change.
36 images. This catches drift over time. It does not prove parity with Auto-Bill, and should not be
described as if it does.

### 2c. Why 4 and not 52

The 13-country accent is written as a **single inline custom property on `<html>`** (`App.jsx:64`–`66`), so
it can recolour a pixel but never move one. Imaging it 13 times tests nothing that one assertion cannot,
so the accents get a **token test** asserting all 13 triples resolve — not 12 redundant images per screen.

Thai gets its **own** baseline per theme, so `th` is diffed against `th` and differing Thai metrics never
produce a false failure. Baselines are captured on one fixed machine, since cross-platform font rendering
is what makes these gates flaky, and a flaky gate gets switched off. **A pixel tolerance must be agreed
when the harness is built** — zero tolerance will be flaky regardless.

## 3. Elements with no Auto-Bill counterpart

Token-only conformance, plus a declared ancestor:

```tsx
// StageBlockedNotice.tsx
// derives-from: element 26 .recent-row-item
```

The inventory already assigned each of the 18 a nearest Auto-Bill element to build from, so the ancestor is
recorded work rather than new analysis. It makes review answerable — "does this look like its ancestor" can
be judged; "does this look like Auto-Bill" cannot — and it catches an element drifting into its own visual
dialect while every individual value stays legal.

**One explicit exemption:** the numbered map has no ancestor. `WF-021` found the visual language does not
extend to it, since Auto-Bill contains no spatial element at all. Its nearest relative is the donut
**legend** for the stop list beneath, which does have an ancestor; the map canvas itself is exempt and is
gated on token conformance only.

## 4. The deviation register

Auto-Bill's defects are fixed, not reproduced. **Without this register the gate cannot function** — every
intentional fix would read as a parity failure, and a gate that cries wolf gets disabled. The donor is
archived afterwards, so this becomes the only record of why the two differ.

| ID | Deviation | Why |
|---|---|---|
| **D1** | The dark accent triple is **implemented** | Dead code in the donor: `App.jsx:64`–`66` writes the country accent as an inline style on `<html>`, which beats `:root.dark`. The dark theme's accent never applies |
| **D2** | Radius **unified on `2px`**; pills (`9999px`) exempt | §6 |
| **D3** | The fallback accent is the **house red**, not `#2563eb` | Both documented fallbacks return blue, so a no-country state renders in a colour the app does not own |
| **D4** | Stale blue **removed** (`index.css:1427`, `:1797`) | Survives from a previous accent theme inside a red app |
| **D5** | `#8b5cf6` **tokenised** as a fifth semantic colour | Untokenised across 8 uses, so a raw hex would otherwise have to be permitted by the allowlist |
| **D6** | **One** country→accent mapping | `utils.js` carries a second, larger country table that shadows the accent table (`WF-020` AMBIGUITY 6) |
| **D7** | The **export palette is re-tokenised** | §7 |
| **D8** | **JetBrains Mono 700 is a real loaded weight** | Added 2026-08-03 by `Decide the offline asset policy for the webapp`. `.font-mono` is used at 700/800 in six places while only 400/500/600 load, so every bold numeral in the donor is browser-synthesised — and faux bold smears digit shapes at exactly the size where a `3` and an `8` must stay distinguishable. Resolves AMBIGUITY 4 |
| **D9** | **Flags are a local SVG sprite with a mandatory country name**, not `flagcdn.com` images alone | Added 2026-08-03 by the same ticket. Removes a remote dependency; the name is required by `WF-027` regardless, since a flag-only cell becomes an empty cell in the PDF. Scoped to `destinations.COUNTRIES`' 32 — flag absent shows the name alone |

| **D10** | **The day-summary header is `aspect-ratio: 3/1`**, not a locked `260px` height | Added 2026-08-03 by `Prototype the itinerary day screen in the new design`, at the owner's request. The donor's CSS has a locked `260px` and **no `aspect-ratio` anywhere**; `3/1` is what its README claims. So this deviates from the donor's *code* toward the donor's *documentation* — the column rule `minmax(320px,34%) minmax(0,1fr)` is kept unchanged |

**Not deviations, decided the same day:** the webapp ships **no tile map** (the donor has no spatial element,
so there is nothing to deviate from), and the token source is **`tokens.css`** rather than the drafted JS
config, which is a format decision rather than a visual one.

**Also not a deviation:** the outbound map links (Google Maps, or Amap for mainland China) follow a pattern the
planner already uses — it redirects to TripAdvisor and Wikimedia Commons rather than faking richer content — so
they extend an existing behaviour rather than departing from the donor.

**Not deviations:**

- `.landing-wizard-side` declared twice (`index.css:156`–`162` and `:253`) — deduplicated with no visual
  change, so it is cleanup rather than a deviation.
- **Faux bold monospace** (AMBIGUITY 4) — the weight is never loaded. Deferred to `Decide the offline asset
  policy for the webapp`, as `WF-025`'s own text already assigns it.
- The **currency disagreement** in the two fallbacks — moot. That is Auto-Bill *behaviour*, and the planner
  has its own currency handling in `costs.COMMON_CURRENCIES` and `destinations.py`, so the fallback does not
  port at all.

Any future fix that is not in this register is indistinguishable from drift, and the gate must treat it as
a failure.

## 5. Radius unified on 2px

`2px` on cards, buttons, inputs and avatars versus `0.375rem`–`1rem` on charts, badges, settings and the
modal — plus `.setup-card` alone at `4px`. `WF-020` reads it as an unfinished sharp restyle and states the
source cannot say whether it was deliberate.

Unifying finishes the restyle. Sharpness *is* the signature alongside the zero-blur offset shadows, and the
contract itself names `2px` "the house radius". This dissolves **two** ambiguities at once — the rounded
layer and `.setup-card`'s lone `4px` both stop being open questions — and collapses 11 radius values to one,
which makes the allowlist trivially checkable.

Accepted: this is a real visual change rather than a bug fix. Charts, badges and the modal will read sharper
than the donor. Pill shapes stay at `9999px`, so it is one value plus one exemption, not literally one.

## 6. One colour source, read by both renderers

```
tokens (single machine-readable source)
   ├── @theme            → the webapp
   └── exporters.py      → poster PNG, trip PDF, Excel workbook
```

**This closes a parity hole nobody had noticed.** `exporters.py` hardcodes **8 distinct hex colours across
17 occurrences** — `#F2F5F7`, `#A9BECD`, `#8FB8D8`, `#2A3B49`, `#101820`, `#F2C14E`, `#E8EEF3`, `#6C8598` —
a cool blue-grey palette. Auto-Bill's is warm off-white `#FCFBF9` on near-black with a house red. So the
poster, PDF and workbook currently look like a different product, and `views/itinerary.py:94,104` adds three
more hardcoded pin hexes.

That matters more than it might: `WF-022` made the exports a **pilot-ready gate**, compared against the four
reference workbooks. They are already a checked surface — just not for colour — and they are what the owner
carries in Taipei.

The precedent is this repo's own: `WF-018` put split math in one implementation so "the screen, the workbook
and the PDF cannot disagree by a satang." Colour is the same argument.

This also resolves the palettes-as-data finding: the category and participant colours stop being duplicated
verbatim across two JSX files, and the **five undocumented tint alphas get named** rather than built by
string concatenation.

Accepted costs: 17 hexes in `exporters.py` and 3 in `views/itinerary.py` must be replaced; the Python side
gains a dependency on a token file, and that direction must stay one-way; and if `Decide which exporter
survives, Python or JavaScript` retires the Python exporters, part of this work is wasted.

## What counts as a parity failure

The gate fails on any of:

1. An **element-level** diff beyond tolerance against the donor capture, for any of the 41 lifted elements.
2. A **screen-level** diff beyond tolerance against an approved baseline, for any of the 36 route variants.
3. A **token-allowlist violation** — a raw hex, shadow, or radius not in the completed contract.
4. A **new element with no declared ancestor**, except the numbered map canvas.
5. A **deviation from the donor that is not in the register**.
6. Any of the **13 accent triples** failing to resolve.

## Prerequisites, in order

1. Complete the token contract for the 39 inline-only classes, the 114 inline sites, and the off-token
   literals. **The gate cannot run before this.**
2. Capture the 41 lifted elements from the donor — **before `Auto-Bill-Splitter` is archived**.
3. Build the token source and re-point `exporters.py` and `views/itinerary.py` at it.
4. Agree the pixel tolerance and fix the capture machine.
5. Approve the 36 screen baselines once the rebuild exists.

## What this hands downstream

| Ticket | Consequence |
|---|---|
| `Extract the Auto-Bill design token contract` | Reopens in effect: it must absorb 39 inline-only classes, 114 inline sites, and the 3 pin hexes. Its extend-vs-override pointer is moot under Tailwind v4 |
| `Decide the offline asset policy for the webapp` | Owns AMBIGUITY 4, the faux bold monospace, and now also whether the token source ships as JSON or CSS |
| `Decide which exporter survives, Python or JavaScript` | Its answer decides whether §6's Python re-tokenisation is needed at all — so it should be answered **before** that work starts |
| `Prototype the merged cost and split screen` | The `/split` surface it prototypes is the one whose layout is **inline-only in the donor**: 5 split-mode classes, 3 settlement classes, the cardholder selector. There is no stylesheet to lift from |
| `Prototype the itinerary day screen in the new design` and `Prototype the ranked candidate card grid` | Unblocked on parity: token conformance plus a declared ancestor is the rule, and the numbered map canvas is exempt |
| `Lock the Phase 2 slice plan and validation scorecard` | The five prerequisites above are sequenced work with a hard ordering constraint on step 2 |
