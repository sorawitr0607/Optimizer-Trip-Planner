"""City-independent pre-trip readiness board.

Pure: no Streamlit, SQLite, provider, exporter, or model imports.

No configured provider supplies official entry rules, so nothing here asserts a
legal conclusion.  Generated items name what must be verified and against which
kind of authority, and stay `verification_needed` until the owner records an
official source.  Requirement level is a planning attribute; evidence state is a
provenance attribute; the two move independently.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


SCHEMA_VERSION = 1

# Timing is the primary grouping; topic categories are filters.
TIMING_BUCKETS = (
    "do_now",
    "30_days_before",
    "7_days_before",
    "24_hours_before",
    "departure_arrival_day",
)
BUCKET_OFFSET_DAYS = {
    "30_days_before": 30,
    "7_days_before": 7,
    "24_hours_before": 1,
    "departure_arrival_day": 0,
}
REQUIREMENT_LEVELS = ("required", "recommended", "optional")
PROGRESS_STATES = ("to_do", "waiting", "done", "not_applicable")
CLOSED_STATES = frozenset({"done", "not_applicable"})
EVIDENCE_STATES = ("verified", "verification_needed")
CATEGORIES = (
    "entry_requirements",
    "immigration_customs",
    "money",
    "connectivity",
    "insurance_health",
    "transport_setup",
    "reservations",
    "registrations",
    "packing",
    "local_rules",
    "emergency",
    "accommodation",
)
# Only these may ever support a `required` item.
AUTHORITY_TYPES = (
    "government",
    "embassy",
    "immigration",
    "customs",
    "health_authority",
    "transport_operator",
    "attraction_operator",
)
READY = "ready"
ACTION_NEEDED = "action_needed"
VERIFICATION_NEEDED = "verification_needed"

# One generic worldwide board. Titles name the destination but assert nothing
# about it; a destination-specific rule can only come from an official source.
TEMPLATES = (
    {
        "template_id": "entry_requirements",
        "category": "entry_requirements",
        "requirement_level": "required",
        "timing": "do_now",
        "per_nationality": True,
        "title": "Verify entry requirements for {destination}",
        "consequence": "Denied boarding or refused entry",
        "expected_authority": "government",
    },
    {
        "template_id": "passport_validity",
        "category": "entry_requirements",
        "requirement_level": "required",
        "timing": "do_now",
        "title": "Confirm every passport stays valid for the whole trip",
        "consequence": "Denied boarding",
        "expected_authority": "government",
    },
    {
        "template_id": "immigration_forms",
        "category": "immigration_customs",
        "requirement_level": "required",
        "timing": "7_days_before",
        "title": "Check whether {destination} requires an arrival or customs declaration",
        "consequence": "Held at the border or fined",
        "expected_authority": "immigration",
    },
    {
        "template_id": "insurance_health",
        "category": "insurance_health",
        "requirement_level": "recommended",
        "timing": "30_days_before",
        "title": "Decide travel insurance and check health requirements",
        "consequence": "Unfunded medical cost, or a refused entry where cover is mandatory",
        "expected_authority": "health_authority",
    },
    {
        "template_id": "money",
        "category": "money",
        "requirement_level": "recommended",
        "timing": "7_days_before",
        "title": "Prepare payment methods and local cash",
        "consequence": "Unable to pay where cards are not accepted",
        "expected_authority": None,
    },
    {
        "template_id": "connectivity",
        "category": "connectivity",
        "requirement_level": "recommended",
        "timing": "7_days_before",
        "title": "Arrange data connectivity",
        "consequence": "No maps, tickets, or translation on arrival",
        "expected_authority": None,
    },
    {
        "template_id": "transport_setup",
        "category": "transport_setup",
        "requirement_level": "recommended",
        "timing": "7_days_before",
        "title": "Set up local transport payment or passes",
        "consequence": "Queues and higher fares on the first day",
        "expected_authority": "transport_operator",
    },
    {
        "template_id": "local_rules",
        "category": "local_rules",
        "requirement_level": "recommended",
        "timing": "7_days_before",
        "title": "Read local rules and etiquette that carry penalties",
        "consequence": "Fines or refused access",
        "expected_authority": "government",
    },
    {
        "template_id": "packing",
        "category": "packing",
        "requirement_level": "optional",
        "timing": "24_hours_before",
        "title": "Pack against the planned weather and walking load",
        "consequence": "Avoidable discomfort or an unusable item",
        "expected_authority": None,
    },
    {
        "template_id": "emergency",
        "category": "emergency",
        "requirement_level": "recommended",
        "timing": "24_hours_before",
        "title": "Save emergency contacts and embassy details offline",
        "consequence": "No usable contact during an incident",
        "expected_authority": "embassy",
    },
    {
        "template_id": "departure_recheck",
        "category": "transport_setup",
        "requirement_level": "required",
        "timing": "departure_arrival_day",
        "title": "Recheck departure time, terminal, and any closures",
        "consequence": "Missed departure",
        "expected_authority": "transport_operator",
    },
)


def propose_items(
    *,
    destination: str,
    setup: dict[str, Any],
    choices: list[dict[str, Any]] | None = None,
    facts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return the generated board for this trip, deterministically ordered."""

    basics = setup.get("trip_basics", {}) or {}
    start_date = basics.get("start_date")
    travellers = _travellers(setup)
    proposed: list[dict[str, Any]] = []

    for template in TEMPLATES:
        if template.get("per_nationality"):
            # Shared where nationalities match or are unknown; split when they differ.
            for group, members in _nationality_groups(travellers):
                proposed.append(
                    _generated(
                        template,
                        destination=destination,
                        start_date=start_date,
                        scope=group or "shared",
                        applies_to=[member["traveller_id"] for member in members],
                        nationality=group,
                    )
                )
            continue
        proposed.append(
            _generated(
                template,
                destination=destination,
                start_date=start_date,
                scope="shared",
                applies_to=[member["traveller_id"] for member in travellers],
            )
        )

    if basics.get("accommodation_status") != "booked":
        proposed.append(
            _generated(
                {
                    "template_id": "accommodation_base",
                    "category": "accommodation",
                    "requirement_level": "required",
                    "timing": "do_now",
                    "title": "Confirm accommodation and record its address offline",
                    "consequence": "No usable base for routing or for an arrival form",
                    "expected_authority": None,
                },
                destination=destination,
                start_date=start_date,
                scope="shared",
                applies_to=[member["traveller_id"] for member in travellers],
                related_component="accommodation",
            )
        )

    for place in _booking_places(choices or [], facts or []):
        proposed.append(
            _generated(
                {
                    "template_id": "place_booking",
                    "category": "reservations" if place["timed"] else "registrations",
                    "requirement_level": "required" if place["timed"] else "recommended",
                    "timing": "30_days_before",
                    "title": "Check opening hours and advance booking for {place}",
                    "consequence": (
                        "A timed or limited entry sells out or closes the visit"
                        if place["timed"]
                        else "Queueing, or arriving when the place cannot be entered"
                    ),
                    "expected_authority": "attraction_operator",
                },
                destination=destination,
                start_date=start_date,
                scope=f"place:{place['place_id']}",
                applies_to=[member["traveller_id"] for member in travellers],
                related_component=place["place_id"],
                place=place["name"],
            )
        )
    return sorted(proposed, key=_order)


def diff_proposal(
    current: list[dict[str, Any]], proposed: list[dict[str, Any]]
) -> dict[str, Any]:
    """Preview additions, removals, and deadline changes before applying them."""

    generated = {
        item["generated_key"]: item
        for item in current
        if item.get("origin") == "generated" and item["generated_key"]
    }
    incoming = {item["generated_key"]: item for item in proposed}
    additions = [incoming[key] for key in sorted(incoming.keys() - generated.keys())]
    removals = [
        generated[key]
        for key in sorted(generated.keys() - incoming.keys())
        if not generated[key].get("dismissed")
    ]
    deadline_changes = []
    for key in sorted(incoming.keys() & generated.keys()):
        before, after = generated[key], incoming[key]
        if (before.get("due_date"), before.get("timing")) != (
            after.get("due_date"),
            after.get("timing"),
        ):
            deadline_changes.append(
                {
                    "generated_key": key,
                    "title": after["title"],
                    "from": {"due_date": before.get("due_date"), "timing": before.get("timing")},
                    "to": {"due_date": after.get("due_date"), "timing": after.get("timing")},
                }
            )
    return {
        "additions": additions,
        "removals": removals,
        "deadline_changes": deadline_changes,
        "unchanged": len(incoming) - len(additions) - len(deadline_changes),
    }


def readiness(
    items: list[dict[str, Any]], *, today: str, due_soon_days: int = 7
) -> dict[str, Any]:
    """Summarize the board. Warnings never block the itinerary or its exports."""

    active = [item for item in items if not item.get("dismissed")]
    open_items = [item for item in active if item["progress"] not in CLOSED_STATES]
    required_open = [item for item in open_items if item["requirement_level"] == "required"]
    unverified = [
        item
        for item in active
        if item["requirement_level"] == "required"
        and item["evidence_state"] != "verified"
        and item["progress"] not in CLOSED_STATES
    ]
    overdue = sorted(
        (item for item in open_items if _is_overdue(item, today)),
        key=_order,
    )
    due_soon = sorted(
        (item for item in open_items if _is_due_soon(item, today, due_soon_days)),
        key=_order,
    )
    if unverified:
        state = VERIFICATION_NEEDED
    elif required_open or overdue:
        state = ACTION_NEEDED
    else:
        state = READY
    return {
        "state": state,
        "counts": {
            "total": len(active),
            "open": len(open_items),
            "required_open": len(required_open),
            "unverified_required": len(unverified),
            "overdue": len(overdue),
            "due_soon": len(due_soon),
            "dismissed": len(items) - len(active),
        },
        "overdue": overdue,
        "due_soon": due_soon,
        "blocks_itinerary": False,
    }


def due_date_for(timing: str, start_date: str | None) -> str | None:
    """Resolve a milestone against the trip start; an exact deadline overrides it."""

    if timing not in TIMING_BUCKETS:
        raise ValueError(f"Unsupported timing bucket: {timing}")
    offset = BUCKET_OFFSET_DAYS.get(timing)
    if offset is None or not start_date:
        return None
    return (date.fromisoformat(start_date) - timedelta(days=offset)).isoformat()


def validate_item(item: dict[str, Any]) -> dict[str, Any]:
    """Reject a board item that breaks the agreed contract."""

    title = str(item.get("title") or "").strip()
    if not title:
        raise ValueError("Checklist item needs a title")
    for field, allowed in (
        ("category", CATEGORIES),
        ("requirement_level", REQUIREMENT_LEVELS),
        ("progress", PROGRESS_STATES),
        ("evidence_state", EVIDENCE_STATES),
        ("timing", TIMING_BUCKETS),
    ):
        if item.get(field) not in allowed:
            raise ValueError(f"Unsupported checklist {field}: {item.get(field)}")
    authority = item.get("authority_type")
    if authority is not None and authority not in AUTHORITY_TYPES:
        raise ValueError(f"Unsupported authority type: {authority}")
    if item["progress"] == "not_applicable" and not str(item.get("note") or "").strip():
        raise ValueError("Choosing Not applicable needs a short reason")
    if item["evidence_state"] == "verified" and not str(item.get("source_url") or "").strip():
        raise ValueError("A verified item needs its official source URL")
    if (
        item["requirement_level"] == "required"
        and item["evidence_state"] == "verified"
        and authority not in AUTHORITY_TYPES
    ):
        raise ValueError(
            "A verified required item needs a responsible authority type"
        )
    return {**item, "title": title}


def needs_recheck(item: dict[str, Any], *, today: str, start_date: str | None) -> bool:
    """True when a verified item passed a mandatory refresh point since its check."""

    if item.get("dismissed") or item["evidence_state"] != "verified":
        return False
    checked = str(item.get("last_checked_at") or "")[:10]
    if not checked:
        return True
    for bucket in ("30_days_before", "7_days_before", "24_hours_before"):
        point = due_date_for(bucket, start_date)
        if point and checked < point <= today:
            return True
    return False


def _generated(
    template: dict[str, Any],
    *,
    destination: str,
    start_date: str | None,
    scope: str,
    applies_to: list[str],
    nationality: str | None = None,
    related_component: str | None = None,
    place: str | None = None,
) -> dict[str, Any]:
    timing = template["timing"]
    title = template["title"].format(
        destination=destination.strip() or "this destination", place=place or ""
    )
    return {
        "generated_key": f"{template['template_id']}:{scope}",
        "template_id": template["template_id"],
        "origin": "generated",
        "title": title,
        "category": template["category"],
        "requirement_level": template["requirement_level"],
        "timing": timing,
        "due_date": due_date_for(timing, start_date),
        "progress": "to_do",
        "evidence_state": "verification_needed",
        "owner": "owner",
        "applies_to": sorted(applies_to),
        "nationality": nationality,
        "related_component": related_component,
        "consequence": template["consequence"],
        "expected_authority": template.get("expected_authority"),
        "authority_type": None,
        "source_url": None,
        "last_checked_at": None,
        "note": None,
        "dismissed": False,
    }


def _travellers(setup: dict[str, Any]) -> list[dict[str, Any]]:
    owner = setup.get("owner", {}) or {}
    people = [
        {
            "traveller_id": "owner",
            "nationality": _nationality(owner.get("nationality")),
        }
    ]
    people.extend(
        {
            "traveller_id": str(member.get("traveller_id") or ""),
            "nationality": _nationality(member.get("nationality")),
        }
        for member in setup.get("travellers", []) or []
    )
    return people


def _nationality(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _nationality_groups(
    travellers: list[dict[str, Any]],
) -> list[tuple[str | None, list[dict[str, Any]]]]:
    """One shared item when nationalities match or are unknown, else one each."""

    known = {person["nationality"] for person in travellers if person["nationality"]}
    if len(known) <= 1:
        return [(next(iter(known), None), travellers)]
    groups: dict[str | None, list[dict[str, Any]]] = {}
    for person in travellers:
        groups.setdefault(person["nationality"], []).append(person)
    return sorted(groups.items(), key=lambda pair: (pair[0] is None, pair[0] or ""))


def _booking_places(
    choices: list[dict[str, Any]], facts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Selected places that warrant a booking or access check."""

    timed_subjects = {
        str(fact.get("subject_id"))
        for fact in facts
        if fact.get("status") == "verified"
        and fact.get("fact_type") in {"show_intervals", "queue_wait_minutes", "crowd_risk"}
    }
    places = []
    for choice in choices:
        if choice.get("action") != "must_do":
            continue
        place_id = str(choice.get("place_id") or "")
        if not place_id:
            continue
        candidate = choice.get("candidate") or {}
        places.append(
            {
                "place_id": place_id,
                "name": str(candidate.get("name") or place_id),
                "timed": place_id in timed_subjects,
            }
        )
    return sorted(places, key=lambda item: item["place_id"])


def _is_overdue(item: dict[str, Any], today: str) -> bool:
    due = item.get("due_date")
    return bool(due) and due < today


def _is_due_soon(item: dict[str, Any], today: str, window: int) -> bool:
    due = item.get("due_date")
    if not due or due < today:
        return False
    limit = (date.fromisoformat(today) + timedelta(days=window)).isoformat()
    return due <= limit


def _order(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        TIMING_BUCKETS.index(item.get("timing", "do_now")),
        item.get("due_date") or "9999-12-31",
        REQUIREMENT_LEVELS.index(item.get("requirement_level", "optional")),
        item.get("title", ""),
        item.get("generated_key") or "",
    )
