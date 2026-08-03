# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm --prefix web install                                             # first web run only
uv run --locked python -m api                                        # production shell on 127.0.0.1:8765
uv run streamlit run app.py                                          # temporary Phase 1 POC
uv run --locked python scripts/check.py                              # every free Python + web gate
uv run --locked python -m unittest discover -s tests -p 'test_*.py'  # 312 tests, ~11s
uv run --locked python -m unittest tests.test_optimizer.OptimizerCoreTest.test_safe_route_and_weather_fallback_are_selected  # one test
python3 scripts/validate_regression_fixtures.py                      # fixture catalog structure
uv run --locked python scripts/run_optimizer_regressions.py          # 27 historic cases through the real optimizer
uv run --locked python -m compileall -q app.py travel_planner scripts tests
python3 scripts/build_project_graph.py --check                       # graph integrity (free)
python3 scripts/check_provider_access.py --self-test                 # redaction check, no network
```

All commands run from the repo root: `tests/` imports both `travel_planner` and `scripts` as top-level
packages via cwd on `sys.path`. Python has no linter or formatter; `web/` uses ESLint and deliberately has
no formatter.

`scripts/check_provider_access.py --live-paid` makes billable Google requests. Don't run it unasked.

## Architecture

Phase 1 is the temporary local Streamlit POC. Phase 2 S1 adds the local React shell without deleting it.
The design decisions are already locked in `.wayfinder/tickets/` (see below) — the constraints in this
section are decisions, not incidental structure.

### Dependency direction is one-way and enforced by review, not by tooling

```
web/ (React)  →  api/ (stdlib localhost HTTP)  →  travel_planner/actions.py
app.py (Streamlit POC) ────────────────────────→             │
                                                             ├─ core / optimizer / ranking / setup / discovery
                                                             └─ store.py (SQLite) · providers.py (HTTP)
```

- `core.py`, `optimizer.py`, `ranking.py`, `setup.py`, `discovery.py` are the planning core: pure,
  language-neutral, no Streamlit / SQLite / HTTP / LLM imports. Check the module docstrings — they
  each state this. Adding such an import is the single easiest way to break the design.
- `PlannerActions` (`actions.py`) is the only coordinator: it assembles snapshots, calls the core,
  and persists results. It holds no Streamlit session state and no presentation formatting.
- The POC UI is split by journey stage. `app.py` owns only what every stage shares: the language, selected
  trip, journey state, and `st.navigation`. Each stage is under `views/`; `ui/text.py` re-exports the shared
  JSON catalogue and `ui/shared.py` holds POC state plus row renderers.
  A view never recomputes context: it calls `shared.actions()`, `shared.words()`, `shared.trip()`.
- `PlannerActions.journey()` decides which stages are done and which is next; `shared.journey()` is only a
  POC compatibility shim. `shared.require(stage, trip)`
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

All user-facing strings live in the eight `en`/`th` tables in `i18n/copy.json`; `ui/text.py` is a thin POC
compatibility shim and React imports the same catalogue. The core emits stable codes; the views map code →
language → text. Switching language must never change ranking, scheduling, or the active plan — so
never put display text in the core or a language check in a scoring path. New user-visible string ⇒ add both
`en` and `th`. Tests enforce key parity across all tables except `CATEGORY_TEXT`'s documented derived-English
rule. Unknown stable codes render visibly as `⚠ CODE`; never prettify them into copy-looking prose.

### Tests

Python uses `unittest`, plus `streamlit.testing.v1.AppTest` for the temporary POC paths
(`AppTest.from_file(ROOT / "app.py")` with `TOURIST_DB_PATH` patched to a temp dir). The webapp uses Vitest
for focused UI behavior. No network, no paid API, no Python fixtures framework.
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

**Rebuilt for S1 on 2026-08-03 and `--check` passes**: 1358 nodes, 3185 directed edges. The guarded S1
run cost US$0.067015 across two restored clustering failures and one successful cached run; recorded
cumulative cost is US$0.228995. The script reads `OPENAI_API_KEY` from `secrets.local.json` itself.
Three things to know: **ticket nodes are keyed by title, not by ID**, so `WF-0nn` never appears in a node
name; **`--exclude` patterns are gitignore lines**, so anchor them (`/artifacts`, not `artifacts`) or they
match at every depth; and **never run `graphify extract` by hand** — it is incremental against an existing
`graph.json` and will overwrite it with a partial. `AGENTS.md` has the detail.

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
day summary, timeline, and numbered map; `exporters.py` writes the six-sheet Excel workbook and the
readiness ICS — both snapshot-in, bytes-out. **The 9:16 poster and the trip PDF were dropped in slice S0**
(2026-08-03), and with them the whole export-font apparatus. `checklist.py` generates the readiness board and `costs.py` converts owner-recorded
expenses into THB against an owner-editable, timestamped rate snapshot; a paid charge locks its actual
THB so a later rate cannot rewrite it, and a missing rate stays a visible gap rather than a guess.
**Phase 2 S4 is complete:** `api/` owns the localhost boundary and downloads, `web/` owns the nine
routes and in-place `StageGate`, and `scripts/check.py` is the one free green command. The allowlist is
**59 methods**: 51 at S1, five split-ledger ones at S2, `setup_vocabulary` at S3, then the paid-call
preflight and export-snapshot reads at S4; 28 refusal codes. `/costs`, `/split`, `/setup`, `/places`,
`/optimize` and `/itinerary` are real; `evidence`, `readiness` and `revise` remain stubs. **Slice 6's
core exists but only behind the POC UI:** `revision.py`'s non-AI quick actions (`a7ad537`) and
`interpret.py`'s constrained GenAI revision (`a2d59f6`) landed 2026-07-29 with tests, wired into
`views/revise.py`. The pure modules survive the redesign; their Streamlit surfaces are POC code awaiting
deletion, so **slice 6 still has to be built in the webapp** and the live pilot remains unbuilt. Every new
output must read
`build_export_snapshot()` rather than the raw variant — that is what keeps their times, totals, and
statuses from diverging. Complete a slice vertically with its own runnable check before starting the next.

The export-font requirement is **gone** with the poster and PDF (S0): no Unicode TTF, no `resolve_font()`,
no `TOURIST_EXPORT_FONT`. `_labels()` still strips pictographs, because the wording alone carrying the state
is an accessibility rule and not only an export one.

Explicitly out of scope for the Python core: FastAPI, Docker, Redis, background workers, remote
collaboration, hosted notifications. `pyproject.toml` lists exactly two runtime dependencies:
`xlsxwriter` exists only because slice 5 renders a workbook, and `streamlit` is the only one for the
*interface*. Keep it that way. **After S0 there are two**: `fpdf2` and `pillow` were dropped with the PDF and
poster — though `pillow` stays *installed* because `streamlit` depends on it, so it only leaves the
environment when Streamlit is deleted at S6.

## Phase 2 implementation follows the locked slice order

`WF-MAP-002` is **decision-complete as of 2026-08-03**: 19 tickets, **18 closed, 1 open**. The one open
ticket, `Prototype the ranked candidate card grid`, is **deferred past the pilot by decision** rather than
outstanding. `Lock the Phase 2 slice plan and validation scorecard` is the destination artifact — read it
first: `.wayfinder/artifacts/033-phase-2-slice-plan-and-scorecard.md`.

**The Phase 2 code freeze has lifted.** S0 through S4 are complete; **S5 is the next allowed slice** —
the non-AI quick actions plus `revise` and `readiness`. S4 made the saved real Taipei trip assessable
through discovery, ranking, optimization, activation and export; fresh trips still wait on the
route-evidence surface assigned to parity work.

**S4 landed the expensive journey screens on 2026-08-04**
(evidence: `artifacts/validation/2026-08-04-slice-4/notes.md`). Its constraints are:

- **`places` is a functional ranked list, not the deferred card grid.** It preserves all lanes,
  choices, reasons, score breakdowns, provenance and the owner-triggered paid overlay. Every paid
  action shows its estimate immediately before its button; insight and photos stay session-only.
- **`itinerary` reads `build_export_snapshot()`**, never the raw variant. The six row types, fallbacks,
  bilingual stop list, true-relative coordinate SVG, workbook and readiness calendar therefore share
  one set of times and statuses.
- **`check_paid_call` and `build_export_snapshot` are allowlisted reads 58 and 59.** No internal writer
  was exposed and no runtime dependency was added.
- **Five more portable behaviours now live below Streamlit; four remain.** No `AppTest` original is
  deleted before S6.
- **The exact visual witness is still owed.** The in-app browser connector was unavailable during the
  S4 run, so production build, server/API transport, SSR render tests and export validation are retained,
  but no S4 screen capture is claimed.

**S3 landed the cheap journey screens on 2026-08-03**
(evidence: `artifacts/validation/2026-08-03-slice-3/notes.md`). Five things from it bind later work:

- **The setup draft is one object, always sent whole.** `save_setup` defaults every field to empty, so
  a partial payload **erases what it omits**. Five steps are five views over one piece of state, never
  five requests. The draft also carries `owner_nationality` and each member's `nationality`, which
  `views/setup.py` drops on save — readiness reads them, so losing them is not round-tripping whole.
- **`setup_vocabulary` is the 57th allowlisted method**, a read returning planning modes, accommodation
  statuses, the four tag groups as codes, and countries with **both** language labels plus their cities.
  Both languages in one payload so a language switch never refetches. Its picker orders are explicit
  lists asserted against the core frozensets: a frozenset is right for validation and useless for a
  radio group.
- **The step indicator is step-count-agnostic.** The donor's `.*-4` family hardcoded four; renaming to
  `-5` would hardcode the next wrong number. Clicking a step navigates **backwards only**, kept because
  later steps depend on earlier answers.
- **`copyFrom(table, code, language)`** renders the seven catalogue tables beside `TEXT`. Unknown codes
  still surface as `⚠ CODE`. A flash or any other message must hold a **code**, never rendered text, or
  a language switch cannot re-render it.
- **The accent is destination-driven now.** `AppShell` sets `data-country` on the root from the
  destination's country (D6); an unknown country matches no rule and keeps the house red (D3). **The
  phone sidebar collapse below 992px is a new element** — artifact 028 explicitly left it undesigned —
  so it declares element 17 `.sidebar` as its ancestor and still needs a real-phone capture before the
  parity gate runs.

**`tests/test_ported_behaviours.py` is the S6 deletion checklist.** It holds the actions-level homes for
behaviours still asserted through `AppTest`, organised by provenance on purpose. Two of artifact 029's
"14 portable" were already at actions level, so **12 were outstanding and 4 remain after S4**; its module
docstring lists what is owed. No `AppTest` original is deleted until `views/` goes at S6.

**S2 landed the merge on 2026-08-03** (evidence: `artifacts/validation/2026-08-03-slice-2/notes.md`).
Four things from it bind later work:

- **`travel_planner/split.py` owns all split math** and is pure like the rest of the core. Shares are
  **recomputed on read, never stored**, so there is exactly one rounding rule: the division happens in
  integer satang and the remainder spreads one satang at a time over the first participants in the
  row's own order. That deviates from the donor's dump-it-on-the-first-person and is recorded as a
  deviation, not drift.
- **Schema is 13.** `split_rows` and `split_settled_markers` carry **no append-only triggers** by
  decision. `store._copy_before_bump()` copies to `data/tourist-pre-v<n>-<date>.sqlite3` before any
  bump and raises rather than migrating if the copy fails. It is gated on
  `0 < on_disk_version < SCHEMA_VERSION`: version 0 is a database being created and an equal version
  is not a bump, and without that gate every temp database in the suite would leave a junk copy.
  **`data/tourist.sqlite3` is still at 12 and was deliberately not bumped** — that is a one-way change
  to the only real trip in the file and needs to be the owner's deliberate act.
- **Claimed-ness is derived in exactly one place: `costs.totals()`**, which returns `claimed_cost_ids`
  for the screen to read. Do not add a second derivation — `split.py` had one and it was deleted for
  the vocabulary-drift reason `WF-018` names. Dependency direction is `split.py → costs.py`; the
  reverse is a cycle, which is why the tag → category map lives in `split.py` and `apply_rates()`
  stamps a resolved `category` before `costs.totals()` sees the row.
- **The settled marker stores the balance it settled**, not a payment, and `settled` is derived by
  comparing it to the current net. So a marker goes stale silently the moment the arithmetic moves,
  with no write-time cascade to keep in sync. **The owner is the cardholder** (`PlannerActions.CARDHOLDER`);
  there is no stored setting and no `delete_split_row` — removing a row voids it.

**A scope cut landed with the slice plan: the PDF and the 9:16 poster are dropped.** `pyproject.toml` goes to
**two** runtime dependencies (`streamlit`, `xlsxwriter`), the whole export-font apparatus is void — do not
build the merged Noto pipeline — and tests went **235 → 230**. The workbook and ICS survive.
**S0 is done as of 2026-08-03**: `exporters.py` is 1136 → 692 lines, and the workbook now localises optimizer
codes through `_code()` as the PDF always did, so a Thai owner still gets Thai where a label exists.

The destination specification is decision-complete. The Python transport adds no runtime dependency; the
browser dependencies live only in `web/package.json`. Build one slice vertically and retain its evidence
before starting the next.

Read the map before touching anything in this area. Work it one ticket per session — claim a ticket by
setting its `assignee:` before doing any work, and only research tickets may be resolved more than one
per session.

> **The owner set that last clause aside on 2026-07-31**, directing seven grilling tickets to be resolved in
> one session (`WF-019`, `WF-022`, `WF-026`, `WF-028`, `WF-025`, `WF-023`, `WF-030`). It was explicit each
> time, not drift. The rule still stands as written unless the owner says otherwise — do not assume a
> standing exception.

Locked by the destination interview, so not open for re-litigation inside a ticket:

- The planning core, `actions.py`, and `store.py` remain the domain layer behind a thin local HTTP layer.
  React replaces the `views/`, `app.py`, and `ui/` presentation surface. The deterministic optimizer, the
  hash gates, the append-only plan history, and the 248 current tests all survive the redesign. *(248 was
  the count when this was locked; the suite is 287 after S2 and none of the originals were rewritten.)*
- **Two linked ledgers**, not one merged record: cost rows stay the budget and estimate truth, the split
  ledger records actual group spend. Reconciling them is now **decided**, not open — see the claim rule below.
- Everything lands in this repository (`api/` + `web/`). `Auto-Bill-Splitter` is a read-only donor, then
  archived.
- Tokens are **rebuilt** in Tailwind, so visual parity with Auto-Bill is a hard gated requirement rather
  than an aspiration — same palette, same zero-blur hard offset shadows, same fonts, same elements.
- Bilingual `en`/`th` stays mandatory, and the key-parity test keeps running.
- Local-only and owner-led: `localhost`, SQLite on disk, no accounts, no auth.
- **Streamlit is the POC that proved the core works — not a product, not a pilot fallback.** It stays in
  the tree unmaintained (`views/` need not stay green) and `views/`, `app.py` and `ui/` are deleted once
  the webapp reaches parity across all 8 stages. Slice 6 is built as part of the webapp. Schema is fully
  unconstrained — there is no tag, no downgrade path, no restorable old checkout. The webapp is the
  **committed** vehicle for the pilot with a **1 November 2026** checkpoint; not on track means Taipei is
  planned by hand in Excel, as the four reference trips were.
- **Validation compares generated output against the four reference workbooks in
  `data/reference-itineraries/`, programmatically — never against Streamlit's output.** Their four
  recurring sheets (`ตารางเวลา`, `ค่าใช้จ่าย`, `♢ To-Do List`, `☺ Things to Bring`) are the merged app's
  entire output surface, so they validate the merge itself. Comparison asserts structural coverage, not
  cell equality: the workbooks are hand-made and inconsistent. Reading them needs `openpyxl` as a **dev**
  dependency; the Python runtime dependencies stay untouched. See
  `.wayfinder/artifacts/022-streamlit-poc-retirement-and-pilot-commitment.md`.

Already decided, and binding on any future implementation:

- Split math lives in a new pure `travel_planner/split.py` beside `costs.py`, under the same no-Streamlit,
  no-SQLite, no-HTTP rule. The API returns resolved shares, balances, and settlement; the frontend renders
  numbers it was given. One rounding implementation, so the screen and the workbook cannot disagree by a
  satang. (Originally "and the PDF"; the PDF was dropped in S0 and the reasoning is unchanged.)
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
- The webapp stack: **TypeScript, react-router, TanStack Query, Tailwind v4 configured in CSS**, npm with
  Node pinned by `.nvmrc`. `web/src/` is organised **by stage** beside `shared/`, `api/` and `i18n/`.
  ESLint with `react-hooks`, `tsc` for types, no formatter. `web/dist` is not committed. Six web runtime
  dependencies, ten dev — and **Python stays at four**. See
  `.wayfinder/artifacts/026-webapp-stack-and-layout.md`.
- Two rules from that ticket are correctness, not taste. **`retry: false` is TanStack Query's default
  here**: the library's 3 retries would burn both of Overpass's 2 concurrent slots on a 34 s call and
  double-spend paid calls against the US$10 cap. And **`save_setup` takes all 18 fields every time, each
  defaulting to empty, so a partial payload silently erases what it omits** — the setup form holds one
  draft object and always sends it whole.
- The webapp's IA: **9 stage routes under `/trips/:tripId/`** resolving to **5 gate keys**, in the same two
  BUILD/USE sections, with the eight ported slugs unchanged. The trip id lives in the **path** because all
  51 methods take `trip_id` and TanStack keys must include it. One `<StageGate>` wrapper renders the blocked
  explanation **in place** — `require()` never redirected, and only `/` does, to `journey["next"]`. Setup is
  one route with five steps in state. **Costs and split are two cross-linked screens**: costs holds estimates
  for the drafted plan, split holds actual bills split per person. Navigation adapts Auto-Bill's existing
  sidebar shell. See `.wayfinder/artifacts/028-webapp-information-architecture.md`.
- `shared.journey()` (`ui/shared.py:160`) is 74 lines of business logic in the UI layer, and it moves into
  `PlannerActions.journey()` as the 51st allowlisted method. It currently reaches into the private
  `_optimizer_input`, invents the gap code `OPENING_EVIDENCE_MISSING` that the core never emits, and
  duplicates the rated-place filter `rank_candidates` enforces. React cannot recompute it — that would
  require exposing `_optimizer_input`.
- The visual parity gate: the **token contract is the target, and it must be completed before the gate can
  run** — 39 JSX classes have no CSS rule (not the 18 or ~28 earlier tickets claimed) across 114 inline
  style sites. Checking is screenshot comparison at two levels: **element-level captures of the 41 lifted
  elements, which must be taken before `Auto-Bill-Splitter` is archived**, plus 4 screen baselines per route
  (light/dark × en/th) that catch drift only. New elements pass on token conformance plus a declared
  ancestor. Auto-Bill's defects are **fixed and recorded as deviations D1–D7** — without that register every
  fix reads as a parity failure. Radius unifies on `2px`. See
  `.wayfinder/artifacts/025-visual-parity-gate.md`.
- **The Python exporters survive; `excelExporter.js` is deleted and `exceljs`/`file-saver` never join `web/`.**
  One generator is the only way `build_export_snapshot()`'s one-snapshot rule can hold, the 25 export tests
  have no JS counterpart, and only Python has the ICS. *(The PDF-and-poster half of that argument died with
  S0; the conclusion stands on the other two grounds.)* **Two workbooks**: a plan file and a
  shareable money file, both from the same snapshot — so the money file carries no itinerary, no addresses and
  no readiness evidence. Planned-versus-actual lands in the plan workbook's Costs sheet as **values, not
  formulas**, because there is nothing in the same file to point at; an export is a snapshot, not a live
  document. Downloads are dedicated `GET` routes with `Content-Disposition` — **an exception to the RPC
  convention, and bare `GET` may reach downloads and nothing else**, never a mutation or a paid call, because
  a `GET` carries no `Content-Type` for the guard to check. See
  `.wayfinder/artifacts/030-exporter-and-download-contract.md`.
- **Copy moves to one JSON catalogue that both renderers read** — Python for the exports, TypeScript for the
  screen — because `_export_labels()` is `TEXT[lang] | OPTIMIZER_CODE_TEXT[lang]`, so Python needs it whatever
  React does. **No i18n library**: importing JSON `as const` checks keys at compile time, which beats runtime
  lookup and is exactly the guarantee whose absence hid the 24 missing English strings. The parity test grows
  to all eight tables; the fallback becomes visibly machine output (`⚠ ACCESS_UNVERIFIED`); `CATEGORY_TEXT` is
  the one documented exemption, with derived English plus a `place_of_worship` override. **Emoji decorate and
  never carry meaning alone** — a flag-only cell becomes an empty cell in the **workbook**, since `_labels()`
  still strips pictographs after S0. See
  `.wayfinder/artifacts/027-bilingual-copy-pipeline.md`.
- Testing after `AppTest`: exposure is **7%** — 18 tests of the 235 that existed when it was measured, not 12
  of 15 files — so the great majority survive untouched. The suite is **230** after S0. Of the 18, **14 port down** to actions/core/exports and are moved **before** anything is deleted,
  **3 are genuinely UI**, and 1 dies with Streamlit's `$`-as-LaTeX workaround. API contract tests are
  `unittest` at two levels: dispatch directly, plus a real server on **port 0**, because the `Content-Type`
  guard, the `Host` allowlist and the bare-`GET` rule are **security controls** unreachable without a socket.
  **Vitest** for frontend units; the journey walk comes free from the parity harness. One green command,
  `scripts/check.py`. See `.wayfinder/artifacts/029-test-strategy-after-apptest.md`.
- Migration: **no importer is built.** `data/tourist.sqlite3` holds exactly **one trip — the Taipei pilot** —
  and Auto-Bill keeps one trip's data at a time, so there is nothing to merge it into. The backup JSON is an
  **archive record**, and the split ledger starts empty. A row arriving with known THB and no rate keeps it as
  a **locked `actual_thb`**; fabricating an `as_of` would put a made-up date in a field that means something
  else. **Every schema bump copies the database to `data/tourist-pre-v<n>-<date>.sqlite3` first and refuses to
  proceed if the copy fails** — WF-022 removed the downgrade path, so that copy is the only way back. And
  **no schema change between 29 December 2026 and 4 January 2027**: a one-way bump on the only trip in the
  file, while that trip is happening abroad, is not worth any feature. See
  `.wayfinder/artifacts/024-migration-path.md`.
- Offline assets: **no tile map.** The exports never had one — they print numbered stops with coordinates —
  and the only tile use was `st.map`, so the numbered stop list *is* the map and screen and export agree by
  construction. Fonts **self-host as `woff2`** plus a **merged Noto TTF for exports**, because today exports
  work only on a machine that happens to have proprietary `Arial Unicode.ttf` and `resolve_font()` raises
  rather than rendering tofu. **Void after S0** — the PDF and poster are gone, so there is no export font at
  all. Do not build the merged Noto pipeline. **Bold monospace becomes real.** `flagcdn.com` becomes a local sprite where a
  missing flag shows the country name alone. **Everything local works offline** — the optimizer and
  `revision.py` are pure — **and network-requiring actions say so before being pressed.** The colour source is
  **`tokens.css`, in CSS not JSON**. See `.wayfinder/artifacts/034-offline-asset-policy.md`.
- **Two things must be taken from `Auto-Bill-Splitter` before it is archived**: a backup JSON per trip (kept as
  an archive record — a file survives archiving, `localStorage` does not) and the 41 lifted element captures
  for the parity gate. Both need the donor runnable. The token extraction is **done**, so it no longer does.
- The token contract's inline-only layer is extracted (§10). Two counts worth knowing: of the 39 classes with no
  CSS rule, **only 23 carry any styling** — 16 are bare containers with nothing to port — and **not one
  hardcoded colour appears in any of the 114 inline sites**, so the off-token colour problem is entirely in the
  stylesheet (41 literals, 75 uses). Auto-Bill has **no tab element** and `/split`'s allocation-mode views are
  **bare containers**, so both must be designed rather than recovered.
- Cost/split reconciliation: **a split row may claim a cost row via one optional `cost_id`, and the claimed
  row defers its actual.** Nothing is added to the cost row and `payment_state` is untouched — claimed-ness is
  derived — so `planned` is every cost row and `actual` is non-voided split rows **plus unclaimed paid cost
  rows**, making double counting structurally impossible. `costs.totals()` **gains** `planned_thb` and
  `actual_thb` and redefines nothing, because its `estimated_thb` sums non-paid rows only and so is not the
  plan figure. The seven categories become the default tag vocabulary. Split rows inherit the cost rate
  snapshot with **`buffer_percent` skipped**. Gaps warn and never block. See
  `.wayfinder/artifacts/023-cost-and-split-reconciliation.md`.
- **`group_preference_weights` is not a cost weight.** `setup.py:93`–`97` gives the owner 0.5 and members
  0.5 between them, it feeds only `ranking.py`, and it expresses *taste*. Using it for money would charge the
  owner half the trip. Estimated per-person is `planned_thb / headcount`; actual per-person comes from
  `split.py`'s resolved shares.
- **Colour gets one machine-readable source that both renderers read.** `exporters.py` hardcodes 8 hexes
  across 17 occurrences in a cool blue-grey palette matching nothing in Auto-Bill, and
  `views/itinerary.py:94,104` adds three pin hexes — so the workbook looks like a different product
  *(after S0 only one hex remains, the poster having taken 16 of the 17 with it)*, and `WF-022` already made them a pilot-ready gate. Same reasoning as `WF-018`'s single
  rounding implementation.
- `.wayfinder/artifacts/` holds the Auto-Bill token contract, the element inventory matrix, the local API
  contract, the POC-retirement decision, the webapp stack, the information architecture, and the parity
  gate. Consult them instead of re-reading 2458 lines of `index.css` — and read the correction block at the
  top of the token contract before trusting its counts or its Tailwind config draft.
