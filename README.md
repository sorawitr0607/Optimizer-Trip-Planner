# Optimizer Trip Planner

Personal, evidence-aware trip planning. The planning core builds and revises a
timetable from traveler preferences, attraction choices, opening hours, travel
time, and pacing constraints.

A Streamlit app was the **proof of concept** that established the core works —
not the product. Phase 2 replaced it with a local React webapp that also absorbs
`Auto-Bill-Splitter` as a group split ledger. The planning core, `actions.py`,
and `store.py` remain the domain boundary. **`views/`, `app.py` and `ui/` were
deleted at slice S6 on 2026-08-04**, once the webapp reached parity across all
nine routes; there is one runnable surface now.

## Release status

This repository is a **local, single-owner personal-planning pilot**, not an Internet-facing
service. Its local server, SQLite file and credential model must not be exposed directly to public
traffic. When the owner chooses a hosted release, follow [the public release improvement
plan](PUBLIC_RELEASE_PLAN.md); it covers the production trust boundary, privacy, human accessibility
and Thai review, field performance, operations and an invite-only beta gate.

## Run locally

```bash
npm --prefix web install             # first run only
uv run --locked python -m api        # http://127.0.0.1:8765
```

**All nine routes are real screens**: **setup** (five steps), **places**, **evidence**, **optimize**,
**itinerary**, **readiness**, **costs**, **split** and **revise**. A saved trip runs end to end — discovery,
ranking, evidence, activation, readiness, costs, split and workbook/calendar export.

### The map

Every place, day and route is drawn on a real map. **Online it is OpenStreetMap's own tiles** — the same
images `openstreetmap.org` serves. **Offline it draws itself** from data already on disk: land use, water,
parks, building footprints, the road hierarchy with street names, rail, and station entrances, all from one
free Overpass request per window. It falls back the moment a tile fails to load, so the plan still works on
a plane, and it says which of the two you are looking at.

Zoom out far enough and the destination country's own outline appears, so a place can be seen in its
country rather than only its city. `/itinerary` opens on the map, drawing the day's stops in order along
the walk actually taken, and every stop hands off to the phone's own map for the last fifty metres.

This reverses `WF-034` §3, which ruled out tiles to protect the app's premise of a plane and a hotel with
no usable network. The revision is recorded in that artifact with its reasoning: tiles are a layer over the
offline map, never instead of it. `© OpenStreetMap contributors` is shown beside every map, which the ODbL
requires of the geometry as well.

The app uses `data/tourist.sqlite3` by default. Copy `secrets.example.json` to
`secrets.local.json` for optional provider configuration; never commit local secrets.

> **The database is at schema 14**, bumped on 2026-08-07 for `WF-039`'s comfort acceptances.
> `data/tourist-pre-v14-2026-08-07.sqlite3` holds the pre-bump file at version 13 and is the only way
> back — there is no downgrade path by decision. Any bump copies the file first and refuses to migrate if
> that copy fails. No schema change is permitted between 29 December 2026 and 4 January 2027: those are the
> trip's own dates.

## Repository map

- `PUBLIC_RELEASE_PLAN.md` — the deferred build and evidence gates for a future hosted public service.
- `api/` — stdlib localhost transport and the local webapp entry point.
- `web/` — React, TypeScript, Tailwind, route shell, and stage gates.
- `i18n/copy.json` and `tokens.css` — copy and design truth shared across renderers.
- `travel_planner/` — planner domain logic, storage, providers, ranking, and optimization.
- `travel_planner/exporters.py` — snapshot-in, bytes-out writers: the six-sheet Excel workbook and the
  readiness ICS. The 9:16 poster and the trip PDF were dropped in slice S0, and with them the export-font
  requirement.
- `travel_planner/climate.py` and `travel_planner/areas.py` — pure modules, like the rest of the core:
  which months suit a destination, and which station neighbourhood to stay in.
- `web/src/stages/PlaceMap.tsx` and `web/src/shared/tiles.ts` — the one map component every screen draws,
  and the tile arithmetic behind it.
- `travel_planner/destinations.py` — the country/city picker table. A convenience only: both
  dropdowns accept a typed value, so any worldwide destination still works.
- `tests/` — deterministic unit tests; historic trip regressions are in `tests/fixtures/`.
  `tests/test_ported_behaviours.py` is organised by provenance rather than domain on purpose: it holds
  the actions-level homes for the 14 behaviours that used to be asserted through Streamlit `AppTest`, and
  it was the checklist read before deleting `views/`.
- `artifacts/parity/` — the donor style capture and 56 approved screen baselines (36 desktop plus 20 phone) with their README.
- `scripts/` — validation, regression, provider, and Graphify maintenance commands.
- `data/reference-itineraries/<city>/` — source workbooks and PDF itineraries.
- `graphify-out/` — checked-in graph snapshot; generated caches are ignored.
- `artifacts/validation/<date>-*/` — retained evidence bundles: numbers in `manifest.json`, narrative in
  `notes.md` beside it.
- `.wayfinder/` — project decisions and implementation tickets. Two maps: `map.md` is the closed Phase 1
  plan; `map-002-splitter-merge-and-webapp.md` is Phase 2 — merging the bill splitter and replacing
  Streamlit with a webapp. **Phase 2 is decision-complete as of 2026-08-03** (18 of 19 tickets closed; the
  one open ticket is deferred past the pilot, not outstanding). **Slices S0 through S6 are done**: S6
  landed the two-level visual parity gate and deleted the POC. Retained evidence is in
  `artifacts/validation/2026-08-0*-slice-*/`. Start with
  `.wayfinder/artifacts/033-phase-2-slice-plan-and-scorecard.md`, which carries the build order and
  pass-or-fail gates. The map's *Decisions so far* index links every decision to its artifact.

## Checks

```bash
uv run --locked python scripts/check.py

# Individual gates remain available:
python3 scripts/validate_regression_fixtures.py
uv run --locked python scripts/run_optimizer_regressions.py
uv run --locked python -m unittest discover -s tests -p 'test_*.py' -v
uv run --locked python -m compileall -q api travel_planner scripts tests
python3 scripts/build_project_graph.py --check
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run test
```

## Credits

The split ledger and the interface's visual language come from
**Auto-Bill-Splitter**, this project's own earlier app, absorbed as a read-only
donor in Phase 2 and archived afterwards. Nothing was copied: `split.py` was
rebuilt from the donor's behaviour and deliberately diverges on rounding, and the
41 lifted element designs are attributed individually in the source by the
`derives-from:` declarations that `scripts/check_design_tokens.py` validates
against `artifacts/parity/2026-08-04-auto-bill-donor/`.
