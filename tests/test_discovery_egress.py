"""The cheap read of a discovery run, which is most of a hosted deployment's egress.

`get_latest_discovery` is `SELECT *`, and on a real city `candidates_json` is around
390 KB while `report_json` is under two. Four callers wanted nothing from the run but
`query_boundary` -- four floats -- and three of them (`refresh_basemap`, the country
outline, `trip_forecast`) run on every itinerary page load, so a single view read roughly
1.5 MB out of the database to answer a question the report already held.

Supabase bills egress, and the free tier allows 5.5 GB: at 1.5 MB a view that is about
3,700 page loads, which a few 56-screen baseline capture runs reach on their own.

These tests pin the saving by measuring it, so restoring a `SELECT *` on this path fails
here rather than on a billing email a month later.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import unittest.mock

from travel_planner.actions import PlannerActions
from travel_planner.store import SQLiteStore

from tests.test_setup_discovery import FakePlaceProvider


class DiscoveryReportReadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "tourist.sqlite3"
        self.actions = PlannerActions(self.database_path, place_provider=FakePlaceProvider())
        self.trip = self.actions.create_trip(
            name="Taipei New Year",
            destination="Taipei",
            planning_mode="ready_to_schedule",
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            owner_age=26,
            main_style=["sightseeing"],
            start_date="2026-12-29",
            end_date="2027-01-04",
            accommodation_status="not_booked",
            confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        self.store = SQLiteStore(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_the_report_read_returns_the_searched_window(self) -> None:
        report = self.store.get_latest_discovery_report(self.trip.trip_id)
        self.assertIsNotNone(report)
        self.assertEqual(4, len(report["query_boundary"]))
        # The same window the full read reports, so the cheap path is not a different
        # answer -- it is the same answer without the freight.
        full = self.store.get_latest_discovery(self.trip.trip_id)
        self.assertEqual(
            full.report.as_dict()["query_boundary"], report["query_boundary"]
        )

    def test_a_trip_with_no_run_reads_as_none_rather_than_raising(self) -> None:
        other = self.actions.create_trip(
            name="Nothing yet", destination="Osaka", planning_mode="explore_first"
        )
        self.assertIsNone(self.store.get_latest_discovery_report(other.trip_id))

    def test_the_report_read_never_carries_the_candidates(self) -> None:
        """The measurement, not the intention.

        `discovery_runs` is immutable by trigger, so the blob cannot be inflated here to
        a real city's size. What is asserted instead is the thing that actually causes
        the egress: the cheap read carries no candidates at all, whatever they weigh.
        """

        cheap = self.store.get_latest_discovery_report(self.trip.trip_id)
        self.assertNotIn("candidates", cheap)
        # Under a page of JSON even before the boundary is picked out of it.
        self.assertLess(len(json.dumps(cheap).encode("utf-8")), 8_000)

        full = self.store.get_latest_discovery(self.trip.trip_id)
        self.assertGreater(
            len(full.candidates.canonical_json.encode("utf-8")),
            len(json.dumps(cheap).encode("utf-8")),
        )

    def test_the_cheap_read_selects_three_columns_and_not_a_star(self) -> None:
        """The guard against the change being undone.

        `SELECT *` here is the whole bug, and it is a one-word edit away at all times, so
        the statement itself is inspected. A trace callback sees exactly what SQLite was
        asked, which is the only place the distinction is visible.
        """

        statements: list[str] = []
        original = SQLiteStore.connect

        import contextlib

        @contextlib.contextmanager
        def traced(store_self):
            with original(store_self) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        with unittest.mock.patch.object(SQLiteStore, "connect", traced):
            self.store.get_latest_discovery_report(self.trip.trip_id)

        selects = [text for text in statements if "discovery_runs" in text]
        self.assertTrue(selects, "no statement touched discovery_runs")
        for text in selects:
            self.assertNotIn("*", text)
            self.assertNotIn("candidates_json", text)
            self.assertIn("report_json", text)

    def test_the_boundary_helper_reads_the_report_and_not_the_run(self) -> None:
        """`_discovery_boundary` is what the four callers now use, so it is pinned too."""

        reads: list[str] = []
        original = self.actions.store.get_latest_discovery

        def record(trip_id: str):
            reads.append(trip_id)
            return original(trip_id)

        self.actions.store.get_latest_discovery = record  # type: ignore[method-assign]
        boundary = self.actions._discovery_boundary(self.trip.trip_id)
        self.assertEqual(4, len(boundary))
        self.assertEqual([], reads, "the full run was read to find four floats")

    def test_journey_never_reads_the_candidate_catalogue(self) -> None:
        """Navigation needs stage state, not the multi-megabyte discovery payload."""

        full = self.store.get_latest_discovery(self.trip.trip_id)
        candidate = full.candidates.as_dict()["candidates"][0]
        self.actions.save_candidate_choice(
            trip_id=self.trip.trip_id,
            place_id=candidate["place_id"],
            action="interested",
        )
        statements: list[str] = []
        original = SQLiteStore.connect

        import contextlib

        @contextlib.contextmanager
        def traced(store_self):
            with original(store_self) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        with unittest.mock.patch.object(SQLiteStore, "connect", traced):
            self.actions.journey(self.trip.trip_id)

        selects = [text for text in statements if "discovery_runs" in text]
        self.assertTrue(selects, "journey did not check whether discovery exists")
        for text in selects:
            self.assertNotIn("SELECT *", text.upper())
            self.assertNotIn("candidates_json", text)

    def test_ranked_discovery_reads_the_candidate_catalogue_once(self) -> None:
        """The places page needs the run and its ranking, but not two blob reads."""

        statements: list[str] = []
        original = SQLiteStore.connect

        import contextlib

        @contextlib.contextmanager
        def traced(store_self):
            with original(store_self) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        with unittest.mock.patch.object(SQLiteStore, "connect", traced):
            result = self.actions.get_ranked_discovery(self.trip.trip_id)

        selects = [text for text in statements if "FROM discovery_runs" in text]
        self.assertEqual(1, len(selects), selects)
        self.assertEqual(
            len(result["discovery"].candidates.as_dict()["candidates"]),
            len(result["ranking"]["lanes"]["browse_all"]),
        )

    def test_optimizer_input_reads_the_candidate_catalogue_once(self) -> None:
        """Every plan calculation reuses the discovery it already loaded."""

        discovery = self.store.get_latest_discovery(self.trip.trip_id)
        candidate = discovery.candidates.as_dict()["candidates"][0]
        self.actions.save_candidate_choice(
            trip_id=self.trip.trip_id,
            place_id=candidate["place_id"],
            action="interested",
        )
        statements: list[str] = []
        original = SQLiteStore.connect

        import contextlib

        @contextlib.contextmanager
        def traced(store_self):
            with original(store_self) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        with unittest.mock.patch.object(SQLiteStore, "connect", traced):
            self.actions._optimizer_input(self.trip.trip_id)

        selects = [text for text in statements if "FROM discovery_runs" in text]
        self.assertEqual(1, len(selects), selects)

    def test_basemap_read_carries_the_server_expiry_for_browser_reuse(self) -> None:
        self.store.upsert_trip_evidence(
            trip_id=self.trip.trip_id,
            kind="basemap",
            value={"roads": [], "water": [], "green": []},
            provider="fake",
            retrieved_at="2026-08-22T00:00:00+00:00",
            expires_at="2026-09-21T00:00:00+00:00",
        )

        held = self.actions.get_basemap(self.trip.trip_id)
        self.assertEqual("2026-09-21T00:00:00+00:00", held["expires_at"])


class PaidUsageLedgerReadTest(unittest.TestCase):
    """Spend status is aggregate-only; diagnostic ledger reads stay bounded."""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "tourist.sqlite3"
        self.actions = PlannerActions(self.database_path, place_provider=FakePlaceProvider())
        self.trip = self.actions.create_trip(
            name="Taipei New Year", destination="Taipei", planning_mode="ready_to_schedule"
        )
        self.store = SQLiteStore(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _record(
        self,
        created_at: str,
        *,
        operation: str = "openstreetmap:basemap",
        requests: int = 1,
        estimated_usd: float = 0.0,
    ) -> None:
        """A ledger row at a chosen time.

        Inserted rather than written through `_spend` and backdated: the table is
        immutable by trigger, which is the right property and means a test wanting an old
        row has to make it old on the way in.
        """

        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO paid_usage
                (id, trip_id, operation, provider, request_count, estimated_usd,
                 outcome, detail_json, created_at)
                VALUES (?, ?, ?, 'test', ?, ?, 'success', '{}', ?)
                """,
                (
                    f"usage_{created_at}_{operation}",
                    self.trip.trip_id,
                    operation,
                    requests,
                    estimated_usd,
                    created_at,
                ),
            )

    def test_a_bounded_month_read_leaves_other_months_in_the_database(self) -> None:
        self._record("2026-06-04T09:00:00+00:00")
        self._record("2026-07-04T09:00:00+00:00")
        self._record("2026-08-04T09:00:00+00:00")

        self.assertEqual(3, len(self.store.list_paid_usage(limit=100)))
        august = self.store.list_paid_usage(month="2026-08", limit=100)
        self.assertEqual(1, len(august))
        self.assertTrue(august[0]["created_at"].startswith("2026-08"))

    def test_spend_summary_is_computed_in_sql_and_matches_the_ledger(self) -> None:
        self._record("2026-07-31T23:59:59+00:00", requests=99)
        self._record(
            "2026-08-01T00:00:00+00:00",
            operation="google_places:details",
            requests=2,
            estimated_usd=0.034,
        )
        self._record(
            "2026-08-02T00:00:00+00:00",
            operation="google_places:details",
            requests=3,
            estimated_usd=0.051,
        )
        self._record("2026-08-03T00:00:00+00:00", requests=4)
        statements: list[str] = []
        original = SQLiteStore.connect

        import contextlib

        @contextlib.contextmanager
        def traced(store_self):
            with original(store_self) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        with unittest.mock.patch.object(SQLiteStore, "connect", traced):
            summary = self.store.summarize_paid_usage(month="2026-08")

        self.assertEqual(9, summary["requests"])
        self.assertEqual(0.085, summary["estimated_usd"])
        self.assertEqual(3, summary["entries"])
        self.assertEqual(
            {"requests": 5, "estimated_usd": 0.085},
            summary["by_operation"]["google_places:details"],
        )
        selects = [text for text in statements if "paid_usage" in text]
        self.assertEqual(1, len(selects))
        self.assertIn("GROUP BY operation", selects[0])
        self.assertNotIn("SELECT *", selects[0].upper())

    def test_raw_ledger_reads_are_explicitly_bounded_and_do_not_select_details(self) -> None:
        for day in range(1, 4):
            self._record(f"2026-08-0{day}T00:00:00+00:00")
        statements: list[str] = []
        original = SQLiteStore.connect

        import contextlib

        @contextlib.contextmanager
        def traced(store_self):
            with original(store_self) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        with unittest.mock.patch.object(SQLiteStore, "connect", traced):
            rows = self.store.list_paid_usage(limit=2)

        self.assertEqual(2, len(rows))
        selects = [text for text in statements if "paid_usage" in text]
        self.assertEqual(1, len(selects))
        self.assertIn("LIMIT 2", selects[0])
        self.assertNotIn("SELECT *", selects[0].upper())
        self.assertNotIn("detail_json", selects[0])
        with self.assertRaises(ValueError):
            self.store.list_paid_usage(limit=1_001)


if __name__ == "__main__":
    unittest.main()
