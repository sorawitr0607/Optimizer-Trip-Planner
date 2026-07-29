# Project agent notes

## Graphify cadence

- Use direct source files and tests for routine implementation work.
- Do not run Graphify query, update, save-result, graph rebuild, or cost checks on every task.
- Read the existing graph only when a relationship question materially benefits from it.
- Rebuild the graph only when explicitly requested or after a major milestone that changes architecture topology.
- Save a Graphify result only when the graph materially changes a decision.
- Read/report Graphify cost only after a paid graph rebuild.

## Graphify update guard

- The canonical graph is `graphify-out/graph.json` and must remain directed.
- On 2026-07-29, `graphify update . --no-cluster` rebuilt only the code graph,
  dropped the directed flag, and removed Wayfinder/document nodes. Treat that
  CLI output as an intermediate code scan, not the project graph.
- After any Graphify update, run `python3 scripts/build_project_graph.py --check`.
  If it fails, restore or rebuild the full directed graph before committing.
- Keep Graphify fixes and guardrails in this file so future sessions loading
  this repository inherit the workflow; the installed `graphify` skill remains
  available globally for new sessions that trigger it.

## Validation evidence belongs in bundles

- Ticket 012 is an index. Put each validation run's numbers in
  `artifacts/validation/<run-id>/manifest.json` and narrative in a notes file
  beside it, then link them from the ticket in one line.
- Appending long evidence prose to that ticket has twice starved its Graphify
  extraction, which fails the build with `Extraction produced no node for WF-012`.
  Keep the file short and the rebuild keeps working.
