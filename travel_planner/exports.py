"""One immutable export snapshot shared by every active-plan view and exporter.

Pure: no Streamlit, SQLite, provider, exporter, or model imports.  The in-app
timeline, daily poster, PDF, and Excel all read this snapshot, so their times,
totals, statuses, and warnings cannot diverge.
"""

from __future__ import annotations

from typing import Any

from .core import LANGUAGES


EXPORT_SCHEMA_VERSION = 1
BASE_CURRENCY = "THB"

CONFIRMED = "confirmed"
RECHECK = "recheck"
TRADEOFF_ACCEPTED = "tradeoff_accepted"
UNVERIFIED_CONFLICT = "unverified_conflict"
LOCKED = "locked"
# Worst first: a day summary surfaces its highest-risk item.
STATUS_RANK = (UNVERIFIED_CONFLICT, RECHECK, TRADEOFF_ACCEPTED, LOCKED, CONFIRMED)

READY = "ready"
ACTION_NEEDED = "action_needed"
VERIFICATION_NEEDED = "verification_needed"


def build_export_snapshot(
    *,
    trip: dict[str, Any],
    plan: dict[str, Any],
    version_id: str,
    active_version_id: str | None,
    language: str,
    exported_at: str,
    checklist_items: list[dict[str, Any]] | None = None,
    checklist_readiness: dict[str, Any] | None = None,
    cost_items: list[dict[str, Any]] | None = None,
    cost_totals: dict[str, Any] | None = None,
    rate_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the display-ready snapshot for one active plan version."""

    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    variant = plan.get("variant")
    planner_input = plan.get("optimizer_input")
    if not isinstance(variant, dict) or not isinstance(planner_input, dict):
        raise ValueError("Plan version does not carry an optimizer variant")
    context = {
        "language": language,
        "cards": {
            str(item.get("id")): item for item in planner_input.get("candidates", [])
        },
        "locked": {
            str(lock.get("subject_id") or lock.get("place_id"))
            for lock in planner_input.get("locks", [])
        },
        "tradeoff": {
            item["place_id"]
            for item in variant.get("reconciliation", [])
            if item["status"] == "fits_with_tradeoff"
        },
        "opening_verified": {
            fact["subject_id"]
            for fact in planner_input.get("facts", [])
            if fact.get("fact_type") == "opening_interval"
            and fact.get("status") == "verified"
        },
        "discovery_status": str(
            planner_input.get("source", {}).get("discovery_status") or "verified"
        ),
    }

    context["reconciliation_by_id"] = {
        item["place_id"]: item for item in variant.get("reconciliation", [])
    }
    days = [_day(day, context) for day in variant["days"]]
    fallbacks = _fallbacks(variant, days, context)
    board = [item for item in (checklist_items or []) if not item.get("dismissed")]
    for day in days:
        # A fallback belongs beneath the half-day its replacement lands in.
        day["fallbacks"] = [
            item for item in fallbacks if item["date"] == day["date"]
        ]
        # A poster shows only the tasks needed on its own day.
        day["tasks"] = [
            _task(item) for item in board if item.get("due_date") == day["date"]
        ]
    totals = _trip_totals(days)
    _reconcile_with_optimizer(totals, variant["metrics"])
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "stamp": {
            "trip_id": trip["trip_id"],
            "trip_name": trip["name"],
            "destination": trip["destination"],
            "plan_version_id": version_id,
            "is_active_plan": version_id == active_version_id,
            "variant_id": variant["variant_id"],
            "variant_status": variant["status"],
            "optimizer_version": plan["optimizer_version"],
            "input_sha256": plan["input_sha256"],
            "language": language,
            "base_currency": BASE_CURRENCY,
            "exported_at": exported_at,
            "timezone": planner_input["trip"].get("timezone"),
            "capability_gaps": sorted(planner_input["trip"].get("capability_gaps", [])),
            "discovery_status": context["discovery_status"],
        },
        "readiness": _readiness(variant, planner_input),
        "days": days,
        "totals": totals,
        "reconciliation": [
            {
                **item,
                "display_name": display_name(
                    item.get("names"), item.get("name"), language
                ),
            }
            for item in variant.get("reconciliation", [])
        ],
        "unscheduled": [
            {
                "place_id": item["place_id"],
                "display_name": display_name(
                    item.get("names"), item.get("name"), language
                ),
                "priority": item["priority"],
                "reason": item["reason"],
                "consequence": item["consequence"],
                "smallest_alternative": item["smallest_alternative"],
            }
            for item in variant.get("reconciliation", [])
            if item["status"] == "cannot_currently_fit"
        ],
        # The readiness board travels with the plan; it never gates it.
        "checklist": {
            "readiness": checklist_readiness,
            "items": [_task(item) for item in board],
            "dismissed": [
                _task(item)
                for item in (checklist_items or [])
                if item.get("dismissed")
            ],
        },
        "sources": [
            {
                "subject_id": fact.get("subject_id"),
                "display_name": _leg_name(str(fact.get("subject_id") or ""), context),
                "fact_type": fact.get("fact_type"),
                "status": fact.get("status"),
                "source": fact.get("source"),
            }
            for fact in planner_input.get("facts", [])
        ],
        "fallbacks": fallbacks,
        "accommodation": _accommodation(variant, planner_input, context),
        "warnings": sorted(set(variant.get("warnings", []))),
        # Owner-recorded costs in THB plus their original currency. A provider
        # fare would add rows here; it is not required for the sheet to work.
        "costs": {
            "base_currency": BASE_CURRENCY,
            "exchange_rate_snapshot": rate_snapshot,
            "items": list(cost_items or []),
            "totals": cost_totals,
        },
    }


def display_name(
    names: dict[str, Any] | None, fallback: Any, language: str
) -> str:
    """Selected language, then English, then the local script."""

    values = names or {}
    return str(
        values.get(language)
        or values.get("en")
        or values.get("local")
        or fallback
        or ""
    )


def _task(item: dict[str, Any]) -> dict[str, Any]:
    """The agreed checklist columns, kept separate rather than merged for display."""

    return {
        "item_id": item.get("item_id"),
        "title": item.get("title"),
        "template_id": item.get("template_id"),
        "consequence_code": item.get("consequence_code"),
        "title_args": dict(item.get("title_args") or {}),
        "category": item.get("category"),
        "requirement_level": item.get("requirement_level"),
        "progress": item.get("progress"),
        "timing": item.get("timing"),
        "due_date": item.get("due_date"),
        "owner": item.get("owner"),
        "applies_to": list(item.get("applies_to") or []),
        "related_component": item.get("related_component"),
        "consequence": item.get("consequence"),
        "source_url": item.get("source_url"),
        "authority_type": item.get("authority_type"),
        "expected_authority": item.get("expected_authority"),
        "evidence_state": item.get("evidence_state"),
        "last_checked_at": item.get("last_checked_at"),
        "note": item.get("note"),
        "origin": item.get("origin"),
        "dismissed": bool(item.get("dismissed")),
    }


def half_day(start: str) -> str:
    """Morning or afternoon, the grouping fallbacks and day summaries hang off."""

    return "morning" if start < "12:00" else "afternoon"


def _accommodation(
    variant: dict[str, Any], planner_input: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Booking state plus the map anchor for the recommended hotel area."""

    recommendation = variant.get("hotel_recommendation")
    anchor = None
    if recommendation:
        area_id = str(recommendation.get("default_area_id") or "")
        card = context["cards"].get(area_id, {})
        anchor = {
            "subject_id": area_id,
            "display_name": _leg_name(area_id, context),
            "latitude": card.get("latitude"),
            "longitude": card.get("longitude"),
        }
    return {
        "status": planner_input["trip"].get("accommodation_status"),
        "anchor": anchor,
        "recommendation": recommendation,
    }


def _fallbacks(
    variant: dict[str, Any], days: list[dict[str, Any]], context: dict[str, Any]
) -> list[dict[str, Any]]:
    """Locate each fallback by the scheduled visit that replaced its primary."""

    visits = [
        (day, item)
        for day in days
        for item in day["items"]
        if item["type"] == "visit"
    ]
    records = []
    for fallback in variant.get("fallbacks", []):
        primary_id = str(fallback.get("primary_id") or "")
        replacement_id = str(fallback.get("fallback_id") or "")
        match = next(
            (
                (day, item)
                for day, item in visits
                if item["subject_id"] == replacement_id
                or item.get("replaces") == primary_id
            ),
            None,
        )
        displaced = context["reconciliation_by_id"].get(primary_id, {})
        records.append(
            {
                **fallback,
                "date": match[0]["date"] if match else None,
                "half_day": half_day(match[1]["start"]) if match else None,
                "primary_name": _leg_name(primary_id, context),
                "replacement_name": _leg_name(replacement_id, context),
                "replacement_item_id": match[1]["item_id"] if match else None,
                "replacement_start": match[1]["start"] if match else None,
                "displaced_reason": displaced.get("reason"),
                "displaced_consequence": displaced.get("consequence"),
            }
        )
    return records


def _day(day: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    stop_number = 0
    for order, item in enumerate(day["items"], start=1):
        if item["type"] == "visit":
            stop_number += 1
        items.append(_item(order, stop_number, item, context))

    stops = [
        {
            "stop_number": item["stop_number"],
            "subject_id": item["subject_id"],
            "display_name": item["display_name"],
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "status": item["status"],
        }
        for item in items
        if item["type"] == "visit"
    ]
    return {
        "date": day["date"],
        "window": day["window"],
        "start": items[0]["start"] if items else day["window"]["start"],
        "end": items[-1]["end"] if items else day["window"]["start"],
        "items": items,
        "stops": stops,
        "totals": _day_totals(items),
        "highest_risk": _highest_risk(items),
        "statuses": sorted({item["status"] for item in items}),
    }


def _item(
    order: int, stop_number: int, item: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    subject_id = str(item.get("subject_id") or "")
    card = context["cards"].get(subject_id, {})
    row = {
        "order": order,
        "item_id": f"{item['date']}#{order:02d}",
        "type": item["type"],
        "subject_id": subject_id,
        "date": item["date"],
        "start": item["start"],
        "end": item["end"],
        "duration_minutes": item["duration_minutes"],
        "status": CONFIRMED,
    }
    if item["type"] == "visit":
        names = item.get("names") or card.get("names")
        row.update(
            {
                "stop_number": stop_number,
                "display_name": display_name(names, item.get("name"), context["language"]),
                # Every language kept side by side: Excel exports them as
                # separate columns, so switching the UI cannot rewrite identity.
                "names": dict(names or {}),
                "local_name": (names or {}).get("local"),
                "kind": item.get("kind"),
                "priority": item.get("priority"),
                "score": item.get("score"),
                "replaces": item.get("replaces"),
                "latitude": card.get("latitude"),
                "longitude": card.get("longitude"),
                "address": card.get("address"),
                "opening_verified": subject_id in context["opening_verified"],
                "status": _visit_status(subject_id, card, context),
            }
        )
    elif item["type"] == "travel":
        origin = str(item.get("origin_id") or "")
        destination = str(item.get("destination_id") or "")
        row.update(
            {
                "origin_id": item.get("origin_id"),
                "destination_id": item.get("destination_id"),
                "origin_name": _leg_name(origin, context),
                "destination_name": _leg_name(destination, context),
                "mode": item.get("mode"),
                "walking_minutes": int(item.get("walking_minutes", 0)),
                "distance_m": item.get("distance_m"),
                "transfers": item.get("transfers"),
                "boarding_buffer_minutes": int(item.get("boarding_buffer_minutes", 0)),
                "sightseeing_walk": bool(item.get("experience_evidence")),
                "experience_evidence": list(item.get("experience_evidence", [])),
                "claimed_experience": item.get("claimed_experience"),
                "experience_supported_at_time": bool(
                    item.get("experience_supported_at_time")
                ),
                "route_status": item.get("status"),
                "status": _travel_status(item),
            }
        )
    elif item["type"] in {"meal", "preparation", "logistics"}:
        names = item.get("names") or {}
        notes = item.get("notes") or {}
        row.update(
            {
                "display_name": display_name(
                    names, item.get("name"), context["language"]
                ),
                "names": dict(names),
                "local_name": names.get("local"),
                "kind": item.get("kind"),
                "notes": display_name(notes, item.get("note"), context["language"]),
                "from_name": item.get("from_name"),
                "to_name": item.get("to_name"),
                "mode": item.get("mode"),
                "reason": item.get("reason"),
                "status": RECHECK if item.get("status") == "assumed" else CONFIRMED,
            }
        )
    else:
        row["reason"] = item.get("reason")
    return row


def _leg_name(place_id: str, context: dict[str, Any]) -> str:
    card = context["cards"].get(place_id, {})
    return display_name(card.get("names"), card.get("name") or place_id, context["language"])


def _visit_status(
    subject_id: str, card: dict[str, Any], context: dict[str, Any]
) -> str:
    if subject_id in context["locked"]:
        return LOCKED
    if subject_id in context["tradeoff"]:
        return TRADEOFF_ACCEPTED
    if card.get("requires_opening_evidence") and subject_id not in context["opening_verified"]:
        return UNVERIFIED_CONFLICT
    if context["discovery_status"] == "stale":
        return RECHECK
    return CONFIRMED


def _travel_status(item: dict[str, Any]) -> str:
    if item.get("status") != "verified":
        return UNVERIFIED_CONFLICT
    if item.get("claimed_experience") and not item.get("experience_supported_at_time"):
        return RECHECK
    return CONFIRMED


def _highest_risk(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for status in STATUS_RANK:
        if status == CONFIRMED:
            return None
        match = next((item for item in items if item["status"] == status), None)
        if match:
            return {
                "status": status,
                "item_id": match["item_id"],
                "subject_id": match["subject_id"],
            }
    return None


def _day_totals(items: list[dict[str, Any]]) -> dict[str, int]:
    visits = [item for item in items if item["type"] == "visit"]
    travel = [item for item in items if item["type"] == "travel"]
    buffers = [item for item in items if item["type"] == "buffer"]
    meals = [item for item in items if item["type"] == "meal"]
    preparation = [item for item in items if item["type"] == "preparation"]
    logistics = [item for item in items if item["type"] == "logistics"]
    return {
        "scheduled_visits": len(visits),
        "visit_minutes": sum(item["duration_minutes"] for item in visits),
        "travel_minutes": sum(item["duration_minutes"] for item in travel),
        "buffer_minutes": sum(item["duration_minutes"] for item in buffers),
        "meal_minutes": sum(item["duration_minutes"] for item in meals),
        "preparation_minutes": sum(item["duration_minutes"] for item in preparation),
        "logistics_minutes": sum(item["duration_minutes"] for item in logistics),
        "walking_minutes": sum(item["walking_minutes"] for item in travel),
        "plain_walking_minutes": sum(
            item["walking_minutes"] for item in travel if not item["sightseeing_walk"]
        ),
        "rewarding_walking_minutes": sum(
            item["walking_minutes"] for item in travel if item["sightseeing_walk"]
        ),
    }


def _trip_totals(days: list[dict[str, Any]]) -> dict[str, int]:
    keys = (
        "scheduled_visits",
        "visit_minutes",
        "travel_minutes",
        "buffer_minutes",
        "meal_minutes",
        "preparation_minutes",
        "logistics_minutes",
        "walking_minutes",
        "plain_walking_minutes",
        "rewarding_walking_minutes",
    )
    return {key: sum(day["totals"][key] for day in days) for key in keys}


def _reconcile_with_optimizer(
    totals: dict[str, int], metrics: dict[str, Any]
) -> None:
    """Refuse to export numbers that disagree with the optimizer result."""

    expected = {
        "scheduled_visits": metrics["scheduled_visits"],
        "visit_minutes": metrics["visit_minutes"],
        "travel_minutes": metrics["travel_minutes"],
        "buffer_minutes": metrics["buffer_minutes"],
        "walking_minutes": metrics["walking_minutes"],
        "plain_walking_minutes": metrics["plain_walking_minutes"],
        "rewarding_walking_minutes": metrics["rewarding_walking_minutes"],
        "meal_minutes": metrics.get("meal_minutes", 0),
        "preparation_minutes": metrics.get("preparation_minutes", 0),
        "logistics_minutes": metrics.get("logistics_minutes", 0),
    }
    mismatched = sorted(key for key, value in expected.items() if totals[key] != value)
    if mismatched:
        raise ValueError(
            "Export totals do not reconcile with the optimizer result: "
            + ", ".join(mismatched)
        )


def _readiness(variant: dict[str, Any], planner_input: dict[str, Any]) -> dict[str, Any]:
    gaps = sorted(planner_input["trip"].get("capability_gaps", []))
    if not variant["validation"]["valid"]:
        state = VERIFICATION_NEEDED
    elif variant["status"] == READY and not gaps:
        state = READY
    else:
        state = ACTION_NEEDED
    return {
        "state": state,
        "variant_status": variant["status"],
        "validation_valid": bool(variant["validation"]["valid"]),
        "capability_gaps": gaps,
        "blocking_warnings": sorted(set(variant.get("warnings", []))),
    }
