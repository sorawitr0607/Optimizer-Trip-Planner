---
id: WF-046
title: Decide whether a model may supply the assumed opening window
status: closed
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide whether a model may supply the assumed opening window

## The app already guesses; the question is how badly

The owner asked whether a model API could answer for opening hours and be plugged in.
The first reading of that was "let a model state facts instead of evidence", which the
codebase forbids on purpose — `interpret.py`'s prompt says *"Never state an opening time,
route, fare, closure or crowd level"*, and no `revision.OPERATIONS` field can carry one.

That reading was wrong, and measuring showed why. When a place has no verified hours and
the trip is `explore_first`, `actions._optimizer_input` **has always emitted an assumed
window** — a flat `09:00–21:00`, for every place on earth, under
`source: "explore_first_planning_assumption"`. So the choice was never
*evidence versus a guess*. It was *which guess*.

And the constant is a bad one. The pilot's Sun Yat-sen Memorial Hall ran on it, the
optimizer scheduled a visit at **17:17–19:32**, and the real hours turned out to be
**08:30–17:30**. The plan passed validation with a visit two hours after closing.

## Measured 2026-08-07, against verified ground truth for 13 places

All 13 chosen places had Google-verified hours, so the model could be scored against them
directly. 13 calls, US$0.026.

| | Window ends **after** real closing | By how much |
|---|---|---|
| `gpt-4.1-mini` recall | 5 of 13 | 30–60 min |
| the `09:00–21:00` constant | 6 of 13 | **180–270 min** |

Five of thirteen matched both ends exactly (Shilin Cixian Temple, Chiang Kai-shek Memorial
Hall, Lungshan Temple, Taipei Fine Arts Museum, Taipei Zoo). Overshooting the closing time
is the failure that matters, because it is the one that schedules an impossible visit. On
Sun Yat-sen the model is 30 minutes wrong where the constant was 210.

The model also errs conservatively in places — Taipei Confucius Temple 09:00–17:00 against
a real 08:30–21:00, four hours short — which loses planning time but cannot schedule a
visit into a closed building. That is the right direction to be wrong in.

## Closures were requested, measured, and rejected

The same benchmark asked for weekly closed days. Seven claims came back; checked against
Google:

| Claim | Verdict |
|---|---|
| Red House, Beitou, Confucius Temple, Fine Arts Museum closed Mon | **confirmed** — matches `WF-041` exactly |
| Herbarium closed Mon | confirmed, but **missed Tuesday** |
| **Huashan 1914 closed Mon** | **invented** |
| **Taipei Zoo closed Tue** | **invented** |

A false closure silently removes a place from a day, and 29 December is a Tuesday. Two
inventions in seven is disqualifying for a field whose only effect is to drop things — and
Google supplies real closures anyway, so the risky half buys nothing. The model also
returned `"Mon"` and `"Monday"` interchangeably, which a loose schema allowed.

**`closed_weekdays` is therefore not requested at all**, and the system prompt forbids it.
A test asserts the response schema has exactly three properties. Do not add the field back
without re-running this benchmark.

## Decided and built 2026-08-07: the window only, still `assumed`

`providers.OpenAIOpeningWindowProvider` asks for one window per place.
`actions.refresh_assumed_windows` stores it as `place_evidence` of kind
`assumed_opening_window`, and `_optimizer_input` reads it in place of the constant.

Five properties carry the decision:

- **The status never changes.** The fact stays `status: "assumed"` whichever guess fills
  it. Only `source` differs — `model_recalled_window:<model>` against
  `explore_first_planning_assumption` — so the evidence screen can tell them apart and an
  owner can see where a window came from. Nothing is upgraded.
- **A place with verified hours is never asked about.** There is nothing an assumption can
  add to evidence, and asking would invite comparing the two as equals.
- **A `ready_to_schedule` trip refuses** (`assumptions_not_used_by_this_trip`). An assumed
  fact is only ever read under `allow_provisional_assumptions`, so buying one there would
  spend money on something the optimizer will not look at.
- **Declining is a valid answer.** `known: false` stores nothing and leaves the constant.
  Confirmed against the live model: an invented place, `萬華第六巷茶亭`, returned
  `known: false` rather than a plausible schedule.
- **`_optimizer_input` never fetches.** It runs on every read, so the window is read from
  storage only; a network call there would be a bill on page load. A test asserts three
  reads add no provider calls.

A malformed or backwards pair is treated as a refusal rather than repaired. Guessing what
was meant is how a bad assumption becomes an invisible one.

### Result on the pilot: it correctly does nothing

All 13 places have verified hours, so `refresh_assumed_windows` reports
`skipped_verified_or_held: 13`, `asked: 0`, and spends nothing. This is a fallback for the
next trip, or for a place Google cannot answer for — not a change to the live plan.

### What it does not do

It cannot help with a holiday closure. "Closed 1 January 2027" is after any training
cutoff and venues publish it weeks ahead; recall structurally cannot reach it. That gap is
`WF-044` and needs a fetch, not a model's memory.

### Tests

`tests/test_assumed_windows.py`, 13 tests. Negative-tested three ways: labelling a
recalled window `verified` fails, and asking about a place that already has verified hours
fails. That second guard was **untested at first** — the negative pass showed the fixture
had no verified hours, so the branch was never exercised, and a test using
`FakeHoursProvider` was added to close it.

386 tests green, all 12 `check.py` stages pass. Ledger US$1.995 of the US$10 cap, which
includes the 13 benchmark calls and 2 live wiring checks recorded after the fact — they
were made from a scratch probe that bypassed `_spend`, and the cap has to stay honest.

## The model changed to `gpt-5.6-luna` on 2026-08-07, and the benchmark was re-run

The owner asked for `5.6 luna`. It was not a name recognisable from here, so it was
**looked up rather than guessed** — `GET /v1/models` lists `gpt-5.6-luna`, and writing a
plausible-looking model string into config would have been the same fabrication this
ticket is about. It works on the existing Responses call with no code change.

Re-benchmarked against the same verified ground truth, through the shipped provider:

| | `gpt-4.1-mini` | `gpt-5.6-luna` |
|---|---|---|
| Answered | 13 of 13 | **12** of 13 |
| Exact on both ends | 5 of 13 | **6 of 12** |
| Ends after real closing | 5 | **4** |

Better on every count that matters, and better calibrated: it **declined** Shilin Cixian
Temple where `mini` claimed to know all thirteen. It also fixed `mini`'s worst answer —
Taipei Confucius Temple exactly right at 08:30–21:00, where `mini` said 09:00–17:00, four
hours short.

### One new failure mode, and the guard it forced

`gpt-5.6-luna` answered **00:00–23:59** for Huashan 1914, whose real hours are 11:00–21:00.
That is not a wrong window, it is a **non-answer that permits more than the constant it
replaces** — which inverts the entire justification for asking. `mini` never did this.

So `DEGENERATE_SPAN_MINUTES = 20 * 60`: a window spanning twenty hours or more is
discarded as `known: false` and the constant stands. The bar has to sit above sixteen
hours because temples really do open 06:00–22:00, and below a full day. Confirmed against
the live model — Huashan now returns `known: false` while Taipei Fine Arts Museum still
returns its exact 09:30–17:30.

The general rule worth keeping: **an assumption looser than the one it replaces is not an
improvement**, however specific it looks.

### The prices are now over-estimates and should be corrected

`openai:opening_window`, `openai:interpret_revision` and `openai:explain_revision` were
calibrated for `gpt-4.1-mini`. `gpt-5.6-luna`'s published rate is not known here, so all
three were raised **tenfold as deliberate over-estimates**, following the rule
`google_places:search_text` already states: an over-estimate protects the cap, an
under-estimate spends past it. They are wrong on purpose and should be replaced with the
real rates — an over-estimate that is wildly high will refuse calls the cap could afford.

## Related

- `WF-044` — the holiday-closure gap this does not close.
- `WF-045` — the activated plan that stayed `valid: true` after its evidence improved,
  found in the same measurement.
- `WF-038` — the `estimated` precedent for admitting weaker information honestly.
