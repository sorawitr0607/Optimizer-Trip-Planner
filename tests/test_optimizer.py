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
from travel_planner import optimizer as optimizer_module
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
    def test_first_leg_starts_at_the_accommodation_not_an_unselected_place(self) -> None:
        snapshot = {
            "candidates": [
                {"id": "base", "kind": "hotel_area"},
                {"id": "visit", "kind": "museum"},
            ],
            "routes": [
                {
                    "origin_id": "unselected-neighbour",
                    "destination_id": "visit",
                    "duration_minutes": 5,
                    "status": "verified",
                },
                {
                    "origin_id": "base",
                    "destination_id": "visit",
                    "duration_minutes": 20,
                    "status": "verified",
                },
            ],
            "trip": {},
        }

        route = optimizer_module._best_inbound_route(snapshot, "visit")

        self.assertEqual("base", route["origin_id"])

    def test_free_time_is_not_counted_as_contingency_buffer(self) -> None:
        days = [
            {
                "items": [
                    {"type": "buffer", "duration_minutes": 180, "reason": "free_time_or_rest"},
                    {"type": "buffer", "duration_minutes": 10, "reason": "transfer_contingency"},
                ]
            }
        ]

        metrics = optimizer_module._schedule_metrics(
            {"trip": {}, "facts": [], "thresholds": {}}, days
        )

        self.assertEqual(10, metrics["buffer_minutes"])

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

    def _route_evidence_snapshot(self, *, provisional: bool) -> dict:
        """Shibuya, but every route is `estimated` and every place demands evidence.

        That is the real shape of a transit leg: `WF-038` states a route derived from a
        timetable or from OSM topology is `estimated` by construction, never `verified`.
        """

        snapshot = json.loads(
            json.dumps(fixture("ix-jp-shibuya-hours-view-walk")["planner_input"])
        )
        snapshot["trip"]["requires_route_evidence"] = True
        snapshot["trip"]["allow_provisional_assumptions"] = provisional
        for candidate in snapshot["candidates"]:
            candidate["requires_route_evidence"] = True
        for route in snapshot["routes"]:
            route["status"] = "estimated"
            route["mode"] = "transit"
        return snapshot

    def test_an_estimated_route_is_evidence_enough_for_an_explore_trip(self) -> None:
        """The fourth site `WF-038` needed and did not get.

        `validate_variant`, `_routes_between` and `_best_inbound_route` all admit an
        `estimated` route under `allow_provisional_assumptions` — the same rule
        `_planning_fact` applies to an assumed opening window. `_prepare_candidates`
        did not, so a place reachable only by train was thrown out before any of them
        ran, and reported `ROUTE_UNVERIFIED · collect_a_verified_route` on a trip
        already holding a usable transit leg for it.
        """

        variant = optimize_trip(self._route_evidence_snapshot(provisional=True))["variants"][0]

        self.assertEqual([], [
            item for item in variant["reconciliation"] if item["reason"] == "ROUTE_UNVERIFIED"
        ])
        self.assertTrue(variant["metrics"]["scheduled_visits"])

    def test_an_estimated_route_is_still_refused_when_the_trip_is_not_exploring(self) -> None:
        """The other half, and the reason this is a status rule rather than a relaxation:
        a `ready_to_schedule` trip is unaffected and `ROUTE_UNVERIFIED` stays fatal."""

        variant = optimize_trip(self._route_evidence_snapshot(provisional=False))["variants"][0]

        refused = [
            item for item in variant["reconciliation"] if item["reason"] == "ROUTE_UNVERIFIED"
        ]
        self.assertTrue(refused)
        self.assertEqual("cannot_currently_fit", refused[0]["status"])
        self.assertEqual("collect_a_verified_route", refused[0]["consequence"])

    def test_a_place_with_no_route_at_all_is_still_refused(self) -> None:
        """It admits a route the snapshot *has*; it does not invent one. A fabricated
        travel time errs optimistic, which is the one direction this must not err in."""

        snapshot = self._route_evidence_snapshot(provisional=True)
        snapshot["routes"] = []

        variant = optimize_trip(snapshot)["variants"][0]

        self.assertTrue([
            item for item in variant["reconciliation"] if item["reason"] == "ROUTE_UNVERIFIED"
        ])

    def test_a_skipped_place_names_a_threshold_only_when_one_was_exceeded(self) -> None:
        """`_skip_reason` blamed a comfort setting that was nowhere near its cap.

        It answered `PLAIN_WALK_THRESHOLD` whenever a plain-walking threshold merely
        *existed* — and `balanced_pace` always sets one — so a trip with no room for
        another place blamed the owner's walking preference. Measured on the owner's
        Fukuoka trip: three places reported that reason while `comfort_tradeoffs`
        reported 21 minutes against a cap of 45 and nothing exceeded at all.
        """

        snapshot = json.loads(
            json.dumps(fixture("ix-jp-shibuya-hours-view-walk")["planner_input"])
        )
        # A cap far above anything this plan can reach, so it exists and is not met.
        snapshot.setdefault("thresholds", {})["plain_walking_minutes_per_day"] = 10_000
        # Two hours for 225 minutes of visiting, so the room is what runs out.
        snapshot["trip"]["usable_windows"] = [
            {**snapshot["trip"]["usable_windows"][0], "start": "09:00", "end": "11:00"}
        ]

        variant = optimize_trip(snapshot)["variants"][0]
        skipped = [
            item for item in variant["reconciliation"] if item["status"] != "fits"
        ]

        self.assertTrue(skipped, "the fixture must skip something for this to test")
        for item in skipped:
            self.assertEqual("NO_TIME_CAPACITY", item["reason"])

    def _squeezed(self) -> dict:
        """The fixture with one two-hour day, which is not enough room for its places."""

        snapshot = json.loads(
            json.dumps(fixture("ix-jp-shibuya-hours-view-walk")["planner_input"])
        )
        snapshot.setdefault("thresholds", {})["plain_walking_minutes_per_day"] = 10_000
        snapshot["trip"]["usable_windows"] = [
            {**snapshot["trip"]["usable_windows"][0], "start": "09:00", "end": "11:00"}
        ]
        return snapshot

    def test_the_two_ways_out_of_no_time_capacity_actually_lead_out(self) -> None:
        """`/optimize` offers "Add a day" and "Drop these N". Both must change the answer.

        Shipped unverified: no live trip had produced a `NO_TIME_CAPACITY` refusal to
        press them on, so the controls were typecheck-covered and nothing had shown that
        the remedies remedy. They are the two things the optimizer can be given more of
        — room, or fewer places — and this asserts each one clears what it claims to.

        A refusal with a control beside it that does nothing is worse than the dead end
        it replaced, which is the report that produced these buttons in the first place.
        """

        squeezed = self._squeezed()
        before = optimize_trip(squeezed)["variants"][0]
        unfit = [
            item
            for item in before["reconciliation"]
            if item["status"] == "cannot_currently_fit"
        ]
        self.assertTrue(unfit, "the fixture must refuse something for this to test")
        self.assertEqual({"NO_TIME_CAPACITY"}, {item["reason"] for item in unfit})

        # "Add a day" — `addDayAndRebuild` moves `end_date` one day out, which reaches
        # the optimizer as another usable window.
        longer = self._squeezed()
        first = longer["trip"]["usable_windows"][0]
        longer["trip"]["usable_windows"] = [first, {**first, "date": "2030-01-03"}]
        # `local_dates` and the windows must agree; `_validate_input` says so, and
        # `save_setup` keeps them in step for the real path.
        longer["trip"]["local_dates"] = ["2030-01-02", "2030-01-03"]
        after_day = optimize_trip(longer)["variants"][0]
        self.assertGreater(
            sum(1 for item in after_day["reconciliation"] if item["status"] == "fits"),
            sum(1 for item in before["reconciliation"] if item["status"] == "fits"),
            "a second day bought no additional place, so the button is a dead end",
        )

        # "Drop these N" — `cutUnfitAndRebuild` marks each refused place `not_for_trip`,
        # which reaches the optimizer as a shorter candidate list.
        refused = {item["place_id"] for item in unfit}
        fewer = self._squeezed()
        fewer["candidates"] = [
            candidate
            for candidate in fewer["candidates"]
            if candidate.get("id", candidate.get("place_id")) not in refused
        ]
        after_cut = optimize_trip(fewer)["variants"][0]
        self.assertEqual(
            [],
            [
                item
                for item in after_cut["reconciliation"]
                if item["status"] == "cannot_currently_fit"
            ],
            "dropping every refused place left a refusal, so the count on the button lies",
        )

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

    def test_a_variant_cut_off_by_the_limit_is_never_worse_than_greedy(self) -> None:
        """`WF-043`. The invariant was measured, reported, and not acted on.

        `objective_improved_or_equal_to_greedy` was `False` on the pilot while
        `greedy_baseline` sat in the same payload holding 13 visits the variant threw
        away. A budget small enough to expire immediately is the cheap way to force
        the branch: greedy has no time limit, so it is always available as a floor.
        """

        snapshot = fixture("ix-jp-shibuya-hours-view-walk")["planner_input"]

        proposal = optimize_trip(snapshot, time_limit_seconds=0.000001)

        self.assertTrue(proposal["stopped_at_limit"])
        for variant in proposal["variants"]:
            with self.subTest(variant=variant["variant_id"]):
                self.assertTrue(variant["stopped_at_limit"])
                self.assertTrue(variant["objective_improved_or_equal_to_greedy"])
                # The beam reached nothing, so every one of these visits came from the
                # greedy floor.
                self.assertEqual(
                    ["harajuku", "magnet_shibuya", "shibuya_sky"],
                    variant["greedy_baseline"]["scheduled_place_ids"],
                )
                self.assertEqual(3, variant["metrics"]["scheduled_visits"])

    def test_each_variant_gets_its_own_time_budget(self) -> None:
        """`WF-043`. One shared deadline starved whichever variant ran last.

        Consumed in order, so `more_highlights` inherited what the first two left --
        0.04s of a 30s budget on the pilot, against the 21.5s it needs to place all
        13. Asserted structurally because reproducing the starvation needs a snapshot
        slow enough to burn 30 seconds.
        """

        snapshot = fixture("dali-hotel-backtracking-pattern")["planner_input"]
        seen: list[float] = []
        real = optimizer_module._solve_variant

        def record(snap, config, *, deadline):
            seen.append(deadline)
            return real(snap, config, deadline=deadline)

        with patch.object(optimizer_module, "_solve_variant", record):
            optimize_trip(snapshot, time_limit_seconds=5.0)

        self.assertEqual(3, len(seen))
        # Each deadline is set when its own variant starts, so they strictly increase.
        self.assertEqual(sorted(seen), seen)
        self.assertEqual(3, len(set(seen)))

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
