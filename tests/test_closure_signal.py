"""What a free source says about a place still existing, and what is deliberately ignored.

`NHK Studio Park` closed in 2020 and was given four and a half hours on a 2026 plan. The
claims that reveal it are already in the `wbgetentities` response the app makes for
photographs, so this costs no request, no key and no second provider.

**The absences are the load-bearing part.** Reading `P576` instead would have removed Edo
Castle, whose site is the Imperial Palace East Gardens; reading `P5817` would have removed
Tokyo Skytree. Both were measured over 500 candidate QIDs from a real catalogue, and both
are asserted here as absences because the temptation to add them is the hazard.
"""

from __future__ import annotations

import unittest

from travel_planner.providers import WikidataSummaryProvider


class ClosurePropertyTest(unittest.TestCase):
    def test_official_closure_and_end_time_are_read(self) -> None:
        self.assertEqual(("P3999", "P582"), WikidataSummaryProvider.CLOSURE_PROPERTIES)

    def test_demolished_is_not_read(self) -> None:
        """`P576` flagged Edo Castle, an open museum and a monument out of 500 QIDs."""

        self.assertNotIn("P576", WikidataSummaryProvider.CLOSURE_PROPERTIES)

    def test_state_of_use_is_not_read(self) -> None:
        """Its common value is literally "in use", and `Tokyo Skytree` carries it."""

        self.assertNotIn("P5817", WikidataSummaryProvider.CLOSURE_PROPERTIES)


class ClosureExtractionTest(unittest.TestCase):
    """The extraction itself, over hand-built claims and no network."""

    @staticmethod
    def summary_for(claims: dict) -> dict:
        # `summary` already takes an entity, so this needs no patching and no network:
        # everything it does is pure over the claims it is handed.
        return WikidataSummaryProvider().summary(
            "Q1",
            entity={"sitelinks": {}, "claims": claims, "labels": {}, "descriptions": {}},
        )

    @staticmethod
    def stamp(prop: str, time: str) -> dict:
        return {prop: [{"mainsnak": {"datavalue": {"value": {"time": time}}}}]}

    def test_a_zeroed_wikidata_date_keeps_the_source_s_precision(self) -> None:
        # `+2020-00-00` is how Wikidata says "2020, month and day unknown" — exactly what
        # `NHK Studio Park` carries. Kept as stated rather than invented into a real date.
        summary = self.summary_for(self.stamp("P582", "+2020-00-00T00:00:00Z"))
        self.assertEqual("2020-00-00", summary["closed_on"])

    def test_official_closure_wins_over_end_time(self) -> None:
        claims = {
            **self.stamp("P3999", "+2019-04-01T00:00:00Z"),
            **self.stamp("P582", "+2020-00-00T00:00:00Z"),
        }
        self.assertEqual("2019-04-01", self.summary_for(claims)["closed_on"])

    def test_a_place_with_no_closure_claim_says_nothing(self) -> None:
        # The ordinary case, and the one that must stay quiet.
        self.assertIsNone(self.summary_for({})["closed_on"])

    def test_demolished_or_in_use_do_not_close_a_place(self) -> None:
        """Edo Castle and Tokyo Skytree, as claims."""

        edo = self.stamp("P576", "+1869-00-00T00:00:00Z")
        self.assertIsNone(self.summary_for(edo)["closed_on"])

        skytree = {"P5817": [{"mainsnak": {"datavalue": {"value": {"id": "Q55654238"}}}}]}
        self.assertIsNone(self.summary_for(skytree)["closed_on"])


if __name__ == "__main__":
    unittest.main()
