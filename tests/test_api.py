from __future__ import annotations

from http.client import HTTPConnection
from io import BytesIO
import inspect
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
import zipfile

from api import ACTIONS, REFUSAL_STATUS, PlannerHTTPServer, dispatch, jsonable
from travel_planner.actions import PlannerActions
from travel_planner.core import (
    CandidateChoice,
    ChecklistItem,
    DiscoveryRun,
    OptimizationPreview,
    PlanVersion,
    ProviderCacheEntry,
    SetupDraft,
    Trip,
    freeze_snapshot,
)


class JsonableContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = freeze_snapshot({"answer": 42})

    def test_frozen_snapshot_shape(self) -> None:
        self.assertEqual(
            {"data": {"answer": 42}, "sha256": self.snapshot.sha256},
            jsonable(self.snapshot),
        )

    def test_trip_shape(self) -> None:
        value = Trip("t", "Taipei", "Taipei", "explore_first", "en", "now")
        self.assertEqual(
            {"trip_id", "name", "destination", "planning_mode", "language", "created_at"},
            set(jsonable(value)),
        )

    def test_plan_version_shape(self) -> None:
        value = PlanVersion("v", "t", None, "test", self.snapshot, "now")
        self.assertEqual(
            {"version_id", "trip_id", "parent_version_id", "cause", "snapshot", "created_at"},
            set(jsonable(value)),
        )

    def test_setup_draft_shape(self) -> None:
        value = SetupDraft("t", self.snapshot, True, "now")
        self.assertEqual(
            {"trip_id", "snapshot", "confirmed", "updated_at"}, set(jsonable(value))
        )

    def test_provider_cache_shape(self) -> None:
        value = ProviderCacheEntry("p", "f", self.snapshot, "now", "later")
        self.assertEqual(
            {"provider", "request_fingerprint", "snapshot", "retrieved_at", "expires_at"},
            set(jsonable(value)),
        )

    def test_discovery_run_shape(self) -> None:
        value = DiscoveryRun("r", "t", "s", "p", "verified", self.snapshot, self.snapshot, "now")
        self.assertEqual(
            {
                "run_id", "trip_id", "setup_sha256", "provider", "status",
                "candidates", "report", "created_at",
            },
            set(jsonable(value)),
        )

    def test_candidate_choice_shape(self) -> None:
        value = CandidateChoice("t", "p", "r", "maybe", None, self.snapshot, "now")
        self.assertEqual(
            {"trip_id", "place_id", "discovery_run_id", "action", "reason", "candidate", "updated_at"},
            set(jsonable(value)),
        )

    def test_checklist_item_shape(self) -> None:
        value = ChecklistItem("i", "t", None, "owner", self.snapshot, False, "now", "now")
        self.assertEqual(
            {
                "item_id", "trip_id", "generated_key", "origin", "snapshot",
                "dismissed", "created_at", "updated_at",
            },
            set(jsonable(value)),
        )

    def test_optimization_preview_shape(self) -> None:
        value = OptimizationPreview("t", self.snapshot, self.snapshot, "now")
        self.assertEqual(
            {"trip_id", "optimizer_input", "proposal", "created_at"}, set(jsonable(value))
        )


class DispatchContractTest(unittest.TestCase):
    def test_allowlist_is_literal_and_excludes_internal_writes(self) -> None:
        self.assertIsInstance(ACTIONS, tuple)
        # 71: WF-038 added refresh_transit_routes, the free Wikidata place summaries
        # added refresh_place_summaries and list_place_summaries, WF-040 added
        # recommend_areas, WF-039 added the four comfort-acceptance methods, WF-046
        # added refresh_assumed_windows and list_assumed_windows, WF-045 added
        # active_plan_drift, and WF-044 added scan_venue_notices and
        # list_venue_notices, and WF-047 added opening_evidence_options. The
        # count is asserted so a
        # method cannot join the allowlist unnoticed -- save_plan_version writes an
        # activated version with no optimizer validation and record_paid_call forges
        # ledger rows, so what is reachable over the socket has to be deliberate.
        self.assertEqual(82, len(ACTIONS))  # +month guide, +basemap pair, +map detail, +country outline pair, +forecast, WF-048
        self.assertIn("refresh_assumed_windows", ACTIONS)
        self.assertIn("active_plan_drift", ACTIONS)
        self.assertIn("scan_venue_notices", ACTIONS)
        self.assertIn("opening_evidence_options", ACTIONS)
        self.assertIn("refresh_transit_routes", ACTIONS)
        self.assertIn("refresh_place_summaries", ACTIONS)
        self.assertIn("recommend_areas", ACTIONS)
        self.assertIn("accept_comfort_tradeoff", ACTIONS)
        self.assertIn("withdraw_comfort_tradeoff", ACTIONS)
        self.assertEqual(len(ACTIONS), len(set(ACTIONS)))
        self.assertNotIn("save_plan_version", ACTIONS)
        self.assertNotIn("record_paid_call", ACTIONS)
        self.assertIn("check_paid_call", ACTIONS)
        self.assertIn("build_export_snapshot", ACTIONS)
        self.assertEqual(35, len(REFUSAL_STATUS))

    def test_the_split_ledger_is_reachable_but_deletion_is_not(self) -> None:
        for name in (
            "save_split_row",
            "list_split_rows",
            "set_split_voided",
            "split_summary",
            "set_split_settled",
        ):
            self.assertIn(name, ACTIONS)
        # Removing a row voids it, so no delete exists to expose.
        self.assertFalse(hasattr(PlannerActions, "delete_split_row"))

    def test_no_action_accepts_a_snapshot_hash(self) -> None:
        for name in ACTIONS:
            parameters = inspect.signature(getattr(PlannerActions, name)).parameters
            self.assertFalse(
                any("sha256" in parameter for parameter in parameters),
                f"{name} accepts a client-supplied hash",
            )

    def test_dispatch_round_trips_a_real_action(self) -> None:
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "planner.sqlite3")
            self.assertEqual([], dispatch(actions, "list_trips", {}))


class SplitWireShapeTest(unittest.TestCase):
    """The wire shape is implicit, so these tests are what catch a rename."""

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.actions = PlannerActions(Path(self.directory.name) / "planner.sqlite3")
        trip = dispatch(
            self.actions, "create_trip", {"name": "Taipei", "destination": "Taipei, Taiwan"}
        )
        self.trip_id = trip["trip_id"]

    def save(self, **row) -> dict:
        return dispatch(
            self.actions,
            "save_split_row",
            {"trip_id": self.trip_id, "row": {"label": "Hotel", "original_amount": 900, **row}},
        )

    def test_a_saved_row_carries_its_id_and_no_resolved_shares(self) -> None:
        saved = self.save()

        self.assertIn("split_id", saved)
        self.assertEqual("owner", saved["paid_by"])
        self.assertEqual(["owner"], saved["participants"])
        self.assertFalse(saved["voided"])
        # Shares are recomputed on read, never stored, so one rounding rule
        # cannot be bypassed by a row that carries its own numbers.
        self.assertNotIn("shares", saved)
        self.assertNotIn("shares_thb", saved)

    def test_the_summary_shape_is_stable(self) -> None:
        self.save()
        summary = dispatch(self.actions, "split_summary", {"trip_id": self.trip_id})

        self.assertEqual(
            {
                "base_currency", "cardholder", "actual_thb", "by_category", "rows",
                "voided_rows", "balances", "settlement", "unconvertible_rows",
                "missing_rates", "unconvertible",
            },
            set(summary),
        )
        self.assertEqual("owner", summary["cardholder"])
        self.assertEqual(
            {"traveller_id", "shares_thb", "paid_out_thb", "net_thb"},
            set(summary["balances"][0]),
        )

    def test_cost_totals_gains_the_two_figures_without_losing_any(self) -> None:
        totals = dispatch(self.actions, "cost_totals", {"trip_id": self.trip_id})

        for key in ("planned_thb", "actual_thb", "by_category_comparison",
                    "claimed_cost_ids", "unclaimed_paid_rows", "planned_per_person_thb"):
            self.assertIn(key, totals)
        for key in ("estimated_thb", "paid_thb", "total_thb", "by_category"):
            self.assertIn(key, totals)

    def test_voiding_an_unknown_row_refuses_with_a_stable_code(self) -> None:
        with self.assertRaises(Exception) as caught:
            dispatch(
                self.actions,
                "set_split_voided",
                {"trip_id": self.trip_id, "split_id": "split_nope"},
            )
        self.assertEqual("unknown_split_row", caught.exception.code)
        self.assertEqual(404, REFUSAL_STATUS["unknown_split_row"])

    def test_a_marker_is_stored_against_the_balance_it_settled(self) -> None:
        self.save()
        marked = dispatch(
            self.actions,
            "set_split_settled",
            {"trip_id": self.trip_id, "traveller_id": "owner"},
        )
        # The owner is the cardholder, so they never appear in settlement.
        self.assertEqual([], marked["settlement"])
        with self.assertRaises(Exception) as caught:
            dispatch(
                self.actions,
                "set_split_settled",
                {"trip_id": self.trip_id, "traveller_id": "mum"},
            )
        self.assertEqual("unknown_traveller", caught.exception.code)


class SocketGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        root = Path(self.directory.name)
        web = root / "dist"
        web.mkdir()
        (web / "index.html").write_text("<main>S1 shell</main>", encoding="utf-8")
        self.actions = PlannerActions(root / "planner.sqlite3")
        self.server = PlannerHTTPServer(("127.0.0.1", 0), self.actions, web)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        result = response.status, {key.lower(): value for key, value in response.getheaders()}, payload
        connection.close()
        return result

    def test_content_type_guard(self) -> None:
        status, _, body = self.request(
            "POST", "/api/list_trips", body=b"{}", headers={"Content-Type": "text/plain"}
        )
        self.assertEqual(415, status)
        self.assertEqual("unsupported_media_type", json.loads(body)["code"])

    def test_host_guard(self) -> None:
        status, _, body = self.request(
            "POST",
            "/api/list_trips",
            body=b"{}",
            headers={"Content-Type": "application/json", "Host": "attacker.example"},
        )
        self.assertEqual(421, status)
        self.assertEqual("bad_host", json.loads(body)["code"])

    def test_bare_get_reaches_downloads_and_nothing_else(self) -> None:
        trip = self.actions.create_trip(name="Keep", destination="Taipei")
        status, _, _ = self.request("GET", "/api/delete_trip")
        self.assertEqual(404, status)
        self.assertIsNotNone(self.actions.get_trip(trip.trip_id))
        with patch("api._download", return_value=(b"file", "application/octet-stream", "trip.bin")):
            status, headers, body = self.request("GET", "/api/export/t/workbook.xlsx")
        self.assertEqual(200, status)
        self.assertEqual(b"file", body)
        self.assertEqual('attachment; filename="trip.bin"', headers["content-disposition"])

    def test_a_missing_asset_is_a_404_and_not_the_whole_application(self) -> None:
        """The SPA fallback is for routes, and a route has no file extension.

        `/favicon.ico` used to answer 200 with `index.html` as its body. A browser
        discards that as an icon, so the tab kept the blank default and nothing in
        any log said why — the audit read it as an unfinished app. The distinction
        has to hold in both directions, so a real route still gets the shell.
        """

        for path in ("/favicon.ico", "/assets/index-deadbeef.js", "/robots.txt"):
            status, _, _ = self.request("GET", path)
            self.assertEqual(404, status, path)
        status, _, body = self.request("GET", "/trips/example/setup")
        self.assertEqual(200, status)
        self.assertIn(b"S1 shell", body)

    def test_shell_and_real_api_call_round_trip(self) -> None:
        status, _, body = self.request("GET", "/trips/example/setup")
        self.assertEqual(200, status)
        self.assertIn(b"S1 shell", body)

        payload = json.dumps({"name": "Taipei", "destination": "Taipei"}).encode()
        status, _, body = self.request(
            "POST",
            "/api/create_trip",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(200, status)
        trip = json.loads(body)
        status, _, body = self.request(
            "POST",
            "/api/journey",
            body=json.dumps({"trip_id": trip["trip_id"]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(200, status)
        self.assertEqual("setup", json.loads(body)["next"])

    def test_s4_taipei_journey_reaches_activation_and_both_downloads(self) -> None:
        """The S4 transport path, with route evidence prepared deterministically."""

        from tests.test_routes import FakePlaceProvider, FakeRouteProvider

        self.actions.place_provider = FakePlaceProvider()
        self.actions.route_provider = FakeRouteProvider()

        def post_api(method: str, payload: dict) -> object:
            status, _, body = self.request(
                "POST",
                f"/api/{method}",
                body=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(200, status, (method, body.decode()))
            return json.loads(body)

        trip = post_api(
            "create_trip",
            {
                "name": "Taipei New Year",
                "destination": "Taipei, Taiwan",
                "planning_mode": "explore_first",
            },
        )
        trip_id = trip["trip_id"]
        post_api(
            "save_setup",
            {
                "trip_id": trip_id,
                "owner_age": 34,
                "main_style": ["sightseeing", "culture"],
                "also_enjoy": ["local_street_food", "photography"],
                "travellers": [{"label": "Mum", "age": 63, "tags": ["culture"]}],
                "start_date": "2030-01-01",
                "end_date": "2030-01-03",
                "arrival_time": "09:00",
                "departure_time": "21:00",
                "accommodation_status": "not_booked",
                "confirmed": True,
            },
        )
        discovery = post_api("discover_places", {"trip_id": trip_id})
        ranking = post_api("rank_candidates", {"trip_id": trip_id})
        self.assertEqual(
            len(discovery["candidates"]["data"]["candidates"]),
            len(ranking["lanes"]["browse_all"]),
        )
        for place_id in ranking["lanes"]["browse_all"]:
            post_api(
                "save_candidate_choice",
                {"trip_id": trip_id, "place_id": place_id, "action": "must_do"},
            )
        post_api("refresh_routes", {"trip_id": trip_id})
        preview = post_api("generate_plan_preview", {"trip_id": trip_id})
        variant = preview["proposal"]["data"]["variants"][0]
        self.assertEqual("provisional", variant["status"])
        self.assertTrue(variant["validation"]["valid"])
        post_api(
            "activate_plan_preview",
            {"trip_id": trip_id, "variant_id": variant["variant_id"]},
        )
        post_api("apply_checklist_proposal", {"trip_id": trip_id})
        snapshot = post_api("build_export_snapshot", {"trip_id": trip_id, "language": "th"})
        self.assertEqual(
            {"buffer", "logistics", "meal", "preparation", "travel", "visit"},
            {item["type"] for day in snapshot["data"]["days"] for item in day["items"]},
        )

        status, _, workbook = self.request("GET", f"/api/export/{trip_id}/workbook.xlsx")
        self.assertEqual(200, status)
        self.assertTrue(zipfile.is_zipfile(BytesIO(workbook)))
        status, _, calendar = self.request("GET", f"/api/export/{trip_id}/checklist.ics")
        self.assertEqual(200, status)
        self.assertTrue(calendar.startswith(b"BEGIN:VCALENDAR"))


if __name__ == "__main__":
    unittest.main()
