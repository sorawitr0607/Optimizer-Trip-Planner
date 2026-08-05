---
id: WF-038
title: Decide how the planner gets transit routing
status: closed
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide how the planner gets transit routing

## The finding

**The planner cannot produce a valid plan for a real city trip, because it has no
transit routing.** Found on 2026-08-04 attempting pilot-ready gate 1 with the real
Taipei trip and a hand-picked selection of 15 named Taipei sights.

`OpenRouteServiceProvider.mode` is `"walk"`. All 340 route snapshots on the real
trip are walking. The optimizer recognises `walk` and `bike` and nothing else.
`google_routes:compute` is priced in `PRICES_USD` at US$0.005 but **no provider
class implements it** — it is a priced, unbuilt operation.

With the 15 landmarks selected, `optimize_trip` returns three variants and every
one is `status: unavailable`, `valid: false`:

| Variant | Plain walking / day | Limit | Longest single leg | Limit | Visits |
|---|---|---|---|---|---|
| `best_balance` | 874 min | 45 | 205 min | 20 | 20 |
| `relaxed` | 0 | 45 | 0 | 20 | **0** |
| `more_highlights` | 0 | 45 | 0 | 20 | **0** |

Hard violations: `UNAPPROVED_PLAIN_WALK_THRESHOLD`,
`UNAPPROVED_WALKING_LEG_THRESHOLD`.

> **Correction, same day.** This ticket first recorded 1289 min and a 205-min leg
> and attributed all of it to the missing transit mode. **A large part was missing
> route data, not distance.** A pair with no measured route falls back to a
> pessimistic estimate, so the plan showed phantom 68-minute walks between places
> a kilometre apart. Fetching those nine specific pairs turned the legs into 14,
> 10 and 9 minutes and a three-stop Wanhua cluster went **valid** with the owner's
> 20-min and 45-min limits fully intact. The figures above are after 500 measured
> routes and still fall, so treat any single reading as an upper bound until the
> pairs the plan uses are measured.
>
> That misattribution had a cause worth keeping: `refresh_routes` ordered pairs by
> `place_id`, so 340 free calls went on arbitrary pairs while every pair the plan
> used stayed unmeasured. **Now fixed** — nearest pairs first, since the cap bites
> long before 1640 pairs and a 17 km pair will never be walked. Fixed with a test.

**The transit gap is real, and measured cleanly.** With all 110 pairs fetched for a
complete ten-landmark, four-district set — no missing data at all — the plan still
needs **206 min/day of plain walking and a 45-minute longest leg**. The
inter-district hops are genuinely 45-minute walks. So:

- **one walkable district validates today** — verified: 3 stops, 33 min/day
  walking, 14-min longest leg, `valid`, `provisional`
- **four districts does not**, and no amount of route data changes that

The optimizer is behaving correctly throughout. It refuses to assert a schedule
that violates the owner's stated limits, and it will not fabricate a connection it
has no evidence for. The gap is in what evidence it can be given.

## Why every earlier plan looked fine

This did not surface before because **every fixture and the trip's own earlier
state used walkable clusters**. The trip's previous selection was four adjacent
hills — Dailaokengshan, Yuantanzikengshan, Daxiangshan, Ejiaogeshan — close
enough to walk between, so `best_balance` came back `valid: true` and
`provisional`. The 27 historic regression cases are single-city day-scale
clusters too.

The moment the trip became an actual Taipei itinerary — Beitou in the north, the
zoo in the south, Tamsui-area viewpoints west — the walking-only assumption broke
it. Gate 1 says "the real Taipei trip planned end to end in the webapp. **Not a
fixture.**" This is precisely the class of thing that wording exists to catch.

## The owner's own four reference trips all used transit

Measured directly from `data/reference-itineraries/`:

| Trip | Transit words found in the workbook |
|---|---|
| Fukuoka | bus, JR, subway, taxi, train |
| Japan | bus, JR, metro, รถไฟ, นั่งรถ |
| Kunming | bus, didi, รถไฟ |
| Shanghai | didi, metro, train, รถบัส, รถไฟ, แท็กซี่ |

Japan's workbook carries a dedicated `Transport` sheet. `WF-022` makes those four
workbooks the validation target because their recurring sheets are the merged
app's entire output surface. So the app is validated against four trips that all
moved by transit, while being structurally unable to plan with transit.

Not one of the four was walked.

## What has to be decided

- **Add a transit-capable route provider.** `google_routes:compute` is already
  priced, so the ledger and cap need no change. But it is a **paid** provider on
  every leg, and pairs grow quadratically: the real trip needs 1640 pairs for 41
  selected places, which at US$0.005 is US$8.20 against a US$10 monthly cap —
  one trip would nearly exhaust it. A sparse strategy is not optional.
- **Free transit alternatives.** OpenRouteService has no public-transport
  profile on the free tier. OpenTripPlanner or a GTFS feed would be free and
  offline-friendly, which fits the destination's local-only stance, but it is a
  real component to run and Taipei's GTFS would need sourcing.
- **Model transit without routing it.** The optimizer could accept a coarse
  city-wide transit assumption — a mean speed with a transfer penalty — so legs
  become plausible rather than absent. Cheap and offline, and it means the plan
  asserts times no provider verified, which cuts against the evidence-first rule
  that every other part of this app follows.
- **Constrain trips to walkable clusters.** Honest and free: the planner declares
  that it plans walkable day-clusters, and the owner groups stops by district
  themselves. It makes the four reference trips out of scope as a target, so it
  needs `WF-022`'s validation claim revisited.

Whichever is chosen, two existing rules apply. A new provider is provider policy,
so the redaction self-test and `_spend` routing must both cover it. And
`MAX_ROUTE_REQUESTS` is 60 per run — with quadratic pair growth, any transit
provider needs a sparse-pair strategy rather than a full matrix.

## Related

- `WF-037` — the ranking cannot surface a city's landmarks. Fixing that produces
  *more* geographically-spread selections, so it makes this ticket more pressing,
  not less.
- The route-request cap defect found alongside this is **already fixed**:
  `MAX_ROUTE_REQUESTS` capped total coverage rather than per-run coverage, because
  the cache check sat inside the loop while the cap sliced a fixed sort of all
  pairs. Route coverage on the real trip was pinned at 60 of 1640 and re-running
  changed nothing. That is a straightforward defect against the stated intent, not
  a decision, so it was fixed with a test rather than deferred here. The pair
  *ordering* defect above is fixed the same way and for the same reason.

## Decided 2026-08-05: a local GTFS feed, read with the standard library

The owner chose GTFS. Built and green:

- **`travel_planner/gtfs.py`** — pure, no HTTP and no SQLite, like the rest of the
  core. It reads a GTFS zip with `zipfile` and `csv`, indexes stops, derives edges
  from consecutive `stop_times` within each trip keeping the fastest, and answers
  origin/destination with Dijkstra. **No runtime dependency was added**, which is
  what ruled OpenTripPlanner out as much as the operational weight did.
- **`providers.GtfsTransitProvider`** — `mode: "transit"`, priced at US$0.00 in
  `PRICES_USD` because it is a file read, but priced rather than omitted since an
  unpriced operation raises.
- **`actions.refresh_transit_routes`** — allowlisted as the 61st method. Transit
  legs are stored *beside* walking ones, because the store keys a snapshot by
  (origin, destination, **mode**) and the optimizer takes the shortest it holds for
  a pair. Short hops keep their walk; long ones gain a ride.

**Why this unblocks the gate.** `maximum_walking_minutes_per_leg` measures
`walking_minutes`, and a transit leg reports **access and egress only**. Measured on
the test feed: a 43-minute journey reports **2 minutes of walking**. A 43-minute
walk can never pass a 25-minute cap; a 43-minute ride to a 2-minute walk passes it
easily.

**What it does not do.** The journey is schedule-*derived*, not schedule-bound: it
takes the fastest observed ride per edge, adds half the measured mean headway per
boarding and a 4-minute transfer penalty, and never consults the clock. So it does
not know the last train has gone. Every route it produces is `status: "estimated"`,
never `"verified"`. Do not use these times to catch a flight.

The headway is measured from the feed's own service span rather than an assumed
18-hour day — assuming the day inferred a 90-minute wait from six trips that ran
15 minutes apart.

### The Taipei feed itself is outstanding

The code is done and tested; the **data is not sourced**. Checked on 2026-08-05:

- Taiwan's official TDX platform answers **HTTP 401** — it needs a free account.
- The MobilityData open catalogue holds **9 Taiwan feeds and none for Taipei**
  (Changhua, Miaoli, Nantou, Taichung, Yunlin). All 2,146 catalogue objects were
  scanned; the apparent `taipei` matches are `tper`, an Italian operator.

So the remaining step is owner-side: register at TDX, download the Taipei feed, and
put it at `data/gtfs/transit.zip` or point `TOURIST_GTFS_PATH` at it. Until then
`refresh_transit_routes` refuses cleanly with "GTFS feed unusable" and changes
nothing, which is asserted by a test.

## Interim position

Gate 1 cannot pass for a city-wide Taipei itinerary as things stand. It **can**
pass for a walkable cluster, which is what the trip's earlier four-peak state
demonstrated. The 1 November checkpoint should be judged knowing that distinction,
because "the real trip planned end to end" means different things either side of
it.
