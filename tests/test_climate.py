from __future__ import annotations

import unittest

from travel_planner import climate
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


if __name__ == "__main__":
    unittest.main()
