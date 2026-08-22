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


class PaidUsageLedgerReadTest(unittest.TestCase):
    """The other unbounded read on a page load.

    `paid_usage_status` sums one calendar month, but read the entire ledger to do it and
    filtered in Python. The table only grows -- 7,084 rows and 1.6 MB on a trip that has
    been worked on for a while -- so the whole history crossed the wire every time the
    cap banner was rendered.
    """

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

    def _record(self, created_at: str) -> None:
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
                VALUES (?, ?, 'openstreetmap:basemap', 'openstreetmap', 1, 0.0,
                        'success', '{}', ?)
                """,
                (f"usage_{created_at}", self.trip.trip_id, created_at),
            )

    def test_a_month_scoped_read_leaves_other_months_in_the_database(self) -> None:
        self._record("2026-06-04T09:00:00+00:00")
        self._record("2026-07-04T09:00:00+00:00")
        self._record("2026-08-04T09:00:00+00:00")

        self.assertEqual(3, len(self.store.list_paid_usage()))
        august = self.store.list_paid_usage(month="2026-08")
        self.assertEqual(1, len(august))
        self.assertTrue(august[0]["created_at"].startswith("2026-08"))

    def test_the_scoped_read_agrees_with_filtering_in_python(self) -> None:
        """The change is only safe if it is the same filter, so both are compared."""

        for stamp in ("2026-06-30T23:59:59+00:00", "2026-07-01T00:00:00+00:00",
                      "2026-07-31T23:59:59+00:00", "2026-08-01T00:00:00+00:00"):
            self._record(stamp)

        for month in ("2026-06", "2026-07", "2026-08"):
            with self.subTest(month=month):
                in_sql = self.store.list_paid_usage(month=month)
                in_python = [
                    row for row in self.store.list_paid_usage()
                    if row["created_at"][:7] == month
                ]
                self.assertEqual(in_python, in_sql)


if __name__ == "__main__":
    unittest.main()
