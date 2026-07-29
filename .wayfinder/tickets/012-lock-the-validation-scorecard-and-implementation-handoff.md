---
id: WF-012
title: Lock the validation scorecard and implementation handoff
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-001
assignee:
blocked_by:
  - WF-003
  - WF-006
  - WF-009
  - WF-010
  - WF-011
---

# Lock the validation scorecard and implementation handoff

## Question

What evidence must the Taipei pilot, historic regression fixtures, source checks, optimizer results, UI prototypes, exports, privacy checks, and cost measurements retain before the decision map is complete and Phase 1 implementation may begin?

## Confirmed decisions

### 2026-07-29 — Separate permission to build from proof of a working MVP

- The decision map may close and implementation may begin when every specification ticket is closed, the regression catalog passes its structural validator, and the architecture handoff has no unresolved product decision.
- A working MVP may be claimed only after the implemented app passes every applicable hard gate below with retained evidence. Closing this ticket does not claim those runtime results already exist.
- A failed hard gate blocks the `working MVP` claim. It also blocks `Ready` or certified export status for the affected plan when the failure concerns schedule validity or required operational evidence; the owner can still inspect a clearly labelled draft and its exact failure reason.
- Preference scores can never compensate for a hard failure. Unknown required opening, access, route, or countdown evidence keeps a timetable provisional.

### 2026-07-29 — Retain one small evidence bundle per validation run

Keep each run under `artifacts/validation/<run-id>/` with a short manifest recording:

- timestamp, application and schema versions, source revision, operating system, Python version, language, configuration, deterministic seed, and fixture-catalog hash;
- input snapshot and IDs of the evidence, route, plan, and export snapshots used;
- command or owner action, pass/fail result, measured runtime, request counts, estimated paid cost, and failure details;
- only the screenshots, reports, generated files, and redacted provider diagnostics needed to reproduce the result.

Never retain secret values, passport data, booking documents, unrelated member details, restricted review text, or unrestricted raw provider payloads in a validation bundle.

## Working-MVP scorecard

| Gate | Hard pass condition | Minimum retained evidence |
|---|---|---|
| Setup and worldwide schema | Explore-first and Ready-to-schedule both work; approximate arrival/departure and an unbooked hotel remain provisional; English/Thai preserve stable values; Taipei and a destination without a local adapter use the same core schema; age alone creates no preference or mobility rule. | Saved setup snapshots and bilingual screenshots for both destinations. |
| Source and operational evidence | Every governed fact has provider/source, retrieval time, applicable date/timezone, confidence and one normalized status; unavailable/conflicting facts stay visible; the Taipei countdown keeps viewing/access/transit/closure/weather details provisional until the required 30-day, 7-day, 24-hour and applicable same-day refreshes. | Redacted provider report plus normalized evidence snapshots before and after one refresh. |
| Coverage, ranking and choice reconciliation | Broad baseline discovery runs before personalization; City Icons and one-in-five protected exploration remain visible; Browse All retains every retrieved canonical candidate; the 30/20/20/10/15/5 score and deductions are explainable; every selected item is `Fits`, `Fits with tradeoff`, or `Cannot currently fit` with reason, consequence and smallest supported alternative. | Coverage report, ordered-card snapshot, score breakdown, deduplication examples, and selection reconciliation. |
| Whole-trip optimizer validity | All three variants use the same hard constraints and snapshot; there are zero hard/lock violations, overlaps, absent required travel legs, negative slack, impossible transfers, or unapproved member thresholds; timelines are continuous; no removable A-B-A backtrack remains; every fallback is independently valid; a deterministic whole-trip result equals or improves the day-greedy baseline lexicographically. | Input/output snapshots, validation report, baseline comparison, objective breakdown and repeat-run equality check. |
| Optimizer runtime and failure mode | Initial `Best balance`, `Relaxed`, and `More highlights` target 30 seconds total; a normal accepted-plan revision targets 10 seconds. At a limit, only a labelled fully valid incumbent is returned, with an `Optimize longer` action; an invalid or partial schedule is never exposed as a plan. | Timings on the target laptop and one forced-limit run. |
| Historic regression protection | The structural catalog validator passes, then every one of the 20 atomic and 7 interaction cases satisfies all expected rules and at least one acceptable outcome through the real optimizer/validator. Tests make no network, UI, database, export, or GenAI calls. | Validator output and generic-runner result report keyed by fixture ID and catalog hash. |
| Timeline, map and phone UI | At 390 px there is no horizontal scroll; every visit, meal, rest, buffer and travel leg appears exactly once; durations/totals and all walking reconcile; map order, anchors, modes and metrics match the timeline; colour is never the sole status signal. | Phone screenshots and automated reconciliation report for the active plan. |
| Poster, PDF and Excel | The 9:16 daily poster is readable; PDF is legible with offline-critical text; Excel contains only the active plan and the six specified sheets with working formulas and reconciled costs; all outputs share plan/version, status, warning, source freshness, route, THB/destination-currency and fallback values; a changed active plan makes older exports visibly stale. | Generated poster, PDF and workbook plus export-snapshot comparison and spreadsheet recalculation results. |
| Revision assistant | English, Thai and mixed text produce validated typed operations; quick actions work without AI; model text cannot create operational facts; cross-day consequences appear before apply; apply/restore create immutable versions; all AI/error/offline/budget failure paths leave active state unchanged; normal interpretation uses at most one model call. | Redacted typed intents, before/after consequence snapshots, version history and failure-path results. |
| Checklist and privacy | Shared tasks deduplicate while traveller-specific tasks remain separate; changes preview checklist additions/removals/deadlines; stale requirements become `Verification needed`; incomplete tasks warn without hiding itinerary/exports; secrets and sensitive documents never enter SQLite, logs, prompts or exports. | Checklist change examples, readiness outputs and a redacted storage/log/prompt inspection. |
| Cost and provider failure | The local ledger reconciles calls and estimated spend; warn at US$8 and stop new paid calls at US$10 unless the owner raises the cap; staged enrichment and sparse route edges are used; quota, credentials, provider and offline failures preserve usable local planning and name evidence gaps. | Cost-ledger export, forced warning/stop results and provider-unavailable screenshots. |

## Phase 1 implementation handoff

### Current truth

- Product decisions are complete. Foundation Slice 1 provides the locked Python 3.12 project, local Streamlit entry point, application-action boundary, language-neutral core records, SQLite schema, saved-trip resume flow, and immutable active plan versions. Setup and Discovery Slice 2 adds bilingual owner/member setup drafts and a provider-neutral worldwide discovery path. Choice and Ranking Slice 3 adds deterministic personalized cards and owner choices. Whole-trip Optimization Slice 4 adds pure three-variant scheduling, independent validation, persisted previews, and evidence-gated activation.
- Route and dated operational-evidence enrichment for the live Taipei selections, itinerary output/export, checklist, revision assistant, optional paid/local enrichment adapters, and the remaining runtime scorecard rows remain unimplemented.
- Existing executable assets can inspect redacted provider capability and validate the historic regression catalog. They do not prove the runtime scorecard or guarantee provider availability.
- The Taipei pilot is 29 December 2026 through 4 January 2027 for the owner aged 26, one member aged 19, and their mother aged 50. Arrival around 17:00, departure around 11:00, transport and hotel are provisional/unbooked inputs.
- Owner style is balanced sightseeing, culture, local street food and worthwhile landmarks, with rewarding walks allowed but plain long walks, tourist traps, missed opening/best times and late ordinary meals discouraged. The 19-year-old values impressive attractions and breathtaking views without empty walking; the mother values temples, culture, nature and photography and dislikes food stops that are not worth their travel effort.
- The countdown is a fixed trip intention but its final viewing, access, closure, transit, crowd and weather instructions remain evidence-gated. The exact candidate set and seven-day timetable must be generated from then-current sources during implementation, not copied into this specification.

### Slice 1 implementation evidence — 2026-07-29

- [`pyproject.toml`](../../pyproject.toml), [`.python-version`](../../.python-version), and [`uv.lock`](../../uv.lock) resolve the locked Python 3.12 environment; the current lock selects Streamlit 1.60.0.
- [`app.py`](../../app.py) renders the local English/Thai trip-create and saved-trip resume screen through application actions. It deliberately labels the trip as a draft and does not fabricate discovery or itinerary results.
- [`travel_planner/core.py`](../../travel_planner/core.py) contains only language-neutral records and canonical snapshot validation. [`travel_planner/store.py`](../../travel_planner/store.py) makes SQLite authoritative and prevents direct update or deletion of a plan version with database triggers.
- Restoring a prior plan creates and activates a new child version. Canonical SHA-256 hashes detect stored snapshot mutation, and secret-bearing snapshot keys are rejected before persistence.
- `uv run --locked python -m unittest tests.test_foundation -v` passes three foundation tests covering reopen/resume, append/activate/restore lineage, database immutability, secret rejection, English trip creation, Thai switching, localized required-field feedback, and Streamlit rendering. The complete discovery run also passes two focused Graphify edge-preservation tests.
- A real headless `uv run --locked streamlit run app.py` server returned `ok` from `/_stcore/health`. The separate in-app visual-browser connection could not start because its environment sandbox metadata was absent, so no screenshot is claimed; official Streamlit `AppTest` interaction is retained as the UI evidence for this slice.

### Slice 2 implementation evidence — 2026-07-29

- [`app.py`](../../app.py) now saves and resumes language-neutral owner tags, optional descriptions, approximate dates/times, accommodation status, explicit `Must respect` text, and compact additional-traveller cards in English or Thai. Age is stored but creates no inferred preference, pace, walking, meal, or mobility value.
- [`travel_planner/providers.py`](../../travel_planner/providers.py) supplies one low-volume, user-triggered, bounded OpenStreetMap baseline for any destination. Its Nominatim and Overpass endpoints are replaceable by environment settings, identical requests use a seven-day local cache, and the UI shows OpenStreetMap attribution plus the broad-but-not-exhaustive warning.
- [`travel_planner/discovery.py`](../../travel_planner/discovery.py) creates stable internal place IDs, preserves provider aliases and local-script names, conservatively merges only matching names/categories within 150 metres, flags ambiguous nearby names, retains per-record evidence and leaves opening/access/best-time facts visibly unconfirmed or regular-schedule-only.
- SQLite schema version 2 adds hashed setup snapshots, fingerprinted provider cache entries, and immutable discovery runs with normalized candidates and coverage reports. Provider failure records `unavailable` or `error`; a failed refresh may reuse retained candidates only as explicitly `stale` evidence.
- `uv run --locked python -m unittest discover -s tests -p 'test_*.py' -v` passes 13 tests covering schema migration, age neutrality, setup confirmation, English/Thai value preservation, concrete OSM normalization without network, empty-response rejection, cached-boundary refresh, cache reuse, deduplication, immutable discovery evidence, and unavailable/stale provider behavior.
- A real bounded Taipei provider smoke on the current adapter retrieved the 500-record query cap, retained 494 canonical named candidates, merged six duplicates, and served an immediate identical repeat from cache. The coverage report marks the result-limit gap and does not claim exhaustive attraction coverage; no paid API was called.
- A real headless Streamlit server returned `ok` from `/_stcore/health` and HTTP 200 for `/`. Public-provider availability remains best-effort, and the tested failure path preserves the local setup without fabricating candidates.

### Slice 3 implementation evidence — 2026-07-29

- [`travel_planner/ranking.py`](../../travel_planner/ranking.py) deterministically scores every canonical candidate with the locked 30/20/20/10/15/5 dimensions and separately named deductions. Missing route, rating, best-time, or opening evidence remains neutral or visibly unconfirmed; it is never invented.
- The main queue inserts one protected-exploration card after every four ranked cards. Open-data identifiers create a separate City Icons lane, alternatives remain optional, and Browse All retains every current candidate even after the owner records a choice.
- Trip-specific group weights default to 50/25/25 for this three-person pilot, omit members without preference input and renormalize the remaining weights. Ages do not influence ranking. `Must do`, `Interested`, `Maybe`, and `Not for trip` choices persist in SQLite schema version 3 with candidate snapshots and optional rejection reasons; positive choices add a small, capped category signal without filtering other places.
- The bilingual Streamlit card shows name, local name, available open-data photo, category, score breakdown, duration estimate, evidence gaps, pros/cons, choice actions, complete Browse All, group-weight explanation, and reconciliation. Selected candidates missing from a later discovery snapshot remain visible from their stored snapshot.
- Reconciliation deliberately reports `Pending optimizer` rather than `Fits`, `Fits with tradeoff`, or `Cannot currently fit`. Route, opening-time, cross-day, and timetable feasibility become valid only in Slice 4.
- `uv run --locked python -m unittest discover -s tests -p 'test_*.py' -v` passes 17 tests. `python3 scripts/validate_regression_fixtures.py` still passes with 24 rules, 20 atomic cases, and 7 interaction cases.
- A local Streamlit `AppTest` rendered the retained 494-candidate Taipei catalog and ranking in 0.506 seconds with no exception. A real headless server returned `ok` from `/_stcore/health` and HTTP 200 for `/`; no paid API was called for this slice.

### Slice 4 implementation evidence — 2026-07-29

- [`travel_planner/optimizer.py`](../../travel_planner/optimizer.py) is a pure, provider-neutral, snapshot-in/proposal-out optimizer with no SQLite, Streamlit, provider, exporter, or GenAI imports. It produces deterministic `Best balance`, `Relaxed`, and `More highlights` variants from the same facts and hard constraints, using different supported dwell bounds and contingency buffers.
- Whole-trip insertion search can move candidates across days and positions, preserves fixed locks, prefers verified lower-effort routes, schedules inside verified opening/show/best-time windows, applies traveller thresholds before experience/travel tie-breaks, selects legal transport modes, compares unbooked hotel areas across the trip, and activates a verified indoor weather fallback by reoptimizing the day.
- The independent validator rechecks timeline continuity, overlap/negative slack, usable windows, opening/show intervals, route status, transport legality, locks, selected-item reconciliation, access evidence, walking/cycling/heat limits, and meal windows. Missing required opening, route, access, timezone, accommodation-base, or structured hard-constraint evidence cannot become `Ready`.
- Every solve retains its lexicographic objective, deterministic signature, bounded-runtime state, and deterministic day-greedy baseline. A forced-limit test exposes only a validated incumbent or an unavailable result and offers the `optimize_longer` action; it never promotes an invalid partial schedule.
- SQLite schema version 4 adds one replaceable, hash-verified optimizer preview per trip. Activation reassembles and hashes the current input to reject stale choices, accepts only a fully validated `Ready` variant, and stores the exact optimizer input and result in a new immutable active plan version.
- The bilingual Streamlit section generates or resumes a preview, recommends Minimum/Balanced/Relaxed stay length when dates are unknown, compares the three dated variants, shows load/travel/buffer metrics, warnings, the complete reconciliation and timeline, and disables activation for provisional or unavailable results.
- `uv run --locked python scripts/run_optimizer_regressions.py` passes all 20 atomic and 7 interaction fixtures through the real optimizer, three variants each, without provider, UI, database, GenAI, or paid calls. The structural fixture validator still passes 24 rules, 20 atomic fixtures, and 7 interactions.
- `uv run --locked python -m unittest discover -s tests -p 'test_*.py' -v` passes 25 tests. Coverage includes deterministic equality, lock preservation, safe-route selection, rain fallback reoptimization, independent corruption rejection, forced limits, preview persistence, stale/unverified activation blocking, Ready activation, exact-input retention, unknown-date stay recommendations, and English/Thai optimizer UI.
- A synthetic 12-place, four-day route-complete solve produced three independently valid Ready variants in 8.365 seconds on the current laptop, below the 30-second initial target, and each equalled or improved its greedy baseline. The retained 494-candidate Taipei app rendered in 0.721 seconds; a headless server returned `ok` and HTTP 200.
- The current live Taipei catalog still lacks the selected-place route snapshot, destination timezone, confirmed accommodation base, and dated official opening/access facts required for a Ready timetable. Slice 4 reports those exact gaps and refuses activation rather than inventing a subway leg, transfer time, opening hour, or usable schedule.

### Slice 5 and readiness-checklist implementation evidence — 2026-07-29

Detail and retained files live in their validation bundles under `artifacts/validation/`, per the retention rule above. Summary only here:

- Slice 5 built the shared export snapshot, the phone-first active-plan view with hotel and locked anchors and per-half-day fallbacks, the 9:16 poster, the trip PDF, and the six-sheet workbook. Every output reads one snapshot, whose totals must reconcile with the optimizer's own metrics or the export is refused.
- Phone UI gate: [`2026-07-29-slice5-phone-390`](../../artifacts/validation/2026-07-29-slice5-phone-390/manifest.json) — 390-pixel viewport, no sideways scroll.
- Poster/PDF/Excel gate: [`2026-07-29-slice5-pdf-review`](../../artifacts/validation/2026-07-29-slice5-pdf-review/manifest.json) and [`2026-07-29-slice5-excel-recalc`](../../artifacts/validation/2026-07-29-slice5-excel-recalc/manifest.json). Reading the PDF found clipped poster text and raw optimizer codes; both were fixed. The workbook recalculates correctly in Excel and in an independent engine.
- The readiness board generates city-independent tasks, previews additions, removals, and deadline moves, dismisses rather than deletes, and summarizes as Ready, Action needed, or Verification needed without ever gating the itinerary. No provider supplies official entry rules, so an item names what to verify and stays `verification_needed` until the owner records an official source. Generated wording follows the selected language through template codes.
- Checklist gate: [`2026-07-29-checklist-board-390`](../../artifacts/validation/2026-07-29-checklist-board-390/manifest.json).
- Still open. Costs stay headers-only until a provider supplies fare or ticket evidence. Destination-specific requirements, transit-country tasks, and the mandatory 30-day, 7-day, and 24-hour verification runs need official sources no configured provider supplies. `st.map` draws no basemap offline.

### Smallest build order

1. **Foundation:** one Python 3.12/Streamlit project, SQLite schema, environment settings, stable domain records, immutable snapshot/version storage, and no extra web service.
2. **Setup and discovery:** bilingual setup/drafts, traveller cards, worldwide provider adapters and cache, evidence ledger, broad candidate discovery, deduplication and coverage report.
3. **Choice and ranking:** card lanes, transparent scoring, pros/cons, owner actions, protected exploration and complete selection reconciliation.
4. **Optimization:** pure snapshot-in/proposal-out whole-trip solver, deterministic validator, greedy baseline, three variants, fallback activation, generic execution of the historic catalog, and runtime limits.
5. **Use and export:** active-plan timeline/map, posters, PDF, six-sheet Excel, THB plus destination currency, readiness checklist and stale-export handling from one export snapshot.
6. **Revision and acceptance:** non-AI quick actions first, constrained optional GenAI intent parsing, immutable apply/restore, then the live Taipei pilot and every scorecard gate.

Complete each slice vertically with its smallest runnable check before starting the next. Do not add FastAPI, React, Docker, Redis, workers, remote collaboration, or hosted notification infrastructure in Phase 1.

### Definition of done

Phase 1 is done only when:

- `uv run streamlit run app.py` launches the local app from a locked environment and can resume a saved trip;
- the owner can set up, discover, compare, select and reconcile candidates, then generate and activate a valid Taipei plan from live/fresh-enough normalized evidence;
- the active plan has the three valid variants or a precise unavailable reason, survives all historic regressions, and can be revised without silently breaking locks or other days;
- the phone UI, poster, PDF, active-plan Excel and checklist agree through one immutable export snapshot;
- all hard scorecard rows pass, their evidence bundle contains no secret or prohibited sensitive data, and paid usage remains within the confirmed cap.

## Specification checkpoint evidence

- `python3 scripts/validate_regression_fixtures.py` passes with 24 rules, 20 atomic cases and 7 interaction cases.
- All dependent Wayfinder tickets are closed and their decisions are linked from the map.
- `python3 scripts/build_project_graph.py --check` passes; the multigraph diagnostic reports zero dangling endpoints, self-loops, duplicate edges, or same-endpoint collapses.
- `python3 scripts/check_provider_access.py --self-test` passes without exposing a secret. A 2026-07-29 no-paid-call capability check found openrouteservice reachable and the Google/OpenAI keys configured, while Open-Meteo returned HTTP 503 and public Overpass returned HTTP 504. This is retained as an expected provider-unavailable implementation case, not misreported as current verified evidence.

## Resolution

The validation boundary and minimal implementation order are fully decided. Phase 1 implementation may begin, but the project must remain described as an implementation-ready specification—not a working MVP—until the runtime scorecard passes with retained evidence.
