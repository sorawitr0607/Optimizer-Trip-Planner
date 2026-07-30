---
id: WF-025
title: Define the visual parity gate for the Tailwind rebuild
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
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
