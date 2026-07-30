---
id: WF-028
title: Map every Streamlit stage to its webapp screen and route
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
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
