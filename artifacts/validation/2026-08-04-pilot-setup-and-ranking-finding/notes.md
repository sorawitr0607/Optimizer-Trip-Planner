# Completing the real setup, and what it exposed

The owner supplied the three missing facts — "Me (26) Sister (19) Mom (51), not
booked please recommend, explore first" — so the real trip's setup is now
complete and confirmed. Doing that, and then trying to answer "please
recommend", surfaced a ranking defect that gate 1 exists to find.

## Three corrections to what I reported earlier

Two of the three facts were **already in the file**:

- `planning_mode` was already `explore_first`. My earlier probe read it from
  `trip_basics`, but it sits at the snapshot's top level, so it reported `None`.
- `accommodation_status` was already `not_booked`. Same probe error.
- `confirmed` is a field on `SetupDraft`, not a key inside the frozen snapshot.
  Reading `setup["confirmed"]` returned `None` because the key never existed.

The owner's answers matched what was stored, so nothing was lost — but I told
them those fields were unset and they were not.

## What was written

Owner age 26, plus Sister (19) and Mom (51) as `member_1` and `member_2`,
confirmed. **Headcount is now 3**, which is what makes every per-person figure in
costs and split mean something.

Every pre-existing owner preference was sent back verbatim, because `save_setup`
defaults each field to empty and erases what it omits: `main_style`
`[sightseeing, nature, chill]`, `also_enjoy`
`[local_street_food, architecture, neighborhoods]`, `avoid`
`[tourist_traps, plain_long_walks]`, `comfort` `[rewarding_walks]`, description
"Landmarks", and the dates.

Three things were left null on purpose:

- **Nationality**, owner and members. It drives entry-requirement generation for
  three real people, and a guess there produces a confident prompt to verify the
  wrong country's rules.
- **Arrival and departure times.** Flight facts, not inferable.
- **Per-member tags.** Filling these would be inventing two real people's tastes.

`group_preference_weights` came out `owner 0.5, member_1 0.25, member_2 0.25` —
taste only. Artifact 023 is explicit that this must never touch money.

## The hash gate fired, exactly as designed

Saving the setup moved `setup_sha256` from `d70f21bb4826…` to `00fcfd3c59dc…`,
and `rank_candidates` immediately refused with `discovery_stale`. That is the
staleness mechanism working: discovery stores the setup hash it was built
against.

Recovery is `discover_places`, which is free (`openstreetmap:discover`, US$0.00)
and returned `verified` with 832 candidates in 0.4 s from the provider cache. It
was rehearsed on a byte-identical copy before the real file was touched, so the
refusal and its fix were both known before they mattered.

Route evidence was then refreshed through `OpenRouteServiceProvider` — also
US$0.00 — filling 8 pairs from the network and 12 from cache, 0 failed, taking
snapshots from 12 to 20. Lifetime paid spend is unchanged at **US$0.7690**.

## "Please recommend" cannot be answered yet, and the reason is worth reading

The refresh did improve the recommendation's inputs: `missing_route_count` 4 → 0
and `total_known_travel_minutes` 0 → 55. It still returns no comparison, and it
never can as things stand:

`_hotel_recommendation()` scores candidates whose `kind == "hotel_area"`. The
catalogue contains **exactly one**, and it is synthetic —
`provisional_accommodation_base`, the centroid of whatever is selected. One
candidate means no runner-up, no delta, and therefore no neighbourhood
comparison at all.

Worse, the centroid is of **four obscure mountain peaks** — Dailaokengshan,
Yuantanzikengshan, Daxiangshan, Ejiaogeshan — because those are the four places
selected on this trip. So the recommended base is the middle of four hills.

## The ranking defect

Those four peaks are not a strange manual choice. They are the **top of the
ranking**, and whoever selected them took what the app offered.

Sorted by `total_score`, the **top 50 of 832 candidates are 49 peaks and 1
park**. Where Taipei's actual landmarks sit:

| Place | Rank | Score | `group_preference_fit` |
|---|---|---|---|
| Elephant Mountain | 22 | 70.2 | 27.0 / 30 |
| Chiang Kai-shek Memorial Hall | 181 | 57.3 | 15.8 / 30 |
| Beitou Hot Spring Museum | 265 | 54.3 | 15.8 / 30 |
| National Palace Museum | 269 | 54.3 | 15.8 / 30 |
| **Taipei 101** | **363** | 51.6 | 12.8 / 30 |
| Red House, Ximending | 561 | 43.0 | 3.0 / 30 |
| *Dailaokengshan, for comparison* | *1* | *75.2* | *27.0 / 30* |

**Discovery is not at fault.** All of those are present in the catalogue — checked
directly, because `out center qt` truncation is a known way for a big city to
lose its landmarks. They are found and then buried.

**Root cause.** `group_preference_fit` is the largest dimension, 30 of 100, and
it is tag matching. A peak carries `[nature, rewarding_walks, sightseeing]` and
matches three recorded preferences for 27/30. Taipei 101 carries `[sightseeing]`
alone: 12.8/30. With 85 near-identical peaks in the catalogue, they saturate the
head of the ranking and nothing cultural can reach it.

**`is_city_icon` contributes nothing to the score.** 302 candidates carry the
flag, and in `ranking.py` it appears only in lane assignment, `pros`, and
`why_shown` — never in any score computation. So a world landmark and a nameless
hill are scored purely on tag density, and the hill wins.

**A missing tag is not the explanation.** Adding `culture`, `markets` and
`night_view` to the profile — tested on a copy — moved the top 50 from 49 peaks
to 44 peaks plus 4 museums and 1 historic site. The top six did not change.

## Deliberately not fixed

`FORMULA_WEIGHTS` is locked at 30/20/20/10/15/5 by decision, and the scorecard
states that a change altering ranking is a regression. Giving `is_city_icon`
weight, or damping near-identical candidates within a category, is a scoring
change and needs its own decision ticket. `WF-021` already called this the
biggest design gap and `WF-036` — the ranked card grid, deferred past the pilot —
was framed as presentation; this is scoring, underneath it.

## Where gate 1 stands

Setup is complete and evidence-backed. Route evidence is full. The plan
regenerates cleanly: three variants, 8 days, all valid, all `provisional`, 4
scheduled visits.

It is still not a real Taipei trip, because the selection is four hills. That is
now a decision for the owner — either pick places directly, or settle the
scoring question first. `OPENING_EVIDENCE_MISSING` is deliberately still open:
clearing it costs US$0.017 per selected place, and paying for evidence on four
peaks that are likely to be replaced would be wasted.
