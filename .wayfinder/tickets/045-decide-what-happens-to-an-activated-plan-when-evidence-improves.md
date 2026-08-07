---
id: WF-045
title: Decide what happens to an activated plan when evidence improves
status: closed
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide what happens to an activated plan when evidence improves

## One paid lookup left a visit scheduled two hours after closing

Measured 2026-08-07. Sun Yat-sen Memorial Hall was the only chosen place without hours —
`OPENING_NOT_FETCHED` — so the optimizer had scheduled it on an **assumed** window and
the activated plan placed the visit at **17:17–19:32 on 2026-12-30**.

Buying the lookup (US$0.025) returned real hours of **08:30–17:30**. The visit now starts
thirteen minutes before closing and runs two hours past it.

The activated plan did not notice. `get_active_plan(...)` still returned
`variant.validation.valid: true`, because that flag was computed when the plan was built,
against the evidence that existed then. Nothing re-checks an activated plan when the
evidence underneath it changes.

Regenerating fixed it — Sun Yat-sen moved to 2027-01-01 13:54–16:09, inside its window,
and the plan came out *better* on comfort as well (worst day 35 minutes against 39,
longest leg 19 against 22). But that only happened because the evidence was being read
by hand at the time. An owner who bought the lookup from `/evidence` and then opened
`/itinerary` would have seen a plan marked valid with a visit that cannot happen.

## Why the existing gates do not catch it

They gate the **forward** direction only:

- `activate_plan_preview` refuses unless the preview's `input_sha256` still matches
  current choices and the variant is `ready` and valid. That protects activation.
- Discovery and ranking refuse on a `setup_sha256` mismatch. That protects the pipeline.
- `plan_versions` is append-only, so an activated plan is immutable **by design** — which
  is right, and is also why it cannot silently self-correct.

What is missing is a *backward* check: the activated plan holds its own
`optimizer_input`, and nothing compares that against the current one. The hash to do it
with already exists in the stored snapshot.

This is not the same as `WF-036`'s revision flow: `propose_revision` handles the owner
*choosing* to change constraints. Here the owner changed nothing — the world got better
described.

## What has to be decided

- **Compare the stored `input_sha256` against the current one and say so.** Smallest, and
  it needs no new data: the activated version already carries its input. `/itinerary`
  gains a "the evidence under this plan has moved" banner and an offer to regenerate. It
  cannot auto-regenerate — that would rewrite a plan the owner may have printed — so it
  has to be a visible prompt.
- **Re-validate the active plan against current facts on read.** Stronger and more
  expensive: run `validate_variant` against today's snapshot whenever the plan is read,
  and show the violations. Says exactly what broke rather than just that something did.
  Risks reporting churn for a hash change with no scheduling consequence.
- **Invalidate the activation outright.** Refuse to serve a plan whose input has moved.
  Safest and hostile: the owner loses their itinerary for a change that may not affect any
  visit.
- **Leave it and rely on regenerating before travel.** The plan is regenerated whenever
  anything is bought anyway, in practice. But "in practice" here means "because someone
  remembered", and this trip is being planned five months ahead with evidence bought
  incrementally.

Whichever is chosen, `validation.valid: true` on a plan whose evidence has since
contradicted it is the thing that should not survive — an owner reading that word has no
way to know when it was computed.

## Decided and built 2026-08-07: the hash says whether, the validator says what

The first option — compare the stored `input_sha256` against the current one — with the
second folded in behind it, because on its own the hash only says *something moved* and
cannot say whether it matters.

`actions.active_plan_drift` runs two steps, in this order and for different reasons:

1. **Has anything moved?** The activated version stores its own `optimizer_input`, so
   re-freezing it and comparing hashes is exactly the check `activate_plan_preview`
   already makes, run the other way round. No optimizer work at all.
2. **Did it matter?** *Only when the hash moved*, re-run `validate_variant` against
   today's snapshot.

That ordering is what answers the ticket's own objection to option two. Re-validating on
every read risks "reporting churn for a hash change with no scheduling consequence"; the
hash gate means the validator runs only when something actually changed, and its verdict
then separates *the evidence moved and the plan still holds* from *these visits no longer
work*. A test asserts the validator is not called for an unchanged plan and exactly once
for a changed one.

**It reports and never repairs.** `plan_versions` is append-only and the owner may have
printed or shared the itinerary, so regenerating is an offer on the screen, not a side
effect of reading. A test asserts the stored snapshot is byte-identical after a drift
check.

`claimed_valid` and `still_valid` are both returned. The stored flag stays visible beside
today's verdict so the two can be *seen* to disagree, rather than one quietly overwriting
the other — an owner reading `valid` has no way to know when it was computed, which is
the thing this ticket said should not survive.

### The screen

A warning banner on `/itinerary`, above the day picker, with two distinct wordings and a
link to rebuild. Conflating "still holds" with "no longer works" would train the owner to
ignore it. Its own query with `retry: false`, deliberately separate from the export
snapshot: **a plan that no longer holds must still render**, or the owner loses the
itinerary they opened the page to read.

`active_plan_drift` is the 71st allowlisted method, and a read.

### Tests

`tests/test_plan_drift.py`, 6 tests, including the regression itself — activate a plan
built on the 09:00–21:00 assumption, buy narrow verified hours, and assert
`moved: true`, `claimed_valid: true`, `still_valid: false` with `CLOSED_DURING_VISIT`.
Negative-tested twice: never re-validating fails two tests, and comparing the stored hash
against itself fails three.

393 tests green, all 12 `check.py` stages pass. On the pilot the current plan reports
`moved: false` — it was regenerated after the lookup that exposed this.

## Related

- `WF-044` — the lookup that exposed this, and the reason more evidence is expected to
  arrive late.
- `WF-042` — the last time an activated plan had to be regenerated after inputs changed
  (flight times). That one refused loudly at generation; this one did not refuse at all.
