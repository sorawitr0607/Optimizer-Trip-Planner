---
id: WF-041
title: Decide how per-day opening hours reach the optimizer
status: closed
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

## Decided and built 2026-08-06: the intersection option

The owner chose the third option — schedule against the overlap of the open days'
windows and skip the closed dates. **No new fact type, and the mechanism it needed
already existed and was dead.**

- `opening.common_interval` now takes the overlap across the days a place is **open**
  instead of refusing outright, and returns `open_dates` beside the existing
  `closed_dates`. A usable `interval` and a `CLOSED_ON_A_TRIP_DATE` reason now
  coexist: the hours are known *and* the place shuts on a named day. Callers key off
  `interval`.
- `actions._optimizer_input` sets `applies_to_dates` to the open dates rather than
  every trip date. **That field was already being written and read by nothing** —
  which is why the information was present the whole time and still lost.
- `optimizer._open_on()` is consulted in two places: `_earliest_visit_start` returns
  `None` for a day the place is shut, and `validate_variant` raises
  `CLOSED_DURING_VISIT` if one is scheduled anyway. A fact without
  `applies_to_dates` applies everywhere, so every frozen fixture stays valid.

**Result on the pilot trip: 8 visits became 13, all thirteen chosen landmarks, with
no closed-door visits.** Opening facts reaching the optimizer went from 8 of 13 to
13 of 13. Worst day 27 minutes of walking, longest leg 14 minutes, well inside the
owner's 25/60 cap. 2027-01-04, the Monday, now carries only Sun Yat-sen Memorial Hall
and Taipei 101 — both open Mondays — and the five Monday-closed venues moved to other
days.

27 of 27 historic regressions pass unchanged, 327 tests green.

### Three tests asserted the defect and were rewritten

`test_a_place_closed_on_a_trip_date_produces_no_fact` required *no fact* — the bug,
written down as a requirement. It is now
`test_a_place_closed_on_one_trip_date_is_still_usable_on_the_others`. Likewise
`test_closed_on_any_trip_date_yields_no_interval` became
`test_a_closed_date_narrows_the_window_rather_than_removing_it`, and a new
`test_closed_on_every_trip_date_yields_no_interval` covers the case that genuinely has
nothing to offer.

`report["unusable"]` no longer lists these places, because they are no longer
unusable — the closure is reported on the evidence rather than as a rejection.

### A note on the behavioural test

The end-to-end walk over the proposal is weaker than it looks and says so in the
test: the fixture's single open day is the one the optimizer would choose anyway, so
deleting the guard still produced a clean plan. `_earliest_visit_start` is asserted
directly for that reason, and *that* assertion does fail when the guard is removed.

`OPENING_UNVERIFIED` no longer appears for these places, which was the other half of
the complaint above — the hours were verified and paid for, and the code sent an owner
hunting for evidence they already had.

## Related

- The per-day walking budget bug, fixed 2026-08-05, was the same collapse of a
  per-day quantity into a trip-wide one.
- `WF-038` — transit. Unrelated in mechanism, but it is what made the trip long and
  wide enough for this to bite: with 13 landmarks across seven days instead of 5
  across two, most of the city's museums are now in scope.
