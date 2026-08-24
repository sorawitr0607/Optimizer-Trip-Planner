---
id: WF-050
title: Decide how feedback-driven dashboards show progress and estimates
status: closed
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide how feedback-driven dashboards show progress and estimates

## The feedback was about state, not decoration

Owner testing found actions whose result appeared elsewhere or much later: a paid photo
updated another card, discovery drew card skeletons before a catalogue existed, itinerary
generation could be silent for minutes, plan-derived cost rows saved as zero, and empty
place lanes still appeared as choices. The itinerary also had the same data as the four
reference dashboards but did not coordinate its map, clock and timeline as one surface.

## Decision

- A stage advances only from reported work. `web/src/stages/OptimizePage.tsx` shows the
  dot-and-line list immediately for every preview/rebuild path; `on_variant` remains the
  pure observer in `travel_planner/optimizer.py`, with deterministic output pinned by
  `tests/test_optimizer.py`. Route passes move into `travel_planner/actions.py` so the
  browser queues one job; forced refresh remains one pass.
- A card action uses the card's own id. `web/src/stages/PlacesPage.tsx` invalidates the
  tapped card after a paid photograph arrives, hides discovery skeletons until discovery
  has returned, and omits every zero-count lane.
- The itinerary is an interactive view over the one active export snapshot.
  `web/src/stages/ItineraryPage.tsx` coordinates URL-backed day/view state, the live clock,
  selectable map pins and timeline rows; wide screens show both panels and phones switch.
  `web/src/stages/PlaceMap.tsx` supplies keyboard-operable timed pins. Readiness, planned
  costs and actual bills remain authoritative on their existing routes rather than being
  duplicated into the dashboard.
- `web/src/stages/CostsPage.tsx` turns the active plan's non-zero counts into editable THB
  seeds at Budget, Value, Standard, Premium or Luxury. A tier selection never writes;
  explicit Save upserts rows by `related_item_id`, accommodation assumes two people per
  room, and setup dates—not preparation days—determine nights.
- Visual status already conveyed by controls is not repeated in prose. Setup loses its
  step/status sentence, Places loses its free/complete/deck helper lines, and itinerary
  loses its one-snapshot explanation. Safety, provisional-result and paid-action wording
  stays.

## Resolution comments

### 2026-08-24

Built the decision without a second dashboard or money model: the existing export,
checklist, map, cost and split components are the data boundaries. The four reference
dashboard exports pass their own structural checker. Focused web tests cover the loading
list, the sole route-accept action, empty lanes, tier values and the interactive itinerary;
mobile and desktop browser checks cover pin-to-clock behavior, URL day persistence,
simultaneous wide panels and horizontal overflow.

The capture seam in `web/src/shared/AppShell.tsx` also marks the visible build timestamp as
volatile only during baseline capture. The real interface keeps the diagnostic while
unchanged tablet screens stop drifting on every rebuild.

## Related

- [Decide what the journey must explain before it asks](048-decide-what-the-journey-must-explain-before-it-asks.md)
- [Decide what the interface owes a reader who is not the owner](049-decide-what-the-interface-owes-a-reader-who-is-not-the-owner.md)
- [Decide cost-and-split reconciliation rules](023-decide-cost-and-split-reconciliation-rules.md)
