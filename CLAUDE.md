# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run streamlit run app.py                                          # run the app
uv run --locked python -m unittest discover -s tests -p 'test_*.py'  # 111 tests, ~7s
uv run --locked python -m unittest tests.test_optimizer.OptimizerCoreTest.test_safe_route_and_weather_fallback_are_selected  # one test
python3 scripts/validate_regression_fixtures.py                      # fixture catalog structure
uv run --locked python scripts/run_optimizer_regressions.py          # 27 historic cases through the real optimizer
uv run --locked python -m compileall -q app.py travel_planner scripts tests
python3 scripts/build_project_graph.py --check                       # graph integrity (free)
python3 scripts/check_provider_access.py --self-test                 # redaction check, no network
```

All commands run from the repo root: `tests/` imports both `travel_planner` and `scripts` as top-level
packages via cwd on `sys.path`. There is no linter or formatter configured.

`scripts/check_provider_access.py --live-paid` makes billable Google requests. Don't run it unasked.

## Architecture

Phase 1 is one local Streamlit app. The design decisions are already locked in `.wayfinder/tickets/`
(see below) — the constraints in this section are decisions, not incidental structure.

### Dependency direction is one-way and enforced by review, not by tooling

```
app.py (Streamlit)  →  travel_planner/actions.py  →  core.py / optimizer.py / ranking.py / setup.py / discovery.py
                                    ↓
                       store.py (SQLite) · providers.py (HTTP)
```

- `core.py`, `optimizer.py`, `ranking.py`, `setup.py`, `discovery.py` are the planning core: pure,
  language-neutral, no Streamlit / SQLite / HTTP / LLM imports. Check the module docstrings — they
  each state this. Adding such an import is the single easiest way to break the design.
- `PlannerActions` (`actions.py`) is the only coordinator: it assembles snapshots, calls the core,
  and persists results. It holds no Streamlit session state and no presentation formatting.
- `app.py` is a flat top-level Streamlit script (no `main()`), executed top to bottom, holding all UI
  copy and all widget wiring.

### Everything crossing a boundary is a frozen, hashed snapshot

`core.freeze_snapshot()` canonicalizes a mapping (sorted keys, no NaN, UTF-8) into
`FrozenSnapshot(canonical_json, sha256)`. Every domain record wraps its payload in one, and every
`store.py` read re-verifies the hash before returning. Consequences:

- `freeze_snapshot()` rejects secret-bearing keys (`api_key`, `*_api_key`, `access_token`, passport and
  booking document keys — see `FORBIDDEN_SNAPSHOT_KEYS`) anywhere in the tree. Snapshots are the place
  secrets could leak into SQLite and exports; that guard is why they can't.
- Hashes are the staleness mechanism, not timestamps: discovery stores `setup_sha256`, and ranking or
  optimization refuses to run when it no longer matches the confirmed setup.

### Pipeline: setup → discovery → ranking → optimization → activation

Each stage is gated on the previous one having a matching hash (`_current_choice_inputs`).

1. **Setup** — `setup.build_setup_payload()` normalizes owner/member preferences into a draft;
   nothing downstream runs until `confirmed`.
   Setup and the optimizer use different accommodation vocabularies — `unknown`/`not_booked`/`booked`
   versus the `unbooked` that `optimizer._hotel_recommendation()` and the frozen fixtures test for.
   `_optimizer_input` translates at the boundary; before it did, hotel-area recommendations silently
   never fired for any app-created trip.
2. **Discovery** — `providers.OpenStreetMapProvider` (Nominatim + Overpass, free) → `discovery.build_candidate_catalog()`
   normalizes and dedupes into provider-neutral candidates with an explicit status
   (`verified` / `stale` / `unavailable` / `error`). Raw responses live in the `provider_cache` table
   (7-day TTL, keyed by provider + request fingerprint); an expired entry may back a visibly `stale`
   result but never a `verified` one. Inject a fake via `PlannerActions(path, place_provider=...)` —
   that is how every test avoids the network.
3. **Ranking** — `ranking.build_ranking()` scores cards on the fixed 30/20/20/10/15/5 weights in
   `FORMULA_WEIGHTS`, with protected exploration slots and per-card explanations. Deterministic.
4. **Optimization** — `optimizer.optimize_trip()` takes one complete snapshot and returns three
   variants (`best_balance`, `relaxed`, `more_highlights`), each independently rechecked by
   `optimizer.validate_variant()` — never trust solver construction. Same input + same
   `OPTIMIZER_VERSION` must yield the same proposal, asserted via `deterministic_signature`. With no
   trip dates it returns `mode: "stay_recommendation"` instead of a timetable. At the time limit it
   returns only a labelled valid incumbent, never a partial schedule.
5. **Activation** — `activate_plan_preview()` refuses unless the preview's `input_sha256` still
   matches current choices AND the variant is `status == "ready"` with `validation.valid`. It then
   writes an immutable plan version and deletes the preview.
6. **Readiness** — `checklist.propose_items()` generates a city-independent board from setup, choices,
   and verified facts; `diff_proposal()` previews additions, removals, and deadline moves;
   `apply_checklist_proposal()` writes them, dismissing rather than deleting so nothing silently
   disappears. No provider supplies official entry rules, so a generated item stays
   `verification_needed` with no `source_url` until the owner records one — the board names what to
   verify and against which authority, and never asserts a legal conclusion. Requirement level and
   evidence state move independently, and `validate_item()` refuses a verified `required` item with no
   responsible authority type. Board items are the one mutable record type; readiness warnings are
   explicitly non-blocking (`blocks_itinerary` is always False).

Plans are append-only: `plan_versions` and `discovery_runs` carry SQLite triggers that abort UPDATE
and DELETE. Restoring an old plan creates a *new* version pointing at the old snapshot. `active_plans`
holds exactly one version per trip; `optimization_previews` holds at most one replaceable pending
preview. `SCHEMA_VERSION` (`store.py`) is stamped into `PRAGMA user_version`; a newer DB refuses to open.

### Bilingual by data, not by branching

All user-facing strings live in `en`/`th` dicts at the top of `app.py` (`TEXT`, `TAG_TEXT`,
`EXPLANATION_TEXT`, `OPTIMIZER_CODE_TEXT`, …). The core emits stable codes; `app.py` maps code →
language → text. Switching language must never change ranking, scheduling, or the active plan — so
never put display text in the core or a language check in a scoring path. New user-visible string ⇒
add both `en` and `th`.

### Tests

`unittest` only, plus `streamlit.testing.v1.AppTest` for UI paths (`AppTest.from_file(ROOT / "app.py")`
with `TOURIST_DB_PATH` patched to a temp dir). No network, no paid API, no fixtures framework.
`tests/fixtures/historic_regressions.json` encodes 20 atomic + 7 interaction failures from four real
past trips; `scripts/run_optimizer_regressions.py` replays all of them through the real optimizer.
Behavior changes to the optimizer should be expressed there.

## Configuration

`TOURIST_DB_PATH` (default `data/tourist.sqlite3`), `TOURIST_NOMINATIM_URL`, `TOURIST_OVERPASS_URL`,
`TOURIST_USER_AGENT`. Keys are read from the environment only — `.env` / `secrets.local.json` are
gitignored, `.env.example` / `secrets.example.json` hold names and placeholders. Paid usage is capped
at US$10/month by decision (warn at $8). `usage.py` is that ledger: `PRICES_USD` holds the estimated
unit price per `provider:operation`, `actions._spend()` refuses a call that would cross the cap and
records what it cost, and free-tier operations are recorded at zero so call counts stay reconcilable.
Every paid provider call must route through `_spend`; an unpriced operation raises rather than being
assumed free. Ledger rows are append-only by SQLite trigger.

## Graphify: this repo overrides the parent instructions

The ancestor `Thaksin/CLAUDE.md` tells agents to run `graphify query` for codebase questions and `graphify update .`
after edits. **Do not do either here.** Read source and tests directly; consult
`graphify-out/GRAPH_REPORT.md` only for a broad architecture question.

`graphify-out/GRAPH_REPORT.md` carries a generated "Graph Freshness" line advising `graphify update .`
after code changes. That is graphify 0.9.3 boilerplate, it is regenerated on every rebuild, and it is
wrong for this repo — ignore it.

On 2026-07-29 `graphify update . --no-cluster` corrupted the checked-in graph: it dropped the
`directed` flag and removed the Wayfinder/document nodes. `graphify-out/graph.json` is canonical and
must stay directed. Rebuild only through `python3 scripts/build_project_graph.py` (paid, needs
`OPENAI_API_KEY`; wraps extract → normalize → cluster-only → export and restores the previous graph on
failure), and only when explicitly asked or after a topology-changing milestone. After any graph
change, `--check` must pass before committing. See `AGENTS.md`.

## Wayfinder: decisions live in tickets

`.wayfinder/map.md` indexes 17 closed decision tickets in `.wayfinder/tickets/`. Before changing
scoring weights, optimizer rules, schema, or provider policy, read the relevant ticket — the "why" is
there, not in the code. Reference tickets by linked title, never bare ID.

Slices 1–4 are built and evidenced (foundation, setup+discovery, ranking, optimization). Slice 5 is
**complete**, including the readiness checklist and owner-recorded costs: `exports.py` builds the one shared export snapshot; `app.py` renders the active-plan
day summary, timeline, and numbered map; `exporters.py` writes the 9:16 poster PNG, the trip PDF, and
the six-sheet Excel workbook — all three snapshot-in, bytes-out. `checklist.py` generates the readiness board and `costs.py` converts owner-recorded
expenses into THB against an owner-editable, timestamped rate snapshot; a paid charge locks its actual
THB so a later rate cannot rewrite it, and a missing rate stays a visible gap rather than a guess.
**Not yet built:** all of slice 6 (non-AI quick actions, then optional
constrained GenAI revision, then the live Taipei pilot). Every new output must read
`build_export_snapshot()` rather than the raw variant — that is what keeps their times, totals, and
statuses from diverging. Complete a slice vertically with its own runnable check before starting the next.

PDF and poster rendering needs a Unicode TTF covering Latin + Thai + local script (CJK for the Taipei
pilot). `exporters.resolve_font()` checks `TOURIST_EXPORT_FONT` first, then a small candidate list
(macOS `Arial Unicode.ttf` is the one that covers all three here); with no font it raises rather than
rendering tofu. The app's status labels carry emoji that no such font has, so `_labels()` strips
pictographs — the wording alone still carries the state.

Explicitly out of scope for Phase 1: FastAPI, React, Docker, Redis, background workers, remote
collaboration, hosted notifications. `streamlit` is the only runtime dependency in `pyproject.toml`;
keep it that way.
