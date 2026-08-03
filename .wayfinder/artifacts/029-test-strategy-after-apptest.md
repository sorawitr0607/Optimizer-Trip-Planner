# Test strategy after Streamlit AppTest dies

Resolves `Decide the test strategy after Streamlit AppTest dies` (WF-029).

Decided 2026-08-03 through the test-strategy interview. Measured against the checkout at `e682089`.
Paths are repo-relative.

## AppTest exposure is 7%, not 80%

The ticket notes that 12 of 15 test files use `AppTest`. True at file level, and misleading: each of those
files holds one to four `AppTest` tests amid mostly pure ones.

| File | Tests | `AppTest` |
|---|---|---|
| `test_checklist.py` | 30 | 2 |
| `test_interpret.py` | 28 | **0** |
| `test_exports.py` | 25 | 4 |
| `test_revision.py` | 25 | 1 |
| `test_opening.py` | 24 | 1 |
| `test_routes.py` | 21 | 1 |
| `test_setup_discovery.py` | 17 | 2 |
| `test_usage.py` | 15 | **0** |
| `test_costs.py` | 13 | 1 |
| `test_foundation.py` | 13 | 3 |
| `test_optimizer.py` | 8 | 1 |
| `test_ranking.py` | 8 | 1 |
| `test_graph_builder.py` | 7 | **0** |
| `test_workflow.py` | 1 | 1 |
| **Total** | **235** | **18 (7%)** |

**217 of 235 tests survive the UI replacement untouched.** The decision is about 18 tests, not 12 files.

## What those 18 actually assert

Classified by the lowest layer that could assert the same thing:

### Portable to actions / core / exports — 14

| Test | New home |
|---|---|
| `trip_without_setup_explains_the_board_is_unavailable` | `journey()` gate data |
| `a_trip_without_a_plan_is_told_which_stage_to_finish` | `journey()` gate data |
| `deleting_the_last_trip_returns_to_first_trip_setup` | `journey()` + `delete_trip` |
| `trip_slots_create_switch_and_keep_drafts_independent` | `create_trip` / `get_setup` |
| `owner_and_two_members_confirm_and_survive_thai_switch` | `save_setup` + copy tests |
| `a_destination_outside_the_picker_still_creates_a_trip` | `create_trip` |
| `preview_is_persisted_but_unverified_inputs_cannot_activate` | `activate_plan_preview` gate |
| `missing_hours_and_hotel_create_a_visible_provisional_plan` | optimizer + actions |
| `costs_section_renders_and_saves` | `save_cost_item` |
| `interested_choice_persists_and_ranking_renders_in_thai` | `save_candidate_choice` + copy |
| `board_renders_previews_and_applies_in_both_languages` | checklist actions + copy |
| `the_section_previews_and_applies_in_both_languages` | revision actions + copy |
| `active_plan_renders_timeline_and_map_in_both_languages` | export snapshot + copy |
| `fallback_block_renders_beneath_its_half_day` | `exports.py` placement |

**Most of these were never UI tests.** They assert product logic through a UI because that was the only
surface available. At actions level they become faster, browser-free, and independent of which frontend
exists. Three of them are only portable *because* `WF-028` turned `shared.journey()` into a real
`PlannerActions.journey()` method — they can now assert the gate data directly.

### Genuinely UI — 3

| Test | Why it needs a frontend |
|---|---|
| `each_paid_enrichment_offers_its_own_card` | "Every paid action states its cost immediately before the spending button" is a placement rule, not a value |
| `streamlit_entry_point_renders` | Becomes a **React smoke test**. It does not die; it changes subject |
| `owner_can_go_from_new_trip_to_every_export` | The full journey walk — the highest-value single test in the suite |

*(A reclassification worth naming: `streamlit_entry_point_renders` was counted as a dying Streamlit artifact
when the options were framed. Counting each test precisely, it is a subject change rather than a deletion,
which makes the split 14 / 3 / 1 rather than 13 / 3 / 2.)*

### Dies with no replacement — 1

`money_on_screen_is_not_read_as_maths` — Streamlit reads a pair of `$` as inline LaTeX and silently
swallowed the amounts in `US$0.1300 / US$10.00`. That is a Streamlit defect, `shared.plain()` is its
workaround, and both disappear. React has no such behaviour.

## The four decisions

| # | Question | Decided |
|---|---|---|
| 1 | The 18 `AppTest` tests | **Ported down to their lowest layer now, then deleted with `views/`** |
| 2 | API contract tests | **`unittest` at two levels** — dispatch directly, plus a real server on port 0 |
| 3 | Frontend tests | **Vitest for units**; the parity harness doubles as the journey walk |
| 4 | The green command | **One `scripts/check.py`, one exit code** |

Two further items the ticket lists were already settled elsewhere and are restated rather than re-decided:
**split and settlement math is tested in Python** as pure `unittest` against `travel_planner/split.py`, per
`WF-018`'s no-Streamlit/SQLite/HTTP rule; and **the historic regression runner stays a separate script**,
now called by `check.py` rather than duplicated into it.

## 1. Port down before deleting, so coverage never dips

Each behaviour is asserted at its new home **before** the `AppTest` file is removed. Deletion happens with
`views/` at 8-stage parity, as `WF-022` set out.

This deliberately does not take up the alternative of keeping `AppTest` green until parity: `WF-022`
explicitly dropped that obligation, and re-adopting it would constrain every schema change to keep a UI
nobody will use passing.

Accepted costs: it is real work now, before any webapp code exists; two ported assertions will look inert
until React exists to render what they describe; and the full journey walk has no home until either the
frontend or the API harness can drive it.

## 2. API contract tests, two levels, no new dependency

```python
# level 1 — dispatch, no socket, instant
dispatch("discover_places", {"trip_id": t})     # → jsonable payload

# level 2 — a real server, ephemeral port
HTTPServer(("127.0.0.1", 0), Handler)           # + urllib
```

**Level 1** covers the substance: the literal allowlist, one `jsonable()` contract test per
dataclass-returning method (`WF-019`'s explicit obligation), refusal code → HTTP status, and that **no
endpoint accepts a hash as an argument**.

**Level 2** covers what only a socket can reach, and it is not optional:

- The `Content-Type: application/json` requirement — which *is* the CORS defence.
- The `Host` allowlist — which *is* the DNS-rebinding defence.
- The `GET` download exception, including that bare `GET` reaches downloads **and nothing else**.

Those three are security controls. A guard nobody tests is a guard someone relaxes — and `WF-030` already
recorded that the download routes rest on the `Host` check alone.

Port 0 means no fixed port and no collisions. Accepted: server lifecycle needs careful teardown or state
leaks between cases, and each test needs a decision about which level it belongs at.

This keeps "`unittest` only, no fixtures framework" intact — the convention that has held for 235 tests.
`pytest` + `httpx` was rejected as ergonomics rather than coverage: everything above is reachable from
`unittest` plus `urllib`.

## 3. Frontend: Vitest, and the parity harness earns its keep twice

**Vitest for unit tests** — it ships with Vite, so it is one dev dependency and no new config. It targets
the logic most likely to break, and most expensively:

- `StageGate` rendering the blocked explanation **in place** rather than redirecting — a Phase 1 decision no
  screenshot can verify.
- The **whole-draft** setup rule, whose failure mode is silent data loss (`save_setup`'s 18 fields each
  default to empty, so a partial payload erases what it omits).
- The `jsonable()` round-trip against the hand-written TypeScript types.
- Copy lookups.

**The journey walk comes free.** `WF-025`'s parity gate must already navigate all 9 routes in both themes and
both languages to shoot its 36 baselines. That navigation *is* the end-to-end walk; asserting a few things
along the way costs nothing extra, and it means no second browser toolchain to install and pin.

Playwright was rejected on overlap: it would largely duplicate the screenshot harness, and e2e suites are
the flakiest thing in most projects — the exact failure mode `WF-025` already worried about, where a flaky
gate gets switched off.

Accepted: a failing navigation says the walk broke without always saying why, and a baseline refresh now
touches the walk too.

## 4. One green command

```
uv run python scripts/check.py

  1  unittest discover -s tests          235+ tests
  2  run_optimizer_regressions.py        27 historic cases
  3  validate_regression_fixtures.py     fixture catalogue structure
  4  build_project_graph.py --check      graph integrity, free
  5  npm --prefix web run typecheck && lint && test
  → one exit code
```

Three properties that matter:

- **It reports stage by stage.** A single exit code is useless if a failure does not say which stage failed.
- **Frontend steps skip cleanly when `web/` does not exist**, so the command works today and after the port
  without editing.
- **The individual commands stay usable.** `check.py` is for before a commit; a tight edit loop still runs
  the one suite it cares about, and `CLAUDE.md` keeps listing them.

Steps 3 and 4 are the ones most likely to be skipped by hand — and the graph check is exactly what caught
staleness this week, so folding it in is the point rather than a detail.

Accepted: it crosses toolchains, so it must fail clearly when `uv` or `npm` is missing rather than
mysteriously.

## The work this creates

| Item | Scale |
|---|---|
| Behaviours to port down before deletion | **14** |
| Frontend tests to write | **3** behaviours + the units above |
| Tests that simply die | **1** (`money_on_screen_is_not_read_as_maths`) |
| API contract tests | 1 per dataclass shape (18) + allowlist + error map + 3 security guards |
| New dev dependencies | **1** (`vitest`) |
| New scripts | `scripts/check.py` |
| Tests deleted at parity | the 18 `AppTest` cases, with `views/` |

## Explicitly not decided here

- Whether `check.py` runs the frontend steps in parallel with the Python suite.
- Whether the parity harness's walk assertions live with the baselines or beside the Vitest suite.
- What replaces `TOURIST_DB_PATH`-patched temp dirs for API-level tests — probably the same mechanism, but
  the transport adds a server per test that the current pattern does not.
- Whether `deterministic_signature` gets an explicit transport-level test asserting the API cannot reorder or
  re-serialize its way into a different proposal. The ticket raises the risk; the guard is not specified.

## What this hands downstream

| Ticket | Consequence |
|---|---|
| `Lock the Phase 2 slice plan and validation scorecard` | `scripts/check.py` is the scorecard's green signal, and porting 14 behaviours is a sequenceable item that must precede deleting `views/` |
| `Define the visual parity gate for the Tailwind rebuild` | Its harness gains a second job — the journey walk — so its 36-baseline navigation is now load-bearing for behaviour coverage too |
| `Prototype the merged cost and split screen` and the other prototypes | Prototypes stay throwaway and untested by decision; only shipped elements get Vitest coverage |
| `Decide the migration path for existing trips and splitter data` | The backup-JSON reader needs a test, and it is pure Python, so it lands in the existing suite with no new machinery |
