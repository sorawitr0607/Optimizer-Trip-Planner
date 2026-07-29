# Optimizer Trip Planner

Personal, evidence-aware trip planning MVP. The Streamlit app builds and
revises a timetable from traveler preferences, attraction choices, opening
hours, travel time, and pacing constraints.

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
- `.wayfinder/` — project decisions and implementation tickets.

## Checks

```bash
python3 scripts/validate_regression_fixtures.py
uv run --locked python scripts/run_optimizer_regressions.py
uv run --locked python -m unittest discover -s tests -p 'test_*.py' -v
uv run --locked python -m compileall -q app.py travel_planner scripts tests
python3 scripts/build_project_graph.py --check
```
