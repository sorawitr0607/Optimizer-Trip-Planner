"""When to go, from measured weather and local holidays.

Pure and language-neutral like the rest of the planning core: no HTTP, no SQLite, no
copy. It takes a daily observation series and a holiday list and returns a judgement
per month as **stable codes with numbers attached**, which the views render.

Why this exists as data rather than as recall: the owner asked for a recommended month
with reasons, and a model will happily say "March is best, it is cherry blossom season"
for a city it has never checked. That is exactly the failure `WF-044` and `WF-046` were
written to prevent. Open-Meteo's archive is free, needs no key, and answers from
observations, so "best" can mean something a person can check and disagree with — every
number behind a verdict is returned with it.

**A judgement is relative to the destination, never absolute.** Taipei's coolest month
is warmer than Seoul's warmest, and a global comfort threshold would call one city
uniformly bad and the other uniformly fine. The bands rank a city's twelve months
against each other, so every destination has a best month and a worst month — which is
the question actually being asked.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence


# The band a daytime high is comfortable to walk a city in. Wider than a "nice day"
# because this is sightseeing in whatever the traveller packed, not sunbathing.
COMFORT_LOW_C = 18.0
COMFORT_HIGH_C = 26.0
# One point of score per degree outside the band, times this. Temperature dominates
# rain because a downpour ends and a heatwave does not.
DEGREE_WEIGHT = 3.0
# Per percentage point of days with 1mm or more of rain.
WET_DAY_WEIGHT = 0.8
# A day with 1mm is a day you notice; below that is drizzle that does not change plans.
WET_DAY_MM = 1.0

# Crowding from local public holidays. The owner asked for this to count: a long
# domestic holiday fills the trains, books out the hotels and shuts family businesses,
# which is felt by a visitor whatever the weather is doing.
HOLIDAY_DAY_PENALTY = 2.0
# A run of this many consecutive days off, weekends included, is a *long* holiday --
# the kind whole families travel on, not a single day off.
LONG_HOLIDAY_DAYS = 3
LONG_HOLIDAY_PENALTY = 12.0

# How many of the twelve months fall in each band. Three and three leaves six in the
# middle, which is honest: most months of most cities are simply fine.
BEST_MONTHS = 3
WORST_MONTHS = 3


def monthly_normals(daily: Mapping[str, Sequence[Any]]) -> list[dict[str, Any]]:
    """Average a daily observation series into twelve months.

    `daily` is Open-Meteo's shape: parallel lists of ISO dates, daily maxima, daily
    minima and daily precipitation totals. A missing reading is skipped rather than
    counted as zero, which would drag an average toward a temperature never recorded.
    """

    dates = list(daily.get("time") or [])
    highs = list(daily.get("temperature_2m_max") or [])
    lows = list(daily.get("temperature_2m_min") or [])
    rain = list(daily.get("precipitation_sum") or [])
    buckets: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"highs": [], "lows": [], "wet": 0, "days": 0}
    )
    for index, stamp in enumerate(dates):
        try:
            month = int(str(stamp)[5:7])
        except (TypeError, ValueError):
            continue
        if not 1 <= month <= 12:
            continue
        bucket = buckets[month]
        high = highs[index] if index < len(highs) else None
        low = lows[index] if index < len(lows) else None
        fall = rain[index] if index < len(rain) else None
        if high is not None:
            bucket["highs"].append(float(high))
        if low is not None:
            bucket["lows"].append(float(low))
        bucket["days"] += 1
        if fall is not None and float(fall) >= WET_DAY_MM:
            bucket["wet"] += 1

    months: list[dict[str, Any]] = []
    for month in range(1, 13):
        bucket = buckets.get(month)
        if not bucket or not bucket["highs"]:
            continue
        months.append(
            {
                "month": month,
                "mean_high_c": round(sum(bucket["highs"]) / len(bucket["highs"]), 1),
                "mean_low_c": round(sum(bucket["lows"]) / len(bucket["lows"]), 1)
                if bucket["lows"]
                else None,
                "wet_day_percent": round(bucket["wet"] / bucket["days"] * 100, 1)
                if bucket["days"]
                else 0.0,
                "observed_days": bucket["days"],
            }
        )
    return months


def holiday_months(holidays: Iterable[Mapping[str, Any]]) -> dict[int, dict[str, Any]]:
    """Group dated public holidays by month, and find the long runs.

    A run is consecutive *calendar* days that are public holidays. It deliberately does
    not model weekends: whether 1 January falling on a Friday makes a four-day weekend
    depends on a working week this module is not told about, and guessing it would be
    inventing the very thing the owner would rely on.
    """

    by_month: dict[int, dict[str, Any]] = {}
    dated = sorted(
        {str(item.get("date") or "") for item in holidays if item.get("date")}
    )
    names: dict[str, str] = {}
    for item in holidays:
        date = str(item.get("date") or "")
        if date:
            names.setdefault(date, str(item.get("name") or item.get("localName") or ""))

    run: list[str] = []
    runs: list[list[str]] = []
    for date in dated:
        if run and _is_next_day(run[-1], date):
            run.append(date)
        else:
            if run:
                runs.append(run)
            run = [date]
    if run:
        runs.append(run)

    for date in dated:
        month = int(date[5:7])
        entry = by_month.setdefault(month, {"days": 0, "names": [], "longest_run": 0})
        entry["days"] += 1
        name = names.get(date, "")
        if name and name not in entry["names"]:
            entry["names"].append(name)
    for stretch in runs:
        month = int(stretch[0][5:7])
        entry = by_month.setdefault(month, {"days": 0, "names": [], "longest_run": 0})
        entry["longest_run"] = max(entry["longest_run"], len(stretch))
    return by_month


def _is_next_day(earlier: str, later: str) -> bool:
    from datetime import date, timedelta

    try:
        left = date.fromisoformat(earlier)
        right = date.fromisoformat(later)
    except ValueError:
        return False
    return right - left == timedelta(days=1)


def rank_months(
    months: Sequence[Mapping[str, Any]],
    *,
    holidays: Mapping[int, Mapping[str, Any]] | None = None,
    holiday_source: str | None = None,
) -> list[dict[str, Any]]:
    """Score and band each month, with the reason codes behind every verdict.

    Returns every month, always. The owner asked to still be able to choose any of
    them — a recommendation that removes the choice is a decision taken on their
    behalf, and they may be travelling on dates a school holiday decides.
    """

    holidays = holidays or {}
    scored: list[dict[str, Any]] = []
    for row in months:
        high = float(row["mean_high_c"])
        wet = float(row.get("wet_day_percent") or 0.0)
        miss_cold = max(0.0, COMFORT_LOW_C - high)
        miss_hot = max(0.0, high - COMFORT_HIGH_C)
        holiday = holidays.get(int(row["month"])) or {}
        holiday_days = int(holiday.get("days") or 0)
        longest_run = int(holiday.get("longest_run") or 0)

        penalty = (miss_cold + miss_hot) * DEGREE_WEIGHT + wet * WET_DAY_WEIGHT
        penalty += holiday_days * HOLIDAY_DAY_PENALTY
        if longest_run >= LONG_HOLIDAY_DAYS:
            penalty += LONG_HOLIDAY_PENALTY

        # Pros and cons, not a verdict. Every month is travellable and the trade is
        # what differs: August is hot and sweaty and hard on an open-air day, and it is
        # also when the festival happens and when an indoor afternoon is no hardship.
        # A month reduced to one number tells an owner what to pick; a month with both
        # columns tells them what they are choosing.
        pros: list[dict[str, Any]] = []
        cons: list[dict[str, Any]] = []
        advice: list[dict[str, Any]] = []

        if miss_cold > 0:
            cons.append({"code": "month_too_cold", "args": {"high": high}})
            advice.append({"code": "month_advice_cold", "args": {}})
        elif miss_hot > 0:
            cons.append({"code": "month_too_hot", "args": {"high": high}})
            advice.append({"code": "month_advice_heat", "args": {}})
        else:
            pros.append({"code": "month_comfortable", "args": {"high": high}})

        if wet >= 40:
            cons.append({"code": "month_wet", "args": {"wet": wet}})
            advice.append({"code": "month_advice_rain", "args": {}})
        else:
            pros.append({"code": "month_dry", "args": {"wet": wet}})

        # A national holiday counts on both sides and is listed on both. The crowd is
        # why the score drops; the festival is why an owner might accept that, and it
        # is genuinely unavailable in any other month. Which outweighs which is not the
        # app's call -- it reports, the same way `WF-047` prices both paths and
        # `WF-045` reports drift without repairing it.
        if longest_run >= LONG_HOLIDAY_DAYS:
            named = ", ".join(holiday["names"][:2])
            cons.append(
                {"code": "month_crowded", "args": {"days": longest_run, "names": named}}
            )
            pros.append({"code": "month_festival", "args": {"names": named}})
            advice.append({"code": "month_advice_crowds", "args": {}})
        elif holiday_days:
            pros.append(
                {
                    "code": "month_festival_days",
                    "args": {
                        "days": holiday_days,
                        "names": ", ".join(holiday.get("names") or [])[:60],
                    },
                }
            )
        elif holiday_source is None:
            # Said, not implied. Taiwan and Thailand are both absent from the holiday
            # source, and a silent zero would read as "no local holidays that month".
            cons.append({"code": "month_crowding_unknown", "args": {}})
        else:
            pros.append({"code": "month_quiet", "args": {}})

        scored.append(
            {
                **row,
                "score": round(100.0 - penalty, 1),
                "holiday_days": holiday_days,
                "longest_holiday_run": longest_run,
                "holiday_names": list(holiday.get("names") or []),
                "pros": pros,
                "cons": cons,
                "advice": advice,
            }
        )

    # Banded by rank within this destination, not against a global threshold.
    order = sorted(scored, key=lambda item: (-item["score"], item["month"]))
    for position, item in enumerate(order):
        if position < BEST_MONTHS:
            item["band"] = "best"
        elif position >= len(order) - WORST_MONTHS:
            item["band"] = "avoid"
        else:
            item["band"] = "fair"
    return sorted(scored, key=lambda item: item["month"])
