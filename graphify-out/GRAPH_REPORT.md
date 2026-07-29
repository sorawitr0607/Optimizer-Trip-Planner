# Graph Report - /Users/t1ct1ch20375754/Documents/Thaksin/ML/Personal_Project/Tourist/Optimizer-Trip-Planner  (2026-07-29)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 939 nodes · 2401 edges · 42 communities (37 shown, 5 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 178 edges (avg confidence: 0.52)
- Token cost: 128,630 input · 16,763 output · about US$0.0782 (cumulative)

## Graph Freshness
- Built from commit: `a2d59f6c`
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

## God Nodes (most connected - your core abstractions)
1. `PlannerActions` - 181 edges
2. `SQLiteStore` - 72 edges
3. `ProviderUnavailable` - 37 edges
4. `optimize_trip()` - 36 edges
5. `ProviderBudgetExceeded` - 31 edges
6. `freeze_snapshot()` - 25 edges
7. `plan_pdf()` - 25 edges
8. `_candidate_id()` - 23 edges
9. `OpenStreetMapProvider` - 23 edges
10. `plan_workbook_xlsx()` - 22 edges

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
- 3-file cycle: `travel_planner/__init__.py -> travel_planner/actions.py -> travel_planner/interpret.py -> travel_planner/__init__.py`
- 3-file cycle: `travel_planner/__init__.py -> travel_planner/actions.py -> travel_planner/providers.py -> travel_planner/__init__.py`
- 4-file cycle: `travel_planner/__init__.py -> travel_planner/actions.py -> travel_planner/providers.py -> travel_planner/interpret.py -> travel_planner/__init__.py`

## Hyperedges (group relationships)
- **Phase 1 Pipeline Stages** — travel_planner_setup, travel_planner_discovery, travel_planner_ranking, travel_planner_optimizer, travel_planner_actions_planneractions [EXTRACTED 1.00]

## Communities (42 total, 5 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (30): Connection, Row, Application actions coordinating the domain core and SQLite adapter., CandidateChoice, ChecklistItem, DiscoveryRun, freeze_snapshot(), FrozenSnapshot (+22 more)

### Community 1 - "Community 1"
Cohesion: 0.14
Nodes (57): _time_value(), time, _access_gap(), _activity_route(), _append_wait(), _apply_physical_load_limit(), _best_inbound_route(), _best_route() (+49 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (13): Exception, ExtractionTest, FakeInterpreter, InterpretFlowTest, model_reply(), PayloadTest, A live model returns factor: null for "cut down the walking"., ResponseValidationTest (+5 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (12): fixture(), OptimizerActionsTest, OptimizerCoreTest, Provider, RankingActionsTest, ConsequenceTest, OperationContractTest, planner_input() (+4 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (33): ActivePlanViewTest, export_for(), ExportSnapshotTest, FallbackAndAnchorTest, plan_payload(), planner_input(), AppTest, _text() (+25 more)

### Community 5 - "Community 5"
Cohesion: 0.10
Nodes (40): Counter, candidate(), RankingCoreTest, setup_payload(), build_candidate_catalog(), _candidate(), _distance_metres(), _merge() (+32 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (17): entry(), LedgerPersistenceTest, PricingTest, ThresholdTest, check_allowed(), month_of(), new_entry(), price_for() (+9 more)

### Community 7 - "Community 7"
Cohesion: 0.10
Nodes (31): Reusable core and local application services for the travel planner., allowed_place_ids(), _assert_clean(), build_payload(), interpret_response(), Any, Free text to one typed revision operation.  Pure: no Streamlit, SQLite, provider, The stable IDs the model was shown; it may name no other. (+23 more)

### Community 8 - "Community 8"
Cohesion: 0.13
Nodes (29): _code(), _coordinates(), _day(), day_poster_png(), _draw_block(), _ellipsize(), _fallback_line(), fit_lines() (+21 more)

### Community 9 - "Community 9"
Cohesion: 0.15
Nodes (11): Request, ConcreteProviderTest, _address(), _category(), OpenStreetMapProvider, ProviderUnavailable, Any, Provider payload to one normalized route record, or a refusal. (+3 more)

### Community 10 - "Community 10"
Cohesion: 0.09
Nodes (6): _app_text(), ChecklistDiffAndReadinessTest, ChecklistGenerationTest, ChecklistLocalizationTest, ChecklistPersistenceTest, setup_payload()

### Community 11 - "Community 11"
Cohesion: 0.12
Nodes (10): ProvisionalDerivationTest, A plan may only be Ready once the owner has confirmed the basics., ReductionTest, FakePlaceProvider, FakeRouteProvider, FakeTimeZoneProvider, Stands in for OpenRouteService; tests never touch the network., ProviderBudgetExceeded (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.14
Nodes (25): _booking_places(), diff_proposal(), due_date_for(), _generated(), _is_due_soon(), _is_overdue(), _localized(), _nationality() (+17 more)

### Community 13 - "Community 13"
Cohesion: 0.16
Nodes (17): RuntimeError, annotate_report_cost(), build(), extracted_edge_issues(), main(), normalize_raw_graph(), openai_key(), Find lost pairs or relations not present in the raw DiGraph variants. (+9 more)

### Community 14 - "Community 14"
Cohesion: 0.13
Nodes (7): FakeHoursProvider, google_payload(), NormalizationTest, OpeningRefreshTest, period(), GooglePlacesOpeningHoursProvider, Opening hours for one place, from a licensed live overlay.      Text search carr

### Community 15 - "Community 15"
Cohesion: 0.12
Nodes (6): CostPersistenceTest, CostViewTest, FoundationTest, RankingUiTest, PlannerActions, Only the owner may raise the stop threshold.

### Community 16 - "Community 16"
Cohesion: 0.21
Nodes (20): Project agent notes, Set the Phase 1 destination and pilot rules, Verify permitted live travel data and cost limits, Establish Taipei New Year countdown evidence and refresh timing, Choose the Phase 1 source stack and evidence policy, Define trustworthy attraction coverage and card ranking, Define the strong cross-day optimization contract, Prototype the owner-led setup and confirmation flow (+12 more)

### Community 17 - "Community 17"
Cohesion: 0.13
Nodes (14): _date_value(), _day_poster(), _export_labels(), _optimizer_code(), _plan_documents(), _plan_item_name(), Local Streamlit entry point for the personal travel planner., Interface copy plus optimizer-code wording, so documents match the app. (+6 more)

### Community 18 - "Community 18"
Cohesion: 0.12
Nodes (11): FPDF, ArtifactTest, A formula with no cached value reads blank until the app recalculates., words['x'] with no default raises when a caller passes no labels., _pdf_heading(), _pdf_line(), plan_pdf(), Path (+3 more)

### Community 19 - "Community 19"
Cohesion: 0.32
Nodes (17): _condition_holds(), _has_verified_entrance(), _high_heat(), _hotel_id(), main(), _meal_inside_window(), _minutes(), _outcome_holds() (+9 more)

### Community 20 - "Community 20"
Cohesion: 0.15
Nodes (8): _comfort_thresholds(), Unexpired normalized routes; an expired leg is no longer verified., Fetch opening hours for the selected places, one paid call each., The interval valid on every trip date, per place, with its reason., Unexpired zone evidence, or None. An expired zone is not verified., _simple_interval(), date_range(), Small shared helper for application snapshot assembly.

### Community 21 - "Community 21"
Cohesion: 0.15
Nodes (7): ChecklistExportTest, checklist_ics(), _ics_fold(), _ics_text(), All-day calendar entries for every dated readiness task.      All-day VEVENTs ra, Escape per RFC 5545; an unescaped comma silently truncates a field., Fold to 75 octets; a long unfolded line makes some importers reject the file.

### Community 22 - "Community 22"
Cohesion: 0.28
Nodes (14): build_report(), check_google_places(), check_google_routes(), check_open_meteo(), check_openrouteservice(), check_overpass(), configured_status(), load_keys() (+6 more)

### Community 23 - "Community 23"
Cohesion: 0.17
Nodes (4): FakePlaceProvider, SchemaMigrationTest, SetupDiscoveryTest, SetupUiTest

### Community 24 - "Community 24"
Cohesion: 0.15
Nodes (5): Actions offered for the active plan. None of them needs a model., Build the one pending preview. The active plan is never touched here., Apply the pending preview as a new immutable version, with history., Deterministic reasons for the active plan. No model involved., Verified operational facts that justify a booking or access task.

### Community 25 - "Community 25"
Cohesion: 0.17
Nodes (3): TimeZoneTest, GoogleTimeZoneProvider, The destination's IANA time zone, from coordinates.      A paid, single-value lo

### Community 26 - "Community 26"
Cohesion: 0.23
Nodes (3): ConversionTest, rates(), RateSnapshotTest

### Community 27 - "Community 27"
Cohesion: 0.18
Nodes (4): NormalizationTest, OpenRouteServiceProvider, _point_key(), Foot-walking routes from OpenRouteService, normalized for the planner.      A ro

### Community 28 - "Community 28"
Cohesion: 0.27
Nodes (11): apply_rates(), _currency(), new_rate_snapshot(), Any, Owner-recorded trip costs in THB plus their original currency.  Pure: no Streaml, Estimated and paid THB totals, plus the rows no rate could cover., One timestamped set of THB-per-unit rates, with an optional buffer., Reject a cost row that breaks the agreed contract. (+3 more)

### Community 29 - "Community 29"
Cohesion: 0.25
Nodes (3): Cost rows with their THB value resolved against the rate snapshot., Preview the generated board against what is already saved., Apply the previewed changes. A removal is dismissed, never deleted.

### Community 30 - "Community 30"
Cohesion: 0.22
Nodes (5): This month's paid spend against the cap, with per-operation counts., Judge a prospective paid call. Callers must honour `allowed`., Refuse a call that would cross the cap, then record what it cost., One model call turns free text into a typed operation, then previews it., Look up the destination's IANA zone once, from its discovered centre.

### Community 31 - "Community 31"
Cohesion: 0.31
Nodes (4): Any, Path, Add or edit one board item, generated or owner-authored., Move an item to verified by recording its official source.

### Community 33 - "Community 33"
Cohesion: 0.31
Nodes (8): common_interval(), google_day(), intervals_by_date(), Any, Weekly opening periods to the per-date interval the optimizer can use.  Pure: no, Google Places numbers days from Sunday; Python's isoweekday from Monday., The open windows on each trip date, empty where the place is closed., Reduce a weekly schedule to one interval valid on every trip date.

### Community 34 - "Community 34"
Cohesion: 0.33
Nodes (7): One board row: state, deadline, consequence, and its evidence controls., _render_checklist_item(), display_consequence(), display_title(), Localized task wording, or the stored English literal as a fallback.      Templa, Localized consequence; a template may vary it per generated variant., _task_line()

### Community 35 - "Community 35"
Cohesion: 0.29
Nodes (3): Selected places that carry coordinates, deterministically ordered., The centre of the discovered coverage box, or a selected place., Fetch walking routes between the selected places, sparsely and capped.

### Community 37 - "Community 37"
Cohesion: 0.70
Nodes (4): find_forbidden_keys(), main(), Any, validate()

### Community 38 - "Community 38"
Cohesion: 0.50
Nodes (3): ChecklistViewTest, AppTest, _text()

## Knowledge Gaps
- **5 isolated node(s):** `tourist-planner`, `Local Markdown Wayfinder tracker`, `Optimizer Trip Planner README`, `Project agent notes`, `Slice 5 and 6 implementation evidence`
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PlannerActions` connect `Community 15` to `Community 0`, `Community 2`, `Community 35`, `Community 36`, `Community 9`, `Community 11`, `Community 14`, `Community 20`, `Community 24`, `Community 25`, `Community 27`, `Community 29`, `Community 30`, `Community 31`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Why does `optimize_trip()` connect `Community 3` to `Community 1`?**
  _High betweenness centrality (0.008) - this node is a cross-community bridge._
- **Are the 17 inferred relationships involving `PlannerActions` (e.g. with `CandidateChoice` and `DiscoveryRun`) actually correct?**
  _`PlannerActions` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `SQLiteStore` (e.g. with `CandidateChoice` and `ChecklistItem`) actually correct?**
  _`SQLiteStore` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Local Streamlit entry point for the personal travel planner.`, `Interface copy plus optimizer-code wording, so documents match the app.`, `Cached per plan-version snapshot and language; exporters are pure.` to the rest of the system?**
  _124 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.0662280701754386 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.1397459165154265 - nodes in this community are weakly interconnected._