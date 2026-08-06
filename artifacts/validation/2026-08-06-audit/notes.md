# Audit: overlooked tickets, and every page's UX

Asked for two sweeps. Both found real defects.

## Tickets: 39 of 41 closed, and nothing lost

The two open ones are `WF-039` (comfort-tradeoff acceptance) and `WF-040`
(accommodation recommendation), both raised during this week's pilot work and both
deliberately unresolved.

The map's **"Not yet specified"** list is where anything would hide, and five of its
six items are deferrals by decision — voided rows in exports, GenAI revision
presentation, per-person cost feeding upstream, the unused donut and bar charts, and
the archival mechanics settled today. The sixth was not a deferral.

### The overlooked item: two refusal codes nobody could read

The map asked whether the `PlannerRefusal` migration needed its own ticket. It is
effectively done — 51 `PlannerRefusal` raises against **one** remaining raw
`ValueError`, and that one is an internal invariant ("Provider result must be an
object"), not something an owner can cause. Correct as it stands.

But checking the 28 codes actually raised against the copy catalogue found
**`unknown_split_row` and `unknown_traveller` with no text in *either* language.** Both
came from S2's split ledger. Every owner, in both languages, saw
`⚠ unknown_split_row`.

**The key-parity test passed the whole time**, because both `en` and `th` lacked the
key equally. Parity is symmetry, not coverage — it can never catch a code missing from
both sides. So the fix is two entries plus a new test that walks the AST for every
`PlannerRefusal(...)` raised in the core and asserts each has text in both languages.
Negative-tested: deleting one Thai entry fails it.

## Pages: two real defects, both functional rather than cosmetic

All nine routes captured and read.

### `/costs` had no way to record a cost

The screen said *"Add estimates to see the plan against actual spend"* and contained
**zero mutations**. `save_cost_item` was allowlisted the entire time and unreachable
from the interface, while `/split` could record bills perfectly well. So the
planned-versus-actual comparison — the whole point of `WF-023` — could only ever
compare nothing, which is exactly why the pilot's Costs sheet was empty until rows
were written through the API by hand.

Now there is a form: what it is for, amount, currency, category, and a paid checkbox,
with a warning when a non-THB amount has no rate snapshot to convert against. Its
labels reuse `split_amount`/`split_currency` and the plain category keys the table
already uses, rather than inventing a parallel vocabulary — the first attempt did
invent one and the missing-copy assertion caught all six.

### `/optimize` looked broken once a plan was active

Activation deletes the preview by design, so with a plan active the page rendered a
title, one sentence and a button. Nothing said a plan existed, nothing linked to it,
nothing explained the emptiness. It read as a failure rather than as finished.

It now states that a plan is active, links to it, and says why the drafts area is
empty.

### The other seven

`setup` reads well — five clear steps, the indicator honest about step-count.
`places` was rebuilt earlier today. `evidence` states each card's cost before its
button. `itinerary`, `readiness`, `split` and `revise` all render their content with
honest empty states.

One cosmetic thing left alone: `/costs` prints "No cost rows yet" twice, once in the
category table and once above the rows. Harmless duplication, and worth less than the
diff to remove it.

## What the audit says about the gates

Neither defect was catchable by anything already in `check.py`. A screen with no
mutation still typechecks, lints, renders and passes its baseline; a refusal code with
no copy passes key parity. Both needed someone to open the page and read the
vocabulary. That is worth remembering the next time twelve green stages feel like
proof.
