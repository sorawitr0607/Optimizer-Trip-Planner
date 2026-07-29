from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from travel_planner import opening
from travel_planner.actions import PlannerActions
from travel_planner.providers import (
    GooglePlacesOpeningHoursProvider,
    ProviderBudgetExceeded,
    ProviderUnavailable,
)
from tests.test_routes import FakePlaceProvider

ROOT = Path(__file__).resolve().parents[1]

# 2030-01-01 is a Tuesday, so Google days 2, 3, 4 are Tue, Wed, Thu.
TRIP_DATES = ["2030-01-01", "2030-01-02", "2030-01-03"]


def google_payload(periods: list[dict], *, name: str = "Tower") -> dict:
    return {
        "places": [
            {
                "id": "ChIJtest",
                "displayName": {"text": name},
                "location": {"latitude": 25.04, "longitude": 121.57},
                "regularOpeningHours": {"periods": periods, "weekdayDescriptions": []},
            }
        ]
    }


def period(day: int, open_hm: tuple[int, int], close_hm: tuple[int, int] | None,
           close_day: int | None = None) -> dict:
    entry = {"open": {"day": day, "hour": open_hm[0], "minute": open_hm[1]}}
    if close_hm is not None:
        entry["close"] = {
            "day": day if close_day is None else close_day,
            "hour": close_hm[0],
            "minute": close_hm[1],
        }
    return entry


class FakeHoursProvider:
    name = "google_places"
    operation = "google_places:search_text"
    cache_ttl_days = 3
    kind = "opening_hours"

    def __init__(self, *, periods=None, fail_for: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.periods = periods if periods is not None else [
            period(day, (9, 0), (18, 0)) for day in range(7)
        ]
        self.fail_for = fail_for or set()

    def opening_hours(self, place: dict) -> dict:
        self.calls.append(place["place_id"])
        if place["place_id"] in self.fail_for:
            raise ProviderUnavailable("Places returned no opening hours for this place")
        return GooglePlacesOpeningHoursProvider().normalize(
            google_payload(self.periods, name=place["name"]), place=place
        )


class NormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = GooglePlacesOpeningHoursProvider()
        self.place = {
            "place_id": "p1", "name": "Tower", "latitude": 25.04, "longitude": 121.57,
        }

    def test_google_periods_become_plain_records(self) -> None:
        value = self.provider.normalize(
            google_payload([period(2, (9, 30), (18, 0))]), place=self.place
        )
        self.assertEqual("verified", value["status"])
        self.assertEqual("ChIJtest", value["provider_place_id"])
        self.assertEqual(
            [{"day": 2, "start": "09:30", "end": "18:00", "all_day": False, "overnight": False}],
            value["weekly_periods"],
        )

    def test_a_period_with_no_close_is_open_all_day(self) -> None:
        value = self.provider.normalize(
            google_payload([period(0, (0, 0), None)]), place=self.place
        )
        self.assertTrue(value["weekly_periods"][0]["all_day"])
        self.assertEqual("00:00", value["weekly_periods"][0]["start"])
        self.assertEqual("23:59", value["weekly_periods"][0]["end"])

    def test_an_overnight_close_is_clamped_to_the_same_day(self) -> None:
        value = self.provider.normalize(
            google_payload([period(5, (18, 0), (2, 0), close_day=6)]), place=self.place
        )
        entry = value["weekly_periods"][0]
        self.assertTrue(entry["overnight"])
        self.assertEqual("18:00", entry["start"])
        # A single-day visit window cannot run past midnight.
        self.assertEqual("23:59", entry["end"])

    def test_a_missing_match_or_missing_hours_is_refused(self) -> None:
        for payload in ({"places": []}, {}, {"places": [{"id": "x"}]},
                        google_payload([])):
            with self.assertRaises(ProviderUnavailable):
                self.provider.normalize(payload, place=self.place)


class ReductionTest(unittest.TestCase):
    def test_the_interval_valid_on_every_date_is_the_overlap(self) -> None:
        weekly = [
            {"day": 2, "start": "09:00", "end": "18:00"},
            {"day": 3, "start": "10:00", "end": "17:00"},
            {"day": 4, "start": "08:00", "end": "22:00"},
        ]
        reduced = opening.common_interval(weekly, TRIP_DATES)
        self.assertEqual({"start": "10:00", "end": "17:00"}, reduced["interval"])
        self.assertIsNone(reduced["reason"])

    def test_closed_on_any_trip_date_yields_no_interval(self) -> None:
        weekly = [{"day": 2, "start": "09:00", "end": "18:00"}]
        reduced = opening.common_interval(weekly, TRIP_DATES)
        self.assertIsNone(reduced["interval"])
        self.assertEqual("CLOSED_ON_A_TRIP_DATE", reduced["reason"])
        self.assertEqual(["2030-01-02", "2030-01-03"], reduced["closed_dates"])

    def test_non_overlapping_windows_yield_no_interval(self) -> None:
        weekly = [
            {"day": 2, "start": "07:00", "end": "10:00"},
            {"day": 3, "start": "18:00", "end": "22:00"},
            {"day": 4, "start": "07:00", "end": "23:00"},
        ]
        reduced = opening.common_interval(weekly, TRIP_DATES)
        self.assertIsNone(reduced["interval"])
        self.assertEqual("NO_WINDOW_COMMON_TO_EVERY_DATE", reduced["reason"])

    def test_no_trip_dates_yields_no_interval(self) -> None:
        reduced = opening.common_interval([{"day": 2, "start": "09:00", "end": "18:00"}], [])
        self.assertEqual("NO_TRIP_DATES", reduced["reason"])

    def test_day_numbering_follows_google_not_python(self) -> None:
        # Sunday is 0 for Google and 7 for Python's isoweekday.
        self.assertEqual(0, opening.google_day("2030-01-06"))
        self.assertEqual(2, opening.google_day("2030-01-01"))
        self.assertEqual(6, opening.google_day("2030-01-05"))


class OpeningRefreshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "hours.sqlite3"
        self.provider = FakeHoursProvider()
        self.actions = PlannerActions(
            self.path,
            place_provider=FakePlaceProvider(),
            hours_provider=self.provider,
        )
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="ready_to_schedule"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date=TRIP_DATES[0],
            end_date=TRIP_DATES[-1],
            accommodation_status="booked",
            confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        self.places = [
            item["place_id"]
            for item in self.actions.get_latest_discovery(
                self.trip.trip_id
            ).candidates.as_dict()["candidates"]
        ]
        for place_id in self.places:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=place_id, action="must_do"
            )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_hours_become_a_verified_optimizer_fact(self) -> None:
        report = self.actions.refresh_opening_hours(self.trip.trip_id)

        self.assertEqual(len(self.places), report["fetched"])
        self.assertEqual(len(self.places), report["usable_intervals"])
        self.assertEqual({}, report["unusable"])

        snapshot = self.actions._optimizer_input(self.trip.trip_id)
        facts = [f for f in snapshot["facts"] if f["fact_type"] == "opening_interval"]
        self.assertEqual(len(self.places), len(facts))
        self.assertEqual({"verified"}, {fact["status"] for fact in facts})
        self.assertEqual({"google_places"}, {fact["source"] for fact in facts})
        self.assertEqual({"start": "09:00", "end": "18:00"}, facts[0]["value"])
        self.assertEqual(TRIP_DATES, facts[0]["applies_to_dates"])

    def test_a_place_closed_on_a_trip_date_produces_no_fact(self) -> None:
        actions = PlannerActions(
            self.path,
            hours_provider=FakeHoursProvider(periods=[period(2, (9, 0), (18, 0))]),
        )
        report = actions.refresh_opening_hours(self.trip.trip_id, force=True)

        self.assertEqual(0, report["usable_intervals"])
        self.assertEqual(
            {"CLOSED_ON_A_TRIP_DATE"}, set(report["unusable"].values())
        )
        snapshot = actions._optimizer_input(self.trip.trip_id)
        self.assertEqual(
            [], [f for f in snapshot["facts"] if f["fact_type"] == "opening_interval"]
        )

    def test_the_paid_calls_are_priced_and_capped(self) -> None:
        self.actions.refresh_opening_hours(self.trip.trip_id)
        bucket = self.actions.paid_usage_status()["by_operation"][
            "google_places:search_text"
        ]
        self.assertEqual(len(self.places), bucket["requests"])
        self.assertEqual(round(len(self.places) * 0.025, 6), bucket["estimated_usd"])

        self.actions.record_paid_call(operation="google_places:details", count=600)
        with self.assertRaises(ProviderBudgetExceeded):
            self.actions.refresh_opening_hours(self.trip.trip_id, force=True)

    def test_a_second_refresh_reads_evidence_and_records_a_cached_call(self) -> None:
        self.actions.refresh_opening_hours(self.trip.trip_id)
        calls = len(self.provider.calls)

        again = self.actions.refresh_opening_hours(self.trip.trip_id)

        self.assertEqual(calls, len(self.provider.calls))
        self.assertEqual(len(self.places), again["from_cache"])
        bucket = self.actions.paid_usage_status()["by_operation"][
            "google_places:search_text"
        ]
        # Cached reads add no requests and no cost.
        self.assertEqual(len(self.places), bucket["requests"])

    def test_one_place_failing_leaves_the_others_verified(self) -> None:
        actions = PlannerActions(
            self.path, hours_provider=FakeHoursProvider(fail_for={self.places[0]})
        )
        report = actions.refresh_opening_hours(self.trip.trip_id, force=True)

        self.assertEqual(1, report["failed"])
        self.assertEqual(len(self.places) - 1, report["usable_intervals"])
        facts = [
            f
            for f in actions._optimizer_input(self.trip.trip_id)["facts"]
            if f["fact_type"] == "opening_interval"
        ]
        self.assertEqual(len(self.places) - 1, len(facts))
        self.assertNotIn(self.places[0], {fact["subject_id"] for fact in facts})

    def test_expired_evidence_stops_producing_a_fact(self) -> None:
        self.actions.refresh_opening_hours(self.trip.trip_id)
        with self.actions.store.connect() as connection:
            connection.execute(
                "UPDATE place_evidence SET expires_at = '2000-01-01T00:00:00+00:00'"
            )

        intervals = self.actions.opening_intervals(self.trip.trip_id)
        self.assertEqual({"EVIDENCE_EXPIRED"}, {item["reason"] for item in intervals.values()})
        facts = [
            f
            for f in self.actions._optimizer_input(self.trip.trip_id)["facts"]
            if f["fact_type"] == "opening_interval"
        ]
        self.assertEqual([], facts)

    def test_hours_need_a_selected_place(self) -> None:
        bare = PlannerActions(
            Path(self.directory.name) / "bare.sqlite3", hours_provider=self.provider
        )
        trip = bare.create_trip(name="Bare", destination="Osaka")
        bare.save_setup(trip_id=trip.trip_id, main_style=["sightseeing"], confirmed=True)
        with self.assertRaisesRegex(ValueError, "at least one place"):
            bare.refresh_opening_hours(trip.trip_id)


if __name__ == "__main__":
    unittest.main()


class ProvisionalDerivationTest(unittest.TestCase):
    """A plan may only be Ready once the owner has confirmed the basics."""

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.actions = PlannerActions(
            Path(self.directory.name) / "prov.sqlite3",
            place_provider=FakePlaceProvider(),
            hours_provider=FakeHoursProvider(),
        )
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="ready_to_schedule"
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _setup(self, **basics) -> None:
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date=TRIP_DATES[0],
            end_date=TRIP_DATES[-1],
            confirmed=True,
            **basics,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        for item in self.actions.get_latest_discovery(
            self.trip.trip_id
        ).candidates.as_dict()["candidates"]:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=item["place_id"], action="must_do"
            )

    def test_each_unconfirmed_basic_keeps_the_plan_provisional(self) -> None:
        cases = (
            ({"accommodation_status": "not_booked", "arrival_time": "10:00",
              "departure_time": "20:00"}, True),
            ({"accommodation_status": "booked", "arrival_time": None,
              "departure_time": "20:00"}, True),
            ({"accommodation_status": "booked", "arrival_time": "10:00",
              "departure_time": None}, True),
            ({"accommodation_status": "booked", "arrival_time": "10:00",
              "departure_time": "20:00"}, False),
        )
        for basics, expected in cases:
            self._setup(**basics)
            snapshot = self.actions._optimizer_input(self.trip.trip_id)
            self.assertEqual(
                expected, snapshot["trip"]["provisional"], f"basics={basics}"
            )

    def test_a_confirmed_trip_with_evidence_reaches_ready_and_activates(self) -> None:
        self._setup(
            accommodation_status="booked", arrival_time="09:00", departure_time="21:00"
        )
        # All three evidence sources, since one missing keeps a gap open.
        from tests.test_routes import FakeRouteProvider, FakeTimeZoneProvider

        self.actions.refresh_opening_hours(self.trip.trip_id)
        self.actions.route_provider = FakeRouteProvider()
        self.actions.refresh_routes(self.trip.trip_id)
        self.actions.timezone_provider = FakeTimeZoneProvider()
        self.actions.refresh_timezone(self.trip.trip_id)

        snapshot = self.actions._optimizer_input(self.trip.trip_id)
        self.assertEqual([], snapshot["trip"]["capability_gaps"])
        self.assertFalse(snapshot["trip"]["provisional"])

        self.actions.generate_plan_preview(self.trip.trip_id)
        proposal = self.actions.get_plan_preview(self.trip.trip_id).proposal.as_dict()
        ready = [v for v in proposal["variants"] if v["status"] == "ready"]
        self.assertTrue(ready, [v["status"] for v in proposal["variants"]])

        version = self.actions.activate_plan_preview(
            trip_id=self.trip.trip_id, variant_id=ready[0]["variant_id"]
        )
        export = self.actions.build_export_snapshot(self.trip.trip_id).as_dict()
        self.assertEqual("ready", export["readiness"]["state"])
        self.assertEqual([], export["readiness"]["capability_gaps"])
        self.assertEqual(version.version_id, export["stamp"]["plan_version_id"])
