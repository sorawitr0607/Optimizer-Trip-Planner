"""Every avoid chip must be able to change an answer.

`late_meals` and `heavy_crowds` were offered on the setup form for months and read
by nothing: the optimizer never asked about either, and neither reached its
thresholds. A chip that cannot change a plan is worse than a missing one, because
ticking it is a statement the product then ignores.

A tag qualifies one of two ways, which are the only two routes into the engine:
it turns into a threshold the optimizer honours, or the optimizer asks `_dislikes`
about it directly. Anything else is decoration.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from travel_planner.actions import _comfort_thresholds
from travel_planner.setup import AVOID_TAGS

OPTIMIZER = Path(__file__).resolve().parents[1] / "travel_planner" / "optimizer.py"


def consulted_directly() -> set[str]:
    """Tags the optimizer asks `_dislikes` about, read out of its source."""

    return set(re.findall(r'_dislikes\(\s*snapshot\s*,\s*"([a-z_]+)"', OPTIMIZER.read_text()))


class AvoidTagsReachThePlannerTest(unittest.TestCase):
    def test_the_source_scan_finds_something(self):
        # A regex that matched nothing would make the test below vacuous.
        self.assertIn("tourist_traps", consulted_directly())

    def test_every_avoid_tag_reaches_the_optimizer(self):
        asked = consulted_directly()
        for tag in AVOID_TAGS:
            with self.subTest(tag=tag):
                becomes_thresholds = bool(_comfort_thresholds({"avoid": [tag], "comfort": []}))
                self.assertTrue(
                    becomes_thresholds or tag in asked,
                    f"{tag} is offered on the form but reaches neither the thresholds "
                    f"nor a _dislikes check, so ticking it cannot change a plan",
                )

    def test_heavy_crowds_sets_the_values_the_regression_records(self):
        # Not invented: the Shanghai ferry fixture carries exactly these, and its
        # acceptable outcome is "scheduled with >= 20 minutes of boarding buffer".
        thresholds = _comfort_thresholds({"avoid": ["heavy_crowds"], "comfort": []})
        self.assertEqual("low", thresholds["crowd_tolerance"])
        self.assertEqual(20, thresholds["minimum_boarding_buffer_minutes"])

    def test_walking_and_crowd_preferences_do_not_exclude_each_other(self):
        # The walking rules are an if/elif ladder; crowds and queues are separate
        # questions and must not fall off the end of it.
        thresholds = _comfort_thresholds(
            {"avoid": ["plain_long_walks", "heavy_crowds", "long_queues"], "comfort": []}
        )
        self.assertIn("plain_walking_minutes_per_day", thresholds)
        self.assertIn("crowd_tolerance", thresholds)
        self.assertIn("maximum_queue_minutes", thresholds)


if __name__ == "__main__":
    unittest.main()
