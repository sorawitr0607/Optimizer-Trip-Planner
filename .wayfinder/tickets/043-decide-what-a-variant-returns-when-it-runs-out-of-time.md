---
id: WF-043
title: Decide what a variant returns when it runs out of time
status: closed
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

## The cause is a shared deadline consumed in order, not a slow variant

Measured after the ticket was written, and it corrects the guess above.
`optimize_trip` computes **one** absolute deadline and hands the same one to all
three variants:

| Variant | Time taken | Budget left after | Visits |
|---|---|---|---|
| `best_balance` | 20.74s | 9.26s | 13 |
| `relaxed` | 10.40s | −1.14s | 12 |
| `more_highlights` | **0.04s** | −1.18s | **0** |

`more_highlights` starts already past the deadline, trips the check at candidate
index 0, and returns the initial empty state. Given its own 30 seconds it finishes in
**21.48s with all 13 visits, valid**. It was never infeasible and it is not
intrinsically slower in a way that matters — it simply ran last.

So the third variant is starved *structurally*, for any input where the first two use
the budget. Nothing about `duration: minimum, buffer_minutes: 5` is at fault.

## It is wall-clock dependent, and the determinism guard cannot see it

`more_highlights` is the only variant that hits the limit, because it is the only one
that runs with the budget already spent.

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

## Decided and built 2026-08-06: a budget each, and greedy as a floor

The owner asked for all of it. Two changes, addressing cause and consequence
separately, because either alone leaves a real hole.

**1. One budget per variant.** `deadline=monotonic() + time_limit_seconds` moves inside
the comprehension, so each variant gets the full budget rather than the remainder.
Worst case becomes `len(VARIANT_CONFIGS) × time_limit_seconds`. This fixes the actual
cause: nothing is starved.

**2. Greedy is a floor, not just a report.** `_greedy_sequences` is split out of
`_greedy_baseline`, and `_insertion_search` consults it when the deadline does fire,
taking it whenever it beats the partial beam by the same `_search_objective` the search
already sorts by. Greedy sweeps **every** candidate and has no time limit, so it is
always affordable. This fixes the consequence, which change 1 does not: a genuinely
slow input can still expire, and when it does the answer is now never worse than a
schedule already in hand.

### Result

All three variants `ready`, `more_highlights` at **13 visits**, and **no variant hits
the limit**. Identical across three consecutive runs including
`deterministic_signature` (`bbca02ab2fe9…`).

The honest cost: a full proposal takes **~52s** rather than ~31s, because the third
variant now does its 21s of work instead of returning nothing in 0.04s.

Determinism is restored *in practice* because nothing expires. The wall clock is still
the bound, so a slow enough input remains load-dependent in **which** answer it
returns — but no longer in whether that answer is usable, since greedy floors it.
Bounding the search by nodes explored rather than time was the fourth option and is
not built; it is the only way to make the limited case bit-identical, and nothing
currently reaches it.

### One measured finding worth keeping

`jp-shibuya-plain-walk-overload` still returns 0 visits under an expired budget, and
that is the objective, not the fallback failing. Its greedy schedule carries a comfort
violation, and `comfort_violations` sits **above** `experience_value` in the objective
tuple, so scheduling nothing genuinely outranks scheduling three places uncomfortably.
Whether that ordering is right is `WF-039`'s question, not this one. Likewise
`dali-hotel-backtracking-pattern`, whose greedy pass carries a missing route edge and
so loses on the tuple's first element — the first fixture tried for the test, and the
wrong vehicle for it.

### Tests

- `test_a_variant_cut_off_by_the_limit_is_never_worse_than_greedy` — a budget of one
  microsecond expires before candidate 0, so all three visits in the result come from
  the greedy floor.
- `test_each_variant_gets_its_own_time_budget` — asserts three distinct, strictly
  increasing deadlines. Structural on purpose: reproducing real starvation needs a
  snapshot slow enough to burn 30 seconds, which no fixture is.

Both negative-tested — neutralising the fallback fails three subtests, restoring the
shared deadline fails the second test. 339 tests green, 27 of 27 historic regressions
unchanged.

## Related

- `WF-042` — found while measuring it; exposed this rather than causing it.
- `WF-039` — comfort-tradeoff acceptance, also open, also a case of machinery that
  reports a condition without acting on it.
- `WF-040` — accommodation recommendation. Third instance of dead-by-construction
  optimizer output found during the pilot.
