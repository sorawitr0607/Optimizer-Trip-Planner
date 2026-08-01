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

## The checked-in graph predates the Phase 2 map

- `python3 scripts/build_project_graph.py --check` currently **fails** with
  `Extraction produced no node for WF-018`. This is not the 2026-07-29 corruption:
  no data was lost. `WF-MAP-002` and tickets `018`–`036` were charted after the
  last rebuild, so the graph simply has no nodes for them yet.
- Fixing it needs the paid rebuild (`OPENAI_API_KEY`), so it waits for an explicit
  request or the next topology milestone — most sensibly once the Phase 2 map is
  decision-complete, rather than once per resolved ticket.
- Diagnose as the CLAUDE.md note says: count the wayfinder-sourced nodes first. A
  missing *new* ticket is staleness; a missing *old* ticket is corruption.
- The Phase 2 tickets carry long resolution prose, which is exactly what starved
  ticket 012's extraction twice. Keep long findings in `.wayfinder/artifacts/` and
  link them in one line from the ticket.
- **As of 2026-07-31 the gap is wider and the rebuild milestone is close.** Seven
  Phase 2 grilling tickets were resolved that day and six artifacts now exist
  (`019`, `020`, `021`, `022`, `023`, `025`, `026`, `028`, `030`), while `--check`
  still fails at exactly the same place — `WF-018` — so this is still staleness and
  still not corruption. The map is at 9 closed of 19, so the sensible rebuild moment
  (decision-complete) is near rather than hypothetical.
- The keep-findings-in-artifacts rule was **followed** for all seven of those
  resolutions: each ticket carries a summary and one link, with the detail in its
  artifact. Keep doing that — it is the established pattern now, not advice.

## Validation evidence belongs in bundles

- Ticket 012 is an index. Put each validation run's numbers in
  `artifacts/validation/<run-id>/manifest.json` and narrative in a notes file
  beside it, then link them from the ticket in one line.
- Appending long evidence prose to that ticket has twice starved its Graphify
  extraction, which fails the build with `Extraction produced no node for WF-012`.
  Keep the file short and the rebuild keeps working.
