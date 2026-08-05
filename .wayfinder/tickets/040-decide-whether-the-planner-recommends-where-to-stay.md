---
id: WF-040
title: Decide whether the planner recommends where to stay
status: open
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide whether the planner recommends where to stay

## The owner asked twice and the app cannot answer

On 2026-08-04 the owner set accommodation to "not booked, **please recommend**".
`optimizer._hotel_recommendation()` runs, returns a value, and that value can never
be a recommendation between places, because it only ever has one candidate to
choose from.

`hotel_area` candidates are created in exactly two places, both in
`actions._optimizer_input`:

- `booked_accommodation_base` — the base the owner has already recorded
- `provisional_accommodation_base` — the centroid of whatever is selected

**Discovery never produces one.** `providers` maps the `hotel` category to an empty
tag set, so no accommodation is ever fetched from OpenStreetMap.

The consequence is structural, not a tuning problem. `_hotel_recommendation` sorts
its candidates and reports a winner plus a runner-up, so with one candidate:

- `runner_up_area_id` is **always** `None`
- `runner_up_total_known_travel_minutes` is **always** `None`
- `travel_delta_minutes` is **always** `None`
- `basis` is always `selected_place_centroid` unless a base is already booked

Measured on the real Taipei trip: `default_area_id:
"provisional_accommodation_base"`, `basis: "selected_place_centroid"`,
`total_known_travel_minutes: 144`, `runner_up_area_id: null`. When the selection
was four obscure peaks the "recommendation" was the geometric middle of four hills.

So the runner-up half of that function is **dead code by construction** — the third
such case found during the pilot, after `WF-039`'s acceptance path.

## What the function is actually for

Read charitably, it is not a recommender. It answers *"given where you are staying,
how much whole-trip travel does that base imply"*, and secondarily *"if you have not
chosen, here is a neutral centroid to plan against so the optimizer has an anchor"*.
Both are useful. Neither is "where should we stay", and the field names —
`runner_up_area_id`, `travel_delta_minutes`, `pros`, `cons` — promise the second
thing while delivering the first.

## What has to be decided

- **Discover real accommodation areas and rank them.** Delivers what the owner
  asked. It means fetching lodging from OpenStreetMap, which is free and already
  wired, then deciding what an "area" is — individual hotels are the wrong unit,
  so it needs clustering or a district notion the app does not have. And it invites
  price and room-fit questions the app has no data for, which `cons` already admits
  with `hotel_quality_price_and_room_fit_not_evaluated`.
- **Rename it and delete the dead half.** Cheapest and most honest: it becomes
  `accommodation_anchor`, the runner-up fields go, and the screen stops implying a
  choice was made. The owner still gets no recommendation, but nothing pretends
  otherwise.
- **Recommend by proximity to the plan, not by lodging data.** Score *districts*
  implied by the selected places — "most of your stops are in Wanhua, stay there" —
  which needs no new provider and answers the real question at the granularity a
  person books at. Requires a district notion, same as the first option, but no
  lodging data and no price claims.
- **Say it is out of scope.** Defensible: booking is where owners have the most
  context and the least need for help. Then the field names must still change,
  so this is not a no-op.

## Why it matters beyond one trip

`ACCOMMODATION_BASE_UNCONFIRMED` is one of the two capability gaps that keep every
variant `provisional` rather than `ready`, and `provisional` is only activatable
because the trip is `explore_first` — a `ready_to_schedule` trip cannot activate at
all until a base is confirmed. So an owner who wants a timetable is required to
name a base, and the app that asks them to will not help them pick.

## Related

- `WF-038` — transit routing. It changes which bases are *good*, and cannot create a
  second candidate to compare against, so it does not resolve this.
- `WF-037` — ranking. Same shape of defect one layer up: the machinery exists and
  the inputs make it inert.
