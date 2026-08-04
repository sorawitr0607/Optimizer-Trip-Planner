# The real trip through all nine routes, at schema 13

A read-only witness taken straight after the 12 → 13 bump. It answers one
question — **does the webapp handle the real Taipei trip?** — and deliberately
does not answer pilot-ready gate 1, which needs the trip's data completed first.

Nothing here mutated the trip. Every write and every paid call was excluded by
name: no `refresh_*`, no `save_*`, no `discover_places`, no `enrich_place_card`,
no `activate_plan_preview`.

## 26 reads, 26 answered

All nine screens' reads, exercised over the real socket against
`data/tourist.sqlite3` at version 13. Everything returned 200.

The list came from `web/src/**/*.tsx`, not from memory. That matters: the first
attempt was written from memory and produced seven failures — five method names
that are not in the allowlist at all (`get_trip`, `list_place_evidence`,
`get_trip_evidence`, `paid_usage_summary`, `revision_vocabulary`) and two global
vocabularies I wrongly sent a `trip_id` to. Every one of those was a defect in
the probe. Extracting the calls from the screens that make them removed the
guesswork, and `check_paid_call` then needed one more correction — it takes
`operation` and no `trip_id`, which the extraction had already said.

Worth recording because seven red lines looked exactly like seven app defects.

## What the real trip actually looks like

`itinerary` renders the real plan: dates from 2026-12-29, **day 1 of 7**, active
plan version `bcdd81353160`, **Provisional / needs acceptance · THB**, and an
"Evidence still missing" panel matching the two capability gaps. Day 1 shows
**0 visits, 0 walking, 0 travel** and says so in words: *"No visit is scheduled
on this day; choose another day or a denser variant."*

That is correct, not broken. `CLAUDE.md` already recorded that the stored plan is
sparse — 7 days, 8 rows, three row types — and the screen reports its emptiness
honestly instead of inventing content or erroring.

`split` is the more interesting one, because it diagnoses the setup gap by
itself:

> Only you are recorded on this trip, so a bill has nobody to share with yet.
> Add travellers in setup.

The v13 tables are live and reachable, the ledger is empty as designed, and the
settlement panel carries its honesty note — *"These are suggestions, not debts.
Payments between people are never recorded, so these figures stay the same after
someone pays you back"* — which is the visible consequence of the S2 decision
that a settled marker stores a balance rather than a payment.

The accent renders **teal rather than the house red**, because `data-country`
resolves Taiwan through D6. Worth noting: every screen baseline in the parity set
was captured on a different trip, so this is the first look at a non-default
accent on real content.

## Why these captures are not in `screen-current`

The 36-image baseline gate compares a *specific* trip against approved images of
that same trip. Writing nine real-trip screens into `screen-current` would make
the gate diff two unrelated trips and fail on every one. So these live here, in
the evidence bundle, and the baseline set is untouched.

Light/en only. This is a witness that the real trip renders, not a second
baseline set.

## The paid cap reads US$0.00 and that is right

`check_paid_call` reports `spent_usd: 0.0` with the full US$10 remaining, while
the ledger holds **US$0.7690 across 50 calls**. Not a contradiction: the cap is
monthly, every one of those 50 calls was made in **2026-07**, and this is August.
Checked rather than assumed, because a ledger read returning zero is exactly what
a broken ledger read would also look like.

## Gate 1 is not passed

The webapp handles the real trip. The real trip is not ready to be planned:

- `planning_mode` and `confirmed` are both `None`, and **zero travellers** are
  recorded — the split screen says so out loud
- `ACCOMMODATION_BASE_UNCONFIRMED` and `OPENING_EVIDENCE_MISSING` remain, which
  is why the plan is provisional
- `checklist_items`, `cost_items`, `rate_snapshots` and `split_rows` are all empty

Clearing the opening-evidence gap costs **one `google_places:details` call per
selected place at US$0.017** — about US$0.05 for the current five choices — and is
worth doing only after the choices are final, since changing them means paying
again.
