---
id: WF-005
title: Define trustworthy attraction coverage and card ranking
status: closed
labels:
  - "wayfinder:prototype"
parent: WF-MAP-001
assignee: user-and-root
blocked_by:
  - WF-004
  - WF-014
---

# Define trustworthy attraction coverage and card ranking

## Question

What concrete retrieval, deduplication, ranking, diversity, Browse-all, gap-reporting, and explanation behaviour makes attraction coverage broad and trustworthy without falsely promising completeness or letting popularity dominate personal fit?

## Confirmed source boundary

Ranking begins with the same worldwide retrieval path in every city. Configured official local adapters may add or strengthen evidence, but the card set and ranking flow cannot depend on a destination-specific API being present.

## Confirmed decisions

### 2026-07-28 — Landmark visibility without popularity dominance

- Every globally prominent landmark found by the configured worldwide sources appears in a distinct `City Icons` lane so a personalized rank cannot hide it.
- A City Icon is never forced into the itinerary. The main order prioritizes group fit, experience versus effort, best-time and opening confidence, route synergy, and diversity; popularity is supporting evidence rather than the objective.
- Every discovered and deduplicated candidate remains accessible through `Browse All`, with its source coverage and retrieval gaps visible. The product does not claim that any provider returned every real-world attraction.

### 2026-07-28 — Explain every selected place that does not fit

After card selection, every chosen place must appear in a reconciliation result:

- `Fits`: scheduled without breaking confirmed thresholds.
- `Fits with tradeoff`: schedulable only by a named change such as swapping days, shortening a visit within its allowed range, starting earlier, accepting extra walking/transfers, moving a meal within its allowed window, dropping another place, accepting crowd/weather risk, or choosing a weaker viewing time.
- `Cannot currently fit`: blocked by a hard fact such as closure, impossible travel time, reservation conflict, prohibited access, or a required change outside the group's confirmed thresholds.

Nothing selected disappears silently. For each non-fitting place, show the exact conflicting item/time/threshold, the smallest feasible change, the places affected, and updated travel/walking/meal consequences. The owner can accept that tradeoff, choose a suggested swap, leave the place in an unscheduled shortlist, or remove it. A forced choice reruns the whole cross-day plan; it remains visibly invalid if physical or hard constraints still cannot be satisfied.

### 2026-07-28 — Broad baseline discovery before preference expansion

- Every city first receives the same source-neutral baseline scan across city icons, culture/history/religion, viewpoints/nature, neighborhoods and rewarding walks, local food/markets, shopping, interactive activities, seasonal/events/night, and rest/wellness.
- Discovery is also distributed across meaningful city districts or geographic cells so a popular center cannot crowd every outer area out of consideration.
- The planner unions bounded OpenStreetMap discovery, staged Google searches, user-supplied places, and any configured official local enrichment. Each source/query records what it covered; provider popularity never defines the whole catalog.
- After the baseline, editable trip tags determine which categories, subtypes, and areas receive deeper searches. A low-priority category still receives baseline coverage rather than being filtered out.
- Expansion stops when two consecutive query batches add fewer than a small configured number of meaningful unique candidates, the city/area coverage matrix has no unexplored required cells, or the provider budget limit is reached. The UI states which stop condition occurred.
- `Browse All` contains every retrieved, deduplicated candidate. A coverage panel shows source status, categories and areas searched, gaps, and the honest statement that results are broad but not exhaustive.

### 2026-07-28 — Merge duplicate records, preserve distinct experiences

- Provider records that describe the same physical experience merge into one canonical card using stable cross-source IDs where available, then normalized multilingual names, address, coordinates, category, and parent venue.
- Every merged field retains its source, retrieval time, language, confidence, and export permission. Provider-specific ratings and reviews remain separate; conflicts are displayed rather than averaged away.
- Automatic merging requires high confidence. Ambiguous matches stay separate with a `Possible duplicate` review flag so distinct places are never silently lost.
- Independently schedulable experiences inside one complex remain separate when entrance, opening time, ticket, duration, best-time, or purpose differs—for example, a mall and its observatory.
- Related child experiences share a parent arrival cluster. The optimizer charges the external journey once, then models only the internal transfer between them; each child retains its own dwell time and constraints.

### 2026-07-28 — Owner-led group weighting without averaging away harm

- Every traveller's hard constraints apply before scoring and cannot be outweighed by another traveller's preference.
- For the confirmed three-person pilot, preference fit defaults to 50% for the trip owner, 25% for the second teenager, and 25% for the mother, matching the owner-led trip-style decision.
- Those weights, ages, roles, and preference tags are stored pilot-profile values rather than ranking constants; another trip can supply a different group without code changes.
- A strong dislike, excessive effort, meal conflict, or likely comfort problem adds a worst-member penalty so the mean score cannot hide serious inconvenience to one person.
- Missing optional member preferences remain unknown and contribute no guessed likes or dislikes. The available preference weights are renormalized while known hard constraints still apply to everyone.

### 2026-07-28 — Transparent swipe learning with protected exploration

- `Must do` and `Interested` strengthen the visible place attributes that matched; `Maybe` changes them only slightly.
- `Not for trip` offers optional reason chips such as too crowded, too expensive, too tiring, wrong vibe, weak value, or already seen. A rejection without a reason applies only a small place-level penalty and never suppresses an entire category by assumption.
- Learned tag weights and inferred thresholds remain visible and editable. Each reordered card shows its main `Why shown` reasons and any important counter-signal.
- At least one in every five normal cards is an exploration card from an under-seen category, district, source, or experience style. City Icons have their own guaranteed lane and do not consume this exploration allowance.
- Swipe updates reorder only unseen cards. Previously rated cards keep their decisions and remain available for review; nothing is deleted from `Browse All`.

### 2026-07-28 — Explainable 30/20/20/10/15/5 card score

Each candidate receives a visible score out of 100 before separate penalties and feasibility status:

- `30` group preference fit, internally using the confirmed owner/member weighting.
- `20` expected experience value from uniqueness, impressive view, culture, landmark value, and source-specific quality evidence.
- `20` reward relative to walking, transfers, visit time, cost, and likely fatigue.
- `10` date, season, weather, opening-window, and best-viewing-time fit.
- `15` route and cluster compatibility with selected places and likely day areas.
- `5` evidence authority, agreement, freshness, and completeness.

Crowd mismatch, tourist-trap risk, meal disruption, redundant experiences, and member-comfort concerns appear as named deductions rather than being buried in the positive score. Provider popularity and rating volume are capped inside expected experience value and cannot dominate. Closure, impossible travel, prohibited access, and other hard conflicts determine feasibility status regardless of score; a high score cannot make an invalid place schedulable.

### 2026-07-28 — Confirmed card lanes and minimum explanation

- The main swipe queue repeats four highest-ranked unseen candidates followed by one protected exploration candidate.
- `City Icons` guarantees visible globally prominent landmarks without forcing them into the itinerary.
- `Worth It If...` collects appealing candidates whose crowd, effort, time, cost, confidence, or displacement consequence deserves an explicit choice.
- `Local Alternatives` presents comparable lower-crowd, lower-effort, or better-fitting experiences when evidence supports the comparison.
- `Browse All` retains every retrieved canonical candidate, including low-ranked and currently unworkable places, with filters and the coverage report rather than silent removal.

Every card minimally shows permitted imagery, English/Thai/local-script names, lane and feasibility state, total score and dimension breakdown, `Why shown`, pros and cons, source-specific rating and review count where licensed, an attributed example review only where permitted, expected duration, effort/access summary, best-time and opening evidence state, cost/reservation status, crowd/tourist-trap signals, and the four trip-choice actions. The score is an ordering aid rather than a guarantee or probability.

### 2026-08-22 — Reward versus effort starts with honest visit-time evidence

The pre-selection ranker cannot know walking, transfers, licensed cost, or whole-day fatigue before places are selected and routed. Its `reward_vs_effort` component therefore measures only the evidence it has: category experience per estimated visit minute. The catalogue's median reward density maps to 10/20 through `20 × density / (density + median density)`, so the score stays bounded without letting short categories swallow the ranking. The card labels this provisional result `Value for time`; `effort_state: visit_time_estimated` prevents it from being mistaken for routed effort. Source and heritage bonuses remain solely in `experience_value`, so they are not counted twice. Route, cost, and fatigue consequences remain optimizer evidence and hard comfort thresholds remain outside the card score.

## Resolution summary

Phase 1 retrieves a broad citywide union before personalizing, reports what was and was not searched, merges evidence without losing distinct experiences, and ranks every retained candidate with an explainable owner-led group score. Popularity cannot dominate, diversity is protected, all selections receive a fitting or non-fitting explanation, and the owner always sees the consequences before changing the plan.
