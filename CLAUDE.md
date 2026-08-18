# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm --prefix web install                                             # first web run only
uv run --locked python -m api                                        # production shell on 127.0.0.1:8765
uv run --locked python scripts/check.py                              # every free Python + web gate
uv run --locked python -m unittest discover -s tests -p 'test_*.py'  # 538 tests, ~13s
uv run --locked python -m unittest tests.test_optimizer.OptimizerCoreTest.test_safe_route_and_weather_fallback_are_selected  # one test
python3 scripts/validate_regression_fixtures.py                      # fixture catalog structure
uv run --locked python scripts/run_optimizer_regressions.py          # 27 historic cases through the real optimizer
uv run --locked python -m compileall -q api travel_planner scripts tests
python3 scripts/build_project_graph.py --check                       # graph integrity (free)
python3 scripts/check_provider_access.py --self-test                 # redaction check, no network
uv run --locked python scripts/check_design_tokens.py                 # token gate: 13 accent triples, no literals, ancestors, 4.5:1 contrast
uv run --locked python scripts/check_reference_coverage.py             # structural coverage of the four reference workbooks
```

All commands run from the repo root: `tests/` imports both `travel_planner` and `scripts` as top-level
packages via cwd on `sys.path`. Python has no linter or formatter; `web/` uses ESLint and deliberately has
no formatter.

`scripts/check_provider_access.py --live-paid` makes billable Google requests. Don't run it unasked.

**To run what you just changed: restart the server, then hard-reload the browser.**
`ensure_web_build()` runs **only at startup**, and only rebuilds when a source is newer
than `web/dist/index.html` — so a server left running never picks anything up, and a tab
left open holds the old JavaScript even after it does. Six rounds of owner testing produced
reports of fixes "not working" that had been verified working minutes earlier, and every
one was this. The sidebar prints `build <timestamp>` for exactly this reason: if it does
not match the build just made, nothing about behaviour is worth discussing yet.

## Architecture

There is one interface: the local React webapp behind `api/`. The Streamlit POC that proved the core
works was deleted at slice S6 on 2026-08-04. The design decisions are locked in `.wayfinder/tickets/`
(see below) — the constraints in this section are decisions, not incidental structure.

### Dependency direction is one-way and enforced by review, not by tooling

```
web/ (React)  →  api/ (stdlib localhost HTTP)  →  travel_planner/actions.py
                                                             │
                                                             ├─ core / optimizer / ranking / setup / discovery
                                                             └─ store.py (SQLite) · providers.py (HTTP)
```

- `core.py`, `optimizer.py`, `ranking.py`, `setup.py`, `discovery.py` are the planning core: pure,
  language-neutral, no UI / SQLite / HTTP / LLM imports. Check the module docstrings — they each state
  this. Adding such an import is the single easiest way to break the design, and honouring it is why
  replacing the whole interface at S6 cost the core nothing.
- `PlannerActions` (`actions.py`) is the only coordinator: it assembles snapshots, calls the core,
  and persists results. It holds no session state and no presentation formatting.
- `PlannerActions.journey()` decides which stages are done and which is next. The webapp renders the
  blocked explanation **in place** through `<StageGate>` rather than redirecting; only `/` redirects, to
  `journey["next"]`, so a returning owner lands on the stage needing attention.
- `travel_planner/destinations.py` (country/city) and `costs.COMMON_CURRENCIES` are picker
  convenience only. Both dropdowns take a typed value, so a destination or currency absent from the
  table stays reachable — the worldwide acceptance check requires it. A city name is the geocoder
  query, so it is never localized; localizing it would let a language switch change which place is
  searched.

### Everything crossing a boundary is a frozen, hashed snapshot

`core.freeze_snapshot()` canonicalizes a mapping (sorted keys, no NaN, UTF-8) into
`FrozenSnapshot(canonical_json, sha256)`. Every domain record wraps its payload in one, and every
`store.py` read re-verifies the hash before returning. Consequences:

- `freeze_snapshot()` rejects secret-bearing keys (`api_key`, `*_api_key`, `access_token`, passport and
  booking document keys — see `FORBIDDEN_SNAPSHOT_KEYS`) anywhere in the tree. Snapshots are the place
  secrets could leak into SQLite and exports; that guard is why they can't.
- Hashes are the staleness mechanism, not timestamps: discovery stores `setup_sha256`, and ranking or
  optimization refuses to run when it no longer matches the confirmed setup.

### Pipeline: setup → discovery → ranking → optimization → activation

Each stage is gated on the previous one having a matching hash (`_current_choice_inputs`).

1. **Setup** — `setup.build_setup_payload()` normalizes owner/member preferences into a draft;
   nothing downstream runs until `confirmed`.
   Setup and the optimizer use different accommodation vocabularies — `unknown`/`not_booked`/`booked`
   versus the `unbooked` that `optimizer._hotel_recommendation()` and the frozen fixtures test for.
   `_optimizer_input` translates at the boundary; before it did, hotel-area recommendations silently
   never fired for any app-created trip.
2. **Discovery** — `providers.OpenStreetMapProvider` (Nominatim + Overpass, free) → `discovery.build_candidate_catalog()`
   A dense city takes about 34 s of Overpass time, so the query declares `[timeout:90]` and the socket
   allows 105 s; the earlier 25 s budget failed every Taipei attempt. The endpoint grants 2 concurrent
   slots and answers 504 immediately once they are spent, so a burst of retries reads as an outage that
   is really self-inflicted — space them.
   **Discovery is two Overpass requests, not one, as of `WF-048`** — indexed `["wikipedia"]` landmarks,
   then the balanced family baseline — and each is **best-effort**, failing only when both come back
   empty. As one script Tokyo returned nothing at all: the unindexed baseline scanning the clamped
   0.60-degree window exceeded `[timeout:90]` at 91 s and 93 s, and **Overpass has no partial result**,
   so it discarded the indexed half that had succeeded. Split, Tokyo yields **3082 items**. Three
   consequences. The baseline gets **`[timeout:60]`, not 90** — a browser constraint, since two requests
   run back to back and `web/src/api/client.ts` aborts an RPC at 120 s (Tokyo measured 85.8 s at 90 s
   each). There is a **3 s pause between the blocks**, because fired immediately the second came back
   `Provider HTTP 504` on the 2-slot budget — losing the baseline to a rate limit rather than a timeout,
   which hurts a *small* city most, where little carries a Wikipedia article. And a catalog missing a
   block is **`stale`, never `verified`**, applied after the cache branches so a partial payload is not
   laundered into `verified` on the next read; `coverage.incomplete_blocks` and `known_gaps` name which
   half is missing.
   **A 504 is not always a spent slot.** `overpass-api.de` balances across backends and an unhealthy one
   answers 504 in *seconds*. Measured 2026-08-08 on Singapore: both blocks 504 at 9.0 s and 9.5 s with
   both slots free, and the identical query returned 200 a minute later — an empty catalog for a fault
   that had already passed. `_attempt_block` therefore retries **once**, and only when the failure was
   **fast** (`FAST_FAILURE_SECONDS = 20`) and an HTTP 5xx. That distinction is the whole safety of it: a
   block that died at 90 s died of its own declared timeout, and asking again would spend another 90 s
   to fail identically. A `remark` is never retried — that is the query engine reporting its own
   timeout, not a gateway. `DISCOVERY_BUDGET_SECONDS = 100` is a deadline shared across both blocks and
   their retries, which is what keeps the pair inside `client.ts`'s 120 s abort however the retries
   fall. Do not raise it without moving that abort first. `out center qt` with a 500-record limit truncates in quadtile
   order, so a big city's catalog can miss its landmarks; see the walkthrough notes in
   `artifacts/validation/2026-07-29-slice5-6-evidence-notes.md`.
   normalizes and dedupes into provider-neutral candidates with an explicit status
   (`verified` / `stale` / `unavailable` / `error`). Raw responses live in the `provider_cache` table
   (7-day TTL, keyed by provider + request fingerprint); an expired entry may back a visibly `stale`
   result but never a `verified` one. Inject a fake via `PlannerActions(path, place_provider=...)` —
   that is how every test avoids the network.
3. **Ranking** — `ranking.build_ranking()` scores cards on the fixed 30/20/20/10/15/5 weights in
   `FORMULA_WEIGHTS`, with protected exploration slots and per-card explanations. Deterministic.
4. **Optimization** — `optimizer.optimize_trip()` takes one complete snapshot and returns three
   variants (`best_balance`, `relaxed`, `more_highlights`), each independently rechecked by
   `optimizer.validate_variant()` — never trust solver construction. Same input + same
   `OPTIMIZER_VERSION` must yield the same proposal, asserted via `deterministic_signature`. With no
   trip dates it returns `mode: "stay_recommendation"` instead of a timetable. At the time limit it
   returns only a labelled valid incumbent, never a partial schedule.
5. **Activation** — `activate_plan_preview()` refuses unless the preview's `input_sha256` still
   matches current choices AND the variant is `status == "ready"` with `validation.valid`. It then
   writes an immutable plan version and deletes the preview.
6. **Readiness** — `checklist.propose_items()` generates a city-independent board from setup, choices,
   and verified facts; `diff_proposal()` previews additions, removals, and deadline moves;
   `apply_checklist_proposal()` writes them, dismissing rather than deleting so nothing silently
   disappears. No provider supplies official entry rules, so a generated item stays
   `verification_needed` with no `source_url` until the owner records one — the board names what to
   verify and against which authority, and never asserts a legal conclusion. Requirement level and
   evidence state move independently, and `validate_item()` refuses a verified `required` item with no
   responsible authority type. Board items are the one mutable record type; readiness warnings are
   explicitly non-blocking (`blocks_itinerary` is always False).

**Transit routing arrived on 2026-08-05 (`WF-038`) and changes what the optimizer can plan.**
`travel_planner/transit.py` holds `TransitGraph`, the walking constants and **one** Dijkstra;
`gtfs.TransitFeed` builds one from a timetable zip and `transit.graph_from_osm()` from an
OpenStreetMap `route=subway` relation. `providers.GtfsTransitProvider` and `providers.OsmMetroProvider`
wrap them, both `mode: "transit"`, both priced at US$0.00 — priced rather than omitted, because an
unpriced operation raises. `actions.refresh_transit_routes` stores transit legs **beside** the walking
ones: the store keys a snapshot by (origin, destination, **mode**) and the optimizer takes the shortest it
holds, so short hops keep their walk. `PlannerActions._default_transit_provider` prefers a GTFS feed at
`TOURIST_GTFS_PATH` when one exists and falls back to OSM, which is weaker and says so — GTFS edges carry
`basis: "timetable"`, OSM edges `basis: "nominal"` with ride time from distance at 33 km/h and wait from
an assumed 6-minute headway. Taipei's own GTFS is **not sourced**: TDX needs a Taiwan mobile number.

Three consequences worth knowing. **A transit route is `status: "estimated"`, never `"verified"`**, and
three sites used to admit only `verified` — `actions._optimizer_input`,
`optimizer._routes_between` and `optimizer._best_inbound_route`. All three now admit `estimated` when
`allow_provisional_assumptions` is set, which only `explore_first` sets; a `ready_to_schedule` trip is
unaffected and `ROUTE_UNVERIFIED` stays fatal for it. The precedent is `_planning_fact`'s own docstring —
"a visible assumption allowed only for an Explore preview". **`walking_minutes` excludes the ride**, which
is the whole point: `maximum_walking_minutes_per_leg` measures it, so a 43-minute ride reached by a
2-minute walk passes a 25-minute cap no walk of that distance could. And **`refresh_routes` sorts pairs
nearest-first**, because the 60-per-run cap bites long before 41 places' 1640 pairs and a missing route
falls back to a pessimistic estimate — sorting by `place_id` spent 340 free calls on pairs the plan never
used and produced phantom 68-minute walks.

**Opening hours are per-day as of 2026-08-06 (`WF-041`).** `opening.common_interval` takes the overlap
across the days a place is **open** rather than refusing the moment one trip date is shut, and returns
`open_dates`; `_optimizer_input` puts those in the fact's `applies_to_dates`; `optimizer._open_on()` is
consulted by `_earliest_visit_start` and `validate_variant`. A fact without `applies_to_dates` applies
everywhere, so frozen fixtures are untouched. Before this a venue closed on one trip day was
unschedulable on **every** day — five of thirteen pilot landmarks were lost that way.

**A flight day's window holds its own logistics as of 2026-08-06 (`WF-042`).** The last day owes a fixed
suffix — `optimizer.DEPARTURE_LOGISTICS`, 45 + 45 + 90 = **180 minutes** of checkout, transfer and airport
— so `_optimizer_input` opens that day at `min("08:00", departure_time − DEPARTURE_LOGISTICS_MINUTES)`.
That constant is exported for exactly this reason and is the **one** source both sites read. Before it, a
morning flight made the departure day infeasible, and because `_greedy_baseline` accepts a placement only
when the **whole trip** builds clean, one unusable day emptied the entire plan — 13 visits to 0, every
landmark blamed on `PLAIN_WALK_THRESHOLD`. Two things follow. `_build_day` now refuses only when
`sequence or items`, so an empty day cannot veto the others. And **do not fix a window problem in the
builder**: moving `current` without moving `usable_windows` scheduled all 13 visits and then failed
`validate_variant` with `OUTSIDE_USABLE_WINDOW`, because the validator judges every item against the
snapshot's window and is meant to. `_skip_reason` is also not a measurement — it returns
`PLAIN_WALK_THRESHOLD` whenever a place was skipped and that threshold merely exists, so read
`_build_schedules`' own `hard_errors` when diagnosing. **No test set `include_operational_timeline`**
before this; it is `True` for every trip `actions.py` builds and absent from all 27 fixtures, so arrival
transfers, check-in, meals and the airport run were exercised only by the live pilot.

**Every variant gets its own time budget as of 2026-08-06 (`WF-043`).** `optimize_trip` used to compute
**one** absolute deadline and hand it to all three variants, so it was consumed in order and whichever ran
last inherited the remainder — measured on the pilot at 20.7s + 10.4s of a 30s budget, leaving
`more_highlights` already past it. It returned in 0.04s having placed **nothing**, was labelled `ready`
and `valid` because an empty schedule violates nothing, and reported
`objective_improved_or_equal_to_greedy: false` beside a `greedy_baseline` holding all 13 visits. The
deadline is now per variant, so worst case is `len(VARIANT_CONFIGS) × time_limit_seconds` and **a full
proposal takes ~52s, not ~31s** — that is the third variant doing its 21s of real work. Separately,
`_greedy_sequences` is split out of `_greedy_baseline` and `_insertion_search` **falls back to it** when
the deadline does fire: greedy sweeps every candidate and has no time limit, so it is a floor the search
can always afford, and returning worse than a schedule already in hand is never right. Two things not to
misread: `deterministic_signature` hashes the **input**, so it cannot detect a load-dependent output; and
an expired budget legitimately yields 0 visits where greedy's only schedule carries a comfort violation,
because `comfort_violations` outranks `experience_value` in the objective tuple — that ordering is
`WF-039`'s question.

**Assumed windows are batched and the cost trade is reported, not taken, as of 2026-08-07 (`WF-047`).**
`google_places:search_text` is **US$0.025 a place** and is the only paid step that scales with trip size —
40 places is US$1.00 against a US$10 cap. There is **no cheaper verified path**: Text Search takes one
query per place and cannot be batched, and the cheaper `places/{id}` Details endpoint needs a Google place
id the catalogue does not hold. So US$0.025 is the floor for evidence.

`OpenAIOpeningWindowProvider.windows()` batches the *assumption* instead — one request for up to
`BATCH_SIZE = 20` places, matched back by an **echoed integer index**, never by name, and charged to the
ledger **once per request**. Batching measured **more** accurate, which was not expected: 8 of 11 exact on
both ends against 6 of 12, and one overshoot of real closing against four.

**Do not add a cost threshold that switches automatically.** Verified and assumed are different kinds, not
different prices: an assumed fact is read only under `allow_provisional_assumptions`, so on a
`ready_to_schedule` trip a cost-triggered switch spends money on a fact the optimizer ignores.
`actions.opening_evidence_options` prices both paths and carries the cheap one's measured error rate
*beside* its price, and reports `assumed_is_usable: false` where the trip would not read it.

**A venue's own page is read for dated closures as of 2026-08-07 (`WF-044`) — and it is never a fact.**
An opening fact is a **weekly pattern**, so nothing stored can say "closed 1 January", and the trip spans
31 December and 1 January. `providers.VenueNoticeProvider` fetches the landing page and quotes any dated
visitor closure; `actions.scan_venue_notices` stores it as `place_evidence` of kind `venue_notice`.
**`_optimizer_input` does not read that kind** — there is no code path from a notice to the optimizer, so
a false one cannot delete a landmark. That is the bar the ticket set and it is met structurally, because
`WF-046` measured a model inventing 2 of 7 closures.

Two guards, both load-bearing. **The quote must appear verbatim on the fetched page** — `quotes_the_page`
forgives only whitespace, never case or punctuation, since a paraphrase is exactly what cannot be checked
against the source. **No page, no answer**: a failed fetch raises rather than letting the model recall.
Measured on the pilot: 8 sites read, 1 notice found (Huashan 1914's typhoon hours change, the genuine
one), 4 skipped for having no website, 1 unreachable — and **Sun Yat-sen reported nothing** although its
page really does contain `休館公告`, because that notice is about its website, not the hall. This reads
the landing page only; the three sites whose hours sit two hops into a government CMS are unchanged.

**An activated plan is checked against today's evidence as of 2026-08-07 (`WF-045`).** Every other gate
guards the **forward** direction — activation refuses on a stale preview, discovery and ranking on a stale
setup hash — so nothing noticed when evidence *improved* underneath a live plan. One paid opening-hours
lookup left a visit at 17:17–19:32 against real hours ending 17:30 while the stored variant still said
`validation.valid: true`, because that flag was computed at build time and never recomputed.
`actions.active_plan_drift` compares the activated version's own stored `optimizer_input` hash against the
current one, and **re-runs `validate_variant` only when it moved** — the hash says *whether*, the validator
says *what*, and gating the second on the first is what keeps this off the churn path. It **reports and
never repairs**: `plan_versions` is append-only and the owner may have printed the itinerary, so
regenerating is an offer on `/itinerary`, not a side effect of reading. `claimed_valid` and `still_valid`
are both returned so they can be seen to disagree.

**A model may supply the assumed opening window as of 2026-08-07 (`WF-046`) — and nothing more.** The app
always guessed when a place had no verified hours: `_optimizer_input` emitted a flat **09:00–21:00** for
every place on earth. So the question was never evidence versus a guess, it was *which* guess, and the
constant is the worse one — the pilot scheduled a visit at 17:17–19:32 against real hours ending 17:30 and
passed validation. Benchmarked against verified ground truth for all 13 places: the model's window ends
after real closing 5 times by **30–60 min**, the constant 6 times by **180–270 min**.

Five rules not to relax. **The status stays `assumed`** whichever guess fills it — only `source` differs
(`model_recalled_window:<model>`), so nothing is upgraded. **A place with verified hours is never asked
about.** **A window spanning 20 hours or more is discarded** (`DEGENERATE_SPAN_MINUTES`): `gpt-5.6-luna`
answered `00:00–23:59` for Huashan 1914, and a non-answer that permits *more* than the constant inverts
the reason for asking — the bar sits above sixteen hours because temples really do open 06:00–22:00. **`closed_weekdays` is not requested at all**: the same benchmark got 7 closure claims of which
**2 were invented** (Huashan 1914, Taipei Zoo), a false closure silently drops a place, and 29 December is
a Tuesday — do not add the field back without re-running the benchmark. And **`_optimizer_input` never
fetches**; it runs on every read, so the window is read from storage or the constant stands. Recall cannot
reach a *holiday* closure at all — that is `WF-044` and needs a fetch.

**A comfort tradeoff can be accepted as of 2026-08-07 (`WF-039`), and the acceptance is a number.**
`comfort_acceptances` (schema **14**) stores the *measured value* the owner agreed to per threshold
code, and `optimizer._accepts` requires `measured <= accepted_value` — so agreeing to a 27-minute
walking leg never blesses the 90-minute one a replan produces, while a tighter plan stays covered.
`optimizer.COMFORT_RULES` is the one table pairing each reason code with its violation code, metric and
threshold key; validator, soft count, `actions.comfort_tradeoffs` and the screen all read it.

Two things not to undo. **Consent must reach `_comfort_violation_count`, not just `validate_variant`** —
`comfort_violations` outranks `experience_value` in the objective tuple, so the search drops a place
rather than exceed a budget and the owner silently loses a stop; clearing only the hard error leaves
that intact. Measured on `jp-shibuya-plain-walk-overload`: 2 of 3 visits without an acceptance, **3 of 3
with one**. And **do not revive `fits_with_tradeoff`** — no call site has ever produced it (only `fits`
and `cannot_currently_fit`), and the three threshold violations carry `subject_id: None` because they
are properties of the whole variant, so routing consent through a per-place record was the wrong shape.
`has_unaccepted_tradeoff` and the `exports.py` tradeoff list stay dead for that reason; deleting them is
its own decision.

**Two names, and two sources, as of 2026-08-07.** `shared/names.ts` is still the one place
naming happens, and it now answers two questions: `placeName()` for the readable name and
`placeAltName()` for the local-script one beside it — `null` where they would be identical, so a card
never prints the same string twice. Both are shown because a traveller needs each: the local name is
what the station sign and a taxi driver use. Two sources feed it via `mergeNames()`, **OpenStreetMap
winning** because `name:en` is the name on the ground, with Wikidata's label filling gaps. That matters
because **61% of the Taipei catalogue (525 of 849) has no `name:en` at all**; 131 of those carry a QID,
and sampling 17 of them recovered a real English name for 13 — 三井物產株式會社舊廈 is "Mitsui & Co.,
Ltd. Old Building", not a translation. `WikidataSummaryProvider` gets labels in the request it was
already making (`props=sitelinks|claims|labels`), so the cost is zero, and a label arrives with the free
description rather than before it. A place with no article still yields a name: `text` can be empty while
`names` is not, and `refresh_place_summaries` stores the whole value, so nothing drops it.

Do not machine-translate the rest. The residual is places like 華江橋下自行車練習場 (a bicycle practice
ground) with no name in any free source, and inventing one is fabrication, not naming.

**The planner recommends where to stay as of 2026-08-06 (`WF-040`).** `travel_planner/areas.py` is a new
pure module and `actions.recommend_areas` the coordinator; `recommend_areas` was the **64th** allowlisted
method. **The unit is a transit station, not a hotel and not a district** — that is how the owner
searches ("it only near ximenting station"), it is the only unit whose travel time the app can measure
exactly, and district names do not generalise (Taipei's OSM addresses carry `中正區` on 278 of 832
candidates, so parsing one would be a Chinese-only regex over a third of the data). Five factors:
travel time 45, metro access 20, food 15, after-dark 10, lodging choice 10. Free — one Overpass request
for the whole shortlist via `OsmAreaAmenitiesProvider`, `openstreetmap:areas` priced at 0.0.
Four things are **never** scored and are returned on every result including an empty one: price, room
type and family capacity, cleanliness, safety. Do not fold any of them into the score — the owner's own
constraint was a family room that existed only on Airbnb, which no free source can see.

Three traps, all found by measuring rather than reasoning. **Group graph stops by name**: `STOP_TAGS`
admits platforms so relations resolve, so 437 Taipei stops are 138 stations (six for 板橋) and without
grouping the shortlist fills with duplicates. **Score travel time as a ratio against the best, not a
rank across the observed range**: the shortlisted stations all average 20-22 minutes, and rank-scaling
turned that into a 45-point gap. **Set count ceilings from data and use a log curve**: a linear scale
saturating at 30 gave every station a flat 15 of 15 when Taipei really returns 150-586. And
`TransitGraph.journey` returns `None` when nothing needs riding, so travel time takes the **better of
riding and walking** — otherwise a station across the road from a place scores as unreachable.

**Which months suit a destination is measured, not recalled, as of 2026-08-08 (`WF-048`).**
`travel_planner/climate.py` is a new pure module and `actions.travel_month_guide` the coordinator, the
**75th** allowlisted method when it landed, and a read. A model asked "when should I go to Seoul" answers instantly and
unverifiably — the failure `WF-046` measured — so this answers from Open-Meteo's archive (five whole
years of recorded daily highs, lows and precipitation, keyless, free) and Nager.Date's published public
holidays. Both are priced at **US$0.00** and recorded anyway, so call counts stay reconcilable.

Four things that are decisions rather than implementation. **Bands are relative to the destination**:
Taipei's coolest month is warmer than Seoul's warmest, so a global comfort threshold would call one city
uniformly bad and answer a question nobody asked — three best, three worst, six fair, per city.
**Every month is returned and stays selectable**, because a recommendation that removes the choice
decides for an owner who may be travelling on dates a school year sets. **A long national holiday is a
`con` and a `pro` at once** — it fills the trains *and* it is the only month the festival happens — and
neither is netted into the other, the same "report, do not decide" shape as `WF-047`'s cost options and
`WF-045`'s drift. Every verdict carries the numbers behind it, and the core emits codes with args while
the view renders them.

**Holidays come from two sources, because one was not enough.** Nager.Date's own coverage page puts
**Asia at 38%** (19 of 50) and says it depends on community contributions, so Taiwan, Thailand, Malaysia,
India and the UAE were all missing — the pilot destination among them. Google's public holiday calendars
are free, keyless, published as iCalendar and cover every one, so `_google_holidays` is the fallback and
`holiday_source` records which answered. **Turkey was never missing**: Nager has it as `Türkiye`, and
matching on the `destinations.py` spelling reported a covered country as uncovered — a wrong answer from
a name, now aliased alongside `Czechia`.

Two things about the Google feed that are load-bearing. **Observances are excluded**: it carries both
kinds and Taiwan's has 213 public holidays against 117 observances, so counting International Women's Day
would invent a crowd out of a day nobody takes off — the filter is on the feed's own `DESCRIPTION`, not
on the name. And **the calendar ids follow no derivable rule** — `en.taiwan`, `en.th`, `en.indian` and
`en.turkish` are all real while `en.tw`, `en.thailand` and `en.india` all 500 — so it is a looked-up
table, and a country in neither source stays honestly uncovered with a `month_crowding_unknown` con.

Verified on both. Seoul: best April, October, May; hardest January, February, July, catching **Seollal**
and **Chuseok**. Taipei: best January, March, November; hardest June, July, August, and February drops to
fair on a **9-day Lunar New Year run** — the single most important travel fact about Taiwan, and the one
that was invisible before.

**Two things a self-review caught that testing had not, 2026-08-08.** `travel_month_guide`'s cache-hit
branch read `held["value"]`, but `store.get_trip_evidence` **spreads the stored value at the top level**
and adds only `retrieved_at` / `expires_at` — so every cache hit raised `KeyError`. It shipped because
every read written while building it passed `force=True`, which skips the branch. Measured after the
fix: 9.08 s cold, **0.017 s warm**. And `photos_are_nearby` was written by `refresh_place_summaries` and
**read by nothing** — the flag existed, the comment claimed the screen used it, and a Commons geosearch
photograph of the next street was shown exactly like a photograph of the place. Both the deck and the
detail panel now print `photo_is_nearby` instead of the Wikipedia credit when the flag is set. The
lesson is the general one: a flag nothing renders is not a disclosure, and a branch no test enters is
not code that works.

**A city-only destination resolves its country as of 2026-08-08.** `destination.split(",")[-1]` gave
`"Taipei"` as a country for every trip made before the country/city picker — and for 49 of the fixtures
— which matched no holiday source and reported a covered country as having none.
`destinations.country_for()` looks the city up, falling back to the last segment so a country outside
the picker still reaches the holiday sources, which cover far more than it does.

**Changing setup does not cost a re-search as of 2026-08-08 (`WF-048`).** Discovery stores the setup
hash it ran against, so adding dates made the found places stale — and a stale trip cannot even record
a choice, the server refuses with 409. The advice was "discover again", which on a dense city is a
minute of Overpass and reads as losing the work. Nothing needs re-searching: `discover_places` keys the
provider cache on the **destination alone**, so with a fresh entry it rebuilds the run from disk with
**no network call** — measured at 0.05 s on a 715-place Seoul catalogue — and `place_id` is a hash of
name, coordinates and category, so every existing choice still points at the same place. `StayPlanner`
does it automatically after writing dates, and the stale-setup warning on `/places` carries a button
that does the same. Never `force_refresh` for this: that goes back to Overpass and undoes the point.

**A summary carries the provider version it was written under as of 2026-08-08 (`WF-048`).**
`cache_version` existed on every provider and `refresh_place_summaries` never consulted it, so a place
cached before Commons geosearch was added kept its empty gallery for the full 60-day TTL — cards stayed
blank after the source that would have filled them landed. The version is stored inside the value and
compared on read, so bumping it (`wikidata-summary-v2`) refetches each place once and no further.

**A trip can be deleted from the webapp as of 2026-08-08 (`WF-048`), and `delete_trip` was broken.**
The method has been on the allowlist since S1 with no control anywhere, so a trip made by mistake
stayed in the switcher for good. Building the control found the method itself unusable: `split_rows`,
`split_settled_markers` (S2) and `comfort_acceptances` (`WF-039`) all arrived after
`store.delete_trip`'s ordered table list was written and none was added, so deleting any trip that had
settled a bill or accepted a comfort tradeoff raised `FOREIGN KEY constraint failed`. Its own comment
predicted exactly this — "a future trip-scoped table fails this transaction safely until added here" —
and nothing was checking it. `test_delete_trip_removes_planning_data_but_keeps_paid_usage` already
enumerated every trip-scoped table and asserted zero rows survived, but the victim had no rows in the
three, so it counted zero of zero and passed. It now populates them, and negative-tested against the
old `store.py` it fails with the real error. **Paid usage is deliberately kept** — the charge really
happened, so it stays on the monthly total. The confirmation is type-the-name, which is the POC's own
design: `delete_trip_confirm` was already in the catalogue, the deletion is irreversible, and a button
you can hit twice by reflex is not a confirmation.

**Category variety reverses the learned bonus as of 2026-08-08 (`WF-048`).**
`ranking._learned_category_weights` only ever argued for *more* of what was already chosen: pick three
temples and temples rose, so the fourth and fifth led every lane and the deck offered "the same thing
over and over". It now saturates at `VARIETY_SATURATION = 3.0` weighted picks — unchanged below that,
which is the signal that discovers a taste — then each further pick costs `VARIETY_PENALTY = 1.5`,
bounded at `VARIETY_FLOOR = -6.0` so a category is pushed down the order but never out of reach. Five
temple picks measure −3.0 against a first museum's +2.0. The same number now argues both ways, so it
carries two explanations: `learned_from_choices` when positive, `category_already_well_covered` when
negative, and the latter is a `con` as well. Ranking already re-ran on every choice; only the direction
was missing. Five tests in `tests/test_ranking.py` pin the curve, including that a `not_for_trip`
neither teaches nor saturates.

**Discovery dedupes on name and place, not on tag, as of 2026-08-08 (`WF-048`).** Requiring an
identical `category` as well let one attraction through twice whenever OpenStreetMap disagreed with
itself about what it is — Singapore's "Jelutong Tower" arrived as `viewpoint` and as `landmark`, so the
owner was asked about it in one lane having already answered in another. An identical normalized name
within 150 m is the strong signal; the category was the weak one and it was doing the deciding.
`PlaceDeck` also filters by name, because discovery cannot merge what it cannot tell apart — a zoo
signs one exhibit twice, 200 m apart.

**Photographs have a third source as of 2026-08-08 (`WF-048`).** Wikidata `P18` and Wikipedia both need
a QID, and 61% of the Taipei catalogue has none — those places were `skipped` outright in
`refresh_place_summaries`, which is why so many cards had no picture. Wikimedia Commons **geosearch**
works from the coordinates every candidate has. It answers "what is photographed at this spot", **not**
"photographs of this place" — 300 m around Taipei 101 returns a sunset and a street in Keelung — so the
radius is small, it is used only where nothing better exists, and it is stored `photos_are_nearby:
true` so the screen can say which it is showing. *(**The radius is 400 m since 2026-08-17**, not the
150 m this paragraph was written against: 150 m is the building rather than the site, and a citadel or
a park is routinely photographed from a corner of its own grounds. That was affordable only because the
name filter had by then become much stronger — see "The photo filter got looser in one direction" below.
The Keelung street is still refused, by the name, not by the radius.)* It returns direct thumbnail URLs rather than
`Special:FilePath` redirects, so these load in one round trip instead of two. `web/src/shared/photos.ts`
is the one place a gallery is assembled, and it also reads OpenStreetMap's own `wikimedia_commons` /
`image` tag, stored as `photo_reference` since discovery was written and never read until now.

**A geosearch photograph must name the place as of 2026-08-09 (`WF-048`), or it is not shown.** Saying
which kind of picture it was turned out not to be enough: the pilot offered a city bus as the picture of
a hill, from `KKMT_470-FY_right_side_at_Yuanshan_Bus_Station`, and a caption does not undo a wrong
photograph on a card whose picture is what the swipe decision is made on. `providers.photo_depicts_place`
filters on the file's own name, which is the only evidence available about its subject and turns out to
be a good one.

**Containment alone fails, and the pilot's own case is why.** The catalogue calls that hill `Yuanshan`,
which `Yuanshan Bus Station` contains — so the name must also account for at least
`PHOTO_NAME_MIN_COVERAGE` of the file name, digits and the `File:`/extension wrapper removed. Measured:
the two bus photographs score **0.20 and 0.31** against **0.46, 0.48 and 0.75** for correct ones, which
is a gap rather than a boundary. Strip the wrapper or the rule inverts — counting `File:` and `.jpg` puts
`Daan Forest Park` at 0.39 of its own photograph.

Three costs, all measured and all accepted. **The whole name must appear, not one of its words**:
`Herbarium 植物園蠟業館` really is the Herbarium of Taipei Botanical Garden and is rejected, because
matching single words instead would accept any `Taipei` street scene for the majority of a catalogue
whose names begin with the city. *(**Softened on 2026-08-17**, and only in one direction: the same words
in **any order** now match, so `Thành cổ Điện Hải` is accepted for `Thành Điện Hải`. **Every** word must
still appear — the any-word rule this paragraph rejects is still rejected, and for the reason it gives.
The Herbarium is still lost. See "The photo filter got looser in one direction" below.)* **A verbose file name loses its place** — a title reciting country,
city and district before naming the park scores 0.14 — though such places generally carry a plainer file
too. And **a name under `PHOTO_NAME_MIN_CHARACTERS` matches nothing**: 圓山 is two characters and a
substring of 圓山站, 圓山公園 and 圓山大飯店, three different places. Verified against the live API on
the pilot: Da-an Forest Park and Jieshou Park keep correct photographs and the correct one now *leads*
where `Dongmen by night` used to, while Yuanshan, Yuanshan Park, Mantoushan, Central Art Park and the
Floriculture Experiment Center show **no photograph rather than a wrong one** — 19 of 22 summaries carry
a picture against 19 before, so the whole cost was one correct photograph and four wrong ones.

`cache_version` is bumped to `wikidata-summary-v3`, which is what makes a stored bus heal itself rather
than sit out the 60-day TTL. The screen's caption changes with it: the picture is no longer "not
necessarily of this place".

**Ranking divides by category breadth as of 2026-08-06 (`WF-037`).** `group_preference_fit` divided the
owner's matched styles by how many they *named*, which a category with more tags wins for free: `peak`
carries four tags and `attraction` two, so a nameless hill scored 27 of 30 against Taipei 101's 12.8 and
Taipei 101 ranked **363rd of 832**. It now divides by `_breadth(candidate_tags)`, capped at four.
`FORMULA_WEIGHTS` is untouched. Do not assume the ranker's ordering is tested by the old suite — it
asserted only that the score was internally consistent, which holds under any weighting, and
`test_a_landmark_is_not_buried_by_a_richer_tag_vocabulary` is the first test of what it recommends.

7. **Revision** — `revision.py` holds the whole typed operation set. An operation is a *constraint
   change* on the optimizer input, never a schedule instruction, so nothing in it can write an opening
   time, route, fare or closure; the deterministic optimizer rebuilds the plan and `consequences()`
   reports the before/after. `propose_revision` keeps exactly one pending draft and leaves the active
   plan untouched; `apply_revision` refuses unless the rebuilt variant is `ready` and valid, and
   refuses again if the active plan moved behind the preview. Applying writes a new immutable version
   plus an append-only history row; restore creates another version and deletes nothing.

8. **Free-text revision** — `interpret.py` builds the strict structured-output schema *from*
   `revision.OPERATIONS`, so the model can only choose a supported operation and may name only a
   `place_id` it was actually sent. It cannot return an opening time, route, fare or closure because no
   operation carries such a field. `build_payload` sends the plan slice and the request and nothing
   else; `_assert_clean` refuses a payload carrying travellers, documents or credentials. One call per
   request, `store: false`, one retry at most on a transient failure, and every failure names its cause
   (`missing_credentials`, `offline`, `refused`, `invalid_reply`, `rate_limited`, `api_error`) while
   leaving the plan and history untouched. Where the model omits a magnitude the app supplies a
   documented default and shows it as a visible assumption; where the value is the point of the request
   it asks one clarification instead. GenAI is off by default and everything else works without it.

Plans are append-only: `plan_versions` and `discovery_runs` carry SQLite triggers that abort UPDATE
and DELETE. Restoring an old plan creates a *new* version pointing at the old snapshot. `active_plans`
holds exactly one version per trip; `optimization_previews` holds at most one replaceable pending
preview. `SCHEMA_VERSION` (`store.py`) is stamped into `PRAGMA user_version`; a newer DB refuses to open.

### Bilingual by data, not by branching

All user-facing strings live in the eight `en`/`th` tables in `i18n/copy.json`; `travel_planner/copy.py`
reads it for the exports and React imports the same catalogue. The core emits stable codes; the views map code →
language → text. Switching language must never change ranking, scheduling, or the active plan — so
never put display text in the core or a language check in a scoring path. New user-visible string ⇒ add both
`en` and `th`. Tests enforce key parity across all tables except `CATEGORY_TEXT`'s documented derived-English
rule. Unknown stable codes render visibly as `⚠ CODE`; never prettify them into copy-looking prose.

### Tests

Python uses `unittest`; the webapp uses Vitest. No network, no paid API, no Python fixtures framework.
**`AppTest` is gone** — S6 removed the 18 tests that used it, having first moved the 14 portable
behaviours down to actions/core/exports. It was **311** at S6; it is **538** now, plus 100 Vitest cases in
`web/`.
`tests/fixtures/historic_regressions.json` encodes 20 atomic + 7 interaction failures from four real
past trips; `scripts/run_optimizer_regressions.py` replays all of them through the real optimizer.
Behavior changes to the optimizer should be expressed there.

## Owner testing, 2026-08-13/14: what it found and what it changed

Five rounds of the owner driving the real app. Everything below was reproduced against a
copy of their own database before it was touched, and the 27 historic regressions came
back **byte-identical** after every optimizer change.

**A gap the owner cannot cross is worse than a gap the app admits to.** Three of these
were dead ends — a button that promised work it did not do, a cap that could not be
reached past, a threshold blamed for a limit it did not cause — and each read as the app
refusing rather than as the app being unfinished.

### The optimizer told the truth about the wrong thing

`_skip_reason` answered `PLAIN_WALK_THRESHOLD` whenever a plain-walking threshold merely
**existed**, and `balanced_pace` always sets one. So a two-day Fukuoka trip with no room
for a fifth museum blamed the owner's walking preference, while `comfort_tradeoffs`
reported **21 minutes against a cap of 45 and nothing exceeded** — two screens
contradicting each other about one plan, and a "smallest next step" pointing at a setting
that would have changed nothing. It now reads `COMFORT_RULES`, the same table the
validator, the soft count and the tradeoff screen already share, and names a threshold
only where one was measured past. The bug was old enough to be frozen into
`ix-dali-hotel-whole-trip`, whose 60-minute cap is blamed for a plan that walks **10**;
an export test was pinning that wrong answer.

**An `estimated` route is evidence on an Explore trip, at six sites rather than three.**
`WF-038` gave `validate_variant`, `_routes_between` and `_best_inbound_route` the
`_usable_route_statuses` rule and missed `_prepare_candidates`, `_standalone_activity_route`,
`_activity_route`, `_fallback_route_compatible` and `_missing_route_edges` — the first of
which is the veto, so a place reachable only by train was thrown out before any of the
others ran. The owner's Taipei trip held **208 estimated transit legs** while reporting
`ROUTE_UNVERIFIED · collect_a_verified_route`. It admits a route the snapshot **has**; it
does not invent one, because a fabricated travel time errs optimistic and that is the one
direction this must not err in.

### Free by default, and priced where it is not

**The "Auto-Resolve" button was spending money without saying so** — `refresh_opening_hours`
at US$0.025 a place and `refresh_timezone` at US$0.005, US$0.13 on one five-place press,
from a control whose label promised only to resolve details. Both are out of both
auto-resolve chains: the very next line already assumed the hours, so buying them bought
nothing that button needed. The paid lookup stays on `/evidence` and in the verdict panel,
with its price beside it.

**`OpenMeteoTimeZoneProvider` verifies the zone for nothing.** Open-Meteo echoes the
resolved IANA zone whenever `timezone=auto` is sent, which both weather providers already
send — so the same `destination_timezone` record, same `verified` status, no key, US$0.00.
`GoogleTimeZoneProvider` is kept for anyone who wants Google's answer specifically. It
still never guesses from a country: an empty or `auto` reply raises.

A whole trip now goes from nothing to an activatable plan at **US$0.0000**.

**`refresh_routes` is asked until it is done.** It fetches at most `MAX_ROUTE_REQUESTS`
new pairs a call and eleven places need 110, so one call left the rest fatally unverified.
`web/src/shared/routeEvidence.ts` loops until nothing is outstanding or a pass fetches
nothing; measured on Osaka, one pass left 30 pairs missing and the second fetched all 30.

### The map's scale had no meaning for a single pin

`projectionOf` fits its scale to the spread of the points it is given, and one point has
no spread — the fallback was **1**, which makes the unit a radian. Measured in Nara: a
kilometre was **0.00019 units** against 139 for the same map with a second pin, a factor
of 730,000. Everything downstream reasons in real distance, so `FOCUS_KM`, `MIN_VIEW_KM`,
the detail-fetch gate, the scale note and the tile zoom were all computed against nothing.
That is exactly two screens: the first swipe card, whose shortlist is empty, and an
itinerary day with one stop. A degenerate projection now takes its scale from the
geography — `DEGENERATE_SPAN_KM` of real ground, `cos(latitude)` the only correction
Mercator needs.

**Widening the card map where the surroundings "looked empty" was tried and reverted.**
The only signal available at first paint is the basemap's major roads, and it is a bad
proxy: Nara National Museum has **zero** within 800 m because it sits inside Nara Park, so
the test called the middle of a city empty and opened its card on 8 km. The basemap is
also fetched *after* the deck first paints, so on a new trip every card widened to the
ceiling. `FOCUS_KM` is fixed and predictable; a wooded hill opens on a frame of trees and
the map zooms.

### The deck dealt one category at a time

`WF-005`'s 4:1 ranked-to-exploration rule only ever existed in `main_queue`, and the deck
defaults to **City Icons** — plain score order. Museums score alike, so on the owner's
1108-place Hong Kong catalogue City Icons opened with twelve museums and ran to **70 of
one category** unbroken. `ranking._spread_families` reorders the dealt lanes by
least-recently-used family: a reordering, never a rescoring, so the top scorer still leads
and every candidate survives. Least-recently-used rather than a window, because with two
families a window of two makes everything recent and emits runs of three. `browse_all`
keeps strict score order — it is the audit list. First twelve now cycle museum, viewpoint,
attraction, landmark; longest run 28, where the catalogue really has nothing else.

Lanes are also **dealt a page at a time** (`LANE_PAGE`), because 431 City Icons is a
catalogue rather than a shortlist. Running out of the page offers more; running out of the
lane offers the other lanes.

### Photographs, and what a card may claim

**A card is withheld until its first photograph has painted**, not merely its photo box:
the swipe decision is made on the picture, so showing the text first invites a decision on
half the evidence. A cached image can finish before React attaches `onLoad`, so the `<img>`
ref checks `complete` — without it the card hides for good.

**The summaries prefetch released its own tombstone.** `asked` existed to stop one place
being requested twice at once and was doubling as a permanent marker, so a place whose
fetch *failed* was never asked again and the manual button was the only way. Wikimedia
answers HTTP 429 on a burst and this screen prefetches in bursts.

**Commons files that name a place join its gallery** rather than only substituting for an
empty one, so a place with one P18 photograph stops being a card with one photograph.
Geosearch stays a substitute and stays flagged, because "photographed at this spot" is not
"of this place". **Wikidata's own one-line description fills `text`'s gap** — 27 of 64
stored summaries were a photograph with no words, and every one had a QID but no article —
kept in its own field because it is CC0 rather than CC BY-SA. And **a disambiguation page
is not a description**: OpenStreetMap's `wikidata` tag on Busan's 국립해양박물관 is
**Q1195337**, so the card read "The National Maritime Museum is in Greenwich, United
Kingdom."

### The end of the journey, and the things around it

`journey.next` falls back to `itinerary` when every stage is done so `/` still has
somewhere to send a returning owner — and the sidebar was reading that fallback as an
instruction, keeping a NEXT badge on a screen with nothing left to do. Done now beats next,
and `PlanReady` says so once per plan version, celebrating and listing the assumptions in
the same card.

**The readiness board is applied by activation**, additions only. `apply_checklist_proposal`
also dismisses items the proposal no longer suggests, and doing that silently would retire
something the owner was working through — dismissal stays a deliberate press. Before this,
a workbook exported without visiting `/readiness` carried no readiness at all.

**`/costs` counts what the plan will cost money for and refuses to price it.** Nothing in
this app knows what a museum entry or a metro ride costs, and a plausible number on that
screen would be indistinguishable from one the owner typed. It reads the same
`build_export_snapshot` the itinerary and both workbooks read, reports nights, meals,
entries and journeys, and seeds estimate rows at zero.

**`/split` is gated on an activated plan at the owner's request, 2026-08-14 — and this
reverses the note under `WF-030` above.** That note says split needs only a confirmed setup
because bills get paid before an itinerary is built, and a money file that refuses until
activation is unavailable during exactly the stretch of a trip when people are paying for
things. The reasoning still stands; the owner asked for the lock anyway. Reverting is one
word in `web/src/shared/stages.ts`.

### Right is `must_do` and up is `interested`, 2026-08-14

Right was `interested` and up was `maybe`, with `maybe` paired against `skip` as "the two
ways of not answering yet" — a tidy symmetry that spent the deck's two strongest gestures
on its second- and weakest answers, while `must_do`, the answer the whole plan is built
around, was reachable only from the button row. At the owner's asking right is now the
strongest keep and up is the ordinary one; `maybe` keeps its button, and left and down are
unchanged.

**Four things move together or they stop agreeing about what a swipe does**: `intentOf`,
the arrow keys, the in-hand label, and the legend under the card. The legend is the
contract — it is the only place the owner is told — so the label copy was renamed rather
than reused: `drop_to_keep` ("Keep") meant right, and leaving it in place would have put
"Keep" beside a button that says "Interested". It is `drop_to_must_do` and
`drop_to_interested` now, named for what they name.

Verified through the keyboard against a copy, which reaches the same `act()` the gesture
does: ArrowRight wrote **`must_do` 0 → 1** and ArrowUp wrote **`interested` 9 → 10** in
`candidate_choices`, both with the flight playing. The pointer path cannot be driven this
way — the gesture uses `setPointerCapture`, and a synthetic `PointerEvent` carries no real
pointer to capture — which is the same reason `deck.test.tsx` was built around the buttons.

## `overpass-api.de` was unreachable from the owner's network, 2026-08-17

"No places came back", with `<urlopen error [Errno 61] Connection refused>` twice. That
error is worth reading carefully: a busy public endpoint answers 504 or times out, and
**ECONNREFUSED means no connection was opened at all**. Measured from the owner's own
machine: DNS resolved every host, and `nominatim.openstreetmap.org` (200),
`www.wikidata.org` (301) and `example.com` (200) all answered normally, while
`overpass-api.de` and three of its mirrors did not connect. The internet was fine; that
one service was not reachable from that network.

**And it was intermittent.** The same host answered **200** from the same machine a few
hours later, and a full discovery ran through the app — 715 places for Seoul in 56s. So
this is not a standing block to be routed around permanently; it is a service that
sometimes cannot be reached from here, which is exactly the case a fallback list is worth
having and exactly the case where "wait a minute and press again" is *sometimes* right.
Both messages stay, chosen by what the provider actually said.

Three consequences.

**`TOURIST_OVERPASS_URL` takes a comma-separated list**, tried in order, and **only a
connection failure moves to the next one**. A 5xx or a `remark` is the endpoint being
busy, which `_attempt_block` already handles — asking a second public server the same
heavy question because the first was under load is the burst this file already warns
about, aimed at a stranger. `overpass_url` stays the first entry, because the cache
descriptor keys on it and a fingerprint that moved with a fallback would invalidate
every cached run.

**No mirror is added as a default.** These are third parties with their own
jurisdictions and privacy terms, and which of them a trip's data goes to is the owner's
decision, not a default someone inherits from a bug report. The capability is in the
code; the choice is in the environment.

**The empty-catalogue advice now depends on which failure it was.** "Wait a minute, then
press Find places again" is right for a busy gateway and actively wrong for a host this
network cannot open a connection to, where pressing again fails identically forever. The
two are told apart by the provider's own words, since only one of them can be.

Worth knowing for the next time a mirror is evaluated: **`overpass.osm.ch` is reachable
and useless** — it serves a Switzerland-only extract, so it answers 200 with zero
elements for anywhere else, which looks exactly like a city having nothing in it.

## The courtesy pause is not overhead, and three attempts have now proved it

Profiled at **44.8s of a 74.3s refresh** — sixty percent of the wait is `pause_seconds`,
a flat 0.4s in front of every Wikimedia request. Every attempt to reclaim it made the run
slower:

| Attempt | Result |
|---|---|
| Pause only between retries | 41.6s → **63.3s**, 38 → 97 requests |
| Adaptive from zero, decay 0.6 | 42.6s → **71.6s**, **49** rate-limits in one run |
| Adaptive from zero, decay 0.98 | 42.6s → **73.9s**, **47** rate-limits in one run |

Both adaptive schemes fail for the same reason, and it is not tuning — slowing the decay
from 0.6 to 0.98 changed nothing because the damage was already done in the first second.
**A pause that starts at zero has to discover the limit by exceeding it**, and Wikimedia
does not answer one 429 and forgive: it keeps refusing for a stretch, so a burst is
punished for far longer than it lasted. The flat pause is not paying per request; it is
buying the limiter never being triggered, and that is worth more than it costs.

Do not try a fourth time without a way to learn the limit *without* crossing it. The
lever that remains is asking less, not waiting less.

## Every hint linked to the thing it describes, 2026-08-18

Worked through the remaining forms case by case rather than mechanically, because a
`aria-describedby` pointing at the wrong paragraph makes a screen reader worse, not
better. Section prose stays unlinked — Readiness's "your board is current" and Costs's
plan-shape summary describe a *screen*, not a field.

What was linked, and why each one is the field's own text rather than text near it:

- **Trips**: the trip-name hint to the name box; the destination hint to **both** the
  country and city selects, since it explains the pair; and the "choose a destination
  first" note to the **disabled button**, because a screen reader landing on a disabled
  control is otherwise told only that it is disabled.
- **Split**: the cardholder hint to its select; the allocation hint to the **fieldset**
  rather than to each amount, since it is about how the numbers relate — repeated per
  participant it would be read aloud once per person.
- **Costs**: the categories hint to the box that adds one; the plan-shape hint to the
  button it describes.
- **Revise**: `ai_cost` and `ai_disclosure` to the **opt-in checkbox**. S5 requires the
  price and the transmitted-data boundary to be *visible* before that control is enabled,
  and visible is not announced — a screen-reader user reached the checkbox with both
  sitting unattached below it. `ai_disabled_note` joins the list only while it is
  rendered, because describing an absent element points at nothing.
- **Evidence**: every **price** to the button that spends it. This app's rule is that a
  paid action names its price before it is pressed; an unattached `evidence-cost` span is
  visible and silent.
- **Stay**: the base hint to the address box, plus the empty-field note while it applies.

Verified in a browser across all eight surfaces and all six setup steps: **13 links, zero
broken ids**. That check matters more than the count — a dangling `aria-describedby` is
the one way this change could have made things worse than leaving them alone.

## The same practice across every other form, 2026-08-18

Six containers each carried their own near-identical `input { background; border; radius;
padding }` block — `.trip-form`, `.money-form`, `.setup-fields`, `.evidence-card`,
`.readiness-item-controls`, `.revise-pick` — so the states were written **once**, against
`.app-shell`, rather than copied into six places that would then drift. That is the
article's own instruction: incorporate the styles into a design system for scalability.
Scoped to the shell so the landing page, which has its own palette by decision, is
untouched, and with no `:focus-visible` of its own because `tokens.css` owns the house
ring.

Verified on all five stage forms — costs, split, readiness, revise, evidence — that the
error border and the disabled cursor now actually apply.

**`.money-form` was multi-column for the same reason the setup wizard was.**
`repeat(auto-fit, minmax(160px, 1fr))`, built the same way and measuring the same fault. A
row of short money fields is precisely the case the single-column guidance is about: the
eye should run down one list, not across four. Both money forms now measure **544px, one
column**, with the amount field at 100px rather than a full column's width.

**Required was invisible on the money forms too.** Four fields across Costs and Split
carried the `required` attribute with nothing on screen saying so, which means the message
arrives only after a refused submit — the article asks for it before. `Required` lives in
`money.tsx`, which both pages already share, because two copies of a convention is how two
forms come to disagree about it. Split's amount also gained `inputMode="decimal"`; Costs
already had it, which is what made the omission visible.

## Input-field practice applied to the setup wizard, 2026-08-18

Worked from Eleken's "46 Input Field Design Examples" tip by tip. Most of it the form
already did — visible labels rather than placeholder-only, one column, fieldset grouping,
a step indicator, 44px touch targets, consistent borders. Five things it did not:

**~~There was no focus ring anywhere in the stylesheet.~~ There was, in `tokens.css`,
and I grepped only `shell.css`.** The house rule is
`:focus-visible { outline: 2.5px solid var(--color-purple) }`. A 2px accent ring was
briefly added for the setup fields alone, which would have made one screen ring
differently from every other — the "consistent styles across all fields" rule broken by
the change meant to honour it. Removed. Found by reading the *computed* style in a
browser rather than the stylesheet, which is the only way it could have been found.

**Every hint was unattached.** Eleven inputs, sixteen labels, and not one
`aria-describedby` — a sighted reader could see that the grey line under a field belonged
to it and nobody else could. The hints now carry ids and the fields point at them.

**Required was marked in punctuation only.** A bare `" *"` in the legend says nothing to a
screen reader and nothing to anyone who has not learned the convention, so the word
`(required)` is there too and the asterisk is `aria-hidden`.

**A field as wide as its column, not as its content.** An age is three characters and was
given a full column, which reads as a field expecting something longer. Numerics cap at
`8ch`, dates and times at `18ch`.

**And the form was six columns wide, which I first recorded as already satisfying the
single-column guidance.** It does not: `repeat(auto-fit, minmax(170px, 1fr))` measured
**six columns at 1440px**, which is the two-dimensional scan that guidance exists to
prevent. One column now, capped at `34rem` — the cap matters as much as the count, since a
single column stretched across 1000px is its own problem. The error is worth recording
because of how it happened: I read the rule, agreed the form met it, and did not measure
until asked whether I had actually checked.

**Reading the images, not just the text, is what found the last of it.** The article's
anatomy list names the states a field should have — *inactive, hover, disabled,
validation, error, focused* — and only appears in a screenshot's surrounding bullet list.
Of those six the setup form had **one**. Hover, disabled and an `aria-invalid` error
border are now real, verified on a live number field: inactive `rgb(58,58,58)`, error
`rgb(238,107,107)`, disabled greyed with `not-allowed`, 80px wide.

The before/after screenshot carries the clearest single lesson in the piece: the redesigned
question states its own rule as helper text — *"Select one or more answers – required"* —
directly under the label, rather than leaving the requirement to be discovered on submit.

**Read the page, do not read a summary of it.** Two `WebFetch` calls returned a small
model's précis, and both were faithful — but only opening the article in a browser and
reading it top to bottom surfaced the two checks that were still outstanding: no
horizontal scroll on mobile, and no sticky or fixed element that could sit over a field
with the keyboard open. Both measured clean at 390px. Also worth stating plainly: **the
article does not contain 46 tips.** The count is a title claim about screenshots; the
actual guidance is ten best-practice paragraphs and five layout points.

**And the one that actually mattered: the error was on the wrong screen.** "Choose at
least one Main style" is raised by **Confirm**, which lives on the review step — while the
tags are on step 3. So the owner was told to fix something that was not on screen, which
is the article's "place the message next to the problematic field" failing in a way no
amount of moving the message can fix. A refused confirm now **takes the owner to step 3**,
where the message, `aria-invalid` on the fieldset and the tags themselves are together;
picking a style clears it immediately.

Verified end to end on a fresh trip, because `save_setup` erases what it omits and this
form is the one place that could break silently: confirm with nothing picked lands on step
3 with the error beside the field, picking a style clears both the error and the
`aria-invalid`, and the walk through to Confirm then stores all five `trip_basics` fields,
`confirmed: true`, and moves the journey to `places`.

**Not applied, deliberately.** Password toggles and input masking (no passwords here);
autocomplete on ages and dates (a browser's saved addresses are not this trip's answers,
and `autoCorrect` on a place name is the "overly aggressive auto-correct" the article warns
about); and green success ticks per field, which on a form where every field is optional
would mark "you typed something" as an achievement.

## The back-and-forth day was a drawing fault, not a planning one

Reported as the plan sending the owner back and forth. It was not: measured across every
day with enough stops to test, a 2-opt pass over the visit order found **20 metres** of
improvement on 5.4 km — the order given is already essentially the shortest round of its
own stops.

The line was drawn wrong. A route is stored once per *ordered* pair, so the shape for B→A
is reused when the day walks A→B, and its points were used **in their stored order** —
the leg ran backwards, the next leg began where this one should have ended, and the day
came out as a zig-zag between places next door to each other. A leg matched in reverse now
has its points reversed. Verified in a browser: every junction joins at a gap of **0**,
and the ring closes at **0** now that the walk home is drawn too.

**Worth generalising: "the plan is wrong" and "the picture of the plan is wrong" look
identical on screen.** Measuring the order before touching the solver is what kept a
correct optimizer from being "fixed".

## There is no further free source of photographs, measured three ways

Asked again for more sources, with licensing explicitly set aside. The answer is not a
licence problem and not a filter problem — the pictures do not exist in the free web:

| Source | Yield on the owner's blanks |
|---|---|
| **Openverse** (CC aggregator, Flickr + more) | **0 of 6** probed |
| Commons geosearch at 500 m, name filter **off** | 6 of 61, all one city, all of *neighbouring* buildings |
| Commons category, words rule, 400 m radius | already shipped, a handful recovered |
| The venue's own `og:` preview | already shipped, 3 recovered |

The remaining blanks are a Da Nang tailor, a Chengdu 礼堂 — literally the generic word
"auditorium" — a mini-golf, a martial arts club. Dropping the name filter to reach the six
would put a photograph of the building next door on the card, which is the failure already
measured twice (a Michigan store for a Da Nang shop, Lego for `Jurassic World`).

**The honest lever left is the paid one**, already on the card at its price. Some of these
places are also arguably discovery noise rather than places to visit, which is a different
question from photographs.

## Where a photograph comes from, in order

Assembled across five rounds and written down in five places, so here it is once. Each
step runs only when the ones above it found nothing, except where noted.

1. **Wikidata image properties** — `P18` first because it is the curated one, then
   `P8592`, `P5252`, `P4291`, `P3451`, `P2716`. All mean "an image of this item", so none
   can put another place's photograph on a card.
2. **The article's own images**, from whichever Wikipedia exists, cheapest language first.
3. **The subject's Commons category** (`P373`) — a file in a category is about that
   category's subject by definition, so this needs neither coordinates nor a name match.
   Skipped when a curated `P18` was already found: the round trip would only append to a
   gallery the better picture already leads.
4. **OpenStreetMap's own `wikimedia_commons` / `image` tag**, read by
   `web/src/shared/photos.ts` when the gallery is assembled.
5. **Commons geosearch**, 400 m, every file gated by `photo_depicts_place`. Flagged
   `photos_are_nearby`, because "photographed at this spot" is not "of this place".
6. **Commons search by name**, gated by the same filter *and* by coordinates — the file
   must carry a location and sit within `named_radius_metres`. The coordinate half is not
   redundant: dropping it admitted a Michigan store for a Da Nang shop.
7. **The venue's own `og:image` / `og:description`**, flagged `photo_from_own_site`.

And then nothing. A place past step 7 has no free photograph, the card says so, shows
where the place is, and offers Google's at its price. Roughly two thirds of a real
catalogue's blanks are shops and gyms with no encyclopedic presence anywhere — that
number is not a bug to be driven to zero.

## A place's own website is the last free source, and the only honest "anywhere" one

The owner set the licensing question aside on 2026-08-17 — this is a local, single-user
app — so the wider web was in scope. It is still almost all ruled out, on **relevance**
rather than licence: a general image search for `Ancient Egypt` returns a museum object
from another continent, which is not a hypothetical but the exact failure measured when a
looser Commons rule briefly admitted a Horus canister for a Singapore attraction.

`VenueNoticeProvider.preview()` reads the venue's own `og:image` and `og:description` —
tags a site publishes *specifically* so other software can show a picture and a sentence
for it, and which are about that site by construction. It runs only after every free
encyclopedic source has said nothing, and it is never fatal: no website, an unreachable
page or a page without the tags leaves the blank card that was already there.

Measured across the owner's three catalogues, 38 blanks: **4 recovered**, three of them
through this path — a martial arts club, KidZania, and a gym. Those are precisely the
places with no Wikidata entry, no article and nothing on Commons, which no radius and no
name rule could ever have reached. `cache_version` is `wikidata-summary-v11`.

## Summary fetching: batched, and the profile says that is not where the time is

Asked to make summaries faster by batching, so the first thing was to measure. Ten
Singapore places, refreshed with `force`:

| | |
|---|---|
| **Deliberate courtesy pauses** | **44.8s** |
| Network | 28.5s over 70 requests |
| Everything else | 1.0s |

**Sixty percent of the wait is the app choosing to wait.** `pause_seconds = 0.4` sits in
front of every Wikimedia request because a burst gets HTTP 429 — CLAUDE.md already records
eight of thirteen places failing without it. So the only lever that matters is **the
number of requests**, and each one costs its pause *plus* its network time.

`wbgetentities` takes fifty ids at a time and was being asked once per place:
`WikidataSummaryProvider.entities()` now asks once for the batch, **22 requests → 1**.
`summary()` takes an optional prefetched entity and is otherwise unchanged; it is passed
only when one exists, so every provider and every test fake still works against the old
one-argument signature, and a failed batch simply leaves each place to ask for itself.
The Commons category listing also no longer runs for a place that already has a curated
`P18` — a round trip spent appending to a gallery the better picture already led.

**And the honest part: wall-clock did not improve.** A/B on two identical fresh copies —
without batching 42.6s / 38 requests / 8 of 10 with a photo; with batching 47.2s / 42
requests / **the same** 8 of 10. Twenty-one Wikidata requests disappear and about
twenty-five Commons and Wikipedia ones take their place, because a place whose Wikidata
call used to 429 out was counted `failed` and skipped everything downstream. The old
speed was partly failure.

It is kept because twenty-one fewer requests to a free public service is right on its own
terms, and this app's own notice promises low volume. It is not kept because it is faster.

**Two attempts to shorten the pause both made it worse, and that is the lesson.** Moving
it to fire only between retries: 41.6s → **63.3s**, 38 → 97 requests, because Commons
answered 429 and the retries cost far more than the pauses had. The pause is not overhead
sitting next to the work; it is what stops the work from being rejected. Anything faster
has to come from asking less, or from an adaptive backoff that earns the pause on a real
429 — and given two measured backfires, that deserves its own change and its own testing
rather than being folded into this one.

## A card was released when its bytes arrived, not when its picture could be drawn

Three rounds of "the skeleton stops after the first two cards, and I can swipe a card that
has not finished loading". Instrumentation said the opposite every time — no frame ever
showed a card with `complete: false` — and instrumentation was answering the wrong
question. **`complete` and `onLoad` both mean the response finished**; the image is
decoded afterwards, which `decoding="async"` explicitly asks for off the main thread. So
the card was released with its bytes in hand and its picture still a blank box, and the
owner was right: they were deciding on nothing.

`markPainted()` waits for `element.decode()`, which resolves when the frame can actually
be drawn. It releases the card on rejection too — a broken image, or an `src` that changed
mid-flight — because a card held forever is worse than one released early.

**The lesson is about the measurement, not the fix.** "No bad frames" was true and
irrelevant: the probe tested the same property the code tested, so it could only ever
confirm it. When a report survives three rounds of being measured away, the measurement is
the thing to doubt.

## Ranking a stay area without a metro

`recommend_areas` refused outright where a destination has no published metro, on the
ground that "an area ranking with no travel times is a list of amenity counts pretending
to be advice". That reasoning holds only while the alternative is *inventing* a travel
time. Walking distance is not invented: it comes from coordinates every candidate already
has, and `TransitGraph.journey` has always taken the better of riding and walking anyway —
so this is that same measure with the riding removed, and the two cannot disagree about
what a minute means.

The fallback ranks **the neighbourhoods around the places the owner chose**, not stations,
and says so: every area is named for one of their own places and the report carries
`AREA_TIMES_ARE_WALKING_ONLY`. Measured across three live trips that previously refused:
Singapore 12 areas (30-minute medians), Da Nang 7, Shanghai 4 — where all three had
returned `no_transit_graph_for_areas`.

## The wrong control was nearest, again

Two reports, one cause. "Why does *Assume hours, measure routes, build the plan — free*
appear again" — because it renders whenever activation is refused, including when the
refusal is a **comfort budget**, which fetching routes cannot possibly move. And "I didn't
see the accept button" — because the only accept lived in a panel further up the page.

The auto-resolve offer is now suppressed when every violation is an `UNAPPROVED_` one, and
an **Accept N minutes and rebuild** button sits at the refusal itself. It agrees to the
*measured* value, never the rule: `_accepts` requires `measured <= accepted_value`, so a
later replan that walks further is refused again rather than blessed. It rebuilds
afterwards, because the plan is judged at build time and agreeing to a figure otherwise
appears to do nothing.

Measured on all three live trips, each of which could not reach an itinerary:

| Trip | Before | Accepted | After |
|---|---|---|---|
| Shanghai | `unavailable`, invalid | 64 min (limit 60) | `provisional`, **valid** |
| Da Nang | `unavailable`, invalid | 112 min (limit 35) | `provisional`, **valid** |
| Singapore | `unavailable`, invalid | 40 min (limit 35) | `provisional`, **valid** |

## Photographs: the free sources are close to exhausted for these catalogues

`nearby_radius_metres` goes 150 → **400**. The radius is a proxy for "was this
photographed at the place", and 150 m is the *building* rather than the site — a citadel,
park or temple complex is routinely photographed from a corner of its own grounds.
Widening is safe only because `photo_depicts_place` still has to accept the file name.

It is worth being plain about the yield: across three live catalogues this recovered
**one** further photograph (Shanghai's Site of the First Congress). The remaining blanks
are tailors, mini-golf, a martial arts club, a Marks & Spencer — places with no
encyclopedic presence anywhere free. The paid button on the card is the honest answer for
those, and it is already there.

## The photo filter got looser in one direction and was pushed back in the other

Two changes to `photo_depicts_place`, one kept and one reverted the same hour. Worth
recording together, because the second is the more useful lesson.

**Kept: the same words, in any order.** Containment required the whole normalised name as
one contiguous run, so a single inserted word broke it. Measured on the owner's Da Nang
catalogue: Commons holds **nine** files within 150 m of Thành Điện Hải, filed as
`Thành cổ Điện Hải` — one word in the middle — and every one was rejected. A parenthetical
alias did the same to `Trieu Chau (Chaozhou) Assembly Hall`, which Commons files without
the alias. Every word must appear, which is not the any-word rule this filter exists to
avoid, and the coverage test still applies to their sum. Trieu Chau goes **0 → 2**.

**Reverted: accepting a file with no coordinates.** The argument looked sound — this
search is global, its known failure is *Central Park in Vinnytsya* answering
`Central Art Park`, and the words rule rejects all eight of those on the name alone, so
the coordinate check appeared to be standing in for a name test that could finally do the
job. Run against the owner's real catalogues it admitted, in **one pass**: a 1906 heraldic
engraving for `Dragon's Head`, a **Shopko store in Standish, Michigan** for a Da Nang
shop, **Lego** sets for `Jurassic World`, and a Horus canister for `Ancient Egypt`. Four
wrong photographs out of five new matches.

The words rule only helps where a name has words worth matching. For a name that is
*entirely* generic, every word matches a subject on the other side of the world, and
**locality is the only thing left that can tell them apart**. The cost stands and is
accepted: the citadel keeps a blank card, because a blank card is recoverable — the owner
can buy the photograph — and a confidently wrong one is not.

**The general point: a guard that looks redundant against the case it was written for may
be carrying a different case entirely.** The only way that showed up was running it over
real catalogues instead of the example in the comment.

## Two of the three "remaining" were not bugs

**The skeleton stops after the first two cards** because by then there is nothing to wait
for. Instrumented across eight distinct cards and several hundred samples: not one frame
showed a card displayed with an unloaded image, and cards three onward arrive
`complete: true, naturalWidth: 960` — the gallery prefetch has already fetched them. The
absence of a skeleton is the prefetch working. `act()` refuses while pending regardless,
so a decision cannot land on a card the owner never saw whatever route it arrives by.

**"Plan from the centre of my places" did unlock the plan** — `journey()` returns
`optimize` unblocked and `next` immediately after it is pressed. What it did not do was
say so or take the owner anywhere, which is indistinguishable from nothing happening. It
navigates to `/optimize` now, and picking a ranked area leaves a standing "Build the plan
→" instead, because that one is not obviously terminal: an owner may want to compare two
areas before moving on.

## A finished plan was being withheld over five minutes of walking

"After drop and rebuild, still can't create plan." Measured on the owner's Singapore
trip: **all 14 chosen places scheduled**, `continuous_timeline: true`,
`selected_reconciled_count: 14`, and one hard violation —
`UNAPPROVED_PLAIN_WALK_THRESHOLD`, **40 minutes measured against a 35-minute
preference**. Nothing was wrong with the plan. It exceeded a comfort budget by five
minutes and was therefore `unavailable`.

`WF-039` built the way out and it was already on the screen, above the variant picker:
`ComfortTradeoffs` lets the owner accept the *measured value*. What was missing was any
statement that it was **the reason**. The screen said "cannot activate" and the only
control near the failure was "drop this place" — so the owner dropped places to fix a
problem no place was causing, and the next plan failed the same way.

The optimize screen now says so where the refusal happens, and the test is the server's
own: `COMFORT_RULES` pairs every reason with an `UNAPPROVED_` violation code, so that
prefix means "the owner may agree to this" rather than "the plan is broken". When every
hard violation carries it, the message names the visit count, points at the panel, and
says explicitly that dropping a place is not required.

**The general shape, and it has now cost two rounds: a refusal that does not name its own
cause sends the owner to whichever control is nearest.**

## A three-hour buffer that was not a hole

The trailing gap on a day now has its own reason, `day_ends_free`. On the same Singapore
plan every chosen place was scheduled and the day still ran to 21:15, so the remainder
was printed as a 165-minute `BUFFER` and read as the planner having failed to fill it.
Same row and the same honest length — only the name changes, because "evening free,
everything you chose for today is done" is what it actually is. No frozen fixture sets
`include_operational_timeline`, so this branch is unreachable from the 27 regressions,
which stay byte-identical.

## A decision cannot land on a card that has not arrived

The buttons are disabled and the drag surface is out of layout while a card is pending,
and `act()` now refuses as well. The owner reported swiping cards that had not finished
loading, and a decision recorded against a place they never saw is the one outcome that
must not slip through a gap between three guards — a keypress, or a gesture already in
flight when the card changed, reaches that function directly.

## The pictures are not free, which is a different answer from "there are none"

"The pic is everywhere, find it" was investigated properly rather than answered again.
For every place that comes up blank, the **free** sources hold nothing — and the searches
that look like near-misses are not:

- `Taro Quad Bikes` → Commons returns *Report and findings of the Commission on the
  Abolition of G…* and an 18th-century philosophy volume.
- `Puri Agung Peliatan` → *Permen No. 137 Tahun 2017 - Bali.pdf*.
- `Patung Dewa Indra` → a statue in a different village.

The name filter is right to refuse all of them, and 19 of Bali's 34 have **no Wikidata
entry at all**, so there is no `P18`, no article and no category to read. The photographs
the owner has seen are on Google and TripAdvisor: **licensed sources, not absent ones.**

So the card no longer says "no photograph exists in the free sources" and stop. It says no
*free* source has one, shows where the place is, and offers the one path that can produce
a picture — `enrich_place_card`, priced on the button's face. That is the app's standing
rule applied where the gap is actually felt: a paid control names its price before it is
pressed, and it is never a card's primary action, because a card's primary action is a
decision about the place rather than a purchase.

## Tapping through a gallery outran its prefetch

Only **one** photo ahead was warmed, so a second tap raced the prefetch and every tap
after it waited on a cold fetch — "tap to advance loading so long". The whole gallery of
the card in front is warmed now, plus the next card's lead image. Widening it became both
cheaper to justify and more necessary at once: reading a subject's Commons category means
galleries are six deep where they used to be one or two.

**A direct `upload.wikimedia.org/thumb/...` URL would halve each image's latency and
cannot be built.** Every URL here is a `Special:FilePath` redirect, which costs a round
trip before any bytes move, and the obvious fix — computing the MD5 thumbnail path — was
tried and **measured as HTTP 400: "Use thumbnail sizes listed on…"**, because Wikimedia
restricts widths to its own set and 640 is not in it. Warming early is the way to pay
that cost off screen instead.

## The build stamp, and the bug that made the last round unreadable

Six rounds produced reports of fixes "not working" that had been verified working minutes
earlier, and every one turned out to be a browser holding an older bundle. `python -m api`
rebuilds **only at startup**, and only when a source is newer than `dist/index.html`, so a
server left running never picks anything up — and a tab left open holds the old JavaScript
even after it does. Neither side could tell which build was on screen, so each round spent
its first hour re-diagnosing something already fixed.

The sidebar now prints `build <timestamp>`, stamped by `vite.config.ts`. **If it does not
match the build that was just made, nothing about behaviour is worth discussing yet.** The
recipe is: stop the server, `uv run --locked python -m api`, hard-reload the browser.

**And one of those reports was real, from my own edit the round before.** `firstCardWait`
— which holds the discovery skeleton until the first card is ready — was written as a
plain condition, so it was true for *every* card while the shortlist was still empty. That
flipped `busy` on each swipe, hiding and re-showing the whole workspace and replacing the
deck's own placeholder with the discovery block. Two of the reports in the next round were
that single line: "the places page is blinking" and "some cards show no skeleton". It is
latched now, in state set from the deck's own callback rather than a ref, because a ref
read during render is neither allowed by the lint rules nor correct.

The lesson worth keeping: **a fix that makes a condition true more often needs asking
"how often, and on what"** — this one was scoped to "after a discovery" and read as
"after the first card", and those differ by every card in the deck.

## The deck and the panel beside it are framed differently, and the card nudges

Two identically-framed cards side by side made "which of these do the buttons belong to"
a question to work out rather than to see. The deck takes a **2px accent border**; the
detail panel keeps the plain 1px house border. Written as the `border` shorthand, not as
`border-color`/`border-width` longhands above it — a later `border:` in the same rule
resets both, which is exactly what the first attempt did.

**And an untouched card nudges after five seconds.** The deck already carries a grip bar,
two coloured edges and a four-way legend, and the gesture was still reported as
undiscovered — every one of those is a thing to *read*, and nobody reads a card they are
looking at. Movement is the only hint that needs no reading. A tilt-and-return rather
than a shake, because a shake is what a rejected password field does and this is an
invitation. Three times per card and then it stops: whoever has not taken the hint by the
third has understood and declined it. Behind `prefers-reduced-motion`, and never during a
capture.

**The inline transform had to go for it to work at all.** `.place-deck-drag` always
carried `style.transform`, written as an identity while at rest — and an inline style
beats a stylesheet animation, so the class would go on, the keyframes would be correct,
and nothing would move. It is now omitted entirely when the card is not offset.

## A place's own Commons category is the source that needs no heuristic

"No photograph exists in the free sources" was shown for places that plainly have
photographs. Measured across the owner's catalogues on 2026-08-17, the blanks are three
different problems and only one of them was ours:

- **Bali, 19 of 34 blank** — small businesses (a quad-bike operator, a water park) with
  **no Wikidata entry at all**. No *encyclopedic* source holds a picture of them.
  *(Overtaken a day later: a place like this often publishes its own `og:image`, and
  reading that recovered three of them. "Nothing to fix" was true of Wikidata and Commons
  and wrong about the web — see "A place's own website is the last free source" below.)*
- **Tsiancheng Park, Zhaoyang Tea Park** — a Commons search returns **zero files**. The
  photograph does not exist to be found.
- **Chanchushan** — carries `P373 = "Toad Mountain"` and no image property, so Commons
  held six photographs under a name nothing in the pipeline was looking at.

A file in a Commons **category** is about that category's subject by definition, so it
needs neither coordinates nor a name match — it is the one source that can answer for a
place whose photographs exist but are not geotagged. Chanchushan goes **0 → 6**, and they
are genuinely of the hill. `cache_version` is `wikidata-summary-v9`.

**One gap is left open deliberately.** Taipei City Hakka Cultural Park has two Commons
files whose titles contain its full name, no `P373`, and **no coordinates on either
file** — and a file with no location is refused outright, which is the guard that stops
six photographs of *Central Park in Vinnytsya* landing on a card for `Central Art Park`.
Relaxing it for a strong name match is plausible (containment already rejects the
Vinnytsya case) but it trades a measured safety property for a heuristic, and that is its
own decision rather than something to slip into a fix for something else.

## A tab left open across a rebuild runs the old app, and that cost several rounds

`Failed to fetch dynamically imported module: .../OptimizePage-D8dLZlyq.js`, reported from
the owner's browser. Every build gives each chunk a new content hash and Vite empties
`dist`, so the file a **running** page was told to fetch stops existing. Two symptoms, and
the second is far worse than the first: a navigation to a not-yet-loaded route dies with
that error, and every screen the tab had already loaded keeps running the old code —
looking like the app, answering like the app, and missing whatever was just fixed.

That is the explanation for a run of "this still is not fixed" reports on changes that
were verified working in a browser minutes earlier. **A rejected fix now warrants asking
which build was looked at before the fix is applied again.**

`lazyPage()` treats a failed dynamic import as "this page is out of date" and reloads,
which fetches a fresh `index.html` — already served `no-cache` — and with it the current
chunk names. **Once per session**, recorded in `sessionStorage`: if the second attempt
fails too, the chunk is genuinely missing and the error belongs on screen rather than in a
reload loop. The catch resolves a promise that never settles, because rendering an error
behind an in-flight reload flashes a failure the owner is about to leave anyway.

This does not detect the silently-stale tab that never navigates. A reload after a rebuild
is still the answer there, and a build-version endpoint is the obvious next step if it
keeps happening.

## The visible card is fetched on its own

It led the look-ahead batch — first in the list, but in the *same* request — so the card on
screen was withheld until all seven places had been through Wikidata, Wikipedia and
Commons. One slow neighbour held up the only card anyone was looking at, which is what
"some swipe cards load so long" was. A separate mutation, because `isPending` is per
mutation and sharing one would put them back in each other's way.

**And the "Find places" skeleton now holds until the first card is genuinely ready.** The
wait used to end twice: the discovery skeleton cleared, the workspace appeared, and the
deck immediately showed its own placeholder — two loading states back to back for one
press, which reads as the app finishing and then stalling. Scoped to
`discover.isSuccess` and an empty shortlist, so it covers the press it was asked for and
never a revisit, where the busy block's "searching for places" wording would be a lie.

**"Detailed list" is gone**, at the owner's asking. It was a second way to do the deck's
job that had to be kept in step with it — a hidden choice row, its own paging constant,
its own empty state — and the full catalogue is still readable in the report below, which
is what it was actually used for. `?view=list` still resolves for a bookmark; nothing in
the app offers it.

## The deck's decisions are disabled while a card arrives

The card is withheld until its first photograph has painted, for a reason — the swipe
decision is made on the picture. A live row of decision buttons above the placeholder
undoes that: it invites answering before there is anything to answer about, and the answer
lands on whichever place the deck settles on. All five are disabled while the card is
pending, **Skip included**, because skip is a decision about *this* card rather than a way
past the wait.

Verified on a genuinely cold deck for the first time, which needed a trip whose summaries
had never been fetched: 715 places discovered live for Seoul, then the deck opened with
all five buttons disabled, no detail card, and the loading line cycling "Getting the
pictures ready…" → "Just a moment for this one…" → "Loading this place…". Every earlier
round had to take those three on trust because every photograph on the test trips was
already cached.

## The wizard's steps start at the top too

The shell's scroll reset keys on `pathname`, and the setup wizard's six steps are
component state rather than routes — so it could not see that move at all, and pressing
"Save & continue" at the foot of a long step left the next one scrolled past its own
question. `SetupPage` resets on its own step change, **above the three loading and error
returns** and keyed on `chosenStep` rather than on the derived `step`, because hooks must
run in the same order on every render and that value is not computed until after them.
An effect rather than a line in the handler, because the indicator also walks backwards
and both directions want the same thing.

## Every route change starts at the top

A client-side navigation keeps the browser's scroll offset, because as far as the browser
is concerned nothing was navigated. Leaving a long itinerary half way down and pressing
"Costs" therefore opened Costs half way down, on a heading the owner never saw. Keyed on
`pathname` only, deliberately: the day stepper and the map/timeline toggle both change
the search string many times on one screen, and yanking the page to the top under someone
reading a timetable is worse than the problem being fixed. An in-page `#anchor` is left
alone for the same reason.

## Owner testing, 2026-08-17 (second round)

Three of these were reported as *still* broken, and in each case the first fix had been
aimed one element short of the thing being complained about. Worth stating as a rule: when
a fix is rejected, find out what was actually looked at before applying the same fix
harder.

**The detail card, not its explanations block.** Hiding `.place-explanations` while a card
loaded left the name, score, photograph and every button on screen describing a place the
owner could not see. It is the whole `.place-card` now.

**The loading line changes over time, not per card.** Derived from the place id it was
stable — deliberately, so a screenshot is repeatable — but a fixed sentence during a wait
is exactly what does not look alive. The id now picks the *starting* line and a timer
advances it, so two cards still do not open on the same sentence and nothing is random.

**`/stay` was locked correctly and still not in the workflow.** The route was gated and
sat in the right sidebar slot, but `journey()` had no `stay` stage — so `next` went
straight from places to optimize and the app never sent anyone there. The order existed in
the sidebar and nowhere else. It is a real stage now, done once the owner has **decided**:
either naming a base or pressing "Plan from the centre of my places", which is
`accept_provisional_base`, the **90th** allowlisted method. Without that second answer an
owner who books nothing would have `next` stuck on this stage for the rest of the trip.

That button is also the answer to a screen that could refuse and offer nothing:
`recommend_areas` needs a transit graph, and a city whose metro OpenStreetMap does not
carry returns `no_transit_graph_for_areas`. The centre of the chosen places is what the
planner would use anyway.

### A place with no photograph gets a map, not a grey box

Six places on the Sapporo catalogue have no free photograph anywhere — no image property,
no OpenStreetMap tag, nothing past the Commons name filter, and two of them stone
monuments whose two-character names that filter refuses by design. There is nothing to
find, and inventing one is fabrication. So the card draws **where the place is** and says
that is what it is doing. A swipe decision made on a location is worse than one made on a
photograph and much better than one made on an empty rectangle.

### "No remaining time capacity" is true and was useless

It is the honest residual — those places fit nothing wrong, there are simply more of them
than the days hold — and the optimizer cannot invent a day, because the dates are the
owner's. Saying it without saying *that* was a dead end. It now names how many places and
how many days, states that nothing is wrong with them, and links to where the dates are
changed.

### Smaller things from the same round

**"What this draft assumed" folds behind its own summary** with a ⚠ and a count: the same
list every time until something changes, sitting between the draft and the variants the
owner opened the page to read. A `<details>`, so the triangle, the keyboard behaviour and
the announced expanded state come from the platform.

**The date picker disappears while "Use these dates" runs.** Pace, month grid, guide and
chosen window are inputs to a decision already sent; leaving them up invites changing an
answer nothing is reading, and buries the progress line. `hidden`, not unmounted, so a
failed build returns the picker exactly as it was.

**The lane alternatives got the weight of a control.** At the end of a page of cards
"look at a different list" is one of only two things to do, and it read as disabled chrome
beside the primary.

**The itinerary's day stepper says "Previous day" / "Next day"** with the date beside it,
and sits directly above the map it steers rather than at the top of the page. **The day's
trace autoplays on arrival**, keyed on the date — the map is one component reused across
days, so without a key it would trace the first day and sit still for the other six. That
key is adjusted during render rather than in an effect: React sanctions that shape for
state derived from a changed prop, and the lint rule rejects the effect version as a
cascading render.

**The itinerary names the other five screens and says what each is for.** It is the page
an owner lands on for the rest of the trip, and the sidebar lists those five without ever
saying what any of them does.

## The hero carries three things, 2026-08-18

Read Courey Wong's "How To Design A Killer Landing Page" in a browser, top to bottom. Its
argument is **single focus** — a landing page has one thing it wants the visitor to do,
and "only give the visitor 2 options: buy or leave" — and its hero is exactly three
elements: headline, supporting image, call to action.

Ours carried six. Measured at 1280x800 before the change: headline at 138, lead at 214,
**call to action at 323**, then a four-item feature list and two notes running to 702 —
**306px of other content above the fold, all of it below the one button**. The thing the
page asks anybody to do was the middle of the view rather than its end.

The list and the notes are the article's Section 2 and its trust copy, so they now sit in
a `landing-solutions` band **below** the fold, where a visitor who wants more arrives
looking for exactly them. The call to action is now the last thing above the fold at 458,
with a 54-pixel sliver of the next band showing — enough to say there is more, not enough
to compete. Verified afterwards that the one action still works: it scrolls the form into
view and focuses its first control.

The band keeps the hero's own ground rather than being restyled. Its contents are written
light-on-ink and the working half below is light, so moving them onto that surface would
have made them unreadable; continuing the gradient means scrolling reveals more of one
page instead of crossing a seam into another.

**What was left alone, deliberately.** The headline already follows the article's own
framework — big idea, end result, transformation — and its sub-headline already describes
what you get, which is what the article asks a sub-headline to do. Rewriting the owner's
product copy was not what "apply this to the hero" asked for, and the structure was the
part that was actually wrong.

## The hero is the night map now, 2026-08-18

Repainted at the owner's asking. The golden-hour palette sampled from two travel sites for
`WF-048` is gone; the hero takes its colours from **this app's own dark `--map-*` block** —
graphite ground, water deeper and bluer, the road network lighter than what it runs
through, metro in transit blue. The hero is therefore the same world as the maps the
planner draws, which is a better reason for a palette than a trend, and it reads as modern
because it is cool and high-contrast rather than warm and nostalgic.

**The tokens were renamed, not just repainted.** `--landing-amber` holding a blue and
`--landing-sand` holding a pale slate would have been names that contradicted their
values — the failure this file objects to everywhere else. They are `--landing-route`,
`--landing-route-soft` and `--landing-mark`, named for their job. Every pairing was
measured before it was written: the tightest is haze on the raised surface at **6.3:1**,
and the CTA reads **7.4:1** both ways.

## A full flow on a fresh trip, 2026-08-18

Porto, five days, empty database, driven through the browser from the landing page to the
downloads. What held, and the two things that did not.

**Held.** Setup refused a confirm with no main style and **took the owner to step 3**,
where the error, the `aria-invalid` fieldset and the tags are together. All eight
downstream stages were locked with named reasons. Discovery returned in ~30s. Across ~30
swipes and a lane change — the exact repro that produced three rounds of reports —
**not one card was displayed with an unloaded image**, and the end-of-page panel offered
both "show more" and the four other lanes. "Build the plan" went to Where to stay rather
than past it; ranking produced 12 areas; picking one adopted it and moved on.
`accept_route_estimates` took the plan from **6 unfit / 9 visits to 0 unfit / 15 visits**,
and those estimates are still derived at read time rather than stored, so nothing
fabricated is persisted as though a router said it. Activation, the itinerary map, and all
three exports — the 6-sheet workbook, the 4-sheet money file, a 9-event calendar — were
valid.

**The wait lied.** The optimize screen paced its lines at `expectSeconds={52}` and its note
promised "about a minute". Measured end to end on this trip: **210 seconds**. The 52 is the
*optimizer*; the free button collects routes first, and `collectRouteEvidence` loops
`refresh_routes` before the solver ever starts. The lines cycled four times against a note
that was wrong by a factor of four. Both corrected, and the note now points at the elapsed
counter, which was the only honest thing on screen.

**"Day 1 of 6" counted an evening that is not a trip day.** Dates stored 04-10 → 04-14; the
plan runs 04-09 → 04-14, because the evening before departure is a real planned day —
pack, documents, alarm, 19:00–20:30. Numbering it as a trip day reads as an off-by-one to
anyone who knows when their trip starts; I read it that way myself before checking. It is
named now — "The evening before you go" — and the numbering counts the trip's own days, so
04-10 is **Day 1 of 5**.

**Two false alarms of my own, both the same mistake.** I reported the accept-estimate
control and the activate button as missing; both were present, and my DOM query was scoped
to the wrong section. Scoping a search to where you expect the answer is how you get a
confident wrong one — the same shape as grepping one stylesheet and concluding the app had
no focus ring.

## Owner testing, 2026-08-17: twelve reports

### Nearest-first starved the places that most needed a route

Three `must_do` places on the owner's Sapporo trip — Hitsujigaoka, Asahiyama Memorial
Park and Mount Moiwa, all hills on the city's edge — were dropped `ROUTE_UNVERIFIED`,
and the screen's advice was "press Refresh routes until every pair is measured". That
advice **does not terminate**. Measured: 98 of 182 pairs stored and **not one touching
those three**. `refresh_routes` sorts nearest-first and caps at 60 a run, so the outliers
were last in a queue that was refilled from the front every time.

A place with no route at all is unschedulable; a place with twenty gains nothing from a
twenty-first. So **served-ness now outranks distance**, with nearest-first still ordering
within each group — the relevance win that sort was written for is untouched, and it
converges, because a starved place joins the second group as soon as it has one route.
After the change all 60 of the next batch touch those three, where it was zero.

### A five-hour lunch break

`12:30–17:30 · BUFFER · 300 min · meal_window` on the arrival day. The gap was real —
nothing could be scheduled — but `meal_window` names the wrong cause, and reads as the
planner having decided on a five-hour lunch. Beyond `MEAL_WAIT_MAX_MINUTES` (90) a wait
before a meal is labelled `free_time_or_rest`: **an honest label, not a shorter row**. The
gap is still shown at its real length, because a row's reason is what the owner reads to
decide whether it is a problem. The 27 regressions are byte-identical, so no fixture ever
held a meal wait that long.

### One garden, two word orders

OpenStreetMap held "Botanical Garden of Hokkaido University" and "Hokkaido University
Botanical Garden" **147 m apart**, and the owner was asked about the same garden twice.
`_name_key` strips spaces, so it bakes the word order in and cannot see a permutation.
`_word_key` sorts the words, drops the noise words that are exactly what differs between
two spellings of one name, and is consulted **only** inside the same 150 m radius. It
returns empty for a single word and for scripts that do not space their words — 焼山 is
one token — and an empty key never matches, or every unspaced name in a block would
collapse into one place. The greenhouse, which has a real extra word, stays separate.

### The deck could never reach its own ending

"I think the deck shows more than 20" was right. `main_queue` excludes decided places
**server-side**, every decision invalidates the ranking, and so each refetch shifted the
list up and `slice(0, shown)` handed back twenty fresh cards — forever. The end-of-deck
panel, the one offering the other lanes, was effectively unreachable. The window now
shrinks by what has been decided out of it, and the panel offers **both** "more of this
lane" and the other lanes rather than one or the other, since a 431-card lane never runs
out and the alternatives were therefore invisible.

**Derived during render, not seeded in an effect.** The first attempt held the page in
state and filled it from `useEffect`, which left the first paint — and every static
render — with no cards at all. Six tests caught it immediately.

### "Trace the day" was never going to run

Two independent reasons, either fatal. SMIL's `begin` defaults to `0s` on the **document**
timeline, so by the time anyone presses the button that instant is minutes past and
`fill="freeze"` parks the traveller on the last stop. And, measured in this browser,
`svg.getCurrentTime()` stayed at **0** three seconds in — the SVG timeline does not
advance at all, so no `begin` would have helped. It is `getPointAtLength` plus
`requestAnimationFrame` now: plain DOM, starts when asked, stoppable, and dependent on no
animation engine. The dot is placed at the first stop **before** the first frame, so a
throttled `requestAnimationFrame` cannot leave a circle with no `cx` sitting at the origin
— off the map, and indistinguishable from the button doing nothing.

### A fourth stroke measured in map units, and the gate that could not see it

`.plan-map-route` — the itinerary's day line — carried `stroke-width: 2` with no
`vector-effect`, so at the map's 178x ceiling it was drawn as a band hundreds of pixels
wide. That is the **fourth** occurrence of this one mistake, after the label halo, the
one-way arrows and the pin number.

The reason it shipped is the more useful finding: `check_design_tokens.py` enforced the
rule against a **hand-written tuple of six selectors**, so it silently stopped covering
anything added after it was written — the exact failure it exists to prevent. It now
*finds* every map rule declaring a stroke width. That immediately caught three more,
of which two are deliberate: the one-way arrows ride a carrier line whose stroke width
**is** the marker's unit, and the small literal there is what stopped the ~170px arrows.
Those say so in the stylesheet with `map-units-deliberate`, so the exception lives next
to its reason.

### The paid button was hidden by somebody else's fetch

"Some places can't click Load live gallery" — measured on Sapporo City Museum, which has
both a summary row and a photograph. The control was gated on the bare
`fetchSummary.isPending`, which is the **prefetch** for cards further down the deck, so
any in-flight batch replaced the open card's button with "Loading…". It never recovered
for a place the summaries query holds nothing for, because `!summaries.data?.[id]` stays
true and every future prefetch hid it again. **Second time the shared prefetch has been
mistaken for the card's own request**; the first blanked the whole workspace on every
swipe.

### Six places with no picture, and why

All six carried a QID, no `P18`, no OpenStreetMap image tag, and nothing that passed the
Commons name filter — two of them stone monuments (碑) whose names are two characters,
which `PHOTO_NAME_MIN_CHARACTERS` refuses by design. Wikidata records a picture under
more properties than `P18`, and every one of them means "an image of this item", so none
can put another place's photograph on a card: aerial view, winter view, panoramic view,
plan and collage are now read in that order after the curated `P18`. `cache_version` goes
to `wikidata-summary-v8` so a place that came up blank is asked once more. Places with no
free photograph anywhere still exist, and are still shown without one rather than with
someone else's.

### Smaller things from the same round

**Where to stay is locked until the owner presses "Build the plan"**, at their asking:
ranking neighbourhoods against a shortlist still being swiped ranks them against the wrong
shortlist. It borrows the `optimize` gate key, which carries exactly that predicate.
**"Rank areas to stay" is a primary button** and every ranked area offers **"Stay around
here"**, which writes the station's own coordinates straight to the base — no geocoder
between a known point and the same point, which is the round-trip that produced a hotel
286 km upstate. `confirm_accommodation_base` takes optional coordinates for it.

**The detail panel waits for the card.** It describes the card in front, so showing it
while the card is still arriving is the "decide on half the evidence" problem the card
gate exists to prevent, one element over. **The loading line varies by card**, chosen from
the place id rather than at random — varied to read, and stable to photograph, since
`Math.random()` there would be the self-drifting-baseline bug again.

**"Before you build" is hidden while the optimize runs**: it asks a question whose answer
has already been taken, and leaving it up invites moving a radio the run is already past.

**The itinerary's day picker is prev/next, sticky, above the map.** A trip is a sequence
and the move you make ninety-nine times in a hundred is "the next day"; a select turned
that into open, find, aim, click, and never showed which day you were about to get. The
date is on the control, and the ends disable rather than wrap.

### "Where to stay" is its own route, and the count went nine to ten

Artifact 028 decided nine stage routes. There are **ten** as of 2026-08-14, at the owner's
asking: the area ranking was a section under the deck on `/places`, where it competed with
several hundred cards and was reported as a section with no visible output, and the
accommodation base was one card among five on `/evidence`, which is where evidence is
*checked* rather than where a decision is made. The two halves of one question — which
neighbourhood, then which address — were never on screen together. `/stay` owns both, and
the old homes are removed rather than kept: two places to set a base is the duplication
this consolidation exists to end. It gates on `places`, not on `evidence`, because
choosing a neighbourhood is what you do *before* buying opening hours for the places in it.

**The page's first card states what the planner is using right now**, which nothing did
before. Without a confirmed base the optimizer plans from the centre of the chosen places
— a reasonable default that was completely invisible, and the reason a hotel 286 km away
could survive to plan an itinerary around itself.

**`get_accommodation_base` now returns `used_by_planner`.** The page printed the stored
address under "what the planner is using now", which the implausible-base guard had
already made untrue — the same class of false statement the guard exists to stop. The
verdict is computed on the server from the same helper `_optimizer_input` uses, and
deliberately not re-derived on the screen: a second copy of that distance rule in
TypeScript is exactly how the two would come to disagree. A discarded base is shown as
what is on file, with a line saying the plan is not built from it.

### Accommodation status is two answers, not three

`unknown` is gone at the owner's asking. It was never a third planning outcome:
`_optimizer_input` collapses everything that is not `booked` into `unbooked`, so `unknown`
planned identically to `not_booked` while asking the owner to draw a distinction the
planner then discarded. **A question whose answers do not differ is a question worth
deleting.**

A draft still holding it is **folded, not refused** — `setup.normalise_accommodation_status`
maps it to `not_booked` before validation. That matters because a setup is re-validated on
every save, so rejecting the old value would strand any trip holding it behind a form that
can no longer be submitted. Both directions are tested, including that a genuinely
unsupported status is still refused.

### The loading card was small in the wrong dimension

The placeholder shrank but the deck did not: `.place-deck-drag.pending` was
`visibility: hidden`, which keeps an element's box, so the card still occupied its full
height — **measured at 1526px on a real deck** — and the overlay centred its text some 900px
down, below the fold. `display: none` takes it out of layout, so the deck is as tall as the
**200px** placeholder and the loading state is genuinely small, with its text at the top.
The card returning at full height is a jump, and a deliberate one: it is the answer to
"make the loading card smaller", and it happens once per card.

**A wrong diagnosis on the way there, worth recording.** `.place-deck` looked to be missing
`position: relative`, which would have made the overlay resolve against the viewport — a
tidy explanation for a full-screen loading state. It was wrong: the rule already existed
340 lines further down the same stylesheet. `shell.css` has now yielded three duplicated or
split rules in one session (`.places-map-reset`, `.evidence-verdict.settled`, and this),
so **grep the whole file before concluding a rule is absent** — the second copy is the more
likely explanation, and acting on the first reading adds a fourth duplicate.

### A kept card flies to the shortlist, 2026-08-14

The swipe wrote the choice and the card vanished; a number in the corner changed. Those
two events are only connected if you happen to be watching both, so the deck read as
cards disappearing rather than as a shortlist being built. `shared/flyToShortlist.ts`
cuts a ghost from the card's own photograph and animates it to the shortlist tab —
add-to-cart motion, at the owner's asking — and the tab scales once as it lands, so the
number is *seen* to change rather than found to have changed.

It is decoration and behaves like it: it never blocks, never delays the decision, and
does nothing at all when anything it needs is missing — no tab on screen, no Web
Animations API, a zero-sized rect. Two suppressions, both standing rules rather than
taste: motion sits behind `prefers-reduced-motion: no-preference`, and a **capture runs
with none of it**, because an element mid-flight is a different image on every run for no
code reason — the drift the summaries prefetch and the first-visit tour were already
fixed for.

Three details. The ghost is appended to `<body>`, not to the deck, because a card leaving
its own container would be clipped by it, and it is `position: fixed` because both rects
come from `getBoundingClientRect`, which is viewport-relative. The path **arcs** — it
rises before it falls — since a straight line reads as a UI element being moved where an
arc reads as something being tossed into a container. And a **cancelled** animation still
removes its ghost, or navigating mid-flight leaves an orphan pinned over the next screen.

**The condition is written as "not the rejection", not as a list of the keeps.** The list
was wrong on its first draft: `must_do` is a keep, it is dispatched only from the button
row rather than through `act()`, and naming the keeps one by one silently omitted the
strongest one. `not_for_trip` is the single action that does not join the shortlist.

Measured in a browser: 31 frames, the ghost shrinking 320px → 51px and travelling from
the card at y≈1098 to the tab at y≈100, with the counter moving on each keep. There is no
unit test — `web/`'s Vitest environment is `node`, and this is entirely DOM, so testing it
would mean adding jsdom as a dependency for one decorative function.

### A message describing a partial success was shown for a total failure, 2026-08-14

`/places`'s "Where to stay" panel printed **"Nearby counts are unavailable right now, so
only travel time and metro access are scored"** on *every* error — a sentence about a
result that half-worked, rendered where there was no result at all. So a call that died
outright (`no_transit_graph_for_areas`, reproduced when Overpass was unreachable) read as
a call that succeeded quietly, and the owner's report was the honest reading of it: "what
is this section do, didn't see the output". The refusal's own words are shown now, and
they already had bilingual copy — the screen simply never asked for them. An empty
ranking with no reason also says so rather than rendering an empty `<ol>`.

**The general shape: an error branch that hardcodes one message is a lie the moment a
second failure exists.** Render the code the server sent.

### A hotel 286 km from the trip is not a hotel, 2026-08-14

`confirm_accommodation_base` defaults its query to `f"{destination} Station"`, and for a
trip named `New York, United States` the geocoder answered with a station in **upstate New
York** — 42.796, −76.119, which is **286 km from all eleven places the owner had chosen**.
It was stored as a booked base, so `hotel_recommendation.basis` read
`booked_accommodation` and the whole itinerary was built around it.

Two halves, because either alone leaves owners broken. **The call is out of both
auto-resolve chains** — neither `/optimize` nor `/evidence` invents a base from a
destination string any more. And `_optimizer_input` **drops a base further than
`ACCOMMODATION_BASE_TOO_FAR_KM` (150) from the nearest chosen place**, naming
`ACCOMMODATION_BASE_IMPLAUSIBLE` in `capability_gaps`, so trips that *already* hold a bad
one are rescued rather than needing the owner to notice. Verified on a copy of the owner's
own trip: the base becomes the selected-place centroid at 40.767, −73.973 — Manhattan —
**0.9 to 3.0 km** from the places it serves. The guard is negative-tested: a real hotel
inside the city is untouched.

### The loading text was not stuck; it had run out of things to say

`Thinking` advanced its lines every 2.6 s, so six lines covered **16 seconds of a
52-second optimize** and then held for the remaining 36 — reported as the text being
stuck. It now takes an `expectSeconds` and paces the lines across the real duration, and
carries an **elapsed-seconds counter**, which is the one thing actually known: the server
reports no milestones, so this claims none, but a number that ticks can never read as a
hang. Measured on a real build: line 1 at 4 s, line 4 at 30 s.

**And the build button cannot be pressed twice.** `isPending` flips on the *next* render,
so two clicks inside one frame both passed the disabled check and started two 52-second
optimizes, the second replacing the first's result — which looked exactly like the wait
being twice as long as advertised. A ref set synchronously in `mutationFn` is what closes
that window; the disabled attribute alone cannot.

### One action, and a choice about how to pay for it, 2026-08-14

`/optimize` offered **two buttons** — assume the hours free, or buy them — and hid its own
named action, "Build three plan options", whenever that question was open. So the screen's
one button disappeared exactly when the owner went looking for it, and working out that
*either* button built the plan meant reading both labels. At the owner's asking the choice
is now a **radio group** (free pre-selected, and it stays pre-selected — a control that
spends money is never the default) and "Build three plan options" is the only press. The
paid path is buy-**then**-build: the purchase is only ever made in order to build, so
leaving the owner to press again was the "back and forth" report in miniature.

"More evidence controls" is gone from that panel for the same reason: a third link beside
a decision is a third thing to weigh, and Check trip facts is in the sidebar.

**"Use these dates" now says what it does.** It saves the dates, rebuilds discovery from
cache and generates a preview — three things and about a minute — and the label named only
the first, so it read as saving a date and then appeared to hang.

### Two rules that could not be seen, and one duplicated block that hid them

**`.places-map-reset` was declared twice, verbatim**, so the two copies could have drifted
apart with nothing to notice. It sat at `top: 30px`, across the map's own `<h4>` at y
11–35 — the reported overlap. There is no free corner to move it to: the compass owns the
top-right, and the bottom holds the scale note and the **ODbL attribution, which must stay
legible** — moving it there would have been a worse overlap than the one being fixed. So
it is in the flow beside the trace control now. A control that cannot overlap is one that
is not overlaid.

**The sidebar paid its padding twice.** The section frames put a second border inside the
pane, so `padding: 18px` plus the frame plus each link's own padding read as a deep gutter
down the left of every stage link — 30px from pane edge to text. Now 8 + 4 + 6 = 18. The
`.sidebar` rule also carried **two `gap` declarations**, only the second of which ever
applied.

**The loading card is a small block that says "Loading this place…"**, not a full-height
grey copy of the card it waits for: the placeholder still overlays at the card's height so
nothing jumps when the photograph lands, but a full-size grey rectangle reads as a card
that failed rather than one still arriving.

### Two tests passed only because the machine had a network

`test_ported_behaviours.SetupConfirmationTest` built its `PlannerActions` with **no fake
place provider**, so the two tests that discover places reached Overpass — against a suite
whose stated rule is no network and no paid API. They passed for as long as the connection
held and failed as `discovery_empty` the moment it did not. Injecting the fake the suite
already has fixed both and took the file from 11.9 s to 1.2 s. **A test that needs a socket
is a test that reports the network, not the code.**

### The catalogue of codes was half empty

**Twenty-six optimizer codes had no copy entry**, so the "consequence / smallest next step"
column — the one that says what to do — printed `⚠ collect_a_verified_route` and
`⚠ OPERATIONAL_DETAILS_REQUIRE_CONFIRMATION` verbatim in both languages.
`OPTIMIZER_CODE_TEXT` went 95 → 137 entries each. `⚠ CODE` remains the correct rendering
for a code that genuinely has no entry; it was never meant to be the common case.

### Taiwan's GTFS feed is sourced

`WF-038` parked TDX registration as disproportionate. The owner registered anyway. The
national feed is **7.1 GB extracted**, of which `fare_leg_rules.txt` and `fare_products.txt`
are 6.5 GB the reader never opens, and 6,198,885 `stop_times` rows of which **161,612
(2.6%) are metro** — TRTC, NTMC, TYMC, TMRT and KRTC. `data/gtfs/transit.zip` is the metro
subset at **3.7 MB**, loading in under a second, and 捷運西門站 → 捷運台北101 resolves to a
25-minute journey with one transfer at `basis: "timetable"`. `/gtfs/` is gitignored: it is
gigabytes of someone else's data and not this repository's to redistribute.

### External audit, 2026-08-14: nine of eleven findings closed

An outside audit scored the app 7.8/10 and raised eleven confirmed problems. Nine are
fixed; two are recorded below as open, because both are larger than the audit's framing
and doing them badly would be worse than not doing them.

**A rule that is declared is not a rule that applies.** `min-height: 44px` had been on
`select` at the phone breakpoint since the touch-target work and had *never done
anything*: measured in WebKit at 390px, a native `<select>` stays **23px** under both a
44px `min-height` and 12px of padding, and only an explicit `height` moves it. The rule
looked right, passed review and shipped a control a thumb cannot hit. Twelve of them on
`/readiness` alone. This is the general lesson worth keeping: for natively-rendered form
controls, assert the **computed box**, not the declared CSS.

**Exactly one element may claim to be the current page**, and three did — the brand, the
real stage and "New trip slot", because `/trips` matches every `/trips/:id/*` descendant
without `end`. On a fresh Places route it was **eight**, because a locked stage pointed at
`#`, which resolves to whatever page you are on: every locked stage announced itself as a
link to the page already open. Locked stages are now `<span aria-disabled>` rather than
links, `navSemantics.test.tsx` pins the count at one, and it is negative-tested.

**A failed discovery said "Discovery result saved" beside "No places came back"**, over a
raw `<urlopen error [Errno 61] Connection refused>`, with three equivalent retry buttons —
the app congratulating itself for storing a failure, in developer vocabulary, at its main
conversion point. A run that returns nothing no longer flashes success, and the provider's
own words are folded behind a disclosure rather than being the headline.

**A wrong address reached React Router's development error page**, and a deleted or
mistyped trip id rendered the whole setup wizard before admitting `unknown_trip` after the
owner had re-entered their answers. `shared/Recovery.tsx` is one branded recovery state
behind a catch-all route, an `errorElement` on every route, and a trip check in `AppShell`
before any stage draws.

**The two floating `/places` controls shared a corner at 390px** — the shortlist sat on
"How this works" and its focus ring between roughly y=97 and y=132. They are one container
now, positioned once, and in the document flow on a phone.

Also closed: the Revise horizontal overflow (a flex item's default `min-width: auto` is
its content's width); `US$3.2655` rounded to two places, because that is money and the
figure is an estimate from a price table; and "plan slice" replaced with what it means.

**A gate that compared nothing was reporting `PASS`.** `check_screen_baselines.py` now
exits 2 for "did not run", `check.py` prints `DID NOT RUN` and summarises `11 of 12`, and
the run is no longer describable as green when the visual comparison never happened. Two
real mobile defects shipped under the old wording. Capturing still cannot be a hard local
failure — it needs a running server and headless Chrome — but it may no longer be silent.

**The entry chunk was inspected rather than split further.** 533 kB raw / **159 kB gzip**,
and it holds react-dom, react-router, TanStack Query, `i18n/copy.json` at 137 kB and the
landing hero — no stage code, no map styles, no tour art, so route splitting is working.
`chunkSizeWarningLimit` is a measured budget of 560 rather than Vite's default guess, so a
warning now means a stage has escaped a lazy boundary. Splitting the catalogue by language
would halve it and is deliberately not done: artifact 027 requires both languages in one
payload so a language switch never refetches.

#### Open, and why

**`/places` still decodes ~2.7 MB of JSON** — `rank_candidates` is 1.52 MB (1108 cards at
1279 bytes) and `get_latest_discovery` 1.17 MB, against a deck that now deals twenty. The
fix is a new lightweight read, not a narrower old one: `candidates` is a `Frozen` snapshot
and the client is handed its `sha256`, so trimming at the transport boundary would put a
hash on the wire that does not describe its payload. That is a new allowlisted method, new
types and a rework of the busiest screen — worth doing deliberately, not at the end of a
session.

**The 390px states have no visual baselines.** The 58 approved images are desktop and the
documented 500px phone set; the audit's overlap and overflow both sat outside them. Adding
390px states means re-approving on this machine, and baselines are machine-specific by
decision (`WF-025`) — so it is the owner's call, not a silent re-approval.

### A feed existing is not a feed covering, 2026-08-14

The owner could not build a plan at all. `_default_transit_provider` chose GTFS on
`feed.is_file()` alone, so the moment a **Taiwan** metro feed was placed at the default
`TOURIST_GTFS_PATH`, a **London** trip was routed against a Taipei timetable and every
pair came back "no transit connection within walking reach of both places" — which reads
as the city having no transit rather than as the app holding the wrong country's
timetable. Adding the feed broke every non-Taiwan trip. The feed is now asked whether it
has a stop within `GTFS_COVERAGE_KM` of the destination before it is preferred.

**And walking is the preferred route evidence, not the only kind.** OpenRouteService was
unreachable for that trip — 60 of 60 attempts, `URLError` — which left all ten places
`ROUTE_UNVERIFIED`, the variants `unavailable`, and nothing on screen to press.
`collectRouteEvidence` now asks `refresh_transit_routes` after the walking passes: free,
a different service, and `estimated` routes the optimizer accepts on an Explore trip.
Measured on London: **0 walking routes → 24 transit legs**, and the plan went from
`unavailable` with 0 visits to `provisional`, valid, with **5 scheduled**.

Two smaller things from the same round. `readiness` and `costs` gate on `itinerary`
rather than `setup`, which was a gate that never blocked anything — they were reachable
and empty before there was a plan to be ready for or to pay for, and `setup` is now the
gate of no route. And **`Find places` is a one-press control**: `discover_places` keys its
cache on the destination, so a second press either rebuilds the same catalogue from disk
or spends another 30-90s of a free public service's budget on an answer already held.
"Search again" remains the deliberate re-run.

**Fixing one confusion caused another, twice.** Making the verdict panel's free button do
the same work as the ⚡ button left the journey carrying two identically-worded "assume
and build, free" controls; there is one now. And grouping the two floating `/places`
controls to stop them overlapping kept the wrong idea — "How this works" is read once, at
the start, and belongs beside the heading it explains, while only the shortlist wants to
float. Moved apart, the shortlist floats bottom-right, where nothing else lives; measured
non-overlapping at 1440 and 390.

### Choosing ends when the owner says it does, 2026-08-14

`/evidence` and `/optimize` unlocked the moment a **single** place was kept. The deck
deals hundreds of cards, so one keep is the *start* of choosing — and the sidebar offered
"Check trip facts" and "Build the plan" while the owner was still swiping, which was
reported twice as confusing.

They now wait for the deliberate press of **"Build the plan" on `/places`**, which is the
only moment the app is told the choosing is over. `confirm_places_selection` is the 89th
allowlisted method and writes a `places_confirmed` marker through the existing
`trip_evidence` table — **server-side, not `localStorage`**, because a journey stage that
relocks on another machine is not a journey stage. It is idempotent: it records a decision,
not a transition.

Two things that keep it from being a trap. `_places_confirmed` also returns true for a
trip already holding a **draft or an activated plan**, so owners mid-flight are not
relocked behind a button that did not exist when they chose. And the button navigates
whether or not the mark is written — `onSettled`, not `onSuccess` — because a trip that
cannot record the mark must not be stranded on the screen by it.

## Public release boundary

The current application is local-only and single-owner. Do not make `PlannerHandler`, the SQLite
file or locally loaded provider credentials Internet-facing. A future hosted release is a separate
operating phase whose canonical build order and exit gates are in `PUBLIC_RELEASE_PLAN.md`. Link to
that plan from implementation tickets instead of copying its checklist; retain run evidence under
`artifacts/validation/<run-id>/`.

## Configuration

**The default model is `gpt-5.6-luna` as of 2026-08-07** (`TOURIST_OPENAI_MODEL` still overrides), and it
beat `gpt-4.1-mini` on the `WF-046` benchmark — 6 of 12 exact against 5 of 13, four overshoots against
five, and it declines rather than claiming to know all thirteen. **The three `openai:*` prices were measured against
luna's rate card** (US$0.20/M input, US$1.20/M output at short context; nothing here reaches long
context, and `store: false` means caching never applies). luna is a *reasoning* model, so output is
mostly hidden reasoning and varies: six measured `opening_window` calls ran US$0.000090–US$0.000266, so
it is priced at **US$0.0005** and a 13-place refresh costs US$0.0065. `interpret_revision` and
`explain_revision` are sized from the real payload rather than measured end to end. The revision
surface is now reachable, but no real paid interpretation was submitted during its 2026-08-11
verification, so the UI correctly says **about** US$0.002. **The ledger over-reports OpenAI spend by
~US$0.325** from 30 calls recorded at interim
tenfold prices; `paid_usage` is append-only by design, the error is in the safe direction, and it decays
as new rows use the measured price.

`TOURIST_DB_PATH` (default `data/tourist.sqlite3`), `TOURIST_NOMINATIM_URL`, `TOURIST_OVERPASS_URL`,
`TOURIST_USER_AGENT`, `TOURIST_GTFS_PATH` (default
`data/gtfs/transit.zip`; a GTFS zip read locally for transit legs — see `WF-038`). Providers still read keys from `os.environ` and nowhere else — that is what keeps
a key out of every snapshot, export and log. `credentials.load_local_credentials()` (called once from `api.main()`)
copies a flat `secrets.local.json` into the environment first, so the owner need not
export four variables per shell; an already-set variable always wins, and the module never logs or
returns a value. `.env` / `secrets.local.json` are gitignored, `.env.example` / `secrets.example.json`
hold names and placeholders. `scripts/check_provider_access.py` reads the same file directly.
`tests/__init__.py` sets `TOURIST_LOCAL_SECRETS=off`. The original reason — `AppTest` importing `app.py`,
which loaded secrets at module scope — died with the POC, and `api` now loads them only in `main()`. **Do
not remove that line anyway**: it costs nothing and the failure it prevents is a bill. Paid usage is capped
at US$10/month by decision (warn at $8). `usage.py` is that ledger: `PRICES_USD` holds the estimated
unit price per `provider:operation`, `actions._spend()` refuses a call that would cross the cap and
records what it cost, and free-tier operations are recorded at zero so call counts stay reconcilable.
Every paid provider call must route through `_spend`; an unpriced operation raises rather than being
assumed free. Ledger rows are append-only by SQLite trigger.

## Graphify: this repo overrides the parent instructions

The ancestor `Thaksin/CLAUDE.md` tells agents to run `graphify query` for codebase questions and `graphify update .`
after edits. **Do not do either here.** Read source and tests directly; consult
`graphify-out/GRAPH_REPORT.md` only for a broad architecture question.

`graphify-out/GRAPH_REPORT.md` carries a generated "Graph Freshness" line advising `graphify update .`
after code changes. That is graphify 0.9.3 boilerplate, it is regenerated on every rebuild, and it is
wrong for this repo — ignore it.

On 2026-07-29 `graphify update . --no-cluster` corrupted the checked-in graph: it dropped the
`directed` flag and removed the Wayfinder/document nodes. `graphify-out/graph.json` is canonical and
must stay directed. Rebuild only through `python3 scripts/build_project_graph.py` (paid, needs
`OPENAI_API_KEY`; wraps extract → normalize → cluster-only → export and restores the previous graph on
failure), and only when explicitly asked or after a topology-changing milestone. After any graph
change, `--check` must pass before committing. See `AGENTS.md`.

**Rebuilt again on 2026-08-10 for `WF-049` and `--check` passes**: **2389 nodes, 5732 directed edges,
200 communities**; recorded cumulative cost is US$0.455929 over 41 runs. Adding the ticket file is what
required it — `--check` demands a node per ticket, so stage 4 of `check.py` failed with
`Extraction produced no node for WF-049` until this ran. It cost **US$0.0296** and succeeded on the
first attempt, with no `no node for …` flake.

**A fold guard was wrong, and the rebuild's own output is what showed it.** `normalize_raw_graph`
prints every fold precisely so they can be read, and this run printed eight. Four were genuine file
twins. The other four were **real methods being deleted**: `json` is in `SOURCE_EXTENSIONS`, `_json`
is also an ordinary Python method name, and `PlannerHandler._json` (`api/__init__.py:275`) extracted
as `api_init_plannerhandler_json`, found its own *class* sitting there as a stem, and was folded out
of existence — along with the `_json` on three providers in `travel_planner/providers.py`.

The comment above that code claimed "the stem-must-exist guard is what makes a wrong fold
unreachable". That was true only while every stem was a file. **A class is not a file, and a method is
not a duplicate of its class.** The fold now requires the stem to be a *file node*, recognised rather
than guessed: extraction labels a file with its own name and places it at `L1`, where a class or
method carries an identifier and its real line, and both conditions are required because a one-line
module would satisfy either alone. Re-running with the fix recovered exactly those four nodes and
folded the same four twins, on a **warm semantic cache at 76 hits / 0 misses, so it cost nothing** —
which is the same property that makes a retry after a failed rebuild free.

The earlier build the same day gave **2337 nodes, 5683 directed edges, 177 communities** at
US$0.426294 over 40 runs — +294 nodes and +651 edges over the one before it, which was the map work:
`web/src/shared/tiles.ts`, `tests/test_map_layers.py`, the rebuilt `PlaceMap`, and the forecast,
country-outline and route-shape providers.

**Extraction is not deterministic, and the per-ticket guard will catch that.** The first run failed with
`Extraction produced no node for WF-048` after being billed US$0.0262 — every ticket from 001 to 047
produced a node and 048 produced none. Nothing was wrong with the ticket: **the immediate retry produced
one and the build passed**, for US$0.0059 on a warm cache. So treat a single `Extraction produced no node
for …` as a coin-flip before treating it as a defect: retry first, and only then go looking at the ticket.
The failed run's US$0.0262 is **not** in `cost.json` — the ledger records a run when it completes, so a
failed rebuild costs money the recorded total does not show. The under-report is small and in the honest
direction, but it is there.

The earlier `WF-048` rebuild on 2026-08-07 gave 2043 nodes, 5032 edges and 167 communities at
US$0.420408 cumulative; the `WF-047` one before it gave 2026 nodes, 5002 edges and 165 communities.

**A duplicate node twin can be spelled without a separator, and that cost a paid run.** The
`WF-048` rebuild failed after being billed: extraction emitted `travel_planner_destinationspy` and
`web_src_routestsx` beside the real nodes, where `SOURCE_SUFFIX_IDS` listed only `_py` / `_ts`. Same
trap as below, new spelling — so the list is now generated from one extension tuple in **both**
spellings, and `normalize_raw_graph` **prints every fold it makes**, because a silent fold is
indistinguishable from the pair guard being weakened. Two tests in `tests/test_graph_builder.py`
pin it, including the negative case: `wayfinder_tickets` ends in `ts` and does not fold, because the
stem must itself be a node. **A retry after a failed rebuild is free** — the semantic cache stays
warm, so the second run reported 74 hit / 0 miss and US$0.00. Do not treat a failed rebuild as money
that must be spent again.

**A second name collision, and the same fix the first one needed.** A provider method called `fetch`
collided with the browser `fetch()` that `web/src/api/client.ts`'s `rpc` calls: extraction invented an edge
claiming TypeScript calls Python, clustering rightly dropped it, and the endpoint-pair guard demanded a
false edge survive. Renamed to `read_page`. **Do not name a Python method after something the TypeScript
side calls** — `fetch`, `rpc`, `post`. That is now two occurrences, so treat it as a rule rather than a
curiosity.

A third ticket-authoring trap, and the fix is in `normalize_raw_graph` rather than in how tickets are
written. Extraction sometimes emits one file **twice** — `tests_test_x` and `tests_test_x_py`,
`web_src_shared_names` and `web_src_shared_names_ts` — when a document cites it by path. `SOURCE_SUFFIX_IDS`
lists the extensions this affects; the `_py` case was fixed first and `_ts` appeared on the very next
rebuild, so treat the suffix list as incomplete rather than exhaustive. Both land in the raw node set, so the endpoint-pair guard treats an edge
to the `_py` twin as real, clustering then correctly collapses the duplicate, and the build fails claiming
data was lost. `WF-039` cited `tests/test_comfort.py` in the identical style and extracted cleanly, so it
is extraction variance, not a citation style to correct. The twin is now folded into the real node before
`expected` is computed — the same normalisation the `wayfinder_tickets_NNN` aliases already perform, and
**not** a relaxation of the guard: the edge survives, pointed at the node that does. The `WF-039` rebuild the same day
gave 1868 nodes, 4589 edges and 150 communities. The `WF-040` rebuild the day before
gave 1818 nodes, 4492 edges and 153 communities for US$0.0121.

Two ticket-authoring gotchas learned paying for that run. **Cite a module by its path** — a bare
`exports.py` extracted as a node id `exports` that does not exist, clustering rightly dropped the edge,
and the endpoint-pair guard then demanded a false edge survive; every other ticket writes
`travel_planner/exports.py`, which resolves. And **a ticket dense in code identifiers may extract no
titled node at all**: `WF-039` produced only `comfort_acceptances Table`, `COMFORT_RULES` and
`comfort_tradeoffs`, so `resolve_ticket_node` could not choose among three candidates and aborted the
build. That was fixed at the root rather than worked around — a ticket's node id is read **only** as an
endpoint of a `blocked_by` edge, so `resolve_ticket_node` now takes `required=` and only refuses over
ambiguity when the id is actually used. An **empty** extraction still always raises, because that is the
per-ticket presence guard `--check` depends on. The `WF-042`/`WF-043` rebuild earlier the same day gave 1756
nodes, 4305 edges and 148 communities for US$0.0125.
Adding a ticket file **breaks stage 4 of `check.py` until this is re-run**, because `--check` demands a
node per ticket; that is the normal reason to pay for a rebuild.

The earlier S6 rebuild on 2026-08-04 gave 1599 nodes, 3185 → 3851 directed edges and 149 communities, with
**zero nodes sourced from the deleted POC** (there were 82), for US$0.028350.

One of those failures was not flaky and is worth knowing: validation refused three times over the same
lost pair, `test_s4_taipei_journey_reaches_activation_and_both_downloads → web/src/api/client.rpc`. The
cause was a **name collision** — that test defined a local `def rpc(...)` helper and `client.ts` exports
`rpc`, so extraction invented an edge claiming a Python test calls a TypeScript function. Clustering was
right to drop it and the guard was demanding a false edge survive. Fixed at the source by renaming the
test-local helper to `post_api`; there is now no `def rpc` in any Python file. **Do not weaken the
endpoint-pair guard to get past a failure like this** — find the collision. `build()` now preserves
`failed-raw.json` and `failed-clustered.json` on failure, because the two files that explain a validation
failure were exactly the two its cleanup deleted. The script reads `OPENAI_API_KEY` from `secrets.local.json` itself.
Three things to know: **ticket nodes are keyed by title, not by ID**, so `WF-0nn` never appears in a node
name; **`--exclude` patterns are gitignore lines**, so anchor them (`/artifacts`, not `artifacts`) or they
match at every depth; and **never run `graphify extract` by hand** — it is incremental against an existing
`graph.json` and will overwrite it with a partial. `AGENTS.md` has the detail.

A node's `source_file` may hold an absolute path from the machine that built the graph. Such a path is
not `is_absolute()` on Windows, so joining it to the repository root produced a drive-relative path
that matched nothing, and `--check` failed with `Extraction produced no node for WF-001` on every
ticket except the one stored relatively. That reads exactly like the corruption above but is not it:
the nodes are present. `build_project_graph.source_path()` resolves a node's source against the
longest trailing segments that exist in this checkout, so the check works from any OS and any root.
Diagnose a `--check` failure by counting the wayfinder-sourced nodes before assuming data loss.

## Wayfinder: decisions live in tickets

There are **two maps**, and tickets are numbered continuously across both in `.wayfinder/tickets/`; a
ticket's `parent:` field says which map it belongs to.

- `.wayfinder/map.md` (`WF-MAP-001`, **closed**) indexes the 17 closed Phase 1 decision tickets.
- `.wayfinder/map-002-splitter-merge-and-webapp.md` (`WF-MAP-002`, **open**) is Phase 2: merging
  `Auto-Bill-Splitter` in as a group split ledger and replacing Streamlit with a local React webapp.

Before changing scoring weights, optimizer rules, schema, or provider policy, read the relevant ticket —
the "why" is there, not in the code. Reference tickets by linked title, never bare ID.

Slices 1–4 are built and evidenced (foundation, setup+discovery, ranking, optimization). Slice 5 is
**complete**, including the readiness checklist and owner-recorded costs: `exports.py` builds the one shared export snapshot; `exporters.py` writes the six-sheet Excel workbook and the
readiness ICS — both snapshot-in, bytes-out. **The 9:16 poster and the trip PDF were dropped in slice S0**
(2026-08-03), and with them the whole export-font apparatus. `checklist.py` generates the readiness board and `costs.py` converts owner-recorded
expenses into THB against an owner-editable, timestamped rate snapshot; a paid charge locks its actual
THB so a later rate cannot rewrite it, and a missing rate stays a visible gap rather than a guess.
**Phase 2 S5 is complete:** `api/` owns the localhost boundary and downloads, `web/` owns the nine
routes and in-place `StageGate`, and `scripts/check.py` is the one free green command. The allowlist was
**61 methods** at S5 — 51 at S1, five split-ledger ones at S2, `setup_vocabulary` at S3, the paid-call
preflight and export-snapshot reads at S4, then `checklist_vocabulary` at S5, and `refresh_transit_routes`
for `WF-038` — and is **91** now, the additions being `WF-039`'s comfort tradeoffs, `WF-040`'s
`recommend_areas`, `WF-048`'s month guide, basemap pair, map detail, country-outline pair, route shapes
and trip forecast, `WF-049`'s split-cardholder pair, `build_money_snapshot` and category pair, and
the owner-testing rounds' `confirm_default_opening_windows`, `confirm_places_selection`,
`accept_provisional_base` and `accept_route_estimates`.
**38 refusal codes.** `tests/test_api.py` asserts the count, so it cannot drift silently. **All ten routes are
real screens** — nine as of 2026-08-04, plus `/stay` — `/setup`, `/places`, `/evidence`, `/optimize`, `/itinerary`, `/readiness`,
`/costs`, `/split` and `/revise`. There is no `StagePage`, no `gated()` wrapper and no `stage_stub` copy key;
they went with the last stub. `/evidence` was built between S5 and S6 because **no slice row owned it** and
S6 has since deleted the POC — see `artifacts/validation/2026-08-04-evidence-screen/notes.md`. It is the screen a
*newly created* trip needs, since route and opening evidence are hard optimizer constraints.
**Slice 6's React surface is complete as of 2026-08-11.** S5 delivered the non-AI quick actions;
`/revise` now also exposes the constrained free-text interpreter behind an off-by-default checkbox,
with price and transmitted-data disclosure visible before the control is enabled. The core landed long
before either: `revision.py`'s non-AI quick actions (`a7ad537`) and
`interpret.py`'s constrained GenAI revision (`a2d59f6`) landed 2026-07-29 with tests. The pure modules
survived the redesign exactly as intended; their Streamlit surfaces went at S6. The live pilot remains
local-only. Every new output must read
`build_export_snapshot()` rather than the raw variant — that is what keeps their times, totals, and
statuses from diverging. Complete a slice vertically with its own runnable check before starting the next.

The export-font requirement is **gone** with the poster and PDF (S0): no Unicode TTF, no `resolve_font()`,
no `TOURIST_EXPORT_FONT`. `_labels()` still strips pictographs, because the wording alone carrying the state
is an accessibility rule and not only an export one.

Explicitly out of scope for the Python core: FastAPI, Docker, Redis, background workers, remote
collaboration, hosted notifications. `pyproject.toml` lists exactly two runtime dependencies:
`xlsxwriter` exists only because slice 5 renders a workbook. **After S6 there is exactly one**: `fpdf2` went
with the PDF and poster at S0, and `streamlit` went with the POC. `pillow` used to arrive transitively via
streamlit and is now declared in `[dependency-groups] dev` — the screen-baseline gate reads PNGs with it, so
that declaration is what kept the gate working when the POC went.

## Phase 2 implementation follows the locked slice order

`WF-MAP-002` is **decision-complete as of 2026-08-03**. Across both maps there are 49 tickets, **49
closed, 0 open**. Nothing is outstanding. `WF-049` is the 49th and was written *after* the work,
which is the exception rather than the rule: it answers an external audit rather than opening a
question, so there was nothing to claim an assignee on before starting.

**`WF-048` rebuilt the journey's explanations on 2026-08-07**, after the owner walked the whole
thing and could not use it. The findings were mechanical, not matters of taste: the landing page
never said what the app produces and asked for a geocoder query as free text; the setup wizard
opened on a form with no statement of what it wanted; the swipe gesture had never worked because
nothing captured the pointer or set `touch-action`; photographs were slow because the visible one
was `loading="lazy"` and nothing was prefetched; and neither the shortlist nor the optimizer's
assumptions were shown at all. Four rules from it bind later work. **The destination is
`"City, Country"`** — `AppShell.countrySlug()` takes the last comma-separated segment, so a
city-only string silently loses the destination accent. **Both destination dropdowns keep a typed
fallback**, because `travel_planner/destinations.py` is a picker convenience and the
worldwide-acceptance check requires a city absent from it to still complete setup. **The
assumptions on `/optimize` are read out of the frozen `optimizer_input`, never recomputed** — the
snapshot already records its own `capability_gaps`, and a second opinion derived beside it could
disagree with the plan it claims to describe. And **the places screen shows totals, not a
per-day fit**, because dividing by the optimizer's pacing constants would put a second copy of them
in TypeScript. Two things it deliberately left: the deck is still fed `main_queue`, whose top 20
have no Wikidata id and therefore no photograph (`WF-005`'s lane choice, and its own ticket), and
the 1440×900 viewport is unchanged, so `WF-025`'s blind spot now hides three more features.
The deck's lane was the first of those two and the owner asked for it in the same session: the **lane
picker now drives both modes**, defaulting to City Icons, and decided places are filtered locally
because only `main_queue` excludes them server-side. `main_queue` is one select away, so `WF-005`'s
4:1 queue is still reachable — it is just no longer the only dealable lane.

**The landing page has its own palette as of 2026-08-08 (`WF-048`), and only it.** The owner asked for
the first page to take its vibe from two named sites and for every other screen to stay as it is, so
`tokens.css` gained a `--landing-*` block that nothing outside `.landing` reads — the destination-accent
system (D6) and the house-red fallback (D3) keep working untouched behind it. The colours are **sampled
from the references**, not guessed: the deep teal-ink and amber are Vita Travels' own section background
and golden-hour ground, the cream is Hack the North's sand, and all five clear AA on the ink background
(4.5:1 or better). The hero scene is **drawn in SVG, not photographed** — `WF-034` keeps this app working
offline with no remote assets — which also lets it be about the product: the dotted route with four
numbered stops *is* the thing the planner makes, and those stops are the four stages, so the picture and
the "how it works" list describe one journey. Every animation sits behind
`prefers-reduced-motion: no-preference`.

**A long wait says what it is doing as of 2026-08-09 (`WF-048`).** Discovery runs 30-90 s and a full
optimize about 52 s, and `/optimize` showed a disabled button and nothing else for all of it — reported
three times as "I still can't build a plan" when the work had succeeded every time. Diagnosed by running
the real pipeline against the owner's own databases: `generate_plan_preview` returned `dated_plan` and
all three variants came back **activatable**. Nothing was broken except the silence. `shared/Thinking.tsx`
cycles the real stages in the real order — `think_searching`, `think_routes`, `think_packing` — on a
timer rather than on progress events, which is honest about what it is, since the server reports no
milestones and this claims none.

**A background prefetch must not take the card off the screen, fixed 2026-08-09 (`WF-048`).** The
`/places` skeleton gated on `fetchSummary.isPending` — the prefetch that fetches photographs for cards
*further down the deck*. Every swipe invalidates the ranking, the new order changes which cards are
coming up, and so every swipe started one: the whole workspace, deck, detail panel and lane picker
included, emptied itself after each card, for work on places the owner had not reached. Reported simply
as the deck being broken, and it may as well have been — nobody can work through 300 cards on a screen
that clears itself between them. It now blanks only when there is genuinely nothing to show
(`!ranking.data || summaries.isPending`). A photograph arriving late lands in a fixed-size box and moves
nothing, which is what makes it safe to arrive late.

**The deck looks throwable.** It was styled exactly like every other panel, so nothing invited a hand;
it now carries a tint, a hard shadow, a grip bar and two coloured edges that say which way means what
before the first drag.

**The opening-hours decision moved to where it matters.** It lived only on `/evidence`, so building a
plan meant leaving `/optimize`, reading a wall of controls, deciding and coming back — reported as
"back and forth". `/optimize` now asks the one question that affects the button next to it, in a
sentence with the numbers in it, and offers both answers inline. `/evidence` keeps the detail and stops
being a required stop.

**The evidence screen answers its own question first.** "Am I need to fetch it or not" was the report,
and `opening_evidence_options` had priced both paths and known `assumed_is_usable` since `WF-047` —
the page simply never asked. A verdict panel now states the answer in a sentence with the numbers in
it, and only then shows the controls.

**A month recommends its quietest dates.** `climate.best_window` slides a trip-length window across the
month and scores it: a public holiday costs a full point and a weekend day half of one, because both
fill the same trains and a national holiday empties the offices too. Ties resolve to the earliest window
so re-opening the screen cannot show different dates. It returns `None` for a trip longer than the
month rather than a range scored against holidays it was never given. Computed on read from the stored
holiday dates, so trying a different pace costs no request.

**The map has a real basemap as of 2026-08-09 (`WF-048`).** Faint catalogue dots were still
unreadable — "I can't see anything" — so `OpenStreetMapProvider.basemap()` fetches major roads,
water and parks for the window discovery already searched: **809 roads, 46 water bodies and 45 parks
for Taipei in 5.6 s**, one free Overpass request, stored for 30 days because coastlines do not move.
Tags are dropped and coordinates rounded to ~1 m on the way in, which takes the response from
**1151 KB to 235 KB**. `WF-034` still holds: no tiles, and nothing fetched at view time.

**The zoomed-in map is drawn in layers as of 2026-08-10 (`WF-048`).** One free Overpass request for
the window on screen returns land use, water and parks, building footprints, the **whole road hierarchy**,
rail, and station/bus/charging markers — measured over 1.6 km of Ximending at **2545 elements, 16957
points, 2.0 MB on the wire in 13.6 s, stored at 382 KB** after tags are dropped and coordinates rounded.
`WF-034` still holds: no tiles, nothing fetched per tile, and the numbered list under the map still
repeats every pin.

Four things that make it read as a map rather than a diagram. **Roads are drawn twice**, a wider casing
under a narrower fill, which is what gives a road an edge and makes a crossing a junction; every road was
one grey line of one width before, so a trunk road and a service alley were the same mark. **Street names
run along their own streets** via `textPath`, romanized where OpenStreetMap has `name:en` — 486 of 600
roads in that window carry a name, so `中華路一段` is labelled `Section 1, Zhonghua Road`. **The
catalogue's own categories colour the POI dots** — food, shopping, culture, outdoors, lodging — which is a
map legend for no request and no new data. And **footways, paths and steps are not requested at all**:
they were 615 of those 2545 elements and at this scale they are hatching.

Five bugs found by driving it, four of them the same mistake in different clothes — **a length declared in
user units when it needed to be screen units**. `marker-mid` inherits `markerUnits: strokeWidth`, so the
invisible one-way carrier line's default 1-*unit* stroke drew every arrow about **170 px wide**, and a few
hundred of them merged into a taupe mass that looked like a landmass and hid the entire map; it survives
every layer override because the arrow lives in `<defs>`, which is why it took so long to find. Chrome
**ignores `vector-effect: non-scaling-stroke` on `<text>`**, so a 2.4px label halo became a ~100px white
disc per glyph. The label-length threshold was a share of the *catalogue's* span rather than the visible
width, so every label was silently discarded. `textPath` neither wraps nor shrinks, so a name longer than
its street was cut to **a single stray glyph** — names are measured before they are offered now, and a
street that cannot hold its own name goes unlabelled. And `.places-map svg` outranked `.places-map-svg`,
so the map kept the panel grey until the new rule was written at matching specificity.

**The map has a night palette**, not a dimmed day one: a light panel that size glares in a dark room, so
the same layering is inverted the way a road atlas has a night edition — dark ground, roads *lighter*
than what they run through so the network stays the top layer. That is the one deliberate baseline change
here; the two dark `/places` screens were re-approved and the other 34 are untouched.

**Not built, and why.** Star ratings and review counts are Google Places at **US$0.025 a place** — they
stay behind the owner-triggered button `WF-047` priced, not on a background map fetch. Live traffic-light
state is not static data and is in no free source. Both were asked for; neither is refused for effort.

**Zooming out has to give the city back, fixed 2026-08-10 (`WF-048`).** The detailed layers replaced the
city-wide basemap the moment they arrived, so zooming out past that one window left the map blank except
for the patch it covered — reported as "it only show the certain area", and fatal to the thing the map is
for, which is seeing where everything is before choosing. Coverage is now a question asked of the current
view against `detail.bbox`: while the detailed window contains the view it is drawn and the basemap steps
aside, and the moment the view reaches past its edge the basemap comes back. The window is computed
whether or not it is small enough to fetch, because the fetch gate and the coverage test are different
questions about the same rectangle.

**`/itinerary` opens on the map as of 2026-08-10, and which tab is open lives in the URL.** It opened on
the timeline from when the map was a strip of dots and there was nothing to open onto. Now it draws the
streets, the day's walk and the stops in order, so it is the faster answer to the question the screen is
opened with — *where am I going today* — and the timeline is one click away for the one that follows.
Putting the tab in the query string is not a convenience: two tests assert the timeline's rows, and a
default that silently hid them from the suite would have hidden them from the owner too. Addressable, it
stays assertable, survives a reload and can be linked to. The four `itinerary-*` baselines were
re-approved for the new default; the other 32 are untouched.

**The day's line follows the streets as of 2026-08-10 (`WF-048`), and it cost no new request.**
OpenRouteService has always returned the path as GeoJSON and `normalize` has always thrown it away, so
keeping it is a decision rather than a fetch — the trip already paid for these calls. Thinned at
`shape_step_metres` on the way in, because a leg carries hundreds of points and the record is hashed,
cached and read by every screen that draws a plan; a 658 m walk stores as 16 points, a 2 km one as 274.

**`geometry` is dropped at `_optimizer_input` and nowhere else.** That boundary copies a route **whole**,
so letting the shape through would change the hash of every existing plan, report drift on plans nothing
had touched, and push a few hundred coordinates per leg through the solver and the frozen fixtures for the
sake of a picture. `route_shapes` is a separate read for exactly this reason: `list_routes` is the
optimizer's view of a route — a duration and a distance — and this is the picture of one.

**Every leg is drawn, and a leg with no path says so.** It is dashed where the map is joining two stops
with a straight line, because that line crosses the river and understates the distance and must not be
mistaken for a route anyone can walk. Drawing only the routed legs was worse than either: a day with one
of each showed a single line and no hint that anything was missing. Expect gaps — ORS's free tier answered
40 of 57 pairs and rate-limited the rest, and a transit leg is a timetable rather than a path.

**Four things followed from unlocking the network, 2026-08-10 (`WF-048`).** Worth stating why they belong
together: `WF-034` was never protecting the *planning*, which has always called Overpass, Nominatim,
Wikidata, Commons and Open-Meteo. It was protecting the **trip** — the app working in Taipei with no data.
So unlocking it opens up what the app can do **on the ground**, and that is where the gaps were.

**`/itinerary` now draws the same map as `/places`.** It was a 420×120 strip of dots joined by straight
lines, and its own comment still read "no tiles or network" — written when that was the policy everywhere.
So the screen used while *choosing* got streets, buildings and tiles, and the screen used while *standing
on a corner* kept the diagram. One component draws both now, which is also the only way the two cannot
disagree about where a place is. The day's stops are joined **in order**, because a day is a sequence and a
scatter of numbered dots does not say that — `route` is off on the shortlist, where nothing is sequenced
yet and a line would invent one. The stop list underneath is untouched: `WF-034`'s rule that the drawing is
never the only carrier still holds, and it still prints the coordinates.

**Every stop can hand off to the phone's own map.** This app schedules a day; it does not do turn-by-turn
and should not try — what it stores is a duration, not a path. `mapsLink` uses the `geo:` scheme rather
than a vendor URL, so Android opens whichever map the owner chose and iOS opens Apple Maps.

**The weather is the real forecast for the real dates, where they are close enough to know.**
`OpenMeteoForecastProvider` sits beside the archive that answers "what is January like in Taipei" — the
right question in August and the wrong one on 28 December. Free, keyless, **0.9 KB in 1.0 s for 16 days**,
cached six hours. Beyond the horizon it returns `covered: false` rather than a guess, which is the true
answer and is what stops a fabricated day looking exactly like a real one. Reported beside the day, never
folded into a score: a plan that reshuffles itself because a forecast twitched is worse than one that says
what it knows — the same rule `WF-047` set for cost and `WF-045` for drift.

**A photograph can now be found by name as well as by place.** Geosearch asks "what was photographed at
this spot", which misses a file filed under the place's own name but geotagged from across the park —
measured, it had nothing for Shilin Presidential Residence Park while **four files carry that exact name**.
The search now runs both ways. **The coordinate check is what makes a global text search safe**: Commons
returns six photographs of *Central Park in Vinnytsya, Ukraine* for `Central Art Park`, and not one of them
carries coordinates — so a file with no location is refused outright rather than trusted, and one with a
location must fall within `named_radius_metres`. Both filters, never either. `cache_version` goes to v4 so
places that came up blank are asked again once.

**The map shows OpenStreetMap's own tiles when there is a network, as of 2026-08-10 — and `WF-034` §3 was
revised by the owner to allow it.** Asked whether the map could look exactly like `openstreetmap.org`, the
answer was that it never could: that site is a *tile* service rendering the whole planet database through a
mature stylesheet, and this draws vectors from one Overpass window. So the owner was offered the trade the
ticket had already weighed and chose the **hybrid**: OSMF standard tiles over the top, and the vector map
the instant a tile fails to load. One failed image is enough to decide, because they all come from one
host. **The premise `WF-034` was protecting survives** — with no network the map still has roads,
buildings, land use and street names from data on disk — and the "product loss" that section recorded is
repaid whenever there is one.

**The projection became Web Mercator to carry them.** It was a flat `longitude × cos(latitude)`
approximation, which is within a hair of Mercator at city scale but makes a tile a *trapezoid* instead of a
square, so an image could not be laid on it without smearing against the pins. Everything goes through the
one transform, so the streets, the buildings, the stops and the tiles moved together and none of them can
disagree; the 36 baselines passed **unchanged**, which is the measure of how small the shift is at this
scale.

Four things that keep this honest. **Captures never draw tiles** — a remote image would have the screen
baselines photographing the network, which is the drift bug twice over. **Volume stays courteous**: a view
is 6–20 tiles, browser-cached, chosen at roughly one image pixel per screen pixel, never prefetched, and
`tilesFor` refuses outright rather than asking a public server for hundreds of images if the arithmetic
ever goes wrong. **`© OpenStreetMap contributors` is now on screen beside every map**, which the ODbL
required for the geometry all along and this app had never done. And the fallback **says which map you are
looking at**, because a drawn map and a tiled one are not the same picture and pretending otherwise is how
someone ends up trusting the wrong one.

**The zoom ceiling was a ratio, and that was the bug behind "I still don't see the detail".** `MAX_ZOOM`
was 24 — about **2 km in Taipei**, which is also where the card map *opens*, so the map was already at its
ceiling and could not be zoomed in at all. Every threshold below 2 km was unreachable, so the
service-road tier never fired however far the owner scrolled. The ceiling now comes from `MIN_VIEW_KM`
through the projection's own scale, the same correction the floor and the fetch gate needed: measured, the
map reaches **178x and 800 m** where it used to stop at 24x. `SHOW_SERVICE_KM` also moved 1.5 → 2.5 so the
small streets are in the view a card opens on rather than one step past it, and the arrows kept their own
closer threshold because they are the noisiest thing here.

**The drawing fetches retry a fast failure, which discovery has done since `WF-048` and they never did.**
Measured 2026-08-10 on a 1.5 km Taipei window: **HTTP 504 at 8.5 s, then 200 at 8.5 s on the identical
query**. A map with no streets on it was one retry away from having them, on exactly the fault
`_attempt_block` was written for — `overpass-api.de` balances across backends and an unhealthy one answers
504 in seconds. `_drawing_elements` now wraps both `basemap` and `map_detail`.

**A refusal keeps what is already drawn, and says so.** Two faults hid behind each other here. Discarding
the held detail on a failed fetch wiped streets that were still perfectly good for the view — zooming in
asks for a *smaller* window, so a busy endpoint emptied a map that needed no new data at all; the held
window is kept and `detailCovers` decides whether it still covers the screen, which is the only question
that matters. And a refused fetch drew nothing while looking exactly like a bug, so
`map_detail_unavailable` now says which it is. `SETTLE_MS` went 900 → 1500 for the cause rather than the
symptom: every card opens on its own window, so browsing the deck was one Overpass request per card, and
two concurrent slots do not survive that.

**The scale note reads metres under a kilometre.** Rounded up, every view from a single street to a
district said "About 1 km across" — no scale at all across the half of the range where the layers change.

**The map draws a different amount at every scale as of 2026-08-10 (`WF-048`).** Everything the detailed
fetch returned used to be drawn the moment it arrived, which is right at 1 km and wrong at 6: 244 service
alleys and 994 footprints over a district is grey felt, and the trunk roads that tell you where you are
disappear into it. The ladder is `SHOW_COUNTRY_KM` 40 → `SHOW_MAJOR_KM` 12 → `SHOW_MINOR_KM` 6 →
`SHOW_BUILDINGS_KM` 3 / `SHOW_MARKERS_KM` 3 → `SHOW_LABELS_KM` 2.5 → `SHOW_SERVICE_KM` 1.5, all in
**kilometres across the view**, for the same reason the fetch gate is: zoom is a ratio of the catalogue's
own span, so the same factor is a different real distance in every city. Markers sit at 3 rather than 2
deliberately — a card opens on about 2.2 km, and "which exit do I come out of" is the question the map is
asked there.

**One number now measures scale.** The note under the map read the projection's own span and the ladder
read its units-per-kilometre, and those describe *different axes*: the projection is fitted on whichever
of width or height is limiting. A map saying "1 km across" was being drawn as though it were three, which
is why the transit markers never appeared at any zoom. Both now come from `windowKm(windowBox)` — the
latitude and longitude actually on screen.

**A size inside the `viewBox` is multiplied by the zoom, and that has now broken three times.** A ~100px
label halo, ~170px one-way arrows, and a pin number rendered at ~440px of white that covered the entire
map — the last from an edit that deleted the neighbouring CSS block and took
`.places-map .plan-map-point text` with it. Nothing failed: the markup was unchanged, the tokens were
unchanged, and the screen baselines photograph the default view. `check_design_tokens.py` now asserts that
the pin's number divides by `--map-zoom` and that every stroked map layer carries
`vector-effect: non-scaling-stroke`, and it is negative-tested. **The country outline is only drawn above
`SHOW_COUNTRY_KM`** for the same family of reason: at street scale it is hundreds of times the frame, which
is geometry the browser rasterises for nothing.

**Zooming out goes to the country as of 2026-08-10 (`WF-048`).** The projection is fitted to the city, so
the city was also as far out as the map could go — and "where is this place *in the country*" is the
question that decides whether somewhere is worth a day of a trip. `OpenStreetMapProvider.country_outline`
asks Nominatim for the destination country's boundary **simplified server-side**, which is the whole
reason it is affordable: Taiwan's real coastline is megabytes, and at `outline_threshold` it is **137
points and 4 KB in 1.0 s** (Japan 407 points, Thailand 215). Free, cached for a quarter, one request per
trip rather than per window.

Three things about it. The outline is projected **through** the city's transform and is deliberately not
part of the bounds that define it — including it would open every map on a continent. The zoom floor is
computed from it, so a map with no outline still stops at its city and nothing is lost. And it is fitted
to the **largest ring, not all of them**: a country's boundary includes whatever it administers, so
Taiwan's takes in Kinmen and Matsu against the Chinese coast, and fitting them all zoomed out to
**1986 km**, at which the island the trip is on is a speck. Fitted to the main landmass it is **527 km**
and reads as Taiwan. The outliers still draw; they are allowed off the edge.

**The catalogue dots were removed on 2026-08-10, at the owner's asking.** Every discovered candidate was
drawn as a small coloured dot with a legend naming six families, a name on hover, and a tap that opened
its card. They cost nothing — already in memory, no request — and they were the only thing on the map
answering "where *could* I go" rather than "where am I already going". The case for keeping them was put
once and the owner asked twice to take them out, which settles it: several hundred marks of six colours
over a real street map is a texture rather than a set of choices, and the deck is where choosing actually
happens. `context` is no longer taken by `PlaceMap` at all. Restoring them is a prop and a `map`, not a
rebuild — the reasoning is kept at the top of the component next to where they were.

**Buildings arrive on zoom as of 2026-08-09 (`WF-048`) — and only on zoom.** At the full city window a
footprint is well under a pixel, so `basemap()` still carries none: a city's shape at that scale is its
roads, its water and its green. `OpenStreetMapProvider.buildings()` fetches footprints for the window
actually on screen — measured **1200 rings and 11023 points in 5.5 s** for a 2 km box in Taipei — capped
at `buildings_limit` and refused outright above `buildings_max_span = 0.06` degrees, cached 30 days per
rounded window so panning back over fetched ground is free.

Four things that make it work, all of which were wrong first and found by driving a real browser rather
than by reasoning. **The gate is the window's measured span in degrees, not the zoom factor**: zoom is a
ratio of the *catalogue's* own span, so the same factor is a different real distance in every city — at
the first cut Taipei's 0.56-degree catalogue meant even `MAX_ZOOM` left a 0.07-degree window and the
request was refused at **every zoom the map could reach**, so buildings could never appear at all.
`MAX_ZOOM` went 8 → 24 for the same reason. **The fetch is debounced** (`SETTLE_MS`): one continuous
zoom crosses many distinct windows and asking for each measured **five Overpass requests from a single
gesture**, against the endpoint that grants two slots and answers 504 once they are spent — the burst
CLAUDE.md already warns about, self-inflicted. **Footprints are projected *through* the pins' projection,
never into it**: they cover only the current window, so letting them into the bounds moved the whole map
every time a window loaded. `projectionOf` therefore returns `toXY` as well as `toLatLon` and
`plotCoordinates` is now one call to it — two copies of that maths was one copy too many. And **a viewBox
scales its contents**, so pin radii, dot radii and label type are divided by the zoom (the label through
`calc(var(--text-2xs) / var(--map-zoom))`, so the token stays the source) and strokes carry
`vector-effect: non-scaling-stroke`; at 5x the pins had grown to cover the streets they mark. The
geometry is memoized on its inputs, so dragging no longer reprojects the city.

**Wheel zoom is bound by hand, not through `onWheel`.** React registers its wheel listener **passively**,
where `preventDefault` is ignored — so zooming the map scrolled the page out from under it at the same
time. The listener is added with `{ passive: false }` against a ref.

The buildings fetch is **skipped under the capture flag**, like the summaries prefetch and
`refresh_basemap` before it: it writes a `provider_cache` row, and a screen that changes what it holds
when photographed is the 13%-drift bug again.

**Every map opens on its own subject as of 2026-08-09 (`WF-048`).** Fitting the projection meant the
card's "where is this one" drew the whole 31 km region with one pin somewhere in it — the "I still don't
know where is it" report, which survived both the catalogue dots and the basemap because neither changed
the *scale*. A map with a `focusId` now opens at `FOCUS_KM` on its subject and a map without one fits the
pins it was given: measured on the pilot, the card map went 31 km → **1 km** and the shortlist map 31 km →
**18 km**. As a consequence the card map's window is small enough to be worth footprints, so the detail
arrives without anyone having to know to zoom. Two traps. The home view is compared **by value, not by
object identity** — `geometry` is rebuilt when footprints land, and reacting to that snapped the map home
and undid the pan that asked for them. And the "already settled" marker starts as **`null`, not as the
first key**: seeded with the key, a map whose data was already cached on its first render counted as
settled and kept the initial view, which is why the shortlist map alone stayed at the wrong zoom while
the card map — whose data arrives a beat later — was correct.

**Window snapping was tried and reverted, and the measurement is why.** Snapping the requested window
onto a shared grid would let neighbouring places reuse one cached fetch, but `buildings_limit` is a
budget and snapping spends it off-screen: central Taipei holds **15253** buildings in the snapped 4.4 km
tile against **3546** in the 2.2 km window actually being looked at, so the 1200 returned fell from a
third of the view to 8% of it. A scattered half of a neighbourhood reads as a city; a twelfth of a
district reads as a rash. `SETTLE_MS` holds the request rate down instead, which costs coverage nothing.

The 36 screen baselines pass **unchanged**, which is the proof the default view is untouched: at zoom 1
the window is far too wide to ask, so nothing is fetched and nothing is drawn.

Basemap vertices go through the **same projection pass** as the pins: a second
projection would fit the streets to their own bounds and lay the city where the pins are not. The
`refresh_basemap` call is skipped under the capture flag in favour of the read-only `get_basemap`,
because it writes.

**The map draws the city from the catalogue as of 2026-08-09 (`WF-048`).** Six pins on empty grey told
an owner nothing — no coastline, no districts, no sense of which end of town anything was, reported as
"I still don't know where is it". Every discovered candidate already carries coordinates and is already
in memory, so plotting all of them as faint dots draws the city's real footprint for **no request and no
tiles**: density does the basemap's work, and Taipei's core, southern sprawl and Beitou are all legible.
Pins and city share **one projection** — projecting them separately would scale each to its own bounds
and put the pins where the city is not. `plotCoordinates` now takes a frame, because the itinerary's
420×120 strip squashes a roughly square town into a band and piles every pin in the middle; `/places`
uses 420×260. A north arrow and a "≈ N km across" note make it readable rather than only lookable-at,
and `WF-034`'s no-tile-map rule is untouched.

**The places tour is remembered per trip, not per browser.** Keyed globally it was reported as never
appearing, by an owner who had simply dismissed it on another trip — a new trip is a new context. The
reopen control is a labelled button now rather than the grey whisper it started as.

**The hero is drawn, and it has to be.** The owner asked for it to match hackthenorth.com exactly. That
site builds its hero from **1124 commissioned `.webp` illustrations** and animates them with
**framer-motion** — its own stylesheet states only two timings outright, `vinylSpin` and
`glowPulse 1.7s ease-in-out infinite`. Neither is available here: the artwork is someone else's, `WF-034`
keeps this app working offline with no remote assets, and `WF-026` fixes the web runtime at six
dependencies. So the *vocabulary* and the *motion* are matched in SVG and CSS — drifting clouds,
mountains at three depths, a winding dotted route, tilted sticker cards, sparkles, a glowing pill, and
pointer parallax driven by two custom properties one handler writes, with `glowPulse`'s 1.7s reproduced
exactly. Matching a look is fair; reproducing an illustrator's work is not, and the distinction is the
reason this is drawn rather than copied. Every animation sits behind `prefers-reduced-motion`, and the
36 stage baselines pass **unchanged**, which is the proof that "only the first page" held.

**A UX audit was answered on 2026-08-10, and the accessibility half was the real content.** All
sixteen findings were reproduced in a browser against a byte-identical copy of the pilot before
anything was changed; two of them turned out to be worse than reported and one turned out not to
exist. What binds later work:

**The accent does two jobs and one value has to serve both.** It fills a button and it colours a
link, so `--color-on-accent` alone was never going to be enough. Contrast is symmetric, so an accent
legible as *text* on the theme's lightest surface necessarily takes the opposite ink as a *fill* —
that single rule replaces a second text-accent token, and it is why **all thirteen destination
accents now have a `:root.dark[data-country=…]` half** rather than the two that used to. Six light
accents moved (australia, eurozone, hong-kong, malaysia, taiwan, vietnam were 2.94–4.10:1 against
their own white button text; taiwan is the pilot's). `check_design_tokens.py` now **fails** below
4.5:1 instead of reporting below 3:1, and it checks each semantic colour against **its own `-light`
tint** — the tint is the binding background in dark, which is how four colours sat at 3.72–4.13:1
unnoticed. Negative-tested: restoring `--text-muted: #737373` and taiwan's `#0d9488` reproduces the
audit's exact numbers.

**The type scale is not a preference, it was measured.** On `/setup`, **36 of the 51 elements
carrying their own text rendered at 11px or less**. Every step of the scale moved by about a fifth
rather than the floor alone, because five steps used to live between 11 and 15px and lifting only
the smallest would have collapsed the distinctions the design uses. Body is 16px, supporting text
14–15px, 12px is metadata. Verified for overflow on all nine routes in **Thai**, which is the longer
language.

**Tailwind's preflight resets `h1`–`h6` to `font-size: inherit`.** Only the landing page ever styled
its own, so every stage title on all nine screens rendered at exactly body size. That — not the
palette — is the largest single reason the journey read like a different product from the landing
page, and it was invisible in review because the markup was correct all along.

**The tour is a native `<dialog>`.** `role="dialog" aria-modal="true"` says a thing is modal without
making it one: focus stayed on `<body>`, the first Tab went to the navigation behind the scrim, and
Escape did nothing. `showModal()` gives focus containment, inertness and Escape from the platform.
The one thing it does not do is choose where focus lands afterwards — it restores to whatever had it
before, which on a first visit is `<body>` — so the reopen button is always rendered and explicitly
refocused. Verified in a real browser: focusing a nav link behind the open dialog is refused.

**The sidebar and the gate answer from one predicate.** `web/src/shared/stages.ts` holds the
nine-routes-to-five-gate-keys table that used to exist only as literals on each `<StageGate>`;
`routes.tsx` generates its children from it and `AppShell` reads it. A link marked locked is
therefore exactly a link the gate will block, and the prerequisite is named **before** the click.
Do not derive a second copy of that table in the shell — that is the drift this fixes.

**`<details>` hides its contents; it does not avoid building them.** `/places` mounted all 849
catalogue rows and the full provider JSON inside a collapsed report on every visit. Rendering on
first open plus a 50-row page took the screen from ~4900 DOM nodes to **543**.

**The payload half is fixed at the transport boundary without trimming a snapshot.** `rank_candidates`
is 1.19 MB, `get_latest_discovery` 880 KB and `list_candidate_choices` 152 KB on the current scratch
copy of the pilot. Trimming the discovery response at the API boundary is
**wrong, not merely unattractive**: `candidates` is a `Frozen` snapshot and the client is handed the
`sha256` beside it, so shipping a mutilated `data` would put a hash on the wire that does not
describe its payload — the one contract the whole design rests on. A lightweight read is a *new*
method, not a narrower old one, and per-card fetching for the deck is what `WF-048` already paid to
undo. The stdlib HTTP server now sends JSON over 1 KB with `Content-Encoding: gzip` when the browser
accepts it. Those three responses measure **80 KB + 62 KB + 16 KB** compressed on the same data —
about **93% less wire transfer** — while their decoded bytes and sha256 values remain unchanged.

**The landing page no longer says “No upload.”** The trip file and deterministic planner stay local,
but optional provider and model actions do transmit disclosed slices. The first-screen copy now says
that plainly; `/revise` names the exact model boundary (request plus relevant plan slice) and retention
qualification before its opt-in control.

**A capture writes nothing, and that was measured rather than assumed.** Diffing every table across
a full 56-image run found one `open_meteo:forecast` row and one `provider_cache` row per run — free,
invisible on screen (the forecast is `covered: false` until ~13 December), and still the app being
operated rather than observed. The forecast query is now disabled under the capture flag like the
basemap and the summaries prefetch before it. A clean run over the pilot copy now changes **no row
in any of the 23 tables**. The pilot database itself was never opened: `data/tourist.sqlite3` is
still `d91ac5ad…`.

**The money workbook was decided in `WF-030` and never built, until 2026-08-11.** `exporters.py` had
only `plan_workbook_xlsx`, and `_download` matched only `workbook.xlsx` and `checklist.ics` — so the
only way to export split data was inside the plan file, which is precisely the file that ticket says
must not be handed to anyone, because it carries the itinerary, every address and the readiness
evidence. The stated purpose of the second file is that it *can* be: "a money file can be handed to
Mum without handing over the whole itinerary." That capability did not exist.

`money_workbook_xlsx` has four sheets, which the ticket explicitly left open. **Bills** is the ledger
as entered; **Split Detail** is one row per person per bill, long rather than wide because a
person-per-column matrix is unreadable past about six travellers and cannot be filtered to "just
mine"; **Settlement** is the star through the cardholder; **Summary** carries the per-category figures
with the rate provenance under them. Formulas are **live** here — the ticket's own reasoning is that
cross-workbook references are unreliable, so the plan file carries values while this file's rows are
in the same file as its totals.

**It is not gated on the plan, and that is a departure from the letter of `WF-030`.** The ticket says
both files read `build_export_snapshot()`; that function refuses without an active plan and is shaped
around a variant for five of its six sheets. But `/split` gates on a confirmed setup and nothing more,
so bills are entered long before an itinerary is activated — a money file that refused until then
would be unavailable for exactly the stretch of a trip when people are paying for things. So
`exports.build_money_snapshot` is a second builder, and the one-source rule holds **at the source
rather than at the snapshot**: every figure comes from `costs.totals()` and `split.summary()`, which
are already the only derivations of claimed-ness and of a resolved share. Two renderings cannot
diverge when one function computes the number.

Three details worth keeping. **A voided row is carried, marked, and excluded from every total** — a
void is *why a total moved*, which is the one question a shared file is opened to answer, and dropping
it makes the total look wrong to the person who did not do the voiding; the Summary formula sums only
the live rows by name (`=Bills!J2+Bills!J4`), so the exclusion is visible in the spreadsheet itself.
**The word "Removed" is written beside the strikethrough**, because wording alone carrying the state
is this repo's accessibility rule and survives a paste into anything that drops formatting. And
**Split Detail lists people in the row's own participant order**, not the mapping's: `freeze_snapshot`
canonicalises with sorted keys, so reading `shares_thb` directly lists them alphabetically and stops
matching the "Shared by" column beside it — and that order is what the equal-split remainder rule is
documented against.

**`/split` gained the donor's four modes, its cardholder and its two charts on 2026-08-11.** The mode
was previously *inferred* — `participants.length === 1 ? "single_payer" : "equal_all"` — so choosing
one was not something the screen offered, and "we split this three ways but Ake only had a drink"
could not be said at all. The manual panel shows the remainder **while typing** rather than only
refusing on save, because "it does not add up" is far more useful with the number still in front of
you; it tolerates one satang per participant, which is the most a by-hand equal split can be out.

**Map item 5 is answered where the data is.** The donor's donut and bar chart had no planner use *on
`/places`* — the element inventory found no distribution there, which is what that item recorded — but
the split ledger holds two real ones, money per category and money per person, and they are the two
questions the screen is opened with. Both are SVG: `WF-026` fixes the web runtime at six dependencies
and a ring is one `stroke-dasharray` per slice. **The legend carries the name and the number**, so
colour is never the only thing separating two slices — the same rule the map follows with its numbered
list. The six slice colours are ordered so *neighbours* differ in hue rather than the set looking
varied: accent-then-success put teal beside green on the pilot and the swatches were not tellable
apart at 10px, which was caught by looking at the screen rather than by reading the code.

Verified end to end in a browser against a copy: a manual 60/40/0 bar tab saves with its allocation
intact, the settlement moves to `Sister pays you 40`, and the balances still sum to zero.

**A trip may add its own expense categories as of 2026-08-11, and the seven always stay.** Artifact
023 made them a fixed vocabulary shared by both ledgers and both workbooks; a trip that hires skis or
pays a visa agent had nowhere to put that but `other`, which is the category meaning *unclassified* —
so using it for a real recurring expense loses the grouping the sheet exists for.

Three rules hold it together. **The seven are not removable**: they are what an unrecognised tag falls
back to, what `costs.validate_cost` accepts with no trip in hand, and what the four reference
workbooks are matched against — a custom category is an addition, never a replacement. **A category
still on a row cannot be dropped**, which is the same shape as the cardholder's roster check and for
the same reason: `category_for_tag` would silently re-file those rows under `other`, moving someone's
money between groups without saying so; `set_cost_categories` refuses with `category_still_in_use` and
names them. And **a custom category carries its own label**, because a code the owner invented has no
catalogue entry and `copy()` renders a missing code visibly as `⚠ ski_hire` — correct behaviour, wrong
answer, since nothing is actually missing.

`costs.validate_cost` and `split.category_for_tag`/`apply_rates` take the vocabulary as an argument
defaulting to the seven, so every existing caller and all 27 fixtures are untouched.

`web/src/stages/money.tsx`'s `categoryName()` is the one place a category becomes words: built-ins
through the copy catalogue so they translate, custom ones through their stored label. Driving the
screens found **five** places rendering a raw category, not the two the grep first suggested — the
by-category table, the row tags, the donut legend, the filter chips, and the "categories without a
plan" note. The last one is the reason this is worth stating: it was a `.map(copy)` inside a sentence,
which no amount of reading the diff would have surfaced.

**A capture must observe the app, never operate it.** Two things broke that and both showed up as
double-digit baseline drift on screens nobody had edited. The `/places` first-visit tour is suppressed
by `document.documentElement.dataset.capture`, because a fresh Chrome profile is always a first visit
and every capture would otherwise photograph the overlay. And the **summaries prefetch writes** — it
stores a record per place — so photographing `/places` changed what the next photograph would show, and
the gate reported 13% drift that no code caused. Both now check the capture flag. If a screen ever
drifts without a code change again, ask first what that screen *does* on load.

**The self-drifting baselines are fixed as of 2026-08-08 (`WF-048`).** Capture mode already froze CSS
transitions because a screenshot caught mid-fade differs for no code reason; the same argument covers
three values that move on their own. `/itinerary` prints the export timestamp, `/evidence` the running
paid-usage ledger, and both deck and detail render a **remote photograph** — Wikimedia re-encodes a
thumbnail and the identical image returns subtly different, measured at peak 28 with nothing changed.
The two texts carry `data-volatile` and capture mode collapses them to a fixed-width stand-in
(`font-size: 0` plus a `::after`), so the layout around them is still compared exactly and only the
digits are held. Photographs get `opacity: 0`, which keeps the element laid out at its real size — a
layout change still fails, which is the part of a third-party image this gate can meaningfully own.
Verified by recording a paid call between an approve and a compare: the ledger moved
US$2.3255 → US$2.3505 and the gate stayed green. **Nothing was excluded from the comparison and the
tolerance was not widened.**

The superseded note, kept because the reasoning still applies to any value added later:

**Eight of the 36 screen baselines used to drift on their own**, found while re-approving for `WF-048`:
`/evidence` renders the running paid-usage counter and `/itinerary` the export timestamp, so those
images move with the ledger and the clock rather than with the code. `/evidence` crosses the 0.1%
tolerance unaided; `/itinerary` stays under it. Excluding a region from a baseline is a `WF-025`
decision and has not been taken — so expect `evidence-*-en` to go red after any paid call.

Two measured facts from those worth carrying. **`verified` means a provider said so, not that it is
true** — Google returns Mon–Fri 08:30–17:30 with weekends closed for Sun Yat-sen Memorial Hall, which
reads like the administration office rather than the visitor hall. And **an opening fact is a weekly
pattern**, so nothing in the current shape can express "closed 1 January"; `capability_gaps` is empty
for a trip whose likeliest failure is a closure the app cannot represent. Do not close either by
asserting hours a model recalls: the fix has to come from a fetched, citable source or from the owner.
`Lock the Phase 2 slice plan and validation scorecard` is the destination artifact — read it
first: `.wayfinder/artifacts/033-phase-2-slice-plan-and-scorecard.md`.

**Three S6 decisions the owner settled on 2026-08-04, so nothing is waiting on them:**

- **Baseline tolerance is a small allowance, not zero** — the screen gate fails above **0.1% of pixels
  differing** *and* **>8/255 on a channel**, both conditions. Recorded in artifact 025. The element gate
  compares computed-style values and needs no tolerance.
- **The fonts are bundled.** Two variable `woff2` files in `web/public/fonts` (67 KB total, SIL OFL 1.1,
  licence beside them) cover 100-900 for both families, so **no weight can be synthesised**. That closed D8,
  and **the deviation register is now complete: zero outstanding.** Thai has no subset in either family and
  falls through per glyph to a system font, exactly as before.
- **Auto-Bill was never used with real expenses**, so `WF-030`'s pre-archive backup is **discharged**, not
  skipped. S6 may archive the donor whenever it is ready.

**Phase 2 is complete: S0 through S6 are all done as of 2026-08-04.** S6 landed the two-level visual parity
gate and deleted the POC. `scripts/check.py` is **12 stages**, green in ~17s — the twelfth is the
reference-workbook coverage gate.

The parity gate is two levels, and neither is a whole-screen comparison against the donor — Auto-Bill has
two screens and the planner has nine, so that comparison is meaningless:

- **`check_element_parity.py`** diffs the rebuild's *computed style values* against the donor capture by
  declared `derives-from:` ancestor. Exact, no tolerance, and it still works after the donor is archived. A
  difference fails only when unexplained — a registered deviation must actually license the rebuilt value,
  so D2 permits only `{2px, 9999px, 0px}`, D8 only a real token weight, and any shadow blur other than 0 is
  drift whatever the register says.
- **`check_screen_baselines.py`** compares **56** approved images against a fresh capture: 36 desktop
  (9 routes x light/dark x en/th) plus **20 phone** (landing, setup, places, itinerary and the tour,
  same four variants). It catches **drift over time only**. Tolerance is the owner's pair: fail above
  0.1% of pixels differing *and* more than 8/255 on a channel. See
  `artifacts/parity/screen-baselines/README.md` for the two capture races that had to be fixed to
  make it deterministic, and for the negative test.

  **The phone set landed 2026-08-10 because the desktop-only gate was hiding things.** Every
  responsive rule in the stylesheet was unguarded, and a UX audit found a regression living in
  exactly that gap: below 768px the stop-row grid drops to three columns and re-places `code`, but
  never re-placed `.plan-stop-maps` — so "Open in Maps" auto-flowed into the 10px status-dot column
  on every stop of every day, holding text that needs 77px. Nothing failed, because nothing looked.

  **The phone viewport is 500x844 and the number is not a preference.** Headless Chrome on macOS
  clamps its window, and with it the layout viewport, to a 500px minimum — `--window-size=320,844`
  and `--window-size=450,844` both measure 500. Naming the set 390 would be a 500px image with a
  false label, and the next person to "correct" it would get the same 500 back. Every
  `max-width: 768px` rule is still exercised. A true 320–390px reflow check needs device emulation
  over the DevTools protocol and remains a manual step.

  **The tour has a capture seam of its own.** `?baseline_tour=open` forces the first-visit overlay
  on, which `data-capture` otherwise exists to suppress — without it the app's one modal had no
  visual cover at all. It is the inverse of the suppression, not a hole in it: the flag still hides
  the tour everywhere else.

Capturing needs a running server and headless Chrome, so only the *comparison* is a `check.py` stage; it
skips cleanly where nothing has been captured. Baselines are machine-specific by decision — re-approve when
the machine changes rather than widening the tolerance.

**All three of artifact 029's genuinely-UI tests were resolved before the deletion**, not dropped: the
paid-card placement rule is `web/src/stages/s4.test.tsx`, the entry-point smoke test became
`web/src/routes.test.tsx` (nine routes, five gate keys), and the journey walk kept its actions-level body in
`tests/test_workflow.py` while its eight-page render loop became the 36-screen capture. Only
`money_on_screen_is_not_read_as_maths` died, and only because Streamlit's `$`-as-LaTeX bug went with
Streamlit.

**S5 landed the last journey screens on 2026-08-04**
(evidence: `artifacts/validation/2026-08-04-slice-5/notes.md`). Four things from it bind S6:

- **The GenAI surface is opt-in and constrained.** `RevisePage` keeps AI off initially, states the
  approximate price, data slice and retention boundary before enabling the textarea, and calls the
  existing `interpret_revision` action. A supported result creates the same pending typed draft as a
  quick action; unsupported, missing-key, offline, refused and malformed-result paths leave the active
  plan unchanged. The existing consequence preview and explicit Apply remain the only write path.
- **`placeName` / `placeNameFrom` in `web/src/shared/names.ts` is the one place naming happens.** `places`,
  `optimize` and `revise` each had their own copy with a different signature; they are consolidated. A
  consequence or plan row must name a place, never a truncated `place_id`, and divergence here is invisible
  until a screen shows an id.
- **`checklist_vocabulary` is the 60th allowlisted read**, with its orders asserted against the core tuples
  like `setup_vocabulary`. Do not hardcode a board vocabulary in TypeScript.
- **`revision.py` interpolates values into its assumption codes** (`WALKING_MINUTES_PER_LEG_SET_TO_14`), so
  no catalogue entry can exist and that line is permanently the visible-machine-output fallback. The POC
  does the same. Recorded as a pre-existing gap, not a port defect; changing it needs its own decision.

**S4 landed the expensive journey screens on 2026-08-04**
(evidence: `artifacts/validation/2026-08-04-slice-4/notes.md`). Its constraints are:

- **`places` is a functional ranked list, not the deferred card grid.** It preserves all lanes,
  choices, reasons, score breakdowns, provenance and the owner-triggered paid overlay. Every paid
  action shows its estimate immediately before its button; insight and photos stay session-only.
- **`itinerary` reads `build_export_snapshot()`**, never the raw variant. The six row types, fallbacks,
  bilingual stop list, true-relative coordinate SVG, workbook and readiness calendar therefore share
  one set of times and statuses.
- **`check_paid_call` and `build_export_snapshot` are allowlisted reads 58 and 59.** No internal writer
  was exposed and no runtime dependency was added.
- **Five more portable behaviours moved below Streamlit here; the last four followed at S5.** The
  `AppTest` originals were deleted at S6, once all 14 had homes.
- **The visual witness was obtained 2026-08-04 and Gate 1 is now assessable.** Six captures across
  `places` and `itinerary` in both languages, the tile-free numbered map with its duplicated stop list,
  and both `GET` downloads verified over the socket with a bare `GET` to a mutation still refused.
- **The walkthrough figures are reproducible, not inspectable.** Opening `data/tourist.sqlite3` as-is
  gives the sparser stored plan (7 days, 8 rows, three row types, no readiness). The 8 days / 69 rows /
  six row types / 13 readiness items come from re-running optimize → activate → readiness proposal,
  which is what the evidence steps describe. Re-run them before doubting the numbers.
- **Never open `data/tourist.sqlite3` to demonstrate something.** Copy it first. The witness ran on a
  copy, which bumped to 13 and left its own `-pre-v13-` backup at 12 while the original stayed at 12 —
  the first time S2's refuse-on-failure migration ran against real pilot content rather than a fixture.

**S3 landed the cheap journey screens on 2026-08-03**
(evidence: `artifacts/validation/2026-08-03-slice-3/notes.md`). Five things from it bind later work:

- **The setup draft is one object, always sent whole.** `save_setup` defaults every field to empty, so
  a partial payload **erases what it omits**. Five steps are five views over one piece of state, never
  five requests. The draft also carries `owner_nationality` and each member's `nationality`, which
  the POC's setup view dropped on save — readiness reads them, so losing them is not round-tripping whole.
  `SetupPage` sends them; keep it that way.
- **`setup_vocabulary` is the 57th allowlisted method**, a read returning planning modes, accommodation
  statuses, the four tag groups as codes, and countries with **both** language labels plus their cities.
  Both languages in one payload so a language switch never refetches. Its picker orders are explicit
  lists asserted against the core frozensets: a frozenset is right for validation and useless for a
  radio group.
- **The step indicator is step-count-agnostic.** The donor's `.*-4` family hardcoded four; renaming to
  `-5` would hardcode the next wrong number. Clicking a step navigates **backwards only**, kept because
  later steps depend on earlier answers.
- **`copyFrom(table, code, language)`** renders the seven catalogue tables beside `TEXT`. Unknown codes
  still surface as `⚠ CODE`. A flash or any other message must hold a **code**, never rendered text, or
  a language switch cannot re-render it.
- **The accent is destination-driven now.** `AppShell` sets `data-country` on the root from the
  destination's country (D6); an unknown country matches no rule and keeps the house red (D3). **The
  phone sidebar collapse below 992px is a new element** — artifact 028 explicitly left it undesigned —
  so it declares element 17 `.sidebar` as its ancestor and still needs a real-phone capture before the
  parity gate runs.

**`tests/test_ported_behaviours.py` was the S6 deletion checklist, and it is discharged.** It holds the
actions-level homes for the 14 behaviours that used to be asserted through `AppTest`, organised by
provenance on purpose. Nothing is owed; the file stays because the behaviours are real, and its provenance
grouping is the record of where each one came from.

**S2 landed the merge on 2026-08-03** (evidence: `artifacts/validation/2026-08-03-slice-2/notes.md`).
Four things from it bind later work:

- **`travel_planner/split.py` owns all split math** and is pure like the rest of the core. Shares are
  **recomputed on read, never stored**, so there is exactly one rounding rule: the division happens in
  integer satang and the remainder spreads one satang at a time over the first participants in the
  row's own order. That deviates from the donor's dump-it-on-the-first-person and is recorded as a
  deviation, not drift.
- **Schema was 13 at S2; it is 14 since `WF-039`.** `split_rows` and `split_settled_markers` carry **no append-only triggers** by
  decision. `store._copy_before_bump()` copies to `data/tourist-pre-v<n>-<date>.sqlite3` before any
  bump and raises rather than migrating if the copy fails. It is gated on
  `0 < on_disk_version < SCHEMA_VERSION`: version 0 is a database being created and an equal version
  is not a bump, and without that gate every temp database in the suite would leave a junk copy.
  **Schema is 14 as of 2026-08-07**, when `WF-039` added `comfort_acceptances` — mutable and
trigger-free like the split ledger, since withdrawing an acceptance is a correction rather than
history. Rehearsed on a byte-identical copy first, which confirmed one new table and **no row-count
change in any pre-existing table**; `data/tourist-pre-v14-2026-08-07.sqlite3` is the only way back.
It had to land before `WF-024`'s no-schema-change window (29 Dec–4 Jan, the trip itself).
**`data/tourist.sqlite3` was bumped 12 → 13 on 2026-08-04** by owner decision, rehearsed on a
  byte-identical copy first and leaving `data/tourist-pre-v13-2026-08-04.sqlite3` — verified byte-identical
  to the pre-bump file — as the only way back. It happened then rather than nearer the trip because
  `WF-024`'s no-schema-change window, 29 December 2026 to 4 January 2027, **is the trip's own dates**:
  the bump had to precede the window or wait until the trip was over. Evidence in
  `artifacts/validation/2026-08-04-schema-13-bump/`.
- **Claimed-ness is derived in exactly one place: `costs.totals()`**, which returns `claimed_cost_ids`
  for the screen to read. Do not add a second derivation — `split.py` had one and it was deleted for
  the vocabulary-drift reason `WF-018` names. Dependency direction is `split.py → costs.py`; the
  reverse is a cycle, which is why the tag → category map lives in `split.py` and `apply_rates()`
  stamps a resolved `category` before `costs.totals()` sees the row.
- **The settled marker stores the balance it settled**, not a payment, and `settled` is derived by
  comparing it to the current net. So a marker goes stale silently the moment the arithmetic moves,
  with no write-time cascade to keep in sync. **The owner is the cardholder** (`PlannerActions.CARDHOLDER`);
  there is no stored setting and no `delete_split_row` — removing a row voids it.

**A scope cut landed with the slice plan: the PDF and the 9:16 poster are dropped.** `pyproject.toml` goes to
**two** runtime dependencies (`streamlit`, `xlsxwriter`), the whole export-font apparatus is void — do not
build the merged Noto pipeline — and tests went **235 → 230**. The workbook and ICS survive.
**S0 is done as of 2026-08-03**: `exporters.py` is 1136 → 692 lines, and the workbook now localises optimizer
codes through `_code()` as the PDF always did, so a Thai owner still gets Thai where a label exists.

The destination specification is decision-complete. The Python transport adds no runtime dependency; the
browser dependencies live only in `web/package.json`. Build one slice vertically and retain its evidence
before starting the next.

Read the map before touching anything in this area. Work it one ticket per session — claim a ticket by
setting its `assignee:` before doing any work, and only research tickets may be resolved more than one
per session.

> **The owner set that last clause aside on 2026-07-31**, directing seven grilling tickets to be resolved in
> one session (`WF-019`, `WF-022`, `WF-026`, `WF-028`, `WF-025`, `WF-023`, `WF-030`). It was explicit each
> time, not drift. The rule still stands as written unless the owner says otherwise — do not assume a
> standing exception.

Locked by the destination interview, so not open for re-litigation inside a ticket:

- The planning core, `actions.py`, and `store.py` remain the domain layer behind a thin local HTTP layer.
  React replaces the `views/`, `app.py`, and `ui/` presentation surface. The deterministic optimizer, the
  hash gates, the append-only plan history, and the 248 current tests all survive the redesign. *(248 was
  the count when this was locked; the suite is 287 after S2 and none of the originals were rewritten.)*
- **Two linked ledgers**, not one merged record: cost rows stay the budget and estimate truth, the split
  ledger records actual group spend. Reconciling them is now **decided**, not open — see the claim rule below.
- Everything lands in this repository (`api/` + `web/`). `Auto-Bill-Splitter` is a read-only donor, then
  archived.
- Tokens are **rebuilt** in Tailwind, so visual parity with Auto-Bill is a hard gated requirement rather
  than an aspiration — same palette, same zero-blur hard offset shadows, same fonts, same elements.
- Bilingual `en`/`th` stays mandatory, and the key-parity test keeps running.
- Local-only and owner-led: `localhost`, SQLite on disk, no accounts, no auth.
- **Streamlit was the POC that proved the core works — not a product, not a pilot fallback.** `views/`,
  `app.py` and `ui/` were **deleted at S6 on 2026-08-04** (2,951 lines) once the webapp reached parity
  across all nine routes. There is no fallback and that is deliberate. Schema is fully
  unconstrained — there is no tag, no downgrade path, no restorable old checkout. The webapp is the
  **committed** vehicle for the pilot with a **1 November 2026** checkpoint; not on track means Taipei is
  planned by hand in Excel, as the four reference trips were.
- **Validation compares generated output against the four reference workbooks in
  `data/reference-itineraries/`, programmatically — never against Streamlit's output.** Their four
  recurring sheets (`ตารางเวลา`, `ค่าใช้จ่าย`, `♢ To-Do List`, `☺ Things to Bring`) are the merged app's
  entire output surface, so they validate the merge itself. Comparison asserts structural coverage, not
  cell equality: the workbooks are hand-made and inconsistent. Reading them needs `openpyxl` as a **dev**
  dependency; the Python runtime dependencies stay untouched. See
  `.wayfinder/artifacts/022-streamlit-poc-retirement-and-pilot-commitment.md`.

Already decided, and binding on any future implementation:

- Split math lives in a new pure `travel_planner/split.py` beside `costs.py`, under the same no-Streamlit,
  no-SQLite, no-HTTP rule. The API returns resolved shares, balances, and settlement; the frontend renders
  numbers it was given. One rounding implementation, so the screen and the workbook cannot disagree by a
  satang. (Originally "and the PDF"; the PDF was dropped in S0 and the reasoning is unchanged.)
- Settlement is a star through the main cardholder with fronted cash netted off. Rows are editable and
  void rather than delete, so the split ledger takes **no** append-only triggers.
- The local API is a stdlib `ThreadingHTTPServer` with **zero new runtime dependencies**, dispatching
  `POST /api/<method>` straight onto `PlannerActions`. Two rules from that contract are safety-critical, not
  taste: **the dispatch table is an explicit literal allowlist, never introspection**, because
  `save_plan_version` writes an arbitrary snapshot as an activated immutable version with no optimizer
  validation and `record_paid_call` forges append-only ledger rows — `dir()` would expose both. And a
  snapshot `sha256` is **exposed but never accepted as an argument**; the server re-derives every hash
  itself. Full contract in `.wayfinder/artifacts/019-local-api-contract.md`.
- Refusals use stable codes: the migration landed in S1. `actions.py` now has one `ValueError`, an
  internal provider-result invariant caught inside discovery; every owner-visible refusal is a
  `PlannerRefusal`. `tests/test_foundation.py` discovers all **38** codes and requires bilingual copy,
  while `tests/test_api.py` pins the status map.
- The webapp stack: **TypeScript, react-router, TanStack Query, Tailwind v4 configured in CSS**, npm with
  Node pinned by `.nvmrc`. `web/src/` is organised **by stage** beside `shared/`, `api/` and `i18n/`.
  ESLint with `react-hooks`, `tsc` for types, no formatter. `web/dist` is not committed. Six web runtime
  dependencies, ten dev — and **Python stays at four**. See
  `.wayfinder/artifacts/026-webapp-stack-and-layout.md`.
- Two rules from that ticket are correctness, not taste. **`retry: false` is TanStack Query's default
  here**: the library's 3 retries would burn both of Overpass's 2 concurrent slots on a 34 s call and
  double-spend paid calls against the US$10 cap. And **`save_setup` takes all 18 fields every time, each
  defaulting to empty, so a partial payload silently erases what it omits** — the setup form holds one
  draft object and always sends it whole.
- The webapp's IA: **9 stage routes under `/trips/:tripId/`** resolving to **5 gate keys**, in the same two
  *(**10 routes** since `/stay` landed on 2026-08-14 at the owner's asking; still 5 gate keys, and
  `stay` borrows the `optimize` key. The decision below is otherwise unchanged.)*
  BUILD/USE sections, with the eight ported slugs unchanged. The trip id lives in the **path** because all
  51 methods take `trip_id` and TanStack keys must include it. One `<StageGate>` wrapper renders the blocked
  explanation **in place** — `require()` never redirected, and only `/` does, to `journey["next"]`. Setup is
  one route with five steps in state. **Costs and split are two cross-linked screens**: costs holds estimates
  for the drafted plan, split holds actual bills split per person. Navigation adapts Auto-Bill's existing
  sidebar shell. See `.wayfinder/artifacts/028-webapp-information-architecture.md`.
- `shared.journey()` was 74 lines of business logic in the POC's UI layer; it moved into
  `PlannerActions.journey()` as the 51st allowlisted method, which is why deleting `ui/` cost nothing. It currently reaches into the private
  `_optimizer_input`, invents the gap code `OPENING_EVIDENCE_MISSING` that the core never emits, and
  duplicates the rated-place filter `rank_candidates` enforces. React cannot recompute it — that would
  require exposing `_optimizer_input`.
- The visual parity gate: the **token contract is the target, and it must be completed before the gate can
  run** — 39 JSX classes have no CSS rule (not the 18 or ~28 earlier tickets claimed) across 114 inline
  style sites. Checking is screenshot comparison at two levels: **element-level captures of the 41 lifted
  elements, which must be taken before `Auto-Bill-Splitter` is archived**, plus 4 screen baselines per route
  (light/dark × en/th) that catch drift only. New elements pass on token conformance plus a declared
  ancestor. Auto-Bill's defects are **fixed and recorded as deviations D1–D7** — without that register every
  fix reads as a parity failure. Radius unifies on `2px`. See
  `.wayfinder/artifacts/025-visual-parity-gate.md`.
- **The Python exporters survive; `excelExporter.js` is deleted and `exceljs`/`file-saver` never join `web/`.**
  One generator is the only way `build_export_snapshot()`'s one-snapshot rule can hold, the 25 export tests
  have no JS counterpart, and only Python has the ICS. *(The PDF-and-poster half of that argument died with
  S0; the conclusion stands on the other two grounds.)* **Two workbooks**: a plan file and a
  shareable money file, both from the same snapshot — so the money file carries no itinerary, no addresses and
  no readiness evidence. Planned-versus-actual lands in the plan workbook's Costs sheet as **values, not
  formulas**, because there is nothing in the same file to point at; an export is a snapshot, not a live
  document. Downloads are dedicated `GET` routes with `Content-Disposition` — **an exception to the RPC
  convention, and bare `GET` may reach downloads and nothing else**, never a mutation or a paid call, because
  a `GET` carries no `Content-Type` for the guard to check. See
  `.wayfinder/artifacts/030-exporter-and-download-contract.md`.
- **Copy moves to one JSON catalogue that both renderers read** — Python for the exports, TypeScript for the
  screen — because `_export_labels()` is `TEXT[lang] | OPTIMIZER_CODE_TEXT[lang]`, so Python needs it whatever
  React does. **No i18n library**: importing JSON `as const` checks keys at compile time, which beats runtime
  lookup and is exactly the guarantee whose absence hid the 24 missing English strings. The parity test grows
  to all eight tables; the fallback becomes visibly machine output (`⚠ ACCESS_UNVERIFIED`); `CATEGORY_TEXT` is
  the one documented exemption, with derived English plus a `place_of_worship` override. **Emoji decorate and
  never carry meaning alone** — a flag-only cell becomes an empty cell in the **workbook**, since `_labels()`
  still strips pictographs after S0. See
  `.wayfinder/artifacts/027-bilingual-copy-pipeline.md`.
- Testing after `AppTest`: exposure is **7%** — 18 tests of the 235 that existed when it was measured, not 12
  of 15 files — so the great majority survive untouched. The suite is **230** after S0. Of the 18, **14 port down** to actions/core/exports and are moved **before** anything is deleted,
  **3 are genuinely UI**, and 1 dies with Streamlit's `$`-as-LaTeX workaround. API contract tests are
  `unittest` at two levels: dispatch directly, plus a real server on **port 0**, because the `Content-Type`
  guard, the `Host` allowlist and the bare-`GET` rule are **security controls** unreachable without a socket.
  **Vitest** for frontend units; the journey walk comes free from the parity harness. One green command,
  `scripts/check.py`. See `.wayfinder/artifacts/029-test-strategy-after-apptest.md`.
- Migration: **no importer is built.** `data/tourist.sqlite3` holds exactly **one trip — the Taipei pilot** —
  and Auto-Bill keeps one trip's data at a time, so there is nothing to merge it into. The backup JSON is an
  **archive record**, and the split ledger starts empty. A row arriving with known THB and no rate keeps it as
  a **locked `actual_thb`**; fabricating an `as_of` would put a made-up date in a field that means something
  else. **Every schema bump copies the database to `data/tourist-pre-v<n>-<date>.sqlite3` first and refuses to
  proceed if the copy fails** — WF-022 removed the downgrade path, so that copy is the only way back. And
  **no schema change between 29 December 2026 and 4 January 2027**: a one-way bump on the only trip in the
  file, while that trip is happening abroad, is not worth any feature. See
  `.wayfinder/artifacts/024-migration-path.md`.
- Offline assets: **no tile map.** The exports never had one — they print numbered stops with coordinates —
  and the only tile use was `st.map`, so the numbered stop list *is* the map and screen and export agree by
  construction. Fonts **self-host as `woff2`** plus a **merged Noto TTF for exports**, because today exports
  work only on a machine that happens to have proprietary `Arial Unicode.ttf` and `resolve_font()` raises
  rather than rendering tofu. **Void after S0** — the PDF and poster are gone, so there is no export font at
  all. Do not build the merged Noto pipeline. **Bold monospace becomes real.** `flagcdn.com` becomes a local sprite where a
  missing flag shows the country name alone. **Everything local works offline** — the optimizer and
  `revision.py` are pure — **and network-requiring actions say so before being pressed.** The colour source is
  **`tokens.css`, in CSS not JSON**. See `.wayfinder/artifacts/034-offline-asset-policy.md`.
- **The donor capture happened on 2026-08-04** — `artifacts/parity/2026-08-04-auto-bill-donor/` holds 431
  style records across both themes, 97 inline-style sites, resolved tokens per theme and **35 of the 41
  elements fully covered**, with the six gaps named. Diff S6's rebuild against `computed-styles.json` rather
  than trying to recreate the donor. **The backup JSON could not be taken: the donor held no trip data** —
  `alipay_splitter_settings` absent, `alipay_splitter_transactions` empty. If Auto-Bill was ever used for
  real, that data is in another browser profile and is exportable until S6 archives the donor; the files in
  that bundle named `synthetic-*` are a schema record from a trip the capture created, **not** the owner's
  archive. One measured finding binds S6: **the donor's accent is `#dc2626` in both themes**, which is the
  evidence for deviation D1.
- **Two things must be taken from `Auto-Bill-Splitter` before it is archived**: a backup JSON per trip (kept as
  an archive record — a file survives archiving, `localStorage` does not) and the 41 lifted element captures
  for the parity gate. Both need the donor runnable. The token extraction is **done**, so it no longer does.
- The token contract's inline-only layer is extracted (§10). Two counts worth knowing: of the 39 classes with no
  CSS rule, **only 23 carry any styling** — 16 are bare containers with nothing to port — and **not one
  hardcoded colour appears in any of the 114 inline sites**, so the off-token colour problem is entirely in the
  stylesheet (41 literals, 75 uses). Auto-Bill has **no tab element** and `/split`'s allocation-mode views are
  **bare containers**, so both must be designed rather than recovered.
- Cost/split reconciliation: **a split row may claim a cost row via one optional `cost_id`, and the claimed
  row defers its actual.** Nothing is added to the cost row and `payment_state` is untouched — claimed-ness is
  derived — so `planned` is every cost row and `actual` is non-voided split rows **plus unclaimed paid cost
  rows**, making double counting structurally impossible. `costs.totals()` **gains** `planned_thb` and
  `actual_thb` and redefines nothing, because its `estimated_thb` sums non-paid rows only and so is not the
  plan figure. The seven categories become the default tag vocabulary. Split rows inherit the cost rate
  snapshot with **`buffer_percent` skipped**. Gaps warn and never block. See
  `.wayfinder/artifacts/023-cost-and-split-reconciliation.md`.
- **`group_preference_weights` is not a cost weight.** `setup.py:93`–`97` gives the owner 0.5 and members
  0.5 between them, it feeds only `ranking.py`, and it expresses *taste*. Using it for money would charge the
  owner half the trip. Estimated per-person is `planned_thb / headcount`; actual per-person comes from
  `split.py`'s resolved shares.
- **Colour gets one machine-readable source that both renderers read.** `exporters.py` hardcodes 8 hexes
  across 17 occurrences in a cool blue-grey palette matching nothing in Auto-Bill, and
  `views/itinerary.py:94,104` adds three pin hexes — so the workbook looks like a different product
  *(after S0 only one hex remains, the poster having taken 16 of the 17 with it)*, and `WF-022` already made them a pilot-ready gate. Same reasoning as `WF-018`'s single
  rounding implementation.
- `.wayfinder/artifacts/` holds the Auto-Bill token contract, the element inventory matrix, the local API
  contract, the POC-retirement decision, the webapp stack, the information architecture, and the parity
  gate. Consult them instead of re-reading 2458 lines of `index.css` — and read the correction block at the
  top of the token contract before trusting its counts or its Tailwind config draft.
