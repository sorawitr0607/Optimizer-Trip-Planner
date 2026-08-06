from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


from scripts.run_optimizer_regressions import run_catalog
from travel_planner.actions import PlannerActions
from travel_planner.core import new_optimization_preview
from travel_planner.optimizer import (
    DEPARTURE_LOGISTICS_MINUTES,
    optimize_trip,
    validate_variant,
)
from tests.test_routes import FakePlaceProvider

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads(
    (ROOT / "tests" / "fixtures" / "historic_regressions.json").read_text(
        encoding="utf-8"
    )
)


def fixture(fixture_id: str) -> dict:
    return next(
        item for item in CATALOG["fixtures"] if item["metadata"]["id"] == fixture_id
    )


class OptimizerCoreTest(unittest.TestCase):
    def test_three_variants_are_deterministic_valid_and_not_worse_than_greedy(self) -> None:
        snapshot = fixture("ix-jp-shibuya-hours-view-walk")["planner_input"]

        first = optimize_trip(snapshot)
        second = optimize_trip(snapshot)

        self.assertEqual(first, second)
        self.assertEqual(
            ["best_balance", "relaxed", "more_highlights"],
            [item["variant_id"] for item in first["variants"]],
        )
        for variant in first["variants"]:
            self.assertEqual("ready", variant["status"])
            self.assertTrue(variant["validation"]["valid"])
            self.assertTrue(variant["objective_improved_or_equal_to_greedy"])
            visits = [
                item
                for day in variant["days"]
                for item in day["items"]
                if item["type"] == "visit"
            ]
            self.assertEqual(
                ["harajuku", "magnet_shibuya", "shibuya_sky"],
                [item["subject_id"] for item in visits],
            )
            self.assertGreaterEqual(int(visits[1]["start"][:2]), 10)
            self.assertGreaterEqual(int(visits[2]["start"][:2]), 16)

    def test_safe_route_and_weather_fallback_are_selected(self) -> None:
        odaiba = optimize_trip(
            fixture("jp-teamlab-odaiba-long-walk")["planner_input"]
        )["variants"][0]
        rain = optimize_trip(
            fixture("ix-jp-rain-fallback-reoptimization")["planner_input"]
        )["variants"][0]

        self.assertEqual(["transit"], odaiba["metrics"]["selected_modes"])
        self.assertLessEqual(odaiba["metrics"]["maximum_walking_minutes_per_leg"], 20)
        self.assertEqual("activated", rain["fallbacks"][0]["status"])
        self.assertTrue(rain["fallbacks"][0]["day_reoptimized"])
        self.assertNotIn(
            "outdoor_walk",
            {
                item["subject_id"]
                for day in rain["days"]
                for item in day["items"]
                if item["type"] == "visit"
            },
        )

    def test_lock_is_preserved_and_forced_limit_never_exposes_an_invalid_plan(self) -> None:
        snapshot = json.loads(
            json.dumps(fixture("ix-jp-shibuya-hours-view-walk")["planner_input"])
        )
        snapshot["locks"] = [
            {
                "subject_id": "shibuya_sky",
                "date": "2030-01-02",
                "start": "16:30",
            }
        ]

        variant = optimize_trip(snapshot)["variants"][0]
        sky = next(
            item
            for day in variant["days"]
            for item in day["items"]
            if item.get("subject_id") == "shibuya_sky"
        )
        self.assertEqual("16:30", sky["start"])
        self.assertTrue(variant["validation"]["valid"])

        limited = optimize_trip(snapshot, time_limit_seconds=1e-12)
        self.assertTrue(limited["stopped_at_limit"])
        for item in limited["variants"]:
            self.assertTrue(item["stopped_at_limit"])
            self.assertTrue(item["validation"]["valid"] or item["status"] == "unavailable")
            self.assertFalse(item["status"] == "ready" and not item["validation"]["valid"])

    def test_a_daily_walking_budget_is_measured_per_day_not_per_trip(self) -> None:
        """`plain_walking_minutes_per_day` is a daily budget, so judge a day.

        `_schedule_metrics` sums across every day, and that whole-trip total used
        to be compared against the per-day budget, making an n-day trip n times too
        strict. It was invisible here because 25 of the 27 historic fixtures are
        single-day and 2 are two-day. Measured on the real 8-day Taipei trip: 147
        minutes of plain walking across the trip, about 18 a day, failed a 60-a-day
        budget.
        """

        from travel_planner.optimizer import (
            _comfort_violation_count,
            _schedule_metrics,
        )

        def leg(minutes: int) -> dict:
            return {
                "type": "travel", "duration_minutes": minutes,
                "walking_minutes": minutes, "mode": "walk",
                "origin_id": "a", "destination_id": "b",
            }

        # Four days, 30 minutes of plain walking each: 120 across the trip, which
        # is over a 45-a-day budget only if the trip total is mistaken for a day.
        days = [{"date": f"2030-01-0{n}", "items": [leg(30)]} for n in range(1, 5)]
        snapshot = {"thresholds": {"plain_walking_minutes_per_day": 45}, "travellers": []}
        metrics = _schedule_metrics(snapshot, days)

        self.assertEqual(120, metrics["plain_walking_minutes"])
        self.assertEqual(30, metrics["maximum_plain_walking_minutes_per_day"])

        metrics["maximum_walking_minutes_per_leg"] = 30
        self.assertEqual(0, _comfort_violation_count(snapshot, metrics))

        # A single day that genuinely exceeds the budget must still be caught.
        days[2]["items"].append(leg(40))
        heavy = _schedule_metrics(snapshot, days)
        heavy["maximum_walking_minutes_per_leg"] = 30
        self.assertEqual(70, heavy["maximum_plain_walking_minutes_per_day"])
        self.assertEqual(1, _comfort_violation_count(snapshot, heavy))

    def test_independent_validator_rejects_a_corrupted_timeline(self) -> None:
        snapshot = fixture("ix-jp-shibuya-hours-view-walk")["planner_input"]
        variant = optimize_trip(snapshot)["variants"][0]
        variant["days"][0]["items"][1]["start"] = "08:00"

        validation = validate_variant(snapshot, variant)

        self.assertFalse(validation["valid"])
        self.assertIn(
            "TIMELINE_OVERLAP_OR_NEGATIVE_SLACK",
            {item["code"] for item in validation["hard_violations"]},
        )

    def test_a_departure_day_too_short_for_its_flight_does_not_empty_the_trip(self) -> None:
        """An early flight consumes the last day; it must not veto every other day.

        `WF-042`. The departure suffix is 180 fixed minutes (pack and check out,
        transfer, airport), so a flight before roughly 11:00 leaves the last day with
        no room at all. `_build_day` reported that as a hard error even when nothing
        was scheduled there, and `_greedy_baseline` only accepts a placement when the
        **whole trip** builds clean -- so one unusable day emptied the entire plan.
        """

        snapshot = fixture("dali-hotel-backtracking-pattern")["planner_input"]
        snapshot["trip"]["include_operational_timeline"] = True
        snapshot["trip"]["local_dates"] = ["2030-03-02", "2030-03-03"]
        # A 10:40 flight home: leaving at 07:40 is required, so 09:00 is already late.
        snapshot["trip"]["usable_windows"][-1]["end"] = "10:40"

        variant = optimize_trip(snapshot)["variants"][0]
        by_date = {day["date"]: day["items"] for day in variant["days"]}

        self.assertGreater(variant["metrics"]["scheduled_visits"], 0)
        self.assertNotIn(
            "NO_SELECTED_PLACE_COULD_BE_SCHEDULED", variant["metrics"]["warnings"]
        )
        # The last day carries the departure logistics and no visits, rather than
        # rendering as a blank day with the flight left implicit.
        self.assertEqual(
            [], [item for item in by_date["2030-03-03"] if item["type"] == "visit"]
        )
        self.assertEqual(
            ["pack_and_check_out", "departure_transfer", "airport_departure"],
            [
                item["kind"]
                for item in by_date["2030-03-03"]
                if item["type"] == "logistics"
            ],
        )

    def test_all_historic_fixtures_pass_the_real_optimizer(self) -> None:
        self.assertEqual([], run_catalog())


class OptimizerActionsTest(unittest.TestCase):
    def test_ready_preview_activates_as_an_immutable_plan_version(self) -> None:
        snapshot = fixture("ix-jp-shibuya-hours-view-walk")["planner_input"]
        proposal = optimize_trip(snapshot)
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "ready.sqlite3")
            trip = actions.create_trip(name="Ready", destination="Test City")
            actions.store.save_optimization_preview(
                new_optimization_preview(
                    trip_id=trip.trip_id,
                    optimizer_input=snapshot,
                    proposal=proposal,
                )
            )

            with patch.object(actions, "_optimizer_input", return_value=snapshot):
                version = actions.activate_plan_preview(
                    trip_id=trip.trip_id, variant_id="best_balance"
                )

            self.assertEqual(version, actions.get_active_plan(trip.trip_id))
            self.assertEqual(snapshot, version.snapshot.as_dict()["optimizer_input"])
            self.assertEqual("ready", version.snapshot.as_dict()["variant"]["status"])
            self.assertIsNone(actions.get_plan_preview(trip.trip_id))

    def test_the_departure_day_window_opens_early_enough_for_the_flight(self) -> None:
        """`WF-042`. The root fix: the window, not the builder's clock.

        Moving only the builder forward fought the independent validator, which
        judges every item against the snapshot's own `usable_windows` — so the day
        laid out correctly and was then rejected as `OUTSIDE_USABLE_WINDOW`. The
        window is what every consumer reads, so the window is what has to be right.
        """

        with TemporaryDirectory() as directory:
            actions = PlannerActions(
                Path(directory) / "flight.sqlite3", place_provider=FakePlaceProvider()
            )
            trip = actions.create_trip(name="Taipei", destination="Taipei")
            actions.save_setup(
                trip_id=trip.trip_id,
                main_style=["sightseeing"],
                start_date="2030-01-01",
                end_date="2030-01-03",
                arrival_time="17:40",
                departure_time="10:40",
                accommodation_status="booked",
                confirmed=True,
            )
            actions.discover_places(trip_id=trip.trip_id)
            first = actions.get_latest_discovery(trip.trip_id).candidates.as_dict()[
                "candidates"
            ][0]["place_id"]
            actions.save_candidate_choice(
                trip_id=trip.trip_id, place_id=first, action="must_do"
            )

            windows = actions._optimizer_input(trip.trip_id)["trip"]["usable_windows"]

        # 10:40 minus pack-and-check-out, transfer and airport time.
        self.assertEqual(DEPARTURE_LOGISTICS_MINUTES, 180)
        self.assertEqual({"date": "2030-01-03", "start": "07:40", "end": "10:40"}, windows[-1])
        # The arrival day still tightens from its own flight, and the middle day is
        # untouched — only the departure day borrows time.
        self.assertEqual("17:40", windows[0]["start"])
        self.assertEqual({"date": "2030-01-02", "start": "08:00", "end": "22:00"}, windows[1])

    def test_missing_dates_returns_stay_length_choices(self) -> None:
        snapshot = fixture("jp-shibuya-sky-morning-view")["planner_input"]
        snapshot = json.loads(json.dumps(snapshot))
        snapshot["trip"]["local_dates"] = []
        snapshot["trip"]["usable_windows"] = []

        result = optimize_trip(snapshot)

        self.assertEqual("stay_recommendation", result["mode"])
        self.assertEqual(["minimum", "balanced", "relaxed"], [item["id"] for item in result["stay_recommendations"]])


if __name__ == "__main__":
    unittest.main()
