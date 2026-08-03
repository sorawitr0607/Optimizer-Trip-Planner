---
id: WF-033
title: Lock the Phase 2 slice plan and validation scorecard
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
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

## Resolution comments

### 2026-08-03 — Locked. The map is decision-complete.

The slice table, the full gate list and the deferred set are in
[`033-phase-2-slice-plan-and-scorecard.md`](../artifacts/033-phase-2-slice-plan-and-scorecard.md).

**A scope cut is recorded here by owner decision: the PDF and the 9:16 poster are dropped.** Measured, the
rendered pair costs ~350 lines, **2 of 4 runtime dependencies** (`pillow`, `fpdf2`), **the entire font
apparatus** — merged Noto TTF, `fonttools` recipe, multi-MB binary, licence record, `resolve_font()`,
`TOURIST_EXPORT_FONT` — and **16 of the 17 hexes** behind deviation D7. `pyproject.toml` drops to `streamlit`
+ `xlsxwriter`. It is defensible rather than a retreat because `WF-013` records that the owner produced the
four reference PDFs themselves by exporting the `.xlsx`, so a PDF is already a rendering of the workbook in
the established workflow. Lost: the poster, with no substitute, and the PDF as an automatic artifact.
**Tests: 235 → 231**, and three PDF-only tests assert content rather than rendering, so they **re-base onto
the workbook** instead of being deleted.

- **Slice order: S0 scope cut → S1 foundation → S2 the merge → S3 cheap journey screens → S4 the expensive
  two → S5 slice 6 and the rest → S6 parity and deletion.** Each closes with its own runnable check, per the
  Phase 1 rule that made slices 1–5 evidenced.
- **Two answers conflicted and the conflict is recorded rather than hidden.** The chosen strategy was
  thin-walkable-path-cheap-first, which put money at S4; the chosen split-ledger placement was early. Resolved
  by moving money to **S2** and shifting the journey screens back one — cheap-before-expensive still holds
  *within* the journey, and the merge is proven early. Consequences accepted: `places` and `itinerary` are
  stubs until S4; the irreversible schema bump lands at S2 when coverage is thinnest, which makes `WF-024`'s
  refuse-on-failure pre-bump copy load-bearing rather than ceremonial; and S1 must ship routing and
  `<StageGate>` because S2 depends on them.
- **S4 is where the webapp first works end to end**, and it is what the 1 November checkpoint measures.
- **Evidence per slice** follows the established convention: `artifacts/validation/<date>-slice-<n>/` with
  numbers in `manifest.json`, prose in a notes file, one line linking them — because appending long evidence
  into a ticket starved `WF-012`'s extraction twice.
- **The gate list is compiled in full**: the eight inherited gates (with **231** tests, not the 202 this
  ticket was charted with) plus eight new ones, and the rule that a port altering ranking, scheduling or the
  active plan is a **regression** rather than a change.
- **Deferred past the pilot:** constrained GenAI revision, the ranked candidate card grid, voided rows in
  exports, and per-person figures feeding upstream.
- **The calendar, stated plainly:** 13 weeks to 1 November, seven slices, under two weeks each, from zero
  webapp code — and gate 1 not assessable until S4. Three things make it survivable: S0 removes work from
  every later slice; the POC keeps working until S6 so the trip can be planned on Streamlit meanwhile; and the
  1 November call is a checkpoint whose failure mode `WF-022` already decided, and it is a spreadsheet.

**`WF-MAP-002` now has no unresolved decisions, which is the destination it named — so the Phase 2 code
freeze lifts and S0 may be built.** `WF-036` stays open by decision rather than omission: the card grid is
deferred past the pilot.
