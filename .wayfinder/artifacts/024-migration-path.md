# Migration path for existing trips and splitter data

Resolves `Decide the migration path for existing trips and splitter data` (WF-024).

Decided 2026-08-03 through the migration interview. The database census below was taken **read-only**
(`file:…?mode=ro`); nothing in `data/` was written. Paths are repo-relative.

## The measured scale: one trip, and it is the pilot

| Table | Rows |
|---|---|
| `trips` | **1** |
| `trip_setups` | 1 |
| `active_plans` | 1 |
| `plan_versions` | 3 |
| `candidate_choices` | 5 |
| `discovery_runs` | 4 |
| `route_snapshots` | 12 |
| `paid_usage` | 50 |
| `provider_cache` · `place_evidence` · `trip_evidence` · `optimization_previews` | 1 · 2 · 1 · 1 |

`PRAGMA user_version` = **12**. The file is 3.3 MB.

**That one trip is `Taipei, Taiwan`**, `explore_first`, language `en`, created 2026-07-30. So this ticket is
not about migrating historic archives — it is about migrating **the pilot trip itself**, five months before
the pilot.

Two other facts from the same directory:

- `data/tourist-backup-2026-07-29.sqlite3` and `data/tourist-preflow-2026-07-30.sqlite3` already exist.
  **The owner already has a backup habit**, hand-made before risky work, with descriptive names.
- **No Auto-Bill backup JSON exists anywhere on disk**, so `WF-030`'s pre-archive export is still unmet.

## The decisions

| # | Question | Decided |
|---|---|---|
| 1 | Import historic splitter data? | **No. Archive only** — the split ledger starts fresh |
| 2 | Rate provenance for rows with no as-of date | **Locked `actual_thb`**, never a fabricated snapshot |
| 3 | Is the schema bump gated? | **Yes — an automatic timestamped copy before any bump** |
| 4 | Downgrade to the frozen Streamlit app? | **Void question** — see below |
| 5 | Upgrading mid-trip | **A database change freeze across the pilot window** |

## 1. Archive only — three problems deleted rather than solved

Auto-Bill's `localStorage` holds **one trip's data at a time** (`alipay_splitter_settings`,
`alipay_splitter_transactions`, `alipay_splitter_theme`). The planner's only trip is Taipei, created
2026-07-30. Importing a different trip's expenses into Taipei would be wrong, and creating a trip to receive
them produces a trip with money and no itinerary.

So: **the owner exports a backup JSON from Auto-Bill before it is archived, and that file is kept as an
archive record. No importer is built.** Taipei's split ledger starts empty and is filled during the trip,
which is what the ledger is for.

This deletes three problems the ticket called mandatory rather than solving them:

- **Name → traveller id mapping.** No historic names to resolve, so no mapping step and no typo/duplicate
  reconciliation UI.
- **`paid_by` with no source.** Auto-Bill never recorded who paid; with no import there is no row needing a
  payer the source never had.
- **Rate provenance with no as-of date.** Covered by §2 as a standing rule rather than an import concern.

**`WF-030` is narrowed by this, and its ticket now records it.** That ticket called the backup JSON "the
migration channel", which overstates what gets built: the channel exists and the file is still exported
before archiving, but it carries an **archive** rather than an import. Nothing in `WF-030` is reversed —
`exceljs` and `file-saver` still never join `web/`, and the pre-archive export is still a dated obligation.

Accepted: if that browser profile holds expenses the owner wants inside the app, they stay outside it, and
the JSON is readable only by hand afterwards.

## 2. A row that arrives with known THB and no rate keeps it, locked

Auto-Bill stores one flat `fxRate` per trip with no as-of date; the planner's `new_rate_snapshot()` requires
`as_of` **and** `source`. The rule, which applies to any row arriving with a known THB value and no rate
provenance — a future importer, or the owner entering a historic expense by hand:

```
row.actual_thb = the THB already known    →  never re-converted, so no as_of and no source are needed
```

**This invents nothing.** `WF-018` already established that an `actual_thb` the owner records wins
permanently and is never re-converted, precisely because such a row exists *because money already moved*.
Imported or hand-entered history is exactly that case.

The rejected alternative is worth naming: a snapshot with `source: "imported"` and `as_of` set to the import
date would put a **fabricated date in a field that means something else**, and re-converting historic spend
at a made-up date can silently change what a past trip cost. This app's stance is that invented evidence is
a defect.

Accepted: the original currency amount stops being convertible, so a locked row cannot be re-expressed if
the rate is later disputed. `costs.py` already behaves this way for `paid` rows, so it is an existing
pattern rather than a new one.

## 3. Every schema bump copies the database first

```
data/tourist-pre-v13-2026-08-03.sqlite3      ← automatic, before anything is written
    then bump user_version and add the table
```

If the copy fails, **the migration refuses to proceed.**

Two pending bumps need this: the **split ledger table** and the **discovery in-flight marker** from
`WF-019`. And this bump differs in kind from the twelve before it — every earlier one happened while a
downgrade was at least possible in principle, and `WF-022` removed that. `store.py:332` refuses a newer
database on older code, there is no downgrade tool by decision, so **a pre-bump copy is the only way back**.

It also formalises an instinct already visible in `data/`: the owner makes these copies by hand before risky
work. Making it automatic converts an occasional habit into a guarantee, and `data/*.sqlite3*` is already
gitignored so copies never reach the repository.

Accepted: copies accumulate with nothing pruning them; a copy is not a tested restore; and refusing to
migrate on a failed disk write is a new failure mode.

## 4. The downgrade question is void

The ticket asks "whether an owner can downgrade to the frozen Streamlit app after upgrading." **There is no
frozen Streamlit app.** `WF-022` made Streamlit a POC awaiting deletion at parity, with no tag, no
downgrade path and no restorable old checkout. The question had a subject when it was charted and does not
now.

What replaces it is §3: the way back is a file copy, not an older build.

## 5. Nobody upgrades mid-trip

The ticket's Question also asks what happens to an owner who upgrades mid-trip. The answer follows from the
facts rather than needing a mechanism:

> **The database does not change during the pilot window, 29 December 2026 – 4 January 2027.**

A one-way schema bump with no downgrade path, applied to the only trip in the file, while that trip is
happening, in a foreign country, is not a risk worth taking for any feature. The 1 November checkpoint is
where the vehicle is chosen; after that the schema is frozen until the trip ends.

This is a **rule, not a mechanism** — nothing enforces it in code, and it does not need to. It is written
here so the November conversation and the December weeks both have it already decided.

## What this creates

| Item | Scale |
|---|---|
| Importer | **none** — deliberately not built |
| Pre-archive action | 1 backup JSON exported from Auto-Bill by the owner |
| Migration code | a timestamped copy + refuse-on-failure, in the schema-bump path |
| Standing rule | known THB with no rate provenance → locked `actual_thb` |
| Standing rule | no schema change 29 Dec 2026 – 4 Jan 2027 |

## Explicitly not decided here

- Whether old `tourist-pre-v*` copies are ever pruned, and by what.
- Whether the copy is verified after writing (opened and counted) or merely written.
- What the archive JSON is *for*, beyond being kept — nothing reads it.
- Whether the two existing hand-made backups are retained or removed.

## What this hands downstream

| Ticket | Consequence |
|---|---|
| `Lock the Phase 2 slice plan and validation scorecard` | **This was its last decision blocker.** The scorecard inherits two dated constraints: the pre-archive backup export, and the no-schema-change freeze across the pilot window |
| `Decide which exporter survives, Python or JavaScript` | Narrowed: the backup JSON is an archive record, not an import source. A dated note is on its ticket |
| `Prototype the merged cost and split screen` | The split ledger it prototypes starts **empty** — there is no imported history to design around, so no import states, no mapping UI, no provenance badges |
| `Decide the offline asset policy for the webapp` | Unaffected, but shares the same pre-archive window: the donor must stay runnable for the backup export and the 41 element captures |
