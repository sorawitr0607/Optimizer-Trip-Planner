---
id: WF-023
title: Decide cost-and-split reconciliation rules
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
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
