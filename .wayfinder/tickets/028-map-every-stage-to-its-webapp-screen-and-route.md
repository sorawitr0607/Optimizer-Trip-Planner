---
id: WF-028
title: Map every Streamlit stage to its webapp screen and route
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
blocked_by:
  - WF-021
  - WF-026
---

# Map every Streamlit stage to its webapp screen and route

## Question

What is the webapp's information architecture — the routes, the navigation, the landing behaviour, and where
the split ledger sits in the journey?

## Context

- Nine stages exist today: setup, places, optimize, itinerary, costs, readiness, evidence, revise, plus the
  split ledger being merged in. `st.navigation` renders them in the sidebar, with the trip context directly
  under the stages and the language control at the foot; `app.py` is about 100 lines and owns only what every
  stage shares — the language, the selected trip, the journey state.
- The landing page is deliberately not a fixed home: it is the stage that needs attention, so a returning
  owner sees the itinerary rather than the setup form. `shared.journey()` computes that, and
  `shared.require(stage, trip)` renders one clear next step and returns False when a stage is not reachable,
  so a view explains itself instead of erroring. Both behaviours are decisions from Phase 1, not incidental —
  whatever the router does must reproduce them.
- Auto-Bill's architecture is the opposite shape: a wizard until setup completes, then one dashboard forever
  (`src/App.jsx:108`), with filters and a modal instead of navigation. Its visual language therefore has no
  precedent for a nine-destination navigation, and the map's Not-yet-specified list flags this.
- The trip selector is a sidebar widget and multiple trips exist, so a route needs to carry which trip it
  refers to, or the app needs an equivalent of the selected-trip context.
- Setup is five editable steps rather than one form, by decision, and each step's city list depends on the
  chosen country. Whether that becomes five routes, one route with steps, or Auto-Bill's wizard shell is part
  of this ticket.
- Some stages are read-mostly panels (evidence, readiness) and some are heavy interactions (places with 400
  lines of view logic, revise with version history and restore).

The element inventory has already separated product behaviour from Streamlit accident: **14 of 23 load-bearing
behaviours are decisions that must survive** the port — among them `journey()` picking the landing stage,
`require()` explaining rather than erroring, the five autosaving setup steps, the country-to-city dependency,
nothing pre-selected, explanations collapsed so decision buttons stay above the fold, every paid action stating
its cost immediately before the spending button, disabled actions always saying why, and a place always named
rather than shown as a truncated `place_id`. **9 are Streamlit artifacts that die**, but three leave a rule
behind. Work from that list rather than re-deriving it:
[`021-element-inventory-matrix.md`](../artifacts/021-element-inventory-matrix.md). The inventory also rates
`costs.py`, the app chrome, `optimize.py`, and the `setup.py` shell as nearly free, and `places.py` and
`itinerary.py` as nearly all-new — which is a sequencing input for the slice plan.

Decide at least: the route table and URL shape; whether trip selection is a route parameter or ambient state;
how journey gating and the attention-based landing are expressed client-side without duplicating the rules;
where the split ledger and the cost ledger sit relative to each other; and what the navigation looks like in
the Auto-Bill visual language on both desktop and phone.

## Resolution comments

### 2026-07-31 — Decided through the IA interview

Route table, gate mapping, and the consequences for other tickets are in
[`028-webapp-information-architecture.md`](../artifacts/028-webapp-information-architecture.md).

- **9 stage routes under `/trips/:tripId/`, resolving to 5 gate keys, in 2 sections.** The eight ported
  paths keep the slugs `st.navigation` already assigns, so the stage segment of every URL is unchanged.
- **The trip id lives in the path**, not in ambient context. Every one of the 51 methods takes `trip_id`,
  and TanStack Query keys must include it — reading it from `useParams` prevents a bug class where ~51
  query keys each have to *remember* the ambient trip, and one omission serves another trip's cached data.
  Refresh and deep links then work with no persistence layer at all.
- **One `<StageGate>` wrapper, and exactly one redirect.** This is where a router would have quietly broken
  Phase 1: `shared.require()` **does not redirect** — it renders one clear next step in place and returns
  False, so a view explains itself. A redirect explains nothing and makes the URL disagree with the click.
  The attention-based landing *is* a redirect, but only from `/`. `StageGate` reads `journey()`'s answer
  and renders; it never decides.
- **Setup stays one route with five steps in state**, inside Auto-Bill's wizard shell. `WF-026` already made
  the draft one object sent whole, so five steps are five views over one piece of state. Two adaptations are
  unavoidable: the step indicator **hardcodes four steps in its class names** (`.wizard-progress-4`,
  `.progress-step-4`, …) so the family must be renamed to five, and clicking a step navigates **backwards
  only** — which suits a wizard whose later steps depend on earlier answers, so it is kept rather than fixed.
- **Costs and split are two cross-linked screens, on the owner's distinction:** costs is the *estimated*
  cost for the drafted plan; split splits the bill for *actual cost that happened*; values can be linked
  and edited for convenience. The split screen therefore gets Auto-Bill's full surface — the 694-line
  `TransactionModal`, participant chips, settlement grid, cardholder selector — with no estimates table
  competing for the space. **One overlap is flagged, not resolved:** `costs.py` is not purely estimates
  (`PAYMENT_STATES = ("estimate", "committed", "paid")`, and a paid row locks `actual_thb`), so a paid cost
  row is already actual money. That boundary belongs to `Decide cost-and-split reconciliation rules`.
- **Removing a split row voids it, and the button still says remove.** Add, edit and remove all exist as
  asked and the modal is lifted intact, while `WF-018`'s void-not-delete holds for its stated reason: the
  voided row is *why* a total that moved can be explained. Needs a hide/show control, and the wording must
  make clear it does not destroy the row.
- **Navigation adapts Auto-Bill's sidebar shell** (element 17), keeping today's two sections, trip context
  under the stages, and language at the foot. Only the content changes, so the visual language is honoured
  rather than extended. **The one real gap:** at 992px `.sidebar` goes static, which for a nine-item
  navigation means a long list above the content on every phone — a drawer must be designed, not lifted.
  Auto-Bill's own shape (wizard, then one dashboard forever) was rejected because it destroys the journey
  model and rebuilds the donor's 2,183-line dashboard by construction.

**This changes `Prototype the merged cost and split screen`'s premise — there is no merged screen.** Its
substance survives across two screens plus the link action, and a dated note has been added to its Context;
its title is now misleading.
