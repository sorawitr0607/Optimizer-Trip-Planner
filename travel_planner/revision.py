"""Typed plan-revision operations and their consequence comparison.

Pure: no Streamlit, SQLite, provider, exporter, or model imports.

An operation is a *constraint change*, never a schedule instruction. It edits the
optimizer's input snapshot; the deterministic optimizer then rebuilds the plan
and the comparison below reports what that did. Nothing here writes an opening
time, route, fare, closure, or any other operational fact, so a future model that
only chooses among these operations still cannot invent one.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


SCHEMA_VERSION = 1

# Every supported Phase 1 operation, with the arguments it needs. A request that
# does not map onto this set is unsupported rather than improvised.
OPERATIONS = {
    "reduce_walking": {"args": ("factor",), "changes_plan": True},
    "reduce_daily_load": {"args": ("factor",), "changes_plan": True},
    "fix_meal_timing": {"args": ("start", "end"), "changes_plan": True},
    "adjust_duration": {"args": ("place_id", "minutes"), "changes_plan": True},
    "lock_item": {"args": ("place_id",), "changes_plan": True},
    "unlock_item": {"args": ("place_id",), "changes_plan": True},
    "drop_place": {"args": ("place_id",), "changes_plan": True},
    "fully_reoptimize": {"args": (), "changes_plan": True},
    "explain": {"args": (), "changes_plan": False},
}
CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MIN_THRESHOLD_MINUTES = 5
MIN_VISIT_MINUTES = 15


def validate_operation(operation: dict[str, Any]) -> dict[str, Any]:
    """Reject anything outside the typed set, before any optimizer run."""

    name = str(operation.get("operation") or "")
    if name not in OPERATIONS:
        raise ValueError(f"Unsupported revision operation: {name or '(missing)'}")
    args = dict(operation.get("arguments") or {})
    for required in OPERATIONS[name]["args"]:
        if args.get(required) in (None, ""):
            raise ValueError(f"{name} needs {required}")
    if "factor" in args:
        factor = float(args["factor"])
        if not 0.1 <= factor < 1.0:
            raise ValueError("factor must be between 0.1 and just below 1.0")
        args["factor"] = factor
    if "minutes" in args:
        minutes = int(args["minutes"])
        if minutes < MIN_VISIT_MINUTES:
            raise ValueError(f"minutes must be at least {MIN_VISIT_MINUTES}")
        args["minutes"] = minutes
    for key in ("start", "end"):
        if key in args and not CLOCK.fullmatch(str(args[key])):
            raise ValueError(f"{key} must use HH:MM")
    if {"start", "end"} <= set(args) and str(args["start"]) >= str(args["end"]):
        raise ValueError("start must be before end")
    return {
        "operation": name,
        "arguments": args,
        "changes_plan": bool(OPERATIONS[name]["changes_plan"]),
    }


def apply_operation(
    snapshot: dict[str, Any], operation: dict[str, Any]
) -> dict[str, Any]:
    """Return a new optimizer input with the operation's constraints applied."""

    clean = validate_operation(operation)
    name, args = clean["operation"], clean["arguments"]
    proposed = deepcopy(snapshot)
    assumptions: list[str] = []

    if name in {"explain", "fully_reoptimize"}:
        # Nothing to change: the same input is re-solved, which is the point.
        if name == "fully_reoptimize":
            assumptions.append("REOPTIMIZED_WITH_UNCHANGED_CONSTRAINTS")
        return {"snapshot": proposed, "assumptions": assumptions}

    thresholds = proposed.setdefault("thresholds", {})
    if name == "reduce_walking":
        for key, current in (
            ("walking_minutes_per_leg", _current_walking_leg(proposed)),
            ("plain_walking_minutes_per_day", _current_plain_walking(proposed)),
        ):
            tightened = max(MIN_THRESHOLD_MINUTES, int(current * args["factor"]))
            thresholds[key] = tightened
            assumptions.append(f"{key.upper()}_SET_TO_{tightened}")
    elif name == "reduce_daily_load":
        current = int(thresholds.get("physical_load_points_per_day") or 100)
        tightened = max(1, int(current * args["factor"]))
        thresholds["physical_load_points_per_day"] = tightened
        assumptions.append(f"PHYSICAL_LOAD_POINTS_PER_DAY_SET_TO_{tightened}")
    elif name == "fix_meal_timing":
        thresholds["meal_window"] = {"start": args["start"], "end": args["end"]}
        assumptions.append(f"MEAL_WINDOW_SET_TO_{args['start']}_{args['end']}")
    elif name == "adjust_duration":
        candidate = _candidate(proposed, args["place_id"])
        bounds = candidate.setdefault("duration_bounds", {})
        minutes = args["minutes"]
        bounds.update(
            {
                "minimum_minutes": min(int(bounds.get("minimum_minutes", minutes)), minutes),
                "ideal_minutes": minutes,
                "maximum_minutes": max(int(bounds.get("maximum_minutes", minutes)), minutes),
            }
        )
        assumptions.append(f"IDEAL_VISIT_MINUTES_SET_TO_{minutes}")
    elif name == "lock_item":
        locks = proposed.setdefault("locks", [])
        place_id = str(args["place_id"])
        _candidate(proposed, place_id)
        if not any(str(lock.get("subject_id")) == place_id for lock in locks):
            locks.append({"subject_id": place_id, "reason": "owner_locked"})
        assumptions.append("LOCK_ADDED")
    elif name == "unlock_item":
        place_id = str(args["place_id"])
        locks = proposed.get("locks", [])
        proposed["locks"] = [
            lock for lock in locks if str(lock.get("subject_id")) != place_id
        ]
        if len(proposed["locks"]) == len(locks):
            raise ValueError(f"{place_id} is not locked")
        assumptions.append("LOCK_REMOVED")
    elif name == "drop_place":
        place_id = str(args["place_id"])
        _candidate(proposed, place_id)
        remaining = [
            item
            for item in proposed.get("candidates", [])
            if str(item.get("id")) != place_id
        ]
        if not any(_is_selected(item) for item in remaining):
            raise ValueError("Dropping this place would leave no selected place")
        proposed["candidates"] = remaining
        proposed["locks"] = [
            lock
            for lock in proposed.get("locks", [])
            if str(lock.get("subject_id")) != place_id
        ]
        assumptions.append("PLACE_DROPPED_FROM_THIS_REVISION")
    return {"snapshot": proposed, "assumptions": assumptions}


def consequences(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Before and after comparison across every day the change touched."""

    before_visits = _visits_by_place(before)
    after_visits = _visits_by_place(after)
    added = sorted(set(after_visits) - set(before_visits))
    removed = sorted(set(before_visits) - set(after_visits))
    moved, shortened, lengthened = [], [], []
    for place_id in sorted(set(before_visits) & set(after_visits)):
        was, now = before_visits[place_id], after_visits[place_id]
        if (was["date"], was["start"]) != (now["date"], now["start"]):
            moved.append(
                {
                    "place_id": place_id,
                    "from": {"date": was["date"], "start": was["start"]},
                    "to": {"date": now["date"], "start": now["start"]},
                }
            )
        if now["duration_minutes"] < was["duration_minutes"]:
            shortened.append(
                {
                    "place_id": place_id,
                    "from_minutes": was["duration_minutes"],
                    "to_minutes": now["duration_minutes"],
                }
            )
        elif now["duration_minutes"] > was["duration_minutes"]:
            lengthened.append(
                {
                    "place_id": place_id,
                    "from_minutes": was["duration_minutes"],
                    "to_minutes": now["duration_minutes"],
                }
            )

    changed_dates = sorted(
        {item["from"]["date"] for item in moved}
        | {item["to"]["date"] for item in moved}
        | {after_visits[place_id]["date"] for place_id in added}
        | {before_visits[place_id]["date"] for place_id in removed}
        | {after_visits[item["place_id"]]["date"] for item in shortened + lengthened}
    )
    metric_keys = (
        "scheduled_visits",
        "visit_minutes",
        "travel_minutes",
        "walking_minutes",
        "plain_walking_minutes",
        "rewarding_walking_minutes",
        "buffer_minutes",
    )
    return {
        "added": added,
        "removed": removed,
        "moved": moved,
        "shortened": shortened,
        "lengthened": lengthened,
        "changed_dates": changed_dates,
        "metrics": {
            key: {
                "before": before["metrics"].get(key),
                "after": after["metrics"].get(key),
                "delta": _delta(before["metrics"].get(key), after["metrics"].get(key)),
            }
            for key in metric_keys
        },
        "warnings": {
            "before": sorted(set(before.get("warnings", []))),
            "after": sorted(set(after.get("warnings", []))),
            "new": sorted(set(after.get("warnings", [])) - set(before.get("warnings", []))),
            "cleared": sorted(
                set(before.get("warnings", [])) - set(after.get("warnings", []))
            ),
        },
        "displaced": _displaced(before, after),
        "status": {"before": before.get("status"), "after": after.get("status")},
        "validation": {
            "before_valid": bool(before.get("validation", {}).get("valid")),
            "after_valid": bool(after.get("validation", {}).get("valid")),
        },
        # Apply stays closed until the proposal passes the same gates as any plan.
        "can_apply": bool(
            after.get("status") == "ready" and after.get("validation", {}).get("valid")
        ),
    }


def _delta(before: Any, after: Any) -> Any:
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return round(after - before, 2)
    return None


def _visits_by_place(variant: dict[str, Any]) -> dict[str, dict[str, Any]]:
    visits = {}
    for day in variant.get("days", []):
        for item in day.get("items", []):
            if item.get("type") != "visit":
                continue
            visits[str(item["subject_id"])] = {
                "date": day["date"],
                "start": item["start"],
                "duration_minutes": int(item["duration_minutes"]),
            }
    return visits


def _displaced(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Selections that stopped fitting, with the reason the optimizer gave."""

    was = {
        item["place_id"]: item["status"] for item in before.get("reconciliation", [])
    }
    now = []
    for item in after.get("reconciliation", []):
        if item["status"] == "cannot_currently_fit" and was.get(item["place_id"]) == "fits":
            now.append(
                {
                    "place_id": item["place_id"],
                    "name": item.get("name"),
                    "reason": item.get("reason"),
                    "consequence": item.get("consequence"),
                }
            )
    return now


def _is_selected(candidate: dict[str, Any]) -> bool:
    """Mirror the optimizer's own rule, so a drop cannot empty the plan.

    An absent priority means `interested` there, and a hotel area is a base
    rather than a selection.
    """

    return (
        candidate.get("priority", "interested")
        not in {"backup", "alternative", "not_for_trip"}
        and candidate.get("kind") != "hotel_area"
    )


def _candidate(snapshot: dict[str, Any], place_id: str) -> dict[str, Any]:
    for item in snapshot.get("candidates", []):
        if str(item.get("id")) == str(place_id):
            return item
    raise ValueError(f"{place_id} is not a selected place in this plan")


def _current_walking_leg(snapshot: dict[str, Any]) -> int:
    stated = snapshot.get("thresholds", {}).get("walking_minutes_per_leg")
    if stated:
        return int(stated)
    legs = [
        int(route.get("walking_minutes") or 0) for route in snapshot.get("routes", [])
    ]
    return max(legs) if legs else 30


def _current_plain_walking(snapshot: dict[str, Any]) -> int:
    stated = snapshot.get("thresholds", {}).get("plain_walking_minutes_per_day")
    if stated:
        return int(stated)
    legs = [
        int(route.get("walking_minutes") or 0)
        for route in snapshot.get("routes", [])
        if not route.get("experience_evidence")
    ]
    return sum(sorted(legs, reverse=True)[:3]) or 60
