# Optimizer Trip Planner

Personal, evidence-aware trip planning. The planning core builds and revises a
timetable from traveler preferences, attraction choices, opening hours, travel
time, and pacing constraints.

The Streamlit app is the **proof of concept** that established the core works —
not the product. Phase 2 is replacing it with a local React webapp that also
absorbs `Auto-Bill-Splitter` as a group split ledger. The planning core,
`actions.py`, and `store.py` remain the domain boundary; `views/`, `app.py`
and `ui/` are deleted once the webapp reaches parity. Until then both surfaces
remain runnable: the webapp is incomplete and the POC remains the planner UI.

## Run locally

```bash
npm --prefix web install             # first run only
uv run --locked python -m api        # http://127.0.0.1:8765
```

The webapp currently provides the S1 shell and route gates; stage surfaces land in later slices. The
Streamlit POC remains available with `uv run streamlit run app.py` until parity. Both use
`data/tourist.sqlite3` by default. Copy `secrets.example.json` to `secrets.local.json`
for optional provider configuration; never commit local secrets.

## Repository map

- `api/` — stdlib localhost transport and the production webapp entry point.
- `web/` — React, TypeScript, Tailwind, route shell, and stage gates.
- `app.py`, `views/`, `ui/` — the temporary Streamlit POC surface.
- `i18n/copy.json` and `tokens.css` — copy and design truth shared across renderers.
- `travel_planner/` — planner domain logic, storage, providers, ranking, and optimization.
- `travel_planner/exporters.py` — snapshot-in, bytes-out writers: the six-sheet Excel workbook and the
  readiness ICS. The 9:16 poster and the trip PDF were dropped in slice S0, and with them the export-font
  requirement.
- `travel_planner/destinations.py` — the country/city picker table. A convenience only: both
  dropdowns accept a typed value, so any worldwide destination still works.
- `tests/` — deterministic unit and UI tests; historic trip regressions are in `tests/fixtures/`.
- `scripts/` — validation, regression, provider, and Graphify maintenance commands.
- `data/reference-itineraries/<city>/` — source workbooks and PDF itineraries.
- `graphify-out/` — checked-in graph snapshot; generated caches are ignored.
- `artifacts/validation/<date>-*/` — retained evidence bundles: numbers in `manifest.json`, narrative in
  `notes.md` beside it.
- `.wayfinder/` — project decisions and implementation tickets. Two maps: `map.md` is the closed Phase 1
  plan; `map-002-splitter-merge-and-webapp.md` is Phase 2 — merging the bill splitter and replacing
  Streamlit with a webapp. **Phase 2 is decision-complete as of 2026-08-03** (18 of 19 tickets closed; the
  one open ticket is deferred past the pilot, not outstanding), **so implementation has begun**: slices S0
  and S1 are done. Start with `.wayfinder/artifacts/033-phase-2-slice-plan-and-scorecard.md`, which carries
  the build order and pass-or-fail gates. The map's *Decisions so far* index links
  every decision to its artifact.

## Checks

```bash
uv run --locked python scripts/check.py

# Individual gates remain available:
python3 scripts/validate_regression_fixtures.py
uv run --locked python scripts/run_optimizer_regressions.py
uv run --locked python -m unittest discover -s tests -p 'test_*.py' -v
uv run --locked python -m compileall -q app.py travel_planner scripts tests
python3 scripts/build_project_graph.py --check
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run test
```
