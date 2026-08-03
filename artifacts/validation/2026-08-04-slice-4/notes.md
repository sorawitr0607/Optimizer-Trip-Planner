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

## The browser witness, obtained 2026-08-04

**This closes the item the rest of this bundle recorded as owed.** The connector became available, so the
walk was driven in a real browser against a fresh copy of `data/tourist.sqlite3`. Six captures are retained
in `captures/`.

The copy was served on port 8801 and **the original was never opened**: it is still at schema 12 while the
copy bumped to 13 and left `s4-pre-v13-2026-08-04.sqlite3` at 12 beside it. That is S2's refuse-on-failure
migration path running against real pilot content for the first time — S2 only ever exercised it on a
synthetic fixture.

**A reproduction note this bundle should have carried from the start.** The numbers above are not in the
committed database. Opening `data/tourist.sqlite3` as-is gives a sparser stored plan — 7 days, 8 rows, three
row types, no readiness items. The 8 days / 69 rows / 13 readiness items / six row types come from *re-running*
steps 3 to 5, which activates a new plan version and applies a readiness proposal. Those steps are listed
above, so nothing here was overstated, but a reader who only opened the database would have thought the
figures were wrong. Re-running them reproduced every figure exactly: three provisional valid variants at 4
scheduled visits, 8 days, 69 rows, all six row types, 13 readiness items.

What the captures show, each against the rule it has to satisfy:

| Capture | What it witnesses |
|---|---|
| `places-coverage-and-lane-en-light.jpg` | 832 candidates, 6 merged duplicates, 9 geographic cells, provider `Verified`, the 525-card lane, ODbL attribution as a link (element 22), and the two raw-report disclosures |
| `places-card-paid-preflight-en-light.jpg` | Element 16 — "estimated maximum US$0.075" sits immediately above the spending button. Element 14 — the rejection reason is inside the *Not for trip* disclosure, not above the three plain choices. Element 12 — explanations collapsed so the choices stay above the fold. Element 21 — `Liufenshan · 六分山` |
| `itinerary-day-totals-en-light.jpg` | The one-snapshot banner, the evidence-gap disclosure, day totals across all eight metrics, and the highest-risk line |
| `itinerary-row-types-en-light.jpg` | Stop, travel, buffer and meal rows with state carried **in words** (`⚠️ Unverified / conflict`, `✅ Confirmed`), never colour alone |
| `itinerary-map-and-stop-list-en-light.jpg` | Artifact 034 — a tile-free numbered map, no network. Element 15 — the textual stop list repeats every marker's meaning with coordinates, so a prettier map could not drop it. Marker geometry matches the real longitudes |
| `itinerary-th-light.jpg` | The same screen fully in Thai, including day totals, the risk line, tabs and map |

The paid button was deliberately **not** pressed: it spends real money and needs credentials, and nothing in
this gate requires it.

The `GET` download contract was verified over the socket rather than inferred. Both routes answer 200 with
server-side filenames — `Taipei-Taiwan-plan.xlsx` (23,574 bytes, valid ZIP, 7 worksheets) and
`Taipei-Taiwan-readiness.ics` (5,073 bytes, `BEGIN:VCALENDAR`) — and **a bare `GET` to `/api/delete_trip`
returns 404**, so `WF-030`'s "downloads and nothing else" rule holds. *(The workbook is 23,574 bytes here
against 23,571 in the run above; the plan version id inside the file differs per run, so that figure is
run-dependent rather than a fixed expectation.)*

One behaviour worth recording because it first looked like a defect: the itinerary opens on the trip's first
day, which schedules nothing, and offers only the workbook until readiness items exist. Both are correct —
the empty day states "No visit is scheduled on this day; choose another day or a denser variant", and the
`.ics` button appears as soon as the readiness board is generated.

## What remains explicit
- **Fresh-trip route evidence:** S4's locked gate is the saved real Taipei trip, which already has route
  evidence. A newly created trip cannot yet acquire that evidence through the React UI because `evidence`
  remains a stub. Do not weaken the optimizer's route-evidence hard constraint to disguise that missing
  surface.
- **Ranked card grid:** intentionally deferred past the pilot. The functional lane/card list is the S4 scope.
- **Graph snapshot:** `--check` passes, but the paid Graphify rebuild was not requested, so the checked-in graph
  does not include the new S4 screens.
