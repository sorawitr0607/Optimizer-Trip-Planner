from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from travel_planner.actions import MAX_ROUTE_REQUESTS, PlannerActions
from travel_planner.providers import (
    GoogleTimeZoneProvider,
    OpenRouteServiceProvider,
    ProviderBudgetExceeded,
    ProviderUnavailable,
)

ROOT = Path(__file__).resolve().parents[1]


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


class EvidenceUiTest(unittest.TestCase):
    """The evidence view had no render test, so its layout was unverified."""

    def test_each_paid_enrichment_offers_its_own_card(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "evidence-ui.sqlite3"
            actions = PlannerActions(path, place_provider=FakePlaceProvider())
            trip = actions.create_trip(name="Taipei", destination="Taipei")
            actions.save_setup(
                trip_id=trip.trip_id,
                main_style=["sightseeing"],
                start_date="2030-01-01",
                end_date="2030-01-01",
                confirmed=True,
            )
            actions.discover_places(trip_id=trip.trip_id)
            # The stage is only reachable once a place has been chosen.
            catalog = actions.get_latest_discovery(trip.trip_id).candidates.as_dict()
            actions.save_candidate_choice(
                trip_id=trip.trip_id,
                place_id=catalog["candidates"][0]["place_id"],
                action="must_do",
            )
            place_id = catalog["candidates"][0]["place_id"]

            with patch.dict(os.environ, {"TOURIST_DB_PATH": str(path)}):
                app = AppTest.from_file(ROOT / "app.py", default_timeout=10)
                app.switch_page("views/evidence.py")
                app.run()

                self.assertFalse(app.exception)
                # One button per enrichment, each inside its own card.
                for key in (
                    f"fetch_tz_{trip.trip_id}",
                    f"fetch_hours_{trip.trip_id}",
                    f"fetch_routes_{trip.trip_id}",
                ):
                    self.assertIsNotNone(app.button(key=key))
                app.button(key=f"confirm_hours_{trip.trip_id}_{place_id}").click().run()
                self.assertEqual(
                    {"start": "08:00", "end": "18:00"},
                    PlannerActions(path).opening_intervals(trip.trip_id)[place_id][
                        "interval"
                    ],
                )
                # The cap control no longer reuses the expander's own label.
                self.assertEqual(
                    "New monthly cap (US$)",
                    app.number_input(key=f"cap_{trip.trip_id}").label,
                )
