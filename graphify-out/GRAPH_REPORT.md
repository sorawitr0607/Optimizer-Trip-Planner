# Graph Report - /Users/t1ct1ch20375754/Documents/Thaksin/ML/Personal_Project/Tourist/Optimizer-Trip-Planner  (2026-08-01)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1126 nodes · 2827 edges · 54 communities (43 shown, 11 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 223 edges (avg confidence: 0.51)
- Token cost: 179,352 input · 24,452 output · about US$0.1108 (cumulative)

## Graph Freshness
- Built from commit: `9de78049`
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

## God Nodes (most connected - your core abstractions)
1. `PlannerActions` - 204 edges
2. `SQLiteStore` - 74 edges
3. `ProviderUnavailable` - 54 edges
4. `optimize_trip()` - 36 edges
5. `ProviderBudgetExceeded` - 36 edges
6. `OpenStreetMapProvider` - 28 edges
7. `plan_pdf()` - 27 edges
8. `freeze_snapshot()` - 26 edges
9. `FakeRouteProvider` - 24 edges
10. `plan_workbook_xlsx()` - 24 edges

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
- **Phase 2 map tickets** — wayfinder_tickets_018_define_the_split_ledger_model_and_where_its_math_lives, wayfinder_tickets_019_lock_the_local_api_contract_between_webapp_and_core [EXTRACTED 1.00]

## Communities (54 total, 11 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (31): Connection, Row, Application actions coordinating the domain core and SQLite adapter., CandidateChoice, ChecklistItem, DiscoveryRun, freeze_snapshot(), FrozenSnapshot (+23 more)

### Community 1 - "Community 1"
Cohesion: 0.12
Nodes (65): _access_gap(), _activity_route(), _append_operational(), _append_wait(), _apply_physical_load_limit(), _base_name(), _best_inbound_route(), _best_route() (+57 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (38): Counter, candidate(), FakeCardProvider, Provider, RankingCoreTest, RankingUiTest, setup_payload(), GooglePlacesCardProvider (+30 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (13): Exception, ExtractionTest, FakeInterpreter, InterpretFlowTest, model_reply(), PayloadTest, A live model returns factor: null for "cut down the walking"., ResponseValidationTest (+5 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (34): ActivePlanViewTest, export_for(), ExportSnapshotTest, FallbackAndAnchorTest, plan_payload(), planner_input(), AppTest, _text() (+26 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (10): fixture(), OptimizerActionsTest, OptimizerCoreTest, ConsequenceTest, OperationContractTest, planner_input(), RevisionFlowTest, RevisionViewTest (+2 more)

### Community 6 - "Community 6"
Cohesion: 0.11
Nodes (14): FakePlaceProvider, ExploreFirstEvidenceTest, FakeHoursProvider, PlaceProvider, ProvisionalDerivationTest, A plan may only be Ready once the owner has confirmed the basics., ReductionTest, FakePlaceProvider (+6 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (20): Request, CardEnrichmentTest, _address(), _best_nearby_match(), _category(), _category_accepts_primary_type(), _distance_metres(), _name_similarity() (+12 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (17): entry(), LedgerPersistenceTest, PricingTest, ThresholdTest, check_allowed(), month_of(), new_entry(), price_for() (+9 more)

### Community 9 - "Community 9"
Cohesion: 0.09
Nodes (8): ConcreteProviderTest, DestinationPickerTest, FakePlaceProvider, The picker is a convenience; a city it does not list must still work.          `, SchemaMigrationTest, SetupDiscoveryTest, SetupUiTest, OpenStreetMapProvider

### Community 10 - "Community 10"
Cohesion: 0.10
Nodes (31): Reusable core and local application services for the travel planner., allowed_place_ids(), _assert_clean(), build_payload(), interpret_response(), Any, Free text to one typed revision operation.  Pure: no Streamlit, SQLite, provider, The stable IDs the model was shown; it may name no other. (+23 more)

### Community 11 - "Community 11"
Cohesion: 0.13
Nodes (22): RuntimeError, annotate_report_cost(), build(), deduplicate_nodes(), extracted_edge_issues(), main(), normalize_raw_graph(), openai_key() (+14 more)

### Community 12 - "Community 12"
Cohesion: 0.09
Nodes (6): _app_text(), ChecklistDiffAndReadinessTest, ChecklistGenerationTest, ChecklistLocalizationTest, ChecklistPersistenceTest, setup_payload()

### Community 13 - "Community 13"
Cohesion: 0.15
Nodes (24): _booking_places(), diff_proposal(), due_date_for(), _generated(), _is_due_soon(), _is_overdue(), _nationality(), _nationality_groups() (+16 more)

### Community 14 - "Community 14"
Cohesion: 0.17
Nodes (21): _code(), _coordinates(), _draw_block(), _ellipsize(), _fallback_line(), fit_lines(), plan_workbook_xlsx(), Any (+13 more)

### Community 15 - "Community 15"
Cohesion: 0.15
Nodes (21): actions(), chosen(), journey(), language(), _language_key(), Shared presentation state and renderers used by every view.  The entry script re, The stored choice, kept selectable across a language switch., A selectbox whose shown option survives a language switch.      Streamlit caches (+13 more)

### Community 16 - "Community 16"
Cohesion: 0.18
Nodes (21): Define the split ledger model and where its math lives, Lock the local API contract between the webapp and the planning core, Merge the bill splitter and rebuild the planner as a webapp, Define the split ledger model and where its math lives, Lock the local API contract between the webapp and the planning core, Extract the Auto-Bill design token contract, Inventory the Auto-Bill elements each planner stage needs, Decide the Streamlit freeze and pilot fallback rules (+13 more)

### Community 17 - "Community 17"
Cohesion: 0.13
Nodes (7): ChecklistViewTest, AppTest, _text(), CostPersistenceTest, CostViewTest, PlannerActions, Only the owner may raise the stop threshold.

### Community 18 - "Community 18"
Cohesion: 0.13
Nodes (17): FPDF, _day(), day_poster_png(), _item_line(), _labels(), _pdf_heading(), _pdf_line(), plan_pdf() (+9 more)

### Community 19 - "Community 19"
Cohesion: 0.32
Nodes (17): _condition_holds(), _has_verified_entrance(), _high_heat(), _hotel_id(), main(), _meal_inside_window(), _minutes(), _outcome_holds() (+9 more)

### Community 20 - "Community 20"
Cohesion: 0.22
Nodes (19): Set the Phase 1 destination and pilot rules, Verify permitted live travel data and cost limits, Establish Taipei New Year countdown evidence and refresh timing, Choose the Phase 1 source stack and evidence policy, Define trustworthy attraction coverage and card ranking, Define the strong cross-day optimization contract, Prototype the owner-led setup and confirmation flow, Wayfinder Map (+11 more)

### Community 21 - "Community 21"
Cohesion: 0.16
Nodes (8): _comfort_thresholds(), The interval valid on every trip date, per place, with its reason., Store a planning window the owner says they independently checked., Add or edit one board item, generated or owner-authored., Fetch opening hours for the selected places, one paid call each., _simple_interval(), date_range(), Small shared helper for application snapshot assembly.

### Community 22 - "Community 22"
Cohesion: 0.17
Nodes (7): Any, Path, Unexpired zone evidence, or None. An expired zone is not verified., Unexpired normalized routes; an expired leg is no longer verified., This month's paid spend against the cap, with per-operation counts., Judge a prospective paid call. Callers must honour `allowed`., Move an item to verified by recording its official source.

### Community 23 - "Community 23"
Cohesion: 0.17
Nodes (15): date, time, _date_value(), _time_value(), _confirm(), _edited_values(), _go(), Trip basics, travellers, and confirmation. The first stage.  Five short editable (+7 more)

### Community 24 - "Community 24"
Cohesion: 0.13
Nodes (5): EvidenceUiTest, The evidence view had no render test, so its layout was unverified., TimeZoneTest, GoogleTimeZoneProvider, The destination's IANA time zone, from coordinates.      A paid, single-value lo

### Community 25 - "Community 25"
Cohesion: 0.28
Nodes (14): build_report(), check_google_places(), check_google_routes(), check_open_meteo(), check_openrouteservice(), check_overpass(), configured_status(), load_keys() (+6 more)

### Community 26 - "Community 26"
Cohesion: 0.24
Nodes (5): google_payload(), NormalizationTest, period(), GooglePlacesOpeningHoursProvider, Opening hours for one place, from a licensed live overlay.      Text search carr

### Community 27 - "Community 27"
Cohesion: 0.15
Nodes (6): Actions offered for the active plan. None of them needs a model., Build the one pending preview. The active plan is never touched here., One model call turns free text into a typed operation, then previews it., Apply the pending preview as a new immutable version, with history., Deterministic reasons for the active plan. No model involved., Verified operational facts that justify a booking or access task.

### Community 28 - "Community 28"
Cohesion: 0.18
Nodes (7): ChecklistExportTest, checklist_ics(), _ics_fold(), _ics_text(), All-day calendar entries for every dated readiness task.      All-day VEVENTs ra, Escape per RFC 5545; an unescaped comma silently truncates a field., Fold to 75 octets; a long unfolded line makes some importers reject the file.

### Community 29 - "Community 29"
Cohesion: 0.15
Nodes (6): Look up the destination's IANA zone once, from its discovered centre., The centre of the discovered coverage box, or a selected place., Fetch walking routes between the selected places, sparsely and capped., Selected places that carry coordinates, deterministically ordered., Refuse a call that would cross the cap, then record what it cost., Fetch a session-only photo/rating/review overlay for one visible card.

### Community 30 - "Community 30"
Cohesion: 0.22
Nodes (12): apply_rates(), _currency(), new_rate_snapshot(), Any, Owner-recorded trip costs in THB plus their original currency.  Pure: no Streaml, Resolve each row's THB value against one rate snapshot., Estimated and paid THB totals, plus the rows no rate could cover., One timestamped set of THB-per-unit rates, with an optional buffer. (+4 more)

### Community 31 - "Community 31"
Cohesion: 0.19
Nodes (11): _day_poster(), _export_labels(), _optimizer_code(), _plan_item_name(), Interface copy plus optimizer-code wording, so documents match the app., The half-day's fallback, with its trigger, swap, and displaced selection., One compact export-snapshot row; details stay behind progressive disclosure., _render_fallback() (+3 more)

### Community 32 - "Community 32"
Cohesion: 0.23
Nodes (3): ConversionTest, rates(), RateSnapshotTest

### Community 33 - "Community 33"
Cohesion: 0.17
Nodes (3): ArtifactTest, A formula with no cached value reads blank until the app recalculates., words['x'] with no default raises when a caller passes no labels.

### Community 34 - "Community 34"
Cohesion: 0.18
Nodes (4): NormalizationTest, OpenRouteServiceProvider, _point_key(), Foot-walking routes from OpenRouteService, normalized for the planner.      A ro

### Community 39 - "Community 39"
Cohesion: 0.25
Nodes (3): Cost rows with their THB value resolved against the rate snapshot., Preview the generated board against what is already saved., Apply the previewed changes. A removal is dismissed, never deleted.

### Community 40 - "Community 40"
Cohesion: 0.25
Nodes (10): display_consequence(), display_title(), _localized(), Localized task wording, or the stored English literal as a fallback.      Templa, Localized consequence; a template may vary it per generated variant., _task_line(), _write_checklist(), One board row: state, deadline, consequence, and its evidence controls. (+2 more)

### Community 41 - "Community 41"
Cohesion: 0.20
Nodes (9): city_options(), country_label(), country_options(), destination_text(), Curated country and city picker list for the setup form.  This is a convenience, Countries in region order. The dropdown also accepts a typed name., Cities for one country, empty for a country that was typed in., Display name for one country. Falls back to the value itself when typed. (+1 more)

### Community 42 - "Community 42"
Cohesion: 0.20
Nodes (7): _candidate_name(), _category_text(), _empty_setup(), _explain(), _photo_url(), Broad discovery, then explainable ranking and the owner's choices., Quick actions and free-text revision, with preview and undo.

### Community 44 - "Community 44"
Cohesion: 0.47
Nodes (8): build_candidate_catalog(), _candidate(), _distance_metres(), _merge(), _name_key(), _occupied_cells(), Any, Provider-neutral candidate identity, conservative dedupe, and coverage reporting

### Community 45 - "Community 45"
Cohesion: 0.31
Nodes (8): common_interval(), google_day(), intervals_by_date(), Any, Weekly opening periods to the per-date interval the optimizer can use.  Pure: no, Google Places numbers days from Sunday; Python's isoweekday from Monday., The open windows on each trip date, empty where the place is closed., Reduce a weekly schedule to one interval valid on every trip date.

### Community 46 - "Community 46"
Cohesion: 0.25
Nodes (6): _open_selected_trip_stage(), Local Streamlit entry point for the personal travel planner.  This script owns o, Name and destination, but never the same text twice.      An unnamed trip takes, After a slot switch, open that trip where its own progress left off., _trip_label(), Every user-facing string, keyed by language.  The core emits stable codes; this

### Community 47 - "Community 47"
Cohesion: 0.70
Nodes (4): find_forbidden_keys(), main(), Any, validate()

## Knowledge Gaps
- **4 isolated node(s):** `tourist-planner`, `Slice 5 and 6 implementation evidence`, `Decide the Streamlit freeze and pilot fallback rules`, `WF-034 Decide the offline asset policy for the webapp`
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PlannerActions` connect `Community 17` to `Community 0`, `Community 2`, `Community 3`, `Community 34`, `Community 38`, `Community 39`, `Community 6`, `Community 9`, `Community 7`, `Community 21`, `Community 22`, `Community 24`, `Community 26`, `Community 27`, `Community 29`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `optimize_trip()` connect `Community 5` to `Community 1`?**
  _High betweenness centrality (0.007) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `PlannerActions` (e.g. with `CandidateChoice` and `DiscoveryRun`) actually correct?**
  _`PlannerActions` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `SQLiteStore` (e.g. with `CandidateChoice` and `ChecklistItem`) actually correct?**
  _`SQLiteStore` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Local Streamlit entry point for the personal travel planner.  This script owns o`, `Name and destination, but never the same text twice.      An unnamed trip takes`, `After a slot switch, open that trip where its own progress left off.` to the rest of the system?**
  _174 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06349206349206349 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.12307692307692308 - nodes in this community are weakly interconnected._