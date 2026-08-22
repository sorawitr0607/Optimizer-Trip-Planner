"""The hours the owner wants to be out, instead of a pair of literals.

`_optimizer_input` built every day's window from `start = "08:00"` / `end = "22:00"` --
the same shape of invention `WF-046` argued against for opening hours, and with the same
consequence: a plan built for someone who does not want a 08:00 start says nothing about
that, it simply schedules one.

Setup asks now. `setup.DEFAULT_ACTIVE_START` / `DEFAULT_ACTIVE_END` hold the old literals
so a draft saved before the field existed plans identically -- which is what keeps the 27
historic regressions byte-identical, since none of them carries the field.

Arrival and departure still tighten their own day. Those are flights; active hours are a
preference, and the flight wins.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from travel_planner import setup as setup_module
from travel_planner.actions import PlannerActions

from tests.test_setup_discovery import FakePlaceProvider


class ActiveHoursTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.actions = PlannerActions(
            Path(self.directory.name) / "hours.sqlite3", place_provider=FakePlaceProvider()
        )
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="explore_first"
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _confirm(self, **extra: object) -> None:
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date="2030-01-01",
            end_date="2030-01-03",
            accommodation_status="booked",
            confirmed=True,
            **extra,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        for item in self.actions.get_latest_discovery(
            self.trip.trip_id
        ).candidates.as_dict()["candidates"]:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=item["place_id"], action="must_do"
            )

    def _windows(self) -> list[dict]:
        return self.actions._optimizer_input(self.trip.trip_id)["trip"]["usable_windows"]

    def test_saying_nothing_plans_exactly_as_before(self) -> None:
        """The whole safety of the change: the default is the literal it replaced."""

        self._confirm()
        windows = self._windows()

        self.assertEqual(3, len(windows))
        for window in windows:
            self.assertEqual(setup_module.DEFAULT_ACTIVE_START, window["start"])
            self.assertEqual(setup_module.DEFAULT_ACTIVE_END, window["end"])
        self.assertEqual("08:00", setup_module.DEFAULT_ACTIVE_START)
        self.assertEqual("22:00", setup_module.DEFAULT_ACTIVE_END)

    def test_the_owner_s_hours_reach_every_day(self) -> None:
        self._confirm(active_start="10:30", active_end="19:00")
        windows = self._windows()

        self.assertEqual(
            [("10:30", "19:00")] * 3,
            [(window["start"], window["end"]) for window in windows],
        )

    def test_a_flight_still_tightens_its_own_day(self) -> None:
        """Active hours are a preference; an arrival time is a fact about an aeroplane."""

        self._confirm(
            active_start="09:00", active_end="21:00",
            arrival_time="14:00", departure_time="23:30",
        )
        windows = self._windows()

        self.assertEqual("14:00", windows[0]["start"], "arrival must win on day one")
        self.assertEqual("21:00", windows[0]["end"])
        self.assertEqual("09:00", windows[1]["start"], "the middle day is the owner's")
        self.assertEqual("23:30", windows[-1]["end"], "departure must win on the last day")

    def test_the_hours_are_recorded_on_the_draft_so_the_hash_moves(self) -> None:
        """Changing them has to invalidate a preview, which the payload hash is how."""

        self._confirm(active_start="10:00", active_end="18:00")
        basics = self.actions.get_setup(self.trip.trip_id).snapshot.as_dict()["trip_basics"]
        self.assertEqual("10:00", basics["active_start"])
        self.assertEqual("18:00", basics["active_end"])

    def test_a_window_that_closes_before_it_opens_is_refused(self) -> None:
        from travel_planner.actions import PlannerRefusal

        self._confirm(active_start="20:00", active_end="07:00")
        with self.assertRaises(PlannerRefusal) as caught:
            self._windows()
        self.assertEqual("no_planning_time", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
