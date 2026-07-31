---
id: WF-036
title: Prototype the ranked candidate card grid
status: open
labels:
  - "wayfinder:prototype"
parent: WF-MAP-002
assignee:
blocked_by:
  - WF-025
  - WF-028
  - WF-035
---

# Prototype the ranked candidate card grid

## Question

What does a comparable, explainable ranked place card look like, and how does a grid of them read when the owner
is choosing what to do on the trip?

## Context

The element inventory named this the biggest design gap in the whole redesign — bigger than the map — and also
the thing the port **unlocks** rather than ports.

- `views/places.py:147-155` is a selectbox plus one detail panel **because Streamlit cannot lay out comparable
  cards**, not because that is the right interaction. The inventory's instruction is explicit: do not port the
  selectbox. The card grid is the point of the redesign for this stage. `places.py` is 400 lines and rated
  nearly all-new.
- Auto-Bill supplies parts but no whole: a selectable card skin, a framed insight card, a media wrapper, and
  badges — but **no card in the file exceeds about 120px or carries nested explanation**. So the visual language
  extends to cover this, but the element itself is new and must obey the token contract rather than invent.
- What a card must carry, from the Phase 1 decisions: fit, best time to visit, source-specific ratings and
  reviews, effort, price, pros, cons, reliability, and a per-card explanation of *why* it scored as it did.
  Ranking runs on fixed 30/20/20/10/15/5 weights with protected exploration slots, and the explanation is a
  product promise, not debug output.
- Selection is four states, not a checkbox: Must do, Interested, Maybe, Not for this trip. Nothing is
  pre-selected, by decision. Every candidate stays reachable through Browse All, and coverage gaps by source,
  category, and area are reported honestly — the UI must never imply exhaustive real-world coverage.
- Explanations are collapsed today so the decision buttons stay above the fold; that is a must-survive
  behaviour. A place is always named, never shown as a truncated `place_id`.
- Candidates carry an explicit evidence status — `verified` / `stale` / `unavailable` / `error` — and a stale
  result may be backed by an expired cache entry while a verified one never is. That status has to be legible on
  the card without shouting, and it is a word-valued state, so by the rule from the feedback-element ticket it
  gets a pill rather than a metric tile.

Produce a throwaway prototype with realistic candidate data and link it from this ticket, including the layouts
rejected and how the grid degrades on a phone.
