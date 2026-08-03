# Bilingual copy pipeline for the webapp

Resolves `Decide the bilingual copy pipeline for the webapp` (WF-027).

Decided 2026-08-03 through the copy-pipeline interview. Measured against the checkout at `a774aae`.
Paths are repo-relative.

## The state of the copy tables, measured

`ui/text.py` holds **eight** bilingual tables. The parity rule everyone believes is enforced is enforced
for exactly **one** of them — `tests/test_foundation.py:346`, `assertEqual(set(TEXT["en"]), set(TEXT["th"]))`.

| Table | `en` | `th` | Parity | Tested |
|---|---|---|---|---|
| `TEXT` | 524 | 524 | OK | **yes** |
| `TAG_TEXT` | 21 | 21 | OK | no |
| `EXPLANATION_TEXT` | 26 | 26 | OK | no |
| `REJECTION_TEXT` | 7 | 7 | OK | no |
| `DIMENSION_TEXT` | 6 | 6 | OK | no |
| `ACCOMMODATION_TEXT` | 3 | 3 | OK | no |
| `CATEGORY_TEXT` | **0** | 25 | derived by design (§5) | no |
| `OPTIMIZER_CODE_TEXT` | **5** | 29 | **24 English missing** | no |

### The live defect, and why nobody saw it

**24 optimizer codes have Thai text and no English.** `ACCESS_UNVERIFIED`,
`ACCOMMODATION_BASE_UNCONFIRMED`, `CLOSED_AT_AVAILABLE_TIME`, `DESTINATION_TIMEZONE_UNVERIFIED`,
`EFFORT_OR_TIME_CONFLICT`, `ENTRANCE_UNVERIFIED` and 18 more.

The asymmetry runs **against English**, which is the reverse of what `CLAUDE.md` warns about ("a missing
`th` key is a `KeyError` in front of a Thai owner"). And it is invisible because every consumer prettifies
rather than raising:

- `ui/shared.py:266` — `OPTIMIZER_CODE_TEXT.get(language, {}).get(code, code.replace("_", " ").capitalize())`
- `exporters.py:991` — `words.get(text) or text.replace("_", " ").capitalize()`

So an English owner reads `Access unverified`, `Closed at available time`, `Effort or time conflict` — machine
output that looks exactly like intentional copy — while a Thai owner reads curated sentences. **The fallback
is the camouflage.** That is the mechanism this ticket has to remove, not just the missing strings.

## The six decisions

| # | Question | Decided |
|---|---|---|
| 1 | Where copy truth lives | **One JSON catalogue both renderers read** |
| 2 | A missing key | **Parity test over all tables; the fallback marks itself visibly** |
| 3 | Format and library | **Plain JSON, no library.** TypeScript imports it `as const` |
| 4 | Thai for the ~120 new strings | **Machine-drafted and owner-reviewed; the memo template written by hand** |
| 5 | `CATEGORY_TEXT` | **English stays derived, with one override**, tested on rendered output |
| 6 | Emoji | **Decorative only — wording always carries the meaning** |

## 1. One catalogue, because both renderers need it

```
i18n/copy.<lang>.json          the single source
   ├── ui/text.py  (thin loader)  →  exporters.py → PDF · poster · workbook
   └── web/src/i18n/              →  React
```

This is not a preference — it follows from a measured fact. `WF-030` kept the Python exporters, and
`_export_labels()` (`ui/shared.py:331`) is literally `TEXT[language] | OPTIMIZER_CODE_TEXT.get(language, {})`.
Python needs the copy for the PDF, poster and workbook regardless of where React reads it. Moving the
catalogue to the frontend would not remove Python's need; it would **duplicate** it.

It is the same shape `WF-025` chose for colour, for the same reason: one source so the screen and the
workbook cannot disagree.

Accepted costs: `ui/text.py`'s 1,293 lines lose their inline comments unless those move too (see §3), and
Python gains load-and-validate code where a module-level dict was free.

## 2. The parity test grows to all tables, and the fallback stops lying

Two changes, and the first matters more:

**The test covers every bilingual table.** Seven of eight are unchecked today and two of those seven are
broken. Extending it is what makes a gap unable to ship — and it turns the 24 missing English strings from
an invisible defect into a red test.

**The fallback becomes visibly machine output.** A surviving fallback must not read as copy:

```
⚠ ACCESS_UNVERIFIED          not          Access unverified
```

A fallback is still needed, because the core can emit a code nobody has catalogued yet, and crashing the
screen in front of the owner mid-trip is worse than showing an ugly label. But it must be obviously not-copy
or it hides exactly what it exists to surface.

**Consequence, and it is mandatory work:** the 24 missing English optimizer strings must be written before
the test can go green. Plus the new vocabularies this phase created — `WF-019`'s **26 refusal codes** and the
**6 `interpret.py` causes** — need entries in both languages, since they are new code→text keys the frontend
will branch on.

## 3. Plain JSON, no library

Two locales, roughly **640 existing keys** plus ~120 ported ones plus 32 new code keys. Thai has no plural
forms and the existing copy demonstrably needs no pluralisation machinery, so a translation library would be
a seventh runtime dependency for capability that stays unused — against `WF-026`'s six.

The decisive property is the opposite of what a library offers:

```ts
import copy from "./copy.en.json";   // as const → keys checked at COMPILE time
```

**TypeScript's compile-time key checking is a stronger guarantee than any runtime i18n lookup** — and it is
free. Runtime lookup is precisely the mechanism that let 24 gaps hide. Python reads JSON with no dependency
at all.

Interpolation stays hand-rolled, as the existing code already does it.

**Where the comments go.** `ui/text.py`'s inline notes are real design record, not clutter — they explain why
strings are worded as they are. They move to a sibling notes file keyed by the same keys, not into the JSON,
so the catalogue stays machine-clean while the reasoning survives.

## 4. Thai authoring: machine-drafted, owner-reviewed, memo by hand

The ~120 hardcoded English strings across Auto-Bill's three components are the single largest mechanical
change in the port. Routine labels are machine-drafted and reviewed; **the copy-memo clipboard template is
written by the owner personally**, because it is pasted into a real chat asking real people for money, and
Thai carries obligation and politeness registers a translation gets subtly wrong.

> **Provenance is marked.** The accepted risk here is review fatigue — 110 plausible-looking strings get
> skimmed and a wrong register survives. So machine-drafted entries are flagged in the notes file until
> reviewed, which makes "reviewed" a visible state rather than an assumption, and lets a second pass find
> what the first skimmed.

## 5. `CATEGORY_TEXT`: English is derived, not missing

`CATEGORY_TEXT["en"]` is `{}` and that is **almost right by construction**. The `code.replace("_", " ").title()`
fallback renders correct English for **24 of 25** categories — `Aquarium`, `Theme Park`, `Nature Reserve`,
`Department Store`, `Sports Centre`. Exactly one is wrong:

```
place_of_worship  →  "Place Of Worship"      ← capitalised preposition
```

So: **keep derivation as the English mechanism and add one override.**

```python
CATEGORY_TEXT["en"] = {"place_of_worship": "Place of worship"}
```

Writing all 25 by hand would retype what the machine already produces correctly, and would mean every new
OSM category needs a string before it can display — where today it just works.

**`CATEGORY_TEXT` is therefore the one documented exemption from the all-tables parity rule**, and it gets a
*stronger* test in exchange: assert that every `th` key renders acceptable English through override-then-
title-case, with no capitalised prepositions. That checks the rendered **output** rather than key equality,
which is what actually matters, and it catches the next multi-word category automatically.

Accepted: "acceptable English" is a heuristic, not a proof.

## 6. Emoji decorate; wording carries meaning

The rule already exists in Python and only needs stating and enforcing. `exporters._labels()` strips
pictographs, and its docstring is the rationale:

> "The app's status labels carry emoji for on-screen scanning; a PDF or poster font has no pictographs, so
> they would silently drop. The wording alone still carries the state, which is what *colour is never the
> only signal* needs."

So emoji are allowed on screen — keeping Auto-Bill's visual character — but **never the only signal**, and it
is directly testable: strip pictographs from every catalogue string and assert none becomes empty or
ambiguous.

```
✓  "✈️ Flight to Taipei"   →  "Flight to Taipei"
✗  "✈️"                    →  ""
```

> **Country flags are the hard case.** Auto-Bill uses flag emoji where the flag carries essentially all the
> meaning, so a flag-only cell becomes an **empty cell** in the PDF. Those elements need a text country name
> beside the flag, or a non-emoji flag asset — which is `Decide the offline asset policy for the webapp`'s
> concern, since it already owns replacing `flagcdn.com`.

This is also an accessibility floor, not only an export concern.

## The work this creates

| Item | Scale |
|---|---|
| Missing English optimizer strings | **24**, mandatory before the test goes green |
| New code→text keys from this phase | **32** (26 refusal codes + 6 interpret causes), both languages |
| Ported Auto-Bill strings needing Thai | ~120, machine-drafted and reviewed |
| Memo template | 1, owner-written |
| `CATEGORY_TEXT` override | 1 |
| Tests | parity over all tables · derived-English check · pictograph-strip check |
| Migration | `ui/text.py` → JSON catalogue + sibling notes file |

## Explicitly not decided here

- Whether the catalogue is one file per language or one file with language keys.
- The notes file's format.
- How the language is persisted in the webapp (the POC used a Streamlit widget key; `WF-028` put the trip in
  the path but said nothing about language).
- Whether `ui/text.py` survives as a shim after the port or is deleted with the rest of `ui/`.

## What this hands downstream

| Ticket | Consequence |
|---|---|
| `Decide the offline asset policy for the webapp` | Inherits the country-flag problem: flag emoji cannot be the only signal, so it needs a text name or a non-emoji asset alongside its `flagcdn.com` replacement |
| `Decide the test strategy after Streamlit AppTest dies` | Three new copy tests are all pure and browser-free — parity, derived English, pictograph-strip — so they are exactly the model post-`AppTest` coverage should follow |
| `Design the feedback, confirm, and disabled elements Auto-Bill never had` | The 26 refusal codes are its copy surface, and they need Thai written as part of that work |
| `Prototype the merged cost and split screen` | The memo template is on the split screen and is owner-written, not machine-drafted — treat it as content, not a label |
| `Lock the Phase 2 slice plan and validation scorecard` | ~180 strings of copy work is a sizeable, sequenceable item that no prototype can proceed far without |
