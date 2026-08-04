---
id: WF-038
title: Decide how the planner gets transit routing
status: open
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
| `best_balance` | **1289 min** | 45 | **205 min** | 20 | 16 |
| `relaxed` | 0 | 45 | 0 | 20 | **0** |
| `more_highlights` | 0 | 45 | 0 | 20 | **0** |

Hard violations: `UNAPPROVED_PLAIN_WALK_THRESHOLD`,
`UNAPPROVED_WALKING_LEG_THRESHOLD`. The longest stored walking route on the trip
is **379 minutes** — a 6.3-hour walk offered as a connection between two stops.

The optimizer is behaving correctly. It refuses to assert a schedule that
violates the owner's stated limits, and it will not fabricate a connection it has
no evidence for. The gap is in what evidence it can be given.

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
  a decision, so it was fixed with a test rather than deferred here.

## Interim position

Gate 1 cannot pass for a city-wide Taipei itinerary as things stand. It **can**
pass for a walkable cluster, which is what the trip's earlier four-peak state
demonstrated. The 1 November checkpoint should be judged knowing that distinction,
because "the real trip planned end to end" means different things either side of
it.
