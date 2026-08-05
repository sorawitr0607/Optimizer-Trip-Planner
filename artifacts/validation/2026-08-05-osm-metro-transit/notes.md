# Transit from OpenStreetMap, and the three gates that were discarding it

`WF-038` chose GTFS. Taipei's feed needs a Taiwan mobile number or a manual identity
review at TDX, so the owner parked it. OpenStreetMap needs no account, the app
already queries Overpass for free, and OSM carries `route=subway` relations listing
each line's stations in order.

**The trip went from 3 visits over 2 days to 11 visits over 7.**

## One Dijkstra, two sources

`travel_planner/transit.py` now holds `TransitGraph`, the walking constants, and the
routing. `gtfs.TransitFeed` and `graph_from_osm()` both build one. That split was
worth doing before adding the second source rather than after: otherwise there would
be two shortest-path implementations to keep honest, and `Edge.basis` would have
nowhere to live.

`basis` is the whole difference. GTFS states ride times and lets headway be measured
from trips-per-edge, so its edges are `timetable`. OSM states only topology, so its
ride times come from distance at an assumed **33 km/h** and its waits from an assumed
**6-minute headway**, and its edges are `nominal`. Both are named constants, stated
rather than buried.

## The real Taipei network

| | |
|---|---|
| Overpass nodes returned | 6,751 |
| Stops after filtering | **437** |
| Edges | 432 |
| Lines | R, BL, BR, G, O, Y, A, and the Xinbeitou branch |

The filter is load-bearing. `(._;>;)` is needed to resolve the relations' ordered
member lists, and it also drags in every node of every track way — so without
`STOP_TAGS` a place beside a tunnel would be handed a walk to "a station" that is a
point on a rail line. `stop_position` and `platform` stay in the allowed set
deliberately: subway relations generally order stop positions, not station nodes, so
filtering to `railway=station` alone would leave the relations unresolvable and the
graph empty.

## What metro buys, measured against the real walking routes

| pair | walk | metro | walking part |
|---|---|---|---|
| Lungshan Temple → Taipei 101 | **89 min** | **32 min** | 13 min |
| Red House → Fine Arts Museum | **55 min** | **28 min** | 8 min |
| Lungshan Temple → CKS Memorial Hall | 32 min | 25 min | 8 min |
| Taipei 101 → Taipei Zoo | — | 43 min | 12 min |
| Lungshan Temple → Beitou | — | 56 min | 8 min, 2 changes |

The walking part is what matters: `maximum_walking_minutes_per_leg` measures
`walking_minutes`, so a 56-minute ride reached by an 8-minute walk passes a
25-minute cap that no walk of that distance could.

## The finding: three gates were discarding every metro route

162 metro routes were fetched and stored, and the optimizer used none of them. Modes
came back `['walk']` and the longest leg got *worse*.

Transit routes are `status: "estimated"` by construction — derived from a timetable
or from topology, never looked up. Three separate sites admitted only `"verified"`:

- `actions._optimizer_input` — filtered them out **before the snapshot existed**
- `optimizer._routes_between`
- `optimizer._best_inbound_route`

Three sites is a systemic property, not an oversight: the app deliberately admits
only verified routes into planning. So the question was whether transit may be an
exception, and the answer was already in the codebase.

`optimizer._planning_fact` is documented as *"Verified fact, or a visible assumption
allowed only for an Explore preview"* — the app **already** plans against provisional
opening hours in `explore_first` mode. Routes are the same category of thing. So all
three sites now admit `estimated` when `allow_provisional_assumptions` is set, which
only `explore_first` sets. A `ready_to_schedule` trip is unaffected and still demands
verification, and `ROUTE_UNVERIFIED` remains a hard violation for it.

**27 of 27 historic regressions pass unchanged**, 325 tests green. That matters more
than the argument: the change is inert everywhere it should be.

## Two landmarks had to go, for a real reason

| | |
|---|---|
| National Palace Museum | metro-connected to **0 of 14** — bus-served from Shilin, and the app has no bus routing |
| Elephant Mountain | metro-connected to **0 of 14** — OSM places the peak beyond the 900 m access radius |

The last remaining violation was a single **43-minute walk from Shilin Cixian Temple
to the Palace Museum**. Dropping those two cleared it. They are `not_for_trip`, not
deleted, so each is one choice away if bus routing ever lands.

## The plan now

`plan_1d875c0e7a0143db93401`, valid, provisional, **11 visits across all seven trip
days** — worst day 35 minutes of walking, longest leg 22 minutes, inside the owner's
25/60 cap. 8 days, 90 rows, 25 checklist items, a 26 KB workbook and a calendar with
22 events.

- 2026-12-29 Huashan 1914
- 2026-12-30 Taipei Zoo
- 2026-12-31 Shilin Cixian Temple, Beitou Hot Spring Museum
- 2027-01-01 Taipei 101, Sun Yat-sen Memorial Hall
- 2027-01-02 Chiang Kai-shek Memorial Hall
- 2027-01-03 Lungshan Temple
- 2027-01-04 Confucius Temple, Baoan Temple, Fine Arts Museum

Cost: **US$0.00.** Overpass is free and the topology is cached for 30 days.

## What is still not true

The times are `nominal`, so the plan stays `provisional` and every route reads
`estimated`. **Do not use these times to catch a flight.** A real feed would replace
the assumed speed and headway with measured ones, and `PlannerActions` already
prefers a feed over OSM whenever one is on disk — so dropping a TDX zip at
`data/gtfs/transit.zip` upgrades this with no code change.

`ACCOMMODATION_BASE_UNCONFIRMED` and `OPENING_EVIDENCE_MISSING` remain. The first is
`WF-040`; the second needs paid opening hours for the eight newly added landmarks.
