---
id: WF-047
title: Decide how cost chooses between verified and assumed hours
status: closed
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide how cost chooses between verified and assumed hours

## The owner asked for a switch, and the switch is the wrong shape

Asked 2026-08-07, before a self-test of the whole journey: *if fetching opening hours for
N places costs more than using the model, switch to the model — batch it if that helps.*

The money is real. `google_places:search_text` is **US$0.025 a place** and it is the only
paid step that scales with the size of a trip: 13 places is US$0.325, 40 places is
US$1.00 against a US$10 monthly cap.

**There is no cheaper verified path.** Text Search takes one query per place and cannot be
batched. The cheaper `places/{id}` Details endpoint at US$0.017 needs a Google place id,
and the catalogue holds only OpenStreetMap ids — obtaining one costs the same search. So
US$0.025 a place is the floor for evidence, and no amount of engineering moves it.

**But an automatic switch would trade kinds, not prices.** Google returns
`status: "verified"`. The model returns `status: "assumed"`, which
`optimizer._planning_fact` reads **only** under `allow_provisional_assumptions` — so on a
`ready_to_schedule` trip a cost-triggered switch would spend money on a fact the optimizer
ignores, and produce a plan with *less* evidence for the same outcome. A rule phrased in
dollars cannot see that difference.

## Decided and built 2026-08-07: batch the assumption, price both, let the owner choose

**Batched.** `OpenAIOpeningWindowProvider.windows()` asks for many places in one request,
matched back by an **echoed integer index** rather than by name — a model may translate or
normalise a name, and an invented or repeated index simply yields no answer for that
place. `refresh_assumed_windows` charges the ledger **once per request** instead of once
per place, chunked at `BATCH_SIZE = 20` so a large trip cannot put an unpredictable payload
behind one price.

For the pilot that is one call instead of thirteen: **US$0.0005 against US$0.0065**, and
against Google's US$0.325 it is roughly 650× cheaper.

### Batching measured *more* accurate, not less

Against verified hours for all 13 pilot places:

| | 13 separate calls | one batched call |
|---|---|---|
| Answered | 12 of 13 | 11 of 13 |
| **Exact on both ends** | 6 of 12 | **8 of 11** |
| **Ends after real closing** | 4 | **1** |
| Cost | US$0.0065 | US$0.0005 |

Taipei 101, Taipei Confucius Temple, Dalongdong Baoan Temple and Red House all landed
exactly right where individual calls missed. Seeing the list together appears to steady
it. That was not the expected result — batching is normally a quality compromise — so it is
recorded as measured rather than reasoned, and the prompt gained an explicit instruction to
judge each place independently rather than copy one place's hours onto a similar one.

Two places got no answer at all and keep the flat constant, which is the correct outcome
for a place it does not know.

### The trade is reported, not taken

`actions.opening_evidence_options` returns both paths with their call counts and prices,
which trip states can use them, and — travelling **with** the price so it cannot be read
without it — the measured error rate of the cheap one: 8 of 11 exact, 1 overshooting real
closing, worst overshoot 30 minutes.

It also returns `assumed_is_usable: false` for a `ready_to_schedule` trip, because
offering a cheaper path that the optimizer will not read is selling something that does
nothing.

**No threshold, and no automatic switch.** After batching, the cheap option costs a
rounding error at any trip size, so a dollar threshold would fire every time and amount to
"never buy evidence". Removing money from the comparison is what leaves the real question
visible: an owner who wants a timetable they can rely on buys hours, and one still
exploring does not.

### Tests

`tests/test_assumed_windows.py`, 18 tests. Three pin this ticket: the ledger is charged
per **call** not per place, a trip larger than one chunk makes one call per chunk, and the
preflight prices both paths and reports the error rate beside them. One existing test
asserted the old per-place billing and was rewritten rather than deleted — it was
describing the cost model this ticket changed.

418 tests green, all 12 `check.py` stages pass. `opening_evidence_options` is the 74th
allowlisted method, and a read.

## Related

- `WF-046` — where the assumed window came from, and where 2 of 7 invented weekly closures
  were measured. The reason a cheaper answer is still not a better one.
- `WF-044` — the other reason hours cost money: a weekly pattern cannot carry a holiday
  closure, whatever it cost to obtain.
