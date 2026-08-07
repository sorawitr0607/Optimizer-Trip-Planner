---
id: WF-044
title: Decide whether a venue's own site fills the holiday-hours gap
status: open
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide whether a venue's own site fills the holiday-hours gap

## A weekly pattern cannot say "closed 1 January"

The pilot trip runs 29 December 2026 to 4 January 2027. Every opening fact the app holds
is a **weekly** pattern — `google_places:search_text` returns periods by weekday, and
`opening.intervals_by_date` expands them by day of week. Nothing in that shape can
express a one-off holiday closure, and New Year is the single most likely week in the
year for one.

As of 2026-08-07 all 13 chosen places carry `status: "verified"` hours and
`capability_gaps` is **empty**. So the app now reports full opening coverage for a trip
whose most likely failure is a closure it structurally cannot represent. That is the
gap: not missing evidence, but evidence of the wrong shape, reported as complete.

The readiness board already works around it by hand — 13 generated items reading "Check
opening hours and advance booking for X", one per landmark, all
`verification_needed`. That is the honest fallback and it is entirely manual.

## `verified` means a provider said so, not that it is true

Found while buying the last missing lookup. Google returns, for **Sun Yat-sen Memorial
Hall**:

| Weekday | Hours |
|---|---|
| Mon–Fri | 08:30–17:30 |
| Sat, Sun | **closed** |

A major Taipei attraction closed at weekends is implausible; Mon–Fri 08:30–17:30 is an
office schedule. The likeliest explanation is that the matched Place is the hall's
**administration office** rather than the visitor hall. The app cannot tell the
difference, and neither can a reader of the word `verified`.

The consequence is not hypothetical. The optimizer now routes around a weekend closure
that may not exist, and would refuse a Saturday visit that is probably fine. The place's
own site is `https://www.yatsen.gov.tw/`.

**Do not "fix" this from memory.** Asserting the real hours because a model recalls them
is exactly the failure this ticket is about; the correction has to come from a fetched,
citable source or from the owner.

## What has to be decided

- **Fetch the venue's own page and extract stated hours with a model.** Answers both
  problems: a holiday notice and a wrong Place match are both visible on the site. Two
  conditions are non-negotiable. It must **fetch and refuse when the fetch fails** — a
  model answering from memory is recall dressed as evidence — and the result can never
  be `verified`. A new `status: "extracted"` carrying `source_url` and a retrieval
  timestamp, admitted only where `allow_provisional_assumptions` is set, mirrors exactly
  what `WF-038` did for `estimated` transit routes. A venue page is also **untrusted
  content**, so the strict output schema is a containment boundary and not just a parser.
  Costs about US$0.002 a place at `openai:interpret_revision`'s rate.
- **Read schema.org `OpeningHoursSpecification` from the page instead.** Many venue and
  museum sites publish JSON-LD. Deterministic, free, no model, no prompt-injection
  surface — and it fails silently on the sites that do not publish it, which is probably
  most Taiwanese government venues. Worth measuring before assuming the LLM is needed.
- **Re-fetch Google nearer the trip.** US$0.325 for all 13. Fixes *stale* hours, which is
  a real risk for August data, and does **nothing** for the holiday case, because the
  shape is still weekly. Cheap, and not a substitute.
- **Leave it to the owner and the board.** Defensible: the 13 checklist items already
  name the task, and a venue's own site is exactly where a person would look. Then the
  fact that `capability_gaps` is empty while a one-day closure is unrepresentable should
  still be said out loud somewhere, so this is not a no-op either.

Whichever is chosen, `interpret.py` **cannot** be widened to do it. Measured: all nine
`revision.OPERATIONS` take arguments like `factor`, `place_id` and `minutes`, and not one
can carry a time, a closure or a fare. That is deliberate — an operation is a constraint
change, never a fact — so this needs a separate provider, not a bigger interpreter.

## Related

- `WF-041` — per-day opening hours. It made a per-date `by_date` map reach the optimizer,
  which is the mechanism a holiday closure would ride on; the data to put in it is what
  is missing.
- `WF-045` — an activated plan is not re-validated when evidence improves. Found in the
  same measurement, and the reason that one lookup silently left a visit scheduled two
  hours after closing.
- `WF-038` — the `estimated` precedent for admitting weaker evidence honestly.
