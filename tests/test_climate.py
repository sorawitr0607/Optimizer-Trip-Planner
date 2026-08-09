from __future__ import annotations

import unittest

from pathlib import Path
from tempfile import TemporaryDirectory

from travel_planner import climate
from travel_planner.actions import PlannerActions, PlannerRefusal
from travel_planner.providers import _google_public_holidays


def series(highs_by_month: dict[int, float], *, wet_days: dict[int, int] | None = None):
    """A year of daily readings with one flat high per month."""

    wet_days = wet_days or {}
    time, high, low, rain = [], [], [], []
    for month, value in highs_by_month.items():
        for day in range(1, 29):
            time.append(f"2024-{month:02d}-{day:02d}")
            high.append(value)
            low.append(value - 8)
            rain.append(5.0 if day <= wet_days.get(month, 0) else 0.0)
    return {
        "time": time,
        "temperature_2m_max": high,
        "temperature_2m_min": low,
        "precipitation_sum": rain,
    }


class MonthlyNormalsTest(unittest.TestCase):
    def test_a_missing_reading_is_skipped_not_counted_as_zero(self) -> None:
        """Averaging a gap as 0°C invents a temperature that was never recorded."""

        daily = {
            "time": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "temperature_2m_max": [10.0, None, 12.0],
            "temperature_2m_min": [2.0, None, 4.0],
            "precipitation_sum": [0.0, None, 0.0],
        }

        months = climate.monthly_normals(daily)

        self.assertEqual(1, len(months))
        self.assertEqual(11.0, months[0]["mean_high_c"])

    def test_only_rain_over_the_threshold_counts_as_a_wet_day(self) -> None:
        # Drizzle does not change a plan; 1mm does.
        daily = {
            "time": ["2024-05-01", "2024-05-02", "2024-05-03", "2024-05-04"],
            "temperature_2m_max": [20.0] * 4,
            "temperature_2m_min": [12.0] * 4,
            "precipitation_sum": [0.0, 0.2, 1.0, 8.0],
        }

        months = climate.monthly_normals(daily)

        self.assertEqual(50.0, months[0]["wet_day_percent"])


class MonthRankingTest(unittest.TestCase):
    def test_bands_are_relative_to_the_destination(self) -> None:
        """Taipei's coolest month is warmer than Seoul's warmest.

        A global comfort threshold would call one city uniformly bad and the other
        uniformly fine, which answers a question nobody asked. Every destination gets a
        best month and a worst month because that is what "when should I go" means.
        """

        tropical = {month: 30.0 + month * 0.2 for month in range(1, 13)}
        months = climate.monthly_normals(series(tropical))

        ranked = climate.rank_months(months, holiday_source="test")
        bands = {row["month"]: row["band"] for row in ranked}

        self.assertEqual(climate.BEST_MONTHS, sum(1 for b in bands.values() if b == "best"))
        self.assertEqual(climate.WORST_MONTHS, sum(1 for b in bands.values() if b == "avoid"))
        # Coolest months win in a city that is hot all year.
        self.assertEqual("best", bands[1])
        self.assertEqual("avoid", bands[12])

    def test_every_month_is_returned_so_none_is_taken_off_the_table(self) -> None:
        # The owner asked to still be able to choose any month. A recommendation that
        # removes the choice is a decision taken on their behalf.
        months = climate.monthly_normals(series({m: 20.0 for m in range(1, 13)}))

        ranked = climate.rank_months(months, holiday_source="test")

        self.assertEqual(list(range(1, 13)), [row["month"] for row in ranked])

    def test_a_long_holiday_is_a_con_and_a_pro_at_once(self) -> None:
        """The owner's point: a national holiday fills the trains *and* is the only time
        the festival happens. Both are said and neither is netted away — which of them
        outweighs the other is the owner's call, not the app's."""

        months = climate.monthly_normals(series({9: 22.0}))
        holidays = climate.holiday_months(
            [
                {"date": "2026-09-24", "name": "Chuseok"},
                {"date": "2026-09-25", "name": "Chuseok"},
                {"date": "2026-09-26", "name": "Chuseok"},
            ]
        )

        ranked = climate.rank_months(months, holidays=holidays, holiday_source="test")
        row = ranked[0]

        self.assertIn("month_crowded", [item["code"] for item in row["cons"]])
        self.assertIn("month_festival", [item["code"] for item in row["pros"]])
        self.assertIn("month_advice_crowds", [item["code"] for item in row["advice"]])
        self.assertEqual(3, row["longest_holiday_run"])

    def test_a_hot_month_carries_advice_for_surviving_it(self) -> None:
        # "Difficult for open-area, but can still travel indoor and rest every hour."
        months = climate.monthly_normals(series({7: 34.0}, wet_days={7: 20}))

        row = climate.rank_months(months, holiday_source="test")[0]

        self.assertIn("month_too_hot", [item["code"] for item in row["cons"]])
        self.assertIn("month_advice_heat", [item["code"] for item in row["advice"]])
        self.assertIn("month_advice_rain", [item["code"] for item in row["advice"]])

    def test_an_uncovered_country_says_so_rather_than_reading_as_quiet(self) -> None:
        """Taiwan and Thailand are both absent from the holiday source. A silent zero
        would read as "no local holidays that month", which is a claim, not a gap."""

        months = climate.monthly_normals(series({4: 20.0}))

        row = climate.rank_months(months, holidays={}, holiday_source=None)[0]

        self.assertIn("month_crowding_unknown", [item["code"] for item in row["cons"]])
        self.assertNotIn("month_quiet", [item["code"] for item in row["pros"]])

    def test_a_covered_country_with_no_holidays_that_month_is_quiet(self) -> None:
        # The other side of the same distinction: source present, month genuinely clear.
        months = climate.monthly_normals(series({4: 20.0}))

        row = climate.rank_months(months, holidays={}, holiday_source="test")[0]

        self.assertIn("month_quiet", [item["code"] for item in row["pros"]])
        self.assertNotIn("month_crowding_unknown", [item["code"] for item in row["cons"]])


class HolidayRunTest(unittest.TestCase):
    def test_consecutive_days_are_one_run_and_separate_days_are_not(self) -> None:
        grouped = climate.holiday_months(
            [
                {"date": "2026-02-16", "name": "Lunar New Year"},
                {"date": "2026-02-17", "name": "Lunar New Year"},
                {"date": "2026-02-18", "name": "Lunar New Year"},
                {"date": "2026-02-28", "name": "Something Else"},
            ]
        )

        self.assertEqual(4, grouped[2]["days"])
        self.assertEqual(3, grouped[2]["longest_run"])

    def test_a_single_day_holiday_is_not_a_long_holiday(self) -> None:
        grouped = climate.holiday_months([{"date": "2026-05-05", "name": "Children's Day"}])

        self.assertEqual(1, grouped[5]["longest_run"])
        self.assertLess(grouped[5]["longest_run"], climate.LONG_HOLIDAY_DAYS)


class BestWindowTest(unittest.TestCase):
    """The month says roughly when; this says which days. Same holiday data, no further
    request — a public holiday costs a full point and a weekend day half of one, because
    both fill the same trains and a national holiday empties the offices too."""

    LNY = [{"date": f"2027-02-{day:02d}"} for day in range(15, 22)]

    def test_it_steps_around_a_long_holiday_entirely(self) -> None:
        window = climate.best_window(2027, 2, 5, holidays=self.LNY)

        self.assertEqual(0, window["holiday_days"])
        self.assertNotIn(window["start"][:10], [h["date"] for h in self.LNY])

    def test_weekends_are_avoided_where_holidays_allow(self) -> None:
        # April 2027 has no public holidays in this fixture, so the only thing left to
        # optimise is the weekend, and a weekday-only run exists.
        window = climate.best_window(2027, 4, 5, holidays=[])

        self.assertEqual(0, window["weekend_days"])

    def test_a_trip_longer_than_the_month_gets_no_answer(self) -> None:
        # A window spilling into the next month would be scored against holidays this
        # function was never given, so `None` beats a confident wrong range.
        self.assertIsNone(climate.best_window(2027, 2, 31, holidays=[]))

    def test_ties_resolve_to_the_earliest_window(self) -> None:
        # Stability matters more than which equal answer wins: re-opening the screen
        # must not show different dates.
        first = climate.best_window(2027, 4, 3, holidays=[])
        again = climate.best_window(2027, 4, 3, holidays=[])

        self.assertEqual(first["start"], again["start"])

    def test_the_reasons_say_which_it_avoided(self) -> None:
        clear = climate.best_window(2027, 2, 5, holidays=self.LNY)
        codes = [item["code"] for item in clear["reasons"]]

        self.assertIn("window_clear_of_holidays", codes)
        self.assertIn("window_weekend_days", codes)


class GoogleCalendarHolidayTest(unittest.TestCase):
    """Nager\'s own coverage page puts Asia at 38% and depends on community
    contributions, so Taiwan, Thailand, Malaysia, India and the UAE were all missing --
    the pilot destination among them. Google\'s holiday calendars are free, keyless and
    cover every one of them."""

    ICS = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20260217\r\n"
        "SUMMARY:Lunar New Year\'s Day\r\nDESCRIPTION:Public holiday\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20260308\r\n"
        "SUMMARY:International Women\'s Day\r\n"
        "DESCRIPTION:Observance\\nTo hide observances\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20250217\r\n"
        "SUMMARY:Last year\r\nDESCRIPTION:Public holiday\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    def test_an_observance_is_not_a_public_holiday(self) -> None:
        # The feed carries both -- Taiwan\'s has 213 public holidays and 117 observances.
        # Counting International Women\'s Day as a reason the trains are full would
        # invent a crowd out of a day nobody takes off.
        found = _google_public_holidays(self.ICS, 2026)

        self.assertEqual(["2026-02-17"], [item["date"] for item in found])
        self.assertEqual("Lunar New Year\'s Day", found[0]["name"])

    def test_only_the_asked_year_is_returned(self) -> None:
        # One feed carries several years; counting them all would multiply every month.
        self.assertEqual([], [x for x in _google_public_holidays(self.ICS, 2024)])
        self.assertEqual(1, len(_google_public_holidays(self.ICS, 2025)))

    def test_a_folded_line_is_rejoined_before_it_is_read(self) -> None:
        # RFC 5545 splits a long line with a leading space. Unread, the continuation
        # looks like a new property and the event loses its name.
        ics = (
            "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20260401\r\n"
            "SUMMARY:Children\'s Day and Tomb Sweep\r\n ing Day\r\n"
            "DESCRIPTION:Public holiday\r\nEND:VEVENT\r\n"
        )

        found = _google_public_holidays(ics, 2026)

        self.assertEqual("Children\'s Day and Tomb Sweeping Day", found[0]["name"])


class FakeClimateProvider:
    """Records what it was asked, so the coordinator's own decisions are visible."""

    name = "openmeteo"
    operation = "openmeteo:climate"
    holiday_operation = "nager:holidays"
    kind = "travel_months"
    cache_version = "climate-test"
    cache_ttl_days = 120
    google_calendars = {"Taiwan": "en.taiwan"}

    def __init__(self, holidays=None):
        self.archive_calls: list[tuple[float, float]] = []
        self.holiday_calls: list[tuple[str, int]] = []
        self._holidays = holidays

    def daily_archive(self, latitude, longitude, *, end_year):
        self.archive_calls.append((round(latitude, 3), round(longitude, 3)))
        return {
            "daily": series({month: 15.0 + month for month in range(1, 13)}),
            "from": f"{end_year - 4}-01-01",
            "to": f"{end_year}-12-31",
        }

    def holidays(self, country, year):
        self.holiday_calls.append((country, year))
        return self._holidays


class MonthGuideActionsTest(unittest.TestCase):
    """The coordinator, which the pure-module tests do not reach: where the
    coordinates come from, what is cached, and which source gets the credit."""

    def _trip(self, directory, destination="Taipei, Taiwan"):
        actions = PlannerActions(Path(directory) / "guide.sqlite3", climate_provider=self.provider)
        trip = actions.create_trip(name="T", destination=destination)
        return actions, trip

    def setUp(self) -> None:
        self.provider = FakeClimateProvider(holidays=[{"date": "2027-02-17", "name": "Lunar New Year"}])

    def test_it_refuses_before_discovery_rather_than_guessing_a_city(self) -> None:
        # The coordinates come from the discovery run's own searched window. Without
        # one there is nothing to centre on, and geocoding a name again here would be a
        # second opinion about where the trip is.
        with TemporaryDirectory() as directory:
            actions, trip = self._trip(directory)

            with self.assertRaises(PlannerRefusal) as raised:
                actions.travel_month_guide(trip.trip_id)

            self.assertEqual("discovery_required_for_climate", str(raised.exception))
            self.assertEqual([], self.provider.archive_calls)

    def _with_discovery(self, actions, trip, boundary):
        actions.save_setup(trip_id=trip.trip_id, main_style=["culture"], confirmed=True)
        from travel_planner.core import new_discovery_run
        setup = actions.get_setup(trip.trip_id)
        actions.store.add_discovery_run(
            new_discovery_run(
                trip_id=trip.trip_id,
                setup_sha256=setup.snapshot.sha256,
                provider="test",
                status="verified",
                candidates={"candidates": []},
                report={"query_boundary": boundary},
            )
        )

    def test_the_centre_of_the_searched_window_is_what_gets_asked_about(self) -> None:
        with TemporaryDirectory() as directory:
            actions, trip = self._trip(directory)
            self._with_discovery(actions, trip, [24.9, 121.4, 25.2, 121.7])

            actions.travel_month_guide(trip.trip_id)

            # Midpoint of (south, west, north, east), not a corner.
            self.assertEqual([(25.05, 121.55)], self.provider.archive_calls)

    def test_a_second_read_is_served_from_cache_and_asks_nothing(self) -> None:
        # Normals move over decades and holidays are published a year ahead, so this
        # must not be a request per visit to a screen anyone with no dates reaches.
        with TemporaryDirectory() as directory:
            actions, trip = self._trip(directory)
            self._with_discovery(actions, trip, [24.9, 121.4, 25.2, 121.7])

            first = actions.travel_month_guide(trip.trip_id)
            second = actions.travel_month_guide(trip.trip_id)

            self.assertEqual(first["months"], second["months"])
            self.assertEqual(1, len(self.provider.archive_calls))
            self.assertEqual(1, len(self.provider.holiday_calls))

    def test_a_city_only_destination_still_resolves_its_country(self) -> None:
        # Every trip made before the country/city picker holds a bare city, and passing
        # "Taipei" on as a country found nothing -- reporting a covered country as
        # having no published holidays.
        with TemporaryDirectory() as directory:
            actions, trip = self._trip(directory, destination="Taipei")
            self._with_discovery(actions, trip, [24.9, 121.4, 25.2, 121.7])

            guide = actions.travel_month_guide(trip.trip_id)

            self.assertEqual("Taiwan", guide["country"])
            self.assertEqual("Taiwan", self.provider.holiday_calls[0][0])

    def test_the_source_named_is_the_one_that_answered(self) -> None:
        # Taiwan comes from Google's calendar, not Nager. Crediting the wrong one makes
        # a future gap untraceable.
        with TemporaryDirectory() as directory:
            actions, trip = self._trip(directory)
            self._with_discovery(actions, trip, [24.9, 121.4, 25.2, 121.7])

            guide = actions.travel_month_guide(trip.trip_id)

            self.assertEqual("google.calendar", guide["holiday_source"])

    def test_an_uncovered_country_reports_no_source_at_all(self) -> None:
        with TemporaryDirectory() as directory:
            self.provider = FakeClimateProvider(holidays=None)
            actions, trip = self._trip(directory, destination="Nowhere City")
            self._with_discovery(actions, trip, [24.9, 121.4, 25.2, 121.7])

            guide = actions.travel_month_guide(trip.trip_id)

            self.assertIsNone(guide["holiday_source"])
            crowding = [
                item["code"] for row in guide["months"] for item in row["cons"]
            ]
            self.assertIn("month_crowding_unknown", crowding)

    def test_both_free_calls_are_recorded_at_zero(self) -> None:
        # Every provider call routes through `_spend`; an unpriced one raises. Recorded
        # at zero so call counts stay reconcilable against the paid operations.
        with TemporaryDirectory() as directory:
            actions, trip = self._trip(directory)
            self._with_discovery(actions, trip, [24.9, 121.4, 25.2, 121.7])

            actions.travel_month_guide(trip.trip_id)

            usage = actions.paid_usage_status()
            self.assertEqual(0.0, usage["estimated_usd"])
            self.assertEqual(1, usage["by_operation"]["openmeteo:climate"]["requests"])
            self.assertEqual(1, usage["by_operation"]["nager:holidays"]["requests"])


if __name__ == "__main__":
    unittest.main()
