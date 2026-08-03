---
id: WF-025
title: Define the visual parity gate for the Tailwind rebuild
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
blocked_by:
  - WF-020
---

# Define the visual parity gate for the Tailwind rebuild

## Question

Since the tokens are being rebuilt rather than copied, how is "the same design as Auto-Bill" proven rather
than asserted — and what counts as a parity failure that must be fixed?

## Context

- The destination interview chose a Tailwind / CSS-modules rebuild over lifting `index.css` verbatim, while
  the stated requirement is the same design, the same colour palette, and the same elements. Those two
  choices only coexist if parity is checked mechanically; every re-derived value is a chance to drift.
- The signature is fragile in specific ways: hard offset shadows at zero blur (`1px`, `3px`, `5px`) read as
  neo-brutalist, and Tailwind's default shadow scale is soft and blurred. The `1px` black card border, the
  warm off-white `#FCFBF9` rather than pure white, and JetBrains Mono on numerals are equally load-bearing.
  Any one of them replaced by a framework default loses the look while every colour still "matches".
- Auto-Bill overrides the accent per destination at the document root at runtime, so parity is not a single
  screenshot — it varies by country, and by light versus dark theme.
- Half the planner's screens have no Auto-Bill counterpart at all (see the element inventory ticket), so a
  pure screenshot-diff gate cannot cover them. Those need a rules-conformance check instead: does the new
  element use only tokens from the contract.
- The webapp is bilingual. Thai text sets at different metrics than Latin, so a layout that is pixel-perfect
  in English can break in Thai — parity must be checked in both languages.

The token contract is now extracted — [`020-auto-bill-token-contract.md`](../artifacts/020-auto-bill-token-contract.md)
is the target artifact, and it hands this ticket seven numbered ambiguities that a parity gate must rule on
rather than reproduce blindly. Each is a place where "identical to Auto-Bill" and "correct" diverge:

- The dark accent triple (`#E53E3E` / `#3B1C1C` / `#FC8181`) is dead code, because `App.jsx:64-66` writes the
  country accent as an inline style on `<html>` which beats `:root.dark`. Parity with a bug is still a choice.
- Two radius systems coexist — `2px` on cards, buttons, inputs, avatars versus `0.375rem`–`1rem` on charts,
  badges, settings, modal, plus `.setup-card` alone at `4px`. Reads as an unfinished sharp-restyle.
- Both documented fallbacks return blue (`#2563eb`), never the house red, and disagree on currency.
- `#8b5cf6` is an untokenised fifth semantic colour across 8 uses.
- Stale blue from a previous accent theme survives in a red app (`index.css:1427`, `:1797`).
- Bold monospace is faux — the weight is never loaded. (Handled with the fonts in the offline asset ticket.)
- The category and participant colour palettes are **data, not decoration**, living in JSX and duplicated
  verbatim across two files, with tints built by string concatenation at five undocumented alphas.
- Roughly 28 classes are styled inline only, so the entire filter-dimming interaction exists nowhere in the
  stylesheet — a CSS-only port loses it silently, which is precisely what this gate exists to catch.

The element inventory sharpens that last point and partly contradicts the count: it found **18 JSX class names
with zero CSS rules**, styled across **113 inline `style={{…}}` sites**, including the entire settlement grid,
the settlement item, and the main-cardholder selector. The two tickets measured different things (classes styled
only inline versus classes with no rule at all), so reconcile the numbers against the sources rather than
trusting either figure — and treat the token contract as **incomplete for inline-only elements** until that is
done. A parity gate that reads only the extracted contract inherits the same blind spot the contract had.
See [`021-element-inventory-matrix.md`](../artifacts/021-element-inventory-matrix.md).

Decide at least: the artifact that defines the target (extracted token table, reference screenshots, the
running Auto-Bill app itself); whether checking is manual review, a token-diff test, screenshot comparison,
or a linted allowlist of permitted values; who signs off; and what the gate does for elements that never
existed in Auto-Bill.

## Resolution comments

### 2026-07-31 — Decided through the parity interview

The gate's full definition, the deviation register, the failure conditions and the ordered prerequisites are
in [`025-visual-parity-gate.md`](../artifacts/025-visual-parity-gate.md).

**The inline-only count is reconciled, and both prior figures undercount.** Measured against the sources:
**39** JSX classes have no CSS rule (not 18 or 28), across **114** inline `style={{…}}` sites (88 Dashboard /
16 Modal / 10 Wizard), against **250** distinct class selectors in `index.css`. `WF-021` counted renderable
elements and `WF-020` a different slice, so neither was wrong for what it measured — but **the contract's
blind spot is larger than either ticket assumed**. Three groups matter most: the six filter-dimming classes,
the five split-allocation-mode classes plus three settlement classes (which is the `/split` screen's entire
layout), and **seven Tailwind-shaped names that were never written** and now dissolve into real v4 utilities
for free. Also noted: Auto-Bill *does* have tab views, styled inline only, which is why the inventory
reported none.

- **The target is the token contract, but the gate is blocked until it is completed** for those 39 classes,
  the 114 inline sites, the off-token literals, and the 3 hardcoded pin hexes in `views/itinerary.py`. It is
  chosen over the running app because the donor gets archived, so an app-anchored gate expires by design.
- **Checking is screenshot comparison at two levels, and only one of them is parity.** Whole-screen diffs
  against the donor are impossible — Auto-Bill has 2 screens, the planner has 9 routes. So: **element-level**
  diffs of the 41 lifted elements rendered in isolation in both projects, which **must be captured before
  `Auto-Bill-Splitter` is archived**; plus **screen-level** regression baselines of the rebuild, which catch
  drift but do not prove parity and must not be described as if they do.
- **4 baselines per screen, 36 total** — light/dark × en/th. The 13 accents collapse to a token assertion
  because the accent is a single inline custom property on `<html>`: it can recolour a pixel but never move
  one. Thai gets its own baseline per theme so Thai metrics never cause a false failure, captures happen on
  one fixed machine, and a pixel tolerance must be agreed when the harness is built.
- **Elements with no counterpart pass on token-only conformance plus a declared ancestor**, which the
  inventory already assigned for all 18. The numbered map canvas is explicitly exempt — `WF-021` found the
  visual language does not extend to it — though the stop list beneath it derives from the donut legend.
- **Auto-Bill's defects are fixed and recorded in a deviation register (D1–D7).** Without the register the
  gate cannot function: every intentional fix would read as a parity failure. Faux bold monospace stays with
  `WF-034`; the duplicated `.landing-wizard-side` is cleanup, not a deviation; and the fallbacks' currency
  disagreement is moot because the planner has its own currency handling.
- **Radius unified on `2px`**, pills exempt. This finishes what `WF-020` reads as an unfinished sharp
  restyle, dissolves two ambiguities at once, and collapses 11 radius values to one. Accepted as a real
  visual change: charts, badges and the modal will read sharper than the donor.
- **Colour data gets one machine-readable source that both renderers read.** This closes a parity hole
  nobody had noticed: `exporters.py` hardcodes **8 hexes across 17 occurrences** in a cool blue-grey palette
  that matches nothing in Auto-Bill, so the poster, PDF and workbook currently look like a different
  product — and `WF-022` already made those exports a pilot-ready gate. The precedent is `WF-018`'s: one
  implementation so the screen, the workbook and the PDF cannot disagree. It also names the five
  undocumented tint alphas and de-duplicates the category and participant palettes.

Sign-off is the owner; single-owner is a locked destination decision, so there is nobody else.

### 2026-08-03 — Amended by the slice plan: D7 shrinks to one hex

[Lock the Phase 2 slice plan and validation scorecard](033-lock-the-phase-2-slice-plan-and-validation-scorecard.md)
records an owner decision to drop the PDF and the poster. Measured, **16 of the 17 hardcoded export hexes live
in the poster**, so **deviation D7 shrinks to a single workbook hex**. The gate, the register D1–D10, the
element-level captures, the 36 baselines and the token allowlist are all unaffected.
