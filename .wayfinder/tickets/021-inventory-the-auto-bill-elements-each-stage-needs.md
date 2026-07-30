---
id: WF-021
title: Inventory the Auto-Bill elements each planner stage needs
status: closed
labels:
  - "wayfinder:research"
parent: WF-MAP-002
assignee: research-agent
blocked_by: []
---

# Inventory the Auto-Bill elements each planner stage needs

## Question

Which reusable elements does the Auto-Bill design actually contain, and which of them does each planner
stage need — where is the gap that Auto-Bill has no element for?

## Context

AFK reading work against local files, resolvable in one session. Two inventories meeting in a matrix.

Supply side — `Auto-Bill-Splitter/src`:

- `components/Dashboard.jsx` (95 KB): stat cards, filter bar by traveller / day / category, settlement
  grid, transaction list rows, hero banner with a `3 / 1` aspect ratio, main-cardholder selector, theme
  toggle, copy-memo action, import and export controls.
- `components/SetupWizard.jsx` (22 KB): multi-step wizard shell, step indicator, the split landing grid
  with a dark hero panel at `1.1fr 0.9fr` collapsing below 992 px.
- `components/TransactionModal.jsx` (27 KB): modal shell, allocation-mode picker, participant chooser,
  amount field with currency affordance.
- `lucide-react` supplies icons; `public/icons.svg` and `assets/hero.png` supply artwork.

Demand side — the eight Streamlit stages in `views/`:

- `setup.py` (511 lines, five editable steps, deliberately no `st.form`), `places.py` (400),
  `itinerary.py` (197), `revise.py` (220), `optimize.py` (156), `costs.py` (178), `readiness.py` (144),
  `evidence.py` (130). Shared row renderers and state live in `ui/shared.py` (499 lines).

Produce a matrix of stage against element, marking each cell reuse-as-is, adapt, or absent. The absent
cells matter most: the planner has a numbered map, a day timeline, an activity-and-leg schedule, ranked
candidate cards with per-card explanations, a three-variant optimizer comparison, an evidence and
provenance panel, a readiness board with deadlines and verification states, and a version history with
restore — Auto-Bill has an element for none of those. Note for each absent element whether the Auto-Bill
language extends to cover it or whether a new element must be designed inside the same visual rules.

## Resolution comments

### 2026-07-31 — Inventoried both sides

- Auto-Bill contains **45 catalogue entries — 41 renderable elements**, one utility/animation layer, one
  empty-state family (four unshared variants, no common element), one explicit absence (feedback), and
  one cross-cutting theming contract. Every entry is anchored to `index.css` and its JSX call site in
  `021-element-inventory-matrix.md`.
- **The class names are not the whole catalogue.** 18 JSX class names have zero CSS rules — including
  the entire settlement grid, settlement item, and main-cardholder selector, which are styled inline
  (113 inline `style={{…}}` sites across the three components). A token extraction that reads only
  `index.css` will silently miss the newest elements. Relevant to `Extract the Auto-Bill design token
  contract`.
- **The hero banner has no `3 / 1` aspect ratio.** `README.md:9` claims one; `aspect-ratio` appears
  nowhere in the CSS or JSX. The real rule is a locked `height/min-height/max-height: 260px` with
  `grid-template-columns: minmax(320px, 34%) minmax(0, 1fr)` (`index.css:460-484`). Port the fixed
  height, not a ratio.
- **18 planner elements have no Auto-Bill counterpart.** Of those, only **one** — the numbered map — is
  a gap the visual language cannot reach: Auto-Bill has no spatial primitive, no map dependency, and no
  analogous visual. Everything else is either an adapt of an existing element or a new element composed
  from existing parts, so the language holds.
- **The biggest design gap is the ranked candidate card**, not the map. Auto-Bill supplies parts (a
  selectable card skin, a framed insight card, a media wrapper, badges) but no card in the file exceeds
  ~120px or carries nested explanation. It is also the element the port *unlocks*: `views/places.py:147-155`
  is a selectbox plus one detail panel because Streamlit cannot lay out comparable cards. **Do not port
  the selectbox** — the card grid is the point.
- **Nearly free stages:** `costs.py` (every element exists), app-level chrome, `setup.py` shell,
  `optimize.py`. **Nearly all-new stages:** `places.py` and `itinerary.py`. `readiness.py`,
  `evidence.py` and `revise.py` are roughly half each.
- **The strongest reuse is the one nobody would look for:** the US$10 paid-usage meter
  (`app.py:81-87`, `views/evidence.py:52-63`) is a straight adapt of `.person-meter-item`
  (`index.css:1010-1050`) — a labelled bar with a percentage fill and a secondary currency line. In
  Auto-Bill it means "who owes what"; in the planner it means "how much have we spent on APIs".
- **The reverse surprise: Auto-Bill has no inline feedback element at all.** Zero toasts, zero banners,
  zero field-error components — 33 `window.alert()` and 5 `window.confirm()` stand in, and
  `.manual-validation-panel` is the only in-page success/error surface. The planner emits **59**
  `st.success/error/warning/info` calls across eight views plus `shared.py`, several of them structural
  (`require()`'s blocked panel, the flash-after-write pattern in every stage, the three-level spend
  state). A four-level banner element plus a confirm dialog must be designed from scratch.
- **Auto-Bill's step indicator hardcodes its step count in the class names** (`.wizard-progress-4`,
  `.progress-step-4`, `.step-num-4`, `.step-label-4`). The planner has five steps, so the family needs
  generalising. Two setup parts are genuinely absent: the country-dependent city picker (Auto-Bill has
  no city concept, and uses a plain 13-entry `<select>` plus a separate `isCustomCountry` boolean and a
  second text input rather than one combobox accepting a typed value), and the review step whose four
  summary rows each jump back to their own step.
- **`index.css` has no `:disabled` or `[disabled]` rule anywhere.** The planner disables a primary
  action with an explanatory caption in five places, so a disabled token is a hard prerequisite.
- **Dead weight not to port (6):** the banner-upload canvas colour extraction (~200 lines deriving a
  panel gradient from a user photo — the planner's hero content is a computed day summary); the
  reset-trip wipe button (append-only `plan_versions` triggers and dismiss-not-delete make it
  contradict a locked decision); localStorage persistence (SQLite with per-read sha256 verification is
  strictly better); `alert`/`confirm`; `.glassmorphic-card` and both `backdrop-filter` uses
  (`--glass-blur` is `0px` — all three are no-ops); and one of the two duplicated filter bars.
- **Deferred, not dead (6):** the settlement grid, copy-memo, main-cardholder selector,
  allocation-mode picker, participant chooser, and manual-split validation panel all wait on `Define
  the split ledger model and where its math lives`. `views/costs.py` records what the owner paid with
  no participants, so there is nothing to settle yet — but the traveller model already exists
  (`views/setup.py:376-418`, up to 8 members with ids, labels, ages, tags), so the participant chooser
  has a data source ready.
- **Probably dead, pending a design call:** the donut and vertical bar charts. Nothing in the planner
  charts a distribution. The only candidate is the ranking dimension breakdown
  (`views/places.py:215-227`), already a table with an explicit per-dimension maximum.
- **14 of 23 load-bearing behaviours are product decisions, not Streamlit accidents.** Must survive:
  `journey()` picking the landing stage; `require()` explaining rather than erroring; five editable
  autosaving setup steps; the country→city dependency; typed-value acceptance with city names never
  localized (localizing would change which place is searched); nothing pre-selected; explanations
  collapsed so decision buttons stay above the fold; the unscheduled panel auto-expanding on an empty
  day; map marker colours duplicated as text labels (accessibility); every paid action stating its cost
  immediately before the spending button; the actual-THB field existing only for a paid cost; disabled
  actions always saying why; deadline banners above the setup stepper; and a place always named, never
  a truncated `place_id`.
- **9 are Streamlit artifacts that die with the port**, but three leave a rule behind: `plain()`'s `$`
  escaping dies (re-verify money rendering once in HTML — the hazard is different, not absent); the
  per-language widget keys die but the rule that a label's language never changes the stored value, and
  that a typed-in option survives a switch, must keep its test; and the "word-valued state is a text
  line, never a metric" workaround dies while its rule survives as an element choice — a word gets a
  pill, a number gets a tile. The codebase learned that one three separate times
  (`views/setup.py:428-433`, `views/places.py:55-60`, `views/optimize.py:73-74`); encode it once.
- **Largest mechanical change, and it is not an element:** ~120 hardcoded English strings across the
  three Auto-Bill components (`.mode-badge`'s four emoji+word pairs, every `.stat-label`, every insight
  title, all nine table headers, all 33 alert strings) must become dict lookups. Auto-Bill has no
  code→text layer; the planner's whole UI is built on one.
- Full matrix: [`021-element-inventory-matrix.md`](../artifacts/021-element-inventory-matrix.md)
