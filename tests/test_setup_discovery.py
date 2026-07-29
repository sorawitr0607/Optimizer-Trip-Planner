from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from travel_planner.actions import PlannerActions
from travel_planner.providers import OpenStreetMapProvider, ProviderUnavailable
from travel_planner.store import SCHEMA_VERSION, SQLiteStore


ROOT = Path(__file__).resolve().parents[1]


class FakePlaceProvider:
    name = "fake_places"
    cache_ttl_days = 7

    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    def cache_descriptor(self, destination: str) -> dict:
        return {
            "provider": self.name,
            "operation": "baseline_place_discovery",
            "version": 1,
            "destination": destination.casefold(),
        }

    def discover(self, destination: str) -> dict:
        self.calls += 1
        if self.fail:
            raise ProviderUnavailable("temporary test outage")
        return {
            "items": [
                {
                    "provider_place_id": "node/1",
                    "name": "Sky View",
                    "names": {"en": "Sky View", "local": "天空景觀"},
                    "latitude": 25.0330,
                    "longitude": 121.5654,
                    "category": "viewpoint",
                    "source_url": "https://example.test/node/1",
                },
                {
                    "provider_place_id": "relation/2",
                    "name": "Sky View",
                    "names": {"en": "Sky View", "local": "天空景觀"},
                    "latitude": 25.0331,
                    "longitude": 121.5655,
                    "category": "viewpoint",
                    "source_url": "https://example.test/relation/2",
                },
                {
                    "provider_place_id": "way/3",
                    "name": "Culture Temple",
                    "names": {"en": "Culture Temple", "local": "文化寺"},
                    "latitude": 25.0370,
                    "longitude": 121.4999,
                    "category": "place_of_worship",
                    "opening_hours": "08:00-20:00",
                    "source_url": "https://example.test/way/3",
                },
                {
                    "provider_place_id": "node/4",
                    "name": "",
                    "latitude": 25.04,
                    "longitude": 121.51,
                    "category": "park",
                },
            ],
            "coverage": {
                "bbox": [24.9, 121.4, 25.2, 121.7],
                "searched_categories": ["city_icons", "culture_history_religion"],
                "known_gaps": ["Test provider is intentionally small."],
                "result_limit_reached": False,
            },
            "attribution": "Fake open provider",
            "license": "Test licence",
            "license_url": "https://example.test/licence",
        }


class SetupDiscoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "tourist.sqlite3"
        self.provider = FakePlaceProvider()
        self.actions = PlannerActions(self.database_path, place_provider=self.provider)
        self.trip = self.actions.create_trip(
            name="Taipei New Year",
            destination="Taipei",
            planning_mode="ready_to_schedule",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _confirmed_setup(self):
        return self.actions.save_setup(
            trip_id=self.trip.trip_id,
            owner_age=26,
            main_style=["sightseeing", "culture", "culture"],
            also_enjoy=["local_street_food"],
            avoid=["tourist_traps", "plain_long_walks"],
            comfort=["balanced_pace", "meal_on_time"],
            travellers=[
                {"label": "Teen", "age": 19},
                {"label": "Mother", "age": 50},
            ],
            start_date="2026-12-29",
            end_date="2027-01-04",
            arrival_time="17:00",
            departure_time="11:00",
            accommodation_status="not_booked",
            confirmed=True,
        )

    def test_setup_keeps_age_neutral_and_discovery_is_cached_and_deduplicated(self) -> None:
        setup = self._confirmed_setup()
        payload = setup.snapshot.as_dict()
        self.assertEqual(["sightseeing", "culture"], payload["owner"]["main_style"])
        self.assertEqual([19, 50], [item["age"] for item in payload["travellers"]])
        self.assertEqual([[], []], [item["tags"] for item in payload["travellers"]])

        first = self.actions.discover_places(trip_id=self.trip.trip_id)
        second = self.actions.discover_places(trip_id=self.trip.trip_id)

        self.assertEqual(1, self.provider.calls)
        self.assertEqual("verified", first.status)
        self.assertFalse(first.report.as_dict()["from_cache"])
        self.assertTrue(second.report.as_dict()["from_cache"])
        self.assertEqual(first.candidates, second.candidates)

        report = first.report.as_dict()
        candidates = first.candidates.as_dict()["candidates"]
        self.assertEqual(2, report["canonical_candidates"])
        self.assertEqual(1, report["duplicates_merged"])
        self.assertEqual({"missing_name": 1}, report["rejected_records"])
        self.assertFalse(report["personalization_applied"])
        sky_view = next(item for item in candidates if item["name"] == "Sky View")
        self.assertEqual(2, len(sky_view["provider_aliases"]))

        connection = sqlite3.connect(self.database_path)
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    "UPDATE discovery_runs SET status = 'error' WHERE id = ?",
                    (first.run_id,),
                )
        finally:
            connection.close()

    def test_provider_failure_keeps_setup_and_uses_stale_cache(self) -> None:
        setup = self._confirmed_setup()
        current = self.actions.discover_places(trip_id=self.trip.trip_id)
        self.provider.fail = True

        stale = self.actions.discover_places(trip_id=self.trip.trip_id, force_refresh=True)

        self.assertEqual("stale", stale.status)
        current_candidates = current.candidates.as_dict()["candidates"]
        stale_candidates = stale.candidates.as_dict()["candidates"]
        self.assertEqual(
            [item["place_id"] for item in current_candidates],
            [item["place_id"] for item in stale_candidates],
        )
        self.assertEqual(
            [item["provider_aliases"] for item in current_candidates],
            [item["provider_aliases"] for item in stale_candidates],
        )
        self.assertEqual(
            ["stale"] * len(stale_candidates),
            [item["evidence"][0]["status"] for item in stale_candidates],
        )
        self.assertIn("temporary test outage", stale.report.as_dict()["provider_error"])
        self.assertEqual(setup, self.actions.get_setup(self.trip.trip_id))

    def test_unavailable_provider_is_recorded_without_a_fake_catalog(self) -> None:
        self._confirmed_setup()
        self.provider.fail = True

        result = self.actions.discover_places(trip_id=self.trip.trip_id)

        self.assertEqual("unavailable", result.status)
        self.assertEqual([], result.candidates.as_dict()["candidates"])
        self.assertIn("temporary test outage", result.report.as_dict()["provider_error"])


class SchemaMigrationTest(unittest.TestCase):
    def test_version_one_database_gains_current_tables(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute("CREATE TABLE legacy_marker (value TEXT)")
                connection.execute("PRAGMA user_version = 1")
                connection.commit()
            finally:
                connection.close()

            SQLiteStore(path)

            connection = sqlite3.connect(path)
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                connection.close()
            self.assertEqual(SCHEMA_VERSION, version)
            self.assertTrue(
                {
                    "trip_setups",
                    "provider_cache",
                    "discovery_runs",
                    "candidate_choices",
                    "optimization_previews",
                    "checklist_items",
                    "cost_items",
                    "exchange_rate_snapshots",
                }
                <= tables
            )


class ConcreteProviderTest(unittest.TestCase):
    def test_osm_adapter_normalizes_local_names_without_network(self) -> None:
        provider = OpenStreetMapProvider()
        responses = iter(
            [
                [
                    {
                        "display_name": "Taipei, Taiwan",
                        "lat": "25.0375",
                        "lon": "121.5637",
                        "boundingbox": ["24.9", "25.2", "121.4", "121.7"],
                    }
                ],
                {
                    "elements": [
                        {
                            "type": "node",
                            "id": 123,
                            "lat": 25.033,
                            "lon": 121.565,
                            "tags": {
                                "name": "台北景點",
                                "name:en": "Taipei Place",
                                "tourism": "attraction",
                                "wikidata": "Q123",
                                "wikimedia_commons": "File:Taipei Place.jpg",
                            },
                        }
                    ]
                },
            ]
        )
        requests = []

        def fake_request_json(request):
            requests.append(request)
            return next(responses)

        provider._request_json = fake_request_json

        result = provider.discover("Taipei")

        self.assertEqual(2, len(requests))
        self.assertEqual("Taipei Place", result["items"][0]["name"])
        self.assertEqual("台北景點", result["items"][0]["names"]["local"])
        self.assertEqual("node/123", result["items"][0]["provider_place_id"])
        self.assertEqual("Q123", result["items"][0]["signals"]["wikidata"])
        self.assertEqual(
            "File:Taipei Place.jpg", result["items"][0]["photo_reference"]
        )
        self.assertLessEqual(
            result["coverage"]["bbox"][2] - result["coverage"]["bbox"][0], 0.60
        )

    def test_osm_adapter_rejects_an_empty_baseline(self) -> None:
        provider = OpenStreetMapProvider()
        responses = iter(
            [
                [
                    {
                        "display_name": "Taipei, Taiwan",
                        "lat": "25.0375",
                        "lon": "121.5637",
                        "boundingbox": ["24.9", "25.2", "121.4", "121.7"],
                    }
                ],
                {"elements": []},
            ]
        )
        provider._request_json = lambda request: next(responses)

        with self.assertRaisesRegex(ProviderUnavailable, "empty baseline"):
            provider.discover("Taipei")

    def test_osm_refresh_reuses_cached_boundary(self) -> None:
        provider = OpenStreetMapProvider()
        requests = []

        def fake_request_json(request):
            requests.append(request)
            return {
                "elements": [
                    {
                        "type": "node",
                        "id": 123,
                        "lat": 25.033,
                        "lon": 121.565,
                        "tags": {"name": "台北景點", "tourism": "attraction"},
                    }
                ]
            }

        provider._request_json = fake_request_json
        result = provider.refresh(
            "Taipei",
            {
                "coverage": {
                    "bbox": [24.9, 121.4, 25.2, 121.7],
                    "geocoded_name": "Taipei, Taiwan",
                }
            },
        )

        self.assertEqual(1, len(requests))
        self.assertEqual("Taipei, Taiwan", result["coverage"]["geocoded_name"])


class SetupUiTest(unittest.TestCase):
    def test_owner_and_two_members_confirm_and_survive_thai_switch(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "ui.sqlite3"
            with patch.dict(os.environ, {"TOURIST_DB_PATH": str(database_path)}):
                app = AppTest.from_file(ROOT / "app.py", default_timeout=10).run()
                app.text_input(key="trip_name").input("Taipei New Year")
                app.text_input(key="destination").input("Taipei")
                app.selectbox(key="planning_mode").select("ready_to_schedule")
                app.button[0].click().run()
                trip_id = app.selectbox(key="resume_trip").value

                app.number_input(key=f"member_count_{trip_id}").set_value(2).run()
                app.multiselect(key=f"main_style_{trip_id}").set_value(
                    ["sightseeing", "culture"]
                )
                app.number_input(key=f"owner_age_{trip_id}").set_value(26)
                app.number_input(key=f"member_age_{trip_id}_0").set_value(19)
                app.number_input(key=f"member_age_{trip_id}_1").set_value(50)
                next(
                    button for button in app.button if button.label == "Confirm setup"
                ).click().run()

                self.assertFalse(app.exception)
                setup = PlannerActions(database_path).get_setup(trip_id)
                self.assertTrue(setup.confirmed)
                self.assertEqual(
                    [19, 50],
                    [item["age"] for item in setup.snapshot.as_dict()["travellers"]],
                )

                app.radio[0].set_value("th").run()
                self.assertFalse(app.exception)
                self.assertEqual("ตัวช่วยวางแผนท่องเที่ยวส่วนตัว", app.title[0].value)
                self.assertIn("ตั้งค่าทริป", [item.value for item in app.subheader])


if __name__ == "__main__":
    unittest.main()
