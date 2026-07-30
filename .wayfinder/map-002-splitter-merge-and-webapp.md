---
id: WF-MAP-002
title: Merge the bill splitter and rebuild the planner as a webapp
status: open
labels:
  - "wayfinder:map"
tracker: local-markdown
---

# Merge the bill splitter and rebuild the planner as a webapp

## Destination

Reach a decision-complete, implementation-ready Phase 2 specification for two joined changes: absorbing
`Auto-Bill-Splitter` into this repository as a group split ledger linked to the existing cost ledger, and
replacing the Streamlit UI with a local React webapp whose visual design is anchored to Auto-Bill's.
Implementation begins only after this map has no unresolved decisions. Prototypes produced while
resolving tickets are throwaway artifacts, not the build.

## Notes

- Domain: local, owner-led trip planning plus group expense splitting, one repository, Python planning
  core behind a thin local API, React frontend.
- Locked by the destination interview (2026-07-31), not open for re-litigation inside tickets:
  - The Python planning core, `actions.py`, and `store.py` stay as they are. A thin local HTTP layer
    exposes `PlannerActions`. React replaces `views/*.py` and `app.py` only. The deterministic
    optimizer, hash gates, append-only history, and the 202 tests survive the redesign.
  - **Two linked ledgers.** Planner cost rows stay the budget/estimate truth; the split ledger records
    actual group spend keyed to the trip. Reconciliation between them is an explicit open problem with
    its own ticket, not a detail.
  - Everything lands in `Optimizer-Trip-Planner` (`api/` + `web/` beside `travel_planner/`).
    `Auto-Bill-Splitter` becomes a read-only donor — lift its tokens, elements, and split math — then
    it is archived.
  - The design tokens are **rebuilt** in Tailwind / CSS modules rather than lifted verbatim, so visual
    parity with Auto-Bill is a hard, gated requirement: same palette, same hard offset shadows, same
    fonts, same elements. Drift is a defect, not a style choice.
  - Bilingual `en`/`th` is mandatory. The `ui/text.py` copy ports to the webapp, the core keeps emitting
    stable codes, and the key-parity test keeps running. Auto-Bill-derived elements gain Thai strings
    they never had.
  - Local-only, single owner: `localhost` API plus local frontend, SQLite on disk, no accounts, no auth.
  - Streamlit is frozen at slices 1–5 as the fallback Taipei pilot vehicle. Slice 6 (non-AI quick
    actions, constrained GenAI revision, live pilot) is built **only** in React — never twice.
- The Phase 1 "why" lives in [`map.md`](map.md) and its 17 closed tickets. Read the relevant ticket
  before contradicting a scoring weight, optimizer rule, schema choice, or provider policy. This map
  may re-decide the UI; it may not silently re-decide Phase 1's planning contracts.
- Consult Wayfinder, Grilling, and Domain-modeling for decision work; Prototype for the screen tickets.
- Refer to tickets by linked title, never by a bare ID.

## Decisions so far

<!-- Closed-ticket index. The detailed decision belongs in its ticket. -->

- [Extract the Auto-Bill design token contract](tickets/020-extract-the-auto-bill-design-token-contract.md) —
  The visual language is captured exactly in [`020-auto-bill-token-contract.md`](artifacts/020-auto-bill-token-contract.md):
  23 light / 21 dark custom properties, a zero-blur hard-offset shadow scale that must **replace** Tailwind's
  soft default rather than extend it, 5 desktop-first max-width breakpoints, and a 13-country inline accent
  override — plus 7 unresolved ambiguities (the dark accent triple is dead code, two radius systems coexist,
  both fallbacks return blue rather than the house red, bold monospace is faux) and a large body of off-token
  JSX literals that a CSS-only port would silently lose.
- [Inventory the Auto-Bill elements each planner stage needs](tickets/021-inventory-the-auto-bill-elements-each-stage-needs.md) —
  Auto-Bill supplies 41 reusable elements; 18 planner elements have no counterpart but only the numbered map
  falls outside what the visual language can reach. The biggest design gap is the ranked candidate card, which
  the port *unlocks* rather than ports; the biggest surprise is that Auto-Bill has no inline feedback element
  at all against the planner's 59 status calls, while the US$10 spend meter is a free adapt of the per-person
  meter. 14 of 23 load-bearing behaviours are product decisions that must survive, 9 are Streamlit artifacts
  that die — 3 of those leaving a rule behind. Full matrix and the six-item dead-weight list are in
  [`021-element-inventory-matrix.md`](artifacts/021-element-inventory-matrix.md).
- [Define the split ledger model and where its math lives](tickets/018-define-the-split-ledger-model-and-where-its-math-lives.md) —
  A split row records who paid (defaulting to the cardholder), the split mode plus traveller-id participants
  with shares recomputed on read, an amount in its original currency with an optional permanent `actual_thb`
  lock, an owner-defined tag, and optional day and place links. All math lives in a new pure
  `travel_planner/split.py`; settlement is a star through the cardholder with fronted cash netted off, which is
  exact. Rows are editable and void rather than delete — so the ledger needs **no** append-only discipline.
  Settling up is not recorded, so balances stay trip-to-date totals.

## Not yet specified

<!-- In-scope fog: suspected questions not yet sharp enough to ticket. Graduates as the frontier advances. -->

- How a 34-second Overpass discovery run reports progress across an HTTP boundary that a Streamlit
  rerun used to hide. Sharpens once the API contract is locked.
- Whether a trip that is fully settled in real life gets any marker at all, given that settlement payments
  are deliberately not recorded — and whether that matters once the trip is over rather than mid-trip.
- Whether voided split rows appear in the PDF and Excel exports, or only in the app where the owner can see
  why a total moved.
- How slice 6's free-text GenAI revision presents itself in the new design, and whether its typed-intent
  preview survives as a modal, a diff panel, or something else.
- Whether per-person cost data should feed anything upstream (affordability in ranking, budget caps in
  optimization) or stay strictly downstream reporting.
- Whether the donut and vertical bar charts have any planner use at all. The element inventory found no
  distribution the planner charts today; the only candidate is the ranking dimension breakdown, which is
  already a table with an explicit per-dimension maximum.
- Archival mechanics for the `Auto-Bill-Splitter` repository, and how lifted code is attributed once its
  origin repo is read-only.

## Out of scope

- Hosted deployment, accounts, per-traveller login, remote member voting, notifications. These stay a
  later phase; the destination is explicitly local and owner-led.
- Rewriting the planning core, optimizer, or ranking in JavaScript or TypeScript.
- Building any slice 6 feature in Streamlit.
- Changing optimizer, ranking, or scoring behaviour as part of the redesign. A UI port that alters
  planning output is a regression, not an improvement.
- Purchasing flights, accommodation, tickets, or subscriptions on the user's behalf.
