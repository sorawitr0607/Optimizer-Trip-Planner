"""Weekly opening periods to the per-date interval the optimizer can use.

Pure: no Streamlit, SQLite, provider, exporter, or model imports.

The optimizer's fact model carries one opening interval per place, with no date.
So a weekly schedule is reduced to the interval that holds on *every* trip date,
which is the only interval a date-less fact can honestly assert. When the place
is closed on a trip date, or the daily windows do not overlap, no verified fact
is emitted: the place stays unverified rather than being scheduled into a closed
day.

ponytail: per-date opening facts need the optimizer's fact model to carry an
applicable date. Until it does, the conservative intersection is the honest
reduction.
"""

from __future__ import annotations

from datetime import date
from typing import Any


def google_day(value: str) -> int:
    """Google Places numbers days from Sunday; Python's isoweekday from Monday."""

    return date.fromisoformat(value).isoweekday() % 7


def intervals_by_date(
    weekly_periods: list[dict[str, Any]], local_dates: list[str]
) -> dict[str, list[dict[str, str]]]:
    """The open windows on each trip date, empty where the place is closed."""

    by_day: dict[int, list[dict[str, str]]] = {}
    for period in weekly_periods:
        by_day.setdefault(int(period["day"]), []).append(
            {"start": str(period["start"]), "end": str(period["end"])}
        )
    return {
        local_date: sorted(
            by_day.get(google_day(local_date), []), key=lambda item: item["start"]
        )
        for local_date in local_dates
    }


def common_interval(
    weekly_periods: list[dict[str, Any]], local_dates: list[str]
) -> dict[str, Any]:
    """Reduce a weekly schedule to one interval valid on every trip date."""

    if not local_dates:
        return {
            "interval": None,
            "reason": "NO_TRIP_DATES",
            "by_date": {},
            "closed_dates": [],
        }
    by_date = intervals_by_date(weekly_periods, local_dates)
    closed = sorted(local_date for local_date, windows in by_date.items() if not windows)
    if closed:
        return {
            "interval": None,
            "reason": "CLOSED_ON_A_TRIP_DATE",
            "by_date": by_date,
            "closed_dates": closed,
        }
    # Widest window per date, then the overlap across dates.
    starts, ends = [], []
    for windows in by_date.values():
        starts.append(min(window["start"] for window in windows))
        ends.append(max(window["end"] for window in windows))
    start, end = max(starts), min(ends)
    if start >= end:
        return {
            "interval": None,
            "reason": "NO_WINDOW_COMMON_TO_EVERY_DATE",
            "by_date": by_date,
            "closed_dates": [],
        }
    return {
        "interval": {"start": start, "end": end},
        "reason": None,
        "by_date": by_date,
        "closed_dates": [],
    }
