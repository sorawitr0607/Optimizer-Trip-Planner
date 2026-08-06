---
id: WF-040
title: Decide whether the planner recommends where to stay
status: closed
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

## Decided and built 2026-08-06: rank transit-station neighbourhoods

The owner rejected the "moot now that a base is confirmed" reading and was right to:
*"it should be benefit when I want to explore before I really booked, make it as a
feature."* Confirming the Ximending base closed the **gap**, not the question. The value
is in the state the owner was in a week earlier, and their own experience is the brief —
they wanted to know which areas fit the plan, then went to Airbnb for a family room.

The third option, scored *areas* rather than individual lodging. But the unit is a
**transit station**, not an administrative district, which the ticket had not considered:

- It is how the owner already thinks. Their words while searching were "it only near
  ximenting station".
- It is measurable exactly. Travel time from a station to every selected place comes from
  the graph `WF-038` already builds, free, with no new provider.
- District names do not generalise. Taipei's OSM addresses carry `中正區` on **278 of 832**
  candidates, so a district would be a Chinese-only regex over a third of the data, in an
  app whose acceptance check is worldwide. Station names are already bilingual in OSM.

### Five factors, weighted like what they are

The owner chose all five, adding the last themselves — "popular by tourist, so can infer
that it has many choice", which is answered by counting listed beds.

| Factor | Weight | Source |
|---|---|---|
| Travel time to your places | 45 | The transit graph. Measured, not inferred. |
| Metro access | 20 | Lines served at the station. |
| Places to eat nearby | 15 | Overpass count within 600 m. |
| Open after dark | 10 | Overpass count. A proxy for activity, **not** safety. |
| Choice of places to stay | 10 | Overpass count of listed lodging. |

Travel time dominates because it is the only one measured rather than inferred, and the
only one that recurs every day of the trip.

### And four things it refuses to score

`areas.NOT_EVALUATED` is returned on **every** result, including an empty one, and renders
at the same size as the scores: price, room type and family capacity, cleanliness, and
safety. The owner's own case is the whole argument — the best-fitting area was still one
where the only family room was on Airbnb, and no amount of OpenStreetMap counting would
have known. This ranks *where*; the owner books *what*.

### Result on the pilot trip

111 stations reached at least one selected place, out of 138. Cost **US$0.00** — one
Overpass request for the whole shortlist, cached for 7 days.

| Score | Station | Avg to plan | Food | After dark | Beds |
|---|---|---|---|---|---|
| 97.9 | 中山 Zhongshan | 22 min | 522 | 31 | 51 |
| **94.2** | **西門 Ximen** | 24 min | 478 | 28 | **114** |
| 93.0 | 台北車站 Taipei Main | 23 min | 586 | 8 | 90 |
| 90.1 | 台大醫院 NTU Hospital | 22 min | 392 | 5 | 49 |
| 89.5 | 雙連 Shuanglian | 23 min | 433 | 10 | 35 |
| 87.5 | 民權西路 Minquan W. Rd | 23 min | 298 | 7 | 12 |
| 83.7 | 東門 Dongmen | 23 min | 267 | 2 | 11 |
| 77.9 | 中正紀念堂 CKS Memorial | 22 min | 150 | 1 | 1 |

Ximending — where the owner actually booked, independently — comes second, and carries
more listed lodging than any other area. The rest are Taipei's recognised accommodation
districts. That is the closest thing to external validation available without a second
trip.

### Three defects found by measuring rather than reasoning

Each was in the first working version and each was visible only against real data.

- **The shortlist filled with duplicates of two stations.** `transit.STOP_TAGS`
  deliberately admits `stop_position` and `platform` so subway relations stay resolvable,
  so Taipei's 437 graph stops are really **138 named stations** — six platform nodes for
  板橋 alone. Grouping by name also cut the work from 373 Dijkstra runs to 138. An unnamed
  stop is skipped rather than merged: an area the app cannot name is not advice, because
  the owner cannot search a booking site for it.
- **A two-minute spread became a 45-point gap.** The first scoring ranked travel time
  between the observed best and worst, and the eight shortlisted stations averaged 20 to
  22 minutes — so rank-scaling made the leader look decisive when the honest answer is
  "these are equivalent, choose on price". It is now a ratio against the best, which
  gives 20/22 = 0.91 and says so.
- **Food scored a flat 15 of 15 for every station.** Saturation was set at 30 from
  intuition; Taipei returns **150 to 586** places to eat within 600 m. The factor was a
  constant wearing a score's clothes. Ceilings are now set from measured data and the
  curve is logarithmic, because the difference between 5 and 50 is the difference between
  "nowhere" and "plenty" while 450 against 586 is no difference at all.

A fourth was found by a failing test rather than by the pilot: `TransitGraph.journey`
answers only once something has been **ridden** — correct, or a walk would arrive wearing
a journey's clothes — so a station across the road from a place returned `None`. Taking
that as "unreachable" scored the *best possible* area worst. Travel time is now the better
of riding and walking.

### Degrading rather than refusing

If Overpass will not answer, the two locally-measured factors still score and the report
says `amenities_counted: false` so the screen can name which half it is showing. Refusing
would be wrong: travel time and metro access are the heavy factors and cost nothing.

### Tests

`tests/test_areas.py`, 12 tests: six on the pure scoring, five through `actions` with a
fake graph and a fake amenity provider, one on the query shape. All negative-tested, and
**one negative test caught a bad test**: neutralising the log scale did not fail anything,
because raising the ceiling alone already fixed the flatness. The assertion now pins the
*shape* — 150 places to eat must score above 12 of 15, where straight division gives 5.6.

351 tests green, 27 of 27 historic regressions unchanged, all 12 `check.py` stages pass.
`recommend_areas` is the **64th** allowlisted method, and the count assertion in
`test_api.py` caught it joining, which is what that assertion is for.

### What the screen gate could not witness

The `/places` baseline cannot see this feature: the section renders **below the fold** at
the 1440x900 capture viewport, under a deck card that fills it. Recorded rather than
worked around, because it is the same blind spot noted when the gate was built.

Re-capturing also surfaced something worth knowing: **the capture renders live provider
state**, so a run made while Overpass was rate-limiting produced a `/places` image
carrying a provider-error banner. Approving that would have baked a failure state into the
baseline. The captures were discarded instead. The baselines are therefore now stale with
respect to this trip's *data* — the confirmed accommodation base alone moves `/evidence` by
13.9% — and a clean re-approval needs a quiet Overpass.

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
