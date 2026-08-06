---
id: WF-041
title: Decide how per-day opening hours reach the optimizer
status: open
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide how per-day opening hours reach the optimizer

## One closed day makes a place unschedulable on every day

Found 2026-08-06, immediately after buying real opening hours for the pilot trip.

`actions.opening_intervals()` stores per-date windows — a `by_date` map, one entry
per trip date, which is exactly what a provider returns. The optimizer never sees
them. `_optimizer_input` emits a single `opening_interval` fact per place: **one
window for the whole trip, or nothing at all.**

So a place whose hours differ across the trip, including any place shut on one
single day, gets `interval: None` with `reason: "CLOSED_ON_A_TRIP_DATE"`, no fact is
emitted, and the optimizer treats it as `OPENING_UNVERIFIED` and refuses to schedule
it on **any** day.

Measured on the real Taipei trip, 2026-12-29 to 2027-01-04. **2027-01-04 is a
Monday**, and five of thirteen chosen landmarks close that day:

| Landmark | Real hours | Closed |
|---|---|---|
| Red House | 11:00–21:00 | 2027-01-04 only |
| Taipei Fine Arts Museum | — | 2027-01-04 only |
| Taipei Confucius Temple | — | 2027-01-04 only |
| Beitou Hot Spring Museum | — | 2027-01-04 only |
| Botanical Garden herbarium | 09:30–16:30 | 2026-12-29 and 2027-01-04 |

Red House is open **six of the seven trip days** and is scheduled on none of them.
Every one of the five reports `OPENING_UNVERIFIED` in the unscheduled shortlist,
which is misleading: the hours are known, verified, and paid for. What is unusable is
not the evidence but the shape the optimizer will accept.

The trip lost 5 of 13 landmarks to this. In a city where museums close on Mondays and
a trip long enough to contain one, that is close to the worst case — and it is the
normal case for any trip over a week.

## Why it was invisible until now

`opening_interval` as a single window is fine for a **day trip**, where "the trip" and
"the day" are the same thing. All 27 historic regression fixtures are single-day
except two, which are two-day. The pilot's own earlier states were 4 or 5 walkable
places where the question never arose.

This is the same shape of blind spot as the per-day walking budget fixed on
2026-08-05: a per-day quantity collapsed to a trip-wide one, invisible to a suite made
of day trips.

## What has to be decided

- **Emit one `opening_interval` fact per date.** Most faithful to the data already
  stored. It changes the fact shape the optimizer consumes, so `_planning_fact`,
  `CLOSED_DURING_VISIT` and every frozen fixture carrying an `opening_interval` are
  in scope, and `WF-006`'s optimizer contract names that fact explicitly.
- **Keep one fact, add the closed dates beside it.** Smaller: the window stays
  trip-wide and a `closed_dates` list forbids specific days. Cheap and it handles the
  Monday case, but it cannot express a place that opens 09:30 on weekdays and 11:00 at
  weekends, which is common.
- **Schedule against the narrowest window that covers every open day.** No shape
  change at all — take the intersection of the open days' windows and simply skip the
  closed dates. Loses time at the edges but needs no new fact, and would recover all
  five landmarks here.
- **Leave it and let the owner move the trip dates.** Not viable: the dates are
  flights.

Whichever is chosen, `OPENING_UNVERIFIED` is the wrong code for this and should not
survive the fix. The hours are verified; the place is closed. Those are different
facts and an owner reading the first would go looking for evidence they already have.

## Related

- The per-day walking budget bug, fixed 2026-08-05, was the same collapse of a
  per-day quantity into a trip-wide one.
- `WF-038` — transit. Unrelated in mechanism, but it is what made the trip long and
  wide enough for this to bite: with 13 landmarks across seven days instead of 5
  across two, most of the city's museums are now in scope.
