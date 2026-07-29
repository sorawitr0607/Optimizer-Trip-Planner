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

### Slice 5 partial implementation evidence — 2026-07-29

This records the use-and-export work that exists; it does not claim Slice 5 is complete. The costs and readiness-checklist parts remain open, and two acceptance checks remain unverified, both named below.

- [`travel_planner/exports.py`](../../travel_planner/exports.py) builds one immutable, hash-stamped export snapshot from the exact active plan version, with no Streamlit, SQLite, provider, exporter, or GenAI imports. It recomputes every day and trip total from the timeline items and refuses to publish a snapshot whose totals disagree with the optimizer's own metrics, so the app, poster, PDF, and workbook cannot report different numbers.
- The snapshot carries the five agreed output states per item (`Confirmed`, `Recheck`, `Tradeoff accepted`, `Unverified / conflict`, `Locked`), numbered map stops that follow timeline visit order, plain versus rewarding walking, the localized reconciliation, the unscheduled shortlist with reason and consequence, evidence sources, the resolved hotel-area anchor, and every fallback located to the day and half-day its replacement actually runs in.
- [`travel_planner/exporters.py`](../../travel_planner/exporters.py) writes the 1080×1920 daily poster PNG, the trip PDF (cover and readiness, one section per day with poster, timeline, and day overview, unscheduled choices, checklist placeholder, source appendix), and the six agreed Excel sheets with frozen headers, autofilters, bounded widths, a daily walking-versus-travel chart, and `SUMIFS`/`COUNTIFS` formulas over `Timeline` that also store their computed values. `Timeline` keeps separate English, Thai, and local-name columns, so switching the interface language cannot rewrite identity.
- Poster and PDF text resolves a Unicode font through `TOURIST_EXPORT_FONT` and then a candidate list, and raises a precise error rather than rendering unreadable glyphs. Interface status labels carry emoji that no such font provides, so the exporters strip pictographs and keep the wording, which preserves the rule that colour or icon is never the only status signal.
- The bilingual Streamlit `Active plan` section renders the day summary, the chronological timeline grouped by half-day with each fallback beneath its own half-day, the numbered map with the hotel area and locked stops distinguished by colour and by wording, the superseded-plan warning, and poster/PDF/Excel downloads cached per snapshot hash and language.
- `_optimizer_input` now translates the accommodation vocabulary: setup stores `not_booked` while the optimizer and the frozen fixtures test for `unbooked`. Before this, `hotel_recommendation` was always absent for an app-created trip, so no hotel anchor could ever appear.
- `uv run --locked python -m unittest discover -s tests -p 'test_*.py' -v` passes 45 tests. New coverage includes totals reconciliation against optimizer metrics, one appearance per item in chronological order, stop numbering versus timeline order, English/Thai display text without moving times or identities, refusal of mismatched totals, superseded-version staleness, poster geometry, PDF page structure, the six sheets with chart and autofilter, formula-to-column agreement, tri-lingual name columns, pictograph stripping, missing-font error, fallback half-day placement, hotel-anchor resolution, and the accommodation vocabulary translation.
- The 390-pixel acceptance check was measured in Chrome, not asserted. Against a seeded two-day plan carrying long Thai, Chinese, and English place names and full addresses, a 390-pixel viewport reported `clientWidth` 390, `documentElement.scrollWidth` 390, and no sideways page scroll, with the map canvas mounted at 347 pixels and the expanders open. The only elements wider than the viewport are the data grid's own scroll layers, which contain no text and scroll inside the widget. Retained: [`slice5-phone-390-timeline.png`](../evidence/slice5-phone-390-timeline.png) and [`slice5-phone-390-map.png`](../evidence/slice5-phone-390-map.png).
- Still open in this slice. `Costs` is headers-only and the exchange-rate snapshot is null because no configured provider supplies fare or ticket evidence; converting absent amounts would invent them. The readiness checklist stays with its own ticket, and the `Checklist` sheet exists with the agreed columns so the workbook contract does not move when it lands. Fallback records carry trigger, swap, re-optimization state, and displaced selection, but no decision deadline or route/cost/walking deltas, because the optimizer does not produce them.
- The PDF was rendered and read page by page in both languages, at A4 100 dpi, for a two-day plan carrying long Thai, Chinese, and English names. Five pages: cover and readiness, one page per day holding its poster, timeline, and day overview together, unscheduled choices, then checklist and sources. Text is real extractable text rather than pictures of text, local-script names survive, and each day stays inside one section. Retained: [`slice5-pdf-th-day-page.png`](../evidence/slice5-pdf-th-day-page.png) and [`slice5-pdf-th-unscheduled-page.png`](../evidence/slice5-pdf-th-unscheduled-page.png).
- Reading it found two defects, both fixed. Pillow draws whatever it is given, so long place names ran off the poster canvas and were clipped, by 78 pixels in English and 162 in Thai; poster text now wraps to the available width, ellipsizes visibly when it must, breaks on spaces where they exist, and refuses to strand a Thai combining mark at the start of a line. The PDF also printed raw optimizer codes such as `PLAIN_WALK_THRESHOLD` where the app shows localized wording, so exporters now resolve codes through the same table the app passes them, which restores the rule that labels agree across app, poster, PDF, and Excel. Retained: [`slice5-poster-th-wrapped.png`](../evidence/slice5-poster-th-wrapped.png).
- The workbook was recalculated in Microsoft Excel and, independently, in the `formulas` engine. Both produce exactly the snapshot's numbers. For the eight-item Tokyo plan: Visits 3, At places 225, Travel 45, Walking 45, Buffers 240, with the trip-total row equal to the single day row; for the two-day Dali plan: 1/0/10/10/0 per day and 2/0/20/20/0 as the trip total. No cell evaluates to an error.
- Excel also confirmed the formulas are live rather than reading back stored values. Raising one visit's duration by 100 moved `At places` from 225 to 325 and left `Travel` at 45; raising one travel leg by 100 moved `Travel` to 145 and left `At places` at 225; adding 7 walking minutes moved `Walking` to 52; blanking one row's type dropped `Visits` from 3 to 2. Every value returned to 225/45/45/240/3 when the inputs were restored, and the workbook was closed without saving. Formulas exist only on `Summary`, each carries a cached value, and no other sheet can therefore error.
- Structure matches the sheet contract: the six agreed sheets in order, `Timeline` frozen below its header with an autofilter across all 22 columns and one row per exported item, `Choices & Backups` and `Sources` likewise filtered, no column wider than 40 characters, and one titled daily walking-versus-travel chart on `Summary`.
- Two small notes rather than defects. `Checklist` and `Costs` carry frozen headers but no autofilter because they hold no rows yet; whichever slice fills them should add one. Excel allows a single autofilter per sheet, so on `Choices & Backups` the filter covers the reconciliation table and the linked-fallback block below it sits outside that range.
- The rendered workbook was also inspected on screen in Excel. `Summary` shows the fact block, the per-day KPI table, and the titled `Daily walking and travel load` column chart with a text legend for both series, so colour is not its only signal. `Timeline` shows a filter control on each of the 22 headers, a frozen header row, and one row per item in chronological order with stop numbers only on visits. Retained: [`slice5-excel-summary-chart.png`](../evidence/slice5-excel-summary-chart.png) and [`slice5-excel-timeline-filters.png`](../evidence/slice5-excel-timeline-filters.png).
- Unverified acceptance checks. `st.map` draws its basemap from an external tile provider, so the day overview renders its canvas and controls but no basemap without network access. Thai consequence codes such as `kept_in_unscheduled_shortlist` have no entry in the interface code table, so app and PDF agree but both fall back to prettified English wording.

### Readiness checklist implementation evidence — 2026-07-29

The board from the readiness ticket, generated and editable, plus its outputs. Costs remain out of scope here.

- [`travel_planner/checklist.py`](../../travel_planner/checklist.py) generates a city-independent board from destination, dates, travellers, accommodation state, and selected places, with no Streamlit, SQLite, provider, exporter, or model imports. No configured provider supplies official entry rules, so nothing asserts a legal conclusion: a generated item names what to verify and which kind of authority can support it, and stays `verification_needed` with no source URL until the owner records one. Requirement level is a planning attribute and evidence state a provenance attribute; `validate_item` refuses a verified `required` item with no responsible authority type, and refuses `Not applicable` without a reason.
- Timing is the primary grouping and resolves against the trip start: `do_now` carries no date, then 30-day, 7-day, 24-hour, and departure-day milestones. Entry-requirement items stay shared when nationalities match or are unknown and split per nationality when they differ; other tasks stay shared either way. A selected place with verified show, queue, or crowd evidence raises its booking task from recommended to required. Setup gained an optional nationality per traveller, which generation needs; passport numbers stay out.
- Changes are previewed, never applied silently: `diff_proposal` reports additions, removals, and deadline moves, and applying a removal dismisses the row rather than deleting it, so a generated requirement stays visible in history. Schema 5 adds `checklist_items`, the one mutable record type, hash-verified on read like every other snapshot.
- Readiness summarizes as `Ready`, `Action needed`, or `Verification needed`, surfaces overdue and due-soon work, flags a verified item that passed a refresh point since its last check, and sets `blocks_itinerary` false so warnings never gate the itinerary or its exports.
- One export snapshot carries the board to every output. The workbook `Checklist` sheet holds the agreed columns with one row per item plus dismissed history and an autofilter; the PDF carries a cover summary line and an appendix grouped by timing with level, progress, evidence state, deadline, consequence, and source; each daily poster shows only the tasks due on its own day; and `checklist_ics` writes all-day calendar entries for every dated task.
- The calendar file was validated by the `icalendar` parser, not only by reading it: ten events, unique UIDs, all-day `DTSTART`/`DTEND` spanning one day, descriptions unfolding into separate lines, and a summary containing literal commas round-tripping correctly, which proves the RFC 5545 escaping and the 75-octet folding.
- `uv run --locked python -m unittest discover -s tests -p 'test_*.py' -v` passes 74 tests. New coverage includes generic generation with no invented rule, nationality dedup and split, milestone resolution, booking-task escalation, preview additions/removals/deadline changes, dismissal not reappearing as a removal, the three readiness states, refresh-point staleness, every contract violation, idempotent apply across a reopen, owner edits with history, tamper detection, the workbook sheet, the PDF appendix, per-day poster tasks, `.ics` structure and escaping, and a guard that every directly indexed export label has a default.
- The board was measured at a 390-pixel viewport in Chrome with all five timing groups, 31 selectboxes, and 83 controls rendered: `clientWidth` 390, `documentElement.scrollWidth` 390, no sideways page scroll, and zero elements past the right edge.
- Generated task wording now follows the selected language. Each template carries a code and its format arguments, the way optimizer reasons do, and the app, poster, PDF, workbook, and calendar resolve it through the same label table; a missing or mistyped entry falls back to the stored English rather than losing the wording. Applying a proposal also refreshes template-derived fields on items saved earlier while preserving owner progress, note, evidence, source, authority, and dismissal, so a template change or a new language reaches a board that was applied before it existed. Verified by reading the Thai appendix, workbook, and calendar.
- Still open. Destination-specific requirements, transit-country tasks, and the mandatory 30-day, 7-day, and 24-hour verification runs need official sources that no configured provider supplies, so the board can only prompt for them.

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
