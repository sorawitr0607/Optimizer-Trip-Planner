# Slice 4 — places and itinerary

Built 2026-08-04. Numbers are in `manifest.json`. This implements the S4 row in
`.wayfinder/artifacts/033-phase-2-slice-plan-and-scorecard.md`; the exact browser witness remains open
because the in-app connector was unavailable, and this bundle does not pretend otherwise.

## Outcome

The two expensive journey stubs are now real React screens. `places` covers free discovery, source and
coverage reporting, the functional ranked-list scope, persistent choices, bilingual explanations and an
owner-triggered live overlay whose paid estimate sits immediately before the button. `itinerary` reads the
shared export snapshot and renders all six row types, half-day fallbacks, day totals, readiness gaps, a
tile-free true-relative coordinate map, a duplicated textual stop list, and the workbook/calendar downloads.

No ranking, optimizer, evidence, export or storage rule changed. No runtime dependency was added. The full
ranked candidate card grid remains deferred by the locked scorecard; one functional selected-card surface is
the smallest S4 implementation that serves the pilot.

## S3 check before S4

S3 is valid. Its 19 targeted Python behaviours, the real Taipei setup fixed-point round-trip, activation
gate, 21 web tests and all eight repository stages passed before S4 work began.

One presentation defect was real: `OptimizePage` sent refusal codes through `copy()`, which reads `TEXT`,
while the refusal prose lives in `OPTIMIZER_CODE_TEXT`. Activation still refused correctly and wrote nothing,
but the user would see the visible unknown-code fallback rather than the existing bilingual reason. The fix is
the one shared lookup change to `copyFrom("OPTIMIZER_CODE_TEXT", ...)`; no domain or stored state changed.

## The real Taipei gate

The repository database was copied to `/private/tmp` and opened there. The original
`data/tourist.sqlite3` was not migrated or written. The production server then exercised the saved real
Taipei record with no network or paid call:

1. Cached, verified OpenStreetMap discovery returned 832 candidates, 6 merged duplicates and 9 populated
   geographic cells.
2. Ranking returned 832 cards, with 525 in the main queue and 4 persisted considered choices.
3. Optimization produced `best_balance`, `relaxed` and `more_highlights`; all three were valid provisional
   variants with 4 scheduled visits and all six operational row types.
4. `best_balance` activated as a new immutable plan version. Journey then reported all five gated stages done
   and `itinerary` as the attention stage.
5. The shared snapshot contained 8 days, 69 rows, 13 readiness items and the expected visible capability
   gaps: accommodation still unconfirmed and opening evidence missing.
6. The 23,571-byte workbook passed its ZIP integrity test. The 5,073-byte calendar began with
   `BEGIN:VCALENDAR`.

The production route shell also served the itinerary deep link and its hashed JS/CSS assets. The automated
socket test keeps the same transport path deterministic by preparing discovery and route evidence with the
existing fake providers; it does not claim that the still-stubbed evidence screen is implemented.

## Runnable proof

`uv run --locked python scripts/check.py` passed all eight stages in 19.2 seconds:

- 312 Python tests, up from 306 at S3.
- All 27 historic optimizer regressions and the fixture catalogue.
- Graph integrity at 1,358 nodes and 3,185 directed edges.
- Provider redaction self-test.
- Web typecheck, lint and 26 web tests, up from 21 at S3.

The production web build transformed 1,903 modules. The final assets are 30.14 kB CSS and 484.00 kB JS
(142.04 kB gzip). Five focused web tests cover both languages, the paid-cost preflight, all six row types,
fallback placement, downloads, coordinate geometry and the textual stop-status duplicate. Five additional
portable behaviours now live below Streamlit, leaving four on the S6 deletion checklist. No `AppTest` original
was deleted.

## What remains explicit

- **Visual witness/captures:** the in-app browser connector rejected its session metadata (`sandboxPolicy`
  was missing), so no S4 screen image is retained. SSR render tests, the production build, production server
  transport and real export files passed; a browser walk and captures still need to be added when the connector
  is available.
- **Fresh-trip route evidence:** S4's locked gate is the saved real Taipei trip, which already has route
  evidence. A newly created trip cannot yet acquire that evidence through the React UI because `evidence`
  remains a stub. Do not weaken the optimizer's route-evidence hard constraint to disguise that missing
  surface.
- **Ranked card grid:** intentionally deferred past the pilot. The functional lane/card list is the S4 scope.
- **Graph snapshot:** `--check` passes, but the paid Graphify rebuild was not requested, so the checked-in graph
  does not include the new S4 screens.
