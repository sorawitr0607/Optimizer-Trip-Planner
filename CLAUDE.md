# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run streamlit run app.py                                          # run the app
uv run --locked python -m unittest discover -s tests -p 'test_*.py'  # 202 tests, ~7s
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
- The UI is split by journey stage. `app.py` (about 100 lines) owns only what every stage shares: the
  language, the selected trip, the journey state, and `st.navigation`. Each stage is a script under
  `views/`, all copy lives in `ui/text.py`, and shared state plus row renderers live in `ui/shared.py`.
  A view never recomputes context: it calls `shared.actions()`, `shared.words()`, `shared.trip()`.
- `shared.journey()` decides which stages are done and which is next; `shared.require(stage, trip)`
  renders one clear next step and returns False when a stage is not reachable, so a view explains
  itself instead of erroring. The landing page is the stage that needs attention, so a returning owner
  sees the itinerary rather than the setup form.
- `st.navigation` always renders at the top of the sidebar, so `app.py` cannot put anything above it;
  the trip context sits directly under the stages and the language control at the foot. The language is
  read with `shared.language()` before its widget is created, which is what lets that widget render last.
- Any string built from numbers or exception text goes through `shared.plain()`. Streamlit markdown reads
  a pair of `$` as inline LaTeX, which silently swallowed the amounts in `US$0.1300 / US$10.00`.
- A UI test must select its stage: `at = AppTest.from_file(ROOT / "app.py", ...)`, then
  `at.switch_page("views/<stage>.py")`, then `at.run()`. Without the switch, the default landing stage
  renders and assertions about another stage will fail. The trip selector is a sidebar widget keyed
  `selected_trip_id`.
- Setup is the five editable steps of `Prototype the owner-led setup and confirmation flow`, not one
  form. `views/setup.py` holds no `st.form`: the city list depends on the chosen country, and a form
  defers every value until submit. Each step seeds its widgets from the saved draft rather than from
  session state, because Streamlit drops widget state once a widget stops rendering, and each
  `Save & continue` autosaves through an `on_click` callback. A callback runs after the values are
  committed but before the rerun, so it saves what the owner can see; a closure captured at render time
  would miss an edit made just before the click, and `st.rerun()` mid-script leaves two steps in one run.
- A selectbox or multiselect whose `format_func` depends on the language must go through
  `shared.translated_selectbox` / `shared.translated_multiselect`. Streamlit caches the selected
  option's rendered text in the browser, so the plain widget keeps the previous language's wording
  after a switch — the dropdown list updates, the closed control does not. The helpers key the widget
  per language and carry the choice in a language-free key. Consequences: widget keys end in
  `__<language>`, so a UI test looks up `key="country__en"`; and a value is read back with
  `shared.chosen("<base key>")`, never straight from session state.
- `travel_planner/destinations.py` (country/city) and `costs.COMMON_CURRENCIES` are picker
  convenience only. Both dropdowns take a typed value, so a destination or currency absent from the
  table stays reachable — the worldwide acceptance check requires it. A city name is the geocoder
  query, so it is never localized; localizing it would let a language switch change which place is
  searched.

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
   A dense city takes about 34 s of Overpass time, so the query declares `[timeout:90]` and the socket
   allows 105 s; the earlier 25 s budget failed every Taipei attempt. The endpoint grants 2 concurrent
   slots and answers 504 immediately once they are spent, so a burst of retries reads as an outage that
   is really self-inflicted — space them. `out center qt` with a 500-record limit truncates in quadtile
   order, so a big city's catalog can miss its landmarks; see the walkthrough notes in
   `artifacts/validation/2026-07-29-slice5-6-evidence-notes.md`.
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

7. **Revision** — `revision.py` holds the whole typed operation set. An operation is a *constraint
   change* on the optimizer input, never a schedule instruction, so nothing in it can write an opening
   time, route, fare or closure; the deterministic optimizer rebuilds the plan and `consequences()`
   reports the before/after. `propose_revision` keeps exactly one pending draft and leaves the active
   plan untouched; `apply_revision` refuses unless the rebuilt variant is `ready` and valid, and
   refuses again if the active plan moved behind the preview. Applying writes a new immutable version
   plus an append-only history row; restore creates another version and deletes nothing.

8. **Free-text revision** — `interpret.py` builds the strict structured-output schema *from*
   `revision.OPERATIONS`, so the model can only choose a supported operation and may name only a
   `place_id` it was actually sent. It cannot return an opening time, route, fare or closure because no
   operation carries such a field. `build_payload` sends the plan slice and the request and nothing
   else; `_assert_clean` refuses a payload carrying travellers, documents or credentials. One call per
   request, `store: false`, one retry at most on a transient failure, and every failure names its cause
   (`missing_credentials`, `offline`, `refused`, `invalid_reply`, `rate_limited`, `api_error`) while
   leaving the plan and history untouched. Where the model omits a magnitude the app supplies a
   documented default and shows it as a visible assumption; where the value is the point of the request
   it asks one clarification instead. GenAI is off by default and everything else works without it.

Plans are append-only: `plan_versions` and `discovery_runs` carry SQLite triggers that abort UPDATE
and DELETE. Restoring an old plan creates a *new* version pointing at the old snapshot. `active_plans`
holds exactly one version per trip; `optimization_previews` holds at most one replaceable pending
preview. `SCHEMA_VERSION` (`store.py`) is stamped into `PRAGMA user_version`; a newer DB refuses to open.

### Bilingual by data, not by branching

All user-facing strings live in `en`/`th` dicts in `ui/text.py` (`TEXT`, `TAG_TEXT`,
`EXPLANATION_TEXT`, `OPTIMIZER_CODE_TEXT`, …). The core emits stable codes; the views map code →
language → text. Switching language must never change ranking, scheduling, or the active plan — so
never put display text in the core or a language check in a scoring path. New user-visible string ⇒
add both `en` and `th`; a test asserts `TEXT["en"]` and `TEXT["th"]` carry the same keys, because a
missing `th` key is a `KeyError` in front of a Thai owner rather than a typo.

### Tests

`unittest` only, plus `streamlit.testing.v1.AppTest` for UI paths (`AppTest.from_file(ROOT / "app.py")`
with `TOURIST_DB_PATH` patched to a temp dir). No network, no paid API, no fixtures framework.
`tests/fixtures/historic_regressions.json` encodes 20 atomic + 7 interaction failures from four real
past trips; `scripts/run_optimizer_regressions.py` replays all of them through the real optimizer.
Behavior changes to the optimizer should be expressed there.

## Configuration

`TOURIST_DB_PATH` (default `data/tourist.sqlite3`), `TOURIST_NOMINATIM_URL`, `TOURIST_OVERPASS_URL`,
`TOURIST_USER_AGENT`. Providers still read keys from `os.environ` and nowhere else — that is what keeps
a key out of every snapshot, export and log. `credentials.load_local_credentials()` (called once at the
top of `app.py`) copies a flat `secrets.local.json` into the environment first, so the owner need not
export four variables per shell; an already-set variable always wins, and the module never logs or
returns a value. `.env` / `secrets.local.json` are gitignored, `.env.example` / `secrets.example.json`
hold names and placeholders. `scripts/check_provider_access.py` reads the same file directly.
`tests/__init__.py` sets `TOURIST_LOCAL_SECRETS=off` because `AppTest` imports `app.py`: without it the
suite would run holding real keys, and a test reaching a real provider would bill rather than fail with
"not configured". Do not remove that line. Paid usage is capped
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

A node's `source_file` may hold an absolute path from the machine that built the graph. Such a path is
not `is_absolute()` on Windows, so joining it to the repository root produced a drive-relative path
that matched nothing, and `--check` failed with `Extraction produced no node for WF-001` on every
ticket except the one stored relatively. That reads exactly like the corruption above but is not it:
the nodes are present. `build_project_graph.source_path()` resolves a node's source against the
longest trailing segments that exist in this checkout, so the check works from any OS and any root.
Diagnose a `--check` failure by counting the wayfinder-sourced nodes before assuming data loss.

## Wayfinder: decisions live in tickets

There are **two maps**, and tickets are numbered continuously across both in `.wayfinder/tickets/`; a
ticket's `parent:` field says which map it belongs to.

- `.wayfinder/map.md` (`WF-MAP-001`, **closed**) indexes the 17 closed Phase 1 decision tickets.
- `.wayfinder/map-002-splitter-merge-and-webapp.md` (`WF-MAP-002`, **open**) is Phase 2: merging
  `Auto-Bill-Splitter` in as a group split ledger and replacing Streamlit with a local React webapp.

Before changing scoring weights, optimizer rules, schema, or provider policy, read the relevant ticket —
the "why" is there, not in the code. Reference tickets by linked title, never bare ID.

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
collaboration, hosted notifications. `pyproject.toml` lists exactly four runtime dependencies:
`fpdf2`, `pillow` and `xlsxwriter` exist only because slice 5 renders a PDF, a poster and a workbook,
and `streamlit` is the only one for the *interface*. Keep it that way.

## Phase 2 is being planned, not built — do not implement it yet

`WF-MAP-002` is **open and unfinished**: 19 tickets, **4 closed, 15 open**, 8 of those on the frontier.
The destination is a decision-complete specification, exactly as Phase 1's was, so **no Phase 2 code gets
written until the map has no unresolved decisions**. Until then the Phase 1 out-of-scope rule above still
binds: today those four remain the only runtime dependencies, and there is no `api/` and no `web/`. The
locked API contract keeps it that way — it adds none.

Read the map before touching anything in this area. Work it one ticket per session — claim a ticket by
setting its `assignee:` before doing any work, and only research tickets may be resolved more than one
per session.

Locked by the destination interview, so not open for re-litigation inside a ticket:

- The planning core, `actions.py`, and `store.py` stay as they are behind a thin local HTTP layer. React
  replaces `views/` and `app.py` only. The deterministic optimizer, the hash gates, the append-only plan
  history, and the 202 tests all survive the redesign.
- **Two linked ledgers**, not one merged record: cost rows stay the budget and estimate truth, the split
  ledger records actual group spend. Reconciling them is an open ticket, not a detail.
- Everything lands in this repository (`api/` + `web/`). `Auto-Bill-Splitter` is a read-only donor, then
  archived.
- Tokens are **rebuilt** in Tailwind, so visual parity with Auto-Bill is a hard gated requirement rather
  than an aspiration — same palette, same zero-blur hard offset shadows, same fonts, same elements.
- Bilingual `en`/`th` stays mandatory, and the key-parity test keeps running.
- Local-only and owner-led: `localhost`, SQLite on disk, no accounts, no auth.
- Streamlit is frozen at slices 1–5 as the fallback Taipei pilot vehicle. **Slice 6 is built only in
  React** — never twice. So the "not yet built" note above is now a Phase 2 obligation, not a Streamlit one.

Already decided, and binding on any future implementation:

- Split math lives in a new pure `travel_planner/split.py` beside `costs.py`, under the same no-Streamlit,
  no-SQLite, no-HTTP rule. The API returns resolved shares, balances, and settlement; the frontend renders
  numbers it was given. One rounding implementation, so the screen, the workbook, and the PDF cannot
  disagree by a satang.
- Settlement is a star through the main cardholder with fronted cash netted off. Rows are editable and
  void rather than delete, so the split ledger takes **no** append-only triggers.
- The local API is a stdlib `ThreadingHTTPServer` with **zero new runtime dependencies**, dispatching
  `POST /api/<method>` straight onto `PlannerActions`. Two rules from that contract are safety-critical, not
  taste: **the dispatch table is an explicit literal allowlist, never introspection**, because
  `save_plan_version` writes an arbitrary snapshot as an activated immutable version with no optimizer
  validation and `record_paid_call` forges append-only ledger rows — `dir()` would expose both. And a
  snapshot `sha256` is **exposed but never accepted as an argument**; the server re-derives every hash
  itself. Full contract in `.wayfinder/artifacts/019-local-api-contract.md`.
- Refusals get stable codes: the 46 `raise ValueError` in `actions.py` collapse into 26 codes behind
  `PlannerRefusal(ValueError)`. Until that migration lands, a Thai owner reads English at every refusal —
  a **Phase 1** defect, so it is not gated by the Phase 2 decision gate.
- `.wayfinder/artifacts/` holds the extracted Auto-Bill token contract, the element inventory matrix, and
  the local API contract. Consult them instead of re-reading 2458 lines of `index.css` — and note the token
  contract is known to be incomplete for the ~18 classes that exist only as inline styles.
