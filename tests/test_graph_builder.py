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

    AMBIGUOUS = [
        {"id": "beta", "label": "Another section"},
        {"id": "alpha", "label": "One section"},
    ]

    def test_an_empty_extraction_always_blocks(self) -> None:
        """The per-ticket presence guard `--check` relies on. Not weakened."""

        for required in (True, False):
            with self.subTest(required=required):
                with self.assertRaisesRegex(RuntimeError, "produced no node"):
                    resolve_ticket_node("WF-012", self.TITLE, [], required=required)

    def test_ambiguity_blocks_when_the_chosen_id_is_used(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Could not resolve"):
            resolve_ticket_node("WF-012", self.TITLE, self.AMBIGUOUS, required=True)

    def test_ambiguity_is_resolved_deterministically_when_the_id_is_unused(self) -> None:
        """`WF-039`. Its node id is read only as an endpoint of a `blocked_by` edge, and
        it neither has blockers nor is one — so a paid rebuild aborted twice over a value
        nothing reads. Candidates are already scoped to the ticket's own file, so the
        smallest id still anchors the right document."""

        self.assertEqual(
            "alpha",
            resolve_ticket_node("WF-012", self.TITLE, self.AMBIGUOUS, required=False)["id"],
        )


class DuplicateModuleNodeTest(unittest.TestCase):
    """Extraction emits a module twice when a document cites it by path."""

    def test_a_py_suffixed_twin_folds_into_the_real_node(self) -> None:
        """`tests_test_x_py` and `tests_test_x` are the same file. Both land in the raw
        node set, so the pair guard treats an edge to the twin as real -- then clustering
        collapses the duplicate and the build fails claiming data was lost. Measured on
        `wayfinder_tickets_046... -> tests_test_assumed_windows_py`, 2026-08-07."""

        from scripts.build_project_graph import SOURCE_SUFFIX_IDS

        node_ids = {
            "tests_test_x", "tests_test_x_py",
            "web_src_shared_names", "web_src_shared_names_ts",
            "travel_planner_areas",
        }
        suffixed = {
            node_id: stem
            for node_id in node_ids
            for suffix in SOURCE_SUFFIX_IDS
            if node_id.endswith(suffix) and (stem := node_id[: -len(suffix)]) in node_ids
        }

        self.assertEqual(
            {
                "tests_test_x_py": "tests_test_x",
                "web_src_shared_names_ts": "web_src_shared_names",
            },
            suffixed,
        )

    def test_a_twin_spelled_without_a_separator_also_folds(self) -> None:
        """The same duplicate, spelled with the extension run onto the stem.

        Measured on the `WF-048` rebuild, 2026-08-07: extraction produced
        `travel_planner_destinationspy` and `web_src_routestsx` beside the real nodes,
        the pair guard demanded both survive, and the build failed having already been
        paid for. The `_py`/`_ts` spellings were the only ones listed, so the list is
        maintained as incomplete rather than exhaustive.
        """

        from scripts.build_project_graph import SOURCE_SUFFIX_IDS

        node_ids = {
            "travel_planner_destinations", "travel_planner_destinationspy",
            "web_src_routes", "web_src_routestsx",
            "web_src_stages_tripspage", "web_src_stages_tripspagetsx",
            "travel_planner_areas",
        }
        suffixed = {
            node_id: stem
            for node_id in node_ids
            for suffix in SOURCE_SUFFIX_IDS
            if node_id.endswith(suffix) and (stem := node_id[: -len(suffix)]) in node_ids
        }

        self.assertEqual(
            {
                "travel_planner_destinationspy": "travel_planner_destinations",
                "web_src_routestsx": "web_src_routes",
                "web_src_stages_tripspagetsx": "web_src_stages_tripspage",
            },
            suffixed,
        )

    def test_a_word_merely_ending_in_an_extension_is_not_folded(self) -> None:
        """The separator-less spelling widens what can match, so the guard that keeps it
        honest is that the stem must itself be a node.

        `wayfinder_tickets` ends in `ts` and `travel_planner_summary` in `md`; neither
        `wayfinder_ticke` nor `travel_planner_summ` is a node, so neither folds. The
        residual hazard is a genuine pair like `x_even` and `x_events` both existing --
        vanishingly unlikely for identifier-derived ids, and every fold is now printed
        by the build, so a wrong one is visible rather than silent.
        """

        from scripts.build_project_graph import SOURCE_SUFFIX_IDS

        node_ids = {
            "wayfinder_tickets", "travel_planner_summary", "web_src_components",
            "travel_planner_areas",
        }
        suffixed = {
            node_id: stem
            for node_id in node_ids
            for suffix in SOURCE_SUFFIX_IDS
            if node_id.endswith(suffix) and (stem := node_id[: -len(suffix)]) in node_ids
        }

        self.assertEqual({}, suffixed)

    def test_a_lone_py_node_is_left_alone(self) -> None:
        """Only a *twin* is folded. A node that exists solely under the suffixed name is
        the real node, and rewriting it would point edges at nothing."""

        from scripts.build_project_graph import SOURCE_SUFFIX_IDS

        node_ids = {"tests_only_here_py", "web_src_only_here_ts", "travel_planner_areas"}
        suffixed = {
            node_id: stem
            for node_id in node_ids
            for suffix in SOURCE_SUFFIX_IDS
            if node_id.endswith(suffix) and (stem := node_id[: -len(suffix)]) in node_ids
        }

        self.assertEqual({}, suffixed)


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
