"""Building footprints for a zoomed-in map window (`WF-048`).

The window guard is the whole safety of this: a footprint at the full city view is well
under a pixel, so an ungated request fetches six figures of geometry to draw nothing.
These pin the guard, the shape of what comes back, and the cache that keeps panning free.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from travel_planner.actions import PlannerActions, PlannerRefusal
from travel_planner.providers import OpenStreetMapProvider


class RecordingBuildingsProvider:
    """Answers `buildings` without a socket, and counts how often it was asked."""

    name = "fake_places"
    cache_ttl_days = 7

    def __init__(self) -> None:
        self.calls: list[list[float]] = []

    def buildings(self, bbox: list[float]) -> dict:
        self.calls.append(list(bbox))
        return {"bbox": bbox, "buildings": [[[1.0, 2.0], [1.0, 2.1], [1.1, 2.1]]], "too_wide": False}


class BuildingsQueryTest(unittest.TestCase):
    """The provider half, which needs no database and no network."""

    def setUp(self) -> None:
        self.provider = OpenStreetMapProvider()

    def test_the_query_carries_the_window_and_the_limit(self) -> None:
        query = self.provider.buildings_query([25.024, 121.554, 25.044, 121.574])
        self.assertIn("25.02400,121.55400,25.04400,121.57400", query)
        self.assertIn('way["building"]', query)
        self.assertIn(f"out geom {self.provider.buildings_limit};", query)

    def test_a_window_wider_than_the_ceiling_is_refused_without_asking(self) -> None:
        # No stub is installed, so reaching the network at all would raise here — that
        # is the assertion. A too-wide window must be answered from the guard alone.
        result = self.provider.buildings([24.9, 121.4, 25.2, 121.7])
        self.assertTrue(result["too_wide"])
        self.assertEqual([], result["buildings"])

    def test_the_ceiling_is_the_wider_of_the_two_spans(self) -> None:
        # Tall and narrow is still too big to draw: the guard takes the max, so a window
        # that is small in longitude cannot smuggle a huge latitude span past it.
        tall = self.provider.buildings([25.0, 121.55, 25.09, 121.56])
        self.assertTrue(tall["too_wide"])

    def test_rings_are_rounded_deduped_and_dropped_when_too_short(self) -> None:
        elements = [
            # Two points is a line, not a footprint.
            {"geometry": [{"lat": 1.0, "lon": 2.0}, {"lat": 1.0, "lon": 2.1}]},
            # Rounding collapses the first two onto each other; what survives is still
            # a triangle, so it is kept.
            {
                "geometry": [
                    {"lat": 1.000001, "lon": 2.0},
                    {"lat": 1.000002, "lon": 2.0},
                    {"lat": 1.001, "lon": 2.0},
                    {"lat": 1.001, "lon": 2.001},
                ]
            },
            # Rounding leaves only two distinct points, so this one goes.
            {
                "geometry": [
                    {"lat": 5.000001, "lon": 6.0},
                    {"lat": 5.000002, "lon": 6.0},
                    {"lat": 5.001, "lon": 6.0},
                ]
            },
            {"geometry": []},
        ]
        self.provider._overpass_elements = lambda query, timeout=None: elements  # type: ignore[method-assign]
        result = self.provider.buildings([1.0, 2.0, 1.01, 2.01])
        self.assertFalse(result["too_wide"])
        self.assertEqual([[[1.0, 2.0], [1.001, 2.0], [1.001, 2.001]]], result["buildings"])


class RefreshBuildingsTest(unittest.TestCase):
    """The coordinator half: refusals, the cache, and the free ledger row."""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "tourist.sqlite3"
        self.provider = RecordingBuildingsProvider()
        self.actions = PlannerActions(self.database_path, place_provider=self.provider)
        self.trip = self.actions.create_trip(
            name="Taipei New Year",
            destination="Taipei, Taiwan",
            planning_mode="ready_to_schedule",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_an_unknown_trip_is_refused(self) -> None:
        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.refresh_buildings("trip_missing", bbox=[1.0, 2.0, 1.01, 2.01])
        self.assertEqual("unknown_trip", caught.exception.code)

    def test_a_malformed_window_is_refused_with_its_own_code(self) -> None:
        for bad in ([1.0, 2.0, 3.0], "25,121,25,121", [], None):
            with self.subTest(bbox=bad):
                with self.assertRaises(PlannerRefusal) as caught:
                    self.actions.refresh_buildings(self.trip.trip_id, bbox=bad)  # type: ignore[arg-type]
                self.assertEqual("bad_map_window", caught.exception.code)
        self.assertEqual([], self.provider.calls)

    def test_the_same_window_is_fetched_once_and_then_served_from_cache(self) -> None:
        first = self.actions.refresh_buildings(self.trip.trip_id, bbox=[25.0241, 121.5541, 25.0441, 121.5741])
        second = self.actions.refresh_buildings(self.trip.trip_id, bbox=[25.0242, 121.5542, 25.0442, 121.5742])
        self.assertEqual(first, second)
        # Both windows round to the same ~100 m key, so panning a few metres re-reads
        # the work rather than asking for it again.
        self.assertEqual(1, len(self.provider.calls))
        self.assertEqual([25.024, 121.554, 25.044, 121.574], self.provider.calls[0])

    def test_a_different_window_is_its_own_request(self) -> None:
        self.actions.refresh_buildings(self.trip.trip_id, bbox=[25.024, 121.554, 25.044, 121.574])
        self.actions.refresh_buildings(self.trip.trip_id, bbox=[25.064, 121.594, 25.084, 121.614])
        self.assertEqual(2, len(self.provider.calls))

    def test_the_call_is_recorded_at_zero_rather_than_left_off_the_ledger(self) -> None:
        # Free-tier operations are priced at zero rather than skipped, so call counts
        # stay reconcilable against the provider's own view.
        self.actions.refresh_buildings(self.trip.trip_id, bbox=[25.024, 121.554, 25.044, 121.574])
        status = self.actions.paid_usage_status()
        self.assertIn("openstreetmap:buildings", status["by_operation"])
        self.assertEqual(1, status["by_operation"]["openstreetmap:buildings"]["requests"])
        self.assertEqual(0.0, status["spent_usd"])


if __name__ == "__main__":
    unittest.main()
