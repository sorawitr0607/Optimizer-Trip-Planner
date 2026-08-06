---
id: WF-037
title: Decide how ranking handles crowded categories and landmark signal
status: closed
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide how ranking handles crowded categories and landmark signal

## Why this exists

Found on 2026-08-04 while completing the real Taipei trip's setup for pilot-ready
gate 1. The owner picked places from the app's own ranked list, made **96
decisions** including rejecting 71 peaks, and still ended up with a `must_do` set
containing no Taipei landmark — four neighbourhood parks, several minor
viewpoints, a university archive, and one hill.

That is not an owner mistake. The ranking never offered the landmarks.

Full measurement in
`artifacts/validation/2026-08-04-pilot-setup-and-ranking-finding/`.

## The measurement

Sorted by `total_score` on the real 832-candidate Taipei catalogue, before any
choices were recorded, the **top 50 were 49 peaks and one park**. Where the city's
actual sights sat:

| Place | Rank of 832 | Score | `group_preference_fit` |
|---|---|---|---|
| Elephant Mountain | 22 | 70.2 | 27.0 / 30 |
| Chiang Kai-shek Memorial Hall | 181 | 57.3 | 15.8 / 30 |
| Beitou Hot Spring Museum | 265 | 54.3 | 15.8 / 30 |
| National Palace Museum | 269 | 54.3 | 15.8 / 30 |
| **Taipei 101** | **363** | 51.6 | 12.8 / 30 |
| Red House, Ximending | 561 | 43.0 | 3.0 / 30 |
| *Dailaokengshan (top-ranked)* | *1* | *75.2* | *27.0 / 30* |

**Discovery is not at fault.** All of those are present in the catalogue —
verified directly, because `out center qt` truncation is a known way for a large
city to lose its landmarks.

## Three contributing causes, all measured

1. **`group_preference_fit` rewards tag count.** It is the largest dimension, 30
   of 100, and it scores tag overlap. `CATEGORY_TAGS["peak"]` has four entries
   `{nature, photography, rewarding_walks, sightseeing}`; `attraction`, which is
   where OSM puts Taipei 101, has two `{photography, sightseeing}`. A category
   with more tags wins more overlap for the same place quality. That is an
   artifact of the taxonomy, not a property of anywhere.
2. **`EXPERIENCE_PRIOR` ranks `landmark` last among sightseeing categories.**
   `peak: 16`, `tower: 15`, `attraction: 14`, and **`landmark: 11`** — below
   everything except `mall` and `spa` at 9 and 8. A category prior asserting that
   an unnamed hill is more rewarding than a city's signature sight.
3. **`is_city_icon` carries no weight at all.** 302 of 832 candidates are flagged,
   and it is the one evidence-derived quality signal available. In `ranking.py` it
   appears only in lane assignment, `pros`, and `why_shown` — never in any score
   computation.

## A cheap fix was tried and it made things worse

A per-category crowding deduction was implemented and measured: rank candidates
within their category, leave the best three untouched, deduct on a log curve
after that. It improved apparent diversity — top 50 went from 49 peaks to 12 —
and **moved four of the six target landmarks further down**:

| Place | Before | After crowding |
|---|---|---|
| Taipei 101 | 363 | **458** |
| National Palace Museum | 269 | **308** |
| Beitou Hot Spring Museum | 265 | **304** |
| Elephant Mountain | 22 | **98** |
| Chiang Kai-shek Memorial Hall | 181 | 43 |
| Red House | 561 | 199 |

The reason is structural and worth keeping: **it ranks within a category using the
same score that is already tag-biased.** Taipei 101 scores 12.8/30 on preference
fit, so it sits low among 43 `attraction`s and then collects a further 15-point
crowding deduction. Any fix that sorts by the broken score amplifies the break
exactly where it hurts.

That change was reverted, not committed.

Also recorded: **adding `culture`, `markets` and `night_view` to the owner profile
does not fix it.** Tested on a copy — the top 50 moved from 49 peaks to 44 peaks
plus 4 museums, and the top six were unchanged. This is not a missing-tag
problem.

One thing that *does* partly work: `learned_category_bonus`. After the owner's 71
peak rejections, the top-50 peak count fell from 49 to 29 unaided. But the same
mechanism then promoted the viewpoint and park categories the owner had picked
from the already-skewed list, pushing Taipei 101 from 363 to 398. The learner
faithfully amplifies whatever the ranking first offered.

## What has to be decided

Not "should this be fixed" — that the pilot's own trip cannot surface Taipei 101
answers that. The decision is **which mechanism**, and each has a real cost:

- **Give `is_city_icon` weight.** It is the honest quality signal and it is
  evidence-derived. But `FORMULA_WEIGHTS` sums to 100 and is locked at
  30/20/20/10/15/5, so this reopens the formula that `WF-005` settled, and every
  frozen ranking fixture moves.
- **Rebalance `EXPERIENCE_PRIOR`.** Smallest diff, no formula change. But it is a
  table of taste constants, and re-tuning it per city is exactly the manual
  fiddling the deterministic ranker exists to avoid.
- **Normalise preference fit by category tag-set size.** Attacks the actual root
  cause, so a 2-tag category is no longer structurally penalised. Highest risk:
  it changes every card's largest dimension, and the 27 historic regressions and
  every ranking fixture would need re-baselining with a judgement about which
  historic outcomes were right for the wrong reason.

Whatever is chosen, two constraints hold. The scorecard states that a change
altering ranking is a regression unless justified, so this needs its own
before/after evidence on the real catalogue. And `deterministic_signature` must
not move for a fixed optimizer input — ranking feeds *which* places are offered,
not how a fixed input is scheduled, so the optimizer regressions should be
unaffected; that must be verified rather than assumed.

## Decided and built 2026-08-06: normalise preference fit by category breadth

The third option. `group_preference_fit` divided the owner's matched styles by how
many styles they *named*, which asks "how many of your interests does this cover" — a
question a category with more tags wins for free. It now divides by how many tags the
**category itself carries**, asking "how much of what this place is matches what you
want". `_breadth()` caps the divisor at four, because past that the divisor stops
discriminating and starts punishing richly-tagged categories, which is the mirror of
the bug.

**Measured on the real 832-candidate Taipei catalogue:**

| Place | Before | After |
|---|---|---|
| Sun Yat-sen Memorial Hall | — | **#12** |
| Taipei Fine Arts Museum | — | **#14** |
| **Taipei 101** | **#398** | **#21** |
| Chiang Kai-shek Memorial Hall | #181 | **#37** |
| National Palace Museum | #251 | **#57** |
| Beitou Hot Spring Museum | #265 | **#82** |
| Lungshan Temple | — | #131 |
| Red House | #561 | #228 |

Top-50 category mix went from **49 peaks and 1 park** to **34 museums, 12
attractions, 3 parks, 1 peak**.

27 of 27 historic regressions pass unchanged, 327 tests green, and the pilot's
activated plan and its 13 choices are untouched — this changes what is *offered*, not
what was chosen.

### It also unblocked the learner

`learned_category_bonus` reads the owner's own choices, and the owner had rejected 71
peaks. That signal could never outweigh a structural gap of 14 points on a 30-point
dimension. With the gap gone it does, so the museums now at the head are partly the
owner's own selections being reflected back — which is what learning is for.

### The residual, stated plainly

**The head of the ranking is now 12 museums tied at exactly 65.0**, among them the
Postal Museum and a Miniatures Museum. The structural bias is fixed; near-identical
candidates filling the head is not. Taipei 101 at #21 sits behind twenty museums,
several of them minor.

This is a **data limit rather than a formula bug**. Every one of those museums carries
a Wikipedia article, so `is_city_icon` is true for all of them and open data offers
nothing further to separate the National Taiwan Museum from the Postal Museum. The
out-of-scope note below already anticipated it: the signal that would separate them is
a commercial popularity measure this project has ruled out.

A per-category crowding deduction was tried first and **reverted** — see the section
above. It ranked within a category using the same biased score and so moved four of
the six target landmarks *further down*. Worth retrying now the bias is gone, but only
with the same before-and-after evidence.

### The ranker's output had no test at all

Nothing caught a world landmark sitting at #363 for months because the suite asserted
the score was *internally consistent* — total equals the dimensions minus the
deductions, which holds under any weighting — and never what the ranking actually
recommended. Not one test pinned an ordering or a score value.

`test_a_landmark_is_not_buried_by_a_richer_tag_vocabulary` is that missing test:
twenty interchangeable peaks against one prominent attraction, and the attraction must
come first. Negative-tested — with the old denominator it scores 55.3 against 62.2 and
loses.

## Explicitly out of scope

- Buying a commercial popularity signal. It would resolve this immediately and it
  is a paid provider dependency the destination interview ruled out.
- `WF-036`, the ranked candidate card grid. That is presentation and is deferred
  past the pilot. This ticket is the scoring underneath it, and fixing the grid
  would not have surfaced Taipei 101.

## Interim position for the pilot

The trip does not wait for this. The owner can select landmarks directly by name,
which sidesteps the ranking entirely, and the shortlist of what the catalogue
actually contains is in the evidence bundle. Gate 1 can pass with a
hand-picked selection; this ticket is what stops the next trip needing the same
workaround.
