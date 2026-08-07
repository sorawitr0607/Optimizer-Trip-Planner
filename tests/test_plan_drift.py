from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from travel_planner.actions import PlannerActions, PlannerRefusal
from tests.test_opening import FakeHoursProvider, period
from tests.test_routes import FakePlaceProvider, FakeRouteProvider


class ActivePlanDriftTest(unittest.TestCase):
    """`WF-045`. Every gate guarded the forward direction; nothing looked back.

    The real failure: one paid opening-hours lookup left a visit scheduled 17:17-19:32
    against hours ending 17:30, while the stored variant still reported
    `validation.valid: true` — computed when the plan was built, and never recomputed.
    """

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.hours = FakeHoursProvider(
            # Narrow, and far tighter than the 09:00-21:00 assumption a plan is built on
            # when no hours are known. Buying these has to contradict that plan.
            periods=[period(day, (9, 0), (10, 0)) for day in range(7)]
        )
        self.actions = PlannerActions(
            Path(self.directory.name) / "drift.sqlite3",
            place_provider=FakePlaceProvider(),
            route_provider=FakeRouteProvider(),
            hours_provider=self.hours,
        )
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="explore_first"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date="2030-01-01",
            end_date="2030-01-02",
            accommodation_status="booked",
            confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        for item in self.actions.get_latest_discovery(
            self.trip.trip_id
        ).candidates.as_dict()["candidates"]:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=item["place_id"], action="must_do"
            )
        # Without routes the optimizer schedules nothing at all, and a plan with no
        # visits cannot demonstrate anything about drift.
        self.actions.refresh_routes(self.trip.trip_id)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def activate(self) -> None:
        proposal = self.actions.generate_plan_preview(self.trip.trip_id).proposal.as_dict()
        best = next(
            v
            for v in proposal["variants"]
            if v["validation"]["valid"] and v["metrics"]["scheduled_visits"]
        )
        self.actions.activate_plan_preview(
            trip_id=self.trip.trip_id, variant_id=best["variant_id"]
        )

    def test_an_untouched_plan_reports_no_drift(self) -> None:
        self.activate()

        drift = self.actions.active_plan_drift(self.trip.trip_id)

        self.assertFalse(drift["moved"])
        self.assertTrue(drift["still_valid"])
        self.assertEqual([], drift["violations"])
        self.assertEqual(drift["stored_input_sha256"], drift["current_input_sha256"])

    def test_buying_evidence_that_contradicts_the_plan_is_reported(self) -> None:
        """The regression. Before this, the plan simply went on saying it was valid."""

        self.activate()
        before = self.actions.active_plan_drift(self.trip.trip_id)
        self.assertFalse(before["moved"])

        self.actions.refresh_opening_hours(self.trip.trip_id)

        after = self.actions.active_plan_drift(self.trip.trip_id)
        self.assertTrue(after["moved"])
        # The stored flag still says valid; that is the point, and both are reported so
        # they can be seen to disagree.
        self.assertTrue(after["claimed_valid"])
        self.assertFalse(after["still_valid"])
        self.assertTrue(after["violations"])
        self.assertIn(
            "CLOSED_DURING_VISIT", {item["code"] for item in after["violations"]}
        )

    def test_the_stored_plan_itself_is_never_rewritten(self) -> None:
        """It reports and never repairs: an activated version is immutable, and the owner
        may have printed it."""

        self.activate()
        before = self.actions.get_active_plan(self.trip.trip_id).snapshot.as_dict()

        self.actions.refresh_opening_hours(self.trip.trip_id)
        self.actions.active_plan_drift(self.trip.trip_id)

        after = self.actions.get_active_plan(self.trip.trip_id).snapshot.as_dict()
        self.assertEqual(before, after)

    def test_regenerating_clears_the_drift(self) -> None:
        self.activate()
        self.actions.refresh_opening_hours(self.trip.trip_id)
        self.assertTrue(self.actions.active_plan_drift(self.trip.trip_id)["moved"])

        self.activate()

        drift = self.actions.active_plan_drift(self.trip.trip_id)
        self.assertFalse(drift["moved"])
        self.assertTrue(drift["still_valid"])

    def test_no_active_plan_refuses_rather_than_reporting_calm(self) -> None:
        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.active_plan_drift(self.trip.trip_id)

        self.assertEqual("no_active_plan", caught.exception.code)

    def test_validation_only_runs_when_the_hash_moved(self) -> None:
        """Cheap by design: the hash answers "did anything change" with no optimizer work,
        and only a change pays for `validate_variant`. That is what keeps this off the
        churn path the ticket warned about."""

        self.activate()
        calls = []
        import travel_planner.actions as module

        real = module.validate_variant
        module.validate_variant = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
        try:
            self.actions.active_plan_drift(self.trip.trip_id)
            self.assertEqual([], calls, "unchanged plan must not re-validate")
            self.actions.refresh_opening_hours(self.trip.trip_id)
            self.actions.active_plan_drift(self.trip.trip_id)
            self.assertEqual(1, len(calls), "a moved hash must re-validate exactly once")
        finally:
            module.validate_variant = real


if __name__ == "__main__":
    unittest.main()
