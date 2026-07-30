---
id: WF-030
title: Decide which exporter survives, Python or JavaScript
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
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
