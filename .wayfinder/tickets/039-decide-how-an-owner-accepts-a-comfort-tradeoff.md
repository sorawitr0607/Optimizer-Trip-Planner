---
id: WF-039
title: Decide how an owner accepts a comfort tradeoff
status: open
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide how an owner accepts a comfort tradeoff

## The escape hatch is unreachable by construction

`optimizer.validate_variant` is written to let an owner accept a comfort overage
instead of being blocked by it:

```python
accepted_reasons = {
    item["reason"]
    for item in variant.get("reconciliation", [])
    if item["status"] == "fits_with_tradeoff"
    and not item.get("owner_acceptance_required", True)
}
```

A threshold violation is then suppressed when its reason is in that set —
`PLAIN_WALK_THRESHOLD`, `LONG_TRANSFER_WALK`, `HEAT_AND_CYCLING_LOAD`.

But the flag is built as:

```python
"owner_acceptance_required": status == "fits_with_tradeoff",
```

So every `fits_with_tradeoff` item **always** has `owner_acceptance_required:
True`, and the set comprehension requires `fits_with_tradeoff` **and not**
required. The two conditions are mutually exclusive: **`accepted_reasons` is always
empty and the acceptance path is dead code.**

There is also no action anywhere that records an acceptance — nothing in
`actions.py` writes the flag, and no allowlisted method exposes it. The mechanism
was designed and never wired.

## Why it matters, measured

Found 2026-08-05 while trying to get the real Taipei trip to validate. With the
ten clustered landmarks and the per-day walking fix in place, the plan comes down
to **one 27-minute walking leg** against a 25-minute limit. Two minutes.

There is no way to accept it. `_comfort_thresholds` is an `elif` ladder with only
three rungs and then nothing:

| Setting | per leg | plain / day |
|---|---|---|
| `low_walking` in comfort | 15 | 35 |
| `plain_long_walks` in avoid | 20 | 45 |
| `balanced_pace` in comfort | 25 | 60 |
| none of them | **no cap** | **no cap** |

So an owner who is two minutes over on one leg has exactly two options: abandon
the plan, or drop the cap **entirely** and lose every walking guard for the whole
trip. Accepting one specific leg — which is what the reconciliation vocabulary
already describes — is not expressible.

## What has to be decided

- **Wire the existing flag.** Smallest change: `owner_acceptance_required` becomes
  false once an acceptance is recorded, and a new action records it per reason or
  per leg. Needs a store field, an allowlisted method, and a screen control. It
  also needs care that an acceptance is invalidated when the plan is rebuilt —
  accepting a 27-minute leg must not silently bless a later 90-minute one.
- **Make the ladder continuous.** Let the owner set the two numbers directly
  rather than inferring them from tag combinations. Honest and simple, but it
  turns a preference vocabulary into a settings form, which `WF-007` deliberately
  avoided.
- **Add rungs to the ladder.** Cheapest, and it only moves the cliff rather than
  removing it. Someone will be two minutes over the new rung.
- **Leave it.** Defensible only if the thresholds are meant as hard safety limits
  rather than comfort preferences — but `_comfort_thresholds` is named for comfort
  and derived from taste tags, so that reading does not hold.

## Related

- `WF-038` — transit routing. With transit the inter-district hop stops being a
  walk at all, so this cliff is met far less often. It does not remove it.
- The per-day measurement bug found alongside this is **already fixed**: a
  whole-trip walking total was compared against a per-day budget, making an n-day
  trip n times too strict. It was invisible to the fixtures because 25 of 27 are
  single-day. That was a straightforward defect, so it was fixed with a test
  rather than deferred here; all 27 regressions still pass.
