---
id: WF-033
title: Lock the Phase 2 slice plan and validation scorecard
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
blocked_by:
  - WF-022
  - WF-023
  - WF-024
  - WF-026
  - WF-027
  - WF-028
  - WF-029
  - WF-030
  - WF-031
  - WF-032
---

# Lock the Phase 2 slice plan and validation scorecard

## Question

In what order is Phase 2 built, and what are the hard gates that decide the merged webapp is done rather than
merely finished?

## Context

The final ticket on the map: it converts every closed decision into a build order and a pass-or-fail scorecard,
and it is the handoff artifact the destination names.

- Phase 1's equivalent is the precedent to follow and to improve on: it separated an implementation-ready
  specification from a proven working MVP, required reproducible validation bundles, and defined six minimal
  vertical slices before certifying every hard runtime gate against the pilot. Its rule — complete a slice
  vertically with its own runnable check before starting the next — is why slices 1–5 are evidenced today.
- The calendar is real. Charted 2026-07-31; the Taipei pilot runs 29 December 2026 to 4 January 2027. The freeze
  ticket sets the go / no-go date, and this ticket must sequence the slices so that date is meetable.
- Slice 6 is inside Phase 2 by the locked frame — non-AI quick actions first, then optional constrained GenAI
  revision, then the live pilot — and it is built only in React. So this plan covers both the port and the
  remaining Phase 1 functionality in one order.
- Gates that already exist and must keep passing: 202 unit tests, the 27 historic optimizer regressions, the
  fixture-structure validator, the `en`/`th` key-parity assertion, graph integrity via
  `scripts/build_project_graph.py --check`, the provider-access redaction self-test, and the US$10 monthly cap
  with its $8 warning. New gates arrive from the visual-parity ticket and the test-strategy ticket.
- The rule against silent behaviour change is a gate too: a UI port that alters ranking, scheduling, or the
  active plan is a regression, and the map puts that explicitly out of scope.

Decide at least: the ordered vertical slices with the runnable check that closes each; which slice first makes
the webapp usable end to end; where the split ledger lands in that order; the retained-evidence requirements
per slice; the full hard-gate list for pilot-ready; and what is explicitly deferred past the pilot.
