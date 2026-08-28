from __future__ import annotations

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from travel_planner import usage
from travel_planner.actions import PlannerActions
from travel_planner.providers import ProviderBudgetExceeded

ROOT = Path(__file__).resolve().parents[1]


def entry(operation: str, count: int, created_at: str, **kwargs) -> dict:
    return usage.new_entry(
        operation=operation, count=count, created_at=created_at, **kwargs
    )


class PricingTest(unittest.TestCase):
    def test_an_unpriced_operation_is_refused_rather_than_assumed_free(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unpriced paid operation"):
            usage.price_for("mystery_provider:guess")
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            usage.price_for("google_places:details", -1)

    def test_free_tier_operations_are_recorded_at_zero(self) -> None:
        row = entry("openrouteservice:directions", 12, "2026-07-29T10:00:00+00:00")
        self.assertEqual(0.0, row["estimated_usd"])
        self.assertEqual(12, row["request_count"])
        self.assertEqual("openrouteservice", row["provider"])

    def test_a_cached_read_costs_nothing_but_is_still_recorded(self) -> None:
        row = entry(
            "google_places:details", 5, "2026-07-29T10:00:00+00:00", outcome="cached"
        )
        self.assertEqual(0, row["request_count"])
        self.assertEqual(0.0, row["estimated_usd"])
        self.assertEqual("cached", row["outcome"])

    def test_unsupported_outcome_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported usage outcome"):
            entry("google_places:details", 1, "2026-07-29T10:00:00+00:00", outcome="maybe")


class ThresholdTest(unittest.TestCase):
    def test_warning_at_eight_and_stop_at_ten(self) -> None:
        self.assertEqual(usage.OK, usage.status(7.99)["state"])
        self.assertEqual(usage.WARNING, usage.status(8.0)["state"])
        self.assertEqual(usage.WARNING, usage.status(9.99)["state"])
        self.assertEqual(usage.STOPPED, usage.status(10.0)["state"])
        self.assertEqual(usage.STOPPED, usage.status(12.0)["state"])
        self.assertEqual(2.0, usage.status(8.0)["remaining_usd"])
        self.assertEqual(0.0, usage.status(12.0)["remaining_usd"])

    def test_a_call_that_would_cross_the_cap_is_refused(self) -> None:
        # 0.017 each: 588 calls fit under 10, the 589th would cross it.
        allowed = usage.check_allowed(
            operation="google_places:details", count=1, spent_usd=9.98
        )
        self.assertTrue(allowed["allowed"])
        refused = usage.check_allowed(
            operation="google_places:details", count=2, spent_usd=9.98
        )
        self.assertFalse(refused["allowed"])
        self.assertIn("above the US$10.00 cap", refused["reason"])

    def test_a_free_call_is_allowed_even_when_stopped(self) -> None:
        decision = usage.check_allowed(
            operation="openrouteservice:directions", count=40, spent_usd=25.0
        )
        self.assertTrue(decision["allowed"])
        self.assertEqual(0.0, decision["estimate_usd"])
        self.assertEqual(usage.STOPPED, decision["state"])

    def test_an_owner_raised_cap_reopens_paid_calls(self) -> None:
        stopped = usage.check_allowed(
            operation="google_places:details", count=1, spent_usd=10.5
        )
        raised = usage.check_allowed(
            operation="google_places:details", count=1, spent_usd=10.5, cap_usd=20.0
        )
        self.assertFalse(stopped["allowed"])
        self.assertTrue(raised["allowed"])
        self.assertEqual(20.0, raised["cap_usd"])

    def test_totals_are_scoped_to_one_calendar_month(self) -> None:
        entries = [
            entry("google_places:details", 100, "2026-06-30T23:00:00+00:00"),
            entry("google_places:details", 10, "2026-07-01T00:00:00+00:00"),
            entry("google_routes:compute", 20, "2026-07-15T00:00:00+00:00"),
        ]
        july = usage.totals(entries, month="2026-07")

        self.assertEqual(30, july["requests"])
        self.assertEqual(round(10 * 0.017 + 20 * 0.005, 6), july["estimated_usd"])
        self.assertEqual({"google_places:details", "google_routes:compute"}, set(july["by_operation"]))
        self.assertEqual(1.7, usage.totals(entries, month="2026-06")["estimated_usd"])


class LedgerPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "usage.sqlite3"
        self.actions = PlannerActions(self.path)
        self.trip = self.actions.create_trip(name="Taipei", destination="Taipei")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_spend_accumulates_and_reconciles_calls(self) -> None:
        for _ in range(3):
            self.actions.record_paid_call(
                operation="google_places:details", count=2, trip_id=self.trip.trip_id
            )
        status = self.actions.paid_usage_status()

        self.assertEqual(6, status["requests"])
        self.assertEqual(round(6 * 0.017, 6), status["estimated_usd"])
        self.assertEqual(usage.OK, status["state"])
        self.assertEqual(10.0, status["cap_usd"])
        self.assertFalse(status["cap_is_owner_raised"])
        self.assertEqual(6, status["by_operation"]["google_places:details"]["requests"])

    def test_the_cap_stops_a_paid_call_and_the_owner_can_raise_it(self) -> None:
        # Spend up to the cap, then attempt one more paid call.
        self.actions.record_paid_call(
            operation="google_places:details", count=589, trip_id=self.trip.trip_id
        )
        self.assertEqual(usage.STOPPED, self.actions.paid_usage_status()["state"])

        with self.assertRaisesRegex(ProviderBudgetExceeded, "cap"):
            self.actions._spend(
                operation="google_places:details",
                count=1,
                trip_id=self.trip.trip_id,
                detail={},
            )

        self.actions.set_paid_cap(20.0)
        raised = self.actions.paid_usage_status()
        # The warning line stays at US$8 as decided; only the stop moves.
        self.assertEqual(usage.WARNING, raised["state"])
        self.assertEqual(20.0, raised["cap_usd"])
        self.assertTrue(raised["cap_is_owner_raised"])
        # Now it goes through and is recorded.
        self.actions._spend(
            operation="google_places:details", count=1, trip_id=self.trip.trip_id, detail={}
        )
        self.assertEqual(590, self.actions.paid_usage_status()["requests"])

    def test_a_free_call_still_works_while_stopped(self) -> None:
        self.actions.record_paid_call(operation="google_places:details", count=600)
        self.assertEqual(usage.STOPPED, self.actions.paid_usage_status()["state"])

        self.actions._spend(
            operation="openrouteservice:directions",
            count=5,
            trip_id=self.trip.trip_id,
            detail={"pairs": 5},
        )
        status = self.actions.paid_usage_status()
        self.assertEqual(5, status["by_operation"]["openrouteservice:directions"]["requests"])

    def test_a_free_call_does_not_read_the_spend_ledger(self) -> None:
        with patch.object(
            self.actions,
            "paid_usage_status",
            side_effect=AssertionError("free calls must not read monthly spend"),
        ):
            self.actions._spend(
                operation="openrouteservice:directions",
                count=1,
                trip_id=self.trip.trip_id,
                detail={},
            )
        rows = self.actions.store.list_paid_usage(limit=10)
        self.assertEqual(1, len(rows))
        self.assertEqual("openrouteservice:directions", rows[0]["operation"])

    def test_a_negative_cap_is_refused(self) -> None:
        with self.assertRaises(ValueError) as raised:
            self.actions.set_paid_cap(-1)
        self.assertEqual("invalid_paid_cap", str(raised.exception))

    def test_ledger_rows_are_immutable(self) -> None:
        self.actions.record_paid_call(operation="google_places:details", count=1)
        connection = sqlite3.connect(self.path)
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute("UPDATE paid_usage SET estimated_usd = 0")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute("DELETE FROM paid_usage")
        finally:
            connection.close()

    def test_no_key_material_reaches_the_ledger(self) -> None:
        with self.assertRaisesRegex(ValueError, "not allowed"):
            self.actions.record_paid_call(
                operation="google_places:details",
                count=1,
                detail={"GOOGLE_MAPS_SERVER_KEY": "must-not-persist"},
            )


if __name__ == "__main__":
    unittest.main()
