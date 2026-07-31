# Cost and split reconciliation rules

Resolves `Decide cost-and-split reconciliation rules` (WF-023).

Decided 2026-07-31 through the reconciliation interview. Measured against the checkout at `0106ac0`.
Paths are repo-relative.

## The seven decisions

| # | Question | Decided |
|---|---|---|
| 1 | Double counting | **A split row may claim a cost row.** A claimed row keeps its estimate and **defers its actual** to the split side |
| 2 | Where the comparison is read | **On the cost screen, per category** — estimated, actual, difference |
| 3 | Rate policy | **Split inherits the cost ledger's timestamped snapshot**, with the buffer skipped |
| 4 | Category mapping | **The seven categories are the default tag vocabulary**; owner additions get assigned |
| 5 | Cost per person | **Headcount for estimates, `split.py`'s resolved shares for actuals** |
| 6 | An unreconciled difference | **A visible gap, non-blocking** |
| 7 | A partially settled trip | **A per-traveller settled marker** — a marker, not a payment record |

## 1. Claiming, and why double counting becomes structurally impossible

The overlap the ticket named: a cost row marked `paid` locks an `actual_thb`, which is also what a split
row records. Same money, twice.

**A split row gains one optional field: `cost_id`.** That is the claim. It mirrors the two optional links
WF-018 already put on the row (`plan_day`, `place_id`), so the model gains a third link rather than a new
concept.

**Nothing is added to the cost row, and `payment_state` is untouched.** "Claimed" is *derived* — does any
non-voided split row reference this cost row? — so there is no second state to keep in sync and no new
`payment_state` value.

### The arithmetic

```
planned  = every cost row's THB              (regardless of payment_state)
actual   = every non-voided split row's THB
         + every UNCLAIMED paid cost row's locked actual_thb
```

**Double counting cannot happen** because a paid cost row is either claimed — in which case its actual
comes from the split side — or unclaimed, in which case it supplies its own. Never both. The rule is one
sentence, and it holds in the app, the PDF and the six-sheet workbook identically because all three read
`build_export_snapshot()`.

This also keeps `paid` useful for the case it is genuinely good at: **an expense the owner paid that is not
split with anyone.** Without it, a 60 THB metro fare would need a split row with one participant.

### Three rules the claim needs

- **Several split rows may claim one cost row; their THB sums.** A hotel estimated once and paid across
  three nights is the normal case.
- **A claimed row's own `actual_thb` becomes inert.** The UI must say why rather than leaving a dead field —
  it is not editable-but-ignored, it is superseded.
- **Unclaiming restores the row exactly.** Since claimed-ness is derived from `cost_id`, clearing that field
  is the whole operation; nothing needs undoing.

## 2. `costs.totals()` needs two new figures, and no existing key changes

Reading `totals()` (`costs.py:155`) closely turns up a mismatch this ticket has to fix:

```python
unpaid = [item for item in resolved if item.get("payment_state") not in LOCKED_STATES]
"estimated_thb": round(sum(float(item["reported_thb"]) for item in unpaid), 2),
```

**`estimated_thb` is the sum of *non-paid* rows only.** So a row that was estimated at 1,200 and later
marked paid drops out of `estimated_thb` entirely. That is correct for its original purpose — "what is
still to pay" — but it is **not** the plan figure, and plan-versus-actual per category needs every row's
estimate including rows later paid.

So `totals()` gains two keys and changes none:

| Key | Meaning |
|---|---|
| `planned_thb` | **new** — every cost row's THB, whatever its state. The plan figure |
| `actual_thb` | **new** — non-voided split rows + unclaimed paid cost rows, per §1 |
| `estimated_thb` | unchanged — non-paid rows only, i.e. still to pay |
| `paid_thb` | unchanged |
| `total_thb` | unchanged |
| `by_category` | unchanged; a parallel per-category planned/actual breakdown is added beside it |

Adding rather than redefining keeps every existing export, view and test working. A redefinition would land
identically in the app, the PDF and the workbook — wrong in three places at once.

## 3. The cost screen is where the comparison is read

The owner's framing: the split screen is transactions with aggregate views above them, as Auto-Bill does;
the cost plan is the overview cost breakdown — ticket, hotel, eating — including cost per person estimated.
So the comparison belongs where the overview already is, and no third screen is invented.

```
COST OVERVIEW                planned    actual     diff
  accommodation (hotel)       12,000    11,450     -550
  activity (tickets)           8,400     9,120     +720
  food (eating)                9,000     6,880   -2,120
  ─────────────────────────────────────────────────────
  per person (estimated)       4,850
```

`/split` stays exactly as described — transactions plus Auto-Bill's aggregates — uncluttered by estimates.

Three consequences, accepted:

- The cost screen now reads from **both** ledgers, so it is the screen that misreports if the claim relation
  is wrong. That is the price of the comparison living somewhere useful.
- Mid-trip, "actual" is incomplete by definition, so every difference reads better than reality until the
  trip ends. The wording must not imply a final verdict.
- Categories with a plan and no actual, and categories with an actual and no plan, both need a sensible
  empty state rather than a misleading zero.

## 4. The category mapping is nearly free

The two vocabularies are almost the same:

| `costs.CATEGORIES` (7) | Auto-Bill (6) |
|---|---|
| `transport` | `transport` |
| `accommodation` | `accommodation` |
| `activity` | `activities` |
| `food` | `food` |
| `shopping` | `shopping` |
| `other` | `others` |
| `fees` | **no counterpart** |

Two differ only by plural, and `fees` is the single category with nothing on the other side.

**So the seven are the default tag vocabulary.** A tag that is one of the seven maps to itself, which means
**most trips need no mapping at all**, and lifted Auto-Bill rows land correctly on arrival. An owner-added
tag — "Disney tickets", "souvenirs for Mum" — is assigned to one of the seven, defaulting to `other` until
it is.

This stays owner-defined as WF-018 requires: the defaults are a starting vocabulary, not a restriction.

**The mapping lives at one boundary, and that placement is the point.** WF-018 named the precedent for what
happens otherwise: setup and the optimizer held different accommodation vocabularies, and hotel-area
recommendations silently never fired for any app-created trip until `_optimizer_input` translated at the
boundary.

Accepted: an unassigned tag falling to `other` is a silent default, and `other` will quietly absorb things.

## 5. Cost per person — two mechanisms, deliberately

```
estimated per person = planned_thb / headcount        (headcount = owner + len(members))
actual    per person = split.py's resolved shares
```

Each side uses the only mechanism correct for it. An estimate has no participants, so headcount is all
there is. An actual has exact participants, and `split.py` already resolves their shares — reusing it
inherits WF-018's guarantee that there is one rounding implementation, so the screen, the workbook and the
PDF cannot disagree by a satang.

> ### The trap: `group_preference_weights` is not a cost weight
>
> `setup.py:93`–`97` computes per-traveller weights where **the owner gets 0.5 and the members share the
> other 0.5**. The field is named `group_preference_weights` (`setup.py:120`) and it feeds **only
> `ranking.py`** — it is a *taste* weight, expressing that the owner's preferences count for half when
> scoring candidate places.
>
> **Using it for money would charge the owner half the trip regardless of headcount.** It is the nearest
> thing to a per-person weight already in the codebase, which is exactly why it is dangerous.

Accepted costs: two mechanisms behind one label, so the UI must not present estimated and actual
per-person as the same kind of number; headcount ignores that a child or a part-trip joiner does not cost
the same, so the estimate is coarse; and a trip with no members yet divides by 1.

## 6. Rates: one snapshot, one documented exception

Split rows convert through the cost ledger's timestamped per-currency `new_rate_snapshot()`
(`costs.py:62`), inheriting the behaviour that matters: **a missing rate stays a visible gap rather than a
guess**, already reported by `totals()` as `unconvertible_rows` and `missing_rates`.

One rate mechanism is what makes the two ledgers comparable at all. Two would make part of every
plan-versus-actual difference an artefact of conversion rather than of spending.

> **The one exception: `buffer_percent` is skipped for split rows.** The buffer exists to pad *estimates*.
> Applying it to money already spent would inflate history. Cost rows keep it; split rows do not.

WF-018's `actual_thb` lock still wins permanently — a real charge the owner recorded is never re-converted,
whichever ledger it sits in. Auto-Bill's one flat editable rate per trip does not port: a trip crossing two
currencies cannot be represented by it.

Accepted: split rows now depend on a snapshot the owner may not have entered yet, so a new trip can show
gaps immediately. That is the visible-gap behaviour working as intended, not a defect.

## 7. Unreconciled differences warn, never block

Named on screen and in exports; blocking nothing. The precedents are both in this repo:

- The **readiness board** is a mutable record type whose warnings are explicitly non-blocking —
  `blocks_itinerary` is always False.
- **`costs.totals()` already behaves this way**: it reports `unconvertible_rows` and `missing_rates` rather
  than refusing to total.

The gaps this surfaces:

```
⚠ 2 paid cost rows are not claimed by any split row
⚠ TWD has no rate in the current snapshot (3 rows)
⚠ 1 category has actual spend with no plan
```

Blocking export was rejected outright: `WF-022` made the exports a **pilot-ready gate** and they are what
the owner physically carries in Taipei. Refusing to produce a PDF because a rate is missing would mean no
itinerary on the trip.

Accepted: a warning nobody must act on is a warning that gets ignored, and exports carry the app's
uncertainty into a document that may be handed to someone else.

## 8. The settled marker

**One mutable per-trip, per-traveller flag the owner sets.** It records that the owner says a balance is
settled — not an amount, not a date, not a transfer.

**This does not reverse WF-018.** Settling up is still never recorded, and balances remain trip-to-date
computations. It follows the readiness board's precedent: owner-set, mutable, explanatory, and it lives as
its own small mutable record rather than on the split row, since it is per traveller and not per row.

It closes the map's own fog item — "whether a trip that is fully settled in real life gets any marker at
all".

> **The staleness rule, decided rather than left open:** **any change to a marked traveller's balance clears
> their marker.** Adding a split row that includes them, editing one, or voiding one all change the
> arithmetic, and a marker that survives new debt is a lie. Clearing is silent and reversible — the owner
> ticks it again when the new amount is settled too.

Balance wording stays a **suggestion** regardless of the marker, because WF-031 already requires wording
that survives the owner having been paid back while the number does not change. The marker says "I consider
this done"; it does not make the arithmetic mean something different.

## What this adds to the model

| Where | Addition |
|---|---|
| Split row | `cost_id` — one optional link, alongside `plan_day` and `place_id` |
| Cost row | **nothing.** Claimed-ness is derived |
| `costs.totals()` | `planned_thb`, `actual_thb`, and a per-category planned/actual breakdown. No existing key changes meaning |
| New mutable record | per-trip, per-traveller settled marker |
| One boundary | the tag → category map, seeded with the seven |

## Explicitly not decided here

- Where the tag→category map is stored and edited (a settings surface, or inline on the split screen).
- Whether `planned_thb` should exclude voided or dismissed cost rows — cost rows have no void concept today.
- Whether the per-category planned/actual breakdown appears in all six Excel sheets or only the money sheet.
- Whether a part-trip joiner or a child should ever weight the per-person estimate. Deliberately left coarse.

## What this hands downstream

| Ticket | Consequence |
|---|---|
| `Prototype the merged cost and split screen` | **Unblocked — this was its last blocker.** It now has concrete shapes for both screens: the cost overview carries planned/actual/diff per category plus an estimated per-person figure, and `/split` carries transactions with Auto-Bill's aggregates. The claim action, the inert `actual_thb` on a claimed row, the settled marker, and suggestion-not-debt wording are all its to design |
| `Decide the migration path for existing trips and splitter data` | Auto-Bill's imported categories map onto the seeded seven almost exactly; only `fees` has no counterpart. Imported rows need no `cost_id` |
| `Lock the Phase 2 slice plan and validation scorecard` | The `ค่าใช้จ่าย` sheet in the reference workbooks is the validation target for both ledgers, and `planned_thb` / `actual_thb` are the figures to compare against it |
| `Decide which exporter survives, Python or JavaScript` | Whichever wins must emit `planned_thb`, `actual_thb`, and the per-category breakdown from `build_export_snapshot()` |
