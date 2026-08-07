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
- ~~**Read schema.org `OpeningHoursSpecification` from the page instead.**~~ **Measured
  2026-08-07 and it does not work: 0 of 9.** See below.
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

## Measured 2026-08-07: the structured-data option is dead, and the model option is
## smaller and riskier than it looks

Nine of the thirteen chosen places publish a website. All nine were fetched read-only
with the app's own user agent, one second apart, and parsed for structured data only.

**schema.org: 0 of 9.** Not one site carries a single `application/ld+json` block — no
opening hours, no structured data of any kind. Eight returned HTTP 200; Beitou Hot Spring
Museum times out from here on repeated attempts. Nor is there any
`itemprop="openingHours"` microdata. So the deterministic, model-free, injection-free
option is simply not available for this trip, and that option is struck above.

**Plain text: 6 of 9 name an hours concept, 5 of 9 contain any `HH:MM`.** But usefulness
is much narrower than that suggests:

| Site | What is actually there |
|---|---|
| Taipei Fine Arts Museum | **Complete weekly hours on the landing page**: 週一 休館, 週二至週日 9:30–17:30, 週六 9:30–20:30 |
| Huashan 1914 | A real one-off change notice — hours altered by **typhoon** 巴威 — exactly the shape Google cannot carry |
| CKS Memorial, Taipei Zoo | 開放時間 appears in **navigation only** |
| Taipei 101 | 觀景台營業時間 in navigation only, and no nav link a probe can follow |
| Baoan Temple, Lungshan Temple | **Nothing.** Zero times, zero keywords — temples do not publish hours |
| Beitou Hot Spring Museum | Unreachable |

**One hop is not enough.** Following the anchor whose own text says 開放時間 lands on
another index page — `cksmh.gov.tw/cl.aspx?n=6025` and
`zoo.gov.taipei/Content_List.aspx?n=…` both contain **zero** `HH:MM`. These are government
CMS sites where the hours sit two or more hops in. So this is not "fetch the site and
extract"; it is "crawl a CMS to find the hours page, then extract", which is a different
and much more fragile piece of work.

**And the one place that most needed it is the trap.** Sun Yat-sen Memorial Hall — the
place whose Google hours look like an office schedule — publishes a 休館公告 (closure
announcement) dated 2026-08-06 that is about a **server-room migration affecting the
website**, not about the hall being shut. A naive extractor reading "closure
announcement" plus a date produces a confident closure that does not exist. That is worse
than no data: an invented closure silently removes a landmark from the plan, and the
owner has no way to tell it from a real one.

### What this implies for the decision

Extraction would reliably help **one** of nine sites today, catch a genuine change notice
on a second, need a CMS crawler for three, find nothing at two, and can reach the ninth
not at all — while carrying a demonstrated failure mode on the very place the gap was
found. Against that, the readiness board's 13 manual checks are performed by someone who
reads Chinese and can tell a website outage notice from a building closure.

Any build should therefore be judged on whether it can be **safely wrong**: an extracted
closure must be visibly weaker than a verified one, must cite the sentence it came from
so the owner can judge it, and must never remove a place from a plan on its own.

## Related

- `WF-041` — per-day opening hours. It made a per-date `by_date` map reach the optimizer,
  which is the mechanism a holiday closure would ride on; the data to put in it is what
  is missing.
- `WF-045` — an activated plan is not re-validated when evidence improves. Found in the
  same measurement, and the reason that one lookup silently left a visit scheduled two
  hours after closing.
- `WF-038` — the `estimated` precedent for admitting weaker evidence honestly.
