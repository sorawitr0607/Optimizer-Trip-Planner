---
id: WF-043
title: Decide what a variant returns when it runs out of time
status: open
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide what a variant returns when it runs out of time

## `more_highlights` returns worse than the baseline it already computed

Found 2026-08-06 while measuring `WF-042`. On the real pilot input, the third variant
returns a schedule with **0 visits** while its own greedy baseline, recorded in the
same object, scheduled **13**:

```
best_balance     visits=13  stopped_at_limit=False  improved_or_equal=True
relaxed          visits=12  stopped_at_limit=False  improved_or_equal=True
more_highlights  visits=0   stopped_at_limit=True   improved_or_equal=False
                 greedy_baseline: 13 visits, objective_tuple [0, 0, 1, -747.8, 460, 0]
                 returned:                   objective_tuple [0, 11, 0, -101.0,  20, 0]
```

`objective_improved_or_equal_to_greedy` is **`False`** — the invariant is measured,
reported, and then not acted on. `greedy_baseline` is a valid schedule sitting in the
same payload, and the variant discards it in favour of a strictly worse incumbent that
misses eleven `must_do` places.

The variant is nonetheless labelled `status: "ready"` with `validation.valid: true`,
because an empty schedule violates nothing. So the screen offers the owner a third
option that is internally consistent, passes every hard check, and is useless.

## It is wall-clock dependent, and the determinism guard cannot see it

`more_highlights` is `duration: minimum, buffer_minutes: 5`, so more candidates fit
per day and the search space is the largest of the three. It is the only variant that
hits the limit.

The cut-off is `time.monotonic()`, so the result depends on machine load. Measured on
the same input: **0 visits in eleven runs across seven processes, 2 visits in one run**
taken while the machine was busier. That contradicts the documented guarantee that
"same input + same `OPTIMIZER_VERSION` must yield the same proposal".

`deterministic_signature` cannot catch it: it was identical (`ee6c171a…`) across every
one of those runs, including the one that returned 2 visits, because it hashes the
**input**. The one guard that would notice is `objective_improved_or_equal_to_greedy`,
and it is a report rather than a rule.

The architecture note says "at the time limit it returns only a labelled valid
incumbent, never a partial schedule". It does honour that literally — the incumbent is
labelled and valid. What it does not do is return the *best* thing it knows about.

## Why it was invisible until now

Every historic fixture is small enough to finish: 4 to 6 candidates over 1 or 2 days.
The pilot is **13 candidates over 7 days** — a search space that only came into
existence when `WF-038` added transit and `WF-041` recovered the Monday-closed venues.
Before `WF-042` all three variants returned 0 visits for an unrelated reason, which
masked this completely.

## What has to be decided

- **Fall back to the greedy baseline whenever the incumbent is worse.** Smallest and
  restores determinism to the extent that greedy is deterministic, which it is. It
  makes `objective_improved_or_equal_to_greedy` a rule instead of a remark, and that
  flag is already computed and stored, so nothing new is measured.
- **Raise or remove the time limit for this variant.** Does not fix the class: a
  bigger trip hits any limit, and the failure mode stays silent when it does.
- **Make a limited variant `status: "unavailable"` rather than `"ready"`.** Honest, and
  the owner simply loses the third option. Cheap, but it throws away a valid 13-visit
  schedule that has already been computed.
- **Make the search deterministic under a limit** — bound by nodes explored rather
  than wall clock. Removes the load dependence properly and is the largest change.

Whichever is chosen, `status: "ready"` for a schedule that misses eleven `must_do`
places should not survive it, and the determinism claim in `CLAUDE.md` needs either a
fix or an honest exception naming the limited case.

## Not urgent for the pilot

`best_balance` is activated with all 13 landmarks and does not hit the limit. This
costs the owner one of three options on `/optimize`, not the trip.

## Related

- `WF-042` — found while measuring it; exposed this rather than causing it.
- `WF-039` — comfort-tradeoff acceptance, also open, also a case of machinery that
  reports a condition without acting on it.
- `WF-040` — accommodation recommendation. Third instance of dead-by-construction
  optimizer output found during the pilot.
