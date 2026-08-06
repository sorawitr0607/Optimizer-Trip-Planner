---
id: WF-042
title: Decide how a flight day that cannot hold its logistics behaves
status: closed
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide how a flight day that cannot hold its logistics behaves

## One unusable day emptied the entire plan

Found 2026-08-06, immediately after the owner supplied the real flight times:
**29 Dec 12:40–17:40 outbound, 4 Jan 10:40–16:40 home.** Recording them dropped the
plan from 13 scheduled visits to **zero**, across all seven days, with every landmark
reported as `PLAIN_WALK_THRESHOLD` in the unscheduled shortlist.

Nothing was wrong with the walking. The chain was:

1. `actions._optimizer_input` gives the departure day the window `08:00–10:40` — the
   default leisure start, tightened at the end by the flight.
2. `optimizer._operational_layout` charges the last day a fixed suffix: pack and check
   out (45), transfer to the terminal (45), be at the airport (90) — **180 minutes**.
3. So `body_end` is `10:40 − 180 = 07:40`, *before* the window opens, and `_build_day`
   raised `OPERATIONAL_TIMELINE_EXCEEDS_DAY` — correctly, in the sense that a 10:40
   flight really does mean leaving at 07:40.
4. `_greedy_baseline` accepts a placement only when `_build_schedules` returns **no
   hard errors for the whole trip**. The departure day emitted its error *while
   holding nothing at all*, so every candidate on every day was refused.

The reported reason was misleading twice over. `_skip_reason` does not measure
anything — if a place ended up skipped and a walking threshold merely *exists*, it
returns `PLAIN_WALK_THRESHOLD`. And the day being blamed carried no visits.

Measured before the fix, one candidate alone on 2026-12-30:
`[NO_VALID_VISIT_INTERVAL(place), OPERATIONAL_TIMELINE_EXCEEDS_DAY(2027-01-04)]` —
the second error is for a day with an empty sequence.

## Why it was invisible until now

**No test set `include_operational_timeline`.** It is `True` for every trip
`actions.py` builds and absent from all 27 historic fixtures, so the entire
operational-timeline path — arrival transfer, check-in, meals, checkout, airport —
was exercised only by the live pilot. The four earlier trips this app was validated
against were planned by hand in Excel, where the flight day is obviously a flight day.

It also needed a **morning** flight. The owner's earlier placeholder was 20:00, which
leaves 12 hours of body time; any departure after roughly 11:00 hides the defect
entirely.

## What had to be decided

- **Open the departure day's window early enough to hold its logistics.** The window
  is the contract every consumer reads, so the derivation is where the fact belongs.
- **Move the builder's clock instead.** Rejected after measurement — see below.
- **Drop the last day from `usable_windows` when it cannot hold the suffix.** The
  owner then loses the checkout and airport rows entirely, which is the half of that
  day they most need.
- **Let the previous day owe the airport run.** A real model for pre-dawn flights and
  far more than this needed.

## Decided and built 2026-08-06: open the window, and stop an empty day vetoing the trip

Two complementary changes, because the chain has two independent faults.

**1. `actions._optimizer_input` opens the departure day early enough.**
`optimizer.DEPARTURE_LOGISTICS` is now one exported tuple of `(kind, minutes)` that
both `_operational_layout` and the window derivation read, so the 180 minutes cannot
drift between them, and the last day's start becomes
`min("08:00", departure_time − DEPARTURE_LOGISTICS_MINUTES)`, clamped to midnight.
The pilot's 4 Jan window is now **07:40–10:40**.

**2. `optimizer._build_day` refuses only when something was going to happen there.**
`if current > body_end and (sequence or items)`. A day with an empty sequence and
nothing appended lays its logistics out instead of aborting, so it can no longer veto
the other six days. The independent validator still judges whether they fit, which is
not the builder's call.

### Moving the builder's clock alone was tried and is wrong

The first attempt rewound `current` to `body_end` and reported the earlier start in
the day header. It scheduled all 13 visits and then **failed validation on every
variant**: `TIMELINE_OVERLAP_OR_NEGATIVE_SLACK` and
`OUTSIDE_USABLE_WINDOW(pack_and_check_out:2027-01-04)`. `validate_variant` judges
every item against the snapshot's own `usable_windows` — it is *supposed* to, per
"never trust solver construction" — so a builder that quietly disagrees with the
window produces a plan that cannot be activated. Recorded because the failure is
instructive: the window is the single source, and a fix that does not move it is
fighting the validator.

## Result on the pilot trip

`best_balance` is **ready and valid with all 13 landmarks**, worst day 39 minutes of
plain walking and longest leg 22, inside the owner's 60-per-day and 25-per-leg caps.
Activated as `plan_b5daf13eaa294e78a5d365063be5a260`.

The two flight days now read honestly:

| Day | Window | Content |
|---|---|---|
| 2026-12-29 | 17:40–22:00 | airport 60, transfer 45, check-in 30 → free from 19:55 |
| 2027-01-04 | 07:40–10:40 | checkout 07:40, transfer 08:25, airport 09:10 |

**29 Dec schedules nothing, and that is correct**, not a residual of this defect.
Check-in ends 19:55 and every one of the 13 landmarks returns
`NO_VALID_VISIT_INTERVAL` for that day — they are all shut by then. The evening is
free rather than planned, which is the true answer for a 17:40 landing. Ximending is
outside the door.

Cost of the whole change: **US$0.00**. The route and opening evidence were already
bought; only the window arithmetic moved.

## Tests

- `test_a_departure_day_too_short_for_its_flight_does_not_empty_the_trip` — built on
  `dali-hotel-backtracking-pattern` with `include_operational_timeline` switched on,
  so it reproduces on a **fixture** rather than needing the pilot database. Asserts
  visits survive elsewhere, no `NO_SELECTED_PLACE_COULD_BE_SCHEDULED`, no visit on the
  departure day, and the three logistics blocks present on it.
- `test_the_departure_day_window_opens_early_enough_for_the_flight` — the root fix,
  through `_optimizer_input`, asserting `07:40–10:40` and that the arrival day and the
  middle day are untouched.

Both were negative-tested. Neutralising the window fix leaves `08:00`; neutralising
the `sequence or items` guard schedules `dali_town` at **07:40 on the departure day**,
during the airport run — so the guard is load-bearing in both directions.

336 tests green, 27 of 27 historic regressions unchanged, all 12 `check.py` stages
pass.

## Related

- `WF-041` — per-day opening hours, fixed the day before. Same shape of blind spot:
  a per-day quantity handled trip-wide, invisible to a fixture suite made of day
  trips. This one is per-day *feasibility* rather than per-day data.
- `WF-043` — the time-limited variant, found while measuring this. Independent, and
  exposed rather than caused by this fix.
- `WF-038` — transit. It is what made the trip 13 landmarks over seven days, which is
  what made a flight day matter.
