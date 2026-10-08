"""Behavioural checks derived from the Taiwan review draft."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from travel_planner.actions import PlannerActions
from travel_planner.optimizer import optimize_trip, validate_variant
from travel_planner.planning import apply_research, normalize_research
from travel_planner.setup import build_setup_payload
from tests.test_routes import FakePlaceProvider, FakeRouteProvider


def snapshot():
    return {"trip": {"destination": "Taipei", "timezone": "Asia/Taipei", "local_dates": ["2026-12-31"],
                     "usable_windows": [{"date": "2026-12-31", "start": "09:00", "end": "22:00"}]},
            "travellers": [{"id": str(index)} for index in range(4)], "candidates": [], "facts": [],
            "routes": [], "locks": [], "weights": {}, "thresholds": {}}


def place(identifier, *, priority="must_do", score=80, minutes=60):
    return {"id": identifier, "name": identifier, "priority": priority, "score": score, "duration_minutes": minutes}


class ExperiencePlanningTest(unittest.TestCase):
    def test_researched_time_yields_to_real_return_without_relaxing_fixed_event(self):
        from travel_planner.optimizer import _build_day, _timing_miss_minutes
        value = snapshot()
        value["trip"]["usable_windows"][0]["end"] = "21:00"
        candidate = {**place("temple", minutes=55), "duration_basis": "researched_activity", "preferred_interval": {"start": "20:05", "end": "21:00"}}
        value["candidates"] = [candidate]
        value["routes"] = [{"origin_id": "temple", "destination_id": "hotel", "mode": "taxi", "duration_minutes": 15, "walking_minutes": 0, "status": "estimated"}]
        result = _build_day(value, "2026-12-31", [candidate], {"duration": "ideal", "buffer_minutes": 10}, end_base="hotel")
        self.assertFalse(result["hard_errors"])
        visits = [item for item in result["day"]["items"] if item["type"] == "visit"]
        self.assertLess(visits[0]["start"], "20:05")
        self.assertEqual(55, _timing_miss_minutes(value, result["day"], visits, None))
        fixed = _build_day(value, "2026-12-31", [{**candidate, "fixed_event": True}], {"duration": "ideal", "buffer_minutes": 10}, end_base="hotel")
        self.assertTrue(fixed["hard_errors"])

    def test_countdown_dinner_is_flexible_and_return_buffer_must_fit(self):
        from travel_planner.optimizer import _fixed_step_timing, _return_to_base
        self.assertFalse(_fixed_step_timing({}, {"name": "Early dinner before countdown", "type": "meal"}))
        self.assertTrue(_fixed_step_timing({}, {"name": "Countdown", "type": "visit"}))
        value = snapshot()
        value["routes"] = [{"origin_id": "place", "destination_id": "hotel", "mode": "taxi", "duration_minutes": 10, "walking_minutes": 0, "status": "estimated"}]
        result = _return_to_base(value, "2026-12-31", "place", "hotel", {"buffer_minutes": 10}, cursor=590, body_end=600)
        self.assertEqual("DAY_WINDOW_EXCEEDED", result["error"]["code"])

    def test_driving_matrix_has_no_walking_and_remains_estimated(self):
        from travel_planner.providers import OpenRouteServiceMatrixProvider
        provider = OpenRouteServiceMatrixProvider(mode="taxi")
        routes = provider.normalize({"durations": [[0, 600], [660, 0]]}, points=[{"place_id": "a"}, {"place_id": "b"}])
        self.assertEqual("taxi", routes[0]["mode"])
        self.assertEqual(0, routes[0]["walking_minutes"])
        self.assertEqual("estimated", routes[0]["status"])
        self.assertIn("driving-car", provider.matrix_url)

    def test_unresolved_fixed_event_remains_visible_in_reconciliation(self):
        value = snapshot()
        value["candidates"] = [place("anchor")]
        profile = normalize_research({"experiences": [{"name": "Countdown", "date": "2026-12-31", "fixed_event": True, "sources": ["https://example.org"], "minimum_minutes": 40, "ideal_minutes": 40, "maximum_minutes": 40}]}, {"places": [{"id": "anchor"}], "dates": ["2026-12-31"]}, {"https://example.org"})
        apply_research(value, profile)
        event = next(item for item in optimize_trip(value)["variants"][0]["reconciliation"] if item["name"] == "Countdown")
        self.assertEqual("cannot_currently_fit", event["status"])
        self.assertEqual("ROUTE_UNVERIFIED", event["reason"])

    def test_composite_market_meal_covers_the_selected_market(self):
        value = snapshot()
        value["candidates"] = [{**place("entry", minutes=120), "duration_bounds": {"minimum_minutes": 120, "ideal_minutes": 120, "maximum_minutes": 120},
            "steps": [{"name": "Entry", "type": "visit", "duration_minutes": 30}, {"name": "Market dinner", "type": "meal", "meal_role": "dinner", "place_id": "market", "duration_minutes": 90}]},
            {**place("market"), "group_parent_id": "entry"}]
        result = optimize_trip(value)["variants"][0]
        self.assertTrue(result["validation"]["valid"], result["validation"])
        self.assertEqual("fits", next(item for item in result["reconciliation"] if item["place_id"] == "market")["status"])

    def test_complete_trip_requires_explicit_acceptance_of_a_provisional_plan(self):
        from travel_planner.actions import PlannerRefusal
        from travel_planner.core import new_optimization_preview
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "test.sqlite3")
            trip = actions.create_trip(name="Scheduled trip", destination="Taipei", planning_mode="ready_to_schedule")
            value = snapshot()
            value["trip"].update(complete_trip=True, provisional=True, allow_provisional_assumptions=True)
            value["candidates"] = [place("anchor")]
            proposal = optimize_trip(value)
            actions.store.save_optimization_preview(new_optimization_preview(trip_id=trip.trip_id, optimizer_input=value, proposal=proposal))
            with patch.object(actions, "_optimizer_input", return_value=value):
                with self.assertRaises(PlannerRefusal):
                    actions.activate_plan_preview(trip_id=trip.trip_id, variant_id="best_balance")
                version = actions.activate_plan_preview(trip_id=trip.trip_id, variant_id="best_balance", accept_provisional=True)
            self.assertEqual("provisional", version.snapshot.as_dict()["variant"]["status"])

    def test_existing_trip_can_relink_places_after_enabling_complete_planning(self):
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "test.sqlite3", place_provider=FakePlaceProvider())
            trip = actions.create_trip(name="Existing trip", destination="Taipei")
            actions.save_setup(trip_id=trip.trip_id, main_style=["nature"], confirmed=True)
            original = actions.discover_places(trip_id=trip.trip_id)
            chosen = original.candidates.as_dict()["candidates"][0]
            actions.save_candidate_choice(trip_id=trip.trip_id, place_id=chosen["place_id"], action="must_do")
            actions.save_setup(trip_id=trip.trip_id, main_style=["nature"], complete_trip=True, confirmed=True)
            stale = actions.get_ranked_discovery(trip.trip_id)
            self.assertEqual(original.run_id, stale["discovery"].run_id)
            self.assertIsNone(stale["ranking"])
            actions.discover_places(trip_id=trip.trip_id)
            self.assertIsNotNone(actions.get_ranked_discovery(trip.trip_id)["ranking"])
            self.assertEqual("must_do", actions.store.list_candidate_choices(trip.trip_id)[0].action)

    def test_untimed_bus_stops_are_explicit_topology_estimates(self):
        from travel_planner.gtfs import TransitFeed
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bus.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\na,Entry,25,121\nb,Middle,25.01,121\nc,Exit,25.02,121\n")
                archive.writestr("routes.txt", "route_id,route_type,route_short_name\nbus,3,849\n")
                archive.writestr("trips.txt", "trip_id,route_id,service_id\ntrip,bus,service\n")
                archive.writestr("stop_times.txt", "trip_id,stop_id,stop_sequence,arrival_time,departure_time\ntrip,a,1,09:00:00,09:00:00\ntrip,b,2,,\ntrip,c,3,,\n")
            journey = TransitFeed(path).journey(origin=(25, 121), destination=(25.02, 121))
            self.assertIsNotNone(journey)
            self.assertEqual("bus_topology_estimate", journey.basis)
            self.assertGreater(journey.total_minutes, 10)

    def test_review_edit_survives_rebuild_and_activates(self):
        from datetime import datetime, timedelta, timezone
        from travel_planner.planning import RESEARCH_KIND, research_key, research_payload
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "test.sqlite3", place_provider=FakePlaceProvider(), route_provider=FakeRouteProvider())
            trip = actions.create_trip(name="Review", destination="Taipei", planning_mode="explore_first")
            actions.save_setup(trip_id=trip.trip_id, owner_age=35, main_style=["nature"], start_date="2026-12-30", end_date="2027-01-02", complete_trip=True, confirmed=True)
            chosen = actions.discover_places(trip_id=trip.trip_id).candidates.as_dict()["candidates"][0]
            actions.save_candidate_choice(trip_id=trip.trip_id, place_id=chosen["place_id"], action="must_do")
            actions.refresh_routes(trip.trip_id)
            seed = actions._optimizer_input(trip.trip_id, include_research=False)
            evidence = normalize_research({"experiences": [{"name": "English anchor", "place_id": chosen["place_id"], "sources": ["https://example.org"], "minimum_minutes": 30, "ideal_minutes": 45, "maximum_minutes": 60}]}, research_payload(seed, "", []), {"https://example.org"})
            now = datetime.now(timezone.utc)
            evidence.update(setup_sha256=actions.store.get_setup(trip.trip_id).snapshot.sha256, request_sha256=research_key(research_payload(seed, "", [])))
            actions.store.upsert_trip_evidence(trip_id=trip.trip_id, kind=RESEARCH_KIND, value=evidence, provider="test", retrieved_at=now.isoformat(), expires_at=(now + timedelta(days=7)).isoformat())
            preview = actions.update_preview_experience(trip_id=trip.trip_id, place_id=chosen["place_id"], priority="interested", duration_minutes=35)
            self.assertFalse(actions._research_experiences(trip.trip_id, seed))
            candidate = next(item for item in preview.optimizer_input.as_dict()["candidates"] if item["id"] == chosen["place_id"])
            self.assertEqual(35, candidate["duration_bounds"]["ideal_minutes"])
            self.assertEqual("interested", candidate["priority"])
            self.assertTrue(preview.proposal.as_dict()["variants"][0]["validation"]["valid"], preview.proposal.as_dict()["variants"][0])
            self.assertIn(preview.proposal.as_dict()["variants"][0]["status"], {"ready", "provisional"}, preview.proposal.as_dict()["variants"][0])
            actions.activate_plan_preview(trip_id=trip.trip_id, variant_id="best_balance")
            self.assertIsNotNone(actions.build_export_snapshot(trip_id=trip.trip_id))

    def test_low_value_optional_does_not_buy_a_hundred_minute_transfer(self):
        value = snapshot()
        value["candidates"] = [place("anchor"), place("detour", priority="maybe", score=1, minutes=15)]
        value["routes"] = [{"origin_id": "anchor", "destination_id": "detour", "mode": "transit", "duration_minutes": 100, "status": "estimated"},
                           {"origin_id": "detour", "destination_id": "anchor", "mode": "transit", "duration_minutes": 100, "status": "estimated"}]
        for variant in optimize_trip(value)["variants"]:
            self.assertEqual(["anchor"], [item["subject_id"] for day in variant["days"] for item in day["items"] if item["type"] == "visit"])

    def test_overnight_countdown_has_actual_january_timestamp(self):
        value = snapshot()
        value["trip"]["usable_windows"][0]["end"] = "25:30"
        value["candidates"] = [{**place("countdown", minutes=40), "preferred_interval": {"start": "23:30", "end": "24:10"}}]
        result = optimize_trip(value)["variants"][0]
        self.assertTrue(result["validation"]["valid"])
        visit = next(item for item in result["days"][0]["items"] if item["type"] == "visit")
        self.assertEqual("2027-01-01T00:10:00+08:00", visit["ends_at"])

    def test_disjoint_and_date_specific_hours_do_not_schedule_over_lunch_closure(self):
        value = snapshot()
        value["trip"]["usable_windows"][0]["start"] = "11:30"
        value["candidates"] = [place("museum", minutes=90)]
        value["facts"] = [{"subject_id": "museum", "fact_type": "opening_interval", "status": "verified", "value": {"start": "09:00", "end": "18:00"},
                           "intervals_by_date": {"2026-12-31": [{"start": "09:00", "end": "12:00"}, {"start": "14:00", "end": "18:00"}]}}]
        result = optimize_trip(value)["variants"][0]
        visit = next(item for item in result["days"][0]["items"] if item["type"] == "visit")
        self.assertEqual("14:00", visit["start"])
        visit["start"], visit["end"] = "11:30", "13:00"
        self.assertIn("CLOSED_DURING_VISIT", {error["code"] for error in validate_variant(value, result)["hard_violations"]})

    def test_market_lunch_is_one_experience_and_consumes_the_meal_slot(self):
        value = snapshot()
        value["trip"].update(include_operational_timeline=True)
        value["trip"]["local_dates"] = ["2026-12-30", "2026-12-31", "2027-01-01"]
        value["trip"]["usable_windows"] = [{"date": day, "start": "08:00", "end": "22:00"} for day in value["trip"]["local_dates"]]
        value["candidates"] = [{**place("market", minutes=75), "scheduled_date": "2026-12-31", "meal_roles": ["lunch"]}]
        result = optimize_trip(value)["variants"][0]
        day = next(day for day in result["days"] if day["date"] == "2026-12-31")
        self.assertFalse(any(item["type"] == "meal" and item["kind"] == "lunch" for item in day["items"]))
        visit = next(item for item in day["items"] if item["type"] == "visit")
        self.assertGreaterEqual(visit["start"], "11:30")

    def test_connected_group_covers_anchors_and_validates_all_steps(self):
        value = snapshot()
        value["candidates"] = [place("entry"), place("peak")]
        evidence = {"experiences": [{"place_id": "entry", "duration_bounds": {"minimum_minutes": 150, "ideal_minutes": 150, "maximum_minutes": 180},
                    "duration_basis": "researched_activity", "sources": ["https://example.org/trail"], "reason": "Connected ridge", "alternative": "Turn back if tired", "group": "Ridge hike",
                    "meal_roles": [], "preferred_interval": None, "scheduled_date": None,
                    "steps": [{"name": "Entry", "type": "visit", "duration_minutes": 30},
                              {"name": "Ridge", "type": "travel", "mode": "walk", "walking_minutes": 90, "duration_minutes": 90},
                              {"name": "Peak", "place_id": "peak", "type": "visit", "duration_minutes": 30}]}]}
        apply_research(value, evidence)
        result = optimize_trip(value)["variants"][0]
        self.assertTrue(result["validation"]["valid"], result["validation"])
        self.assertEqual({"entry", "peak"}, {item["subject_id"] for day in result["days"] for item in day["items"] if item["type"] == "visit"})
        result["days"][0]["items"].pop()
        self.assertIn("EXPERIENCE_GROUP_INCOMPLETE", {error["code"] for error in validate_variant(value, result)["hard_violations"]})

    def test_full_journey_uses_real_elapsed_time_and_cannot_be_tampered_with(self):
        value = snapshot()
        value["candidates"] = [place("temple")]
        value["trip"]["usable_windows"][0]["start"] = "18:00"
        value["trip"]["journey_legs"] = [{"id": "flight", "name": "TG634", "starts_at": "2026-12-31T12:40:00+07:00", "ends_at": "2026-12-31T17:20:00+08:00"}]
        result = optimize_trip(value)["variants"][0]
        self.assertTrue(result["validation"]["valid"], result["validation"])
        flight = next(item for day in result["days"] for item in day["items"] if item.get("fixed_commitment"))
        self.assertEqual(220, flight["duration_minutes"])
        flight["ends_at"] = "2026-12-31T17:21:00+08:00"
        self.assertIn("FIXED_JOURNEY_CHANGED", {error["code"] for error in validate_variant(value, result)["hard_violations"]})

    def test_unsourced_or_invented_recommendations_are_rejected(self):
        payload = {"places": [{"id": "known"}], "dates": ["2026-12-31"]}
        raw = {"experiences": [{"name": "Invented", "place_id": "fake", "sources": ["https://example.org"], "minimum_minutes": 30, "ideal_minutes": 45, "maximum_minutes": 60}]}
        self.assertEqual([], normalize_research(raw, payload, {"https://example.org"})["experiences"])

    def test_setup_carries_special_days_through_actions_and_applies_recovery(self):
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "test.sqlite3", place_provider=FakePlaceProvider(), route_provider=FakeRouteProvider())
            trip = actions.create_trip(name="NYE", destination="Taipei")
            actions.save_setup(trip_id=trip.trip_id, owner_age=35, main_style=["nature"], start_date="2026-12-31", end_date="2027-01-02",
                               complete_trip=True, planning_brief="New Year", day_preferences=[{"date": "2026-12-31", "start": "09:00", "end": "01:30", "purpose": "Countdown"}], confirmed=True)
            run = actions.discover_places(trip_id=trip.trip_id)
            chosen = run.candidates.as_dict()["candidates"][0]
            actions.save_candidate_choice(trip_id=trip.trip_id, place_id=chosen["place_id"], action="must_do")
            value = actions._optimizer_input(trip.trip_id)
            self.assertEqual("25:30", value["trip"]["usable_windows"][0]["end"])
            self.assertEqual("09:30", value["trip"]["usable_windows"][1]["start"])
            self.assertTrue(value["trip"]["complete_trip"])


if __name__ == "__main__":
    unittest.main()
