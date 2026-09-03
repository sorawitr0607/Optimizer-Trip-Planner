"""What may enter the catalogue, and under which family.

A candidate in the catalogue is one the deck offers, the ranking scores and the optimizer
can schedule onto a day. Both defects here reached a real itinerary.
"""

from __future__ import annotations

import unittest

from travel_planner.providers import (
    LODGING_CATEGORIES,
    TOURISM_FAMILIES,
    OpenStreetMapProvider,
    _category,
)


def element(**tags: str) -> dict:
    return {"type": "node", "id": 1, "lat": 35.6896, "lon": 139.7006, "tags": tags}


class CategoryTest(unittest.TestCase):
    def test_the_query_and_the_resolver_share_one_set(self) -> None:
        """They were two literals, and the drift is what mislabelled a hotel."""

        selector = OpenStreetMapProvider.FAMILY_SELECTORS[0]
        for family in TOURISM_FAMILIES:
            self.assertIn(family, selector, f"{family} is accepted but never asked for")
        # And nothing is asked for that would not be accepted back.
        asked = selector.split('^(')[1].split(')$')[0].split("|")
        self.assertEqual(TOURISM_FAMILIES, set(asked))

    def test_a_family_tourism_value_is_the_category(self) -> None:
        for family in sorted(TOURISM_FAMILIES):
            self.assertEqual(family, _category({"tourism": family}))

    def test_a_tourism_value_the_query_never_asked_for_is_not_the_category(self) -> None:
        """The mislabelling. A place matched for being `historic` was called `hotel`.

        `tourism` was returned unconditionally and first, so whatever a place happened to
        also carry won — and `tourism=hotel` is the one that reached the owner's plan.
        Falling through names the tag that actually put the place in the catalogue.
        """

        self.assertEqual("historic", _category({"tourism": "hotel", "historic": "yes"}))
        self.assertEqual("marketplace", _category({"tourism": "motel", "amenity": "marketplace"}))
        self.assertEqual("park", _category({"tourism": "hostel", "leisure": "park"}))


class LodgingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OpenStreetMapProvider()

    def test_a_plain_hotel_never_becomes_a_candidate(self) -> None:
        """"The hotel as an 82-min attraction looks suspicious" — it was in the catalogue.

        `Toyoko Inn Shinjuku Kabukicho` was a candidate with `category: "hotel"`, and the
        optimizer gave it a sightseeing slot. Dropped at the boundary rather than filtered
        later, because a candidate in the catalogue is one the deck offers and the plan can
        schedule.
        """

        for lodging in sorted(LODGING_CATEGORIES):
            self.assertIsNone(
                self.provider._item(element(name="Toyoko Inn", tourism=lodging)),
                f"tourism={lodging} still became a candidate",
            )

    def test_a_hotel_that_is_also_a_landmark_stays(self) -> None:
        """A palace converted into a hotel is in the catalogue for the palace.

        Checked because the blunt fix — dropping anything whose category is lodging —
        would lose it, and `Pousada do Porto Freixo Palace Hotel` is a real candidate with
        a Commons category for the palace it occupies.
        """

        kept = self.provider._item(
            element(name="Palácio do Freixo", tourism="hotel", historic="palace")
        )
        self.assertIsNotNone(kept)
        self.assertEqual("historic", kept["category"])

    def test_an_ordinary_attraction_is_untouched(self) -> None:
        kept = self.provider._item(element(name="Tokyo National Museum", tourism="museum"))
        self.assertIsNotNone(kept)
        self.assertEqual("museum", kept["category"])


if __name__ == "__main__":
    unittest.main()
