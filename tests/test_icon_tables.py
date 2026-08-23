"""The chip glyph tables must cover the vocabularies they draw.

`web/src/shared/tagIcons.tsx` maps a code to a lucide glyph for three chip rows:
trip-style tags on `/setup`, readiness categories on `/readiness`, and expense
categories on `/split` and `/costs`. Two of those vocabularies are **Python
tuples**, so a Vitest test cannot see them — a category added to
`checklist.CATEGORIES` would ship as a chip wearing the fallback glyph and
nothing would say so. `tagIcons.test.tsx` covers the tag table, which does live
in the JSON catalogue; this covers the two that do not.

Parsing TypeScript with a regular expression is normally the wrong tool. It is
right here because the alternative is no check at all, the shape being read is a
flat object literal of `key: Icon,` lines, and the test fails loudly rather than
silently if that shape ever changes — `test_the_tables_were_actually_found`
exists for exactly that.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from travel_planner import checklist, costs


ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "web" / "src" / "shared" / "tagIcons.tsx"


def table(name: str) -> set[str]:
    """The keys of one `export const <name> = { … }` object literal."""

    text = ICONS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = \{{(.*?)\n\}} as const", text, re.S)
    if match is None:
        return set()
    return set(re.findall(r"^\s{2}(\w+):", match.group(1), re.M))


class IconTableTest(unittest.TestCase):
    def test_the_tables_were_actually_found(self) -> None:
        # Guards the regex above: an empty table would make every other assertion
        # in this file pass by comparing nothing against nothing.
        self.assertGreater(len(table("CHECKLIST_ICONS")), 5)
        self.assertGreater(len(table("COST_ICONS")), 3)
        self.assertGreater(len(table("TAG_ICONS")), 20)

    def test_every_readiness_category_has_a_glyph(self) -> None:
        missing = set(checklist.CATEGORIES) - table("CHECKLIST_ICONS")

        self.assertEqual(set(), missing)

    def test_no_glyph_for_a_readiness_category_that_does_not_exist(self) -> None:
        spare = table("CHECKLIST_ICONS") - set(checklist.CATEGORIES)

        self.assertEqual(set(), spare)

    def test_every_expense_category_has_a_glyph(self) -> None:
        missing = set(costs.CATEGORIES) - table("COST_ICONS")

        self.assertEqual(set(), missing)

    def test_no_glyph_for_an_expense_category_that_does_not_exist(self) -> None:
        spare = table("COST_ICONS") - set(costs.CATEGORIES)

        self.assertEqual(set(), spare)


if __name__ == "__main__":
    unittest.main()
