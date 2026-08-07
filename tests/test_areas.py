from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from travel_planner import areas
from travel_planner.actions import PlannerActions, PlannerRefusal
from travel_planner.providers import OsmAreaAmenitiesProvider, ProviderUnavailable
from travel_planner.transit import Edge, Stop, TransitGraph
from tests.test_routes import FakePlaceProvider


def area(area_id: str, **overrides) -> dict:
    base = {
        "area_id": area_id,
        "name": area_id.title(),
        "names": {"en": area_id.title()},
        "latitude": 25.0,
        "longitude": 121.5,
        "total_travel_minutes": 60,
        "reachable_place_count": 3,
        "access_walk_minutes": 0.0,
        "line_count": 2,
        "food_count": 100,
        "after_dark_count": 10,
        "lodging_count": 20,
    }
    base.update(overrides)
    return base


class AreaScoringTest(unittest.TestCase):
    def test_a_two_minute_difference_does_not_become_a_forty_point_gap(self) -> None:
        """The first version rank-scaled travel time and manufactured precision.

        Measured on the real trip: the eight shortlisted Taipei stations averaged 20 to
        22 minutes to the whole plan, and stretching that across the full 45 points made
        the leader look decisive when the honest answer is that they are equivalent. A
        ratio against the best says so.
        """

        report = areas.score_areas(
            [
                area("alpha", total_travel_minutes=60),  # 20 min per place
                area("beta", total_travel_minutes=66),  # 22 min per place
            ],
            place_count=3,
        )

        alpha, beta = report["areas"]
        self.assertEqual(45.0, alpha["factors"]["travel_time"]["score"])
        self.assertEqual(40.9, beta["factors"]["travel_time"]["score"])
        self.assertLess(alpha["total_score"] - beta["total_score"], 5.0)

    def test_food_counts_in_the_hundreds_still_discriminate(self) -> None:
        """A linear scale saturated at 30 gave every Taipei station a flat 15 of 15.

        The counts really do run 150-586 within 600 m, so the scale has to be
        logarithmic to leave any room between "nowhere to eat" and "plenty".
        """

        def food_score(count: int) -> float:
            report = areas.score_areas([area("a", food_count=count)], place_count=3)
            return report["areas"][0]["factors"]["food_nearby"]["score"]

        self.assertLess(food_score(20), 10.0)
        self.assertEqual(15.0, food_score(400))
        # Above saturation the score stops moving, rather than rewarding density nobody
        # can act on.
        self.assertEqual(food_score(400), food_score(586))
        # The shape, not just the ceiling. 150 places to eat is the low end of what
        # central Taipei actually returns and is already "plenty", so it must score near
        # full marks. Straight division by the same saturation gives it 5.6 of 15 --
        # claiming 586 is three times better than 150, which is the false precision the
        # log scale exists to avoid. Raising the ceiling alone does not fix that, which
        # is why this assertion is here: without it the test passes under either scale.
        self.assertGreater(food_score(150), 12.0)

    def test_the_gaps_are_reported_on_every_result_including_an_empty_one(self) -> None:
        full = areas.score_areas([area("alpha")], place_count=3)
        empty = areas.score_areas([], place_count=3)

        for report in (full, empty):
            self.assertEqual(list(areas.NOT_EVALUATED), report["not_evaluated"])
        self.assertIn("AREA_PRICE_NOT_EVALUATED", full["not_evaluated"])
        self.assertIn(
            "AREA_ROOM_TYPE_AND_FAMILY_CAPACITY_NOT_EVALUATED", full["not_evaluated"]
        )
        self.assertEqual("NO_AREA_REACHES_ANY_SELECTED_PLACE", empty["reason"])
        self.assertEqual([], empty["areas"])

    def test_an_area_missing_a_place_is_kept_and_labelled_not_dropped(self) -> None:
        report = areas.score_areas(
            [area("partial", reachable_place_count=2, total_travel_minutes=30)],
            place_count=3,
        )

        self.assertEqual(1, len(report["areas"]))
        self.assertIn("AREA_DOES_NOT_REACH_EVERY_PLACE", report["areas"][0]["notes"])

    def test_travel_time_is_compared_per_place_not_per_total(self) -> None:
        """Otherwise an area reaching two near stops beats one reaching all three."""

        report = areas.score_areas(
            [
                area("near_two", reachable_place_count=2, total_travel_minutes=30),
                area("all_three", reachable_place_count=3, total_travel_minutes=42),
            ],
            place_count=3,
        )

        by_id = {item["area_id"]: item for item in report["areas"]}
        self.assertEqual(15, by_id["near_two"]["median_travel_minutes"])
        self.assertEqual(14, by_id["all_three"]["median_travel_minutes"])
        self.assertGreater(
            by_id["all_three"]["factors"]["travel_time"]["score"],
            by_id["near_two"]["factors"]["travel_time"]["score"],
        )

    def test_ranking_is_deterministic_and_ties_break_on_area_id(self) -> None:
        first = areas.score_areas([area("bravo"), area("alpha")], place_count=3)
        second = areas.score_areas([area("alpha"), area("bravo")], place_count=3)

        self.assertEqual(first, second)
        self.assertEqual(["alpha", "bravo"], [item["area_id"] for item in first["areas"]])


class FakeAmenitiesProvider:
    name = "fake_areas"
    operation = "openstreetmap:areas"
    cache_ttl_days = 7
    RADIUS_METRES = 600

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def cache_descriptor(self, points):
        return {"provider": self.name, "points": [p["area_id"] for p in points]}

    def counts(self, points):
        self.calls += 1
        if self.fail:
            raise ProviderUnavailable("Provider HTTP 504")
        return {
            point["area_id"]: {
                "food_count": 120,
                "after_dark_count": 9,
                "lodging_count": 30,
            }
            for point in points
        }


class FakeMetroProvider:
    """Two stations on one line, one beside each of the fake catalogue's places."""

    def __init__(self, graph: TransitGraph) -> None:
        self.graph = graph

    def build_graph(self) -> TransitGraph:
        return self.graph


def two_station_graph() -> TransitGraph:
    # Placed beside `FakePlaceProvider`'s three places, which sit at 25.04/121.57,
    # 25.05/121.58 and 25.06/121.59.
    stops = {
        # Two nodes for one station, which is what OSM really returns -- the platform
        # and the stop position. They must collapse to one area.
        # Chinese primary name with an English tag, which is the Taipei case.
        "n1": Stop("n1", "中山", 25.0450, 121.5750, name_en="Zhongshan"),
        # The same station's other platform node, with the tag missing on this one.
        "n1b": Stop("n1b", "中山", 25.0451, 121.5751),
        # No English name anywhere: the local name has to stand alone.
        "n2": Stop("n2", "Harbour", 25.0550, 121.5850),
        # No name: unusable as advice, so it must be skipped rather than listed by id.
        "n3": Stop("n3", "n3", 25.0500, 121.5800),
    }
    edge = Edge(ride_minutes=3.0, wait_minutes=3.0, route_id="L1", basis="nominal")
    edges = {("n1", "n2"): edge, ("n2", "n1"): edge}
    return TransitGraph(stops, edges)


class AreaRecommendationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.amenities = FakeAmenitiesProvider()
        self.actions = PlannerActions(
            Path(self.directory.name) / "areas.sqlite3",
            place_provider=FakePlaceProvider(),
            transit_provider=FakeMetroProvider(two_station_graph()),
            area_amenities_provider=self.amenities,
        )
        self.trip = self.actions.create_trip(name="Tokyo", destination="Tokyo")
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date="2030-01-01",
            end_date="2030-01-02",
            accommodation_status="not_booked",
            confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        for item in self.actions.get_latest_discovery(
            self.trip.trip_id
        ).candidates.as_dict()["candidates"]:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=item["place_id"], action="must_do"
            )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_platform_nodes_collapse_to_one_named_area(self) -> None:
        """`transit.STOP_TAGS` admits platforms so relations resolve, which means one
        station arrives as up to six stops -- six for 板橋 in the real Taipei graph. The
        first version filled its shortlist with near-duplicates of two stations."""

        report = self.actions.recommend_areas(self.trip.trip_id)

        names = [item["name"] for item in report["areas"]]
        self.assertEqual(sorted(set(names)), sorted(names))
        self.assertIn("中山", names)
        # The unnamed stop is absent: an area the app cannot name is not advice.
        self.assertNotIn("n3", names)

    def test_a_station_carries_its_english_name_beside_the_local_one(self) -> None:
        """`en` was the Chinese string until 2026-08-07, so every area rendered as 中山
        or 西門 with nothing readable beside it. OSM tags `name:en` on 370 of Taipei's
        437 stop nodes and `graph_from_osm` was discarding all of them."""

        report = self.actions.recommend_areas(self.trip.trip_id)
        by_local = {item["names"].get("local"): item["names"] for item in report["areas"]}

        self.assertEqual({"local": "中山", "en": "Zhongshan"}, by_local["中山"])
        # No `name:en` in OSM means no `en` key at all, rather than the local string
        # copied into it — or the screen would print the same name twice.
        self.assertEqual({"local": "Harbour"}, by_local["Harbour"])

    def test_amenity_counts_reach_the_score_and_are_fetched_once(self) -> None:
        first = self.actions.recommend_areas(self.trip.trip_id)
        second = self.actions.recommend_areas(self.trip.trip_id)

        self.assertTrue(first["amenities_counted"])
        self.assertTrue(second["amenities_counted"])
        self.assertEqual(120, first["areas"][0]["counts"]["food_count"])
        # The second call is served from the provider cache.
        self.assertEqual(1, self.amenities.calls)

    def test_the_free_call_is_recorded_in_the_ledger_at_zero(self) -> None:
        """Free, but counted. An unpriced operation raises, and call counts have to stay
        reconcilable even when every one of them costs nothing."""

        before = self.actions.paid_usage_status()["spent_usd"]

        self.actions.recommend_areas(self.trip.trip_id)

        status = self.actions.paid_usage_status()
        self.assertEqual(before, status["spent_usd"])
        self.assertIn("openstreetmap:areas", status["by_operation"])
        self.assertEqual(0.0, status["by_operation"]["openstreetmap:areas"]["estimated_usd"])

    def test_a_refusing_endpoint_degrades_rather_than_failing_the_ranking(self) -> None:
        """Travel time and metro access are measured locally, so a ranking without the
        three inferred factors is weaker but still true. The screen is told which."""

        actions = PlannerActions(
            Path(self.directory.name) / "degrade.sqlite3",
            place_provider=FakePlaceProvider(),
            transit_provider=FakeMetroProvider(two_station_graph()),
            area_amenities_provider=FakeAmenitiesProvider(fail=True),
        )
        trip = actions.create_trip(name="Tokyo", destination="Tokyo")
        actions.save_setup(
            trip_id=trip.trip_id,
            main_style=["sightseeing"],
            start_date="2030-01-01",
            end_date="2030-01-02",
            accommodation_status="not_booked",
            confirmed=True,
        )
        actions.discover_places(trip_id=trip.trip_id)
        for item in actions.get_latest_discovery(trip.trip_id).candidates.as_dict()[
            "candidates"
        ]:
            actions.save_candidate_choice(
                trip_id=trip.trip_id, place_id=item["place_id"], action="must_do"
            )

        report = actions.recommend_areas(trip.trip_id)

        self.assertFalse(report["amenities_counted"])
        self.assertTrue(report["areas"])
        self.assertGreater(report["areas"][0]["factors"]["travel_time"]["score"], 0)
        self.assertEqual(0, report["areas"][0]["counts"]["food_count"])

    def test_no_chosen_places_refuses_rather_than_ranking_nothing(self) -> None:
        actions = PlannerActions(
            Path(self.directory.name) / "empty.sqlite3",
            place_provider=FakePlaceProvider(),
            transit_provider=FakeMetroProvider(two_station_graph()),
            area_amenities_provider=FakeAmenitiesProvider(),
        )
        trip = actions.create_trip(name="Tokyo", destination="Tokyo")
        actions.save_setup(
            trip_id=trip.trip_id,
            main_style=["sightseeing"],
            start_date="2030-01-01",
            end_date="2030-01-02",
            accommodation_status="not_booked",
            confirmed=True,
        )

        with self.assertRaises(PlannerRefusal) as caught:
            actions.recommend_areas(trip.trip_id)

        self.assertEqual("no_places_chosen", caught.exception.code)


class AmenitiesQueryTest(unittest.TestCase):
    def test_one_request_carries_every_point_and_the_answer_is_length_checked(self) -> None:
        """Overpass ties a count to its point only by statement order, so a short answer
        means the mapping has shifted. A wrong count per area is worse than none."""

        provider = OsmAreaAmenitiesProvider()
        points = [
            {"area_id": "a", "latitude": 25.0, "longitude": 121.5},
            {"area_id": "b", "latitude": 25.1, "longitude": 121.6},
        ]

        query = provider.amenities_query(points)

        self.assertEqual(6, query.count("out count;"))
        self.assertEqual(1, query.count("[out:json]"))
        self.assertIn("around:600,25.0,121.5", query)
        self.assertIn("around:600,25.1,121.6", query)

        provider._osm._request_json = lambda request: {  # type: ignore[method-assign]
            "elements": [{"type": "count", "tags": {"total": "5"}}] * 5
        }
        with self.assertRaises(ProviderUnavailable):
            provider.counts(points)


if __name__ == "__main__":
    unittest.main()
