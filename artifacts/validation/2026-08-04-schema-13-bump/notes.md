# Bumping the real database to schema 13

`data/tourist.sqlite3` held the only real trip — the Taipei pilot — at schema 12
while the code had been at 13 since S2. It is now at 13, with
`data/tourist-pre-v13-2026-08-04.sqlite3` beside it as the only way back.

Authorised by the owner this session. It had been deliberately deferred since S2
as a one-way change to real content that should be a deliberate act, not a side
effect of opening a file.

## Why it had to happen now rather than nearer the trip

`WF-024` forbids any schema change **between 29 December 2026 and 4 January
2027**. The real trip's dates are **2026-12-29 → 2027-01-04**.

The freeze window *is* the trip. So the bump was never a "whenever" item: it had
to land before the window opened, or wait until the trip was over. Doing it on
2026-08-04 leaves five months to discover any problem; doing it in late December
would have meant doing it under the freeze or not at all.

That reading is not in `WF-024` explicitly — the ticket states the window and the
trip dates separately — so it is recorded here.

## Proven on a copy first

`CLAUDE.md` says never to open `data/tourist.sqlite3` to demonstrate something,
so the rehearsal ran on a byte-identical copy in the session scratchpad. Opening
that copy *is* the migration, which made it a real dry run rather than a
simulation of one.

The bump is **purely additive**:

| | Before | After |
|---|---|---|
| Tables | 19 | 21 |
| Added | — | `split_rows`, `split_settled_markers` |
| Removed | — | none |
| Rows moved in any pre-existing table | — | **0** |

Then every record type was read back through `PlannerActions`. That matters more
than the row counts: every `store.py` read **re-verifies its snapshot's SHA-256**
and raises rather than returning a corrupted payload. Setup, all three plan
versions, the active plan, the pending preview, all four discovery runs, the
export snapshot, and both new split reads all came back clean.

## The real bump

- `data/tourist.sqlite3`: `user_version` 12 → **13**
- `data/tourist-pre-v13-2026-08-04.sqlite3`: `user_version` **12**, and its
  SHA-256 is **byte-identical** to the pre-bump live file
  (`faab16d01d708758a75826f71c8bcbdd…`) — verified, not assumed
- Both are gitignored, and the backup is covered by `*.sqlite3` rather than only
  the `data/tourist.sqlite3` pattern, which was checked with `git check-ignore`

Post-bump the trip reads back with 832 candidates, 4 discovery runs, 5 candidate
choices, 3 plan versions, an active plan, and `journey["next"] == "itinerary"`.
The two new split tables are reachable and empty.

`store._copy_before_bump()` refuses to migrate if the copy fails, so the backup
existing is a precondition of the bump having happened at all — but it was
verified independently anyway, because "the guard would have stopped it" is not
the same as "the file is correct".

## What this does not finish

The bump unblocks pilot-ready gate 1; it does not advance it. Three things stand
between here and "the real Taipei trip planned end to end in the webapp":

- **The setup is thin.** `planning_mode` and `confirmed` are both `None`, and
  **zero travellers are recorded**. `journey()` still reports all five gates done,
  so nothing is blocked — but headcount comes from the roster, so with no
  travellers every per-person figure equals the total, and the money half of the
  pilot means nothing until the real people are in. This needs owner data and
  cannot be inferred.
- **Two capability gaps remain**: `ACCOMMODATION_BASE_UNCONFIRMED` and
  `OPENING_EVIDENCE_MISSING`. They are why the active plan is provisional.
- **Nothing is recorded for readiness, costs, rates or split.** Those four tables
  are empty, and they are the other half of the journey.

Paid spend stands at **US$0.7690 of the US$10 cap** across 50 calls, so clearing
the opening-evidence gap has room if it needs provider calls.
