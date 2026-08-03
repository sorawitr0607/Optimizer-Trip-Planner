from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import build_project_graph
from scripts.build_project_graph import (
    cluster_raw_graph,
    deduplicate_nodes,
    extracted_edge_issues,
    resolve_ticket_node,
)


class TicketNodeResolutionTest(unittest.TestCase):
    """Extraction labels drift between runs; resolution must stay deterministic."""

    TITLE = "Lock the validation scorecard and implementation handoff"

    def test_exact_title_wins_and_is_deterministic(self) -> None:
        candidates = [
            {"id": "z_node", "label": self.TITLE},
            {"id": "a_node", "label": self.TITLE},
            {"id": "other", "label": "Some section"},
        ]
        self.assertEqual(
            "a_node", resolve_ticket_node("WF-012", self.TITLE, candidates)["id"]
        )

    def test_reworded_label_falls_back_to_the_ticket_number(self) -> None:
        candidates = [
            {"id": "wayfinder_tickets_012_lock_the_validation_scorecard", "label": "Validation scorecard"},
            {"id": "section_evidence", "label": "Slice 5 evidence"},
        ]
        self.assertEqual(
            "wayfinder_tickets_012_lock_the_validation_scorecard",
            resolve_ticket_node("WF-012", self.TITLE, candidates)["id"],
        )

    def test_single_candidate_is_accepted_however_it_is_labelled(self) -> None:
        candidates = [{"id": "ticket_node", "label": "Renamed by the extractor"}]
        self.assertEqual(
            "ticket_node", resolve_ticket_node("WF-012", self.TITLE, candidates)["id"]
        )

    def test_empty_or_ambiguous_extraction_still_blocks(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "produced no node"):
            resolve_ticket_node("WF-012", self.TITLE, [])
        with self.assertRaisesRegex(RuntimeError, "Could not resolve"):
            resolve_ticket_node(
                "WF-012",
                self.TITLE,
                [
                    {"id": "alpha", "label": "One section"},
                    {"id": "beta", "label": "Another section"},
                ],
            )


class GraphBuilderEdgeValidationTest(unittest.TestCase):
    def test_cluster_reads_a_staged_raw_graph_and_writes_a_fresh_output(self) -> None:
        with TemporaryDirectory() as directory:
            out = Path(directory)
            graph = out / "graph.json"
            graph.write_text("raw", encoding="utf-8")

            def fake_run(*args: str, **_kwargs: object) -> None:
                self.assertFalse(graph.exists())
                self.assertEqual("raw", (out / ".graphify_raw.json").read_text())
                self.assertIn("--graph", args)
                graph.write_text("clustered", encoding="utf-8")

            with (
                patch.object(build_project_graph, "OUT", out),
                patch.object(build_project_graph, "GRAPH", graph),
                patch.object(build_project_graph, "run", side_effect=fake_run),
            ):
                cluster_raw_graph("graphify")

            self.assertEqual("clustered", graph.read_text(encoding="utf-8"))
            self.assertFalse((out / ".graphify_raw.json").exists())

    def test_duplicate_node_ids_follow_networkx_last_attributes_win(self) -> None:
        nodes = deduplicate_nodes(
            [
                {"id": "same", "label": "old", "source_file": "one.py"},
                {"id": "same", "label": "new"},
                {"id": "other", "label": "Other"},
            ]
        )

        self.assertEqual(2, len(nodes))
        self.assertEqual(
            {"id": "same", "label": "new", "source_file": "one.py"}, nodes[0]
        )

    def test_digraph_may_retain_one_extracted_relation_variant(self) -> None:
        expected = {
            ("caller", "target", "calls"),
            ("caller", "target", "references"),
            ("module", "symbol", "imports_from"),
            ("module", "symbol", "re_exports"),
        }
        actual = {
            ("caller", "target", "references"),
            ("module", "symbol", "re_exports"),
        }
        self.assertEqual((set(), set()), extracted_edge_issues(expected, actual))

    def test_real_pair_loss_and_unextracted_relation_are_reported(self) -> None:
        expected = {
            ("caller", "target", "calls"),
            ("module", "symbol", "imports_from"),
        }
        actual = {("caller", "target", "contains")}
        self.assertEqual(
            ({("module", "symbol")}, {("caller", "target")}),
            extracted_edge_issues(expected, actual),
        )


if __name__ == "__main__":
    unittest.main()
