---
id: WF-010
title: Turn historic trip failures into regression fixtures
status: closed
labels:
  - "wayfinder:task"
parent: WF-MAP-001
assignee:
blocked_by:
  - WF-006
  - WF-008
---

# Turn historic trip failures into regression fixtures

## Question

Convert the Japan, Fukuoka, Kunming/Dali, and Shanghai failure reports plus workbook context into compact executable scenarios that fail when the planner repeats a closure, poor timing, unrewarding walk, backtracking, illegal transport, tourist-trap, meal, crowd, access, or weather mistake.

## Confirmed decisions

### 2026-07-29 — Compact provider-independent JSON fixtures

- Encode each historic mistake as a small JSON fixture consumed by one generic regression runner rather than recreating an entire trip.
- Freeze only the relevant trip setup, candidate, opening/best-time, route, effort, weather, crowd, access, and owner-choice facts. Tests never call live providers.
- Each fixture expects either a safe scheduled result or an explicit `cannot_fit` or accepted-tradeoff result with the exact rule, reason, and consequence.
- Keep city and place names as scenario provenance, while rule IDs and assertions remain destination-independent so the same failure cannot return in another country.

### 2026-07-29 — Real planner inputs with invariant-based expectations

- Give every fixture four top-level sections: `metadata`, `planner_input`, `expected_rules`, and `acceptable_outcomes`.
- `metadata` carries a stable fixture ID, schema version, failure class, and source-trip provenance. `planner_input` uses the same normalized snapshot contract as the real optimizer rather than a test-only model.
- `expected_rules` names the destination-independent rule IDs and required or forbidden behaviour. `acceptable_outcomes` permits any safe schedule, explicit `cannot_fit`, or fully explained accepted tradeoff that satisfies those rules.
- Assert exact times or ordering only for a true fixed anchor or when the historic failure specifically concerns that window; otherwise test invariants and metric bounds so scoring improvements do not create brittle failures.

### 2026-07-29 — Atomic root cases plus bounded interaction cases

- Keep one atomic fixture for each of the 20 reported mistakes. Each atomic case isolates one root issue so a failure names the rule that regressed.
- Add only seven interaction fixtures where solving one issue can recreate another: Shibuya hours/view/walking, Odaiba effort/view, Dali hotel backtracking, Erhai permitted mode/heat, Yuyuan/Wukang ordering, Shanghai ferry access/crowds, and rain fallback reoptimization.
- Every interaction names the atomic fixture IDs it covers. This preserves traceability without duplicating complete historic itineraries.
- Store both layers in one versioned catalog until file size or parallel ownership creates a demonstrated reason to split it.

### 2026-07-29 — One deterministic runner contract

- The future generic runner loads a fixture, validates the normalized snapshot, calls the same deterministic optimizer and validator used by the app, and passes only when all `expected_rules` hold and at least one `acceptable_outcomes` branch matches.
- Freeze configuration and seed. Fixture execution performs no provider, database, UI, or GenAI calls.
- A failure reports the fixture ID, violated rule, observed outcome, and smallest relevant result diff. It must not approve a schedule merely because a different high-level score improved.
- The structural catalog validator is executable now. Optimizer-result assertions become active when the Phase 1 core exists; no placeholder optimizer was added just to close this decision ticket.

## Regression assets

- [Historic regression catalog](../../tests/fixtures/historic_regressions.json) — 24 worldwide rule definitions, 20 atomic fixtures, and 7 interaction fixtures.
- [Catalog validator](../../Main/validate_regression_fixtures.py) — dependency-free schema, coverage, reference, status, outcome, and forbidden-key checks.

Run:

```bash
python3 Main/validate_regression_fixtures.py
```

Expected result:

```text
PASS: historic regression catalog (24 rules, 20 atomic, 7 interaction)
```

## Acceptance evidence

- All 20 owner-reported Japan, Fukuoka, Kunming/Dali, and Shanghai failures have an atomic fixture.
- Interaction coverage is limited to the seven combinations where route, timing, fatigue, access, or fallback decisions affect one another.
- Place and trip names appear only as provenance and synthetic test subjects; the asserted rules are destination-independent.
- Fixtures contain no credentials, live calls, raw provider responses, or claims about current venue operations.
- The catalog validator passed on 2026-07-29.

## Resolution

The historic failures are now a compact, provider-independent regression specification. This ticket closes the fixture design and catalog-validation decision; execution against the real optimizer remains a Phase 1 implementation acceptance gate in the implementation handoff.
