# Auto-Bill donor capture — 2026-08-04

Taken while `Auto-Bill-Splitter` was still runnable, which is the point: `WF-025` makes the donor capture a
**dated prerequisite**, and `WF-030`/`WF-024` add the backup JSON to the same window. S6 archives the donor,
so nothing here can be re-derived afterwards.

Captured by running the donor locally (`npm install`, `npm run dev`) and reading the live DOM in Chrome at a
1440-wide viewport, across all four dashboard tabs, all four wizard steps and both themes.

## What the numbers are

| Measure | Value |
|---|---|
| Style records (class combination × theme) | **431** |
| Distinct class tokens | **265**, of which **171** captured in both themes |
| Inline-style sites recorded | **97** |
| Elements fully covered | **35 of 41** |
| Elements partially covered | 4 |
| Elements with no class selector to match | 2 |

`coverage.json` holds the per-element breakdown, keyed by the catalogue numbers in
`.wayfinder/artifacts/021-element-inventory-matrix.md` §1. `element-selectors.json` is the selector list
parsed out of that artifact, so the mapping is reproducible rather than hand-written.

## Why computed styles and not 41 isolated images

`WF-025` §2a asks for each element rendered **in isolation in a component gallery, in both projects**, then
image-diffed. That gallery is part of S6's harness and does not exist yet in either project. What could not
wait is the **donor side of the comparison**, so this captures it in the form that survives best:

- **`computed-styles.json`** — resolved values for 22 parity-relevant properties per class combination per
  theme. This is strictly more useful than a screenshot for diffing, because it is exact and machine
  comparable.
- **`inline-styles.json`** — the 97 inline `style` attributes. **This is the part `index.css` cannot give
  back.** Artifact 021 warned that ~18 class names carry *zero* CSS rules — the settlement grid, the
  main-cardholder selector, the participant border — so a token extraction reading only the stylesheet
  silently misses them. These are captured from the live DOM, so inline styling is included.
- **`resolved-tokens.json`** — the custom-property values each theme actually resolves to.
- **`captures/`** — four reference screenshots for the states that most need a human eye.

When S6 builds the gallery, diff the rebuild's computed styles against `computed-styles.json` rather than
trying to recreate the donor.

## A finding worth carrying into S6

**The donor's accent does not change between themes.** `--color-accent` resolves to `#dc2626` in *both*
light and dark, along with `--color-accent-hover: #b91c1c` and the same `--color-accent-light`. The
planner's `tokens.css` deliberately shifts to `#e53e3e` in dark. That difference is **deviation D1** ("the
dark accent actually works") and this file is its evidence — the register can now cite a measurement rather
than a recollection.

## What is *not* here, and why

### There is no owner backup JSON

`WF-030` and `WF-024` both require one backup JSON per trip exported before archiving. **The donor held no
trip data.** At capture time `localStorage` for its origin contained only:

- `alipay_splitter_theme` — 5 bytes
- `alipay_splitter_transactions` — 2 bytes, i.e. `[]`
- `alipay_splitter_settings` — **absent entirely**

It booted into the setup wizard, not a dashboard. Artifact 024 already recorded that *"no Auto-Bill backup
JSON exists anywhere on disk"*; this adds that no trip data exists in this browser profile either.

`synthetic-trip-settings.json` and `synthetic-trip-transactions.json` are from a **trip this capture created
itself** to reach the dashboard, modal and expense states. They are a **schema record — not the owner's
archive.** Do not treat them as migration input; there is no importer by decision anyway.

> **Answered by the owner on 2026-08-04: Auto-Bill was never used with real trip
> expenses.** So there is nothing to archive and `WF-030`'s pre-archive backup
> action is **discharged**, not skipped. S6 may archive the donor whenever it is
> ready. The original wording is kept below because the reasoning still applies if
> that answer ever turns out to be wrong.
>
> **This needed an owner answer before S6 archives the donor.** If Auto-Bill was ever used with real
> expenses, that data lives in some other browser profile or origin and is still exportable from the
> *Backups → Export Trip JSON Backup* control visible in `captures/backups-import-export-light.jpg`. If it
> was never used with real data, the obligation is discharged by this note and `WF-030`'s pre-archive action
> is satisfiable as "nothing to archive".

### Six elements are short

| # | Element | Gap |
|---|---|---|
| 16 | Filter bar | `filter-icon`, `search-icon` — icon wrappers |
| 27 | Transaction table | `cell-notes` — renders only for a row carrying a note |
| 28 | Split-mode badge | `m-man`, `m-sel`, `m-sgl` — only the `m-all` variant was reached |
| 37 | Import / export cards | `backup-icon`, `text-blue` |
| 30 | Main-cardholder selector | **No class selector exists** — fully inline, as artifact 021 recorded |
| 31 | Copy-memo action | **No class selector exists** — same |

30 and 31 cannot be matched by class at all; their styling is inside `inline-styles.json` but unkeyed, and
`WF-025`'s gate will have to treat them as new elements passing on token conformance plus a declared
ancestor rather than as diffable lifts. The other four are reachable states that this pass did not stage;
they are named here precisely so S6 can decide to stage them or accept them.

## The rebuild side, captured 2026-08-04

`rebuild-computed-styles.json` is the same capture taken against the planner: all
nine routes in both themes, **206 records**. `scripts/check_element_parity.py`
diffs the two by declared ancestor and runs as a `check.py` stage, so the
comparison survives the donor being archived — which an image diff would not.

Two things about how it compares, both learned by getting them wrong first:

- **The pairing is declared, not inferred.** Each `derives-from:` now reads
  `element 14 .stat-card as .money-tile`. Guessing the planner class from the
  nearest `className` picked the filter *container* instead of the chip.
- **Border width and style are not compared.** On a list row they are positional:
  a dashed separator with `:first-child { border-top: 0 }` captures as `0px` for
  whichever row is recorded first. Comparing them measured where an element sat
  in the DOM, not whether it matched the donor, and produced fifteen findings
  that were all artifacts of that.

A deviation licenses a difference only when the rebuild's value is what the
deviation actually mandates: D2 permits `2px` and pills, not any radius; D8
permits a token weight; and a shadow must still have **zero blur**, because
"same zero-blur hard offset shadows" is a locked requirement rather than taste.
Negative-tested by injecting a `14px` radius and a `9px` blur, both of which fail.

## Reproducing

```bash
npm install --prefix Auto-Bill-Splitter
npm --prefix Auto-Bill-Splitter run dev -- --port 5199 --strictPort
```

Then walk the wizard, add expenses in each split mode, and read `getComputedStyle` per classed element in
both themes. **Do this before S6 archives the donor**, or not at all.
