# Graph Report - /Users/t1ct1ch20375754/Documents/Thaksin/ML/Personal_Project/Tourist/Optimizer-Trip-Planner  (2026-07-29)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 424 nodes · 1194 edges · 15 communities (13 shown, 2 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 60 edges (avg confidence: 0.55)
- Token cost: 104,546 input · 15,170 output · about US$0.0660 (cumulative)

## Graph Freshness
- Built from commit: `326b4724`
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

## God Nodes (most connected - your core abstractions)
1. `PlannerActions` - 69 edges
2. `SQLiteStore` - 47 edges
3. `_candidate_id()` - 23 edges
4. `OpenStreetMapProvider` - 23 edges
5. `optimize_trip()` - 21 edges
6. `_prepare_candidates()` - 19 edges
7. `PlanVersion` - 16 edges
8. `plan_pdf()` - 16 edges
9. `plan_workbook_xlsx()` - 16 edges
10. `freeze_snapshot()` - 15 edges

## Surprising Connections (you probably didn't know these)
- `ExportSnapshotTest` --uses--> `PlannerActions`  [INFERRED]
  tests/test_exports.py → travel_planner/actions.py
- `ArtifactTest` --uses--> `PlannerActions`  [INFERRED]
  tests/test_exports.py → travel_planner/actions.py
- `ActivePlanViewTest` --uses--> `PlannerActions`  [INFERRED]
  tests/test_exports.py → travel_planner/actions.py
- `OptimizerCoreTest` --uses--> `PlannerActions`  [INFERRED]
  tests/test_optimizer.py → travel_planner/actions.py
- `OptimizerActionsTest` --uses--> `PlannerActions`  [INFERRED]
  tests/test_optimizer.py → travel_planner/actions.py

## Import Cycles
- 2-file cycle: `travel_planner/__init__.py -> travel_planner/actions.py -> travel_planner/__init__.py`

## Communities (15 total, 2 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (36): Connection, Row, FoundationTest, RankingUiTest, _comfort_thresholds(), PlannerActions, Any, Path (+28 more)

### Community 1 - "Community 1"
Cohesion: 0.15
Nodes (55): _access_gap(), _activity_route(), _append_wait(), _apply_physical_load_limit(), _best_inbound_route(), _best_route(), _buffer_item(), _build_day() (+47 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (40): _date_value(), _day_poster(), _optimizer_code(), _plan_documents(), _plan_item_name(), Local Streamlit entry point for the personal travel planner., Cached per plan-version snapshot and language; exporters are pure., One compact export-snapshot row; details stay behind progressive disclosure. (+32 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (33): Counter, candidate(), Provider, RankingCoreTest, setup_payload(), build_ranking(), candidates_by_id(), _city_icon() (+25 more)

### Community 4 - "Community 4"
Cohesion: 0.12
Nodes (12): Request, ConcreteProviderTest, FakePlaceProvider, SchemaMigrationTest, SetupDiscoveryTest, SetupUiTest, _address(), _category() (+4 more)

### Community 5 - "Community 5"
Cohesion: 0.14
Nodes (23): AppTest, ActivePlanViewTest, ExportSnapshotTest, plan_payload(), planner_input(), _text(), build_export_snapshot(), _day() (+15 more)

### Community 6 - "Community 6"
Cohesion: 0.16
Nodes (23): _condition_holds(), _has_verified_entrance(), _high_heat(), _hotel_id(), main(), _meal_inside_window(), _minutes(), _outcome_holds() (+15 more)

### Community 7 - "Community 7"
Cohesion: 0.24
Nodes (18): Set the Phase 1 destination and pilot rules, Verify permitted live travel data and cost limits, Establish Taipei New Year countdown evidence and refresh timing, Choose the Phase 1 source stack and evidence policy, Define trustworthy attraction coverage and card ranking, Define the strong cross-day optimization contract, Prototype the owner-led setup and confirmation flow, Wayfinder Map (+10 more)

### Community 8 - "Community 8"
Cohesion: 0.25
Nodes (13): RuntimeError, annotate_report_cost(), build(), extracted_edge_issues(), main(), normalize_raw_graph(), openai_key(), Find lost pairs or relations not present in the raw DiGraph variants. (+5 more)

### Community 9 - "Community 9"
Cohesion: 0.28
Nodes (14): build_report(), check_google_places(), check_google_routes(), check_open_meteo(), check_openrouteservice(), check_overpass(), configured_status(), load_keys() (+6 more)

### Community 10 - "Community 10"
Cohesion: 0.47
Nodes (8): build_candidate_catalog(), _candidate(), _distance_metres(), _merge(), _name_key(), _occupied_cells(), Any, Provider-neutral candidate identity, conservative dedupe, and coverage reporting

### Community 11 - "Community 11"
Cohesion: 0.70
Nodes (4): find_forbidden_keys(), main(), Any, validate()

### Community 12 - "Community 12"
Cohesion: 0.67
Nodes (3): Project agent notes, CLAUDE.md Guidance, Optimizer Trip Planner README

## Knowledge Gaps
- **4 isolated node(s):** `tourist-planner`, `Project agent notes`, `Optimizer Trip Planner README`, `Local Markdown Wayfinder tracker`
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PlannerActions` connect `Community 0` to `Community 4`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `optimize_trip()` connect `Community 6` to `Community 1`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `PlannerActions` (e.g. with `CandidateChoice` and `DiscoveryRun`) actually correct?**
  _`PlannerActions` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `SQLiteStore` (e.g. with `CandidateChoice` and `DiscoveryRun`) actually correct?**
  _`SQLiteStore` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Local Streamlit entry point for the personal travel planner.`, `Cached per plan-version snapshot and language; exporters are pure.`, `One compact export-snapshot row; details stay behind progressive disclosure.` to the rest of the system?**
  _31 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06181818181818182 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.1487012987012987 - nodes in this community are weakly interconnected._