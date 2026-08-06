# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm --prefix web install                                             # first web run only
uv run --locked python -m api                                        # production shell on 127.0.0.1:8765
uv run --locked python scripts/check.py                              # every free Python + web gate
uv run --locked python -m unittest discover -s tests -p 'test_*.py'  # 339 tests, ~9s
uv run --locked python -m unittest tests.test_optimizer.OptimizerCoreTest.test_safe_route_and_weather_fallback_are_selected  # one test
python3 scripts/validate_regression_fixtures.py                      # fixture catalog structure
uv run --locked python scripts/run_optimizer_regressions.py          # 27 historic cases through the real optimizer
uv run --locked python -m compileall -q api travel_planner scripts tests
python3 scripts/build_project_graph.py --check                       # graph integrity (free)
python3 scripts/check_provider_access.py --self-test                 # redaction check, no network
uv run --locked python scripts/check_design_tokens.py                 # token gate: 13 accent triples, no literals, ancestors, 3:1 contrast
uv run --locked python scripts/check_reference_coverage.py             # structural coverage of the four reference workbooks
```

All commands run from the repo root: `tests/` imports both `travel_planner` and `scripts` as top-level
packages via cwd on `sys.path`. Python has no linter or formatter; `web/` uses ESLint and deliberately has
no formatter.

`scripts/check_provider_access.py --live-paid` makes billable Google requests. Don't run it unasked.

## Architecture

There is one interface: the local React webapp behind `api/`. The Streamlit POC that proved the core
works was deleted at slice S6 on 2026-08-04. The design decisions are locked in `.wayfinder/tickets/`
(see below) — the constraints in this section are decisions, not incidental structure.

### Dependency direction is one-way and enforced by review, not by tooling

```
web/ (React)  →  api/ (stdlib localhost HTTP)  →  travel_planner/actions.py
                                                             │
                                                             ├─ core / optimizer / ranking / setup / discovery
                                                             └─ store.py (SQLite) · providers.py (HTTP)
```

- `core.py`, `optimizer.py`, `ranking.py`, `setup.py`, `discovery.py` are the planning core: pure,
  language-neutral, no UI / SQLite / HTTP / LLM imports. Check the module docstrings — they each state
  this. Adding such an import is the single easiest way to break the design, and honouring it is why
  replacing the whole interface at S6 cost the core nothing.
- `PlannerActions` (`actions.py`) is the only coordinator: it assembles snapshots, calls the core,
  and persists results. It holds no session state and no presentation formatting.
- `PlannerActions.journey()` decides which stages are done and which is next. The webapp renders the
  blocked explanation **in place** through `<StageGate>` rather than redirecting; only `/` redirects, to
  `journey["next"]`, so a returning owner lands on the stage needing attention.
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

**Transit routing arrived on 2026-08-05 (`WF-038`) and changes what the optimizer can plan.**
`travel_planner/transit.py` holds `TransitGraph`, the walking constants and **one** Dijkstra;
`gtfs.TransitFeed` builds one from a timetable zip and `transit.graph_from_osm()` from an
OpenStreetMap `route=subway` relation. `providers.GtfsTransitProvider` and `providers.OsmMetroProvider`
wrap them, both `mode: "transit"`, both priced at US$0.00 — priced rather than omitted, because an
unpriced operation raises. `actions.refresh_transit_routes` stores transit legs **beside** the walking
ones: the store keys a snapshot by (origin, destination, **mode**) and the optimizer takes the shortest it
holds, so short hops keep their walk. `PlannerActions._default_transit_provider` prefers a GTFS feed at
`TOURIST_GTFS_PATH` when one exists and falls back to OSM, which is weaker and says so — GTFS edges carry
`basis: "timetable"`, OSM edges `basis: "nominal"` with ride time from distance at 33 km/h and wait from
an assumed 6-minute headway. Taipei's own GTFS is **not sourced**: TDX needs a Taiwan mobile number.

Three consequences worth knowing. **A transit route is `status: "estimated"`, never `"verified"`**, and
three sites used to admit only `verified` — `actions._optimizer_input`,
`optimizer._routes_between` and `optimizer._best_inbound_route`. All three now admit `estimated` when
`allow_provisional_assumptions` is set, which only `explore_first` sets; a `ready_to_schedule` trip is
unaffected and `ROUTE_UNVERIFIED` stays fatal for it. The precedent is `_planning_fact`'s own docstring —
"a visible assumption allowed only for an Explore preview". **`walking_minutes` excludes the ride**, which
is the whole point: `maximum_walking_minutes_per_leg` measures it, so a 43-minute ride reached by a
2-minute walk passes a 25-minute cap no walk of that distance could. And **`refresh_routes` sorts pairs
nearest-first**, because the 60-per-run cap bites long before 41 places' 1640 pairs and a missing route
falls back to a pessimistic estimate — sorting by `place_id` spent 340 free calls on pairs the plan never
used and produced phantom 68-minute walks.

**Opening hours are per-day as of 2026-08-06 (`WF-041`).** `opening.common_interval` takes the overlap
across the days a place is **open** rather than refusing the moment one trip date is shut, and returns
`open_dates`; `_optimizer_input` puts those in the fact's `applies_to_dates`; `optimizer._open_on()` is
consulted by `_earliest_visit_start` and `validate_variant`. A fact without `applies_to_dates` applies
everywhere, so frozen fixtures are untouched. Before this a venue closed on one trip day was
unschedulable on **every** day — five of thirteen pilot landmarks were lost that way.

**A flight day's window holds its own logistics as of 2026-08-06 (`WF-042`).** The last day owes a fixed
suffix — `optimizer.DEPARTURE_LOGISTICS`, 45 + 45 + 90 = **180 minutes** of checkout, transfer and airport
— so `_optimizer_input` opens that day at `min("08:00", departure_time − DEPARTURE_LOGISTICS_MINUTES)`.
That constant is exported for exactly this reason and is the **one** source both sites read. Before it, a
morning flight made the departure day infeasible, and because `_greedy_baseline` accepts a placement only
when the **whole trip** builds clean, one unusable day emptied the entire plan — 13 visits to 0, every
landmark blamed on `PLAIN_WALK_THRESHOLD`. Two things follow. `_build_day` now refuses only when
`sequence or items`, so an empty day cannot veto the others. And **do not fix a window problem in the
builder**: moving `current` without moving `usable_windows` scheduled all 13 visits and then failed
`validate_variant` with `OUTSIDE_USABLE_WINDOW`, because the validator judges every item against the
snapshot's window and is meant to. `_skip_reason` is also not a measurement — it returns
`PLAIN_WALK_THRESHOLD` whenever a place was skipped and that threshold merely exists, so read
`_build_schedules`' own `hard_errors` when diagnosing. **No test set `include_operational_timeline`**
before this; it is `True` for every trip `actions.py` builds and absent from all 27 fixtures, so arrival
transfers, check-in, meals and the airport run were exercised only by the live pilot.

**Every variant gets its own time budget as of 2026-08-06 (`WF-043`).** `optimize_trip` used to compute
**one** absolute deadline and hand it to all three variants, so it was consumed in order and whichever ran
last inherited the remainder — measured on the pilot at 20.7s + 10.4s of a 30s budget, leaving
`more_highlights` already past it. It returned in 0.04s having placed **nothing**, was labelled `ready`
and `valid` because an empty schedule violates nothing, and reported
`objective_improved_or_equal_to_greedy: false` beside a `greedy_baseline` holding all 13 visits. The
deadline is now per variant, so worst case is `len(VARIANT_CONFIGS) × time_limit_seconds` and **a full
proposal takes ~52s, not ~31s** — that is the third variant doing its 21s of real work. Separately,
`_greedy_sequences` is split out of `_greedy_baseline` and `_insertion_search` **falls back to it** when
the deadline does fire: greedy sweeps every candidate and has no time limit, so it is a floor the search
can always afford, and returning worse than a schedule already in hand is never right. Two things not to
misread: `deterministic_signature` hashes the **input**, so it cannot detect a load-dependent output; and
an expired budget legitimately yields 0 visits where greedy's only schedule carries a comfort violation,
because `comfort_violations` outranks `experience_value` in the objective tuple — that ordering is
`WF-039`'s question.

**Ranking divides by category breadth as of 2026-08-06 (`WF-037`).** `group_preference_fit` divided the
owner's matched styles by how many they *named*, which a category with more tags wins for free: `peak`
carries four tags and `attraction` two, so a nameless hill scored 27 of 30 against Taipei 101's 12.8 and
Taipei 101 ranked **363rd of 832**. It now divides by `_breadth(candidate_tags)`, capped at four.
`FORMULA_WEIGHTS` is untouched. Do not assume the ranker's ordering is tested by the old suite — it
asserted only that the score was internally consistent, which holds under any weighting, and
`test_a_landmark_is_not_buried_by_a_richer_tag_vocabulary` is the first test of what it recommends.

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

All user-facing strings live in the eight `en`/`th` tables in `i18n/copy.json`; `travel_planner/copy.py`
reads it for the exports and React imports the same catalogue. The core emits stable codes; the views map code →
language → text. Switching language must never change ranking, scheduling, or the active plan — so
never put display text in the core or a language check in a scoring path. New user-visible string ⇒ add both
`en` and `th`. Tests enforce key parity across all tables except `CATEGORY_TEXT`'s documented derived-English
rule. Unknown stable codes render visibly as `⚠ CODE`; never prettify them into copy-looking prose.

### Tests

Python uses `unittest`; the webapp uses Vitest. No network, no paid API, no Python fixtures framework.
**`AppTest` is gone** — S6 removed the 18 tests that used it, having first moved the 14 portable
behaviours down to actions/core/exports. The suite is **311**.
`tests/fixtures/historic_regressions.json` encodes 20 atomic + 7 interaction failures from four real
past trips; `scripts/run_optimizer_regressions.py` replays all of them through the real optimizer.
Behavior changes to the optimizer should be expressed there.

## Configuration

`TOURIST_DB_PATH` (default `data/tourist.sqlite3`), `TOURIST_NOMINATIM_URL`, `TOURIST_OVERPASS_URL`,
`TOURIST_USER_AGENT`, `TOURIST_GTFS_PATH` (default
`data/gtfs/transit.zip`; a GTFS zip read locally for transit legs — see `WF-038`). Providers still read keys from `os.environ` and nowhere else — that is what keeps
a key out of every snapshot, export and log. `credentials.load_local_credentials()` (called once from `api.main()`)
copies a flat `secrets.local.json` into the environment first, so the owner need not
export four variables per shell; an already-set variable always wins, and the module never logs or
returns a value. `.env` / `secrets.local.json` are gitignored, `.env.example` / `secrets.example.json`
hold names and placeholders. `scripts/check_provider_access.py` reads the same file directly.
`tests/__init__.py` sets `TOURIST_LOCAL_SECRETS=off`. The original reason — `AppTest` importing `app.py`,
which loaded secrets at module scope — died with the POC, and `api` now loads them only in `main()`. **Do
not remove that line anyway**: it costs nothing and the failure it prevents is a bill. Paid usage is capped
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

**Rebuilt for `WF-042`/`WF-043` on 2026-08-06 and `--check` passes**: 1756 nodes, 4305 directed edges,
148 communities. Cost **US$0.0125** — the semantic cache hit 66 of 69 documents, so only the two new
tickets and the edited `CLAUDE.md` were extracted; recorded cumulative cost is US$0.315828 over 30 runs.
Adding a ticket file **breaks stage 4 of `check.py` until this is re-run**, because `--check` demands a
node per ticket; that is the normal reason to pay for a rebuild.

The earlier S6 rebuild on 2026-08-04 gave 1599 nodes, 3185 → 3851 directed edges and 149 communities, with
**zero nodes sourced from the deleted POC** (there were 82), for US$0.028350.

One of those failures was not flaky and is worth knowing: validation refused three times over the same
lost pair, `test_s4_taipei_journey_reaches_activation_and_both_downloads → web/src/api/client.rpc`. The
cause was a **name collision** — that test defined a local `def rpc(...)` helper and `client.ts` exports
`rpc`, so extraction invented an edge claiming a Python test calls a TypeScript function. Clustering was
right to drop it and the guard was demanding a false edge survive. Fixed at the source by renaming the
test-local helper to `post_api`; there is now no `def rpc` in any Python file. **Do not weaken the
endpoint-pair guard to get past a failure like this** — find the collision. `build()` now preserves
`failed-raw.json` and `failed-clustered.json` on failure, because the two files that explain a validation
failure were exactly the two its cleanup deleted. The script reads `OPENAI_API_KEY` from `secrets.local.json` itself.
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
**complete**, including the readiness checklist and owner-recorded costs: `exports.py` builds the one shared export snapshot; `exporters.py` writes the six-sheet Excel workbook and the
readiness ICS — both snapshot-in, bytes-out. **The 9:16 poster and the trip PDF were dropped in slice S0**
(2026-08-03), and with them the whole export-font apparatus. `checklist.py` generates the readiness board and `costs.py` converts owner-recorded
expenses into THB against an owner-editable, timestamped rate snapshot; a paid charge locks its actual
THB so a later rate cannot rewrite it, and a missing rate stays a visible gap rather than a guess.
**Phase 2 S5 is complete:** `api/` owns the localhost boundary and downloads, `web/` owns the nine
routes and in-place `StageGate`, and `scripts/check.py` is the one free green command. The allowlist is
**61 methods**: 51 at S1, five split-ledger ones at S2, `setup_vocabulary` at S3, the paid-call preflight
and export-snapshot reads at S4, then `checklist_vocabulary` at S5, and `refresh_transit_routes` for `WF-038`; 28 refusal codes. **All nine routes are
real screens** as of 2026-08-04 — `/setup`, `/places`, `/evidence`, `/optimize`, `/itinerary`, `/readiness`,
`/costs`, `/split` and `/revise`. There is no `StagePage`, no `gated()` wrapper and no `stage_stub` copy key;
they went with the last stub. `/evidence` was built between S5 and S6 because **no slice row owned it** and
S6 has since deleted the POC — see `artifacts/validation/2026-08-04-evidence-screen/notes.md`. It is the screen a
*newly created* trip needs, since route and opening evidence are hard optimizer constraints.
**Slice 6's non-AI half now has its React surface** (S5); its GenAI half stays deferred past the pilot. The
core landed long before either: `revision.py`'s non-AI quick actions (`a7ad537`) and
`interpret.py`'s constrained GenAI revision (`a2d59f6`) landed 2026-07-29 with tests. The pure modules
survived the redesign exactly as intended; their Streamlit surfaces went at S6. The live pilot remains
unbuilt. Every new output must read
`build_export_snapshot()` rather than the raw variant — that is what keeps their times, totals, and
statuses from diverging. Complete a slice vertically with its own runnable check before starting the next.

The export-font requirement is **gone** with the poster and PDF (S0): no Unicode TTF, no `resolve_font()`,
no `TOURIST_EXPORT_FONT`. `_labels()` still strips pictographs, because the wording alone carrying the state
is an accessibility rule and not only an export one.

Explicitly out of scope for the Python core: FastAPI, Docker, Redis, background workers, remote
collaboration, hosted notifications. `pyproject.toml` lists exactly two runtime dependencies:
`xlsxwriter` exists only because slice 5 renders a workbook. **After S6 there is exactly one**: `fpdf2` went
with the PDF and poster at S0, and `streamlit` went with the POC. `pillow` used to arrive transitively via
streamlit and is now declared in `[dependency-groups] dev` — the screen-baseline gate reads PNGs with it, so
that declaration is what kept the gate working when the POC went.

## Phase 2 implementation follows the locked slice order

`WF-MAP-002` is **decision-complete as of 2026-08-03**. Across both maps there are 43 tickets, **41
closed, 2 open**, and both open ones are open *by decision* rather than outstanding:
`Decide how an owner accepts a comfort tradeoff` (`WF-039`) and `Decide whether the planner recommends
where to stay` (`WF-040`). `Lock the Phase 2 slice plan and validation scorecard` is the destination artifact — read it
first: `.wayfinder/artifacts/033-phase-2-slice-plan-and-scorecard.md`.

**Three S6 decisions the owner settled on 2026-08-04, so nothing is waiting on them:**

- **Baseline tolerance is a small allowance, not zero** — the screen gate fails above **0.1% of pixels
  differing** *and* **>8/255 on a channel**, both conditions. Recorded in artifact 025. The element gate
  compares computed-style values and needs no tolerance.
- **The fonts are bundled.** Two variable `woff2` files in `web/public/fonts` (67 KB total, SIL OFL 1.1,
  licence beside them) cover 100-900 for both families, so **no weight can be synthesised**. That closed D8,
  and **the deviation register is now complete: zero outstanding.** Thai has no subset in either family and
  falls through per glyph to a system font, exactly as before.
- **Auto-Bill was never used with real expenses**, so `WF-030`'s pre-archive backup is **discharged**, not
  skipped. S6 may archive the donor whenever it is ready.

**Phase 2 is complete: S0 through S6 are all done as of 2026-08-04.** S6 landed the two-level visual parity
gate and deleted the POC. `scripts/check.py` is **12 stages**, green in ~17s — the twelfth is the
reference-workbook coverage gate.

The parity gate is two levels, and neither is a whole-screen comparison against the donor — Auto-Bill has
two screens and the planner has nine, so that comparison is meaningless:

- **`check_element_parity.py`** diffs the rebuild's *computed style values* against the donor capture by
  declared `derives-from:` ancestor. Exact, no tolerance, and it still works after the donor is archived. A
  difference fails only when unexplained — a registered deviation must actually license the rebuilt value,
  so D2 permits only `{2px, 9999px, 0px}`, D8 only a real token weight, and any shadow blur other than 0 is
  drift whatever the register says.
- **`check_screen_baselines.py`** compares 36 approved images (9 routes x light/dark x en/th) against a
  fresh capture. It catches **drift over time only**. Tolerance is the owner's pair: fail above 0.1% of
  pixels differing *and* more than 8/255 on a channel. See `artifacts/parity/screen-baselines/README.md`
  for the two capture races that had to be fixed to make it deterministic, and for the negative test.

Capturing needs a running server and headless Chrome, so only the *comparison* is a `check.py` stage; it
skips cleanly where nothing has been captured. Baselines are machine-specific by decision — re-approve when
the machine changes rather than widening the tolerance.

**All three of artifact 029's genuinely-UI tests were resolved before the deletion**, not dropped: the
paid-card placement rule is `web/src/stages/s4.test.tsx`, the entry-point smoke test became
`web/src/routes.test.tsx` (nine routes, five gate keys), and the journey walk kept its actions-level body in
`tests/test_workflow.py` while its eight-page render loop became the 36-screen capture. Only
`money_on_screen_is_not_read_as_maths` died, and only because Streamlit's `$`-as-LaTeX bug went with
Streamlit.

**S5 landed the last journey screens on 2026-08-04**
(evidence: `artifacts/validation/2026-08-04-slice-5/notes.md`). Four things from it bind S6:

- **The GenAI surface is absent on purpose.** `interpret_revision` is allowlisted and the transport would
  carry it, but `RevisePage` never calls it, because artifact 033 defers constrained GenAI revision past the
  pilot. A test asserts the screen renders no textarea and no interpret control, so the deferral cannot be
  undone by accident.
- **`placeName` / `placeNameFrom` in `web/src/shared/names.ts` is the one place naming happens.** `places`,
  `optimize` and `revise` each had their own copy with a different signature; they are consolidated. A
  consequence or plan row must name a place, never a truncated `place_id`, and divergence here is invisible
  until a screen shows an id.
- **`checklist_vocabulary` is the 60th allowlisted read**, with its orders asserted against the core tuples
  like `setup_vocabulary`. Do not hardcode a board vocabulary in TypeScript.
- **`revision.py` interpolates values into its assumption codes** (`WALKING_MINUTES_PER_LEG_SET_TO_14`), so
  no catalogue entry can exist and that line is permanently the visible-machine-output fallback. The POC
  does the same. Recorded as a pre-existing gap, not a port defect; changing it needs its own decision.

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
- **Five more portable behaviours moved below Streamlit here; the last four followed at S5.** The
  `AppTest` originals were deleted at S6, once all 14 had homes.
- **The visual witness was obtained 2026-08-04 and Gate 1 is now assessable.** Six captures across
  `places` and `itinerary` in both languages, the tile-free numbered map with its duplicated stop list,
  and both `GET` downloads verified over the socket with a bare `GET` to a mutation still refused.
- **The walkthrough figures are reproducible, not inspectable.** Opening `data/tourist.sqlite3` as-is
  gives the sparser stored plan (7 days, 8 rows, three row types, no readiness). The 8 days / 69 rows /
  six row types / 13 readiness items come from re-running optimize → activate → readiness proposal,
  which is what the evidence steps describe. Re-run them before doubting the numbers.
- **Never open `data/tourist.sqlite3` to demonstrate something.** Copy it first. The witness ran on a
  copy, which bumped to 13 and left its own `-pre-v13-` backup at 12 while the original stayed at 12 —
  the first time S2's refuse-on-failure migration ran against real pilot content rather than a fixture.

**S3 landed the cheap journey screens on 2026-08-03**
(evidence: `artifacts/validation/2026-08-03-slice-3/notes.md`). Five things from it bind later work:

- **The setup draft is one object, always sent whole.** `save_setup` defaults every field to empty, so
  a partial payload **erases what it omits**. Five steps are five views over one piece of state, never
  five requests. The draft also carries `owner_nationality` and each member's `nationality`, which
  the POC's setup view dropped on save — readiness reads them, so losing them is not round-tripping whole.
  `SetupPage` sends them; keep it that way.
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

**`tests/test_ported_behaviours.py` was the S6 deletion checklist, and it is discharged.** It holds the
actions-level homes for the 14 behaviours that used to be asserted through `AppTest`, organised by
provenance on purpose. Nothing is owed; the file stays because the behaviours are real, and its provenance
grouping is the record of where each one came from.

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
  **`data/tourist.sqlite3` was bumped 12 → 13 on 2026-08-04** by owner decision, rehearsed on a
  byte-identical copy first and leaving `data/tourist-pre-v13-2026-08-04.sqlite3` — verified byte-identical
  to the pre-bump file — as the only way back. It happened then rather than nearer the trip because
  `WF-024`'s no-schema-change window, 29 December 2026 to 4 January 2027, **is the trip's own dates**:
  the bump had to precede the window or wait until the trip was over. Evidence in
  `artifacts/validation/2026-08-04-schema-13-bump/`.
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
- **Streamlit was the POC that proved the core works — not a product, not a pilot fallback.** `views/`,
  `app.py` and `ui/` were **deleted at S6 on 2026-08-04** (2,951 lines) once the webapp reached parity
  across all nine routes. There is no fallback and that is deliberate. Schema is fully
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
- `shared.journey()` was 74 lines of business logic in the POC's UI layer; it moved into
  `PlannerActions.journey()` as the 51st allowlisted method, which is why deleting `ui/` cost nothing. It currently reaches into the private
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
- **The donor capture happened on 2026-08-04** — `artifacts/parity/2026-08-04-auto-bill-donor/` holds 431
  style records across both themes, 97 inline-style sites, resolved tokens per theme and **35 of the 41
  elements fully covered**, with the six gaps named. Diff S6's rebuild against `computed-styles.json` rather
  than trying to recreate the donor. **The backup JSON could not be taken: the donor held no trip data** —
  `alipay_splitter_settings` absent, `alipay_splitter_transactions` empty. If Auto-Bill was ever used for
  real, that data is in another browser profile and is exportable until S6 archives the donor; the files in
  that bundle named `synthetic-*` are a schema record from a trip the capture created, **not** the owner's
  archive. One measured finding binds S6: **the donor's accent is `#dc2626` in both themes**, which is the
  evidence for deviation D1.
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
