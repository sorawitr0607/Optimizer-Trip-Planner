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
from travel_planner.optimizer import optimize_trip, validate_variant

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
