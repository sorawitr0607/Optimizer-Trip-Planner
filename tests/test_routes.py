from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


from travel_planner.actions import MAX_ROUTE_REQUESTS, PlannerActions
from travel_planner.providers import (
    GoogleTimeZoneProvider,
    OpenRouteServiceProvider,
    ProviderBudgetExceeded,
    ProviderUnavailable,
)


class FakeRouteProvider:
    """Stands in for OpenRouteService; tests never touch the network."""

    name = "openrouteservice"
    operation = "openrouteservice:directions"
    cache_ttl_days = 14
    mode = "walk"

    def __init__(self, *, fail_for: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_for = fail_for or set()

    def route(self, origin: dict, destination: dict) -> dict:
        self.calls.append((origin["place_id"], destination["place_id"]))
        if destination["place_id"] in self.fail_for:
            raise ProviderUnavailable("OpenRouteService returned HTTP 503")
        return {
            "origin_id": origin["place_id"],
            "destination_id": destination["place_id"],
            "mode": "walk",
            "duration_minutes": 12,
            "walking_minutes": 12,
            "distance_m": 900,
            "transfers": 0,
            "boarding_buffer_minutes": 0,
            "experience_evidence": [],
            "status": "verified",
            "provider": "openrouteservice",
        }


class FakePlaceProvider:
    name = "fake_places"
    cache_ttl_days = 7

    def cache_descriptor(self, destination: str) -> dict:
        return {"provider": self.name, "destination": destination.casefold()}

    def discover(self, destination: str) -> dict:
        return {
            "items": [
                {
                    "provider_place_id": f"node/{index}",
                    "name": name,
                    "names": {"en": name},
                    "latitude": 25.03 + index / 100,
                    "longitude": 121.56 + index / 100,
                    "category": "viewpoint",
                    "opening_hours": "08:00-20:00",
                    "source_url": f"https://example.test/{index}",
                }
                for index, name in enumerate(("Tower", "Temple", "Market"), start=1)
            ],
            "coverage": {"bbox": [24.9, 121.4, 25.2, 121.7], "known_gaps": []},
            "attribution": "Fake",
        }


class NormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OpenRouteServiceProvider()
        self.origin = {"place_id": "a", "latitude": 25.0330, "longitude": 121.5654}
        self.destination = {"place_id": "b", "latitude": 25.0375, "longitude": 121.5600}

    def test_seconds_and_metres_become_planner_units(self) -> None:
        route = self.provider.normalize(
            {"features": [{"properties": {"summary": {"duration": 612.4, "distance": 842.7}}}]},
            origin=self.origin,
            destination=self.destination,
        )
        self.assertEqual(11, route["duration_minutes"])
        self.assertEqual(11, route["walking_minutes"])
        self.assertEqual(843, route["distance_m"])
        self.assertEqual("walk", route["mode"])
        self.assertEqual("verified", route["status"])
        # A machine-generated foot route is a plain transfer, not a rewarding walk.
        self.assertEqual([], route["experience_evidence"])

    def test_a_sub_minute_route_never_rounds_to_zero(self) -> None:
        route = self.provider.normalize(
            {"features": [{"properties": {"summary": {"duration": 20, "distance": 25}}}]},
            origin=self.origin,
            destination=self.destination,
        )
        self.assertEqual(1, route["duration_minutes"])

    def test_an_incomplete_payload_is_refused_rather_than_defaulted(self) -> None:
        for payload in (
            {"features": []},
            {},
            {"features": [{"properties": {}}]},
            {"features": [{"properties": {"summary": {"duration": 60}}}]},
        ):
            with self.assertRaises(ProviderUnavailable):
                self.provider.normalize(
                    payload, origin=self.origin, destination=self.destination
                )

    def test_a_missing_key_is_reported_without_calling_out(self) -> None:
        with patch.dict(os.environ, {"OPENROUTESERVICE_API_KEY": ""}):
            with self.assertRaisesRegex(ProviderUnavailable, "not configured"):
                self.provider.route(self.origin, self.destination)


class RouteRefreshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "routes.sqlite3"
        self.provider = FakeRouteProvider()
        self.actions = PlannerActions(
            self.path,
            place_provider=FakePlaceProvider(),
            route_provider=self.provider,
        )
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="ready_to_schedule"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date="2030-01-01",
            end_date="2030-01-03",
            accommodation_status="booked",
            confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        self.places = [
            item["place_id"]
            for item in self.actions.get_latest_discovery(
                self.trip.trip_id
            ).candidates.as_dict()["candidates"]
        ]
        for place_id in self.places:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=place_id, action="must_do"
            )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_both_directions_are_fetched_for_every_selected_pair(self) -> None:
        report = self.actions.refresh_routes(self.trip.trip_id)
        count = len(self.places)

        self.assertEqual(count, report["places"])
        self.assertEqual(count * (count - 1), report["pairs_needed"])
        self.assertEqual(report["pairs_needed"], report["fetched"])
        self.assertEqual(0, report["skipped_over_cap"])
        self.assertEqual(0, report["failed"])
        # Direction matters: the optimizer asks for a specific leg.
        self.assertIn((self.places[0], self.places[1]), self.provider.calls)
        self.assertIn((self.places[1], self.places[0]), self.provider.calls)

    def test_a_second_refresh_reads_the_cache_and_makes_no_call(self) -> None:
        self.actions.refresh_routes(self.trip.trip_id)
        calls_after_first = len(self.provider.calls)

        again = self.actions.refresh_routes(self.trip.trip_id)

        self.assertEqual(calls_after_first, len(self.provider.calls))
        self.assertEqual(0, again["fetched"])
        self.assertEqual(again["pairs_needed"], again["from_cache"])

        forced = self.actions.refresh_routes(self.trip.trip_id, force=True)
        self.assertEqual(forced["pairs_needed"], forced["fetched"])

    def test_free_tier_calls_are_counted_in_the_ledger(self) -> None:
        report = self.actions.refresh_routes(self.trip.trip_id)
        status = self.actions.paid_usage_status()
        bucket = status["by_operation"]["openrouteservice:directions"]

        self.assertEqual(report["fetched"], bucket["requests"])
        self.assertEqual(0.0, bucket["estimated_usd"])
        self.assertEqual(0.0, status["estimated_usd"])

    def test_a_provider_outage_leaves_the_other_legs_usable(self) -> None:
        actions = PlannerActions(
            self.path, route_provider=FakeRouteProvider(fail_for={self.places[2]})
        )
        report = actions.refresh_routes(self.trip.trip_id)

        self.assertGreater(report["fetched"], 0)
        self.assertEqual(2, report["failed"])
        self.assertIn("HTTP 503", report["provider_errors"][0])
        stored = {
            (route["origin_id"], route["destination_id"])
            for route in actions.list_routes(self.trip.trip_id)
        }
        self.assertNotIn((self.places[0], self.places[2]), stored)
        self.assertIn((self.places[0], self.places[1]), stored)

    def test_the_request_cap_reports_what_it_skipped(self) -> None:
        with patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 2):
            report = self.actions.refresh_routes(self.trip.trip_id)

        self.assertEqual(2, report["fetched"])
        self.assertEqual(report["pairs_needed"] - 2, report["skipped_over_cap"])
        self.assertEqual(2, report["request_cap"])

    def test_the_cap_limits_one_run_and_not_what_a_trip_can_ever_know(self) -> None:
        """Repeated runs must reach pairs beyond the cap.

        The cache check used to sit inside the fetch loop while the cap sliced a
        fixed sort of *all* pairs, so every run attempted the same first N and the
        N+1th pair was unreachable however many times this ran. On the real Taipei
        trip that pinned route coverage at 60 of 1640 pairs and left every plan
        variant `unavailable` for want of evidence.
        """

        with patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 2):
            first = self.actions.refresh_routes(self.trip.trip_id)
            second = self.actions.refresh_routes(self.trip.trip_id)
            third = self.actions.refresh_routes(self.trip.trip_id)

        self.assertEqual(2, first["fetched"])
        # The point: the later runs fetch *new* pairs rather than re-reporting the
        # first two as cached.
        self.assertEqual(2, second["fetched"])
        self.assertEqual(0, second["from_cache"])
        self.assertEqual(first["pairs_needed"] - 2, second["pairs_needed"])
        stored = {
            (route["origin_id"], route["destination_id"])
            for route in self.actions.list_routes(self.trip.trip_id)
        }
        self.assertEqual(6, len(stored))
        self.assertEqual(third["pairs_needed"] - 2, third["skipped_over_cap"])

    def test_the_cap_spends_itself_on_the_nearest_pairs_first(self) -> None:
        """Under the cap, the pairs most likely to be walked must win.

        Ordering by `place_id` spent 340 free calls on arbitrary pairs of the real
        Taipei trip while every pair the plan actually used stayed unmeasured. A
        missing route falls back to a pessimistic estimate, so the plan showed
        68-minute walks between places a kilometre apart and failed validation on
        them; fetching the same pairs by proximity turned those legs into 14, 10
        and 9 minutes.
        """

        from travel_planner.ranking import _distance_metres

        located = self.actions._route_points(self.trip.trip_id)
        with patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 2):
            self.actions.refresh_routes(self.trip.trip_id)

        by_id = {point["place_id"]: point for point in located}
        fetched = [
            _distance_metres(by_id[route["origin_id"]], by_id[route["destination_id"]])
            for route in self.actions.list_routes(self.trip.trip_id)
        ]
        every_pair = [
            _distance_metres(left, right)
            for left in located
            for right in located
            if left["place_id"] != right["place_id"]
        ]
        # Both fetched legs are among the closest pairs available, not simply the
        # first two by identifier.
        self.assertEqual(2, len(fetched))
        self.assertLessEqual(max(fetched), sorted(every_pair)[1])

    def test_routing_needs_two_located_places(self) -> None:
        empty = PlannerActions(
            Path(self.directory.name) / "empty.sqlite3", route_provider=self.provider
        )
        trip = empty.create_trip(name="Bare", destination="Osaka")
        with self.assertRaises(ValueError) as raised:
            empty.refresh_routes(trip.trip_id)
        self.assertEqual("insufficient_geocoded_places", str(raised.exception))

    def test_routes_clear_the_capability_gap_and_reach_the_optimizer(self) -> None:
        before = self.actions._optimizer_input(self.trip.trip_id)
        self.assertIn("ROUTE_SNAPSHOT_MISSING", before["trip"]["capability_gaps"])
        self.assertEqual([], before["routes"])

        self.actions.refresh_routes(self.trip.trip_id)
        after = self.actions._optimizer_input(self.trip.trip_id)

        self.assertNotIn("ROUTE_SNAPSHOT_MISSING", after["trip"]["capability_gaps"])
        self.assertEqual(len(self.places) * (len(self.places) - 1), len(after["routes"]))
        self.assertEqual({"verified"}, {route["status"] for route in after["routes"]})
        # The timezone gap is untouched by routing.
        self.assertIn("DESTINATION_TIMEZONE_UNVERIFIED", after["trip"]["capability_gaps"])

    def test_an_expired_route_is_reported_stale_and_stops_counting(self) -> None:
        self.actions.refresh_routes(self.trip.trip_id)
        with self.actions.store.connect() as connection:
            connection.execute(
                "UPDATE route_snapshots SET expires_at = '2000-01-01T00:00:00+00:00'"
            )

        routes = self.actions.list_routes(self.trip.trip_id)
        self.assertEqual({"stale"}, {route["status"] for route in routes})
        gaps = self.actions._optimizer_input(self.trip.trip_id)["trip"]["capability_gaps"]
        self.assertIn("ROUTE_SNAPSHOT_MISSING", gaps)

    def test_a_budget_stop_aborts_routing_rather_than_half_reporting(self) -> None:
        self.actions.record_paid_call(operation="google_places:details", count=600)
        with patch(
            "travel_planner.usage.PRICES_USD",
            {**__import__("travel_planner.usage", fromlist=["PRICES_USD"]).PRICES_USD,
             "openrouteservice:directions": 0.01},
        ):
            with self.assertRaises(ProviderBudgetExceeded):
                self.actions.refresh_routes(self.trip.trip_id)


if __name__ == "__main__":
    unittest.main()


class FakeTimeZoneProvider:
    name = "google_timezone"
    operation = "google_timezone:lookup"
    cache_ttl_days = 180
    kind = "destination_timezone"

    def __init__(self, *, payload: dict | None = None) -> None:
        self.calls: list[tuple[float, float]] = []
        self.payload = payload or {
            "status": "OK",
            "timeZoneId": "Asia/Taipei",
            "timeZoneName": "Taiwan Standard Time",
            "rawOffset": 28800,
            "dstOffset": 0,
        }

    def lookup(self, *, latitude: float, longitude: float, timestamp: int) -> dict:
        self.calls.append((latitude, longitude))
        return GoogleTimeZoneProvider().normalize(
            self.payload, latitude=latitude, longitude=longitude
        )


class TransitRouteTest(unittest.TestCase):
    """`WF-038`: transit legs from a local GTFS feed, no network and no cost."""

    FEED = Path(__file__).resolve().parent / "fixtures" / "synthetic_transit_gtfs.zip"

    def setUp(self) -> None:
        from travel_planner.providers import GtfsTransitProvider

        self.directory = TemporaryDirectory()
        self.actions = PlannerActions(
            Path(self.directory.name) / "transit.sqlite3",
            place_provider=FakePlaceProvider(),
            route_provider=FakeRouteProvider(),
            transit_provider=GtfsTransitProvider(),
        )
        # The provider reads its path at construction, so point it at the fixture.
        self.actions.transit_provider._path = str(self.FEED)
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="ready_to_schedule"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id, main_style=["sightseeing"],
            start_date="2030-01-01", end_date="2030-01-03",
            accommodation_status="booked", confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        # `_route_points` reads *selected* places, so a route pair only exists once
        # a choice does.
        for candidate in self.actions.get_latest_discovery(
            self.trip.trip_id
        ).candidates.as_dict()["candidates"]:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id,
                place_id=candidate["place_id"],
                action="must_do",
            )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_a_transit_leg_reports_only_access_walking(self) -> None:
        """The reason this ticket exists: a long ride with a short walk.

        `maximum_walking_minutes_per_leg` measures `walking_minutes`, so a 40-minute
        ride reached by a 2-minute walk passes a 25-minute walking cap that a
        40-minute walk never could. Without it a city trip cannot validate at all.
        """

        report = self.actions.refresh_transit_routes(self.trip.trip_id)
        self.assertEqual(0, report["failed"], report.get("provider_errors"))
        self.assertGreater(report["fetched"], 0)

        transit = [
            route
            for route in self.actions.list_routes(self.trip.trip_id)
            if route["mode"] == "transit"
        ]
        self.assertTrue(transit)
        longest = max(transit, key=lambda route: route["duration_minutes"])
        self.assertGreater(longest["duration_minutes"], 20)
        self.assertLess(longest["walking_minutes"], 10)
        # Derived from a timetable, not looked up in one.
        self.assertEqual("estimated", longest["status"])
        self.assertEqual("gtfs", longest["provider"])

    def test_transit_is_stored_beside_walking_rather_than_replacing_it(self) -> None:
        """The store keys by (origin, destination, mode), so both survive."""

        self.actions.refresh_routes(self.trip.trip_id)
        self.actions.refresh_transit_routes(self.trip.trip_id)
        modes = {route["mode"] for route in self.actions.list_routes(self.trip.trip_id)}
        self.assertEqual({"walk", "transit"}, modes)

    def test_a_transit_call_is_recorded_at_zero_rather_than_left_unpriced(self) -> None:
        self.actions.refresh_transit_routes(self.trip.trip_id)
        rows = [
            row
            for row in self.actions.store.list_paid_usage()
            if row["operation"] == "gtfs:transit"
        ]
        self.assertTrue(rows)
        self.assertEqual(0.0, sum(float(row["estimated_usd"]) for row in rows))

    def test_an_absent_feed_refuses_and_never_invents_a_journey(self) -> None:
        from travel_planner.providers import GtfsTransitProvider

        self.actions.transit_provider = GtfsTransitProvider()
        self.actions.transit_provider._path = str(
            Path(self.directory.name) / "not-a-feed.zip"
        )
        report = self.actions.refresh_transit_routes(self.trip.trip_id)
        self.assertEqual(0, report["fetched"])
        self.assertTrue(report["provider_errors"])
        self.assertIn("GTFS feed unusable", report["provider_errors"][0])


class OsmMetroTransitTest(unittest.TestCase):
    """`WF-038` fallback: metro topology from OpenStreetMap when no feed exists."""

    # Three stations on one line plus a crossing line, in the same place as the fake
    # discovery provider's Tower / Temple / Market.
    ELEMENTS = [
        # Tagged as real stations would be: the graph rejects untagged nodes, because
        # the Overpass recursion drags in every node of every track way.
        {"type": "node", "id": 1, "lat": 25.0405, "lon": 121.5705,
         "tags": {"name": "Tower", "railway": "station", "station": "subway"}},
        {"type": "node", "id": 2, "lat": 25.0498, "lon": 121.5798,
         "tags": {"name": "Temple", "railway": "station", "station": "subway"}},
        {"type": "node", "id": 3, "lat": 25.0603, "lon": 121.5903,
         "tags": {"name": "Market", "railway": "station", "station": "subway"}},
        # Track geometry that must never become a boarding point.
        {"type": "node", "id": 4, "lat": 25.0450, "lon": 121.5750},
        {
            "type": "relation", "id": 90,
            "tags": {"route": "subway", "ref": "BR"},
            "members": [
                {"type": "node", "ref": 1}, {"type": "node", "ref": 2},
                {"type": "node", "ref": 3},
            ],
        },
    ]

    def graph(self):
        from travel_planner.transit import graph_from_osm

        return graph_from_osm(self.ELEMENTS)

    def test_a_relation_yields_both_directions(self) -> None:
        """A relation lists one direction; a metro runs both.

        Recording only the stated direction produced a graph where half the network
        was one-way, and journeys back towards the centre simply did not exist.
        """

        graph = self.graph()
        self.assertEqual(3, len(graph.stops))
        self.assertEqual(4, len(graph.edges))
        there = graph.journey(origin=(25.0405, 121.5705), destination=(25.0603, 121.5903))
        back = graph.journey(origin=(25.0603, 121.5903), destination=(25.0405, 121.5705))
        self.assertIsNotNone(there)
        self.assertIsNotNone(back)
        self.assertEqual(there.total_minutes, back.total_minutes)

    def test_it_reports_nominal_basis_where_gtfs_reports_timetable(self) -> None:
        """The whole point of carrying a basis: this data is weaker and says so."""

        from travel_planner.gtfs import TransitFeed

        osm = self.graph().journey(
            origin=(25.0405, 121.5705), destination=(25.0603, 121.5903)
        )
        self.assertEqual("nominal", osm.basis)
        feed = TransitFeed(
            Path(__file__).resolve().parent / "fixtures" / "synthetic_transit_gtfs.zip"
        )
        timetabled = feed.journey(
            origin=(25.040, 121.570), destination=(25.060, 121.590)
        )
        self.assertEqual("timetable", timetabled.basis)

    def test_a_metro_leg_walks_only_to_the_station(self) -> None:
        journey = self.graph().journey(
            origin=(25.0405, 121.5705), destination=(25.0603, 121.5903)
        )
        self.assertGreater(journey.total_minutes, journey.walking_minutes)
        self.assertLess(journey.walking_minutes, 5)

    def test_topology_without_a_usable_relation_refuses(self) -> None:
        """Stations alone are not a network, and inventing edges would be worse."""

        from travel_planner.providers import OsmMetroProvider, ProviderUnavailable
        from travel_planner.transit import graph_from_osm

        stations_only = graph_from_osm([e for e in self.ELEMENTS if e["type"] == "node"])
        self.assertEqual(3, len(stations_only.stops), "untagged track node must be dropped")
        self.assertEqual({}, stations_only.edges)
        provider = OsmMetroProvider(destination="Nowhere", graph=stations_only)
        with self.assertRaises(ProviderUnavailable):
            provider.route(
                {"place_id": "a", "latitude": 25.0405, "longitude": 121.5705},
                {"place_id": "b", "latitude": 25.0603, "longitude": 121.5903},
            )

    def test_the_provider_normalizes_like_any_other_route(self) -> None:
        from travel_planner.providers import OsmMetroProvider

        provider = OsmMetroProvider(destination="Taipei", graph=self.graph())
        route = provider.route(
            {"place_id": "tower", "latitude": 25.0405, "longitude": 121.5705},
            {"place_id": "market", "latitude": 25.0603, "longitude": 121.5903},
        )
        self.assertEqual("transit", route["mode"])
        self.assertEqual("estimated", route["status"])
        self.assertEqual("osm_metro", route["provider"])
        self.assertLess(route["walking_minutes"], route["duration_minutes"])
        self.assertGreaterEqual(route["boarding_buffer_minutes"], 1)

    def test_the_metro_query_pulls_relation_members(self) -> None:
        """`>;` is what makes the ordered member list resolvable.

        Without it the relations arrive referring to nodes that were never returned,
        and every line yields no edges at all.
        """

        from travel_planner.providers import OsmMetroProvider

        query = OsmMetroProvider(destination="Taipei").metro_query([25.0, 121.5, 25.1, 121.6])
        self.assertIn('relation["route"="subway"]', query)
        self.assertIn("(._;>;);", query)


class PlaceSummaryTest(unittest.TestCase):
    """Free descriptions and photos from Wikidata, in both languages."""

    class FakeWikidataPlaces(FakePlaceProvider):
        """The shared fake carries no `wikidata` signal, so nothing would be asked.

        Left as a subclass rather than changing the shared fake: a wikidata signal
        earns +0.5 in `_evidence_score`, so adding it there would move every ranking
        test's numbers for no reason.
        """

        def discover(self, destination: str) -> dict:
            payload = super().discover(destination)
            for index, item in enumerate(payload["items"], start=1):
                # `discovery.normalize` reads a nested `signals` map, not a
                # top-level key.
                item["signals"] = {"wikidata": f"Q{index}00", "wikipedia": f"en:Place {index}"}
            return payload

    class FakeSummaryProvider:
        name = "wikidata"
        operation = "wikidata:summary"
        kind = "place_summary"
        cache_ttl_days = 60

        def __init__(self) -> None:
            self.asked: list[str] = []

        def summary(self, qid: str) -> dict:
            self.asked.append(qid)
            if qid == "Q_MISSING":
                from travel_planner.providers import ProviderUnavailable

                raise ProviderUnavailable(f"Wikidata has no entity {qid}")
            return {
                "qid": qid,
                "text": {"en": f"A description of {qid}.", "th": f"คำบรรยายของ {qid}"},
                "image_url": f"https://commons.example/{qid}.jpg?width=640",
                "licence": "CC BY-SA, Wikipedia and Wikimedia Commons",
                "source_urls": {"en": f"https://en.wikipedia.org/wiki/{qid}"},
            }

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.provider = self.FakeSummaryProvider()
        self.actions = PlannerActions(
            Path(self.directory.name) / "summaries.sqlite3",
            place_provider=self.FakeWikidataPlaces(),
            summary_provider=self.provider,
        )
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="explore_first"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id, main_style=["sightseeing"],
            start_date="2030-01-01", end_date="2030-01-03",
            accommodation_status="booked", confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        self.candidates = self.actions.get_latest_discovery(
            self.trip.trip_id
        ).candidates.as_dict()["candidates"]
        for candidate in self.candidates:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=candidate["place_id"], action="must_do"
            )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_a_summary_is_stored_per_place_in_both_languages(self) -> None:
        report = self.actions.refresh_place_summaries(self.trip.trip_id)
        self.assertEqual(0, report["failed"], report.get("provider_errors"))
        self.assertGreater(report["fetched"], 0)

        stored = self.actions.list_place_summaries(self.trip.trip_id)
        self.assertEqual(report["fetched"], len(stored))
        for place_id, value in stored.items():
            # The id must live inside the value: list_place_evidence returns the
            # stored snapshot and does not add it back.
            self.assertEqual(place_id, value["place_id"])
            self.assertIn("en", value["text"])
            self.assertIn("th", value["text"])
            self.assertTrue(value["image_url"])
            self.assertIn("CC BY-SA", value["licence"])

    def test_it_reads_the_wikidata_id_from_the_selected_place(self) -> None:
        """`_selected_places` had to start carrying `signals`.

        Without it every place was skipped for want of a Wikidata id and the report
        said `fetched: 0` while reporting no failure — a silent no-op that reads as
        success.
        """

        self.actions.refresh_place_summaries(self.trip.trip_id)
        expected = {
            (c.get("signals") or {}).get("wikidata")
            for c in self.candidates
            if (c.get("signals") or {}).get("wikidata")
        }
        self.assertTrue(expected, "the fake discovery must supply a wikidata id")
        self.assertEqual(expected, set(self.provider.asked))

    def test_a_second_run_uses_the_cache_and_spends_nothing_new(self) -> None:
        first = self.actions.refresh_place_summaries(self.trip.trip_id)
        second = self.actions.refresh_place_summaries(self.trip.trip_id)
        self.assertEqual(first["fetched"], second["from_cache"])
        self.assertEqual(0, second["fetched"])

    def test_it_is_recorded_at_zero_rather_than_left_unpriced(self) -> None:
        self.actions.refresh_place_summaries(self.trip.trip_id)
        rows = [
            row
            for row in self.actions.store.list_paid_usage()
            if row["operation"] == "wikidata:summary"
        ]
        self.assertTrue(rows)
        self.assertEqual(0.0, sum(float(row["estimated_usd"]) for row in rows))

    def test_a_place_without_an_article_is_left_blank_not_invented(self) -> None:
        self.provider.summary = lambda qid: {  # type: ignore[method-assign]
            "qid": qid, "text": {}, "image_url": None,
            "licence": "CC BY-SA, Wikipedia and Wikimedia Commons", "source_urls": {},
        }
        self.actions.refresh_place_summaries(self.trip.trip_id, force=True)
        stored = self.actions.list_place_summaries(self.trip.trip_id)
        self.assertTrue(stored)
        for value in stored.values():
            self.assertEqual({}, value["text"])
            self.assertIsNone(value["image_url"])


class TimeZoneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "tz.sqlite3"
        self.provider = FakeTimeZoneProvider()
        self.actions = PlannerActions(
            self.path,
            place_provider=FakePlaceProvider(),
            timezone_provider=self.provider,
        )
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="ready_to_schedule"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date="2030-01-01",
            end_date="2030-01-03",
            accommodation_status="booked",
            confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_a_status_other_than_ok_is_never_a_fallback_zone(self) -> None:
        provider = GoogleTimeZoneProvider()
        for payload in (
            {"status": "ZERO_RESULTS"},
            {"status": "REQUEST_DENIED"},
            {},
            {"status": "OK", "timeZoneId": ""},
        ):
            with self.assertRaises(ProviderUnavailable):
                provider.normalize(payload, latitude=25.0, longitude=121.0)

    def test_the_zone_is_recorded_with_its_provenance(self) -> None:
        result = self.actions.refresh_timezone(self.trip.trip_id)

        self.assertEqual("Asia/Taipei", result["timezone"])
        self.assertEqual("google_timezone", result["provider"])
        self.assertEqual("verified", result["status"])
        self.assertEqual(28800, result["raw_offset_seconds"])
        self.assertFalse(result["from_cache"])
        # Queried at the centre of the discovered coverage box.
        latitude, longitude = self.provider.calls[0]
        self.assertAlmostEqual(25.05, latitude, places=2)
        self.assertAlmostEqual(121.55, longitude, places=2)

    def test_a_second_lookup_is_served_from_evidence_at_no_cost(self) -> None:
        self.actions.refresh_timezone(self.trip.trip_id)
        again = self.actions.refresh_timezone(self.trip.trip_id)

        self.assertTrue(again["from_cache"])
        self.assertEqual(1, len(self.provider.calls))
        bucket = self.actions.paid_usage_status()["by_operation"]["google_timezone:lookup"]
        # One paid request, one cached read recorded at zero.
        self.assertEqual(1, bucket["requests"])
        self.assertEqual(0.005, bucket["estimated_usd"])

    def test_the_zone_clears_its_capability_gap_and_reaches_the_optimizer(self) -> None:
        for place_id in [
            item["place_id"]
            for item in self.actions.get_latest_discovery(
                self.trip.trip_id
            ).candidates.as_dict()["candidates"]
        ]:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=place_id, action="must_do"
            )

        before = self.actions._optimizer_input(self.trip.trip_id)
        self.assertIn("DESTINATION_TIMEZONE_UNVERIFIED", before["trip"]["capability_gaps"])
        self.assertIsNone(before["trip"]["timezone"])

        self.actions.refresh_timezone(self.trip.trip_id)
        after = self.actions._optimizer_input(self.trip.trip_id)

        self.assertNotIn("DESTINATION_TIMEZONE_UNVERIFIED", after["trip"]["capability_gaps"])
        self.assertEqual("Asia/Taipei", after["trip"]["timezone"])

    def test_an_expired_zone_stops_counting_as_verified(self) -> None:
        self.actions.refresh_timezone(self.trip.trip_id)
        with self.actions.store.connect() as connection:
            connection.execute(
                "UPDATE trip_evidence SET expires_at = '2000-01-01T00:00:00+00:00'"
            )

        self.assertEqual("stale", self.actions.get_timezone_evidence(self.trip.trip_id)["status"])
        self.actions.save_candidate_choice(
            trip_id=self.trip.trip_id,
            place_id=self.actions.get_latest_discovery(self.trip.trip_id)
            .candidates.as_dict()["candidates"][0]["place_id"],
            action="must_do",
        )
        gaps = self.actions._optimizer_input(self.trip.trip_id)["trip"]["capability_gaps"]
        self.assertIn("DESTINATION_TIMEZONE_UNVERIFIED", gaps)

    def test_a_lookup_needs_a_discovered_destination(self) -> None:
        bare = PlannerActions(
            Path(self.directory.name) / "bare.sqlite3", timezone_provider=self.provider
        )
        trip = bare.create_trip(name="Bare", destination="Nowhere")
        with self.assertRaises(ValueError) as raised:
            bare.refresh_timezone(trip.trip_id)
        self.assertEqual("discovery_missing", str(raised.exception))

    def test_the_cap_stops_the_paid_lookup(self) -> None:
        self.actions.record_paid_call(operation="google_places:details", count=600)
        with self.assertRaises(ProviderBudgetExceeded):
            self.actions.refresh_timezone(self.trip.trip_id)
        self.assertEqual([], self.provider.calls)


