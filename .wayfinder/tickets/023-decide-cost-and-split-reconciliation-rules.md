---
id: WF-023
title: Decide cost-and-split reconciliation rules
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
blocked_by:
  - WF-018
---

# Decide cost-and-split reconciliation rules

## Question

With two ledgers deliberately kept — planner cost rows as budget and estimate truth, the split ledger as
actual group spend — what does "the trip cost" mean, and what stops the same money being counted twice?

## Context

The destination interview chose two linked ledgers over one merged record, so reconciliation is a named
open problem rather than an accident.

- Today `costs.totals()` (`travel_planner/costs.py:155`) already reports `estimated_thb`, `paid_thb`,
  `total_thb`, a per-category breakdown, and the rows no rate could cover. That function is the current
  answer to "what does the trip cost", and it is computed from cost rows alone.
- Cost rows already have a `paid` state with a locked `actual_thb` — which is *also* what a split
  transaction records. That overlap is exactly where double counting will happen.
- The rate story differs by ledger unless this ticket unifies it: cost rows convert through a timestamped
  per-currency snapshot with an optional buffer, and refuse to invent a missing rate (`rate_missing` stays
  visible). Auto-Bill uses one flat editable rate per trip.
- Both totals reach exports: `travel_planner/exports.py` builds the one shared export snapshot that the
  poster, PDF, and six-sheet Excel workbook all read, and `CLAUDE.md` requires every new output to read
  `build_export_snapshot()` rather than a raw variant, precisely so numbers cannot diverge between outputs.
- The readiness board is the precedent for a mutable record type with non-blocking warnings
  (`blocks_itinerary` is always False), if reconciliation gaps should warn rather than block.

The split ledger model is now decided, and it hands this ticket three specific inheritances:

1. **A category mapping is mandatory, not optional.** Split rows use owner-defined tags while cost rows use the
   fixed seven (`transport`, `accommodation`, `activity`, `food`, `fees`, `shopping`, `other`). The two ledgers
   cannot be summed on one category axis without it. Put it at a boundary — the precedent for what happens
   otherwise is the accommodation vocabulary that silently killed hotel-area recommendations for every
   app-created trip.
2. **Rate policy is this ticket's call.** Split rows store only original amount and currency, and derive THB at
   read time, so this ticket decides whether they convert through the cost ledger's timestamped
   `new_rate_snapshot()` (with its buffer and its refusal to invent a missing rate) or something else. An
   `actual_thb` recorded on a split row already wins permanently and is never re-converted.
3. **Double counting is now concrete.** A cost row marked `paid` with a locked `actual_thb` and a split row for
   the same purchase are the same money twice. Both ledgers reach `build_export_snapshot()`, so whatever rule
   is chosen has to hold in the app, the PDF, and the six-sheet workbook identically.

Also note: settlement payments are deliberately not recorded, so "who still owes what" is always a trip-to-date
computation and can never be reconciled against actual transfers.

Decide at least: whether a split transaction may claim a cost row and, if so, what that does to the row's
payment state; which number is headline in the UI and in exports; how a partially settled trip is reported;
whether an unreconciled difference is a visible gap, a warning, or an error; and whether the split ledger
inherits the cost ledger's rate snapshot or keeps its own.

## Resolution comments

### 2026-07-31 — Decided through the reconciliation interview

The arithmetic, the model additions and what is left open are in
[`023-cost-and-split-reconciliation.md`](../artifacts/023-cost-and-split-reconciliation.md).

- **A split row may claim a cost row, and the claimed row defers its actual.** The split row gains one
  optional `cost_id`, alongside the `plan_day` and `place_id` links WF-018 already gave it. **Nothing is
  added to the cost row and `payment_state` is untouched** — "claimed" is derived from whether any non-voided
  split row references it, so there is no second state to keep in sync. The arithmetic:
  `planned` = every cost row; `actual` = non-voided split rows **plus unclaimed paid cost rows**. Double
  counting is then structurally impossible, because a paid cost row either defers to a split row or supplies
  its own actual, never both. This also keeps `paid` useful for the case it is good at — an expense the owner
  paid that nobody splits, which would otherwise need a one-participant split row. Several split rows may
  claim one cost row and their THB sums; a claimed row's own `actual_thb` becomes inert and the UI must say
  why; unclaiming is just clearing `cost_id`.
- **`costs.totals()` gains two keys and redefines none.** Reading it closely turned up a mismatch:
  `estimated_thb` sums **non-paid rows only** (`unpaid = [not in LOCKED_STATES]`), so a row estimated at 1,200
  and later marked paid drops out of it entirely. That is right for "what is still to pay" but it is not the
  plan figure, and plan-versus-actual per category needs every row's estimate. So `planned_thb` and
  `actual_thb` are added, with a parallel per-category breakdown, while `estimated_thb`, `paid_thb`,
  `total_thb` and `by_category` keep their current meanings — a redefinition would land identically in the
  app, the PDF and the workbook, wrong in three places at once.
- **The comparison is read on the cost screen, per category** — planned, actual, difference — because the
  owner described the cost plan *as* the overview breakdown. `/split` stays transactions plus Auto-Bill's
  aggregates. The cost screen therefore reads from both ledgers, which is the price of putting the comparison
  somewhere useful.
- **The seven categories are the default tag vocabulary.** The two vocabularies are almost identical — two
  differ only by plural and `fees` is the only category with no counterpart — so **most trips need no mapping
  at all** and lifted Auto-Bill rows land correctly. Owner additions are assigned to one of the seven,
  defaulting to `other`. The map lives at one boundary, for the reason WF-018 gave: the accommodation
  vocabulary that silently killed hotel-area recommendations.
- **Cost per person uses two mechanisms deliberately:** estimated is `planned_thb / headcount`
  (owner + members); actual comes from `split.py`'s resolved shares, inheriting WF-018's single rounding
  implementation. **The trap named and avoided:** `setup.py:93`–`97` already computes per-traveller weights
  where the owner gets 0.5 and members share 0.5 — but the field is `group_preference_weights`, it feeds only
  `ranking.py`, and it is a *taste* weight. Using it for money would charge the owner half the trip
  regardless of headcount.
- **Split rows inherit the cost ledger's timestamped snapshot**, including its refusal to invent a missing
  rate, with **one documented exception: `buffer_percent` is skipped for split rows**, since the buffer pads
  estimates and applying it to money already spent would inflate history.
- **An unreconciled difference is a visible, non-blocking gap**, following the readiness board
  (`blocks_itinerary` always False) and `totals()`' existing behaviour. Blocking export was rejected outright:
  `WF-022` made the exports a pilot-ready gate and they are what the owner carries in Taipei.
- **A per-traveller settled marker**, which closes the map's own fog item without reversing WF-018 — it
  records that the owner considers a balance done, not an amount or a transfer. **Staleness rule decided
  rather than left open: any change to a marked traveller's balance clears their marker**, because a marker
  that survives new debt is a lie. Balance wording stays a *suggestion* regardless, as WF-031 requires.
