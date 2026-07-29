from __future__ import annotations

import unittest

from Main.build_project_graph import extracted_edge_issues


class GraphBuilderEdgeValidationTest(unittest.TestCase):
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
