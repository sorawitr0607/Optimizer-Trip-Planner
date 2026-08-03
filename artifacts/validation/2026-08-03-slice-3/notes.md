# Slice 3 — the cheap journey screens

Built 2026-08-03. Numbers are in `manifest.json`; this file carries the narrative and the decisions
taken while building. Closes the S3 row of
`.wayfinder/artifacts/033-phase-2-slice-plan-and-scorecard.md`.

## Post-closure check — 2026-08-04

S3 remains valid: its 19 targeted Python behaviours, the real Taipei setup fixed-point round-trip,
activation gate, 21 web tests and all eight repository stages passed before S4 work began. The review
did find one presentation defect: `OptimizePage` looked refusal codes up in `TEXT`, although their Thai
and English prose lives in `OPTIMIZER_CODE_TEXT`. S4 corrected that shared lookup and the full gate then
passed at 312 Python and 26 web tests. No S3 domain behaviour or stored data changed.

## The three closing checks

| Check | Where it lives |
|---|---|
| The real Taipei trip's setup round-trips whole | `test_the_real_taipei_trip_round_trips_whole` |
| A variant activates and refuses on a stale hash | `ActivationGateTest` — 4 tests |
| 3 of the ported `AppTest` behaviours pass at actions level | `tests/test_ported_behaviours.py` — 19 tests |

306 Python and 21 web tests. No paid call, no new runtime dependency, and **no new copy keys** — every
string both screens need already existed in the catalogue, which is exactly what `WF-027`'s
one-catalogue decision was for.

## A correction to artifact 029's count

Artifact 029 lists **14** behaviours portable down to actions / core / exports. Checking each against
its current test body, **two were already there**:

- `preview_is_persisted_but_unverified_inputs_cannot_activate` (`tests/test_optimizer.py`) never used
  `AppTest`.
- `a_destination_outside_the_picker_still_creates_a_trip` (`tests/test_setup_discovery.py`) only
  *mentions* `AppTest`, in a docstring explaining why it cannot drive a typed value through a
  selectbox.

So **12 were outstanding, not 14**, and 9 remain after S3. `tests/test_ported_behaviours.py` is
organised by provenance rather than by domain on purpose: it is the checklist S6 reads before deleting
`views/`, and its module docstring names what is still owed and which slice each item waits on.

The three ported here are the ones whose surfaces S3 builds — the five-step setup screen and the
sidebar trip selector. No `AppTest` original was deleted; that happens at S6, as `WF-022` set out.

## Setup: one draft, sent whole, or fields disappear

`save_setup` defaults every field to empty, so a payload that omits one **erases it**. That is why the
five steps are five views over one piece of state rather than five requests, and it is the whole
reason artifact 028 refused to split the route.

`test_the_real_taipei_trip_round_trips_whole` pins it with a fixed-point assertion: save a complete
draft, read it back, save what was read, and the snapshot hash must not move. That is the property the
screen depends on every time it reloads a draft it did not just write.

**Two fields the POC drops, which this port keeps.** `views/setup.py`'s `_edited_values` omits
`owner_nationality` and each member's `nationality`, so saving through the POC erases them. Readiness
generation reads nationality, so a round-trip that loses it is not "round-tripping whole". The React
draft carries both, and the test asserts them.

## Decisions taken while building

- **The step indicator is generalised, not renamed.** The donor's family hardcodes four steps
  (`.wizard-progress-4`, `.progress-step-4`, `.step-num-4`, `.step-label-4`). Renaming to `-5` would
  hardcode the next wrong number, so the CSS is step-count-agnostic and the grid takes its column
  count from one rule.
- **Clicking a step navigates backwards only**, kept rather than "fixed": later steps depend on
  earlier answers. Verified live — a forward jump from step 1 to step 5 is refused and the step index
  does not move.
- **The step index is not persisted across a refresh**, which artifact 028 lists as an accepted cost.
- **`setup_vocabulary` is one new allowlisted read** (57 methods now). React needed the country/city
  table from `destinations.py` and the four tag groups from `setup.py`, neither of which was reachable.
  Both language labels ship in one payload so a language switch never refetches — a refetch is a chance
  for a stored value to move, and switching language must never change one.
- **The picker orders are explicit, not set-derived.** `PLANNING_MODES` and `ACCOMMODATION_STATUSES`
  are frozensets, which is right for validation and useless for a radio group: a form would get an
  arbitrary order on every run. The lists are ordered by meaning — planning mode leads with the less
  committed option, accommodation runs least to most certain — and asserted against the core sets so a
  new member cannot be added there and silently miss the form.
- **`MAX_MEMBERS` was not added to the core.** The cap of 8 is a POC view convention
  (`views/setup.py:389`); `setup.py` accepts any number. Advertising it through the API would imply an
  enforcement that does not exist, so the screen caps and says so in a comment.
- **`LanguageProvider` gained an optional `initial` prop.** There was no way to render a Thai screen in
  a test, and both closing checks touch bilingual rendering. Default unchanged, no caller touched.
- **`copyFrom` covers the seven non-`TEXT` tables.** The optimize screen renders
  `OPTIMIZER_CODE_TEXT` and setup renders `TAG_TEXT` / `ACCOMMODATION_TEXT`; there was only a `TEXT`
  lookup before. Unknown codes still surface as `⚠ CODE` rather than being prettified into prose.

## Three defects the live walk caught

None of these were visible in the tests; all three needed a browser.

1. **Checkbox labels stacked above their checkboxes.** `.setup-fields > label` (one class, one element)
   out-specifies `.setup-check` (one class), so the column direction won. Fixed by matching on
   `.setup-fields > .setup-check`.
2. **The review step reported a label against a label** — literally "Mode: Status" — because I left a
   placeholder pair in. It now shows the trip's real `planning_mode` and its confirmation state.
3. **The save flash stored rendered text**, so switching language mid-flash left an English "Draft
   saved." above a Thai screen. It now holds a code and resolves at display time, like every other
   string.

## What the live walk did and did not reach

Walked on a scratch database, never `data/tourist.sqlite3`: all five steps, the draft-saved flash, a
step-2 tag change surviving through steps 3 and 4 into the review, the blocked forward jump, the trip
selector showing `Taipei / Taipei, Taiwan`, and the review in both languages.

**The accent is now teal.** `tokens.css` has carried the country-to-accent mapping (D6) since S1 but
nothing set the attribute; `AppShell` now derives it from the destination's country. An unknown country
matches no rule and keeps the house red, which is D3, so it needs no validation against the mapping.

Two things were **not** reached, recorded rather than glossed:

- **The optimize screen was not seen live.** The scratch trip has no candidate choices, so `StageGate`
  correctly blocks `/optimize` on Places — S1 behaviour working as designed. Its proof is the render
  test, which drives a full provisional variant with metrics, warnings, reconciliation and timeline in
  both languages, plus `ActivationGateTest` for the gate itself.
- **The phone collapse has no screenshot.** The harness could not take the page viewport below 992px
  (1347px was the floor), so the media query never activated. Verified in the live DOM instead: the
  toggle computes to `display: none` above 992px, the sidebar to `flex`, both 992px rules are present
  in the stylesheet, and clicking the toggle does flip `aria-expanded` and the `open` class. **This is
  the one element artifact 028 explicitly left undesigned**, so it is a new element for `WF-025`: it
  declares element 17 `.sidebar` as its ancestor, uses tokens only, and should be captured on a real
  phone before the parity gate runs.

## Still owed

- **9 ported behaviours**, each waiting on the slice that builds its screen — the checklist board pair,
  the two export-render tests plus the fallback block, the ranking choice, the revision section, the
  provisional-plan case, and the cost section. The module docstring in
  `tests/test_ported_behaviours.py` is the live list.
- **The graph was not rebuilt.** `--check` passes at 1358 nodes and 3185 directed edges, so the gate is
  green, but it does not know about the three new screens. Paid, and reserved for an explicit ask.
- **`data/tourist.sqlite3` is still at schema 12**, unchanged by this slice. It bumps to 13 on first
  real open, writing its pre-bump copy first or refusing.
- **The `Auto-Bill-Splitter` pre-archive debt**: one backup JSON per trip and the 41 isolated element
  captures. Unchanged by this slice and still lost once the donor is archived.
