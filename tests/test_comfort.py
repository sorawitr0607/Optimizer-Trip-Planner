from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from travel_planner.actions import PlannerActions, PlannerRefusal
from travel_planner.optimizer import COMFORT_RULES, optimize_trip, validate_variant
from tests.test_routes import FakePlaceProvider

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads(
    (ROOT / "tests" / "fixtures" / "historic_regressions.json").read_text(encoding="utf-8")
)


def fixture(fixture_id: str) -> dict:
    return next(
        item for item in CATALOG["fixtures"] if item["metadata"]["id"] == fixture_id
    )


class AcceptanceIsBoundedByItsValueTest(unittest.TestCase):
    """`WF-039`. The escape hatch existed and could never be reached.

    `validate_variant` keyed on reconciliation items that were `fits_with_tradeoff` **and
    not** `owner_acceptance_required`, while `_reconciliation` set that flag to exactly
    `status == "fits_with_tradeoff"`. Mutually exclusive. And no call site ever produced
    that status in the first place, so the route was dead twice over.
    """

    def setUp(self) -> None:
        self.snapshot = fixture("jp-shibuya-plain-walk-overload")["planner_input"]

    def measure(self, snapshot: dict) -> tuple[dict, float]:
        variant = optimize_trip(snapshot)["variants"][0]
        return variant, float(
            variant["metrics"].get("maximum_plain_walking_minutes_per_day", 0)
        )

    def test_without_an_acceptance_the_overage_is_still_fatal(self) -> None:
        snapshot = json.loads(json.dumps(self.snapshot))
        snapshot["thresholds"] = {"plain_walking_minutes_per_day": 1}
        variant = optimize_trip(snapshot)["variants"][0]
        variant["metrics"]["maximum_plain_walking_minutes_per_day"] = 27

        validation = validate_variant(snapshot, variant)

        self.assertIn(
            "UNAPPROVED_PLAIN_WALK_THRESHOLD",
            {item["code"] for item in validation["hard_violations"]},
        )

    def test_an_acceptance_covering_the_measurement_clears_it(self) -> None:
        snapshot = json.loads(json.dumps(self.snapshot))
        snapshot["thresholds"] = {"plain_walking_minutes_per_day": 25}
        snapshot["comfort_acceptances"] = [
            {"code": "PLAIN_WALK_THRESHOLD", "accepted_value": 27.0}
        ]
        variant = optimize_trip(snapshot)["variants"][0]
        variant["metrics"]["maximum_plain_walking_minutes_per_day"] = 27

        validation = validate_variant(snapshot, variant)

        self.assertNotIn(
            "UNAPPROVED_PLAIN_WALK_THRESHOLD",
            {item["code"] for item in validation["hard_violations"]},
        )

    def test_agreeing_to_27_minutes_does_not_bless_90(self) -> None:
        """The exact thing the ticket said any fix had to get right."""

        snapshot = json.loads(json.dumps(self.snapshot))
        snapshot["thresholds"] = {"plain_walking_minutes_per_day": 25}
        snapshot["comfort_acceptances"] = [
            {"code": "PLAIN_WALK_THRESHOLD", "accepted_value": 27.0}
        ]
        variant = optimize_trip(snapshot)["variants"][0]
        variant["metrics"]["maximum_plain_walking_minutes_per_day"] = 90

        validation = validate_variant(snapshot, variant)

        self.assertIn(
            "UNAPPROVED_PLAIN_WALK_THRESHOLD",
            {item["code"] for item in validation["hard_violations"]},
        )

    def test_an_improvement_on_what_was_agreed_is_still_covered(self) -> None:
        """Or an owner would be asked again every time the plan got better."""

        snapshot = json.loads(json.dumps(self.snapshot))
        snapshot["thresholds"] = {"plain_walking_minutes_per_day": 25}
        snapshot["comfort_acceptances"] = [
            {"code": "PLAIN_WALK_THRESHOLD", "accepted_value": 40.0}
        ]
        variant = optimize_trip(snapshot)["variants"][0]
        variant["metrics"]["maximum_plain_walking_minutes_per_day"] = 30

        self.assertTrue(validate_variant(snapshot, variant)["valid"])

    def test_an_acceptance_of_one_budget_does_not_cover_another(self) -> None:
        snapshot = json.loads(json.dumps(self.snapshot))
        snapshot["thresholds"] = {
            "plain_walking_minutes_per_day": 25,
            "walking_minutes_per_leg": 20,
        }
        snapshot["comfort_acceptances"] = [
            {"code": "PLAIN_WALK_THRESHOLD", "accepted_value": 99.0}
        ]
        variant = optimize_trip(snapshot)["variants"][0]
        variant["metrics"]["maximum_plain_walking_minutes_per_day"] = 27
        variant["metrics"]["maximum_walking_minutes_per_leg"] = 45

        codes = {
            item["code"] for item in validate_variant(snapshot, variant)["hard_violations"]
        }

        self.assertNotIn("UNAPPROVED_PLAIN_WALK_THRESHOLD", codes)
        self.assertIn("UNAPPROVED_WALKING_LEG_THRESHOLD", codes)

    def test_acceptance_buys_a_place_back_and_not_only_a_passing_validator(self) -> None:
        """Suppressing only the hard error would half-fix it.

        `comfort_violations` sits **above** `experience_value` in the objective tuple, so
        the search will drop a place rather than exceed a budget — the plan stays valid
        and the owner silently loses a stop. Clearing the hard error alone would leave
        that intact, because the search never proposes the fuller plan in the first
        place. Consent has to reach `_comfort_violation_count` too.

        This fixture is the real historic case: three places against a 40-minute daily
        walking budget.
        """

        blocked = optimize_trip(self.snapshot)["variants"][0]

        agreed = json.loads(json.dumps(self.snapshot))
        agreed["comfort_acceptances"] = [
            {"code": "PLAIN_WALK_THRESHOLD", "accepted_value": 999.0}
        ]
        allowed = optimize_trip(agreed)["variants"][0]

        self.assertEqual(2, blocked["metrics"]["scheduled_visits"])
        self.assertEqual(35, blocked["metrics"]["maximum_plain_walking_minutes_per_day"])
        # The third place, at the walking cost the owner agreed to.
        self.assertEqual(3, allowed["metrics"]["scheduled_visits"])
        self.assertEqual(70, allowed["metrics"]["maximum_plain_walking_minutes_per_day"])
        self.assertTrue(allowed["validation"]["valid"])

    def test_every_comfort_rule_names_a_metric_the_optimizer_reports(self) -> None:
        """The rules table is the single source; a typo in it would silently never fire."""

        variant = optimize_trip(fixture("ix-jp-shibuya-hours-view-walk")["planner_input"])[
            "variants"
        ][0]

        for rule in COMFORT_RULES:
            with self.subTest(rule=rule["reason"]):
                self.assertIn(rule["metric"], variant["metrics"])
                self.assertIn(rule["fallback_metric"], variant["metrics"])


class AcceptanceActionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.actions = PlannerActions(
            Path(self.directory.name) / "comfort.sqlite3",
            place_provider=FakePlaceProvider(),
        )
        self.trip = self.actions.create_trip(name="Taipei", destination="Taipei")
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date="2030-01-01",
            end_date="2030-01-02",
            accommodation_status="not_booked",
            comfort=["balanced_pace"],
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

    def test_the_setup_tags_really_do_produce_the_cap_being_accepted(self) -> None:
        thresholds = self.actions._optimizer_input(self.trip.trip_id)["thresholds"]

        self.assertEqual(25, thresholds["walking_minutes_per_leg"])
        self.assertEqual(60, thresholds["plain_walking_minutes_per_day"])

    def test_an_acceptance_reaches_the_optimizer_snapshot(self) -> None:
        self.actions.accept_comfort_tradeoff(
            self.trip.trip_id, "PLAIN_WALK_THRESHOLD", 72
        )

        snapshot = self.actions._optimizer_input(self.trip.trip_id)

        self.assertEqual(
            [{"code": "PLAIN_WALK_THRESHOLD", "accepted_value": 72.0,
              "threshold_value": 60.0,
              "updated_at": snapshot["comfort_acceptances"][0]["updated_at"]}],
            snapshot["comfort_acceptances"],
        )

    def test_withdrawing_removes_it(self) -> None:
        self.actions.accept_comfort_tradeoff(
            self.trip.trip_id, "PLAIN_WALK_THRESHOLD", 72
        )
        self.actions.withdraw_comfort_tradeoff(self.trip.trip_id, "PLAIN_WALK_THRESHOLD")

        self.assertEqual([], self.actions.list_comfort_acceptances(self.trip.trip_id))

    def test_accepting_within_the_limit_refuses(self) -> None:
        """Otherwise a permission is left lying around for a later, worse plan."""

        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.accept_comfort_tradeoff(
                self.trip.trip_id, "PLAIN_WALK_THRESHOLD", 30
            )

        self.assertEqual("comfort_value_within_threshold", caught.exception.code)

    def test_an_unknown_code_refuses(self) -> None:
        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.accept_comfort_tradeoff(self.trip.trip_id, "MADE_UP", 99)

        self.assertEqual("unknown_comfort_code", caught.exception.code)

    def test_a_budget_with_no_cap_cannot_be_accepted(self) -> None:
        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.accept_comfort_tradeoff(
                self.trip.trip_id, "HEAT_AND_CYCLING_LOAD", 99
            )

        self.assertEqual("no_comfort_threshold_set", caught.exception.code)

    def test_the_report_marks_an_agreement_stale_once_the_plan_gets_worse(self) -> None:
        self.actions.accept_comfort_tradeoff(
            self.trip.trip_id, "PLAIN_WALK_THRESHOLD", 72
        )
        worse = {
            "variant": {
                "metrics": {
                    "maximum_plain_walking_minutes_per_day": 95,
                    "maximum_walking_minutes_per_leg": 10,
                    "cycling_minutes": 0,
                }
            }
        }

        with patch.object(self.actions, "get_active_plan") as active:
            active.return_value = type("V", (), {"snapshot": type("S", (), {"as_dict": lambda self: worse})()})()
            report = self.actions.comfort_tradeoffs(self.trip.trip_id)

        rule = next(r for r in report["rules"] if r["code"] == "PLAIN_WALK_THRESHOLD")
        self.assertEqual(95, rule["measured"])
        self.assertEqual(72, rule["accepted_value"])
        self.assertTrue(rule["exceeds"])
        self.assertFalse(rule["covered"])

    def test_a_new_preview_wins_over_an_older_active_plan(self) -> None:
        active_payload = {"variant": {"metrics": {"maximum_plain_walking_minutes_per_day": 50}}}
        preview_payload = {
            "variants": [{"metrics": {"maximum_plain_walking_minutes_per_day": 95}}]
        }
        snapshot = lambda value: type("S", (), {"as_dict": lambda self: value})()
        active = type("V", (), {"snapshot": snapshot(active_payload)})()
        preview = type("P", (), {"proposal": snapshot(preview_payload)})()

        with (
            patch.object(self.actions, "get_active_plan", return_value=active),
            patch.object(self.actions, "get_plan_preview", return_value=preview),
        ):
            report = self.actions.comfort_tradeoffs(self.trip.trip_id)

        rule = next(r for r in report["rules"] if r["code"] == "PLAIN_WALK_THRESHOLD")
        self.assertEqual(95, rule["measured"])


if __name__ == "__main__":
    unittest.main()
