---
id: WF-029
title: Decide the test strategy after Streamlit AppTest dies
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
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
