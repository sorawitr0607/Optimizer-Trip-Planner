#!/usr/bin/env python3
"""Build and validate this project's directed Graphify graph."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "graphify-out"
GRAPH = OUT / "graph.json"
MODEL = "gpt-4.1-mini"  # Graphify 0.9.3's pinned OpenAI default.
INPUT_USD_PER_MILLION = 0.40  # Graphify 0.9.3 OpenAI estimate.
OUTPUT_USD_PER_MILLION = 1.60
GENERATED = (
    "graph.json",
    "manifest.json",
    "GRAPH_REPORT.md",
    "graph.html",
    ".graphify_analysis.json",
)


def openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    secrets_file = ROOT / "secrets.local.json"
    if not key and secrets_file.is_file():
        values = json.loads(secrets_file.read_text(encoding="utf-8"))
        key = str(values.get("OPENAI_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return key


def run(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def record_cost(data: dict) -> None:
    input_tokens = int(data.get("input_tokens", 0))
    output_tokens = int(data.get("output_tokens", 0))
    if not input_tokens and not output_tokens:
        return
    estimated_usd = (
        input_tokens * INPUT_USD_PER_MILLION
        + output_tokens * OUTPUT_USD_PER_MILLION
    ) / 1_000_000
    path = OUT / "cost.json"
    cost = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.is_file()
        else {"runs": [], "total_input_tokens": 0, "total_output_tokens": 0}
    )
    cost["runs"].append(
        {
            "date": datetime.now(timezone.utc).isoformat(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_usd": round(estimated_usd, 6),
        }
    )
    cost["total_input_tokens"] += input_tokens
    cost["total_output_tokens"] += output_tokens
    cost["estimated_usd"] = round(
        float(cost.get("estimated_usd", 0)) + estimated_usd, 6
    )
    path.write_text(json.dumps(cost, indent=2) + "\n", encoding="utf-8")


def annotate_report_cost() -> None:
    cost_path = OUT / "cost.json"
    report_path = OUT / "GRAPH_REPORT.md"
    if not cost_path.is_file() or not report_path.is_file():
        return
    cost = json.loads(cost_path.read_text(encoding="utf-8"))
    usage = (
        f"- Token cost: {cost['total_input_tokens']:,} input · "
        f"{cost['total_output_tokens']:,} output · about "
        f"US${float(cost.get('estimated_usd', 0)):.4f} (cumulative)"
    )
    report = report_path.read_text(encoding="utf-8")
    report = re.sub(r"^- Token cost:.*$", usage, report, flags=re.MULTILINE)
    report_path.write_text(report, encoding="utf-8")


def resolve_ticket_node(
    ticket_id: str, title: str, candidates: list[dict], *, required: bool = True
) -> dict:
    """Pick the canonical graph node for one Wayfinder ticket.

    Node ids and labels come from an LLM extraction and drift between runs, so
    requiring one exact title match made a paid rebuild fail on wording alone.
    Prefer the exact title, then a node carrying the ticket number, then a lone
    candidate; only genuine ambiguity or an empty extraction blocks the build.

    **An empty extraction always blocks**, whatever `required` says: that is the
    per-ticket presence guard `--check` relies on, and a ticket absent from the graph
    is the data loss it exists to catch.

    `required` is False when the chosen id will not be used. The id is only ever an
    endpoint of a `blocked_by` edge, so for a ticket that neither has blockers nor is
    one, refusing over ambiguity aborts a paid rebuild for a value nothing reads.
    `WF-039` did exactly that on 2026-08-07: its extraction produced three concept nodes
    (`comfort_acceptances Table`, `COMFORT_RULES`, `comfort_tradeoffs`) and no titled
    node, and the build failed twice on a node it never needed. Candidates are already
    scoped to the ticket's own file by `nodes_by_source`, so the deterministic pick
    still anchors the right document.
    """

    if not candidates:
        raise RuntimeError(f"Extraction produced no node for {ticket_id}")
    titled = [
        node
        for node in candidates
        if str(node.get("label", "")).casefold() == title.casefold()
    ]
    if titled:
        return min(titled, key=lambda node: str(node["id"]))
    number = ticket_id.split("-")[-1]
    numbered = [node for node in candidates if number in str(node.get("id", ""))]
    if numbered:
        return min(numbered, key=lambda node: str(node["id"]))
    if len(candidates) == 1:
        return candidates[0]
    if not required:
        return min(candidates, key=lambda node: str(node["id"]))
    raise RuntimeError(
        f"Could not resolve graph node for {ticket_id} among "
        f"{len(candidates)} candidates"
    )


def source_path(source: str) -> Path:
    """The file in this checkout that a node's `source_file` refers to.

    Nodes may carry an absolute path from the machine that built the graph. Such
    a path is not `is_absolute()` on Windows, so joining it to the repository
    root produced a drive-relative path that matched nothing and made `--check`
    fail on every ticket except the one stored relatively. Match on the longest
    trailing segments that exist here instead, which works for a POSIX-absolute
    path, a Windows-absolute path, and a repo-relative one alike.
    """

    parts = PurePosixPath(str(source).replace("\\", "/")).parts
    for start in range(len(parts)):
        candidate = ROOT.joinpath(*parts[start:])
        if candidate.exists():
            return candidate.resolve()
    return Path(str(source))


def wayfinder_blocker_edges(nodes: list[dict]) -> list[dict]:
    nodes_by_source: dict[Path, list[dict]] = {}
    for node in nodes:
        source = node.get("source_file")
        if source:
            nodes_by_source.setdefault(source_path(source), []).append(node)

    # Parsed first, resolved second: whether a ticket's node id is ever used depends on
    # the blocker graph as a whole, and only a used id has to be unambiguous.
    parsed: list[tuple[str, str, Path, list[str]]] = []
    for path in sorted((ROOT / ".wayfinder" / "tickets").glob("*.md")):
        parts = path.read_text(encoding="utf-8").split("---", 2)
        if len(parts) != 3:
            continue
        metadata = parts[1]
        ticket_match = re.search(r"(?m)^id:\s*(WF-\d+)\s*$", metadata)
        title_match = re.search(r"(?m)^title:\s*(.+?)\s*$", metadata)
        if not ticket_match or not title_match:
            continue

        blocked_by: list[str] = []
        in_blocked_by = False
        for line in metadata.splitlines():
            if line.strip() == "blocked_by:":
                in_blocked_by = True
                continue
            if not in_blocked_by:
                continue
            blocker_match = re.match(r"\s*-\s*(WF-\d+)\s*$", line)
            if blocker_match:
                blocked_by.append(blocker_match.group(1))
            elif line and not line[0].isspace():
                in_blocked_by = False

        parsed.append(
            (ticket_match.group(1), title_match.group(1).strip('"'), path.resolve(), blocked_by)
        )

    # A node id is read only as an endpoint of a `blocked_by` edge — as the source for a
    # ticket that has blockers, or the target for one that is a blocker.
    used = {ticket_id for ticket_id, _, _, blockers in parsed if blockers}
    used |= {blocker for _, _, _, blockers in parsed for blocker in blockers}

    tickets: dict[str, tuple[str, Path, list[str]]] = {}
    for ticket_id, title, path, blocked_by in parsed:
        chosen = resolve_ticket_node(
            ticket_id,
            title,
            nodes_by_source.get(path, []),
            required=ticket_id in used,
        )
        tickets[ticket_id] = (chosen["id"], path, blocked_by)

    result: list[dict] = []
    for ticket_id, (source, path, blockers) in tickets.items():
        for blocker in blockers:
            if blocker not in tickets:
                raise RuntimeError(f"{ticket_id} has unknown blocker {blocker}")
            result.append(
                {
                    "source": source,
                    "target": tickets[blocker][0],
                    "relation": "blocked_by",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": str(path),
                    "source_location": None,
                }
            )
    return result


def deduplicate_nodes(nodes: list[dict]) -> list[dict]:
    """Mirror Graphify/NetworkX's last-attributes-win handling for duplicate IDs."""

    unique: dict[str, dict] = {}
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id:
            raise RuntimeError("Graphify produced a node without an ID")
        unique[node_id] = {**unique.get(node_id, {}), **node}
    return list(unique.values())


# Extensions that appear as node-id suffixes in this repository's extraction, in both
# spellings it has produced: `web_src_shared_names_ts` and `web_src_routestsx`. The
# separator-less form turned up on the `WF-048` rebuild, two rebuilds after `_ts` did,
# and cost a paid run to discover. Longest extension first, so `tsx` is tried before
# `ts` -- the stem-must-exist guard below is what makes a wrong fold unreachable, but
# ordering keeps the intended one obvious.
SOURCE_EXTENSIONS = ("json", "tsx", "css", "py", "ts", "md")
SOURCE_SUFFIX_IDS = tuple(
    f"{separator}{extension}"
    for extension in SOURCE_EXTENSIONS
    for separator in ("_", "")
)


def file_twins(nodes: list[dict[str, Any]]) -> dict[str, str]:
    """`{twin_id: stem_id}` for extraction's duplicate *file* nodes, and only those.

    A function rather than a comprehension inline in `normalize_raw_graph` because the
    tests used to hold their own copy of that expression: they asserted against a
    reimplementation, so they passed whatever the build actually did, and the `_json`
    fold below went through three rebuilds unnoticed. Testing a copy of the logic tests
    nothing.
    """

    extensions = tuple(f".{extension}" for extension in SOURCE_EXTENSIONS)
    # A file node, recognised rather than guessed: extraction labels it with the file's
    # own name and puts it at L1. Both are required -- a one-line module satisfies
    # either alone, and a method named after an extension satisfies neither.
    file_stems = {
        node["id"]
        for node in nodes
        if str(node.get("source_location", "")).strip() in {"L1", "1", ""}
        and str(node.get("label", "")).lower().endswith(extensions)
    }
    node_ids = {node["id"] for node in nodes}
    return {
        node_id: stem
        for node_id in node_ids
        for suffix in SOURCE_SUFFIX_IDS
        if node_id.endswith(suffix) and (stem := node_id[: -len(suffix)]) in file_stems
    }


def normalize_raw_graph() -> set[tuple[str, str, str]]:
    data = json.loads(GRAPH.read_text(encoding="utf-8"))
    nodes = deduplicate_nodes(data.get("nodes", []))
    data["nodes"] = nodes
    edges = data.get("edges", [])
    if not nodes or not isinstance(edges, list):
        raise RuntimeError("Graphify did not produce a raw extraction graph")

    node_ids = {node["id"] for node in nodes}
    candidates: dict[str, list[str]] = {}
    for node_id in node_ids:
        match = re.match(r"^(wayfinder_tickets_\d{3})_", node_id)
        if match:
            candidates.setdefault(match.group(1), []).append(node_id)
    aliases = {short: ids[0] for short, ids in candidates.items() if len(ids) == 1}

    # Extraction sometimes emits one file twice -- `tests_test_x` and `tests_test_x_py`,
    # `web_src_shared_names` and `web_src_shared_names_ts` -- when a document cites it by
    # path. Both land in `node_ids`, so the pair guard treats an edge to the twin as real,
    # clustering then correctly collapses the duplicate, and the build fails claiming data
    # was lost. Seen 2026-08-07 on `..._046 -> tests_test_assumed_windows_py` and
    # `web_src_shared_names_ts -> travel_planner_destinations`, while other tickets cited
    # files in the identical style and extracted cleanly -- so it is extraction variance,
    # not a citation style to correct.
    #
    # Folding the twin into the real node is the same normalisation `aliases` above
    # already performs, not a relaxation of the guard: the edge is preserved, pointed at
    # the node that survives. Only a *twin* folds; a file that exists solely under the
    # suffixed name is the real node and rewriting it would point edges at nothing.
    #
    # **The stem must be a file, and that is not the same as existing.** The guard above
    # said "a wrong fold is unreachable because the stem must itself be a node", which
    # held only while every stem was a file. It is not: `json` is a source extension and
    # `_json` is also a perfectly ordinary Python method name, so `PlannerHandler._json`
    # (`api/__init__.py:275`) extracted as `api_init_plannerhandler_json`, found its own
    # *class* sitting there as a stem, and was folded out of existence. Measured on the
    # 2026-08-10 rebuild: four real methods deleted — `PlannerHandler._json` and the
    # `_json` on three providers — beside four genuine file twins. A class is not a file,
    # and a method is not a duplicate of its class.
    #
    # A file node is recognisable rather than guessable: extraction labels it with the
    # file's own name and places it at `L1`, where a class or method carries an
    # identifier and its real line. Both are required, because a one-line module would
    # satisfy either alone.
    suffixed = file_twins(nodes)
    if suffixed:
        # Named, not silent: a fold that happens quietly is indistinguishable from the
        # guard being weakened, and the whole point is that it is not.
        for twin, stem in sorted(suffixed.items()):
            print(f"  folded duplicate node {twin} into {stem}", flush=True)
        nodes = [node for node in nodes if node["id"] not in suffixed]
        data["nodes"] = nodes
        node_ids -= set(suffixed)

    for edge in edges:
        for endpoint in ("source", "target"):
            value = edge.get(endpoint)
            if value in suffixed:
                edge[endpoint] = suffixed[value]
            elif value not in node_ids and value in aliases:
                edge[endpoint] = aliases[value]

    edge_keys = {
        (edge.get("source"), edge.get("target"), edge.get("relation", ""))
        for edge in edges
    }
    for edge in wayfinder_blocker_edges(nodes):
        key = (edge["source"], edge["target"], edge["relation"])
        if key not in edge_keys:
            edges.append(edge)
            edge_keys.add(key)

    data["directed"] = True
    record_cost(data)
    GRAPH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        (edge["source"], edge["target"], edge.get("relation", ""))
        for edge in edges
        if edge.get("source") in node_ids and edge.get("target") in node_ids
    }


def extracted_edge_issues(
    expected: set[tuple[str, str, str]],
    actual: set[tuple[str, str, str]],
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Find lost pairs or relations not present in the raw DiGraph variants."""
    expected_by_pair: dict[tuple[str, str], set[str]] = {}
    actual_by_pair: dict[tuple[str, str], set[str]] = {}
    for source, target, relation in expected:
        expected_by_pair.setdefault((source, target), set()).add(relation)
    for source, target, relation in actual:
        actual_by_pair.setdefault((source, target), set()).add(relation)

    missing_pairs = set(expected_by_pair) - set(actual_by_pair)
    changed_relations = {
        pair
        for pair in set(expected_by_pair) & set(actual_by_pair)
        if expected_by_pair[pair].isdisjoint(actual_by_pair[pair])
    }
    return missing_pairs, changed_relations


def cluster_raw_graph(graphify: str) -> None:
    """Cluster from a staged raw graph so Graphify's shrink guard cannot retain it."""

    raw_graph = OUT / ".graphify_raw.json"
    shutil.move(GRAPH, raw_graph)
    try:
        run(
            graphify,
            "cluster-only",
            str(ROOT),
            "--graph",
            str(raw_graph),
            "--no-label",
            "--no-viz",
        )
    finally:
        raw_graph.unlink(missing_ok=True)


def validate(expected: set[tuple[str, str, str]] | None = None) -> tuple[int, int]:
    data = json.loads(GRAPH.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    links = data.get("links", [])
    memory_nodes = [
        node for node in nodes
        if "graphify-out/memory/" in str(node.get("source_file", "")).replace("\\", "/")
    ]
    if memory_nodes:
        raise RuntimeError(f"Graph contains {len(memory_nodes)} feedback-memory nodes")
    node_ids = {node.get("id") for node in nodes}
    if not data.get("directed") or not nodes or not links:
        raise RuntimeError("Graph must be non-empty and directed")
    dangling = [
        link for link in links
        if link.get("source") not in node_ids or link.get("target") not in node_ids
    ]
    if dangling:
        raise RuntimeError(f"Graph contains {len(dangling)} dangling edges")
    required = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in wayfinder_blocker_edges(nodes)
    }
    actual = {
        (link["source"], link["target"], link.get("relation", ""))
        for link in links
    }
    missing_blockers = required - actual
    if missing_blockers:
        raise RuntimeError(f"Graph is missing {len(missing_blockers)} Wayfinder blockers")
    if expected:
        missing_pairs, changed_relations = extracted_edge_issues(expected, actual)
        if missing_pairs:
            # Name them: a count alone cannot be judged, and the failure path
            # deletes the raw extraction that would have explained it.
            listed = ", ".join(
                f"{source} -> {target}" for source, target in sorted(missing_pairs)[:5]
            )
            raise RuntimeError(
                f"Graph lost {len(missing_pairs)} valid extracted endpoint pairs: "
                f"{listed}"
            )
        if changed_relations:
            raise RuntimeError(
                "Graph retained an unextracted relation for "
                f"{len(changed_relations)} endpoint pairs"
            )
    return len(nodes), len(links)


def build() -> tuple[int, int]:
    graphify = shutil.which("graphify")
    if not graphify:
        raise RuntimeError("graphify is not installed")

    OUT.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = openai_key()

    with tempfile.TemporaryDirectory(prefix="tourist-graphify-backup-") as backup_dir:
        backup = Path(backup_dir)
        saved: list[str] = []
        for name in GENERATED:
            path = OUT / name
            if path.exists():
                shutil.move(path, backup / name)
                saved.append(name)
        memory = OUT / "memory"
        saved_memory = backup / "memory"
        if memory.exists():
            shutil.move(memory, saved_memory)
        try:
            try:
                run(
                    graphify,
                    "extract",
                    str(ROOT),
                    "--backend",
                    "openai",
                    "--model",
                    MODEL,
                    "--token-budget",
                    "20000",
                    "--max-concurrency",
                    "2",
                    "--api-timeout",
                    "120",
                    "--no-cluster",
                    "--exclude",
                    # Reference itinerary workbooks and PDFs. Case-sensitive, so
                    # this must track the real directory name; it read every PDF
                    # while it still said "Data".
                    #
                    # The LEADING SLASH matters. graphify parses each --exclude as
                    # a gitignore line (detect.py `_parse_gitignore_line`), so a
                    # slashless pattern matches a directory of that name at ANY
                    # depth. Anchor it, or a nested `data/` is silently dropped.
                    "/data",
                    "--exclude",
                    # Retained validation bundles under the ROOT artifacts/. Their
                    # manifests are evidence, not architecture: ingesting them turns
                    # every manifest key into a node and invents edges from code to
                    # those keys.
                    #
                    # Anchored for a reason found on 2026-08-01: as bare `artifacts`
                    # this also excluded `.wayfinder/artifacts/`, so every Phase 2
                    # decision document was missing from the graph while AGENTS.md
                    # was simultaneously directing long findings to live there.
                    "/artifacts",
                    env=env,
                )
            finally:
                if saved_memory.exists():
                    shutil.move(saved_memory, memory)
            expected = normalize_raw_graph()
            cluster_raw_graph(graphify)
            annotate_report_cost()
            run(graphify, "export", "html")
            result = validate(expected)
        except Exception:
            # Keep the raw extraction and the clustered graph that failed, under
            # names `GENERATED` does not cover, so the next run can diagnose
            # instead of re-paying. Without this the two files that explain a
            # validation failure are exactly the two the cleanup deletes.
            for name, keep in (
                (".graphify_raw.json", "failed-raw.json"),
                ("graph.json", "failed-clustered.json"),
            ):
                source = OUT / name
                if source.is_file():
                    shutil.copy(source, OUT / keep)
            for name in GENERATED:
                (OUT / name).unlink(missing_ok=True)
            for name in saved:
                shutil.move(backup / name, OUT / name)
            raise

    launcher = Path(graphify).read_text(encoding="utf-8").splitlines()[0]
    if launcher.startswith("#!") and Path(launcher[2:]).is_file():
        (OUT / ".graphify_python").write_text(launcher[2:], encoding="utf-8")
    (OUT / ".graphify_root").write_text(str(ROOT), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate existing output only")
    args = parser.parse_args()
    nodes, edges = validate() if args.check else build()
    print(f"Graph ready: {nodes} nodes, {edges} directed edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
