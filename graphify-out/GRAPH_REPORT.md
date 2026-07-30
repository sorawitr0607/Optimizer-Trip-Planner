# Graph Report - /Users/t1ct1ch20375754/Documents/Thaksin/ML/Personal_Project/Tourist/Optimizer-Trip-Planner  (2026-07-30)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1064 nodes · 2672 edges · 62 communities (45 shown, 17 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 209 edges (avg confidence: 0.52)
- Token cost: 135,252 input · 19,623 output · about US$0.0855 (cumulative)

## Graph Freshness
- Built from commit: `9560abc1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]

## God Nodes (most connected - your core abstractions)
1. `PlannerActions` - 196 edges
2. `SQLiteStore` - 73 edges
3. `ProviderUnavailable` - 50 edges
4. `optimize_trip()` - 36 edges
5. `ProviderBudgetExceeded` - 34 edges
6. `plan_pdf()` - 27 edges
7. `OpenStreetMapProvider` - 26 edges
8. `freeze_snapshot()` - 25 edges
9. `plan_workbook_xlsx()` - 24 edges
10. `_candidate_id()` - 23 edges

## Surprising Connections (you probably didn't know these)
- `ChecklistGenerationTest` --uses--> `PlannerActions`  [INFERRED]
  tests/test_checklist.py → travel_planner/actions.py
- `ChecklistDiffAndReadinessTest` --uses--> `PlannerActions`  [INFERRED]
  tests/test_checklist.py → travel_planner/actions.py
- `ChecklistPersistenceTest` --uses--> `PlannerActions`  [INFERRED]
  tests/test_checklist.py → travel_planner/actions.py
- `ChecklistLocalizationTest` --uses--> `PlannerActions`  [INFERRED]
  tests/test_checklist.py → travel_planner/actions.py
- `ChecklistExportTest` --uses--> `PlannerActions`  [INFERRED]
  tests/test_checklist.py → travel_planner/actions.py

## Import Cycles
- 2-file cycle: `travel_planner/__init__.py -> travel_planner/actions.py -> travel_planner/__init__.py`
- 3-file cycle: `travel_planner/__init__.py -> travel_planner/actions.py -> travel_planner/providers.py -> travel_planner/__init__.py`
- 3-file cycle: `travel_planner/__init__.py -> travel_planner/actions.py -> travel_planner/interpret.py -> travel_planner/__init__.py`
- 4-file cycle: `travel_planner/__init__.py -> travel_planner/actions.py -> travel_planner/providers.py -> travel_planner/interpret.py -> travel_planner/__init__.py`

## Hyperedges (group relationships)
- **Trip Planning Pipeline Stages** — claude_travel_planner_setup, claude_travel_planner_discovery, claude_travel_planner_ranking, claude_travel_planner_optimizer, claude_travel_planner_actions [EXTRACTED 1.00]

## Communities (62 total, 17 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (30): Connection, Row, Application actions coordinating the domain core and SQLite adapter., CandidateChoice, ChecklistItem, DiscoveryRun, freeze_snapshot(), FrozenSnapshot (+22 more)

### Community 1 - "Community 1"
Cohesion: 0.15
Nodes (55): _access_gap(), _activity_route(), _append_wait(), _apply_physical_load_limit(), _best_inbound_route(), _best_route(), _buffer_item(), _build_day() (+47 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (33): ActivePlanViewTest, export_for(), ExportSnapshotTest, FallbackAndAnchorTest, plan_payload(), planner_input(), AppTest, _text() (+25 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (9): fixture(), OptimizerCoreTest, ConsequenceTest, OperationContractTest, planner_input(), RevisionFlowTest, RevisionViewTest, optimize_trip() (+1 more)

### Community 4 - "Community 4"
Cohesion: 0.13
Nodes (32): Counter, candidate(), RankingCoreTest, setup_payload(), build_ranking(), candidates_by_id(), _city_icon(), _distance_metres() (+24 more)

### Community 5 - "Community 5"
Cohesion: 0.10
Nodes (31): Reusable core and local application services for the travel planner., allowed_place_ids(), _assert_clean(), build_payload(), interpret_response(), Any, Free text to one typed revision operation.  Pure: no Streamlit, SQLite, provider, The stable IDs the model was shown; it may name no other. (+23 more)

### Community 6 - "Community 6"
Cohesion: 0.13
Nodes (22): RuntimeError, annotate_report_cost(), build(), deduplicate_nodes(), extracted_edge_issues(), main(), normalize_raw_graph(), openai_key() (+14 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (29): actions(), _candidate_name(), _category_text(), chosen(), _empty_setup(), _explain(), journey(), language() (+21 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (6): _app_text(), ChecklistDiffAndReadinessTest, ChecklistGenerationTest, ChecklistLocalizationTest, ChecklistPersistenceTest, setup_payload()

### Community 9 - "Community 9"
Cohesion: 0.13
Nodes (12): ExtractionTest, One model call turns free text into a typed operation, then previews it., OpenAIRevisionInterpreter, ProviderBudgetExceeded, Low-volume worldwide place discovery from OpenStreetMap., The monthly paid cap would be crossed; this is a budget stop, not an outage., Free-text interpretation is unavailable, with the reason named.      `cause` is, One structured-output call that chooses a typed revision operation.      The mod (+4 more)

### Community 10 - "Community 10"
Cohesion: 0.16
Nodes (22): FPDF, _code(), _coordinates(), _fallback_line(), _item_line(), _pdf_heading(), _pdf_line(), plan_pdf() (+14 more)

### Community 11 - "Community 11"
Cohesion: 0.15
Nodes (24): _booking_places(), diff_proposal(), due_date_for(), _generated(), _is_due_soon(), _is_overdue(), _nationality(), _nationality_groups() (+16 more)

### Community 12 - "Community 12"
Cohesion: 0.16
Nodes (10): _comfort_thresholds(), Any, Unexpired normalized routes; an expired leg is no longer verified., Add or edit one board item, generated or owner-authored., Move an item to verified by recording its official source., The interval valid on every trip date, per place, with its reason., Unexpired zone evidence, or None. An expired zone is not verified., _simple_interval() (+2 more)

### Community 13 - "Community 13"
Cohesion: 0.16
Nodes (12): _address(), _category(), _category_accepts_primary_type(), _distance_metres(), _name_similarity(), _point_key(), ProviderUnavailable, Any (+4 more)

### Community 14 - "Community 14"
Cohesion: 0.13
Nodes (7): CostViewTest, OptimizerActionsTest, Provider, RankingActionsTest, PlannerActions, Path, Only the owner may raise the stop threshold.

### Community 15 - "Community 15"
Cohesion: 0.12
Nodes (8): Fetch walking routes between the selected places, sparsely and capped., Selected places that carry coordinates, deterministically ordered., Refuse a call that would cross the cap, then record what it cost., Record the sourced, timestamped rates costs convert against., Fetch a session-only photo/rating/review overlay for one visible card., Fetch opening hours for the selected places, one paid call each., Look up the destination's IANA zone once, from its discovered centre., The centre of the discovered coverage box, or a selected place.

### Community 16 - "Community 16"
Cohesion: 0.21
Nodes (20): Project agent notes, Set the Phase 1 destination and pilot rules, Verify permitted live travel data and cost limits, Establish Taipei New Year countdown evidence and refresh timing, Choose the Phase 1 source stack and evidence policy, Define trustworthy attraction coverage and card ranking, Define the strong cross-day optimization contract, Prototype the owner-led setup and confirmation flow (+12 more)

### Community 17 - "Community 17"
Cohesion: 0.13
Nodes (6): EvidenceUiTest, FakeTimeZoneProvider, The evidence view had no render test, so its layout was unverified., TimeZoneTest, GoogleTimeZoneProvider, The destination's IANA time zone, from coordinates.      A paid, single-value lo

### Community 18 - "Community 18"
Cohesion: 0.32
Nodes (17): _condition_holds(), _has_verified_entrance(), _high_heat(), _hotel_id(), main(), _meal_inside_window(), _minutes(), _outcome_holds() (+9 more)

### Community 19 - "Community 19"
Cohesion: 0.17
Nodes (6): google_payload(), NormalizationTest, period(), ReductionTest, GooglePlacesOpeningHoursProvider, Opening hours for one place, from a licensed live overlay.      Text search carr

### Community 20 - "Community 20"
Cohesion: 0.20
Nodes (3): Request, ConcreteProviderTest, OpenStreetMapProvider

### Community 21 - "Community 21"
Cohesion: 0.13
Nodes (9): ChecklistExportTest, checklist_ics(), _ics_fold(), _ics_text(), All-day calendar entries for every dated readiness task.      All-day VEVENTs ra, Escape per RFC 5545; an unescaped comma silently truncates a field., Fold to 75 octets; a long unfolded line makes some importers reject the file., _plan_documents() (+1 more)

### Community 22 - "Community 22"
Cohesion: 0.12
Nodes (14): Local Streamlit entry point for the personal travel planner.  This script owns o, Name and destination, but never the same text twice.      An unnamed trip takes, _trip_label(), Optimizer Trip Planner README, city_options(), country_label(), country_options(), destination_text() (+6 more)

### Community 23 - "Community 23"
Cohesion: 0.18
Nodes (6): ProvisionalDerivationTest, A plan may only be Ready once the owner has confirmed the basics., FakePlaceProvider, FakeRouteProvider, Stands in for OpenRouteService; tests never touch the network., FullWorkflowTest

### Community 24 - "Community 24"
Cohesion: 0.17
Nodes (15): date, time, _date_value(), _time_value(), _confirm(), _edited_values(), _go(), Trip basics, travellers, and confirmation. The first stage.  Five short editable (+7 more)

### Community 25 - "Community 25"
Cohesion: 0.28
Nodes (14): build_report(), check_google_places(), check_google_routes(), check_open_meteo(), check_openrouteservice(), check_overpass(), configured_status(), load_keys() (+6 more)

### Community 26 - "Community 26"
Cohesion: 0.15
Nodes (5): Actions offered for the active plan. None of them needs a model., Build the one pending preview. The active plan is never touched here., Apply the pending preview as a new immutable version, with history., Deterministic reasons for the active plan. No model involved., Verified operational facts that justify a booking or access task.

### Community 27 - "Community 27"
Cohesion: 0.16
Nodes (6): CardEnrichmentTest, FakeCardProvider, RankingUiTest, GooglePlacesCardProvider, One owner-triggered live card overlay: photo, rating, and reviews.      The resp, Resolve one photo resource without exposing the server key to the UI.

### Community 28 - "Community 28"
Cohesion: 0.22
Nodes (12): apply_rates(), _currency(), new_rate_snapshot(), Any, Owner-recorded trip costs in THB plus their original currency.  Pure: no Streaml, Resolve each row's THB value against one rate snapshot., Estimated and paid THB totals, plus the rows no rate could cover., One timestamped set of THB-per-unit rates, with an optional buffer. (+4 more)

### Community 29 - "Community 29"
Cohesion: 0.22
Nodes (13): check_allowed(), month_of(), new_entry(), price_for(), Any, Paid-provider usage ledger and the monthly spend cap.  Pure: no Streamlit, SQLit, Decide one prospective paid call before it is made.      A free-tier operation i, One ledger row. Detail never carries a key, only redacted context. (+5 more)

### Community 30 - "Community 30"
Cohesion: 0.23
Nodes (3): ConversionTest, rates(), RateSnapshotTest

### Community 32 - "Community 32"
Cohesion: 0.23
Nodes (3): model_reply(), A live model returns factor: null for "cut down the walking"., ResponseValidationTest

### Community 33 - "Community 33"
Cohesion: 0.21
Nodes (3): FakePlaceProvider, SchemaMigrationTest, SetupDiscoveryTest

### Community 34 - "Community 34"
Cohesion: 0.21
Nodes (3): entry(), PricingTest, ThresholdTest

### Community 35 - "Community 35"
Cohesion: 0.19
Nodes (11): _day_poster(), _export_labels(), _optimizer_code(), _plan_item_name(), Interface copy plus optimizer-code wording, so documents match the app., The half-day's fallback, with its trigger, swap, and displaced selection., One compact export-snapshot row; details stay behind progressive disclosure., _render_fallback() (+3 more)

### Community 36 - "Community 36"
Cohesion: 0.23
Nodes (5): ArtifactTest, A formula with no cached value reads blank until the app recalculates., words['x'] with no default raises when a caller passes no labels., plan_workbook_xlsx(), The six agreed sheets for the active plan only, with working formulas.

### Community 38 - "Community 38"
Cohesion: 0.25
Nodes (3): Cost rows with their THB value resolved against the rate snapshot., Preview the generated board against what is already saved., Apply the previewed changes. A removal is dismissed, never deleted.

### Community 39 - "Community 39"
Cohesion: 0.20
Nodes (9): _day(), day_poster_png(), _labels(), Path, Merge caller labels over the defaults, minus glyphs no export font has.      The, Return a Unicode TTF able to draw the selected language and local names., One 9:16 share poster for a single day: identity, highlights, load, risk., resolve_font() (+1 more)

### Community 40 - "Community 40"
Cohesion: 0.22
Nodes (3): NormalizationTest, OpenRouteServiceProvider, Foot-walking routes from OpenRouteService, normalized for the planner.      A ro

### Community 44 - "Community 44"
Cohesion: 0.28
Nodes (8): display_consequence(), display_title(), _localized(), Localized task wording, or the stored English literal as a fallback.      Templa, Localized consequence; a template may vary it per generated variant., One board row: state, deadline, consequence, and its evidence controls., _render_checklist_item(), The pre-trip readiness board.

### Community 45 - "Community 45"
Cohesion: 0.47
Nodes (8): build_candidate_catalog(), _candidate(), _distance_metres(), _merge(), _name_key(), _occupied_cells(), Any, Provider-neutral candidate identity, conservative dedupe, and coverage reporting

### Community 46 - "Community 46"
Cohesion: 0.31
Nodes (8): common_interval(), google_day(), intervals_by_date(), Any, Weekly opening periods to the per-date interval the optimizer can use.  Pure: no, Google Places numbers days from Sunday; Python's isoweekday from Monday., The open windows on each trip date, empty where the place is closed., Reduce a weekly schedule to one interval valid on every trip date.

### Community 51 - "Community 51"
Cohesion: 0.70
Nodes (4): find_forbidden_keys(), main(), Any, validate()

### Community 52 - "Community 52"
Cohesion: 0.50
Nodes (3): ChecklistViewTest, AppTest, _text()

### Community 54 - "Community 54"
Cohesion: 0.40
Nodes (5): _draw_block(), _ellipsize(), fit_lines(), Break text to fit max_width, ellipsizing once max_lines is reached.      Pillow, Draw text inside max_width and return the y below the last line.

## Knowledge Gaps
- **4 isolated node(s):** `tourist-planner`, `Local Markdown Wayfinder tracker`, `Slice 5 and 6 implementation evidence`, `Project agent notes`
  These have ≤1 connection - possible missing edges or undocumented components.
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PlannerActions` connect `Community 14` to `Community 0`, `Community 38`, `Community 40`, `Community 9`, `Community 12`, `Community 13`, `Community 15`, `Community 17`, `Community 19`, `Community 20`, `Community 56`, `Community 26`, `Community 27`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `optimize_trip()` connect `Community 3` to `Community 1`?**
  _High betweenness centrality (0.010) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `PlannerActions` (e.g. with `CandidateChoice` and `DiscoveryRun`) actually correct?**
  _`PlannerActions` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `SQLiteStore` (e.g. with `CandidateChoice` and `ChecklistItem`) actually correct?**
  _`SQLiteStore` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Local Streamlit entry point for the personal travel planner.  This script owns o`, `Name and destination, but never the same text twice.      An unnamed trip takes`, `tourist-planner` to the rest of the system?**
  _164 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06522196507468966 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.1487012987012987 - nodes in this community are weakly interconnected._