# Graph Report - /Users/t1ct1ch20375754/Documents/Thaksin/ML/Personal_Project/Tourist/Optimizer-Trip-Planner  (2026-07-29)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 119 nodes · 237 edges · 9 communities (7 shown, 2 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 7 edges (avg confidence: 0.5)
- Token cost: 61,692 input · 10,601 output · about US$0.0416 (cumulative)

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

## God Nodes (most connected - your core abstractions)
1. `Lock the validation scorecard and implementation handoff` - 20 edges
2. `SQLiteStore` - 19 edges
3. `PlannerActions` - 18 edges
4. `PlanVersion` - 15 edges
5. `Main/check_provider_access.py` - 14 edges
6. `travel_planner/core.py` - 14 edges
7. `Trip` - 13 edges
8. `Main/build_project_graph.py` - 12 edges
9. `Choose the Phase 1 source stack and evidence policy` - 9 edges
10. `new_plan_version()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Lock the validation scorecard and implementation handoff` --references--> `Main/build_project_graph.py`  [EXTRACTED]
  .wayfinder/tickets/012-lock-the-validation-scorecard-and-implementation-handoff.md → Main/build_project_graph.py
- `Lock the validation scorecard and implementation handoff` --references--> `Main/check_provider_access.py`  [EXTRACTED]
  .wayfinder/tickets/012-lock-the-validation-scorecard-and-implementation-handoff.md → Main/check_provider_access.py
- `Lock the validation scorecard and implementation handoff` --references--> `Main/validate_regression_fixtures.py`  [EXTRACTED]
  .wayfinder/tickets/012-lock-the-validation-scorecard-and-implementation-handoff.md → Main/validate_regression_fixtures.py
- `Lock the validation scorecard and implementation handoff` --references--> `tests.test_foundation`  [EXTRACTED]
  .wayfinder/tickets/012-lock-the-validation-scorecard-and-implementation-handoff.md → tests/test_foundation.py
- `Lock the validation scorecard and implementation handoff` --references--> `travel_planner/core.py`  [EXTRACTED]
  .wayfinder/tickets/012-lock-the-validation-scorecard-and-implementation-handoff.md → travel_planner/core.py

## Import Cycles
- None detected.

## Communities (9 total, 2 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.11
Nodes (24): Local Streamlit entry point for the personal travel planner., Plan the personalized travel itinerary tool, Set the Phase 1 destination and pilot rules, Verify permitted live travel data and cost limits, Establish Taipei New Year countdown evidence and refresh timing, Choose the Phase 1 source stack and evidence policy, Define trustworthy attraction coverage and card ranking, Define the strong cross-day optimization contract (+16 more)

### Community 1 - "Community 1"
Cohesion: 0.16
Nodes (8): tests.test_foundation, FoundationTest, PlannerActions, Any, Path, Application actions coordinating the domain core and SQLite adapter., PlanVersion, Reusable core and local application services for the travel planner.

### Community 2 - "Community 2"
Cohesion: 0.22
Nodes (5): Connection, Row, Trip, Path, SQLiteStore

### Community 3 - "Community 3"
Cohesion: 0.24
Nodes (13): Main/build_project_graph.py, annotate_report_cost(), build(), extracted_edge_issues(), main(), normalize_raw_graph(), openai_key(), Find lost pairs or relations not present in the raw DiGraph variants. (+5 more)

### Community 4 - "Community 4"
Cohesion: 0.28
Nodes (15): Main/check_provider_access.py, build_report(), check_google_places(), check_google_routes(), check_open_meteo(), check_openrouteservice(), check_overpass(), configured_status() (+7 more)

### Community 5 - "Community 5"
Cohesion: 0.29
Nodes (12): travel_planner/core.py, freeze_snapshot(), FrozenSnapshot, new_plan_version(), new_trip(), Any, Language-neutral domain records with no UI, database, or provider imports., _reject_forbidden_keys() (+4 more)

### Community 6 - "Community 6"
Cohesion: 0.70
Nodes (5): Main/validate_regression_fixtures.py, find_forbidden_keys(), main(), Any, validate()

## Knowledge Gaps
- **11 isolated node(s):** `tourist-planner`, `Local Markdown Wayfinder tracker`, `Plan the personalized travel itinerary tool`, `Set the Phase 1 destination and pilot rules`, `Prototype the owner-led setup and confirmation flow` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `Choose the minimal Phase 1 architecture and data contracts` (14× useful, score=13.986252591)
- `Define the strong cross-day optimization contract` (9× useful, score=8.990177246)
- `Prototype the daily poster, timeline, map, PDF, and Excel` (7× useful, score=6.991461597)
- `Lock the validation scorecard and implementation handoff` (6× useful, score=5.99633162) _(code changed — re-verify)_
- `Choose the Phase 1 source stack and evidence policy` (6× useful, score=5.992927161)
- `Define the constrained GenAI plan revision assistant` (6× useful, score=5.992495253)
- `Turn historic trip failures into regression fixtures` (5× useful, score=4.996869692)
- `Verify a worldwide core and local enrichment model` (4× useful, score=3.995532988)
- `Prototype the owner-led setup and confirmation flow` (4× useful, score=3.994863231)
- `Verify permitted live travel data and cost limits` (2× useful, score=1.997932539)

**Known dead ends** — questions that led nowhere; don't re-derive.
- "agree" -> `Inspect the reference itinerary workbooks`

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PlannerActions` connect `Community 1` to `Community 2`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Why does `SQLiteStore` connect `Community 2` to `Community 1`, `Community 5`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Why does `travel_planner/core.py` connect `Community 5` to `Community 1`, `Community 2`?**
  _High betweenness centrality (0.004) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `SQLiteStore` (e.g. with `FrozenSnapshot` and `PlanVersion`) actually correct?**
  _`SQLiteStore` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `PlannerActions` (e.g. with `PlanVersion` and `Trip`) actually correct?**
  _`PlannerActions` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Find lost pairs or relations not present in the raw DiGraph variants.`, `Local Streamlit entry point for the personal travel planner.`, `tourist-planner` to the rest of the system?**
  _17 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.10582010582010581 - nodes in this community are weakly interconnected._