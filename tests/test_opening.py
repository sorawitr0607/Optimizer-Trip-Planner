from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


from travel_planner import opening
from travel_planner.actions import PlannerActions, _osm_opening_hours
from travel_planner.providers import (
    GooglePlacesOpeningHoursProvider,
    ProviderBudgetExceeded,
    ProviderUnavailable,
)
from tests.test_routes import FakePlaceProvider, FakeRouteProvider


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
        payload = google_payload(self.periods, name=place["name"])
        payload["places"][0]["location"] = {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
        }
        return GooglePlacesOpeningHoursProvider().normalize(
            payload, place=place
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

    def test_hours_search_uses_local_name_and_destination(self) -> None:
        captured = {}
        place = {
            **self.place,
            "name": "Dailaokengshan",
            "names": {"local": "待老坑山"},
            "category": "peak",
            "destination": "Taipei, Taiwan",
        }
        payload = google_payload([period(0, (0, 0), None)], name="待老坑山")
        payload["places"][0]["location"] = {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
        }

        def response(request, timeout):
            captured.update(json.loads(request.data))
            return BytesIO(json.dumps(payload).encode("utf-8"))

        with patch.dict(os.environ, {"GOOGLE_MAPS_SERVER_KEY": "test"}), patch(
            "travel_planner.providers.urlopen", side_effect=response
        ):
            self.provider.opening_hours(place)

        self.assertEqual("待老坑山 peak, Taipei, Taiwan", captured["textQuery"])
        self.assertEqual(5, captured["pageSize"])

    def test_hours_can_use_a_nearby_alias_but_not_a_different_venue_type(self) -> None:
        place = {
            **self.place,
            "name": "Dailaokengshan",
            "names": {"local": "待老坑山"},
            "category": "peak",
        }
        always_open = {"periods": [period(0, (0, 0), None)]}
        payload = {
            "places": [
                {
                    "id": "trail",
                    "displayName": {"text": "Dailaokeng Mountain"},
                    "primaryType": "hiking_area",
                    "location": {"latitude": 25.0401, "longitude": 121.5701},
                    "regularOpeningHours": always_open,
                },
                {
                    "id": "peak",
                    "displayName": {"text": "待老坑山"},
                    "primaryType": "mountain_peak",
                    "location": {"latitude": 25.04, "longitude": 121.57},
                },
            ]
        }

        value = self.provider.normalize(payload, place=place)

        self.assertEqual("trail", value["provider_place_id"])
        self.assertEqual(7, len(value["weekly_periods"]))

        payload["places"] = [
            {
                "id": "temple",
                "displayName": {"text": "待老坑山 Temple"},
                "primaryType": "buddhist_temple",
                "location": {"latitude": 25.0401, "longitude": 121.5701},
                "regularOpeningHours": always_open,
            }
        ]
        with self.assertRaises(ProviderUnavailable):
            self.provider.normalize(payload, place=place)

    def test_a_period_with_no_close_is_open_all_week(self) -> None:
        value = self.provider.normalize(
            google_payload([period(0, (0, 0), None)]), place=self.place
        )
        self.assertEqual(set(range(7)), {item["day"] for item in value["weekly_periods"]})
        self.assertTrue(all(item["all_day"] for item in value["weekly_periods"]))

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

    def test_a_closed_date_narrows_the_window_rather_than_removing_it(self) -> None:
        """`WF-041`. The overlap is taken across the days the place is open."""

        weekly = [{"day": 2, "start": "09:00", "end": "18:00"}]
        reduced = opening.common_interval(weekly, TRIP_DATES)
        self.assertEqual({"start": "09:00", "end": "18:00"}, reduced["interval"])
        # A usable interval and a reason now coexist: the hours are known, and the
        # place is still shut on named days. Callers key off `interval`.
        self.assertEqual("CLOSED_ON_A_TRIP_DATE", reduced["reason"])
        self.assertEqual(["2030-01-02", "2030-01-03"], reduced["closed_dates"])
        self.assertEqual(["2030-01-01"], reduced["open_dates"])

    def test_closed_on_every_trip_date_yields_no_interval(self) -> None:
        """Nothing to intersect, so nothing to offer."""

        reduced = opening.common_interval(
            [{"day": 0, "start": "09:00", "end": "18:00"}], ["2030-01-01", "2030-01-02"]
        )
        self.assertIsNone(reduced["interval"])
        self.assertEqual("CLOSED_ON_EVERY_TRIP_DATE", reduced["reason"])
        self.assertEqual([], reduced["open_dates"])

    def test_non_overlapping_windows_yield_no_interval(self) -> None:
        weekly = [
            {"day": 2, "start": "07:00", "end": "10:00"},
            {"day": 3, "start": "18:00", "end": "22:00"},
            {"day": 4, "start": "07:00", "end": "23:00"},
        ]
        reduced = opening.common_interval(weekly, TRIP_DATES)
        self.assertIsNone(reduced["interval"])
        self.assertEqual("NO_WINDOW_COMMON_TO_EVERY_OPEN_DATE", reduced["reason"])

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

    def test_a_place_closed_on_one_trip_date_is_still_usable_on_the_others(self) -> None:
        """`WF-041`. This test asserted the defect: it required *no* fact.

        A place shut on one trip day was unschedulable on every day, because
        `_optimizer_input` emitted one trip-wide window or nothing. Measured on the
        pilot trip, Red House is open six of seven days and was scheduled on none,
        and five of thirteen landmarks were lost the same way. Now the window is the
        overlap across the **open** days and `applies_to_dates` names them.
        """

        actions = PlannerActions(
            self.path,
            hours_provider=FakeHoursProvider(periods=[period(2, (9, 0), (18, 0))]),
        )
        report = actions.refresh_opening_hours(self.trip.trip_id, force=True)

        # No longer "unusable": the place is schedulable, just not every day. The
        # closure is still reported, on the evidence rather than as a rejection.
        self.assertEqual({}, report["unusable"])
        self.assertGreater(report["usable_intervals"], 0)
        evidence = actions.opening_intervals(self.trip.trip_id)
        reasons = {rec.get("reason") for rec in evidence.values() if rec.get("interval")}
        self.assertEqual({"CLOSED_ON_A_TRIP_DATE"}, reasons)
        snapshot = actions._optimizer_input(self.trip.trip_id)
        facts = [f for f in snapshot["facts"] if f["fact_type"] == "opening_interval"]
        self.assertTrue(facts, "a closed day must not erase the whole window")
        for fact in facts:
            self.assertEqual({"start": "09:00", "end": "18:00"}, fact["value"])
            # Tuesday only: the other two trip dates are shut and must be excluded.
            self.assertEqual(["2030-01-01"], fact["applies_to_dates"])

    def test_a_closed_day_moves_a_visit_rather_than_dropping_it(self) -> None:
        """`WF-041` end to end: schedule on the open days, never on the shut one.

        The unit test above proves the window survives a closed date. This proves the
        optimizer acts on it — the point being that a place open six of seven days
        should appear on one of the six, not vanish.
        """

        from travel_planner.optimizer import optimize_trip

        actions = PlannerActions(
            self.path,
            hours_provider=FakeHoursProvider(periods=[period(2, (9, 0), (18, 0))]),
        )
        actions.refresh_opening_hours(self.trip.trip_id, force=True)
        snapshot = actions._optimizer_input(self.trip.trip_id)
        facts = {
            fact["subject_id"]: fact
            for fact in snapshot["facts"]
            if fact["fact_type"] == "opening_interval"
        }
        self.assertTrue(facts)
        open_dates = set(next(iter(facts.values()))["applies_to_dates"])
        shut = set(snapshot["trip"]["local_dates"]) - open_dates
        self.assertTrue(shut, "the fixture must have a closed trip date to be a test")

        # The guard itself, asserted directly. The walk over the proposal below is a
        # weaker check than it looks: this fixture's single open day is the one the
        # optimizer would pick regardless, so removing the guard still produced a
        # clean plan. `_earliest_visit_start` is where the decision actually lives.
        from travel_planner.optimizer import _earliest_visit_start

        subject = next(iter(facts))
        candidate = next(
            item for item in snapshot["candidates"] if item["id"] == subject
        )
        for day in sorted(open_dates):
            self.assertIsNotNone(
                _earliest_visit_start(snapshot, candidate, day, 9 * 60, 30),
                f"{subject} must be schedulable on {day}",
            )
        for day in sorted(shut):
            self.assertIsNone(
                _earliest_visit_start(snapshot, candidate, day, 9 * 60, 30),
                f"{subject} must not be schedulable on {day}",
            )

        proposal = optimize_trip(snapshot)
        for variant in proposal["variants"]:
            for day in variant.get("days") or []:
                for item in day.get("items", []):
                    if item.get("type") != "visit":
                        continue
                    fact = facts.get(item.get("subject_id"))
                    if fact:
                        self.assertIn(
                            day["date"],
                            fact["applies_to_dates"],
                            f"{item.get('subject_id')} scheduled on a day it is shut",
                        )
            self.assertNotIn(
                "CLOSED_DURING_VISIT",
                {error["code"] for error in variant["validation"]["hard_violations"]},
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
        # The Google layer is unchanged: the failed place has no Google fact and
        # every other place does. OSM catalogue hours are an independent second
        # layer on top, so the total also carries the temple's normalized fact.
        google = [f for f in facts if f["source"] == "google_places"]
        self.assertEqual(len(self.places) - 1, len(google))
        self.assertNotIn(self.places[0], {fact["subject_id"] for fact in google})
        osm = [f for f in facts if f["source"] == "normalized_discovery"]
        # OSM hours are the fallback under Google ones: the two places with live
        # Google intervals keep Google facts, and only the failed place falls
        # through to its catalogue hours.
        self.assertEqual([self.places[0]], [f["subject_id"] for f in osm])

    def test_owner_can_confirm_a_window_when_the_provider_has_none(self) -> None:
        actions = PlannerActions(
            self.path, hours_provider=FakeHoursProvider(fail_for={self.places[0]})
        )
        actions.refresh_opening_hours(self.trip.trip_id, force=True)

        before = actions.opening_intervals(self.trip.trip_id)[self.places[0]]
        self.assertEqual("OPENING_NOT_FETCHED", before["reason"])

        actions.confirm_opening_window(
            self.trip.trip_id,
            self.places[0],
            start="08:00",
            end="18:00",
        )

        after = actions.opening_intervals(self.trip.trip_id)[self.places[0]]
        self.assertEqual({"start": "08:00", "end": "18:00"}, after["interval"])
        fact = next(
            item
            for item in actions._optimizer_input(self.trip.trip_id)["facts"]
            if item["subject_id"] == self.places[0]
            and item["fact_type"] == "opening_interval"
        )
        self.assertEqual("owner_confirmation", fact["source"])

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
        # Expired Google evidence stops producing Google facts -- but the OSM
        # catalogue hours are a separate source with their own life, so the
        # temple's normalized fact survives the expiry.
        self.assertEqual(
            [], [f for f in facts if f["source"] == "google_places"]
        )
        self.assertEqual(
            len(self.places),
            len([f for f in facts if f["source"] == "normalized_discovery"]),
        )

    def test_pre_fix_evidence_is_not_used_after_the_24_7_parser_upgrade(self) -> None:
        self.actions.refresh_opening_hours(self.trip.trip_id)
        current = self.actions.store.list_place_evidence(
            self.trip.trip_id, "opening_hours"
        )[0]
        value = {
            key: value
            for key, value in current.items()
            if key not in {"normalizer_version", "retrieved_at", "expires_at"}
        }
        now = "2030-01-01T00:00:00+00:00"
        self.actions.store.upsert_place_evidence(
            trip_id=self.trip.trip_id,
            place_id=current["place_id"],
            kind="opening_hours",
            value=value,
            provider="google_places",
            retrieved_at=now,
            expires_at="2031-01-01T00:00:00+00:00",
        )

        interval = self.actions.opening_intervals(self.trip.trip_id)[current["place_id"]]

        self.assertIsNone(interval["interval"])
        self.assertEqual("EVIDENCE_NORMALIZER_OUTDATED", interval["reason"])

    def test_hours_need_a_selected_place(self) -> None:
        bare = PlannerActions(
            Path(self.directory.name) / "bare.sqlite3", hours_provider=self.provider
        )
        trip = bare.create_trip(name="Bare", destination="Osaka")
        bare.save_setup(trip_id=trip.trip_id, main_style=["sightseeing"], confirmed=True)
        with self.assertRaises(ValueError) as raised:
            bare.refresh_opening_hours(trip.trip_id)
        self.assertEqual("no_places_chosen", str(raised.exception))


class OsmHoursTest(unittest.TestCase):
    def test_a_weekday_range_parses_to_covered_dates(self) -> None:
        """The Daimyo Clock Museum carries `Tu-Su 10:00-16:00` on OSM, and the
        old path could not read a weekday qualifier at all, so the plan arrived
        22 minutes before closing."""

        interval, open_dates = _osm_opening_hours("Tu-Su 10:00-16:00", TRIP_DATES)
        self.assertEqual({"start": "10:00", "end": "16:00"}, interval)
        # Tue-Thu trip, all inside Tu-Su.
        self.assertEqual(TRIP_DATES, open_dates)

    def test_a_closed_weekday_is_excluded_from_the_dates(self) -> None:
        interval, open_dates = _osm_opening_hours("We-Su 10:00-16:00", TRIP_DATES)
        self.assertEqual({"start": "10:00", "end": "16:00"}, interval)
        # 2030-01-01 is the Tuesday the place is shut.
        self.assertEqual(["2030-01-02", "2030-01-03"], open_dates)

    def test_a_bare_interval_covers_every_trip_date(self) -> None:
        interval, open_dates = _osm_opening_hours("09:00-17:00", TRIP_DATES)
        self.assertEqual({"start": "09:00", "end": "17:00"}, interval)
        self.assertEqual(TRIP_DATES, open_dates)

    def test_anything_fancier_is_refused_never_guessed(self) -> None:
        for value in (
            "Tu-Sa 12:00-18:00; Su 12:00-17:00",
            "Apr-Oct 09:00-18:00",
            "sunrise-sunset",
            "24/7",
            "",
            None,
        ):
            self.assertEqual(
                (None, None), _osm_opening_hours(value, TRIP_DATES), value
            )

    def test_osm_regular_hours_become_a_verified_optimizer_fact(self) -> None:
        """The fake catalogue's Culture Temple carries bare `08:00-20:00` OSM
        hours. The old trust gate ignored every OSM state but official ones, so
        no fact constrained it; now it schedules inside 08:00-20:00."""

        from tests.test_setup_discovery import FakePlaceProvider as DiscoveryFake

        directory = TemporaryDirectory()
        try:
            actions = PlannerActions(
                Path(directory.name) / "osm.sqlite3",
                place_provider=DiscoveryFake(),
            )
            trip = actions.create_trip(
                name="Taipei", destination="Taipei", planning_mode="ready_to_schedule"
            )
            actions.save_setup(
                trip_id=trip.trip_id,
                main_style=["sightseeing"],
                start_date=TRIP_DATES[0],
                end_date=TRIP_DATES[-1],
                accommodation_status="booked",
                confirmed=True,
            )
            actions.discover_places(trip_id=trip.trip_id)
            temple = next(
                item["place_id"]
                for item in actions.get_latest_discovery(
                    trip.trip_id
                ).candidates.as_dict()["candidates"]
                if item["name"] == "Culture Temple"
            )
            actions.save_candidate_choice(
                trip_id=trip.trip_id, place_id=temple, action="must_do"
            )
            snapshot = actions._optimizer_input(trip.trip_id)
            facts = [
                fact
                for fact in snapshot["facts"]
                if fact["fact_type"] == "opening_interval"
                and fact["subject_id"] == temple
            ]
            self.assertEqual(1, len(facts))
            self.assertEqual("verified", facts[0]["status"])
            self.assertEqual("normalized_discovery", facts[0]["source"])
            self.assertEqual({"start": "08:00", "end": "20:00"}, facts[0]["value"])
        finally:
            directory.cleanup()


class ExploreFirstEvidenceTest(unittest.TestCase):
    class PlaceProvider(FakePlaceProvider):
        def discover(self, destination: str) -> dict:
            payload = super().discover(destination)
            for item in payload["items"]:
                item.pop("opening_hours", None)
            return payload

        def geocode(self, query: str) -> dict:
            return {
                "name": query,
                "address": "1 Test Road, Taipei",
                "latitude": 25.045,
                "longitude": 121.515,
                "status": "owner_confirmed",
                "provider": self.name,
            }

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "explore.sqlite3"
        self.actions = PlannerActions(
            self.path,
            place_provider=self.PlaceProvider(),
            route_provider=FakeRouteProvider(),
        )
        self.trip = self.actions.create_trip(
            name="Explore Taipei", destination="Taipei", planning_mode="explore_first"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date=TRIP_DATES[0],
            end_date=TRIP_DATES[-1],
            accommodation_status="not_booked",
            confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        for item in self.actions.get_latest_discovery(
            self.trip.trip_id
        ).candidates.as_dict()["candidates"]:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id,
                place_id=item["place_id"],
                action="must_do",
            )
        self.actions.refresh_routes(self.trip.trip_id)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_a_base_hundreds_of_kilometres_away_is_not_used_as_a_base(self) -> None:
        """The owner's New York trip, reproduced.

        `confirm_accommodation_base` defaults its query to ``f"{destination} Station"``,
        and the geocoder answered "New York, United States Station" with a station in
        **upstate New York** — 42.796, -76.119, which is **286 km** from every one of the
        eleven places the owner had chosen. It was stored as a booked base, so
        `hotel_recommendation.basis` read `booked_accommodation` and the whole itinerary
        was built around a hotel a four-hour drive from the trip.

        A base that far from everything it is meant to serve is not a base, whatever the
        geocoder called it. It is dropped and the gap is named, so the plan falls back to
        the selected-place centroid rather than being quietly wrong.
        """

        far_away = {
            "name": "Upstate Station",
            "latitude": 25.045 + 3.0,  # ~333 km north of the Taipei fixture's places.
            "longitude": 121.515,
            "status": "owner_confirmed",
            "provider": "test",
        }
        self.actions.store.upsert_trip_evidence(
            trip_id=self.trip.trip_id,
            kind="accommodation_base",
            value=far_away,
            provider="test",
            retrieved_at="2026-08-14T00:00:00+00:00",
            expires_at="2036-08-14T00:00:00+00:00",
        )

        snapshot = self.actions._optimizer_input(self.trip.trip_id)
        ids = {item["id"] for item in snapshot["candidates"]}

        self.assertIn(
            "ACCOMMODATION_BASE_IMPLAUSIBLE", snapshot["trip"]["capability_gaps"]
        )
        self.assertNotIn("booked_accommodation_base", ids)
        self.assertIn("provisional_accommodation_base", ids)

    def test_a_base_inside_the_city_is_left_alone(self) -> None:
        """The negative case: the guard must not drop a real hotel."""

        self.actions.confirm_accommodation_base(self.trip.trip_id, "Test Hotel")
        snapshot = self.actions._optimizer_input(self.trip.trip_id)

        self.assertNotIn(
            "ACCOMMODATION_BASE_IMPLAUSIBLE", snapshot["trip"]["capability_gaps"]
        )
        self.assertIn(
            "booked_accommodation_base",
            {item["id"] for item in snapshot["candidates"]},
        )

    def test_a_booked_base_replaces_the_hypothesis_and_routes_from_it(self) -> None:
        saved = self.actions.confirm_accommodation_base(
            self.trip.trip_id, "Test Hotel"
        )
        self.actions.refresh_routes(self.trip.trip_id, force=True)
        snapshot = self.actions._optimizer_input(self.trip.trip_id)

        self.assertEqual("Test Hotel", saved["name"])
        self.assertEqual("booked", snapshot["trip"]["accommodation_status"])
        self.assertNotIn(
            "ACCOMMODATION_BASE_UNCONFIRMED", snapshot["trip"]["capability_gaps"]
        )
        self.assertNotIn(
            "provisional_accommodation_base",
            {item["id"] for item in snapshot["candidates"]},
        )
        self.assertIn(
            "booked_accommodation_base",
            {item["id"] for item in snapshot["candidates"]},
        )
        self.assertTrue(
            any(
                "booked_accommodation_base"
                in {route["origin_id"], route["destination_id"]}
                for route in snapshot["routes"]
            )
        )
        self.assertFalse(
            any(
                "provisional_accommodation_base"
                in {route["origin_id"], route["destination_id"]}
                for route in snapshot["routes"]
            )
        )
        proposal = self.actions.generate_plan_preview(self.trip.trip_id).proposal.as_dict()
        self.assertEqual(
            "booked_accommodation",
            proposal["variants"][0]["hotel_recommendation"]["basis"],
        )


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


class AcceptedRouteEstimateTest(unittest.TestCase):
    """A straight line the owner asked for, and it may only ever over-state the walk.

    `ROUTE_UNVERIFIED` is fatal by design, and the free routers do not always answer —
    OpenRouteService rate-limits, and some pairs it will not route at all. The owner was
    left with "drop the place" as the only way past it. This is the other way, and the
    direction of the error is the whole reason it is allowed: an optimistic guess makes a
    plan that cannot be walked, while a pessimistic one makes a plan with slack in it.
    """

    def test_the_estimate_is_never_shorter_than_the_straight_line(self) -> None:
        from travel_planner.actions import _distance_metres
        from travel_planner.transit import WALK_METRES_PER_MINUTE

        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        actions = PlannerActions(Path(directory.name) / "estimates.sqlite3")
        # Walkable on purpose. These were ~5 km apart, which the walk ceiling now
        # refuses outright — see `test_a_walk_no_one_would_take_is_not_estimated_at_all`
        # below. What this test is about is the *direction* of the error, so the pair only
        # has to be one the app would still offer.
        left = {"id": "a", "latitude": 25.0330, "longitude": 121.5654}
        right = {"id": "b", "latitude": 25.0400, "longitude": 121.5600}
        made = actions._accepted_route_estimates([left, right], [])

        straight = _distance_metres(left, right)
        for leg in made:
            self.assertGreater(leg["distance_metres"], straight)
            self.assertEqual("accepted_estimate", leg["status"])
            self.assertEqual("owner_accepted_straight_line", leg["basis"])
            # And the minutes agree with the distance it claims.
            self.assertAlmostEqual(
                leg["duration_minutes"],
                round(leg["distance_metres"] / WALK_METRES_PER_MINUTE, 1),
                places=1,
            )
        # Both directions, because the optimizer asks for ordered pairs.
        self.assertEqual({("a", "b"), ("b", "a")},
                         {(leg["origin_id"], leg["destination_id"]) for leg in made})

    def test_a_walk_no_one_would_take_is_not_estimated_at_all(self) -> None:
        """The leg the owner reported as "definitely wrong".

        Their itinerary carried "walk 19,951 metres, 240 minutes" from Shinjuku to a house
        in Shibamata that is reachable by rail. This path generated it: with no router
        answer for the pair, it fabricated a pessimistic straight line of any length, and
        the owner had agreed to *a pessimistic estimate where no router would answer* —
        not to walking across a city.

        `optimizer._routes_between` would drop it now anyway, but generating it is worse
        than useless: it lands in the frozen snapshot, in the exports, and in front of the
        owner as though it were a choice they had made. Leaving the pair unrouted is the
        honest result — the place stays `ROUTE_UNVERIFIED` and the screen recommends
        removing it, which is true where a four-hour walk is not.
        """

        from travel_planner.actions import MAX_USABLE_WALK_MINUTES

        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        actions = PlannerActions(Path(directory.name) / "far.sqlite3")
        # Shinjuku to Shibamata, the pair from the report: about 19 km apart.
        near = {"id": "shinjuku", "latitude": 35.6896, "longitude": 139.7006}
        far = {"id": "shibamata", "latitude": 35.7566, "longitude": 139.8697}

        self.assertEqual([], actions._accepted_route_estimates([near, far], []))

        # And the boundary is the ceiling rather than an arbitrary distance: a pair just
        # inside it is still offered.
        from travel_planner.transit import WALK_METRES_PER_MINUTE

        close = {
            "id": "close",
            "latitude": 35.6896,
            # Roughly half the ceiling's walking distance away, before the detour factor.
            "longitude": 139.7006 + 0.012,
        }
        offered = actions._accepted_route_estimates([near, close], [])
        self.assertTrue(offered)
        for leg in offered:
            self.assertLessEqual(
                leg["duration_minutes"], MAX_USABLE_WALK_MINUTES,
                "an offered estimate must be inside the ceiling",
            )

    def test_a_pair_that_already_has_a_route_is_left_alone(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        actions = PlannerActions(Path(directory.name) / "estimates.sqlite3")
        left = {"id": "a", "latitude": 25.03, "longitude": 121.56}
        right = {"id": "b", "latitude": 25.04, "longitude": 121.555}
        held = [{"origin_id": "a", "destination_id": "b"}]

        made = actions._accepted_route_estimates([left, right], held)

        self.assertEqual([("b", "a")],
                         [(leg["origin_id"], leg["destination_id"]) for leg in made])
