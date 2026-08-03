---
id: WF-027
title: Decide the bilingual copy pipeline for the webapp
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
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

## Resolution comments

### 2026-08-03 — Decided through the copy-pipeline interview

The measured table survey, the work it creates and what is left open are in
[`027-bilingual-copy-pipeline.md`](../artifacts/027-bilingual-copy-pipeline.md).

**A live defect surfaced while measuring, and it reframes the ticket.** `ui/text.py` holds **eight**
bilingual tables and the parity rule is enforced for exactly **one** — `tests/test_foundation.py:346` checks
`TEXT` only. Two of the seven unchecked tables are asymmetric, and **24 optimizer codes have Thai text and no
English**. The asymmetry runs *against English*, the reverse of what `CLAUDE.md` warns about, and it is
invisible because every consumer prettifies rather than raising: an English owner reads `Access unverified`,
`Closed at available time` — machine output that looks exactly like intentional copy. **The fallback is the
camouflage**, which is what this ticket removes, not just the strings.

- **One JSON catalogue that both renderers read.** This follows from a fact rather than a preference:
  `WF-030` kept the Python exporters and `_export_labels()` is literally
  `TEXT[language] | OPTIMIZER_CODE_TEXT[language]`, so Python needs the copy for the PDF, poster and workbook
  regardless of where React reads it. Moving it to the frontend would duplicate the need, not remove it. Same
  shape as `WF-025`'s single colour source, for the same reason.
- **The parity test grows to all eight tables, and the fallback stops lying** — it renders as
  `⚠ ACCESS_UNVERIFIED`, not `Access unverified`. A fallback is still needed because the core can emit an
  uncatalogued code, and crashing mid-trip is worse than an ugly label; but it must be obviously not-copy.
  **Mandatory consequence:** the 24 missing English strings, plus `WF-019`'s 26 refusal codes and the 6
  `interpret.py` causes, must be written before the test can go green.
- **Plain JSON, no library.** Two locales, ~640 existing keys, and Thai has no plural forms — a library would
  be a seventh runtime dependency for unused machinery. The decisive property is the opposite of what a
  library offers: **TypeScript importing JSON `as const` checks keys at compile time**, which is stronger than
  runtime lookup, and runtime lookup is precisely what let 24 gaps hide. `ui/text.py`'s inline comments are
  design record and move to a sibling notes file rather than into the catalogue.
- **Thai for the ~120 ported strings is machine-drafted and owner-reviewed; the copy-memo template is written
  by hand**, because it is pasted into a real chat asking real people for money and Thai carries registers a
  translation gets subtly wrong. Machine-drafted entries are **flagged until reviewed**, so "reviewed" is a
  visible state rather than an assumption — the direct mitigation for the review-fatigue risk that choice
  accepts.
- **`CATEGORY_TEXT`'s English stays derived, with one override.** The title-case fallback is correct for
  **24 of 25** categories; only `place_of_worship` renders wrongly as "Place Of Worship". Writing all 25 would
  retype what the machine already gets right and would make every new OSM category need a string first. So it
  is the **one documented exemption** from key parity, and it gets a stronger test in exchange: assert every
  Thai key renders acceptable English through override-then-title-case, checking the rendered output rather
  than key equality.
- **Emoji decorate; wording always carries the meaning.** The rule already exists in `exporters._labels()`,
  whose docstring is the rationale, and it is directly testable by stripping pictographs and asserting nothing
  becomes empty. **Country flags are the hard case** — a flag-only cell becomes an empty cell in the PDF — so
  those elements need a text name or a non-emoji asset, which lands with the offline asset ticket that already
  owns replacing `flagcdn.com`.
