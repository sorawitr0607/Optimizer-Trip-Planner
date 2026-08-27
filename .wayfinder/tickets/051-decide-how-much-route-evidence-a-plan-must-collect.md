---
id: WF-051
title: Decide how much route evidence a plan must collect before it builds
status: closed
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide how much route evidence a plan must collect before it builds

## Three rounds on one report, and the first two moved the number the wrong way

The owner reported a build that loaded for twenty minutes. The first round blamed the
browser's patience and widened nothing it should have. The second found real head-of-line
blocking — one worker, one job, an 843-second sweep starving a three-second plan build —
and bounded a single job. The queue stopped starving and the wait got **longer**, because
bounding a job does not shorten the work; it moves it into the caller's loop. Ten short
jobs in series, with progress resetting the client's deadline on each, is 1200 seconds
where one long job was 843.

The question underneath all three rounds had never been asked: **how much route evidence
does a plan actually need?** Every round had assumed the answer was "all of it".

## Decision

- **Coverage is the goal, not completeness.** A place with no route at all is dropped
  `ROUTE_UNVERIFIED` by `travel_planner/optimizer.py`; a missing pair between two places
  that each have one is a leg the optimizer routes around. `travel_planner/actions.py`
  reports `places_unserved` and `web/src/shared/routeEvidence.ts` stops on it rather than
  on `more_pairs`, which stays true until every one of a trip's N·(N−1) ordered pairs is
  measured. The remaining pairs are refinement and are still collectable from `/evidence`.
- **Reach every place inside one pass.** Pair selection promotes the nearest pair that
  reaches a place nothing ahead of it has reached, in **both directions** — the optimizer
  matches a leg origin-to-destination and does not read a stored one backwards, so a
  single direction buys a place out of `ROUTE_UNVERIFIED` and still leaves a segment the
  plan can arrive at and cannot depart from.
- **Measure the whole trip in one request where the provider offers it.**
  `travel_planner/providers.py` gains a walking-matrix provider whose operation has been
  priced at US$0.00 in `travel_planner/usage.py` since before anything called it. It
  carries **no geometry**, so the trade is explicit: times arrive at once and drawn lines
  arrive afterwards, upgraded pair by pair by the existing directions sweep. A trip past
  the endpoint's ceiling, an unreachable service or a missing key all degrade to exactly
  the behaviour that came before.
- **A bound is read where the work is.** The sweep's wall-clock budget is consulted before
  each provider request, not only before each new pass — checked between passes it could
  never fire, because one pass already exceeded it.
- **The queue is answerable for its own duplicates and its own orphans.** Enqueueing looks
  and inserts in one transaction under a lock keyed on the operation's identity, rather
  than in two transactions with a gap; deleting a trip discards its jobs, which no foreign
  key can do because the queue sits outside `SCHEMA_VERSION` by an earlier decision.
- **A worker's health endpoint describes the service, not the machine.** It answers any
  GET on an unauthenticated port, so it names neither host nor process.

## Resolution comments

### 2026-08-27

Diagnosed from the stored data rather than from the code. Grouping the reported trip's 554
route rows by the minute they were retrieved gives ten bursts of sixty, and **every place
had a route by burst two** — the other eight measured pairs between places that already
had one. That reordered the fix: the loop's stop condition was the twenty minutes, and the
selection order, which the first diagnosis had blamed for all of it, cost one burst. An
earlier draft of this ticket and of the durable notes said nine; the stored rows said two,
and both were corrected.

The matrix path was measured against the live endpoint before it was written down: 23
places, **506 pairs in one request in 1.59 seconds**, against 0.87 seconds for a single
directions call from the same machine. Route work across a build falls from roughly 197
seconds per job across eight to ten jobs, to one job of about 62 seconds — no longer the
largest part of a build, where area recommendation averages 40 seconds and the optimizer
23.

Verified free rather than assumed free: both route operations are priced at zero, and the
month closed unchanged at US$6.913 / US$10.

The remedies offered beside a `NO_TIME_CAPACITY` refusal had shipped unpressed, because no
live trip had produced one. They are checked where it counts rather than on the controls:
squeeze a historic fixture to a single two-hour day, confirm the refusal, then add a day
and assert more places fit, and drop the refused places and assert the refusal clears. A
control beside a refusal that does nothing is worse than the dead end it replaced.

Two gate defects that had been carried as written warnings across three handoffs became
mechanisms instead: `scripts/check.py` refuses a concurrent run rather than letting two of
them share the capture directory and fail like drift, and the screen-baseline gate's own
failure-path test no longer prints a failure into a passing suite. A third became a test —
any dialog class given a `display` must restate the closed-state rule, or the sheet paints
over every phone screen while closed.

## Related

- [Decide how feedback-driven dashboards show progress and estimates](050-decide-how-feedback-driven-dashboards-show-progress-and-estimates.md)
- [Decide how the planner gets transit routing](038-decide-how-the-planner-gets-transit-routing.md)
- [Decide how cost chooses between verified and assumed hours](047-decide-how-cost-chooses-between-verified-and-assumed-hours.md)
