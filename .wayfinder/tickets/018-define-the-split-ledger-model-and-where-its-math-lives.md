---
id: WF-018
title: Define the split ledger model and where its math lives
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
blocked_by: []
---

# Define the split ledger model and where its math lives

## Question

What exactly is a split transaction in this repository — its fields, its identity, its mutability, what it
may reference — and does its balance and settlement math live in the pure Python core or in the React
frontend?

## Context

Facts already in the environment, so no session needs to rediscover them.

- Auto-Bill's record carries: amount in trip currency, one flat `fxRate` to THB, payer, participants,
  split mode (equally-all / selected-travellers / single-payer), day label, category tag, note. Split
  arithmetic is `equalSplit()` in `src/utils.js:212` — largest-remainder correction dumped on the first
  person. Settlement runs against a selectable "main cardholder" inside `src/components/Dashboard.jsx`.
- The planner's cost row (`travel_planner/costs.py`) carries label, category from a fixed tuple,
  `original_amount` + `original_currency`, `payment_state` of estimate/committed/paid, `actual_thb`
  locked once paid, and resolves THB through a timestamped `new_rate_snapshot()` with an optional buffer.
  It has no concept of a person.
- The planner already knows the travellers: setup produces owner and member profiles
  (`travel_planner/setup.py`), so a split participant should be an existing traveller, not free text.
- Every record crossing a boundary is a `core.freeze_snapshot()` with a re-verified SHA-256
  (`travel_planner/core.py`), and `FORBIDDEN_SNAPSHOT_KEYS` rejects secret-bearing keys anywhere in the
  tree. A new record type inherits that discipline or explicitly argues out of it.
- Money precision differs today: Auto-Bill rounds to 2 decimals in JS floats; the planner rounds to 2 in
  Python floats. THB and JPY have no minor unit in practice, TWD does. Whether the merged ledger keeps
  floats at all is part of this decision.

Decide at least: whether a split transaction references a place, a plan day, or nothing; whether it may
exist for a trip with no confirmed setup; whether it is mutable or append-only-with-corrections; whether
it carries its own rate or shares the cost ledger's rate snapshot; whether unequal or weighted shares are
supported now or later; and whether settlement produces a minimal-transfer set or a
pay-the-cardholder-back list.

## Resolution comments

### 2026-07-31 — Decided through the split-ledger interview

**The record.** A split row carries: trip id (required), `paid_by` (one traveller id), participants (traveller
ids), split mode, `original_amount` + `original_currency`, optional `actual_thb`, label, owner-defined tag,
optional plan-day link, optional `place_id`, `voided` flag. Nothing else. Explicitly **not** on the row:
payment states, a per-row exchange rate, free-text participant names, and any settlement record.

- **Every row records who paid, defaulting to the trip's main cardholder.** `paid_by` is one traveller id,
  pre-filled so the common single-card case stays one tap. Auto-Bill has no such field — `Dashboard.jsx:1487`
  states outright that it assumes every expense was charged to the main cardholder — so this is the one place
  the merged model is strictly more general than either source.
- **The row stores the split mode and the participant list; share amounts are recomputed on read.** Not the
  resolved map. The consequence is accepted and load-bearing: there must be exactly one implementation of the
  rounding rule, including which participant absorbs the remainder, and any future unequal or weighted split
  needs a mode that carries amounts, because the current shape cannot express one.
- **All split math lives in a new pure `travel_planner/split.py`, beside `costs.py`** — no Streamlit, SQLite,
  HTTP or model imports, `unittest`-covered like the rest of the core. Share resolution, the rounding
  remainder, balances and settlement all resolve server-side; the API returns finished numbers and React
  renders what it is given. This is what stops the screen, the Excel workbook and the PDF ever disagreeing by
  a satang, and it is why `equalSplit()` in `utils.js:212` is ported rather than reused.
- **Settlement is a star through the cardholder, with fronted cash netted off.** Every suggested payment is
  between one traveller and the cardholder, so there is one memo per person exactly as Auto-Bill produces.
  Cash a non-cardholder fronted is credited against what they owe: `net = their shares − what they paid out`.
  That is arithmetically exact — nobody is over- or under-charged — and the cardholder may end up owing a
  traveller rather than the reverse, which the UI has to be able to say. No minimal-transfer solver, no debt
  graph, no cross-traveller payments.
- **Rows are editable, and removing one voids rather than deletes it.** Corrections happen constantly during a
  trip, so this follows the readiness board's precedent (mutable, dismiss-not-delete) rather than
  `plan_versions`' append-only triggers: data entry is not a decision the optimizer produced. No version
  history, no SQLite triggers, no correction rows. Voided rows stay visible so a total remains explainable.
  **This closes the map's open question about whether the split ledger needed append-only discipline. It does
  not.**
- **Trip is required; the plan day and `place_id` are optional links.** Set them and the app can report what a
  given temple actually cost; leave them empty and a pre-trip flight or an airport taxi still records cleanly.
  Optional means no expense is ever unrecordable because the itinerary moved under it.
- **Categories are owner-defined tags, as in Auto-Bill — not `costs.CATEGORIES`.** Chosen over one shared
  vocabulary with the consequence stated: the two ledgers can no longer be summed on a single category axis
  without a mapping. This repo has already paid for vocabulary drift once — setup and the optimizer held
  different accommodation vocabularies and hotel-area recommendations silently never fired for any app-created
  trip until `_optimizer_input` translated at the boundary. So the mapping is now a required output of
  `Decide cost-and-split reconciliation rules`, and whatever it produces belongs at a boundary, not scattered
  through readers.
- **A participant is an existing traveller id, chosen and never typed.** Setup already holds up to 8 members
  with ids, labels, ages and tags, and detail is optional, so adding someone is cheap. Settlement therefore
  cannot fracture on `Mum` versus `mum`, and the migration ticket's name-to-traveller mapping becomes a
  one-time import concern instead of a permanent data-quality problem. No ad-hoc guests.
- **Money stays 2-decimal floats, matching `costs.py`.** The two ledgers then add up with no conversion layer
  and nothing existing is rewritten. `split.py` carries one documented rounding rule and a `ponytail:` comment
  naming the ceiling — move to integer minor units if a real reconciliation error ever appears. Note the
  no-minor-unit currencies the pilot will actually meet: TWD, JPY, KRW.
- **THB is derived, except when the owner knows the real charge.** The row stores what was spent and in what
  currency; conversion happens at read time through whichever snapshot the reconciliation ticket picks. An
  `actual_thb` the owner records wins permanently and is never re-converted — the same reasoning as
  `costs.py`'s paid-lock, imported without its payment states, because a row in this ledger exists precisely
  because money already moved.
- **Settling up is not recorded. Balances are trip-to-date totals.** No payment rows, no settled flag. The
  accepted consequence: after a traveller actually transfers the money, the app keeps showing the balance,
  because nothing in the ledger knows they paid. That is a live gap for the money screen to present honestly —
  a suggestion, not an outstanding-debt claim — and it is written into `Prototype the merged cost and split
  screen`.
