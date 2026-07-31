---
id: WF-027
title: Decide the bilingual copy pipeline for the webapp
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
blocked_by:
  - WF-026
---

# Decide the bilingual copy pipeline for the webapp

## Question

Where does user-facing copy live once the UI is React — still Python, or in the frontend — and how is
`en`/`th` key parity still enforced?

## Context

- `ui/text.py` is 1170 lines of `en` and `th` dictionaries: `TEXT`, `TAG_TEXT`, `EXPLANATION_TEXT`,
  `OPTIMIZER_CODE_TEXT` and more. The rule is bilingual by data, not by branching: the core emits stable
  codes, the views map code to language to text. A test asserts `TEXT["en"]` and `TEXT["th"]` carry the same
  keys, because a missing Thai key is a `KeyError` in front of a Thai owner rather than a cosmetic typo.
- The hard invariant to preserve: switching language must never change ranking, scheduling, or the active
  plan. No display text in the core, no language check in a scoring path. A city name is the geocoder query,
  so it is never localized — localizing it would change which place is searched.
- Some codes are emitted by the core and must be translated somewhere (`OPTIMIZER_CODE_TEXT`,
  `EXPLANATION_TEXT`), while some copy is purely presentational. Those two groups may not belong on the same
  side of the API boundary.
- Auto-Bill has no i18n at all — every string is inline English JSX across three components, including the
  copy-memo clipboard template. Every element lifted from it needs Thai written for the first time, and the
  memo template is copy a human will paste into a chat with real people.
- The PDF and poster exports need a font covering Latin, Thai, and CJK, and `_labels()` strips pictographs
  because no such font carries emoji. Auto-Bill leans on emoji in its UI (`✈️`, `☀️`, `🌙`, country flags),
  so decide whether emoji in the webapp are allowed to reach an export path.

Scale of the mechanical work, from the element inventory: roughly **120 hardcoded English strings** across the
three Auto-Bill components must become dictionary lookups with Thai written for the first time — including the
copy-memo clipboard template, which a human pastes into a chat with real people. That is the single largest
mechanical change in the whole port, larger than any individual element.

Decide at least: whether Python stays copy truth and serves or generates the frontend catalogue, or the
catalogue moves to the frontend and Python keeps only codes; the file format and where it lives; how the
parity test runs against the new location; whether a translation library is used at all; and who authors
Thai copy for the newly ported splitter elements.
