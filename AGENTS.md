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

## The graph was rebuilt on 2026-08-01 and the guard passes

- `python3 scripts/build_project_graph.py --check` **passes**. The long-standing
  `Extraction produced no node for WF-018` failure is resolved: it was staleness,
  exactly as diagnosed, and never the 2026-07-29 corruption.
- The rebuild cost **US$0.0254** (44,100 in / 4,829 out), taking the cumulative
  total to about US$0.11 over 15 runs. A full rebuild is **cents, not dollars** —
  the earlier reluctance over-weighted the cost. It still needs `OPENAI_API_KEY`,
  which `build_project_graph.py` reads from `secrets.local.json` itself, so no
  variable has to be exported by hand.
- State after the rebuild: **1126 nodes, 2827 directed edges, 54 communities**, with
  **39 nodes from `.wayfinder/tickets/`** covering all 36 tickets plus one node each
  for the two maps. Ticket nodes are keyed by **title**, not by ID — `WF-0nn` will
  not appear in a node name, and `--check` resolves them by source file and title.
- **Secrets are not ingested.** Verified empirically both before and after: zero
  nodes sourced from `secrets.local.json` or `.env`, and no `sk-` string anywhere
  in `graph.json`. Graphify honours `.gitignore`. Source code *is* sent to OpenAI,
  which every prior rebuild already accepted.
- Diagnosing a future failure is unchanged: count the wayfinder-sourced nodes first.
  A missing *new* ticket is staleness; a missing *old* ticket is corruption.
- The Phase 2 tickets carry long resolution prose, which is exactly what starved
  ticket 012's extraction twice. Keep long findings in `.wayfinder/artifacts/` and
  link them in one line from the ticket. That rule was followed for all seven
  resolutions of 2026-07-31, and the tickets extract cleanly as a result — it is the
  established pattern now, not advice.

### Known: `.wayfinder/artifacts/` is excluded from the graph

`build_project_graph.py` passes `--exclude artifacts` to skip the root
`artifacts/validation/` bundles, whose manifests are evidence rather than
architecture. But the pattern carries no leading slash, so in gitignore semantics it
matches a directory called `artifacts` **at any depth** — which silently also
excludes `.wayfinder/artifacts/`. Confirmed: the rebuild produced **zero** nodes from
either directory.

The consequence is worth knowing rather than discovering: following the
keep-long-findings-in-artifacts rule above moves that content **out of the graph**.
Tickets extract cleanly, which was the goal, but the decisions themselves are not
queryable — only the tickets that link to them. That is acceptable while the graph is
for broad architecture questions, as `CLAUDE.md` directs. If decision content should
be graphed, anchor the pattern as `/artifacts` and rebuild.

## Validation evidence belongs in bundles

- Ticket 012 is an index. Put each validation run's numbers in
  `artifacts/validation/<run-id>/manifest.json` and narrative in a notes file
  beside it, then link them from the ticket in one line.
- Appending long evidence prose to that ticket has twice starved its Graphify
  extraction, which fails the build with `Extraction produced no node for WF-012`.
  Keep the file short and the rebuild keeps working.
