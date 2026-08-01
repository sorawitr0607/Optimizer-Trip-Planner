# Optimizer Trip Planner

Personal, evidence-aware trip planning. The planning core builds and revises a
timetable from traveler preferences, attraction choices, opening hours, travel
time, and pacing constraints.

The Streamlit app is the **proof of concept** that established the core works —
not the product. Phase 2 replaces it with a local React webapp that also
absorbs `Auto-Bill-Splitter` as a group split ledger. The planning core,
`actions.py` and `store.py` survive that change untouched; `views/`, `app.py`
and `ui/` are deleted once the webapp reaches parity. Until then the POC is
what runs, and it is unmaintained rather than frozen.

## Run locally

```bash
uv run streamlit run app.py
```

The app uses `data/tourist.sqlite3` by default. Copy `.env.example` to `.env`
for optional provider configuration; never commit local secrets.

## Repository map

- `app.py` — Streamlit entry point.
- `views/` — one script per journey stage; `ui/` holds every user-facing string and the shared renderers.
- `travel_planner/` — planner domain logic, storage, providers, ranking, and optimization.
- `travel_planner/destinations.py` — the country/city picker table. A convenience only: both
  dropdowns accept a typed value, so any worldwide destination still works.
- `tests/` — deterministic unit and UI tests; historic trip regressions are in `tests/fixtures/`.
- `scripts/` — validation, regression, provider, and Graphify maintenance commands.
- `data/reference-itineraries/<city>/` — source workbooks and PDF itineraries.
- `graphify-out/` — checked-in graph snapshot; generated caches are ignored.
- `.wayfinder/` — project decisions and implementation tickets. Two maps: `map.md` is the closed Phase 1
  plan; `map-002-splitter-merge-and-webapp.md` is the open Phase 2 plan for merging the bill splitter and
  replacing Streamlit with a webapp. **Phase 2 is still being decided — 10 of its 19 tickets are open, so
  none of it is built.** Decisions and research findings live in `.wayfinder/artifacts/`; read the map's
  *Decisions so far* index first, then the artifact a decision points at.

## Checks

```bash
python3 scripts/validate_regression_fixtures.py
uv run --locked python scripts/run_optimizer_regressions.py
uv run --locked python -m unittest discover -s tests -p 'test_*.py' -v
uv run --locked python -m compileall -q app.py travel_planner scripts tests
python3 scripts/build_project_graph.py --check
```
