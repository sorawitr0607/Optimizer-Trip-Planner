"""Stable, city-independent setup taxonomy and validation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, time
from typing import Any


# Every tag here has to be *produced* by something. `ranking.CATEGORY_TAGS` maps the
# categories discovery actually returns onto these codes, so a tag no category maps to
# is a control that cannot change an answer -- and two of the avoid tags below are
# already in that position. The five added on 2026-08-20 each name a distinction the
# catalogue can already make: art against culture generally, history against the same,
# viewpoints against sightseeing at large, water against nature, and the family-facing
# places (theme parks, zoos, aquaria) which were reachable only through "activity".
MAIN_STYLE_TAGS = (
    "sightseeing",
    "culture",
    "art",
    "history",
    "nature",
    "views",
    "water",
    "activity",
    "family",
    "shopping",
    "chill",
)
ALSO_ENJOY_TAGS = (
    "local_street_food",
    "photography",
    "night_view",
    "markets",
    "architecture",
    "neighborhoods",
    "parks_gardens",
    "animals",
    "performing_arts",
    "religious_sites",
    "theme_parks",
    "malls",
    "wellness",
)
# Each of these has to reach the optimizer, and until 2026-08-20 two of them did not:
# `late_meals` and `heavy_crowds` were offered and read by nothing. They are wired now
# -- `late_meals` through the meal window the plan already carries, `heavy_crowds`
# through the crowd tolerance and boarding buffer the Shanghai ferry regression
# records. `long_queues` is added on the same condition, using the
# `queue_wait_minutes` fact that was previously consulted for meals alone.
AVOID_TAGS = (
    "tourist_traps",
    "plain_long_walks",
    "late_meals",
    "heavy_crowds",
    "long_queues",
)
COMFORT_TAGS = (
    "balanced_pace",
    "rewarding_walks",
    "meal_on_time",
    "rest_breaks",
    "low_walking",
)
ALL_PREFERENCE_TAGS = frozenset(
    MAIN_STYLE_TAGS + ALSO_ENJOY_TAGS + AVOID_TAGS + COMFORT_TAGS
)
# Two answers, at the owner's asking: a stay is booked or it is not. `unknown` was a third
# that the optimizer could not act on — `_optimizer_input` collapses everything that is not
# `booked` into `unbooked`, so it planned identically to `not_booked` while asking the owner
# to distinguish it. A question whose answers do not differ is a question worth deleting.
ACCOMMODATION_STATUSES = frozenset({"not_booked", "booked"})

# What a draft written before that change says. Folded rather than rejected: a setup is
# re-validated on every save, so refusing the old value would strand any trip holding it
# behind a form that cannot be submitted.
LEGACY_ACCOMMODATION_STATUSES = {"unknown": "not_booked"}


def normalise_accommodation_status(status: str) -> str:
    """The stored value, in today's vocabulary."""

    return LEGACY_ACCOMMODATION_STATUSES.get(status, status)


def build_setup_payload(
    *,
    planning_mode: str,
    owner_age: int | None,
    main_style: Iterable[str],
    also_enjoy: Iterable[str] = (),
    avoid: Iterable[str] = (),
    comfort: Iterable[str] = (),
    owner_description: str = "",
    owner_must_respect: Iterable[str] | str = (),
    owner_nationality: str | None = None,
    travellers: Sequence[Mapping[str, Any]] = (),
    start_date: str | None = None,
    end_date: str | None = None,
    arrival_time: str | None = None,
    departure_time: str | None = None,
    accommodation_status: str = "not_booked",
    confirmed: bool = False,
) -> dict[str, Any]:
    if planning_mode not in {"explore_first", "ready_to_schedule"}:
        raise ValueError(f"Unsupported planning mode: {planning_mode}")
    styles = _tags(main_style)
    if confirmed and not styles:
        raise ValueError("At least one main style is required before confirmation")
    accommodation_status = normalise_accommodation_status(accommodation_status)
    if accommodation_status not in ACCOMMODATION_STATUSES:
        raise ValueError(f"Unsupported accommodation status: {accommodation_status}")

    start = _date_text(start_date, "start_date")
    end = _date_text(end_date, "end_date")
    if start and end and end < start:
        raise ValueError("end_date cannot be before start_date")

    members = [
        {
            "traveller_id": str(item.get("traveller_id") or f"member_{index + 1}"),
            "label": str(item.get("label") or f"Traveller {index + 1}").strip(),
            "age": _age(item.get("age")),
            "tags": _tags(item.get("tags", ())),
            "description": str(item.get("description") or "").strip(),
            "must_respect": _text_list(item.get("must_respect", ())),
            # Readiness generation needs nationality; passport numbers stay out.
            "nationality": _nationality(item.get("nationality")),
        }
        for index, item in enumerate(travellers)
    ]
    member_ids = [member["traveller_id"] for member in members]
    if len(member_ids) != len(set(member_ids)):
        raise ValueError("traveller_id values must be unique")
    owner_weight = 0.5 if members else 1.0
    group_weights = {"owner": owner_weight}
    if members:
        member_weight = (1.0 - owner_weight) / len(members)
        group_weights.update({member["traveller_id"]: member_weight for member in members})

    return {
        "schema_version": 1,
        "planning_mode": planning_mode,
        "trip_basics": {
            "start_date": start,
            "end_date": end,
            "arrival_time": _time_text(arrival_time, "arrival_time"),
            "departure_time": _time_text(departure_time, "departure_time"),
            "accommodation_status": accommodation_status,
        },
        "owner": {
            "age": _age(owner_age),
            "main_style": styles,
            "also_enjoy": _tags(also_enjoy),
            "avoid": _tags(avoid),
            "comfort": _tags(comfort),
            "description": owner_description.strip(),
            "must_respect": _text_list(owner_must_respect),
            "nationality": _nationality(owner_nationality),
        },
        "travellers": members,
        "group_preference_weights": group_weights,
    }


def _tags(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        tag = str(value).strip()
        if tag not in ALL_PREFERENCE_TAGS:
            raise ValueError(f"Unsupported preference tag: {tag}")
        if tag not in result:
            result.append(tag)
    return result


def _nationality(value: Any) -> str | None:
    text = str(value or "").strip()
    if len(text) > 60:
        raise ValueError("nationality must be 60 characters or fewer")
    return text or None


def _text_list(values: Iterable[str] | str) -> list[str]:
    if isinstance(values, str):
        values = values.splitlines()
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _age(value: Any) -> int | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, bool):
        raise ValueError("age must be a number")
    age = int(value)
    if age < 1 or age > 120:
        raise ValueError("age must be between 1 and 120")
    return age


def _date_text(value: str | None, field: str) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"{field} must use YYYY-MM-DD") from error


def _time_text(value: str | None, field: str) -> str | None:
    if not value:
        return None
    try:
        return time.fromisoformat(value).strftime("%H:%M")
    except ValueError as error:
        raise ValueError(f"{field} must use HH:MM") from error
