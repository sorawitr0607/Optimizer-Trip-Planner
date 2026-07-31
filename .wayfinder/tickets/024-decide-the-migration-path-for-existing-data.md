---
id: WF-024
title: Decide the migration path for existing trips and splitter data
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
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
