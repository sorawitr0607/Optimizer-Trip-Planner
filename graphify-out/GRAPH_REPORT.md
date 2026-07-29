# Graph Report - /Users/t1ct1ch20375754/Documents/Thaksin/ML/Personal_Project/Tourist/Optimizer-Trip-Planner  (2026-07-29)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 574 nodes · 1551 edges · 25 communities (21 shown, 4 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 73 edges (avg confidence: 0.54)
- Token cost: 122,374 input · 16,345 output · about US$0.0751 (cumulative)

## Graph Freshness
- Built from commit: `d3192519`
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

## God Nodes (most connected - your core abstractions)
1. `PlannerActions` - 95 edges
2. `SQLiteStore` - 52 edges
3. `plan_pdf()` - 25 edges
4. `optimize_trip()` - 23 edges
5. `_candidate_id()` - 23 edges
6. `OpenStreetMapProvider` - 23 edges
7. `plan_workbook_xlsx()` - 20 edges
8. `_prepare_candidates()` - 19 edges
9. `build_export_snapshot()` - 18 edges
10. `ArtifactTest` - 16 edges

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

## Hyperedges (group relationships)
- **Phase 1 Architecture Layers** — claude_app, travel_planner_actions_planneractions, travel_planner_core, travel_planner_optimizer, travel_planner_ranking, travel_planner_setup, travel_planner_discovery, travel_planner_store, travel_planner_providers [EXTRACTED 1.00]

## Communities (25 total, 4 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (29): Connection, Row, Application actions coordinating the domain core and SQLite adapter., CandidateChoice, ChecklistItem, DiscoveryRun, freeze_snapshot(), FrozenSnapshot (+21 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (19): ChecklistViewTest, AppTest, _text(), FoundationTest, Provider, RankingUiTest, _comfort_thresholds(), PlannerActions (+11 more)

### Community 2 - "Community 2"
Cohesion: 0.15
Nodes (55): _access_gap(), _activity_route(), _append_wait(), _apply_physical_load_limit(), _best_inbound_route(), _best_route(), _buffer_item(), _build_day() (+47 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (33): ActivePlanViewTest, export_for(), ExportSnapshotTest, FallbackAndAnchorTest, plan_payload(), planner_input(), AppTest, _text() (+25 more)

### Community 4 - "Community 4"
Cohesion: 0.13
Nodes (32): Counter, candidate(), RankingCoreTest, setup_payload(), build_ranking(), candidates_by_id(), _city_icon(), _distance_metres() (+24 more)

### Community 5 - "Community 5"
Cohesion: 0.12
Nodes (12): Request, ConcreteProviderTest, FakePlaceProvider, SchemaMigrationTest, SetupDiscoveryTest, SetupUiTest, _address(), _category() (+4 more)

### Community 6 - "Community 6"
Cohesion: 0.16
Nodes (23): _condition_holds(), _has_verified_entrance(), _high_heat(), _hotel_id(), main(), _meal_inside_window(), _minutes(), _outcome_holds() (+15 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (6): _app_text(), ChecklistDiffAndReadinessTest, ChecklistGenerationTest, ChecklistLocalizationTest, ChecklistPersistenceTest, setup_payload()

### Community 8 - "Community 8"
Cohesion: 0.13
Nodes (27): _booking_places(), diff_proposal(), display_consequence(), due_date_for(), _generated(), _is_due_soon(), _is_overdue(), _localized() (+19 more)

### Community 9 - "Community 9"
Cohesion: 0.16
Nodes (17): RuntimeError, annotate_report_cost(), build(), extracted_edge_issues(), main(), normalize_raw_graph(), openai_key(), Find lost pairs or relations not present in the raw DiGraph variants. (+9 more)

### Community 10 - "Community 10"
Cohesion: 0.17
Nodes (22): _coordinates(), _day(), _draw_block(), _ellipsize(), fit_lines(), _item_line(), _labels(), plan_workbook_xlsx() (+14 more)

### Community 11 - "Community 11"
Cohesion: 0.11
Nodes (16): _date_value(), _day_poster(), _export_labels(), _optimizer_code(), _plan_documents(), _plan_item_name(), Local Streamlit entry point for the personal travel planner., The half-day's fallback, with its trigger, swap, and displaced selection. (+8 more)

### Community 12 - "Community 12"
Cohesion: 0.24
Nodes (18): Set the Phase 1 destination and pilot rules, Verify permitted live travel data and cost limits, Establish Taipei New Year countdown evidence and refresh timing, Choose the Phase 1 source stack and evidence policy, Define trustworthy attraction coverage and card ranking, Define the strong cross-day optimization contract, Prototype the owner-led setup and confirmation flow, Wayfinder Map (+10 more)

### Community 13 - "Community 13"
Cohesion: 0.15
Nodes (7): ChecklistExportTest, checklist_ics(), _ics_fold(), _ics_text(), All-day calendar entries for every dated readiness task.      All-day VEVENTs ra, Escape per RFC 5545; an unescaped comma silently truncates a field., Fold to 75 octets; a long unfolded line makes some importers reject the file.

### Community 14 - "Community 14"
Cohesion: 0.28
Nodes (14): build_report(), check_google_places(), check_google_routes(), check_open_meteo(), check_openrouteservice(), check_overpass(), configured_status(), load_keys() (+6 more)

### Community 15 - "Community 15"
Cohesion: 0.17
Nodes (3): ArtifactTest, A formula with no cached value reads blank until the app recalculates., words['x'] with no default raises when a caller passes no labels.

### Community 16 - "Community 16"
Cohesion: 0.47
Nodes (8): build_candidate_catalog(), _candidate(), _distance_metres(), _merge(), _name_key(), _occupied_cells(), Any, Provider-neutral candidate identity, conservative dedupe, and coverage reporting

### Community 17 - "Community 17"
Cohesion: 0.36
Nodes (8): FPDF, _code(), _fallback_line(), _pdf_heading(), _pdf_line(), plan_pdf(), Offline trip snapshot: cover, one section per day, choices, sources., Localize an optimizer code the way the app does, or prettify it.

### Community 18 - "Community 18"
Cohesion: 0.29
Nodes (6): day_poster_png(), Path, Return a Unicode TTF able to draw the selected language and local names., One 9:16 share poster for a single day: identity, highlights, load, risk., resolve_font(), _stamp_line()

### Community 19 - "Community 19"
Cohesion: 0.40
Nodes (5): One board row: state, deadline, consequence, and its evidence controls., _render_checklist_item(), display_title(), Localized task wording, or the stored English literal as a fallback.      Templa, _task_line()

### Community 20 - "Community 20"
Cohesion: 0.70
Nodes (4): find_forbidden_keys(), main(), Any, validate()

## Knowledge Gaps
- **4 isolated node(s):** `tourist-planner`, `Local Markdown Wayfinder tracker`, `Project agent notes`, `Optimizer Trip Planner README`
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PlannerActions` connect `Community 1` to `Community 0`, `Community 5`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Why does `optimize_trip()` connect `Community 6` to `Community 2`?**
  _High betweenness centrality (0.011) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `PlannerActions` (e.g. with `CandidateChoice` and `DiscoveryRun`) actually correct?**
  _`PlannerActions` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `SQLiteStore` (e.g. with `CandidateChoice` and `ChecklistItem`) actually correct?**
  _`SQLiteStore` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Local Streamlit entry point for the personal travel planner.`, `Interface copy plus optimizer-code wording, so documents match the app.`, `Cached per plan-version snapshot and language; exporters are pure.` to the rest of the system?**
  _64 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.08367271380970011 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07199032062915911 - nodes in this community are weakly interconnected._