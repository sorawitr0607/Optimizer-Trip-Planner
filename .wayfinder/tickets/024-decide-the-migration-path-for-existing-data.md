---
id: WF-024
title: Decide the migration path for existing trips and splitter data
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
blocked_by:
  - WF-018
---

# Decide the migration path for existing trips and splitter data

## Question

How do the existing SQLite trips and the existing Auto-Bill browser data reach the merged schema, and what
happens to an owner who upgrades mid-trip?

## Context

- `travel_planner/store.py` stamps `SCHEMA_VERSION` into `PRAGMA user_version`, and a newer database
  refuses to open with an older build. Adding a split ledger table bumps that version, which makes the
  upgrade one-way unless this ticket says otherwise — and one-way conflicts with the Streamlit fallback
  decided in the freeze ticket.
- `plan_versions` and `discovery_runs` carry SQLite triggers that abort UPDATE and DELETE, and
  `data/tourist.sqlite3` is a real file with real trip history. Restoring an old plan creates a new version
  rather than mutating one, so there is no in-place edit path to reuse for a migration.
- Auto-Bill's data lives in browser `localStorage` under `alipay_splitter_settings`,
  `alipay_splitter_transactions`, and `alipay_splitter_theme` (`src/App.jsx:9-43`) — reachable only from
  the browser that holds it, and lost if that profile is cleared. It already ships an Excel and JSON
  backup export plus an import path, which is the obvious migration channel.
- Auto-Bill's people are free-text names; the planner's travellers are owner and member profiles from
  setup. A name-to-traveller mapping step is likely unavoidable, and duplicates or typos in historic data
  are real.
- Auto-Bill stores one flat `fxRate` per trip with a default per country (`utils.js:1`). Historic
  transactions converted at that rate have no as-of date, which the planner's rate snapshot requires.

The split ledger model is now decided and it makes two import problems mandatory rather than optional:

- **Name to traveller id mapping is required at import.** A participant is an existing traveller id, never free
  text, so every historic Auto-Bill name must resolve to a traveller in setup or the row cannot be created.
  Typos and duplicates in the historic data become a mapping step the owner drives, not data the import can
  guess.
- **`paid_by` has no source in the historic data.** Auto-Bill never recorded who paid — it assumed the main
  cardholder — so every imported row needs a payer, and the honest default is the trip's cardholder with that
  assumption recorded rather than presented as fact.
- Owner-defined tags survive import directly, since split rows use the same free tag vocabulary Auto-Bill did.
- Rows are editable and voidable with no triggers, so an import needs no append-only machinery — but it also
  gets no audit trail for free, which is an argument for a dry-run preview before writing.

Decide at least: whether historic splitter data is imported at all or simply left in the archived app;
the import format and who runs it; how missing rate provenance is represented for imported rows without
inventing evidence; whether the schema bump is gated behind a backup step; and whether an owner can
downgrade to the frozen Streamlit app after upgrading.

## Resolution comments

### 2026-08-03 — Decided through the migration interview

The read-only census, the rules and what is left open are in
[`024-migration-path.md`](../artifacts/024-migration-path.md).

**The measured scale reframes the ticket: there is one trip, and it is the pilot.** A read-only census of
`data/tourist.sqlite3` (nothing was written) shows `user_version` 12, **1 trip** — `Taipei, Taiwan`,
`explore_first`, created 2026-07-30 — with 1 setup, 1 active plan, 3 plan versions, 5 candidate choices, 4
discovery runs, 12 route snapshots and 50 paid-usage rows. So this is not migrating historic archives; it is
migrating the pilot trip, five months before the pilot. Two other facts: `data/` already holds
`tourist-backup-2026-07-29.sqlite3` and `tourist-preflow-2026-07-30.sqlite3`, so **the backup habit already
exists**; and **no Auto-Bill backup JSON exists anywhere**, so `WF-030`'s pre-archive export is still unmet.

- **No importer is built. Archive only.** Auto-Bill's `localStorage` holds one trip's data at a time, and the
  planner's only trip is a brand-new Taipei. Importing another trip's expenses into it would be wrong, and
  creating a trip to receive them yields a trip with money and no itinerary. The owner exports a backup JSON
  before the donor is archived and that file is kept as a record; Taipei's split ledger starts empty and is
  filled during the trip. **This deletes three problems the ticket called mandatory** rather than solving
  them: name→traveller-id mapping, a `paid_by` the source never recorded, and rate provenance at import.
- **A row arriving with known THB and no rate keeps it as a locked `actual_thb`** — a standing rule covering
  both a future importer and the owner entering historic spend by hand. This invents nothing: `WF-018`
  already established that a recorded `actual_thb` wins permanently and is never re-converted, precisely
  because such a row exists *because money already moved*. The rejected alternative would have put a
  fabricated date in `as_of`, and re-converting historic spend at a made-up date can silently change what a
  past trip cost.
- **Every schema bump copies the database first**, to `data/tourist-pre-v<n>-<date>.sqlite3`, and **refuses
  to proceed if the copy fails.** Two bumps are pending — the split ledger table and `WF-019`'s in-flight
  marker — and this bump differs in kind from the twelve before it: every earlier one happened while a
  downgrade was possible in principle, and `WF-022` removed that, so **a pre-bump copy is the only way back**.
  It also makes an occasional hand habit automatic.
- **The downgrade question is void.** There is no frozen Streamlit app to downgrade to — `WF-022` made it a
  POC awaiting deletion, with no tag and no restorable checkout. The way back is a file copy, not an older
  build.
- **Nobody upgrades mid-trip.** Answering the Question's second half: **the database does not change during
  29 December 2026 – 4 January 2027.** A one-way bump with no downgrade path, applied to the only trip in the
  file, while that trip is happening abroad, is not worth any feature. This is a rule rather than a
  mechanism, written down so the November and December conversations already have it decided.

Also narrows `WF-030`: the backup JSON is an **archive record**, not an import source. Nothing there is
reversed, and a dated note is on that ticket.
