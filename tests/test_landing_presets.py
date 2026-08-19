"""The landing page may only advertise trips the setup form can actually build.

A card that says "Iceland 5-Day Nature & Glaciers" is a promise. The picker offers
32 countries and Iceland was not one of them, so the promise ended at a form that
could not accept it -- the worst kind of broken, because nothing errors and the
visitor concludes the product is confused rather than the card.

Read out of the TSX rather than duplicated here, so this fails when someone adds a
fourth city, not when someone remembers to update a list.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from travel_planner.destinations import city_options, country_options

SOURCE = Path(__file__).resolve().parents[1] / "web" / "src" / "stages" / "TripsPage.tsx"


def advertised() -> set[tuple[str, str]]:
    """Every (city, country) the landing page shows, in either field order."""

    text = SOURCE.read_text(encoding="utf-8")
    pairs = set(re.findall(r'city:\s*"([^"]+)",\s*\n\s*country:\s*"([^"]+)"', text))
    pairs |= {(city, country) for country, city in
              re.findall(r'country:\s*"([^"]+)",\s*\n\s*city:\s*"([^"]+)"', text)}
    return pairs


class LandingPresetsTest(unittest.TestCase):
    def test_the_page_advertises_something(self):
        # A regex that silently matches nothing would make every test below pass.
        self.assertGreaterEqual(len(advertised()), 4)

    def test_every_advertised_country_is_offered_by_the_picker(self):
        offered = set(country_options())
        for city, country in sorted(advertised()):
            with self.subTest(city=city, country=country):
                self.assertIn(country, offered)

    def test_every_advertised_city_is_offered_for_its_country(self):
        for city, country in sorted(advertised()):
            with self.subTest(city=city, country=country):
                self.assertIn(city, set(city_options(country)))


if __name__ == "__main__":
    unittest.main()
