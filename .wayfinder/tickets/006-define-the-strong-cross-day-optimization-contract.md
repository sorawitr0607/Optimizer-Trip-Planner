---
id: WF-006
title: Define the strong cross-day optimization contract
status: closed
labels:
  - "wayfinder:prototype"
parent: WF-MAP-001
assignee: user-and-root
blocked_by:
  - WF-004
  - WF-005
---

# Define the strong cross-day optimization contract

## Question

What exact hard constraints, soft scores, route and time inputs, cross-day moves, hotel trade-offs, variant rules, fallbacks, explanations, and measurable solver checks constitute strong optimization for Phase 1?

## Confirmed decisions

### 2026-07-28 — Hard facts and explicit cannot-do limits are inviolable

- Venue closure, missed last entry, prohibited access or travel mode, impossible travel, flights, reservations, countdown anchors, locked events, minimum realistic visit/transfer duration, safety/accessibility limits, and traveller-declared `Cannot do` constraints are hard.
- Walking effort, transfer count, crowds, ideal viewing time, preferred meal window, and day length use the editable setup thresholds. The optimizer may propose exceeding a soft target only as a named tradeoff with the affected member and quantified consequence.
- A user-approved tradeoff becomes an explicit plan-level exception, not a silent permanent weakening of that traveller's profile. Physical impossibility and hard safety/operational facts remain invalid even if an item is forced.

### 2026-07-28 — Taipei validates worldwide rules; it does not define them

- Taipei is the complete Phase 1 pilot dataset and regression target, but no optimizer constraint, score, route move, or itinerary schema may depend on Taiwan-specific place types, currency, language, transit names, holidays, or APIs.
- Core facts use city-independent fields such as IANA time zone, local date/time, ISO currency code, coordinates, opening and last-entry intervals, visit-duration bounds, route-mode capabilities, transfer/walking costs, reservation windows, access rules, weather exposure, and evidence status.
- Local official adapters may populate or strengthen those generic fields. Disabling Taipei Travel and TDX must not change the solver contract or prevent another city from being planned.
- Unsupported transit, missing official rules, and unknown holiday exceptions remain explicit capability/evidence gaps; the optimizer never replaces them with Taipei assumptions.
- Taipei must pass deeply. A later non-Taiwan city with no local adapter must pass the already-defined smoke test before the architecture is described as worldwide-ready.

### 2026-07-28 — Separate physical walking load from sightseeing value

- Every walking segment contributes its real minutes, distance, slope/stairs where known, heat/weather exposure, and surface/accessibility evidence to each traveller's physical-load threshold. Attractive scenery never erases fatigue.
- A walk earns experience value only when it is deliberately planned as a city-walk segment with named, evidence-supported sights, streetscape, market, nature, architecture, or viewpoint highlights along the route.
- The timeline shows those highlights and includes the segment as an experience with its own duration. If the planner cannot identify them reliably, the walk remains ordinary transfer rather than being labelled scenic by inference.
- Plain roadside, station-corridor, parking-area, or otherwise unrewarding walking adds transfer effort with no experience value. The optimizer minimizes this dead walking before reducing worthwhile city walks, while all absolute mobility and safety limits remain hard.

### 2026-07-28 — Distinguish preference priority from a hard lock

- `Must do` carries the highest selection priority. The solver tries alternate dates, times, orders, durations within bounds, and compatible day clusters before leaving it unscheduled.
- `Locked` fixes the confirmed place and its applicable date/time window, normally for a flight, reservation, ticket, countdown, or an owner-accepted commitment. Other activities move around it.
- A Must do that cannot fit remains in reconciliation with the exact conflict and smallest feasible alternatives; it never makes an invalid itinerary appear valid.
- Before promoting a Must do to Locked, show the activities displaced and the resulting travel, walking, meals, timing, and risk. Promotion occurs only after owner confirmation and the new whole-trip solution remains visibly invalid if the lock is physically impossible.

### 2026-07-28 — Use lexicographic whole-trip priorities

Valid plans are compared in this order so many small benefits cannot hide one serious failure:

1. Satisfy hard constraints and locks.
2. Schedule the maximum feasible Must-do priority.
3. Minimize the count and severity of meal, fatigue, accessibility, and day-length threshold violations.
4. Maximize personalized experience value at the supported season, weather, and viewing time.
5. Minimize dead travel, geographic backtracking, unnecessary transfers, and hotel returns.
6. Add Interested and Maybe places only when capacity remains.

Later priorities break ties only after earlier priorities are equal. Every soft exception remains visible even when its plan wins.

### 2026-07-28 — Traveller rules are data-driven, not pilot-shaped

- The solver accepts a collection of travellers of any practical size. Owner role, preference influence, hard constraints, comfort thresholds, availability, and optional inputs are data rather than fixed columns or branches.
- The Taipei profiles—owner age 26, member age 19, mother age 50, and 50/25/25 preference influence—are only pilot fixtures. Age alone never generates a preference or mobility assumption.
- Group scores normalize over supplied preference influence. Hard constraints remain per traveller, and worst-member penalties operate over whichever travellers are present.
- A later phase may add detailed profiles, member voting, changed ownership, or remote responses by producing the same normalized traveller/preferences/constraints input; the ranking and optimizer contracts do not change.

### 2026-07-28 — Jointly optimize an unbooked hotel area with the trip

- Before accommodation is booked, the solver compares plausible hotel areas against every day cluster, airport/rail arrival and departure, countdown or other late anchors, first/last transit availability, repeated hotel returns, nearby meal resilience, and the group's effort thresholds.
- Recommend one default home-base area for the trip plus one runner-up with quantified pros, cons, and total travel/effort differences. Taipei uses one hotel by default; a hotel change is proposed only when a genuinely remote overnight objective justifies its full packing/check-in cost.
- Hotel quality, room suitability, price, and booking evidence remain visible alongside location efficiency; a route-efficient poor hotel cannot win on geography alone.
- Once the owner enters a booked hotel, its location and applicable nights become Locked. The whole trip is recalculated, and any newly infeasible selections or threshold consequences return to reconciliation rather than disappearing.

### 2026-07-28 — Optimize globally first, then preserve accepted-plan stability

- The initial solve considers the complete trip at once rather than constructing days independently. It may move places across dates, swap area clusters, reorder stops, adjust dwell time within each candidate's minimum/ideal/maximum bounds, choose supported transport modes, and reposition meals and rests around fixed anchors.
- Geographic day boundaries are not fixed inputs. Opening/best-time windows, weather exposure, route availability, hotel access, and selected-place compatibility determine which day owns each cluster.
- After the owner accepts a plan, normal revisions add a disruption penalty for changing unaffected dates, locked items, accepted time windows, and confirmed bookings. The solver makes the smallest valid change that satisfies the new request.
- If a broad reshuffle clears a meaningful whole-trip improvement threshold, show it as a separate full-reoptimization alternative with all moved items and gains. The owner can also request `Fully re-optimize` explicitly.
- Every revision produces a deterministic before/after change set and reasons; no accepted item moves silently.

### 2026-07-28 — Attach one actionable fallback to each exposed half-day

- Each outdoor-heavy or otherwise weather-sensitive half-day cluster receives one nearby indoor replacement with comparable group value, supported opening evidence, route compatibility, duration fit, and revised meal/effort consequences.
- The fallback records explicit activation conditions such as rain, dangerous heat, poor air quality, venue closure, or crowd conditions beyond the confirmed threshold, plus the latest useful decision time.
- At the 30-day, 7-day, 24-hour, and owner-triggered same-day refreshes, update both the primary cluster and fallback evidence. Activating a fallback reruns the remaining whole-day schedule rather than merely replacing a name in place.
- If no suitable fallback exists, show that coverage gap before travel and offer a broader replan. Do not provide an unverified generic rainy-day list.

### Confirmed three-variant output

Every solve produces the already-approved `Best balance`, `Relaxed`, and `More highlights` variants from the same hard constraints and evidence snapshot. Relaxed increases buffers and reduces load; More highlights may shorten visits only to their supported minimums and use more of the confirmed soft capacity. A variant that cannot be produced validly is labelled unavailable with the binding reason rather than weakening a hard constraint.

### 2026-07-28 — Never infer a missing worldwide transit leg

- A place whose required transit leg is unsupported or absent remains visible as `Transit unverified`; the optimizer never invents a subway, bus, station, entrance, transfer, or duration.
- Show any verified walking, cycling, driving, or taxi alternative with its evidence and consequences. An unverified transit-dependent candidate may appear only under `Fits with tradeoff`, never `Ready`.
- The owner may open an external map and enter a confirmed mode, duration, transfers, or useful route note. Store it as owner-confirmed evidence for that trip and rerun the itinerary before promoting the leg.
- If the owner does not confirm it, the solver uses a verified alternative or leaves the place unscheduled with the missing-transit reason.

### 2026-07-28 — Bounded runtime with a valid incumbent

- On the target local laptop, generating all three initial variants targets 30 seconds; a normal accepted-plan revision targets 10 seconds. Provider enrichment and route collection occur before these solver budgets and never run inside the search loop.
- At a time limit, return only the best fully validated solution found so far, label that optimization stopped at its limit, and retain its objective breakdown. Never expose a partially constructed or invalid schedule as a plan.
- Offer `Optimize longer` as an explicit owner action. Runtime limits are configurable environment inputs rather than city-specific or pilot-specific solver rules.

### 2026-07-28 — Measurable solver acceptance gates

A generated variant is valid only when all applicable checks pass:

- Zero hard-constraint and lock violations.
- No overlapping visits, absent required travel leg, negative slack, or impossible transfer; every arrival, buffer, visit, and departure forms a continuous local-time timeline.
- Every selected candidate appears exactly once in `Fits`, `Fits with tradeoff`, or `Cannot currently fit`, with its reason and smallest supported alternatives.
- Zero unapproved meal, physical walking-load, accessibility, safety, or day-length threshold violations.
- Unknown opening, access, or required transit evidence prevents `Ready` status.
- No single within-day reorder, move, or swap can remove an A-to-B-to-A-style backtrack or improve the lexicographic objective without damaging an earlier priority.
- The whole-trip solution lexicographically equals or improves on a deterministic day-by-day greedy baseline for the same evidence and selections.
- Every presented variant and activated weather fallback independently passes the same checks; locked items remain unchanged in ordinary replans.
- The same normalized input, evidence snapshot, route matrix, configuration, and solver seed reproduce the same ordered result and explanation.
- Runtime meets the confirmed target or returns a labelled, fully valid incumbent with its objective values and an `Optimize longer` action.

The regression-fixture ticket must exercise these gates against the recorded Japan, Fukuoka, Kunming, and Shanghai failures, including closed arrivals, bad viewing times, unrewarding long walks, backtracking, unavailable transport modes, late meals, crowd/tourist-trap tradeoffs, unclear entrances, invalid showtimes, and missing rain alternatives.

## Resolution summary

Phase 1 performs a city-independent whole-trip solve over evidence-bearing places, routes, travellers, hotel choices, meals, weather fallbacks, and locks. It uses ordered priorities rather than an opaque blended objective, exposes every selected-place consequence, preserves accepted plans during normal revision, and cannot label a schedule Ready unless the measurable validity gates pass.
