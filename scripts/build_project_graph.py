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
from pathlib import Path


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


def wayfinder_blocker_edges(nodes: list[dict]) -> list[dict]:
    nodes_by_source: dict[Path, list[dict]] = {}
    for node in nodes:
        source = node.get("source_file")
        if source:
            path = Path(source)
            nodes_by_source.setdefault(
                (path if path.is_absolute() else ROOT / path).resolve(), []
            ).append(node)

    tickets: dict[str, tuple[str, Path, list[str]]] = {}
    for path in sorted((ROOT / ".wayfinder" / "tickets").glob("*.md")):
        parts = path.read_text(encoding="utf-8").split("---", 2)
        if len(parts) != 3:
            continue
        metadata = parts[1]
        ticket_match = re.search(r"(?m)^id:\s*(WF-\d+)\s*$", metadata)
        title_match = re.search(r"(?m)^title:\s*(.+?)\s*$", metadata)
        if not ticket_match or not title_match:
            continue
        title = title_match.group(1).strip('"')
        matches = [
            node for node in nodes_by_source.get(path.resolve(), [])
            if str(node.get("label", "")).casefold() == title.casefold()
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Could not resolve graph node for {ticket_match.group(1)}")

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

        tickets[ticket_match.group(1)] = (matches[0]["id"], path.resolve(), blocked_by)

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


def normalize_raw_graph() -> set[tuple[str, str, str]]:
    data = json.loads(GRAPH.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
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

    for edge in edges:
        for endpoint in ("source", "target"):
            value = edge.get(endpoint)
            if value not in node_ids and value in aliases:
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
            raise RuntimeError(
                f"Graph lost {len(missing_pairs)} valid extracted endpoint pairs"
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
                    # Reference itinerary workbooks and PDFs. Matched as a
                    # case-sensitive gitignore line anchored at the root, so
                    # this must track the real directory name; it read every
                    # PDF while it still said "Data".
                    "data",
                    "--exclude",
                    # Retained validation screenshots: images cost vision
                    # tokens and add no structure. The tickets beside them
                    # stay in the graph.
                    ".wayfinder/evidence",
                    env=env,
                )
            finally:
                if saved_memory.exists():
                    shutil.move(saved_memory, memory)
            expected = normalize_raw_graph()
            run(graphify, "cluster-only", str(ROOT), "--no-label", "--no-viz")
            annotate_report_cost()
            run(graphify, "export", "html")
            result = validate(expected)
        except Exception:
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
