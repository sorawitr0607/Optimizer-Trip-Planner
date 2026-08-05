# Gate 1: the real Taipei trip, planned end to end in the webapp

`WF-022`'s first pilot-ready gate, judged 1 November 2026. **Met in substance and
thin in content**, and the reason it is thin is the point of this bundle.

The trip is real, not a fixture: `data/tourist.sqlite3` at schema 13, the owner's
own Taipei trip, 2026-12-29 to 2027-01-04, three travellers.

## What was delivered

- Setup complete and confirmed — owner 26, Sister 19, Mom 51, all Thai, headcount 3
- The owner's requested **lower-strength walking cap**: `balanced_pace` at
  **25 min/leg, 60 min/day**, one rung looser than the 20/45 it replaced and still
  a genuine cap
- An **activated plan version**, valid, `provisional`, worst day 35 min of plain
  walking and a 22-minute longest leg
- A readiness board of 17 items
- A 23 KB workbook and a 6 KB calendar with 14 events
- **Gate 2 passes**: 10 of 10 recurring reference-workbook elements covered

Three landmarks are scheduled: **Taipei 101** (10:00, opens 10:00), **Sun Yat-sen
Memorial Hall**, **Lungshan Temple** (09:03, opens 06:00).

## The paid call earned its money

US$0.125 for real opening hours found that the previously activated plan had
scheduled **Red House and the Botanical Garden herbarium on 2027-01-04 — the one
day both are closed.** The trip spans New Year, when Taipei venues close on dates a
generic assumption would miss.

| Landmark | Trip-date hours |
|---|---|
| Taipei 101 | 10:00–21:00 every day |
| Lungshan Temple | 06:00–22:00 every day |
| Botanical herbarium | **closed 12-29 and 01-04**, else 09:30–16:30 |
| Red House | **closed 01-04**, else 11:00–21:00 |
| Sun Yat-sen Memorial Hall | not fetched — the one provider failure of five |

With real hours the optimizer dropped both closed venues rather than scheduling
them. Visits fell from five to three, which is the correct trade: a plan that sends
three people to a locked door is worse than a shorter one.

**A cost-estimate error to record.** The preflight used
`google_places:details` at US$0.017 and predicted US$0.085.
`refresh_opening_hours` actually bills `google_places:search_text` at US$0.025, so
it spent US$0.125 — 47% over. The ledger is correct; the estimate asked about the
wrong operation. Anyone preflighting this action should ask about `search_text`.

## Why only three visits across two of seven days

Not a packing defect. With 41 candidate places the optimizer spread 20 visits over
8 days; with 5 it clusters them, because **five places cannot fill seven days**.

The chain is:

1. **No transit routing** (`WF-038`) — every connection is a walk
2. So the walking cap admits only **two adjacent districts**, Wanhua/Ximen and
   Xinyi; adding Zhongzheng introduces a real 33-minute leg
3. Two districts hold **five** of the fifteen chosen landmarks
4. Two of those five are closed on the day the optimizer could use

Measured, not assumed: `ready_to_schedule` produces the identical 3-visit plan, so
`planning_mode` is not involved.

Ten landmarks are excluded pending transit, including Chiang Kai-shek Memorial
Hall, the National Palace Museum, Beitou and the Fine Arts Museum. They are
`not_for_trip` rather than deleted, so flipping them back is one choice each.

## Three defects fixed getting here

Each was found by trying to plan a real trip, and none was visible to the test
suite:

- **`MAX_ROUTE_REQUESTS` capped total coverage, not per-run.** The cache check sat
  inside the loop while the cap sliced a fixed sort of all pairs, so the 61st pair
  was unreachable however often it ran. Coverage was pinned at 60 of 1640.
- **Route pairs were fetched in `place_id` order.** 340 free calls went on
  arbitrary pairs while every pair the plan used stayed unmeasured — and a missing
  route falls back to a pessimistic estimate, so the plan showed phantom 68-minute
  walks between places a kilometre apart. Fetching those nine pairs by proximity
  turned them into 14, 10 and 9 minutes and a cluster went valid with no other
  change. Now nearest-first.
- **A whole-trip walking total was compared against a per-day budget**, making an
  n-day trip n times too strict. Invisible because 25 of 27 fixtures are
  single-day.

## Three tickets it opened

- `WF-037` — ranking buries a city's landmarks under near-identical features.
  Taipei 101 ranked 363rd of 832.
- `WF-038` — no transit routing. The binding constraint on this whole gate.
- `WF-039` — the comfort-tradeoff acceptance path is unreachable by construction,
  so an owner two minutes over one leg must drop every walking guard or abandon
  the plan.

## Honest assessment against the 1 November checkpoint

The machinery works end to end on real data: setup, discovery, ranking, evidence,
optimization, activation, readiness, workbook, calendar, and both parity gates.
Nothing in the pipeline failed.

What it cannot yet do is plan the trip the owner actually wants, because it cannot
route transit — and all four reference trips moved by transit. Judged as "does the
webapp plan the real trip", this passes. Judged as "would the owner use this plan
in Taipei instead of Excel", not yet, and `WF-038` is the single decision standing
in the way.
