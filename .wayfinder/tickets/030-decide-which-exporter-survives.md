---
id: WF-030
title: Decide which exporter survives, Python or JavaScript
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
blocked_by:
  - WF-019
---

# Decide which exporter survives, Python or JavaScript

## Question

Both projects export Excel. After the merge, does file generation happen server-side in Python or in the
browser in JavaScript — and how does a generated file reach the owner's disk?

## Context

- Python side: `travel_planner/exports.py` (496 lines) builds the one shared export snapshot, and
  `travel_planner/exporters.py` (1094 lines) turns it into a 9:16 poster PNG, the trip PDF, and a six-sheet
  Excel workbook. All three are snapshot-in, bytes-out. `CLAUDE.md` requires every new output to read
  `build_export_snapshot()` rather than a raw variant — that rule is what stops times, totals, and statuses
  diverging between outputs, and it is the strongest argument for keeping generation in one place.
- PDF and poster rendering needs a Unicode TTF covering Latin, Thai, and the local script (CJK for the Taipei
  pilot). `exporters.resolve_font()` checks `TOURIST_EXPORT_FONT` first, then a short candidate list, and
  raises rather than rendering tofu. The browser has no equivalent problem for HTML but has no PDF or PNG
  pipeline either.
- JavaScript side: Auto-Bill uses `exceljs` plus `file-saver` (`src/excelExporter.js`, 708 lines) for its
  Excel workbook and JSON backup, and its import path reads those files back. Keeping the split ledger's
  export in JS while everything else is Python would mean two workbook generators in one repo.
- The exports are the offline artifact for the trip itself. Phase 1 decided PDF and Excel snapshots are
  versioned and offline-readable precisely because the app may not be reachable abroad; a browser-side
  exporter inherits that requirement.
- Downloading from a local API is a different mechanism than a client-side blob save: file naming, save
  location, and what happens on a phone all change.

Decide at least: one exporter or two; whether `excelExporter.js` is ported into Python, kept, or deleted with
its output folded into the six-sheet workbook; how the browser triggers and receives a server-generated file;
whether the JSON backup format survives as the import channel for migration; and whether the split ledger
becomes a seventh sheet or its own workbook.

## Resolution comments

### 2026-07-31 — Decided through the exporter interview

The full contract, the download rule and what is left open are in
[`030-exporter-and-download-contract.md`](../artifacts/030-exporter-and-download-contract.md).

- **Python survives; `excelExporter.js` is deleted and its five sheets are reference, not reuse.** The
  decisive argument is `CLAUDE.md`'s rule that every output reads `build_export_snapshot()` — one generator is
  the only arrangement in which that rule can hold. Then the asymmetry: **25 tests against 0**, and not
  shallow ones (`test_summary_formulas_point_at_the_real_timeline_columns`,
  `test_every_formula_ships_with_a_cached_value`, `test_totals_that_disagree_with_the_optimizer_are_refused`).
  And **only Python has PDF, poster PNG and ICS** — JavaScript has none of them in this stack. `exceljs` and
  `file-saver` never join `web/`.
- **Downloads use dedicated `GET` routes with `Content-Disposition`**, because browser-native download
  handling gets the filename, the save location and — decisively — **phone behaviour** right, and these files
  are the Taipei artifact. This is a deliberate exception to `WF-019`'s single RPC convention, and it
  **weakens one guard**: a `GET` has no body, so the `application/json` content-type control cannot apply and
  these routes rest on the **`Host` allowlist alone**. Accepted because a download is a read a cross-origin
  caller cannot see, with a written rule: **bare `GET` reaches export downloads and nothing else** — never a
  mutation, never a paid call.
- **Auto-Bill's backup JSON is the migration channel.** The donor keeps everything in `localStorage` and the
  backup is a dump of exactly that, so **a file survives archiving where `localStorage` does not**. One dated
  pre-archive action now covers two tickets: export a backup per trip, and take `WF-025`'s 41 element
  captures. Both need the donor runnable.
- **The split ledger gets its own workbook**, for a purpose the exports never had: **a money file can be
  handed to a traveller without handing over the whole itinerary.** Both workbooks read
  `build_export_snapshot()`, so the one-snapshot rule holds across two files. Because the money file is meant
  to leave the owner's hands it carries no itinerary, no addresses and no readiness evidence, on top of the
  floor `FORBIDDEN_SNAPSHOT_KEYS` already sets.
- **That collided with `WF-023` and the resolution is recorded rather than left implicit.** Planned-versus-
  actual per category cannot be a cross-workbook formula, so **the plan workbook's Costs sheet carries
  `planned`, `actual` and the difference as plain values computed by the snapshot.** This departs from the
  formula-plus-cached-value pattern that `test_every_formula_ships_with_a_cached_value` protects, with the
  consequence stated: edit a split row in the money workbook and the plan workbook's comparison does not
  update. Acceptable because an export is a snapshot of a plan version rather than a live document — but the
  sheet must say so, so nobody trusts a stale figure. The money workbook keeps live formulas internally.
