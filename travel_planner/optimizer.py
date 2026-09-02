"""Pure deterministic whole-trip scheduling and validation.

The optimizer consumes normalized snapshots only.  It never calls providers,
SQLite, Streamlit, exporters, or a language model.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
import json
from math import ceil
from time import monotonic
from typing import Any


OPTIMIZER_VERSION = "whole-trip-v3"

# What the departure day owes before the flight: pack and check out, reach the
# terminal, be at the airport. Exported because the *usable window* for that day has
# to open early enough to contain them -- a 10:40 flight means leaving at 07:40
# however late the owner likes to start sightseeing, and a window that says 08:00
# makes the day infeasible. See `WF-042`. Kept as one source so the layout below and
# `actions._optimizer_input` cannot drift apart.
DEPARTURE_LOGISTICS: tuple[tuple[str, int], ...] = (
    ("pack_and_check_out", 45),
    ("departure_transfer", 45),
    ("airport_departure", 90),
)
DEPARTURE_LOGISTICS_MINUTES = sum(minutes for _, minutes in DEPARTURE_LOGISTICS)

# The three comfort budgets an owner may agree to exceed, in one table so the validator,
# the soft-violation count and the screen cannot drift apart on which is which. `WF-039`.
#
# `reason` is the code an acceptance is recorded under; `code` is the hard violation
# raised when there is no acceptance covering the measurement.
COMFORT_RULES: tuple[dict[str, str], ...] = (
    {
        "reason": "PLAIN_WALK_THRESHOLD",
        "code": "UNAPPROVED_PLAIN_WALK_THRESHOLD",
        "metric": "maximum_plain_walking_minutes_per_day",
        "fallback_metric": "plain_walking_minutes",
        "threshold": "plain_walking_minutes_per_day",
    },
    {
        "reason": "LONG_TRANSFER_WALK",
        "code": "UNAPPROVED_WALKING_LEG_THRESHOLD",
        "metric": "maximum_walking_minutes_per_leg",
        "fallback_metric": "maximum_walking_minutes_per_leg",
        "threshold": "walking_minutes_per_leg",
    },
    {
        "reason": "HEAT_AND_CYCLING_LOAD",
        "code": "UNAPPROVED_CYCLING_THRESHOLD",
        "metric": "cycling_minutes",
        "fallback_metric": "cycling_minutes",
        "threshold": "cycling_minutes_per_day",
    },
)


def _accepts(snapshot: dict[str, Any], reason: str, measured: float) -> bool:
    """Has the owner agreed to *this much* of this overage? `WF-039`.

    Bounded by the value accepted, not a boolean. Agreeing to a 27-minute walking leg
    must not silently bless the 90-minute one a later replan produces, and the ticket
    named that as the thing any fix had to get right. A tighter plan than the one agreed
    to is still covered, so an owner is not asked again for an improvement.

    Read from the snapshot rather than from `variant["reconciliation"]`, which is where
    the original dead code looked. These violations carry `subject_id: None` -- they are
    properties of the whole variant, not of a place -- so routing consent through a
    per-place record was the wrong shape, and no call site ever produced the
    `fits_with_tradeoff` status that route required.
    """

    for item in snapshot.get("comfort_acceptances", []):
        if item.get("code") != reason:
            continue
        try:
            return measured <= float(item["accepted_value"])
        except (KeyError, TypeError, ValueError):
            return False
    return False

VARIANT_CONFIGS = (
    {"id": "best_balance", "duration": "ideal", "buffer_minutes": 10},
    {"id": "relaxed", "duration": "maximum", "buffer_minutes": 20},
    {"id": "more_highlights", "duration": "minimum", "buffer_minutes": 5},
)
PRIORITY_ORDER = {
    "locked": 0,
    "must_do": 1,
    "interested": 2,
    "maybe": 3,
    "optional": 4,
    "alternative": 5,
    "backup": 6,
}
ACCESS_FACT_TYPES = frozenset(
    {
        "entry_rule",
        "entrance_instruction",
        "internal_walking_route",
        "entrance_coordinate",
        "approach_instruction",
        "access",
    }
)

# These are visible planning defaults, not claims about a booked flight, hotel,
# or airport. They turn the attraction-only result into the same kind of
# operational timetable as the four reference trips; the owner replaces the
# assumptions after booking.
OPERATIONAL_COPY = {
    "pack_bags": (
        "Pack bags for the forecast and planned activities",
        "จัดกระเป๋าตามอากาศและกิจกรรมที่วางไว้",
        "Put passports, medicines, chargers and first-day essentials in carry-on; check activity-specific prohibited items.",
        "ใส่พาสปอร์ต ยา ที่ชาร์จ และของใช้วันแรกไว้ในกระเป๋าถือ พร้อมเช็กของต้องห้ามของกิจกรรม",
    ),
    "documents_and_tickets": (
        "Recheck documents, tickets and terminal",
        "ตรวจเอกสาร ตั๋ว และอาคารผู้โดยสารอีกครั้ง",
        "Confirm passport, booking references, baggage rules, terminal, insurance and offline copies.",
        "ยืนยันพาสปอร์ต เลขจอง กฎสัมภาระ อาคารผู้โดยสาร ประกัน และสำเนาออฟไลน์",
    ),
    "charge_and_alarm": (
        "Charge devices, download maps and set alarms",
        "ชาร์จอุปกรณ์ ดาวน์โหลดแผนที่ และตั้งปลุก",
        "Charge the power bank and phones; save tickets, hotel address, maps and translation offline.",
        "ชาร์จพาวเวอร์แบงก์และโทรศัพท์ พร้อมบันทึกตั๋ว ที่อยู่โรงแรม แผนที่ และคำแปลแบบออฟไลน์",
    ),
    "airport_arrival": (
        "Arrival terminal: immigration, baggage and essentials",
        "อาคารผู้โดยสารขาเข้า: ตม. รับกระเป๋า และเตรียมของจำเป็น",
        "Planner allowance for immigration, baggage claim, restroom, cash or connectivity; confirm the real terminal and duration after booking.",
        "เวลาสำรองสำหรับ ตม. รับกระเป๋า ห้องน้ำ เงินสดหรืออินเทอร์เน็ต ให้ยืนยันอาคารและเวลาจริงหลังจอง",
    ),
    "arrival_transfer": (
        "Arrival terminal to accommodation area",
        "จากอาคารผู้โดยสารขาเข้าไปย่านที่พัก",
        "Confirm airport or station, mode, line, platform, exit, fare and door-to-door duration; this is a provisional transfer slot.",
        "ยืนยันสนามบินหรือสถานี วิธีเดินทาง สาย ชานชาลา ทางออก ค่าโดยสาร และเวลาถึงประตู ที่นี่เป็นช่วงเวลาโดยประมาณ",
    ),
    "accommodation_check_in": (
        "Check in, store bags and recover from the journey",
        "เช็กอิน ฝากกระเป๋า และพักหลังเดินทาง",
        "If the room is not ready, store bags; save the local address, entrance and check-in rule before leaving.",
        "หากห้องยังไม่พร้อมให้ฝากกระเป๋า และบันทึกที่อยู่ ทางเข้า และกฎเช็กอินก่อนออกเที่ยว",
    ),
    "day_preparation": (
        "Wake up, wash and prepare the day bag",
        "ตื่น อาบน้ำ และเตรียมกระเป๋าประจำวัน",
        "Check weather, tickets, batteries, water, medication and the day's first route.",
        "เช็กอากาศ ตั๋ว แบตเตอรี่ น้ำ ยา และเส้นทางแรกของวัน",
    ),
    "breakfast": (
        "Breakfast near the base or first stop",
        "มื้อเช้าใกล้ที่พักหรือจุดแรก",
        "Choose a nearby option and keep a queue backup so the first timed activity is not delayed.",
        "เลือกร้านใกล้ ๆ และมีร้านสำรองกรณีคิว เพื่อไม่ให้กิจกรรมแรกที่กำหนดเวลาล่าช้า",
    ),
    "lunch": (
        "Lunch near the surrounding stops",
        "มื้อกลางวันใกล้จุดเที่ยวช่วงนั้น",
        "Choose or reserve a restaurant near the preceding and next stop; record queue limit and one nearby backup.",
        "เลือกหรือจองร้านใกล้จุดก่อนหน้าและจุดถัดไป พร้อมกำหนดเวลารอคิวและร้านสำรองใกล้ ๆ",
    ),
    "dinner": (
        "Dinner near the evening route",
        "มื้อเย็นใกล้เส้นทางช่วงค่ำ",
        "Confirm opening, last order, reservation or queue plan, and a nearby fallback before the final return leg.",
        "ยืนยันเวลาเปิด เวลารับออเดอร์สุดท้าย การจองหรือแผนคิว และร้านสำรองก่อนเดินทางกลับ",
    ),
    "return_to_accommodation": (
        "Return to the accommodation base",
        "เดินทางกลับที่พัก",
        "Confirm the final service, station or pickup point and hotel entrance; replace this provisional duration with a routed leg.",
        "ยืนยันเที่ยวสุดท้าย สถานีหรือจุดรับรถ และทางเข้าโรงแรม แล้วแทนเวลาโดยประมาณด้วยเส้นทางจริง",
    ),
    "pack_and_check_out": (
        "Pack, room sweep, check out and collect bags",
        "เก็บของ ตรวจห้อง เช็กเอาต์ และรับกระเป๋า",
        "Check drawers, chargers, passports and purchases; confirm luggage storage if sightseeing continues.",
        "ตรวจลิ้นชัก ที่ชาร์จ พาสปอร์ต และของที่ซื้อ พร้อมยืนยันที่ฝากกระเป๋าหากยังเที่ยวต่อ",
    ),
    "departure_transfer": (
        "Accommodation to departure airport or station",
        "จากที่พักไปสนามบินหรือสถานีขาออก",
        "Confirm terminal, mode, line, platform or drop-off point, fare and disruption backup; this duration is provisional.",
        "ยืนยันอาคาร วิธีเดินทาง สาย ชานชาลาหรือจุดส่ง ค่าโดยสาร และแผนสำรองเมื่อขัดข้อง เวลานี้เป็นค่าประมาณ",
    ),
    "airport_departure": (
        "Check in, security, immigration and wait at the gate",
        "เช็กอิน ตรวจความปลอดภัย ตม. และรอที่ประตูขึ้นเครื่อง",
        "Confirm airline or operator cutoff, terminal, gate and baggage rules; include food, water and duty-free only after the gate is known.",
        "ยืนยันเวลาปิดเช็กอิน อาคาร ประตู และกฎสัมภาระ ซื้ออาหาร น้ำ หรือดิวตี้ฟรีหลังทราบประตูแล้ว",
    ),
}


def optimize_trip(
    snapshot: dict[str, Any],
    *,
    time_limit_seconds: float = 30.0,
    on_variant: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Return deterministic proposals from one provider-neutral snapshot.

    `on_variant` is told how many variants have been solved, each time one is. It is
    observation only and the proposal does not depend on it: it receives a count and
    returns nothing, it is never consulted, and `deterministic_signature` is computed
    from the same variants whether it was supplied or not. It imports nothing, so the
    module stays as language-neutral and dependency-free as its docstring says.

    It exists because this is the longest single call in the app — three variants at
    roughly 21s each — and to anything watching from outside it is one opaque wait. A
    variant *returning* is a fact, which is the only kind of progress this project
    reports.
    """

    _validate_input(snapshot)
    if time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds must be positive")
    canonical = json.dumps(
        snapshot, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    input_sha256 = sha256(canonical.encode("utf-8")).hexdigest()
    selected = _selected_candidates(snapshot)
    if not selected:
        raise ValueError("Choose at least one Must do, Interested, or Maybe place")

    if not snapshot["trip"].get("local_dates"):
        return {
            "schema_version": 1,
            "optimizer_version": OPTIMIZER_VERSION,
            "input_sha256": input_sha256,
            "mode": "stay_recommendation",
            "stay_recommendations": _stay_recommendations(selected),
            "variants": [],
            "stopped_at_limit": False,
        }

    # `WF-043`. One budget **per variant**, not one shared across all three. A single
    # absolute deadline is consumed in order, so the third variant inherited whatever
    # the first two left: measured on the pilot at 20.7s + 10.4s of a 30s budget, which
    # left `more_highlights` already past it. It returned in 0.04s having placed
    # nothing, while the same variant on its own budget finishes in 21.5s with all 13
    # visits. Worst case is now len(VARIANT_CONFIGS) x time_limit_seconds.
    variants = []
    for solved, config in enumerate(VARIANT_CONFIGS, start=1):
        variants.append(
            _solve_variant(snapshot, config, deadline=monotonic() + time_limit_seconds)
        )
        # After the append, so the count is of variants in hand rather than of
        # iterations begun.
        if on_variant is not None:
            on_variant(solved)
    proposal = {
        "schema_version": 1,
        "optimizer_version": OPTIMIZER_VERSION,
        "input_sha256": input_sha256,
        "mode": "dated_plan",
        "variants": variants,
        "stopped_at_limit": any(item["stopped_at_limit"] for item in variants),
    }
    signature_payload = deepcopy(proposal)
    proposal["deterministic_signature"] = sha256(
        json.dumps(
            signature_payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return proposal


def validate_variant(snapshot: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    """Recheck a proposal independently; never trust solver construction alone."""
    usable_statuses = _usable_route_statuses(snapshot)

    errors: list[dict[str, Any]] = []
    visits: dict[str, dict[str, Any]] = {}
    for day in variant.get("days", []):
        window = _window_for(snapshot, day["date"])
        previous_end = _minutes(window["start"])
        for item in day.get("items", []):
            start = _minutes(item["start"])
            end = _minutes(item["end"])
            if start < previous_end or end < start:
                errors.append(
                    {
                        "code": "TIMELINE_OVERLAP_OR_NEGATIVE_SLACK",
                        "subject_id": day["date"],
                    }
                )
            if start < _minutes(window["start"]) or end > _minutes(window["end"]):
                errors.append(
                    {"code": "OUTSIDE_USABLE_WINDOW", "subject_id": item.get("subject_id")}
                )
            previous_end = end
            if item["type"] == "visit":
                subject = item["subject_id"]
                if subject in visits:
                    errors.append({"code": "DUPLICATE_VISIT", "subject_id": subject})
                visits[subject] = item
                opening = _planning_fact(snapshot, subject, "opening_interval")
                if opening and (
                    not _inside(item, opening["value"])
                    or not _open_on(opening, day["date"])
                ):
                    errors.append({"code": "CLOSED_DURING_VISIT", "subject_id": subject})
                show = _verified_fact(snapshot, subject, "show_intervals")
                if show and not any(_inside(item, interval) for interval in show["value"]):
                    errors.append({"code": "SHOW_INTERVAL_MISSED", "subject_id": subject})
            if item["type"] == "travel" and item.get("status") not in usable_statuses:
                errors.append(
                    {"code": "ROUTE_UNVERIFIED", "subject_id": item.get("subject_id")}
                )

    selected_ids = {_candidate_id(item) for item in _selected_candidates(snapshot)}
    reconciliation = variant.get("reconciliation", [])
    reconciled_ids = [item["place_id"] for item in reconciliation]
    if len(reconciled_ids) != len(set(reconciled_ids)) or set(reconciled_ids) != selected_ids:
        errors.append({"code": "SELECTION_RECONCILIATION_INCOMPLETE", "subject_id": None})

    locked = {
        str(lock.get("subject_id") or lock.get("place_id")): lock
        for lock in snapshot.get("locks", [])
    }
    for subject, lock in locked.items():
        visit = visits.get(subject)
        if not visit:
            errors.append({"code": "LOCK_MISSING", "subject_id": subject})
            continue
        if lock.get("date") and visit["date"] != lock["date"]:
            errors.append({"code": "LOCK_DATE_CHANGED", "subject_id": subject})
        if lock.get("start") and visit["start"] != lock["start"]:
            errors.append({"code": "LOCK_TIME_CHANGED", "subject_id": subject})

    metrics = variant.get("metrics", {})
    thresholds = _thresholds(snapshot)
    for rule in COMFORT_RULES:
        measured = float(
            metrics.get(rule["metric"], metrics.get(rule["fallback_metric"], 0) or 0)
        )
        cap = int(thresholds.get(rule["threshold"], 10**9))
        if measured > cap and not _accepts(snapshot, rule["reason"], measured):
            errors.append({"code": rule["code"], "subject_id": None})

    meal_window = _meal_window(snapshot)
    if meal_window:
        for visit in visits.values():
            if visit.get("kind") == "meal" and not _inside(visit, meal_window):
                errors.append({"code": "UNAPPROVED_MEAL_WINDOW", "subject_id": visit["subject_id"]})

    candidate_by_id = {_candidate_id(item): item for item in snapshot["candidates"]}
    for subject, visit in visits.items():
        candidate = candidate_by_id.get(subject, {})
        if candidate.get("requires_access_evidence") and _access_gap(snapshot, candidate):
            errors.append({"code": "ACCESS_UNVERIFIED", "subject_id": subject})
    allowed_facts = [
        fact
        for fact in snapshot.get("facts", [])
        if fact.get("fact_type") == "allowed_transport_modes"
        and fact.get("status") == "verified"
    ]
    travel_items = [
        item
        for day in variant.get("days", [])
        for item in day.get("items", [])
        if item["type"] == "travel"
    ]
    for fact in allowed_facts:
        subject = fact["subject_id"]
        relevant = [
            item
            for item in travel_items
            if subject in {item.get("origin_id"), item.get("destination_id")}
        ]
        if not relevant and len(visits) == 1 and subject in visits:
            relevant = travel_items
        if any(item.get("mode") not in set(fact["value"]) for item in relevant):
            errors.append({"code": "TRANSPORT_MODE_PROHIBITED", "subject_id": subject})

    high_heat = any(
        fact.get("fact_type") == "heat_exposure"
        and fact.get("status") == "verified"
        and fact.get("value") == "high"
        for fact in snapshot.get("facts", [])
    )
    if high_heat and thresholds.get("heat_exposure") in {"low", "medium"} and {
        "walk",
        "bike",
    } & set(metrics.get("selected_modes", [])):
        errors.append({"code": "UNAPPROVED_HEAT_EXPOSURE", "subject_id": None})

    return {
        "valid": not errors,
        "hard_violations": errors,
        "scheduled_visit_count": len(visits),
        "selected_reconciled_count": len(reconciled_ids),
        "continuous_timeline": not any(
            item["code"] == "TIMELINE_OVERLAP_OR_NEGATIVE_SLACK" for item in errors
        ),
    }


def _solve_variant(
    snapshot: dict[str, Any], config: dict[str, Any], *, deadline: float
) -> dict[str, Any]:
    prepared = _prepare_candidates(snapshot, config)
    active = prepared["active"]
    active, fatigue_reconciliation = _apply_physical_load_limit(snapshot, active)
    prepared["reconciliation"].update(fatigue_reconciliation)

    schedules, skipped, stopped = _insertion_search(
        snapshot, active, config, deadline=deadline
    )
    scheduled_ids = {
        item["subject_id"]
        for day in schedules
        for item in day["items"]
        if item["type"] == "visit"
    }
    # Measured before the reconciliation rather than after it, because `_skip_reason`
    # now names a threshold only where one was actually exceeded and needs the numbers
    # to say so. Depends on nothing the loop produces.
    metrics = _schedule_metrics(snapshot, schedules)
    reconciliation = []
    selected = _selected_candidates(snapshot)
    for candidate in sorted(selected, key=lambda item: _candidate_id(item)):
        place_id = _candidate_id(candidate)
        if place_id in prepared["reconciliation"]:
            reconciliation.append(prepared["reconciliation"][place_id])
        elif place_id in scheduled_ids:
            reconciliation.append(
                _reconciliation(candidate, "fits", "SCHEDULED", "scheduled_once")
            )
        else:
            reconciliation.append(
                _reconciliation(
                    candidate,
                    "cannot_currently_fit",
                    _skip_reason(snapshot, candidate, skipped, metrics),
                    "kept_in_unscheduled_shortlist",
                )
            )

    objective = _objective(snapshot, selected, scheduled_ids, metrics, reconciliation)
    baseline = _greedy_baseline(snapshot, active, selected, config)
    variant = {
        "variant_id": config["id"],
        "status": "unavailable",
        "days": schedules,
        "reconciliation": reconciliation,
        "fallbacks": prepared["fallbacks"],
        "hotel_recommendation": prepared["hotel_recommendation"],
        "warnings": sorted(set(prepared["warnings"] + metrics["warnings"])),
        "metrics": metrics,
        "objective": objective,
        "objective_tuple": [
            objective["hard_violations"],
            objective["must_do_unscheduled"],
            objective["comfort_violations"],
            -objective["experience_value"],
            objective["dead_travel_minutes"],
            -objective["lower_priority_scheduled"],
        ],
        "greedy_baseline": baseline,
        "stopped_at_limit": stopped,
        "limit_action": "optimize_longer" if stopped else None,
    }
    validation = validate_variant(snapshot, variant)
    variant["validation"] = validation
    variant["objective"]["hard_violations"] = len(validation["hard_violations"])
    variant["objective_tuple"][0] = len(validation["hard_violations"])
    variant["objective_improved_or_equal_to_greedy"] = (
        variant["objective_tuple"] <= baseline["objective_tuple"]
    )
    has_unaccepted_tradeoff = any(
        item["status"] == "fits_with_tradeoff" for item in reconciliation
    )
    if validation["valid"] and validation["scheduled_visit_count"]:
        variant["status"] = (
            "provisional"
            if snapshot["trip"].get("provisional") or has_unaccepted_tradeoff
            else "ready"
        )
    elif not validation["scheduled_visit_count"]:
        variant["warnings"].append("NO_SELECTED_PLACE_COULD_BE_SCHEDULED")
    return variant


def _prepare_candidates(
    snapshot: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    candidates = { _candidate_id(item): deepcopy(item) for item in snapshot["candidates"] }
    active = [deepcopy(item) for item in _selected_candidates(snapshot)]
    reconciliation: dict[str, dict[str, Any]] = {}
    fallbacks: list[dict[str, Any]] = []
    warnings: list[str] = list(snapshot["trip"].get("capability_gaps", []))
    alternatives = [
        item
        for item in snapshot["candidates"]
        if item.get("priority") in {"alternative", "backup"}
    ]

    rain = any(
        fact.get("status") == "verified"
        and fact.get("fact_type") == "weather"
        and isinstance(fact.get("value"), dict)
        and fact["value"].get("condition") in {"rain", "storm", "heavy_rain"}
        for fact in snapshot.get("facts", [])
    )
    prepared: list[dict[str, Any]] = []
    for candidate in active:
        place_id = _candidate_id(candidate)
        kind = candidate.get("kind", "attraction")

        if rain and candidate.get("weather_exposure") == "outdoor":
            backup = next(
                (
                    item
                    for item in snapshot["candidates"]
                    if _candidate_id(item) != place_id
                    if item.get("weather_exposure") == "indoor"
                    and _opening_overlaps_trip(snapshot, item, config)
                    and _fallback_route_compatible(snapshot, place_id, _candidate_id(item))
                ),
                None,
            )
            if backup:
                replacement = deepcopy(backup)
                replacement["replaces"] = place_id
                prepared.append(replacement)
                reconciliation[place_id] = _reconciliation(
                    candidate,
                    "cannot_currently_fit",
                    "RAIN_FALLBACK_ACTIVATED",
                    f"replaced_by:{_candidate_id(backup)}",
                )
                fallbacks.append(
                    {
                        "primary_id": place_id,
                        "fallback_id": _candidate_id(backup),
                        "trigger": "rain",
                        "status": "activated",
                        "day_reoptimized": True,
                    }
                )
                continue
            reconciliation[place_id] = _reconciliation(
                candidate,
                "cannot_currently_fit",
                "NO_VERIFIED_WEATHER_FALLBACK",
                "broader_replan_required",
            )
            continue

        access_gap = _access_gap(snapshot, candidate)
        if access_gap:
            reconciliation[place_id] = _reconciliation(
                candidate,
                "cannot_currently_fit",
                access_gap,
                "verify:" + ",".join(_missing_access_fields(snapshot, place_id)),
            )
            continue

        if candidate.get("requires_opening_evidence") and not _planning_fact(
            snapshot, place_id, "opening_interval"
        ):
            reconciliation[place_id] = _reconciliation(
                candidate,
                "cannot_currently_fit",
                "OPENING_UNVERIFIED",
                "verify_dated_opening_hours",
            )
            continue
        if not _opening_overlaps_trip(snapshot, candidate, config):
            reconciliation[place_id] = _reconciliation(
                candidate,
                "cannot_currently_fit",
                "CLOSED_AT_AVAILABLE_TIME",
                "move_date_or_drop_place",
            )
            continue
        if _verified_fact(snapshot, place_id, "show_intervals") and not _show_fits_trip(
            snapshot, candidate
        ):
            reconciliation[place_id] = _reconciliation(
                candidate,
                "cannot_currently_fit",
                "SHOW_TYPE_UNAVAILABLE_AT_TIME",
                "choose_a_verified_show_time",
            )
            continue

        weak_value = _verified_fact(snapshot, place_id, "expected_value_signal")
        if weak_value and isinstance(weak_value["value"], dict) and weak_value["value"].get(
            "uniqueness"
        ) == "low":
            reconciliation[place_id] = _reconciliation(
                candidate,
                "cannot_currently_fit",
                "WEAK_VALUE_FOR_EFFORT",
                "keep_as_optional_or_choose_stronger_evidence",
            )
            continue

        risk = _verified_fact(snapshot, place_id, "tourist_trap_risk")
        if risk and risk.get("value") == "high" and _dislikes(snapshot, "tourist_traps"):
            alternative = next(
                (item for item in alternatives if item.get("kind") == kind), None
            )
            reconciliation[place_id] = _reconciliation(
                candidate,
                "cannot_currently_fit",
                "TOURIST_TRAP_RISK",
                f"alternative:{_candidate_id(alternative)}" if alternative else "owner_decision",
            )
            if alternative:
                prepared.append(deepcopy(alternative))
            continue

        queue = _verified_fact(snapshot, place_id, "queue_wait_minutes")

        # `long_queues`. The same fact the meal check below has always used, asked of
        # every kind rather than only of meals -- a two-hour queue for a viewpoint was
        # simply scheduled. The threshold is the owner's own if they set one.
        if queue and _dislikes(snapshot, "long_queues"):
            limit = int(_thresholds(snapshot).get("maximum_queue_minutes", 45))
            if int(queue["value"]) > limit:
                alternative = next(
                    (item for item in alternatives if item.get("kind") == kind), None
                )
                reconciliation[place_id] = _reconciliation(
                    candidate,
                    "cannot_currently_fit",
                    "QUEUE_LONGER_THAN_ACCEPTED",
                    f"alternative:{_candidate_id(alternative)}" if alternative else "owner_decision",
                )
                if alternative:
                    prepared.append(deepcopy(alternative))
                continue

        # `late_meals`. `QUEUE_CAUSES_LATE_MEAL` below only fires when a queue is known,
        # so a meal that runs past the window on its own duration was accepted in
        # silence. This asks the same question with no queue in it.
        if (
            kind == "meal"
            and _dislikes(snapshot, "late_meals")
            and _meal_finishes_late(snapshot, candidate)
        ):
            alternative = next(
                (item for item in alternatives if item.get("kind") == "meal"), None
            )
            reconciliation[place_id] = _reconciliation(
                candidate,
                "cannot_currently_fit",
                "LATE_MEAL_NOT_ACCEPTED",
                f"alternative:{_candidate_id(alternative)}" if alternative else "choose_earlier_meal",
            )
            if alternative:
                prepared.append(deepcopy(alternative))
            continue

        if queue and kind == "meal" and _queue_breaks_meal_window(snapshot, candidate, queue):
            alternative = next(
                (item for item in alternatives if item.get("kind") == "meal"), None
            )
            reconciliation[place_id] = _reconciliation(
                candidate,
                "cannot_currently_fit",
                "QUEUE_CAUSES_LATE_MEAL",
                f"alternative:{_candidate_id(alternative)}" if alternative else "choose_earlier_meal",
            )
            if alternative:
                prepared.append(deepcopy(alternative))
            continue

        allowed = _verified_fact(snapshot, place_id, "allowed_transport_modes")
        if allowed:
            route = _activity_route(snapshot, candidate, allowed["value"])
            if not route:
                reconciliation[place_id] = _reconciliation(
                    candidate,
                    "cannot_currently_fit",
                    "TRANSPORT_MODE_PROHIBITED",
                    "choose_a_verified_allowed_mode",
                )
                continue
            if _route_breaks_heat_or_cycling(snapshot, route):
                reconciliation[place_id] = _reconciliation(
                    candidate,
                    "cannot_currently_fit",
                    "HEAT_AND_CYCLING_LOAD",
                    "choose_a_shorter_or_lower_exposure_mode",
                )
                continue
            candidate["_activity_route"] = route
        elif len(active) == 1:
            standalone = _standalone_activity_route(snapshot, place_id)
            if standalone:
                if _route_breaks_heat_or_cycling(snapshot, standalone):
                    reconciliation[place_id] = _reconciliation(
                        candidate,
                        "cannot_currently_fit",
                        "HEAT_AND_CYCLING_LOAD",
                        "choose_a_shorter_or_lower_exposure_mode",
                    )
                    continue
                candidate["_activity_route"] = standalone

        if candidate.get("requires_route_evidence") and not _has_incident_usable_route(
            snapshot, place_id
        ):
            reconciliation[place_id] = _reconciliation(
                candidate,
                "cannot_currently_fit",
                "ROUTE_UNVERIFIED",
                "collect_a_verified_route",
            )
            continue
        prepared.append(candidate)

    # Avoid scheduling an original alternative twice when it was promoted above.
    unique = { _candidate_id(item): item for item in prepared }
    return {
        "active": list(unique.values()),
        "reconciliation": reconciliation,
        "fallbacks": fallbacks,
        "hotel_recommendation": _hotel_recommendation(snapshot, candidates),
        "warnings": warnings,
    }


def _insertion_search(
    snapshot: dict[str, Any],
    candidates: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    deadline: float,
) -> tuple[list[dict[str, Any]], set[str], bool]:
    dates = [window["date"] for window in snapshot["trip"]["usable_windows"]]
    states: list[tuple[dict[str, list[dict[str, Any]]], set[str]]] = [
        ({day: [] for day in dates}, set())
    ]
    ordered = sorted(candidates, key=lambda item: _candidate_sort_key(snapshot, item))
    stopped = False
    for index, candidate in enumerate(ordered):
        if monotonic() >= deadline:
            stopped = True
            remaining = {_candidate_id(item) for item in ordered[index:]}
            sequences, skipped = states[0]
            skipped = skipped | remaining
            # `WF-043`. The beam holds only the candidates reached so far, so cutting
            # out early can leave almost nothing scheduled -- measured at 0 of 13 on
            # the pilot, against a greedy pass that placed all 13. Greedy sweeps every
            # candidate and has no time limit, so it is a floor we can always afford.
            # Returning worse than a schedule already in hand is never right.
            greedy = _greedy_sequences(snapshot, ordered, config)
            if _search_objective(
                snapshot, greedy[0], greedy[1], ordered, config
            ) < _search_objective(snapshot, sequences, skipped, ordered, config):
                sequences, skipped = greedy
            states = [(sequences, skipped)]
            break
        place_id = _candidate_id(candidate)
        generated: list[tuple[dict[str, list[dict[str, Any]]], set[str]]] = []
        for sequences, skipped in states:
            for day in dates:
                lock = _lock_for(snapshot, place_id)
                if lock and lock.get("date") and lock["date"] != day:
                    continue
                for position in range(len(sequences[day]) + 1):
                    proposal = {key: list(value) for key, value in sequences.items()}
                    proposal[day].insert(position, candidate)
                    built = _build_schedules(snapshot, proposal, config)
                    if not built["hard_errors"]:
                        generated.append((proposal, set(skipped)))
            if candidate.get("priority", "interested") != "must_do":
                generated.append((sequences, skipped | {place_id}))
        if not generated:
            sequences, skipped = states[0]
            generated = [(sequences, skipped | {place_id})]

        unique: dict[tuple[Any, ...], tuple[dict[str, list[dict[str, Any]]], set[str]]] = {}
        for state in generated:
            signature = tuple(
                (day, tuple(_candidate_id(item) for item in state[0][day])) for day in dates
            )
            unique.setdefault(signature, state)
        processed = ordered[: index + 1]
        states = sorted(
            unique.values(),
            key=lambda state: _search_objective(
                snapshot, state[0], state[1], processed, config
            ),
        )[:64]

    sequences, skipped = states[0]
    built = _build_schedules(snapshot, sequences, config)
    return built["days"], skipped, stopped


def _build_schedules(
    snapshot: dict[str, Any],
    sequences: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
) -> dict[str, Any]:
    days = []
    hard_errors: list[dict[str, Any]] = []
    if snapshot["trip"].get("include_operational_timeline"):
        days.append(_pre_trip_day(snapshot))
    for day, sequence in sequences.items():
        built = _build_day(snapshot, day, sequence, config)
        hard_errors.extend(built["hard_errors"])
        days.append(built["day"])
    return {"days": days, "hard_errors": hard_errors}


def _build_day(
    snapshot: dict[str, Any],
    day: str,
    sequence: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    window = _window_for(snapshot, day)
    current = _minutes(window["start"])
    window_end = _minutes(window["end"])
    items: list[dict[str, Any]] = []
    hard_errors: list[dict[str, Any]] = []
    previous: str | None = None

    operational = _operational_layout(snapshot, day, window, sequence)
    for block in operational["prefix"]:
        current = _append_operational(items, day, current, block)
    body_end = window_end - sum(block["duration_minutes"] for block in operational["suffix"])
    # `WF-042`. Refuse only when something was actually going to happen here. An
    # overflowing day with nothing scheduled on it used to abort the same way, and
    # because `_greedy_baseline` accepts a placement only when **every** day builds
    # clean, one unusable day emptied the entire trip. Such a day now lays its
    # logistics out honestly instead; the independent validator still judges whether
    # they fit, which is not this function's call to make.
    if current > body_end and (sequence or items):
        hard_errors.append({"code": "OPERATIONAL_TIMELINE_EXCEEDS_DAY", "subject_id": day})
        return {
            "day": {
                "date": day,
                "window": {"start": window["start"], "end": window["end"]},
                "items": items,
            },
            "hard_errors": hard_errors,
        }
    meals = list(operational["meals"])

    for candidate in sequence:
        place_id = _candidate_id(candidate)
        while True:
            segment = _candidate_segment(
                snapshot,
                day,
                candidate,
                previous,
                config,
                current,
            )
            if segment["error"]:
                hard_errors.append(segment["error"])
                break
            due = meals[0] if meals else None
            if due and (
                current >= due["earliest"] or segment["end"] > due["latest_start"]
            ):
                if max(current, due["earliest"]) > due["latest_start"]:
                    hard_errors.append(
                        {"code": "MANDATORY_MEAL_WINDOW_MISSED", "subject_id": due["kind"]}
                    )
                    break
                current = _append_wait(
                    items, day, current, max(current, due["earliest"]), "meal_window"
                )
                current = _append_operational(items, day, current, due)
                meals.pop(0)
                continue
            if segment["end"] > body_end:
                hard_errors.append({"code": "DAY_WINDOW_EXCEEDED", "subject_id": place_id})
                break
            items.extend(segment["items"])
            current = segment["end"]
            previous = place_id
            break

    for meal in meals:
        start = max(current, meal["earliest"])
        if start > meal["latest_start"] or start + meal["duration_minutes"] > body_end:
            hard_errors.append(
                {"code": "MANDATORY_MEAL_WINDOW_MISSED", "subject_id": meal["kind"]}
            )
            continue
        current = _append_wait(items, day, current, start, "meal_window")
        current = _append_operational(items, day, current, meal)

    if snapshot["trip"].get("include_operational_timeline"):
        # The trailing gap gets its own reason. It is the *evening*, not a hole the
        # planner failed to fill: on the owner's Singapore trip all 14 chosen places were
        # scheduled and the day still ran to 21:15, so the remainder was printed as a
        # 165-minute `BUFFER` and read as a fault. Same row, same honest length, named
        # for what it is. No frozen fixture sets `include_operational_timeline`, so this
        # branch is not reached by the 27 regressions.
        current = _append_wait(items, day, current, body_end, "day_ends_free")
        for block in operational["suffix"]:
            current = _append_operational(items, day, current, block)
    return {
        "day": {
            "date": day,
            "window": {"start": window["start"], "end": window["end"]},
            "items": items,
        },
        "hard_errors": hard_errors,
    }


def _candidate_segment(
    snapshot: dict[str, Any],
    day: str,
    candidate: dict[str, Any],
    previous: str | None,
    config: dict[str, Any],
    current: int,
) -> dict[str, Any]:
    """Build one candidate off to the side so a due meal can precede it."""

    place_id = _candidate_id(candidate)
    cursor = current
    segment: list[dict[str, Any]] = []
    route = (
        _best_inbound_route(snapshot, place_id)
        if previous is None
        else _best_route(snapshot, previous, place_id)
    )
    if route:
        departure = _minutes(route["departure_time"]) if route.get("departure_time") else cursor
        if departure < cursor:
            return {
                "items": [],
                "end": cursor,
                "error": {"code": "MISSED_ROUTE_DEPARTURE", "subject_id": place_id},
            }
        cursor = _append_wait(segment, day, cursor, departure, "route_departure")
        route_end = cursor + int(route.get("duration_minutes", 0))
        travel_item = _travel_item(
            day, cursor, route_end, previous, place_id, route, snapshot
        )
        segment.append(travel_item)
        cursor = route_end
        boarding = max(
            int(route.get("boarding_buffer_minutes", 0)),
            _required_boarding_buffer(snapshot, place_id),
        )
        travel_item["boarding_buffer_minutes"] = boarding
        if boarding:
            segment.append(_buffer_item(day, cursor, cursor + boarding, "boarding"))
            cursor += boarding
        if config["buffer_minutes"] and previous is not None:
            segment.append(
                _buffer_item(
                    day,
                    cursor,
                    cursor + config["buffer_minutes"],
                    "transfer_contingency",
                )
            )
            cursor += config["buffer_minutes"]
    elif previous is not None and snapshot["trip"].get("requires_route_evidence"):
        return {
            "items": [],
            "end": cursor,
            "error": {"code": "ROUTE_UNVERIFIED", "subject_id": place_id},
        }

    activity_route = candidate.get("_activity_route")
    if activity_route:
        route_end = cursor + int(activity_route.get("duration_minutes", 0))
        segment.append(
            _travel_item(day, cursor, route_end, place_id, place_id, activity_route, snapshot)
        )
        cursor = route_end

    duration = _duration(candidate, config["duration"])
    start = _earliest_visit_start(snapshot, candidate, day, cursor, duration)
    if start is None:
        return {
            "items": [],
            "end": cursor,
            "error": {"code": "NO_VALID_VISIT_INTERVAL", "subject_id": place_id},
        }
    cursor = _append_wait(segment, day, cursor, start, "timing_window")
    end = start + duration
    segment.append(
        {
            "type": "visit",
            "subject_id": place_id,
            "name": candidate.get("name") or place_id,
            "names": candidate.get("names", {}),
            "kind": candidate.get("kind", "attraction"),
            "date": day,
            "start": _clock(start),
            "end": _clock(end),
            "duration_minutes": duration,
            "priority": candidate.get("priority", "interested"),
            "score": float(candidate.get("score", 10)),
            "replaces": candidate.get("replaces"),
        }
    )
    return {"items": segment, "end": end, "error": None}


def _pre_trip_day(snapshot: dict[str, Any]) -> dict[str, Any]:
    day = (date.fromisoformat(snapshot["trip"]["local_dates"][0]) - timedelta(days=1)).isoformat()
    current = 19 * 60
    items: list[dict[str, Any]] = []
    for kind, duration in (
        ("pack_bags", 45),
        ("documents_and_tickets", 30),
        ("charge_and_alarm", 15),
    ):
        current = _append_operational(
            items,
            day,
            current,
            {"type": "preparation", "kind": kind, "duration_minutes": duration},
        )
    return {
        "date": day,
        "window": {"start": "19:00", "end": "20:30"},
        "items": items,
    }


def _operational_layout(
    snapshot: dict[str, Any],
    day: str,
    window: dict[str, Any],
    sequence: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Visible defaults shared by preview, active view, PDF, and workbook."""

    if not snapshot["trip"].get("include_operational_timeline"):
        return {"prefix": [], "meals": [], "suffix": []}
    dates = snapshot["trip"]["local_dates"]
    first, last = day == dates[0], day == dates[-1]
    prefix: list[dict[str, Any]] = []
    if first:
        terminal = snapshot["trip"].get("terminal") or {}
        prefix.extend(
            [
                {
                    "type": "logistics",
                    "kind": "airport_arrival",
                    "duration_minutes": 60,
                    "name": terminal.get("name"),
                    "latitude": terminal.get("latitude"),
                    "longitude": terminal.get("longitude"),
                },
                {
                    "type": "logistics",
                    "kind": "arrival_transfer",
                    "duration_minutes": 45,
                    "mode": "confirm",
                    "from_name": _terminal_name(snapshot, arrival=True),
                    "to_name": _base_name(snapshot),
                },
                {
                    "type": "logistics",
                    "kind": "accommodation_check_in",
                    "duration_minutes": 30,
                },
            ]
        )
    elif not last:
        prefix.append(
            {"type": "preparation", "kind": "day_preparation", "duration_minutes": 30}
        )

    suffix: list[dict[str, Any]]
    if last:
        terminal = snapshot["trip"].get("terminal") or {}
        extra = {
            "departure_transfer": {
                "mode": "confirm",
                "from_name": _base_name(snapshot),
                "to_name": _terminal_name(snapshot, arrival=False),
            }
        }
        suffix = [
            {
                "type": "logistics",
                "kind": kind,
                "duration_minutes": minutes,
                **extra.get(kind, {}),
            }
            for kind, minutes in DEPARTURE_LOGISTICS
        ]
        for block in suffix:
            if block["kind"] == "airport_departure":
                block.update(
                    name=terminal.get("name"),
                    latitude=terminal.get("latitude"),
                    longitude=terminal.get("longitude"),
                )
    else:
        suffix = [
            {
                "type": "logistics",
                "kind": "return_to_accommodation",
                "duration_minutes": 45,
                "mode": "confirm",
                "to_name": _base_name(snapshot),
            }
        ]

    body_start = _minutes(window["start"]) + sum(
        item["duration_minutes"] for item in prefix
    )
    body_end = _minutes(window["end"]) - sum(
        item["duration_minutes"] for item in suffix
    )
    selected_meals = sum(item.get("kind") == "meal" for item in sequence)
    lunch = _meal_window(snapshot) or {"start": "11:30", "end": "13:30"}
    slots = [
        ("breakfast", "07:00", "09:30", 45),
        ("lunch", lunch["start"], lunch["end"], 60),
        ("dinner", "17:30", "21:00", 60),
    ]
    if selected_meals:
        slots.pop(1)
    if selected_meals > 1:
        slots.pop(-1)
    meals = []
    for kind, start, end, duration in slots:
        earliest = max(body_start, _minutes(start))
        latest_end = min(body_end, _minutes(end))
        if earliest + duration <= latest_end:
            meals.append(
                {
                    "type": "meal",
                    "kind": kind,
                    "duration_minutes": duration,
                    "earliest": earliest,
                    "latest_start": latest_end - duration,
                }
            )
    return {"prefix": prefix, "meals": meals, "suffix": suffix}


def _append_operational(
    items: list[dict[str, Any]],
    day: str,
    current: int,
    block: dict[str, Any],
) -> int:
    kind = block["kind"]
    duration = int(block["duration_minutes"])
    english, thai, note_en, note_th = OPERATIONAL_COPY[kind]
    items.append(
        {
            "type": block["type"],
            "subject_id": f"{kind}:{day}",
            "name": block.get("name") or english,
            "names": {} if block.get("name") else {"en": english, "th": thai},
            "kind": kind,
            "date": day,
            "start": _clock(current),
            "end": _clock(current + duration),
            "duration_minutes": duration,
            "status": "assumed",
            "notes": {"en": note_en, "th": note_th},
            "from_name": block.get("from_name"),
            "to_name": block.get("to_name"),
            "mode": block.get("mode"),
            "reason": "confirm_after_booking",
            "latitude": block.get("latitude"),
            "longitude": block.get("longitude"),
        }
    )
    return current + duration


def _terminal_name(snapshot: dict[str, Any], *, arrival: bool) -> str:
    terminal = snapshot["trip"].get("terminal") or {}
    if terminal.get("name"):
        return str(terminal["name"])
    destination = snapshot["trip"].get("destination") or "Destination"
    direction = "arrival" if arrival else "departure"
    return f"{destination} {direction} airport / station (confirm)"


def _base_name(snapshot: dict[str, Any]) -> str:
    return (
        "Booked accommodation base"
        if snapshot["trip"].get("accommodation_status") == "booked"
        else "Provisional accommodation area"
    )


def _schedule_metrics(
    snapshot: dict[str, Any], days: list[dict[str, Any]]
) -> dict[str, Any]:
    visits = [item for day in days for item in day["items"] if item["type"] == "visit"]
    travel = [item for day in days for item in day["items"] if item["type"] == "travel"]
    buffers = [
        item
        for day in days
        for item in day["items"]
        if item["type"] == "buffer"
        and item.get("reason") not in {"free_time_or_rest", "day_ends_free"}
    ]
    meals = [item for day in days for item in day["items"] if item["type"] == "meal"]
    preparation = [
        item for day in days for item in day["items"] if item["type"] == "preparation"
    ]
    logistics = [
        item for day in days for item in day["items"] if item["type"] == "logistics"
    ]
    plain_walk = sum(
        item.get("walking_minutes", 0)
        for item in travel
        if not item.get("experience_evidence")
    )
    rewarding_walk = sum(
        item.get("walking_minutes", 0)
        for item in travel
        if item.get("experience_evidence")
    )
    # The comfort budget `plain_walking_minutes_per_day` is a **daily** figure, so
    # it needs a daily measurement. `plain_walking_minutes` above is the whole-trip
    # sum, and comparing that against a per-day budget makes an n-day trip n times
    # too strict. It went unnoticed because 25 of the 27 historic fixtures are
    # single-day and 2 are two-day, where the two readings very nearly coincide.
    # Measured on the real 8-day Taipei trip: 147 minutes of plain walking over the
    # whole trip -- about 18 a day -- failed a 60-a-day budget.
    worst_plain_walk = max(
        (
            sum(
                item.get("walking_minutes", 0)
                for item in day["items"]
                if item["type"] == "travel" and not item.get("experience_evidence")
            )
            for day in days
        ),
        default=0,
    )
    warnings = []
    if meals or preparation or logistics:
        warnings.append("OPERATIONAL_DETAILS_REQUIRE_CONFIRMATION")
    for item in travel:
        if item.get("claimed_experience") and not item.get("experience_supported_at_time"):
            warnings.append("ROUTE_EXPERIENCE_NOT_SUPPORTED_AT_SCHEDULED_TIME")
        if _crowd_risk(snapshot, item["destination_id"]) in {"medium", "high"}:
            warnings.append("CROWD_CONSEQUENCE_VISIBLE")
    return {
        "scheduled_visits": len(visits),
        "visit_minutes": sum(item["duration_minutes"] for item in visits),
        "travel_minutes": sum(item["duration_minutes"] for item in travel),
        "walking_minutes": sum(item.get("walking_minutes", 0) for item in travel),
        "plain_walking_minutes": plain_walk,
        "maximum_plain_walking_minutes_per_day": worst_plain_walk,
        "rewarding_walking_minutes": rewarding_walk,
        "cycling_minutes": sum(
            item["duration_minutes"] for item in travel if item.get("mode") == "bike"
        ),
        "buffer_minutes": sum(item["duration_minutes"] for item in buffers),
        "meal_minutes": sum(item["duration_minutes"] for item in meals),
        "preparation_minutes": sum(item["duration_minutes"] for item in preparation),
        "logistics_minutes": sum(item["duration_minutes"] for item in logistics),
        "maximum_walking_minutes_per_leg": max(
            (item.get("walking_minutes", 0) for item in travel), default=0
        ),
        "maximum_boarding_buffer_minutes": max(
            (item.get("boarding_buffer_minutes", 0) for item in travel), default=0
        ),
        "selected_modes": sorted({item.get("mode") for item in travel if item.get("mode")}),
        "route_experience_value": sum(
            1 for item in travel if item.get("experience_supported_at_time")
        ),
        "warnings": warnings,
    }


def _objective(
    snapshot: dict[str, Any],
    selected: list[dict[str, Any]],
    scheduled_ids: set[str],
    metrics: dict[str, Any],
    reconciliation: list[dict[str, Any]],
) -> dict[str, Any]:
    must = {
        _candidate_id(item) for item in selected if item.get("priority") == "must_do"
    }
    comfort = _comfort_violation_count(snapshot, metrics) + sum(
        1 for item in reconciliation if item["status"] == "fits_with_tradeoff"
    )
    experience = sum(
        float(item.get("score", 10))
        for item in selected
        if _candidate_id(item) in scheduled_ids
    )
    lower = sum(
        1
        for item in selected
        if _candidate_id(item) in scheduled_ids
        and item.get("priority", "interested") != "must_do"
    )
    return {
        "hard_violations": 0,
        "must_do_unscheduled": len(must - scheduled_ids),
        "comfort_violations": comfort,
        "experience_value": round(experience, 2),
        "dead_travel_minutes": metrics["travel_minutes"],
        "lower_priority_scheduled": lower,
    }


def _greedy_sequences(
    snapshot: dict[str, Any],
    candidates: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    """First-fit over every candidate: one cheap deterministic sweep, no time limit.

    Extracted for `WF-043` so `_insertion_search` can fall back to it. It considers
    **all** candidates where the beam search considers only those it reached, which is
    what makes it a safe floor rather than merely a baseline to report.
    """

    dates = [window["date"] for window in snapshot["trip"]["usable_windows"]]
    order = {day: index for index, day in enumerate(dates)}
    sequences: dict[str, list[dict[str, Any]]] = {day: [] for day in dates}
    skipped: set[str] = set()
    for candidate in sorted(candidates, key=lambda item: _candidate_sort_key(snapshot, item)):
        placed = False
        # Emptiest day first, not the first day that fits. Plain first-fit walks the
        # dates in order and takes the first day the schedule still builds on, which
        # fills day one to its ceiling before day two is offered anything -- the same
        # crammed shape `_day_crowding` exists to stop, arriving by a different route.
        # It matters because this is the floor the beam search falls back to when it
        # runs out of time, and a real city's catalogue is exactly where that happens.
        # Ties break on the date, so the sweep stays deterministic.
        for day in sorted(dates, key=lambda value: (len(sequences[value]), order[value])):
            lock = _lock_for(snapshot, _candidate_id(candidate))
            if lock and lock.get("date") and lock["date"] != day:
                continue
            proposal = {key: list(value) for key, value in sequences.items()}
            proposal[day].append(candidate)
            if not _build_schedules(snapshot, proposal, config)["hard_errors"]:
                sequences = proposal
                placed = True
                break
        if not placed:
            skipped.add(_candidate_id(candidate))
    return sequences, skipped


def _greedy_baseline(
    snapshot: dict[str, Any],
    candidates: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    sequences, skipped = _greedy_sequences(snapshot, candidates, config)
    built = _build_schedules(snapshot, sequences, config)
    metrics = _schedule_metrics(snapshot, built["days"])
    scheduled = {
        item["subject_id"]
        for day in built["days"]
        for item in day["items"]
        if item["type"] == "visit"
    }
    objective = _objective(snapshot, selected, scheduled, metrics, [])
    objective["hard_violations"] = len(built["hard_errors"]) + _missing_route_edges(
        snapshot, sequences
    )
    objective_tuple = [
        objective["hard_violations"],
        objective["must_do_unscheduled"],
        objective["comfort_violations"],
        -objective["experience_value"],
        objective["dead_travel_minutes"],
        -objective["lower_priority_scheduled"],
    ]
    return {
        "objective": objective,
        "objective_tuple": objective_tuple,
        "scheduled_place_ids": sorted(scheduled),
        "skipped_place_ids": sorted(skipped),
    }


def _day_crowding(days: list[dict[str, Any]]) -> int:
    """The sum of the squares of each day's visit count. Lower is better spread.

    **What it exists to stop.** Nothing in the objective preferred using a day, and
    `travel_minutes` actively preferred not to: every day the plan opens costs another
    base-to-place-and-back journey, so the cheapest arrangement of twelve places over
    seven days is to pile them onto as few days as possible. Measured on exactly that
    input before this existed -- twelve ordinary places, seven ordinary days, every pair
    fifteen minutes apart, nothing closed and no threshold set -- and all three variants
    scheduled all twelve places onto the last two days:

        best_balance     [0, 0, 0, 0, 0, 6, 6]
        relaxed          [0, 0, 0, 0, 4, 4, 4]
        more_highlights  [0, 0, 0, 0, 0, 3, 9]

    Five days of a seven-day trip carrying nothing but free time, reported as "the
    output trip is so weird, it has a lot of days that have only free times". Not one of
    those was a scheduling failure -- every place fitted, no rule was broken, and the
    reconciliation was empty. It was the plan the objective asked for.

    **Squares, not a count of empty days.** Both would fill the blank days, but a count
    is indifferent between `[6, 6]` and `[11, 1]` once neither day is empty, and squares
    are not: they fall as the load levels out, so one number expresses "use the days"
    and "do not cram one of them" together. On the input above it prefers
    `[2, 2, 2, 2, 2, 1, 1]` at 22 over `[0, 0, 0, 0, 0, 6, 6]` at 72.

    **Where it sits in the tuple is the whole design.** After `-experience`, so a
    smoother trip can never cost a place the owner chose; after the comfort count, so it
    cannot buy spread by breaking a threshold; and before `travel_minutes`, because a
    second hotel round trip is exactly the price of not spending a day indoors, and it
    is worth paying. A one-day trip has one arrangement and this is constant for it,
    which is why none of the 27 historic single-day regressions move.
    """

    return sum(
        sum(1 for item in day["items"] if item["type"] == "visit") ** 2 for day in days
    )


def _search_objective(
    snapshot: dict[str, Any],
    sequences: dict[str, list[dict[str, Any]]],
    skipped: set[str],
    processed: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[Any, ...]:
    built = _build_schedules(snapshot, sequences, config)
    metrics = _schedule_metrics(snapshot, built["days"])
    missing_route_edges = _missing_route_edges(snapshot, sequences)
    scheduled = {
        item["subject_id"]
        for day in built["days"]
        for item in day["items"]
        if item["type"] == "visit"
    }
    must_missing = sum(
        1
        for item in processed
        if item.get("priority") == "must_do" and _candidate_id(item) not in scheduled
    )
    soft = _comfort_violation_count(snapshot, metrics)
    experience = sum(float(item.get("score", 10)) for item in processed if _candidate_id(item) in scheduled)
    lower = sum(
        1
        for item in processed
        if _candidate_id(item) in scheduled and item.get("priority", "interested") != "must_do"
    )
    return (
        len(built["hard_errors"]),
        missing_route_edges,
        must_missing,
        soft,
        -experience,
        # Before travel, and deliberately. See `_day_crowding`.
        _day_crowding(built["days"]),
        metrics["travel_minutes"],
        -lower,
        len(skipped),
        tuple(tuple(_candidate_id(item) for item in sequences[day]) for day in sequences),
    )


def _comfort_violation_count(snapshot: dict[str, Any], metrics: dict[str, Any]) -> int:
    """Soft violations, which an acceptance also clears. `WF-039`.

    Suppressing only the hard error would leave the objective still counting the
    overage, and `comfort_violations` outranks `experience_value` in the tuple -- so the
    optimizer would go on preferring an **empty** schedule to an accepted one. Measured
    on `jp-shibuya-plain-walk-overload`, which returns 0 visits rather than 3 for exactly
    that reason. Consent has to reach both readings or it only half works.
    """

    thresholds = _thresholds(snapshot)
    count = 0
    for rule in COMFORT_RULES:
        measured = float(
            metrics.get(rule["metric"], metrics.get(rule["fallback_metric"], 0) or 0)
        )
        if measured > int(thresholds.get(rule["threshold"], 10**9)) and not _accepts(
            snapshot, rule["reason"], measured
        ):
            count += 1
    return count


def _apply_physical_load_limit(
    snapshot: dict[str, Any], candidates: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    limit = _thresholds(snapshot).get("physical_load_points_per_day")
    if limit is None:
        return candidates, {}
    active = list(candidates)
    removed: dict[str, dict[str, Any]] = {}
    while sum(float(item.get("physical_load_points", 0)) for item in active) > float(limit):
        removable = [item for item in active if item.get("priority") != "must_do"]
        if not removable:
            break
        candidate = max(
            removable,
            key=lambda item: (
                PRIORITY_ORDER.get(item.get("priority", "interested"), 9),
                float(item.get("physical_load_points", 0)),
                _candidate_id(item),
            ),
        )
        active.remove(candidate)
        removed[_candidate_id(candidate)] = _reconciliation(
            candidate,
            "cannot_currently_fit",
            "FATIGUE_THRESHOLD",
            f"daily_load_limit:{limit}",
        )
    return active, removed


def _hotel_recommendation(
    snapshot: dict[str, Any], candidates: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    accommodation_status = snapshot["trip"].get("accommodation_status")
    fixed_base_id = snapshot["trip"].get("accommodation_base_id")
    if accommodation_status not in {"unbooked", "booked"}:
        return None
    hotels = [item for item in candidates.values() if item.get("kind") == "hotel_area"]
    if accommodation_status == "booked":
        hotels = [item for item in hotels if _candidate_id(item) == fixed_base_id]
    destinations = [
        item
        for item in _selected_candidates(snapshot)
        if item.get("kind") != "hotel_area"
    ]
    if not hotels:
        return None
    scored = []
    for hotel in hotels:
        hotel_id = _candidate_id(hotel)
        total = 0
        missing = 0
        for destination in destinations:
            routes = _routes_between(snapshot, hotel_id, _candidate_id(destination), symmetric=True)
            if routes:
                total += min(int(route.get("duration_minutes", 0)) for route in routes)
            else:
                missing += 1
        scored.append((missing, total, hotel_id))
    scored.sort()
    winner = scored[0]
    runner = scored[1] if len(scored) > 1 else None
    return {
        "default_area_id": winner[2],
        "basis": candidates[winner[2]].get("planning_basis", "known_route_matrix"),
        "total_known_travel_minutes": winner[1],
        "missing_route_count": winner[0],
        "runner_up_area_id": runner[2] if runner else None,
        "runner_up_total_known_travel_minutes": runner[1] if runner else None,
        "travel_delta_minutes": (runner[1] - winner[1]) if runner else None,
        "pros": (
            ["booked_accommodation_used_as_base"]
            if accommodation_status == "booked"
            else ["lower_whole_trip_known_travel"]
        ),
        "cons": (
            []
            if accommodation_status == "booked"
            else ["hotel_quality_price_and_room_fit_not_evaluated"]
        ),
    }


def _stay_recommendations(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Reserve the arrival and departure logistics already present in every generated
    # plan. Omitting them made the date recommendation optimistic and forced the owner
    # to add a day immediately after accepting it.
    minutes = 315 + sum(_duration(item, "ideal") + 30 for item in candidates)
    minimum = max(1, ceil(minutes / 540))
    balanced = max(minimum, ceil(minutes / 420))
    relaxed = max(balanced, ceil(minutes / 330))
    return [
        {"id": "minimum", "days": minimum, "daily_capacity_minutes": 540},
        {"id": "balanced", "days": balanced, "daily_capacity_minutes": 420},
        {"id": "relaxed", "days": relaxed, "daily_capacity_minutes": 330},
    ]


def _validate_input(snapshot: dict[str, Any]) -> None:
    required = {"trip", "travellers", "candidates", "facts", "routes", "locks", "weights", "thresholds"}
    if not isinstance(snapshot, dict) or required - set(snapshot):
        raise ValueError(f"Optimizer input is missing fields: {sorted(required - set(snapshot or {}))}")
    if not isinstance(snapshot["trip"], dict):
        raise ValueError("trip must be an object")
    for field in required - {"trip", "weights", "thresholds"}:
        if not isinstance(snapshot[field], list):
            raise ValueError(f"{field} must be a list")
    ids = [_candidate_id(item) for item in snapshot["candidates"]]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("Candidate IDs must be non-empty and unique")
    windows = snapshot["trip"].get("usable_windows", [])
    dates = snapshot["trip"].get("local_dates", [])
    if dates and (not windows or {item["date"] for item in windows} != set(dates)):
        raise ValueError("Every local date needs exactly one usable window")
    for window in windows:
        date.fromisoformat(window["date"])
        if _minutes(window["start"]) >= _minutes(window["end"]):
            raise ValueError("Usable window end must be after start")


def _selected_candidates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in snapshot["candidates"]
        if item.get("priority", "interested")
        not in {"backup", "alternative", "not_for_trip"}
        and item.get("kind") != "hotel_area"
    ]


def _candidate_id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("id") or candidate.get("place_id") or "")


def _candidate_sort_key(snapshot: dict[str, Any], candidate: dict[str, Any]) -> tuple[Any, ...]:
    place_id = _candidate_id(candidate)
    preferred = _verified_fact(
        snapshot, place_id, "best_time_interval"
    ) or _planning_fact(
        snapshot, place_id, "opening_interval"
    )
    start = _minutes(preferred["value"]["start"]) if preferred else 0
    return (
        PRIORITY_ORDER.get(candidate.get("priority", "interested"), 9),
        start,
        place_id,
    )


def _duration(candidate: dict[str, Any], choice: str) -> int:
    bounds = candidate.get("duration_bounds") or {}
    if bounds:
        key = {"minimum": "minimum_minutes", "ideal": "ideal_minutes", "maximum": "maximum_minutes"}[choice]
        fallback = bounds.get("ideal_minutes") or bounds.get("minimum_minutes") or 0
        return max(0, int(bounds.get(key, fallback)))
    return max(0, int(candidate.get("duration_minutes", 0)))


def _opening_overlaps_trip(
    snapshot: dict[str, Any], candidate: dict[str, Any], config: dict[str, Any]
) -> bool:
    fact = _planning_fact(snapshot, _candidate_id(candidate), "opening_interval")
    if not fact:
        return True
    duration = _duration(candidate, config["duration"])
    opening = fact["value"]
    return any(
        max(_minutes(window["start"]), _minutes(opening["start"])) + duration
        <= min(_minutes(window["end"]), _minutes(opening["end"]))
        for window in snapshot["trip"]["usable_windows"]
    )


def _show_fits_trip(snapshot: dict[str, Any], candidate: dict[str, Any]) -> bool:
    fact = _verified_fact(snapshot, _candidate_id(candidate), "show_intervals")
    if not fact:
        return True
    return any(
        _minutes(window["start"]) <= _minutes(show["start"])
        and _minutes(show["end"]) <= _minutes(window["end"])
        for window in snapshot["trip"]["usable_windows"]
        for show in fact["value"]
    )


def _earliest_visit_start(
    snapshot: dict[str, Any],
    candidate: dict[str, Any],
    day: str,
    current: int,
    duration: int,
) -> int | None:
    place_id = _candidate_id(candidate)
    window = _window_for(snapshot, day)
    latest = _minutes(window["end"])
    start = current
    opening = _planning_fact(snapshot, place_id, "opening_interval")
    if not _open_on(opening, day):
        return None
    if opening:
        start = max(start, _minutes(opening["value"]["start"]))
        latest = min(latest, _minutes(opening["value"]["end"]))
    show = _verified_fact(snapshot, place_id, "show_intervals")
    if show:
        starts = [
            _minutes(item["start"])
            for item in show["value"]
            if _minutes(item["start"]) >= start
            and _minutes(item["end"]) <= _minutes(window["end"])
        ]
        return min(starts) if starts else None
    best = _verified_fact(snapshot, place_id, "best_time_interval")
    if best and max(start, _minutes(best["value"]["start"])) + duration <= min(
        latest, _minutes(best["value"]["end"])
    ):
        start = max(start, _minutes(best["value"]["start"]))
        latest = min(latest, _minutes(best["value"]["end"]))
    meal = _meal_window(snapshot) if candidate.get("kind") == "meal" else None
    if meal:
        start = max(start, _minutes(meal["start"]))
        latest = min(latest, _minutes(meal["end"]))
    lock = _lock_for(snapshot, place_id)
    if lock:
        if lock.get("date") and lock["date"] != day:
            return None
        if lock.get("start"):
            locked_start = _minutes(lock["start"])
            if locked_start < start:
                return None
            start = locked_start
        if lock.get("end"):
            latest = min(latest, _minutes(lock["end"]))
    return start if start + duration <= latest else None


def _verified_fact(
    snapshot: dict[str, Any], subject_id: str, fact_type: str
) -> dict[str, Any] | None:
    return next(
        (
            fact
            for fact in snapshot.get("facts", [])
            if fact.get("subject_id") == subject_id
            and fact.get("fact_type") == fact_type
            and fact.get("status") == "verified"
            and fact.get("value") is not None
        ),
        None,
    )


def _open_on(fact: dict[str, Any] | None, day: str) -> bool:
    """Whether an opening fact applies on this date. `WF-041`.

    `applies_to_dates` lists the dates the window is good for, which excludes any the
    place is shut. A fact without the field applies everywhere, which keeps every
    frozen fixture valid -- they predate it.

    Before this the field was written and read by nothing, and a place shut on one
    trip day got no fact at all and so could not be scheduled on any day. Red House
    is open six of the pilot trip's seven days and was scheduled on none.
    """

    if not fact:
        return True
    dates = fact.get("applies_to_dates")
    return day in dates if dates else True


def _planning_fact(
    snapshot: dict[str, Any], subject_id: str, fact_type: str
) -> dict[str, Any] | None:
    """Verified fact, or a visible assumption allowed only for an Explore preview."""

    verified = _verified_fact(snapshot, subject_id, fact_type)
    if verified or not snapshot.get("trip", {}).get("allow_provisional_assumptions"):
        return verified
    return next(
        (
            fact
            for fact in snapshot.get("facts", [])
            if fact.get("subject_id") == subject_id
            and fact.get("fact_type") == fact_type
            and fact.get("status") == "assumed"
            and fact.get("value") is not None
        ),
        None,
    )


def _access_gap(snapshot: dict[str, Any], candidate: dict[str, Any]) -> str | None:
    place_id = _candidate_id(candidate)
    access = [
        fact
        for fact in snapshot.get("facts", [])
        if fact.get("subject_id") == place_id and fact.get("fact_type") in ACCESS_FACT_TYPES
    ]
    if any(fact.get("status") in {"unavailable", "stale", "conflicting", "error"} for fact in access):
        return "ENTRANCE_UNVERIFIED" if any(
            fact.get("fact_type") in {"entrance_coordinate", "approach_instruction"}
            for fact in access
        ) else "ACCESS_UNVERIFIED"
    if candidate.get("requires_access_evidence") and not any(
        fact.get("status") == "verified" and fact.get("value") is not None for fact in access
    ):
        return "ACCESS_UNVERIFIED"
    return None


def _missing_access_fields(snapshot: dict[str, Any], place_id: str) -> list[str]:
    missing = [
        str(fact.get("fact_type"))
        for fact in snapshot.get("facts", [])
        if fact.get("subject_id") == place_id
        and fact.get("fact_type") in ACCESS_FACT_TYPES
        and (fact.get("status") != "verified" or fact.get("value") is None)
    ]
    return sorted(missing) or ["access"]


def _dislikes(snapshot: dict[str, Any], value: str) -> bool:
    return any(
        value in traveller.get("preferences", {}).get("dislikes", [])
        for traveller in snapshot.get("travellers", [])
    ) or value in snapshot.get("preferences", {}).get("dislikes", [])


def _meal_finishes_late(
    snapshot: dict[str, Any], candidate: dict[str, Any], extra_minutes: int = 0
) -> bool:
    """Would this meal still be running after the meal window closes?

    `extra_minutes` is time that has to be spent before eating starts -- a queue,
    today. Asked with zero it answers the plainer question of whether the meal fits
    at all, which is what `late_meals` needs.
    """

    meal = _meal_window(snapshot)
    if not meal:
        return False
    earliest = min(
        _minutes(window["start"]) for window in snapshot["trip"]["usable_windows"]
    )
    finish = max(earliest, _minutes(meal["start"])) + extra_minutes + _duration(candidate, "ideal")
    return finish > _minutes(meal["end"])


def _queue_breaks_meal_window(
    snapshot: dict[str, Any], candidate: dict[str, Any], queue: dict[str, Any]
) -> bool:
    return _meal_finishes_late(snapshot, candidate, int(queue["value"]))


def _activity_route(
    snapshot: dict[str, Any], candidate: dict[str, Any], allowed_modes: list[str]
) -> dict[str, Any] | None:
    usable = _usable_route_statuses(snapshot)
    routes = [
        route
        for route in snapshot.get("routes", [])
        if route.get("status") in usable and route.get("mode") in set(allowed_modes)
    ]
    if not routes:
        return None
    thresholds = _thresholds(snapshot)
    heat_high = any(
        fact.get("fact_type") == "heat_exposure"
        and fact.get("status") == "verified"
        and fact.get("value") == "high"
        for fact in snapshot.get("facts", [])
    )
    def key(route: dict[str, Any]) -> tuple[Any, ...]:
        cycling_over = route.get("mode") == "bike" and int(route.get("duration_minutes", 0)) > int(
            thresholds.get("cycling_minutes_per_day", 10**9)
        )
        heat_penalty = route.get("mode") in {"bike", "walk"} and heat_high
        walk_over = int(route.get("walking_minutes", 0)) > int(
            thresholds.get("walking_minutes_per_leg", 10**9)
        )
        return cycling_over, heat_penalty, walk_over, int(route.get("duration_minutes", 0)), str(route.get("mode"))
    return deepcopy(min(routes, key=key))


def _standalone_activity_route(
    snapshot: dict[str, Any], place_id: str
) -> dict[str, Any] | None:
    if _has_incident_usable_route(snapshot, place_id):
        return None
    usable = _usable_route_statuses(snapshot)
    routes = [route for route in snapshot.get("routes", []) if route.get("status") in usable]
    if not routes:
        return None
    allowed = [str(route.get("mode")) for route in routes]
    return _activity_route(snapshot, {"id": place_id}, allowed)


def _route_breaks_heat_or_cycling(snapshot: dict[str, Any], route: dict[str, Any]) -> bool:
    thresholds = _thresholds(snapshot)
    if route.get("mode") == "bike" and int(route.get("duration_minutes", 0)) > int(
        thresholds.get("cycling_minutes_per_day", 10**9)
    ):
        return True
    heat_limit = thresholds.get("heat_exposure")
    heat_high = any(
        fact.get("fact_type") == "heat_exposure"
        and fact.get("status") == "verified"
        and fact.get("value") == "high"
        for fact in snapshot.get("facts", [])
    )
    return bool(heat_high and heat_limit in {"low", "medium"} and route.get("mode") in {"walk", "bike"})


def _best_route(snapshot: dict[str, Any], origin: str, destination: str) -> dict[str, Any] | None:
    routes = _routes_between(snapshot, origin, destination)
    if not routes:
        hotel_ids = {
            _candidate_id(item)
            for item in snapshot.get("candidates", [])
            if item.get("kind") == "hotel_area"
        }
        for hotel_id in sorted(hotel_ids):
            first = _routes_between(snapshot, origin, hotel_id)
            second = _routes_between(snapshot, hotel_id, destination)
            if first and second:
                left = min(first, key=lambda item: int(item.get("duration_minutes", 0)))
                right = min(second, key=lambda item: int(item.get("duration_minutes", 0)))
                routes.append(
                    {
                        "origin_id": origin,
                        "destination_id": destination,
                        "mode": left.get("mode")
                        if left.get("mode") == right.get("mode")
                        else "mixed",
                        "duration_minutes": int(left.get("duration_minutes", 0))
                        + int(right.get("duration_minutes", 0)),
                        "walking_minutes": int(left.get("walking_minutes", 0))
                        + int(right.get("walking_minutes", 0)),
                        "distance_m": None,
                        "status": "verified",
                        "via": [hotel_id],
                        "experience_evidence": [],
                    }
                )
                break
    if not routes:
        return None
    walk_limit = int(_thresholds(snapshot).get("walking_minutes_per_leg", 10**9))
    return deepcopy(
        min(
            routes,
            key=lambda item: (
                int(item.get("walking_minutes", 0)) > walk_limit,
                int(item.get("duration_minutes", 0)),
                int(item.get("walking_minutes", 0)),
                str(item.get("mode")),
            ),
        )
    )


def _best_inbound_route(snapshot: dict[str, Any], destination: str) -> dict[str, Any] | None:
    usable = _usable_route_statuses(snapshot)
    candidate_ids = {_candidate_id(candidate) for candidate in snapshot.get("candidates", [])}
    base_ids = {
        _candidate_id(candidate)
        for candidate in snapshot.get("candidates", [])
        if candidate.get("kind") == "hotel_area"
    }
    if not base_ids:
        base_ids = {
            str(route.get("origin_id"))
            for route in snapshot.get("routes", [])
            if route.get("origin_id") not in candidate_ids
        }
    routes = [
        route
        for route in snapshot.get("routes", [])
        if route.get("status") in usable
        and route.get("destination_id") == destination
        and route.get("origin_id") in base_ids
    ]
    return deepcopy(min(routes, key=lambda item: int(item.get("duration_minutes", 0)))) if routes else None


def _usable_route_statuses(snapshot: dict[str, Any]) -> set[str]:
    """`verified` and `estimated` always; `accepted_estimate` on an Explore preview.

    **`estimated` is the transit status, and only the transit status.** Exactly two
    things in this project produce it -- `GtfsTransitProvider` from a published
    timetable and `OsmSubwayProvider` from a subway relation's topology -- and both say
    so where they set it. Nothing else emits it, which is what makes admitting it a
    narrow rule rather than a relaxation.

    Why it used to be refused, and why that was wrong. `estimated` was grouped with
    `accepted_estimate` and both were held back from a `ready_to_schedule` trip, on the
    reasoning that "a plan that claims to be scheduled against verified evidence must
    not be resting on a guess". That is right about `accepted_estimate` and wrong about
    a timetable. The consequence was that on every ready-to-schedule trip the optimizer
    threw away **every metro leg it had been given** and planned the city on foot and by
    car alone -- reported as "why is the walking not considering the metro line too",
    which is precisely what it was doing. A published ride time is not a guess; it is
    evidence a router was not asked for, and `status: "estimated"` is already how the
    plan tells the reader that.

    `accepted_estimate` stays exactly where it was: a straight line the **owner asked
    for** where no router would answer, inflated by `ACCEPTED_ROUTE_DETOUR` so it can
    only over-state the journey. Deliberately fabricated, so it is admitted only on an
    Explore preview however conservative and however explicitly it was requested. The
    two statuses were already separate for this reason; this is the first thing to
    actually use the distinction.

    What is *not* softened: a leg with no route at all. `_missing_route_edges` and
    `ROUTE_UNVERIFIED` are unchanged, so admitting a real transit journey never becomes
    inventing one.
    """

    if snapshot.get("trip", {}).get("allow_provisional_assumptions"):
        return {"verified", "estimated", "accepted_estimate"}
    return {"verified", "estimated"}


def _routes_between(
    snapshot: dict[str, Any], origin: str, destination: str, *, symmetric: bool = False
) -> list[dict[str, Any]]:
    usable = _usable_route_statuses(snapshot)
    return [
        route
        for route in snapshot.get("routes", [])
        if route.get("status") in usable
        and (
            (route.get("origin_id") == origin and route.get("destination_id") == destination)
            or (
                symmetric
                and route.get("origin_id") == destination
                and route.get("destination_id") == origin
            )
        )
    ]


def _has_usable_route_between(snapshot: dict[str, Any], left: str, right: str) -> bool:
    return bool(_routes_between(snapshot, left, right, symmetric=True))


def _fallback_route_compatible(snapshot: dict[str, Any], left: str, right: str) -> bool:
    if _has_usable_route_between(snapshot, left, right):
        return True
    # The same statuses the line above already allows, through `_routes_between`. These
    # two sets read `"verified"` literally, so on an Explore trip the function contradicted
    # its own first line: a pair joined by a shared transit origin was called incompatible.
    usable = _usable_route_statuses(snapshot)
    left_origins = {
        route.get("origin_id")
        for route in snapshot.get("routes", [])
        if route.get("status") in usable and route.get("destination_id") == left
    }
    right_origins = {
        route.get("origin_id")
        for route in snapshot.get("routes", [])
        if route.get("status") in usable and route.get("destination_id") == right
    }
    return bool(left_origins & right_origins)


def _missing_route_edges(
    snapshot: dict[str, Any], sequences: dict[str, list[dict[str, Any]]]
) -> int:
    if not snapshot.get("routes"):
        return 0
    # `_best_route` below already reads through `_routes_between`, so building the
    # incident set on a literal `"verified"` counted a transit-only pair as having no
    # edge to miss — the metric and the scheduler disagreeing about the same snapshot.
    usable = _usable_route_statuses(snapshot)
    incident = {
        str(endpoint)
        for route in snapshot["routes"]
        if route.get("status") in usable
        for endpoint in (route.get("origin_id"), route.get("destination_id"))
        if endpoint
    }
    return sum(
        1
        for sequence in sequences.values()
        for left, right in zip(sequence, sequence[1:])
        if _candidate_id(left) in incident
        and _candidate_id(right) in incident
        and not _best_route(snapshot, _candidate_id(left), _candidate_id(right))
    )


def _has_incident_usable_route(snapshot: dict[str, Any], place_id: str) -> bool:
    """Is there any route this snapshot may plan with that touches this place?

    Through `_usable_route_statuses` rather than a literal `"verified"`, which is the
    fourth site `WF-038` needed and did not get. The other three — `validate_variant`,
    `_routes_between` and `_best_inbound_route` — admit an `estimated` route on an
    Explore trip, exactly as `_planning_fact` admits an assumed opening window; this one
    did not, so `_prepare_candidates` threw a place out before any of them ran. A trip
    holding 208 estimated transit legs still reported `ROUTE_UNVERIFIED` and
    `collect_a_verified_route` for a place reachable only by train.

    This admits a route the snapshot **has**. It does not invent one: a place with no
    route at all is still refused, because a fabricated travel time makes the whole
    day's chain of connections fiction and errs optimistic, which is the one direction
    an assumption here must not err in.
    """

    usable = _usable_route_statuses(snapshot)
    return any(
        route.get("status") in usable
        and place_id in {route.get("origin_id"), route.get("destination_id")}
        for route in snapshot.get("routes", [])
    )


def _travel_item(
    day: str,
    start: int,
    end: int,
    origin: str | None,
    destination: str,
    route: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    claimed = route.get("claimed_experience")
    supported = _route_experience_supported(snapshot, claimed, start) if claimed else False
    return {
        "type": "travel",
        "subject_id": f"{origin or 'start'}->{destination}",
        "origin_id": origin or route.get("origin_id"),
        "destination_id": destination,
        "date": day,
        "start": _clock(start),
        "end": _clock(end),
        "duration_minutes": end - start,
        "mode": route.get("mode"),
        "walking_minutes": int(route.get("walking_minutes", 0)),
        "distance_m": route.get("distance_m"),
        "transfers": route.get("transfers"),
        "boarding_buffer_minutes": int(route.get("boarding_buffer_minutes", 0)),
        "experience_evidence": list(route.get("experience_evidence", [])),
        "claimed_experience": claimed,
        "experience_supported_at_time": supported,
        "status": route.get("status"),
    }


def _route_experience_supported(
    snapshot: dict[str, Any], claimed: str | None, departure: int
) -> bool:
    if not claimed:
        return False
    fact = _verified_fact(snapshot, claimed, "supported_view_interval")
    return bool(
        fact
        and fact["value"]
        and _minutes(fact["value"]["start"]) <= departure <= _minutes(fact["value"]["end"])
    )


def _required_boarding_buffer(snapshot: dict[str, Any], place_id: str) -> int:
    if _crowd_risk(snapshot, place_id) != "high":
        return 0
    return int(_thresholds(snapshot).get("minimum_boarding_buffer_minutes", 0))


def _crowd_risk(snapshot: dict[str, Any], place_id: str) -> str | None:
    fact = _verified_fact(snapshot, place_id, "crowd_risk")
    return str(fact["value"]) if fact else None


def _meal_window(snapshot: dict[str, Any]) -> dict[str, str] | None:
    value = _thresholds(snapshot).get("meal_window")
    return value if isinstance(value, dict) and value.get("start") and value.get("end") else None


def _thresholds(snapshot: dict[str, Any]) -> dict[str, Any]:
    result = dict(snapshot.get("thresholds", {}))
    for traveller in snapshot.get("travellers", []):
        for key, value in traveller.get("comfort_thresholds", {}).items():
            if key not in result:
                result[key] = value
            elif isinstance(value, (int, float)) and isinstance(result[key], (int, float)):
                result[key] = min(result[key], value)
    return result


def _lock_for(snapshot: dict[str, Any], place_id: str) -> dict[str, Any] | None:
    return next(
        (
            lock
            for lock in snapshot.get("locks", [])
            if str(lock.get("subject_id") or lock.get("place_id")) == place_id
        ),
        None,
    )


def _window_for(snapshot: dict[str, Any], day: str) -> dict[str, Any]:
    match = next(
        (item for item in snapshot["trip"]["usable_windows"] if item["date"] == day),
        None,
    )
    if match:
        return match
    if snapshot["trip"].get("include_operational_timeline"):
        preparation_date = (
            date.fromisoformat(snapshot["trip"]["local_dates"][0]) - timedelta(days=1)
        ).isoformat()
        if day == preparation_date:
            return {"date": day, "start": "19:00", "end": "20:30"}
    raise ValueError(f"No usable window for {day}")


def _reconciliation(
    candidate: dict[str, Any], status: str, reason: str, consequence: str
) -> dict[str, Any]:
    return {
        "place_id": _candidate_id(candidate),
        "name": candidate.get("name") or _candidate_id(candidate),
        "names": candidate.get("names", {}),
        "priority": candidate.get("priority", "interested"),
        "status": status,
        "reason": reason,
        "consequence": consequence,
        "smallest_alternative": consequence,
        "owner_acceptance_required": status == "fits_with_tradeoff",
    }


def _skip_reason(
    snapshot: dict[str, Any],
    candidate: dict[str, Any],
    skipped: set[str],
    metrics: dict[str, Any],
) -> str:
    """Why a chosen place is not on the plan.

    Named from the **measurement**, not from the mere existence of a threshold. It used
    to answer `PLAIN_WALK_THRESHOLD` for every skipped place whenever a plain-walking
    cap was configured at all — and `balanced_pace` always configures one — so a
    two-day trip that simply had no room for a fifth museum blamed the owner's walking
    preference. Measured on the owner's Fukuoka trip: three places reported
    `PLAIN_WALK_THRESHOLD` while `comfort_tradeoffs` reported **21 minutes against a
    cap of 45 and nothing exceeded**. Two screens contradicting each other about one
    plan, and the "smallest next step" pointing at a setting that would have changed
    nothing.

    `COMFORT_RULES` is the one table the validator, the soft count and the tradeoff
    screen already read, so this reads it too rather than deriving a second opinion —
    the same rule `WF-018` sets for rounding and `WF-039` for consent.
    """

    if _candidate_id(candidate) not in skipped:
        return "NO_TIME_CAPACITY"
    thresholds = _thresholds(snapshot)
    for rule in COMFORT_RULES:
        measured = float(
            metrics.get(rule["metric"], metrics.get(rule["fallback_metric"], 0) or 0)
        )
        if measured <= int(thresholds.get(rule["threshold"], 10**9)) or _accepts(
            snapshot, rule["reason"], measured
        ):
            continue
        # A timetabled leg makes a walking overage a scheduling conflict rather than a
        # comfort one — the original distinction, kept, but now behind a real overage.
        if rule["reason"] == "LONG_TRANSFER_WALK" and any(
            route.get("departure_time") for route in snapshot.get("routes", [])
        ):
            return "EFFORT_OR_TIME_CONFLICT"
        return rule["reason"]
    return "NO_TIME_CAPACITY"


def _buffer_item(day: str, start: int, end: int, reason: str) -> dict[str, Any]:
    return {
        "type": "buffer",
        "subject_id": reason,
        "date": day,
        "start": _clock(start),
        "end": _clock(end),
        "duration_minutes": end - start,
        "reason": reason,
    }


#: Beyond this, a gap before a meal is not "waiting for the meal window" — it is an empty
#: afternoon that happens to end at dinner. Measured on the owner's Sapporo arrival day: a
#: single row read `12:30–17:30 · BUFFER · 300 min · meal_window`, which names the wrong
#: cause and reads as the planner having decided on a five-hour lunch break. Ninety minutes
#: is about the longest a genuine wait-for-opening can be while still being about the meal.
MEAL_WAIT_MAX_MINUTES = 90


def _append_wait(
    items: list[dict[str, Any]], day: str, current: int, target: int, reason: str
) -> int:
    if target > current:
        # An honest label, not a shorter row. The gap is real and is still shown at its
        # real length; only the reason changes, because a row's reason is what the owner
        # reads to decide whether it is a problem — and "free time" invites filling the
        # day where "meal window" says the planner needed it.
        if reason == "meal_window" and target - current > MEAL_WAIT_MAX_MINUTES:
            reason = "free_time_or_rest"
        items.append(_buffer_item(day, current, target, reason))
    return max(current, target)


def _inside(item: dict[str, Any], interval: dict[str, Any]) -> bool:
    return _minutes(interval["start"]) <= _minutes(item["start"]) and _minutes(
        item["end"]
    ) <= _minutes(interval["end"])


def _minutes(value: str) -> int:
    try:
        hour, minute = value.split(":", 1)
        result = int(hour) * 60 + int(minute)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid local time: {value!r}") from error
    if not (0 <= result <= 24 * 60) or int(minute) >= 60:
        raise ValueError(f"Invalid local time: {value!r}")
    return result


def _clock(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def date_range(start: str, end: str) -> list[str]:
    """Small shared helper for application snapshot assembly."""

    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return [
        (first + timedelta(days=offset)).isoformat()
        for offset in range((last - first).days + 1)
    ]
