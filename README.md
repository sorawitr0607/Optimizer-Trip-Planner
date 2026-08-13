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

This repository is a **local, single-user personal travel planner**, designed to run privately on your own machine. Its local server, SQLite database, and credential model are built for trusted local environments. When planning a hosted multi-user release, follow [the public release improvement plan](PUBLIC_RELEASE_PLAN.md).

## Supported platforms

| Requirement | Supported version | Notes |
|---|---|---|
| **Operating System** | macOS (Apple Silicon / Intel), Linux (x86_64, aarch64), Windows 10/11 (WSL2 recommended) | Direct POSIX filesystem and process support |
| **Python** | `>= 3.12` | Managed via [`uv`](https://docs.astral.sh/uv/) (recommended) or standard `venv` |
| **Node.js & npm** | Node `>= 20.x` (or `24.x` LTS), npm `>= 10.x` | Required for the React/Vite web interface |
| **Web Browser** | Chrome, Firefox, Safari, Edge (recent versions) | Desktop and mobile responsive views supported |

## Quick start

### 1. Prerequisites

Make sure Python 3.12+, `uv`, and Node.js are installed:

```bash
# Verify runtimes
python3 --version   # Python 3.12+
node --version      # v20+ or v24+
```

### 2. Install dependencies

```bash
# 1. Install frontend dependencies
npm --prefix web install

# 2. Sync locked Python virtual environment
uv sync --locked
```

### 3. Launch the application

```bash
uv run --locked python -m api
```

The app will be available at **`http://127.0.0.1:8765`**.

### 4. Updating

To update an existing checkout:

```bash
git pull
uv sync --locked
npm --prefix web install
uv run --locked python scripts/check.py
```

## Configuration & optional providers

Optimizer Trip Planner works **100% offline and free** out of the box using built-in solvers and OpenStreetMap / Overpass data.

For optional capabilities (such as paid Google Maps validation, OpenRouteService matrix routing, or AI candidate generation), copy the example configuration:

```bash
cp secrets.example.json secrets.local.json
```

Edit `secrets.local.json` with your optional keys:
- `OPENROUTESERVICE_API_KEY`: Matrix travel routing
- `GOOGLE_MAPS_SERVER_KEY`: Server-side address & place verification
- `GOOGLE_MAPS_BROWSER_KEY`: Browser map enrichment
- `OPENAI_API_KEY`: AI-assisted place candidate suggestions

Never commit `secrets.local.json` or `.env`.

## The 9 core workflow routes

Every trip flows through nine real, interactive screens:

1. **Setup (`/trips/:id/setup`)**: 5-step wizard configuring destination country/city, travel dates, pacing constraints, and traveler preferences.
2. **Places (`/trips/:id/places`)**: Candidate place discovery via free OpenStreetMap/Overpass data or custom place additions.
3. **Evidence (`/trips/:id/evidence`)**: Verify opening hours, exact coordinates, admission fees, and transit requirements.
4. **Optimize (`/trips/:id/optimize`)**: Deterministic constraint-aware solver computing optimal daily visit orders and route pacing.
5. **Itinerary (`/trips/:id/itinerary`)**: Interactive day-by-day timetable rendered on the map along the actual walking routes, with one-tap handoff to phone navigation.
6. **Readiness (`/trips/:id/readiness`)**: Actionable pre-trip checklist proposals (reservations, packing, documents) with readiness scoring.
7. **Costs (`/trips/:id/costs`)**: Budget tracking, currency conversion, and categorized expense recording.
8. **Split (`/trips/:id/split`)**: Multi-currency group bill splitting ledger calculating exact settlement transactions.
9. **Revise (`/trips/:id/revise`)**: In-trip live adjustments, stop reordering, weather adaptations, and schedule rescheduling.

### The map

Every place, day and route is drawn on a real map. **Online it is OpenStreetMap's own tiles** — the same images `openstreetmap.org` serves. **Offline it draws itself** from data already on disk: land use, water, parks, building footprints, the road hierarchy with street names, rail, and station entrances, all from one free Overpass request per window. It falls back the moment a tile fails to load, so the plan still works on a plane, and it says which of the two you are looking at.

Zoom out far enough and the destination country's own outline appears, so a place can be seen in its country rather than only its city. `/itinerary` opens on the map, drawing the day's stops in order along the walk actually taken, and every stop hands off to the phone's own map for the last fifty metres.

`© OpenStreetMap contributors` is shown beside every map, which the ODbL requires of the geometry as well.

## Data storage & exports

- **Local SQLite Database**: Stored in `data/tourist.sqlite3`.
- **Database Migrations & Safety**: The database is at schema 14. Schema upgrades automatically create a timestamped backup before migrating.
- **Snapshot Exporters**:
  - **Excel Workbook (`.xlsx`)**: 6-sheet formatted trip workbook (Timetable, Costs, To-Do List, Things to Bring, Transport, etc.).
  - **Calendar Feed (`.ics`)**: Standard iCalendar feed for import into Apple Calendar, Google Calendar, or Outlook.

## Repository map

- `PUBLIC_RELEASE_PLAN.md` — the deferred build and evidence gates for a future hosted public service.
- `api/` — stdlib localhost transport and the local webapp entry point.
- `web/` — React, TypeScript, Tailwind, route shell, and stage gates.
- `i18n/copy.json` and `tokens.css` — copy and design truth shared across renderers.
- `travel_planner/` — planner domain logic, storage, providers, ranking, and optimization.
- `travel_planner/exporters.py` — snapshot-in, bytes-out writers: the six-sheet Excel workbook and the readiness ICS.
- `travel_planner/climate.py` and `travel_planner/areas.py` — pure modules for seasonal suitability and station neighbourhoods.
- `web/src/stages/PlaceMap.tsx` and `web/src/shared/tiles.ts` — the map component and tile arithmetic.
- `travel_planner/destinations.py` — country/city picker table.
- `tests/` — deterministic unit tests and historic trip regressions.
- `artifacts/parity/` — donor style capture and 56 approved screen baselines.
- `scripts/` — validation, regression, provider, and Graphify maintenance commands.
- `data/reference-itineraries/<city>/` — source workbooks and PDF itineraries.
- `graphify-out/` — checked-in graph snapshot.
- `artifacts/validation/<date>-*/` — retained evidence bundles.
- `.wayfinder/` — project decisions and implementation tickets.

## Checks & verification

Run the complete 12-stage validation suite:

```bash
uv run --locked python scripts/check.py

# Individual checks:
uv run --locked python -m unittest discover -s tests -p 'test_*.py' -v
uv run --locked python scripts/run_optimizer_regressions.py
python3 scripts/validate_regression_fixtures.py
python3 scripts/build_project_graph.py --check
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run test
```

## License

This project is licensed under the [MIT License](LICENSE).

## Credits

The split ledger and interface visual language derive from **Auto-Bill-Splitter**, this project's earlier application, absorbed as a read-only donor in Phase 2. Attributions are declared individually in the source via `derives-from:` tokens validated against `artifacts/parity/2026-08-04-auto-bill-donor/`. Map data is `© OpenStreetMap contributors` under the ODbL.

