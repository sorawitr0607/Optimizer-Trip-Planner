# WF-041: one closed day no longer blocks every day

The owner chose the intersection option. **8 visits became 13 — every chosen
landmark, none behind a locked door.**

## The mechanism was already there and dead

Two pieces of the fix existed before any of it was written:

- `opening_intervals()` already stored **per-date** windows in `by_date`, and
  `common_interval` already computed `closed_dates`.
- The `opening_interval` fact already carried **`applies_to_dates`** — and nothing
  anywhere read it. The field had a comment calling it "recorded for audit".

So the information was present the whole time and thrown away twice: once by
`common_interval` refusing to intersect when any date was shut, and once by
`applies_to_dates` being written to a field no consumer looked at.

## The change

- **`opening.common_interval`** takes the overlap across the days a place is *open*
  rather than refusing outright, and returns `open_dates` beside `closed_dates`. A
  usable `interval` and a `CLOSED_ON_A_TRIP_DATE` reason now coexist: the hours are
  known **and** the place shuts on a named day. Callers key off `interval`.
- **`actions._optimizer_input`** sets `applies_to_dates` to the open dates.
- **`optimizer._open_on()`** is consulted twice: `_earliest_visit_start` returns
  `None` for a day the place is shut, and `validate_variant` raises
  `CLOSED_DURING_VISIT` if one is scheduled anyway.

No new fact type. A fact without `applies_to_dates` applies everywhere, so every
frozen fixture stays valid — which is why **27 of 27 regressions pass unchanged**.

## Result

| | before | after |
|---|---|---|
| Opening facts reaching the optimizer | 8 of 13 | **13 of 13** |
| Scheduled visits | 8 | **13** |
| Closed-door visits | 0 | 0 |
| Worst day walking | 34 min | **27 min** |
| Longest leg | 14 min | 14 min |

Recovered: Red House, Taipei Fine Arts Museum, Taipei Confucius Temple, Beitou Hot
Spring Museum, and the Botanical Garden herbarium.

**2027-01-04 is a Monday**, and it now carries only Sun Yat-sen Memorial Hall and
Taipei 101 — both open Mondays. The five Monday-closed venues moved to 12-31, 01-01,
01-02 and 01-03.

Cost: **US$0.00.** No provider call; the hours were already bought.

## Three tests asserted the defect

`test_a_place_closed_on_a_trip_date_produces_no_fact` **required no fact** — the bug
written down as a requirement. Renamed to
`test_a_place_closed_on_one_trip_date_is_still_usable_on_the_others` and inverted.
`test_closed_on_any_trip_date_yields_no_interval` became
`test_a_closed_date_narrows_the_window_rather_than_removing_it`, and a new
`test_closed_on_every_trip_date_yields_no_interval` covers the case that genuinely
has nothing to offer.

`report["unusable"]` no longer lists these places, because they are not unusable. The
closure is reported on the evidence instead of as a rejection — and
`OPENING_UNVERIFIED` no longer appears for hours that were verified and paid for.

## The first behavioural test did not discriminate

The end-to-end walk over the proposal passed **with the guard deleted**. The
fixture's single open day is the one the optimizer would choose anyway, so nothing
exercised the guard. That is recorded in the test rather than quietly fixed, and
`_earliest_visit_start` is now asserted directly — which does fail, with
`540 is not None`, when the guard is removed.

A test that cannot fail is worth nothing, and this one needed catching twice.
