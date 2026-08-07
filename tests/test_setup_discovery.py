from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from time import monotonic
import unittest
from unittest.mock import patch


from travel_planner import destinations
from travel_planner.actions import PlannerActions
from travel_planner.providers import OpenStreetMapProvider, ProviderUnavailable
from travel_planner.store import SCHEMA_VERSION, SQLiteStore


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
                    "paid_usage",
                    "paid_usage_cap",
                    "route_snapshots",
                    "trip_evidence",
                    "place_evidence",
                    "revision_drafts",
                    "plan_revisions",
                    "split_rows",
                    "split_settled_markers",
                }
                <= tables
            )

    @staticmethod
    def _legacy(directory: str, version: int) -> Path:
        path = Path(directory) / "tourist.sqlite3"
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE TABLE legacy_marker (value TEXT)")
            connection.execute("INSERT INTO legacy_marker VALUES ('the pilot trip')")
            connection.execute(f"PRAGMA user_version = {version}")
            connection.commit()
        finally:
            connection.close()
        return path

    @staticmethod
    def _version(path: Path) -> int:
        connection = sqlite3.connect(path)
        try:
            return connection.execute("PRAGMA user_version").fetchone()[0]
        finally:
            connection.close()

    def test_a_bump_copies_the_database_before_writing_anything(self) -> None:
        with TemporaryDirectory() as directory:
            path = self._legacy(directory, SCHEMA_VERSION - 1)

            SQLiteStore(path)

            copies = sorted(Path(directory).glob("tourist-pre-v*.sqlite3"))
            self.assertEqual(1, len(copies), copies)
            self.assertRegex(
                copies[0].name,
                rf"^tourist-pre-v{SCHEMA_VERSION}-\d{{4}}-\d{{2}}-\d{{2}}\.sqlite3$",
            )
            # The copy holds the pre-bump state, which is the only way back.
            self.assertEqual(SCHEMA_VERSION - 1, self._version(copies[0]))
            self.assertEqual(SCHEMA_VERSION, self._version(path))

    def test_a_failed_copy_refuses_the_migration_and_leaves_the_schema_alone(self) -> None:
        with TemporaryDirectory() as directory:
            path = self._legacy(directory, SCHEMA_VERSION - 1)

            with patch(
                "travel_planner.store.shutil.copy2",
                side_effect=OSError("No space left on device"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Refusing to migrate"):
                    SQLiteStore(path)

            self.assertEqual(SCHEMA_VERSION - 1, self._version(path))
            self.assertEqual([], sorted(Path(directory).glob("tourist-pre-v*.sqlite3")))
            connection = sqlite3.connect(path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                connection.close()
            self.assertNotIn("split_rows", tables)

    def test_a_new_database_and_a_current_one_are_never_copied(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "tourist.sqlite3"

            SQLiteStore(path)
            SQLiteStore(path)

            # Version 0 has nothing to preserve and an equal version is not a
            # bump. Without this gate every temp database in the suite would
            # leave a junk copy beside it.
            self.assertEqual([], sorted(Path(directory).glob("tourist-pre-v*.sqlite3")))


class ConcreteProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        """No slot to wait for when `_request_json` is a stub.

        The real pause exists so Overpass releases the first block's slot before the
        second asks for one; against a fake it is six tests times three seconds of
        nothing, on a suite that runs in nine.
        """

        patcher = patch.object(OpenStreetMapProvider, "BLOCK_PAUSE_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dense_city_query_protects_landmarks_and_balances_families(self) -> None:
        """Two blocks, issued as two requests so one can fail alone.

        As one script a dense city lost everything: Tokyo's unindexed family block
        exceeded `[timeout:90]` at 91s and 93s on 2026-08-07, and Overpass has no
        partial result, so the indexed landmarks died with it.
        """

        provider = OpenStreetMapProvider()
        bbox = [24.9, 121.4, 25.2, 121.7]
        landmarks = provider._landmark_query(bbox)
        baseline = provider._baseline_query(bbox)

        # The landmark block is the indexed, cheap, valuable half.
        self.assertIn('["wikipedia"]', landmarks)
        self.assertIn("out center qt;", landmarks)
        # The baseline block is unbounded by index and so is bounded by count.
        self.assertNotIn('["wikipedia"]', baseline)
        self.assertIn("out center qt 500", baseline)
        # One family list feeds both, so they cannot drift apart.
        for selector in OpenStreetMapProvider.FAMILY_SELECTORS:
            self.assertIn(selector, landmarks)
            self.assertIn(selector, baseline)

    def test_a_timed_out_baseline_keeps_the_landmarks_it_did_get(self) -> None:
        """The whole point of splitting: a dense city keeps its landmarks."""

        provider = OpenStreetMapProvider()
        responses = iter(
            [
                [
                    {
                        "display_name": "Tokyo, Japan",
                        "lat": "35.6762",
                        "lon": "139.6503",
                        "boundingbox": ["35.5", "35.8", "139.5", "139.8"],
                    }
                ],
                {
                    "elements": [
                        {
                            "type": "node",
                            "id": 1,
                            "lat": 35.68,
                            "lon": 139.65,
                            "tags": {"name": "Sensoji", "historic": "temple"},
                        }
                    ]
                },
                # Exactly what Overpass returned for Tokyo: a remark, not an HTTP error.
                {
                    "elements": [],
                    "remark": 'runtime error: Query timed out in "query" at line 14 after 91 seconds.',
                },
            ]
        )
        provider._request_json = lambda request: next(responses)

        result = provider.discover("Tokyo, Japan")

        self.assertEqual(["Sensoji"], [item["name"] for item in result["items"]])
        # Named, so the screen can say which half is missing rather than only that
        # something is.
        self.assertEqual(["baseline"], result["coverage"]["incomplete_blocks"])
        self.assertTrue(
            any("timed out" in gap for gap in result["coverage"]["known_gaps"])
        )

    def test_a_fast_gateway_failure_is_retried_once(self) -> None:
        """`overpass-api.de` balances across backends and an unhealthy one 504s in
        seconds. Measured 2026-08-08 on Singapore: both blocks 504 at 9.0s and 9.5s with
        both slots free, and the same query returned 200 a minute later — so the owner
        got an empty catalog for a fault that had already passed."""

        provider = OpenStreetMapProvider()
        provider.RETRY_PAUSE_SECONDS = 0
        calls: list[str] = []

        def fake_overpass(query: str) -> list[dict]:
            calls.append(query)
            if len(calls) == 1:
                raise ProviderUnavailable("Provider HTTP 504")
            return [
                {
                    "type": "node", "id": 7, "lat": 1.3, "lon": 103.8,
                    "tags": {"name": "Merlion", "tourism": "attraction"},
                }
            ]

        provider._overpass_elements = fake_overpass  # type: ignore[method-assign]
        elements = provider._attempt_block("<query>", monotonic() + 100)

        self.assertEqual(2, len(calls), "a fast 504 should be asked again")
        self.assertEqual(1, len(elements))

    def test_a_slow_failure_is_not_retried(self) -> None:
        """A block that died at 90s died of the timeout the query itself declares.
        Asking again spends another 90s to fail the same way, and two of those outlive
        the webapp's 120s abort — so the retry would cost the catalog it meant to save."""

        provider = OpenStreetMapProvider()
        calls: list[str] = []

        def slow_failure(query: str) -> list[dict]:
            calls.append(query)
            # Push the clock past the fast-failure window without actually waiting.
            provider.FAST_FAILURE_SECONDS = -1
            raise ProviderUnavailable("Provider HTTP 504")

        provider._overpass_elements = slow_failure  # type: ignore[method-assign]
        with self.assertRaises(ProviderUnavailable):
            provider._attempt_block("<query>", monotonic() + 100)

        self.assertEqual(1, len(calls))

    def test_a_timed_out_block_is_never_retried(self) -> None:
        """A `remark` is the query engine reporting its own timeout, not a gateway."""

        provider = OpenStreetMapProvider()
        provider.RETRY_PAUSE_SECONDS = 0
        calls: list[str] = []

        def timed_out(query: str) -> list[dict]:
            calls.append(query)
            raise ProviderUnavailable("OpenStreetMap query incomplete: runtime error")

        provider._overpass_elements = timed_out  # type: ignore[method-assign]
        with self.assertRaises(ProviderUnavailable):
            provider._attempt_block("<query>", monotonic() + 100)

        self.assertEqual(1, len(calls), "only an HTTP 5xx is worth asking again")

    def test_the_retry_is_skipped_when_the_budget_is_gone(self) -> None:
        """The shared deadline is what keeps the pair inside the 120s RPC abort however
        the retries fall."""

        provider = OpenStreetMapProvider()
        calls: list[str] = []

        def failing(query: str) -> list[dict]:
            calls.append(query)
            raise ProviderUnavailable("Provider HTTP 504")

        provider._overpass_elements = failing  # type: ignore[method-assign]
        with self.assertRaises(ProviderUnavailable):
            provider._attempt_block("<query>", monotonic())  # no budget left

        self.assertEqual(1, len(calls))

    def test_both_blocks_failing_is_still_a_provider_failure(self) -> None:
        """Degrading is not the same as pretending. Nothing back is still nothing."""

        provider = OpenStreetMapProvider()
        responses = iter(
            [
                [
                    {
                        "display_name": "Tokyo, Japan",
                        "lat": "35.6762",
                        "lon": "139.6503",
                        "boundingbox": ["35.5", "35.8", "139.5", "139.8"],
                    }
                ],
                {"elements": [], "remark": "runtime error: Query timed out"},
                {"elements": [], "remark": "runtime error: Query timed out"},
            ]
        )
        provider._request_json = lambda request: next(responses)

        with self.assertRaisesRegex(ProviderUnavailable, "timed out"):
            provider.discover("Tokyo, Japan")

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
                # The baseline block, now its own request. Empty is not a failure —
                # this place carries `wikipedia`-adjacent tags and came back in the
                # landmark block already.
                {"elements": []},
            ]
        )
        requests = []

        def fake_request_json(request):
            requests.append(request)
            return next(responses)

        provider._request_json = fake_request_json

        result = provider.discover("Taipei")

        # Nominatim, then the two Overpass blocks.
        self.assertEqual(3, len(requests))
        self.assertEqual([], result["coverage"]["incomplete_blocks"])
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
                {"elements": []},
            ]
        )
        provider._request_json = lambda request: next(responses)

        with self.assertRaisesRegex(ProviderUnavailable, "empty baseline"):
            provider.discover("Taipei")

    def test_osm_adapter_deduplicates_landmarks_returned_by_priority_blocks(self) -> None:
        provider = OpenStreetMapProvider()
        landmark = {
            "type": "way",
            "id": 101,
            "center": {"lat": 25.033, "lon": 121.565},
            "tags": {"name": "Taipei 101", "tourism": "attraction"},
        }
        provider._request_json = lambda request: {"elements": [landmark, landmark.copy()]}

        result = provider._discover_bbox(
            [24.9, 121.4, 25.2, 121.7], geocoded_name="Taipei"
        )

        self.assertEqual(1, len(result["items"]))
        self.assertEqual(1, result["coverage"]["raw_records"])

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

        # Two Overpass blocks and no Nominatim call: the cached boundary is the point.
        self.assertEqual(2, len(requests))
        self.assertEqual("Taipei, Taiwan", result["coverage"]["geocoded_name"])


class DestinationPickerTest(unittest.TestCase):
    def test_the_pair_becomes_one_geocoder_query(self) -> None:
        self.assertEqual(
            "Taipei, Taiwan", destinations.destination_text("Taiwan", "Taipei")
        )

    def test_a_city_state_is_not_repeated(self) -> None:
        # "Singapore, Singapore" is a worse Nominatim query than "Singapore".
        self.assertEqual(
            "Singapore", destinations.destination_text("Singapore", "Singapore")
        )
        self.assertEqual(
            "Hong Kong", destinations.destination_text("Hong Kong", "hong kong")
        )

    def test_either_part_alone_is_accepted_but_neither_is_not(self) -> None:
        self.assertEqual("Georgia", destinations.destination_text("Georgia", ""))
        self.assertEqual("Tbilisi", destinations.destination_text("", "Tbilisi"))
        with self.assertRaises(ValueError):
            destinations.destination_text("  ", "")

    def test_a_typed_country_simply_has_no_curated_cities(self) -> None:
        self.assertIn("Taipei", destinations.city_options("Taiwan"))
        self.assertEqual((), destinations.city_options("Georgia"))
        self.assertEqual((), destinations.city_options(""))

    def test_a_country_label_localizes_but_its_stored_value_does_not(self) -> None:
        self.assertEqual("Japan", destinations.country_label("Japan", "en"))
        self.assertEqual("ญี่ปุ่น", destinations.country_label("Japan", "th"))
        # A typed country has no translation and must survive unchanged.
        self.assertEqual("Georgia", destinations.country_label("Georgia", "th"))

    def test_every_country_offers_at_least_one_city(self) -> None:
        for country, entry in destinations.COUNTRIES.items():
            with self.subTest(country=country):
                self.assertTrue(entry["cities"], f"{country} has no cities")
                self.assertTrue(entry["th"], f"{country} has no Thai label")


if __name__ == "__main__":
    unittest.main()
