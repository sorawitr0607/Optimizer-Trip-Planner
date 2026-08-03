---
id: WF-029
title: Decide the test strategy after Streamlit AppTest dies
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
blocked_by:
  - WF-019
  - WF-026
---

# Decide the test strategy after Streamlit AppTest dies

## Question

Which existing tests survive the UI replacement, what covers the layers that Streamlit's `AppTest` used to
cover, and what is the one command that says the project is green?

## Context

- The suite today is `unittest` only, no fixtures framework, no network, no paid API: 235 tests in about 13
  seconds, run as
  `uv run --locked python -m unittest discover -s tests -p 'test_*.py'`. Alongside it,
  `scripts/run_optimizer_regressions.py` replays 27 historic cases — 20 atomic plus 7 interaction failures
  from four real past trips, encoded in `tests/fixtures/historic_regressions.json` — through the real
  optimizer, and `scripts/validate_regression_fixtures.py` checks the catalogue's structure.
- The core tests are UI-independent by construction and should survive untouched: the planning core is pure
  and every provider is injected via `PlannerActions(path, place_provider=...)`, which is how every test
  avoids the network.
- The UI tests are not: they use `streamlit.testing.v1.AppTest` with `TOURIST_DB_PATH` patched to a temp dir,
  `at.switch_page("views/<stage>.py")` before `at.run()`, and lookups by Streamlit widget key including the
  per-language suffix (`key="country__en"`). All of that disappears with `views/`. Whether those files are
  deleted, kept green for the frozen fallback, or rewritten depends on the freeze decision.
- New layers arrive that nothing currently tests: the HTTP transport, its error taxonomy, its refusal to
  bypass `_spend`, and the frontend itself. Auto-Bill ships no tests whatsoever, so it offers no precedent.
- The project convention is one runnable check per piece of non-trivial logic, not a per-function suite, and
  there is no linter or formatter configured for Python today.
- Determinism is a hard requirement to keep asserted: same input plus same `OPTIMIZER_VERSION` must produce
  the same proposal, checked through `deterministic_signature`. A transport layer that reorders or reserializes
  anything could break that silently.

Decide at least: the fate of the `AppTest` files; whether the API gets contract tests and in what framework;
whether the frontend gets unit tests, end-to-end tests, or neither; how the split ledger and settlement math
are tested and on which side of the boundary; whether the historic regression runner stays a separate script;
and the single green-check command that replaces the current one.

## Resolution comments

### 2026-08-03 — Decided through the test-strategy interview

The per-file survey, the classification of all 18 tests and the work this creates are in
[`029-test-strategy-after-apptest.md`](../artifacts/029-test-strategy-after-apptest.md).

**`AppTest` exposure is 7%, not 80%.** The "12 of 15 files" figure is true at file level and misleading:
each of those files holds one to four `AppTest` tests amid mostly pure ones. Measured per test, **18 of 235**
depend on it, so **217 survive the UI replacement untouched** and this ticket is about 18 tests rather than
12 files.

Classified by the lowest layer that can assert the same thing: **14 are portable** to actions, core or
exports, **3 are genuinely UI**, and **1 simply dies** —
`money_on_screen_is_not_read_as_maths`, which exists because Streamlit reads a pair of `$` as inline LaTeX.
**Most of the 18 were never UI tests**; they assert product logic through a UI because that was the only
surface available, and three are portable only because `WF-028` turned `shared.journey()` into a real
`PlannerActions.journey()` method.

- **Port the 14 down to their new homes before deleting anything**, so coverage never dips, then remove the
  `AppTest` files with `views/` at parity. Keeping them green until then was rejected: `WF-022` deliberately
  dropped that obligation, and re-adopting it would constrain every schema change to keep a UI nobody will
  use passing.
- **API contract tests are `unittest` at two levels.** Level 1 calls the dispatch function directly — the
  literal allowlist, one `jsonable()` contract test per dataclass shape (`WF-019`'s explicit obligation),
  refusal code → HTTP status, and that no endpoint accepts a hash as an argument. Level 2 binds a real server
  on **port 0**, because three things are unreachable without a socket and all three are **security
  controls**: the `Content-Type` requirement that *is* the CORS defence, the `Host` allowlist that *is* the
  DNS-rebinding defence, and the `GET`-reaches-downloads-and-nothing-else rule that `WF-030` left resting on
  the `Host` check alone. A guard nobody tests is a guard someone relaxes. `pytest` + `httpx` was rejected as
  ergonomics rather than coverage.
- **Vitest for frontend units — one dev dependency, since it ships with Vite** — aimed at `StageGate`'s
  in-place explanation (a Phase 1 decision no screenshot can verify) and the whole-draft setup rule (whose
  failure mode is silent data loss). **The journey walk comes free**: `WF-025`'s parity gate must already
  navigate all 9 routes in both themes and languages to shoot its 36 baselines, so that navigation *is* the
  end-to-end walk. Playwright was rejected on overlap and flakiness.
- **One green command, `scripts/check.py`, one exit code**, running the suite, the 27 historic regressions,
  the fixture validator, the graph check and the frontend typecheck/lint/test. It must report stage by stage,
  skip the frontend steps cleanly while `web/` does not exist, and leave the individual commands usable for
  tight loops. Steps 3 and 4 are the ones skipped by hand today, and the graph check is exactly what caught
  staleness this week.

Two listed items were already settled and are restated rather than re-decided: **split and settlement math is
tested in Python** as pure `unittest` against `travel_planner/split.py` per `WF-018`, and **the historic
regression runner stays a separate script**, now called by `check.py` rather than duplicated into it.
