---
id: WF-032
title: Prototype the itinerary day screen in the new design
status: open
labels:
  - "wayfinder:prototype"
parent: WF-MAP-002
assignee:
blocked_by:
  - WF-025
  - WF-028
---

# Prototype the itinerary day screen in the new design

## Question

What does the active plan's day view look like in the Auto-Bill visual language — day summary, activity and
leg timeline, numbered map, and variant or version context — when Auto-Bill has no element resembling any of
them?

## Context

The second highest-risk screen, and the one the owner looks at most during the trip. Throwaway prototype; the
question is arrangement and legibility, not code.

- What exists today: `views/itinerary.py` renders a phone-first day summary, an activity-and-leg timeline, and
  a numbered map, all read from `build_export_snapshot()` so the screen and the exports cannot disagree. The
  poster is 9:16 by decision, so the phone layout and the poster already share a shape worth reusing.
- The optimizer returns three variants — `best_balance`, `relaxed`, `more_highlights` — each independently
  revalidated, and with no trip dates it returns a stay recommendation instead of a timetable. The screen must
  handle both, plus the labelled-valid-incumbent case when the solver hits its time limit.
- Plans are append-only: `active_plans` holds exactly one version per trip, restoring an old plan creates a new
  version, and `revision.py` keeps at most one pending draft while showing before-and-after consequences. Some
  of that history and preview context belongs on or beside this screen.
- Auto-Bill's nearest elements are the hero banner, stat cards, and list rows — none of which is a timeline or
  a map. Note that the hero banner has **no** `3 / 1` aspect ratio: its README claims one, but `aspect-ratio`
  appears nowhere. The real rule is a locked `260px` height with `minmax(320px, 34%) minmax(0, 1fr)` columns
  (`index.css:460-484`). Port the fixed height, not a ratio.
- The element inventory found the numbered map to be the **one** planner element the Auto-Bill visual language
  cannot reach — it has no spatial primitive, no map dependency, and no analogous visual anywhere. So this
  prototype also has to answer what draws the map, and the offline asset policy ticket has to answer whether
  its tiles can exist on a plane. Marker colours are duplicated as text labels today for accessibility; that
  is a load-bearing behaviour, not decoration. The Not-yet-specified list already flags that new elements must be
  designed inside the existing visual rules rather than imported from elsewhere.
- Status labels carry emoji in the current UI, and `_labels()` strips pictographs on the export path because no
  Unicode font covers them; the wording alone must still carry the state. The same constraint applies to any
  status chip designed here.

Produce a throwaway prototype and link it from this ticket, along with what was rejected.
