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

## The graph was rebuilt for S1 on 2026-08-03 and the guard passes

- `python3 scripts/build_project_graph.py --check` **passes**. The long-standing
  `Extraction produced no node for WF-018` failure is resolved: it was staleness,
  exactly as diagnosed, and never the 2026-07-29 corruption.
- The S1 milestone rebuild used **124,699 input / 10,709 output tokens**, costing
  **US$0.067015** across two safely restored clustering failures and the successful cached run. Recorded
  cumulative cost is **US$0.228995**. It still needs `OPENAI_API_KEY`, which
  `build_project_graph.py` reads from `secrets.local.json` itself.
- State after the rebuild: **1358 nodes, 3185 directed edges, 137 communities**. Ticket nodes remain keyed
  by **title**, not by ID — `WF-0nn` will not appear in a node name; `--check` resolves them by source file
  and title.
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

### The `--exclude` patterns are gitignore lines — anchor them

`build_project_graph.py` passes `--exclude` straight to graphify, which parses each
one as a gitignore line (`detect.py` `_parse_gitignore_line`, anchored at the scan
root). **A slashless pattern therefore matches a directory of that name at any
depth.**

That bit us. As bare `artifacts`, the exclude meant to skip the root
`artifacts/validation/` bundles *also* silently excluded `.wayfinder/artifacts/`, so
every Phase 2 decision document was missing from the graph while this file was
simultaneously directing long findings to live there. Fixed on 2026-08-01 by
anchoring both patterns as `/data` and `/artifacts`; verified against graphify's own
matcher before rebuilding, and confirmed after:

- **96 nodes across all 9 decision artifacts** are now in the graph.
- Root `artifacts/validation/` and `data/` are still excluded, as intended.

If you add another `--exclude`, anchor it unless you genuinely mean every directory
of that name at every depth.

### Rebuilding: two behaviours that will waste your time

- **`graphify extract` is incremental against an existing `graph.json`.** Leave one in
  place and it re-extracts only changed files and writes a *partial* graph over the
  top — a 1126-node graph became 150 nodes that way. `build_project_graph.py` avoids
  this by moving the generated files into a temp backup first. Never call `graphify
  extract` by hand in this repo; run the script.
- **Clustering is non-deterministic.** The same graph clustered to 121, 123 and 127
  communities across runs. Do not treat a changed community count as a signal.

### One unexplained transient, 2026-08-01

The first rebuild with artifacts included failed `validate()` with
`Graph must be non-empty and directed`, after clustering reported 127 communities.
**It did not reproduce**: two subsequent full runs of the same script over the same
inputs both passed. Isolating each stage against the larger graph showed
`normalize_raw_graph()`, `cluster-only` and `export html` all preserve `directed`,
`nodes` and `links`, so no stage is implicated.

What matters is that **the script's restore-on-failure worked exactly as designed** —
the previous graph was put back intact and `--check` still passed. If this recurs,
capture the failed `graph.json` before the restore runs rather than re-running blind.

### Resolved during the S1 rebuild, 2026-08-03

The apparent transient reproduced twice. Root cause was Graphify's legitimate semantic-ID canonicalization:
`cluster-only` built fewer NetworkX nodes than the raw extraction, then its overwrite guard retained the raw
`edges`-format file. The project validator correctly refused that unclustered shape. The wrapper now stages
the raw graph at `.graphify_raw.json` and passes it with `--graph`, leaving no destination file for the
shrink guard to compare. The existing endpoint-pair validation still blocks genuine loss. A focused unit
test and the full 1358-node rebuild prove the repaired path.

## Validation evidence belongs in bundles

- Ticket 012 is an index. Put each validation run's numbers in
  `artifacts/validation/<run-id>/manifest.json` and narrative in a notes file
  beside it, then link them from the ticket in one line.
- Appending long evidence prose to that ticket has twice starved its Graphify
  extraction, which fails the build with `Extraction produced no node for WF-012`.
  Keep the file short and the rebuild keeps working.
