"""A preview goes stale when the plan changes, not when evidence is re-read.

`activate_plan_preview` compared a digest of the whole optimizer input, and that
input carries `retrieved_at` on every provider-sourced fact. The free build path
refreshes opening hours and routes, each write stamps a new time, and so a preview
built seconds earlier refused as `preview_stale` with an empty detail -- reported as
"it always says stale", which was accurate and impossible to act on.

The guard still has to bite. These check both directions: provenance is ignored, and
anything that could move a stop is not.
"""

from __future__ import annotations

import unittest

from travel_planner.actions import _changed_sections, _plan_digest, _without_volatile


def _input(*, start: str = "09:00", fetched: str = "2026-08-20T04:36:22", places=("a",)):
    return {
        "facts": [
            {
                "subject_id": place,
                "fact_type": "opening_interval",
                "value": {"start": start, "end": "18:00"},
                "retrieved_at": fetched,
                "expires_at": "2026-09-20T00:00:00",
            }
            for place in places
        ],
        "thresholds": {"walking_minutes_per_leg": 25},
        "trip": {"usable_windows": [{"start": "08:00", "end": "20:00"}]},
    }


class PlanDigestTest(unittest.TestCase):
    def test_re_reading_the_same_evidence_is_not_a_change(self):
        self.assertEqual(
            _plan_digest(_input(fetched="2026-08-20T04:36:22")),
            _plan_digest(_input(fetched="2026-08-20T05:11:03")),
        )

    def test_a_moved_window_is_a_change(self):
        self.assertNotEqual(_plan_digest(_input(start="09:00")), _plan_digest(_input(start="10:00")))

    def test_an_added_place_is_a_change(self):
        self.assertNotEqual(
            _plan_digest(_input(places=("a",))), _plan_digest(_input(places=("a", "b")))
        )

    def test_a_changed_threshold_is_a_change(self):
        tighter = _input()
        tighter["thresholds"] = {"walking_minutes_per_leg": 15}
        self.assertNotEqual(_plan_digest(_input()), _plan_digest(tighter))

    def test_a_changed_trip_window_is_a_change(self):
        later = _input()
        later["trip"] = {"usable_windows": [{"start": "10:00", "end": "20:00"}]}
        self.assertNotEqual(_plan_digest(_input()), _plan_digest(later))

    def test_provenance_is_stripped_at_every_depth(self):
        stripped = _without_volatile(_input())
        self.assertNotIn("retrieved_at", stripped["facts"][0])
        self.assertNotIn("expires_at", stripped["facts"][0])
        # And nothing else went with it.
        self.assertEqual({"start": "09:00", "end": "18:00"}, stripped["facts"][0]["value"])
        self.assertEqual("opening_interval", stripped["facts"][0]["fact_type"])

    def test_the_refusal_can_name_what_moved(self):
        self.assertEqual({"facts"}, _changed_sections(_input(), _input(start="10:00")))
        self.assertEqual(set(), _changed_sections(_input(), _input(fetched="2026-08-21T00:00:00")))


if __name__ == "__main__":
    unittest.main()
