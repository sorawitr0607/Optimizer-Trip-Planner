---
id: WF-036
title: Prototype the ranked candidate card grid
status: closed
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


## Built 2026-08-06 as the swipe deck WF-005 specified

The owner asked for it directly, so the deferral ends here. Built against `WF-005`'s
2026-07-28 decisions rather than designed afresh.

**Most of it already existed.** `WF-005` asked for "four highest-ranked unseen
candidates followed by one protected exploration candidate", with rated cards keeping
their decisions and only unseen cards reordering. The core already builds exactly
that: verified on the real 832-candidate catalogue as ranked ×4 then
`protected_exploration`, repeating, with all 111 decided places absent. 86 cards carry
the exploration role. What was missing was only the interface — `/places` rendered a
selectbox, which is what the Context section above called the problem.

**Swipe is the accelerant, not the mechanism.** Every action is a real button and the
arrow keys work, because a gesture-only deck excludes keyboard and screen-reader
users. That also makes the whole contract testable under `renderToStaticMarkup`: the
queue order, the required card content, the exploration label, the gallery counter and
the exhausted state are all asserted, which a gesture-only deck could not be. The
gesture maps right to `interested` and left to `not_for_trip`, matching the button
order so the direction is learnable from the layout.

**Imagery, which was the blocker, is now free.** `WF-005` requires "permitted imagery"
on every card, and until the Wikidata provider landed the same day there was none
without paying Google US$0.007 a photo. `prop=images` on a Wikipedia article gives a
free list — 27 for Chiang Kai-shek Memorial Hall — so the gallery costs one extra
request and nothing else. Capped at six, rasters only, curated `P18` first.

**`WF-005`'s minimum card content** is rendered as one labelled row per topic: visit
estimate, feasibility, effort and access, crowd and tourist-trap signals, cost and
reservation, plus the score, the name, the free description with CC BY-SA attribution,
and an explicit note that an exploration card is shown to widen the search rather than
because it scored highly.

**The page around it changed too.** The deck first landed 620 px down, behind the
coverage report — which is how this screen came to be called unfriendly. Coverage is
how you audit a discovery run, not how you choose a place, so it is collapsed behind a
one-line summary and the whole deck now fits one screen.

Not deferred any longer, and `WF-021`'s "biggest design gap" is closed. Evidence in
`artifacts/validation/2026-08-06-swipe-deck/`.
