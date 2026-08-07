---
id: WF-039
title: Decide how an owner accepts a comfort tradeoff
status: closed
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

## The deadness is deeper than this ticket recorded

Measured 2026-08-07, before building. The ticket names two mutually exclusive
conditions; there is a third, and it comes first.

**No call site ever produces `fits_with_tradeoff`.** Walking every
`_reconciliation(...)` call in the AST returns exactly two statuses: `fits` and
`cannot_currently_fit`. So the status the whole acceptance route keys on is never
written, and **four** readers are dead rather than one:

| Reader | What it can never do |
|---|---|
| `optimizer.py` `accepted_reasons` | suppress a threshold violation |
| `optimizer.py` `has_unaccepted_tradeoff` | make a variant `provisional` |
| `optimizer.py` `_comfort_violation_count` | count a reconciliation tradeoff |
| `travel_planner/exports.py` line 65 | list a tradeoff in the export snapshot |

That changes the fix. The three threshold violations carry `subject_id: None` — they
are properties of the **whole variant**, not of a place — so routing consent through a
per-place reconciliation record was the wrong shape to begin with. Reviving
`fits_with_tradeoff` would have meant inventing a per-place attribution for a
variant-level condition, which is fabrication.

## Decided and built 2026-08-07: acceptance on the snapshot, bounded by its value

The first option — wire the flag — with the carrier changed for the reason above.

**An acceptance is a number, not a yes.** `comfort_acceptances` (new table, schema
**14**) stores the *measured value the owner agreed to* per threshold code, and
`optimizer._accepts` requires `measured <= accepted_value`. That is what the ticket
demanded of any fix: agreeing to a 27-minute leg must never bless a 90-minute one after
a replan. A *tighter* plan than the one agreed stays covered, so nobody is asked again
when the plan improves.

**Consent reaches both readings of a violation, not just the fatal one.** Clearing only
the hard error would have half-fixed it. `comfort_violations` sits above
`experience_value` in the objective tuple, so the search *drops a place* rather than
exceed a budget — the plan stays valid and the owner silently loses a stop. So
`_comfort_violation_count` consults acceptances too.

Measured on `jp-shibuya-plain-walk-overload`, the historic three-place fixture with a
40-minute daily walking budget:

| | Visits | Worst day |
|---|---|---|
| No acceptance | **2** of 3 | 35 min |
| Agreed | **3** of 3 | 70 min |

The third place comes back, at exactly the walking cost the owner agreed to. That is the
feature, and it is a stop recovered rather than merely a validator persuaded.

**One rules table.** `optimizer.COMFORT_RULES` pairs each `reason` code with its
violation code, metric, fallback metric and threshold key, and the validator, the soft
count, `actions.comfort_tradeoffs` and the screen all read it. A test asserts every
metric it names is one the optimizer actually reports, so a typo cannot silently make a
rule never fire.

### Surface

`ComfortTradeoffs` on `/optimize`, above the variant picker — an overage is *why* a
variant will not activate, so the choice has to precede the button that refuses. The
button reads **"Agree to 27 min"**, not "Accept", and sends that number. When a replan
pushes past what was agreed, the row says so and asks again rather than staying quietly
green. Four new methods take the allowlist to **68**; `REFUSAL_STATUS` to 34.

Accepting a value already inside the cap is **refused** (`comfort_value_within_threshold`)
rather than stored, because a permission recorded when nothing needed permitting is one
left lying around for a later, worse plan.

### The schema bump

13 → 14, done 2026-08-07 and **rehearsed on a byte-identical copy first**, exactly as the
12 → 13 bump was. The rehearsal confirmed: one new table, `user_version` 14, and **no
row-count change in any pre-existing table**. `data/tourist-pre-v14-2026-08-07.sqlite3`
is the only way back and was verified byte-identical to the pre-bump state.

Timing is not incidental. `WF-024` forbids any schema change between **29 December 2026
and 4 January 2027**, which is the trip itself, so this had to land before the window or
wait until the trip was over.

### Tests

`tests/test_comfort.py`, 14 tests. The four that carry the decision:
`test_agreeing_to_27_minutes_does_not_bless_90`,
`test_an_improvement_on_what_was_agreed_is_still_covered`,
`test_an_acceptance_of_one_budget_does_not_cover_another`, and
`test_acceptance_buys_a_place_back_and_not_only_a_passing_validator`.

Negative-tested: making `_accepts` return a bare `True` fails the 90-minute test, and
removing the acceptance check from `_comfort_violation_count` fails the place-recovered
test — so both halves are load-bearing. 365 tests green, 27 of 27 historic regressions
unchanged, all 12 `check.py` stages pass.

### What was deliberately not done

The ladder is untouched. Options two and three — letting the owner type the two numbers,
or adding rungs — both remain unbuilt, and the second only moves the cliff. With consent
reachable, the ladder's gaps stop being a trap: an owner two minutes over now agrees to
those two minutes instead of dropping every walking guard for the whole trip.

`has_unaccepted_tradeoff` and the `travel_planner/exports.py` tradeoff list are **still dead**, because
nothing produces `fits_with_tradeoff` and inventing a producer would mean attributing a
variant-level condition to particular places. Recorded here rather than quietly deleted;
removing them is its own decision.

## Related

- `WF-043` — where the objective-ordering consequence was first measured, while fixing
  the time-limited variant.
- `WF-038` — transit routing. With transit the inter-district hop stops being a
  walk at all, so this cliff is met far less often. It does not remove it.
- The per-day measurement bug found alongside this is **already fixed**: a
  whole-trip walking total was compared against a per-day budget, making an n-day
  trip n times too strict. It was invisible to the fixtures because 25 of 27 are
  single-day. That was a straightforward defect, so it was fixed with a test
  rather than deferred here; all 27 regressions still pass.
