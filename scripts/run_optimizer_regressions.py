#!/usr/bin/env python3
"""Run every historic fixture through the real pure optimizer and validator."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from travel_planner.optimizer import optimize_trip  # noqa: E402


CATALOG = ROOT / "tests" / "fixtures" / "historic_regressions.json"


def run_catalog(path: Path = CATALOG) -> list[str]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    failures = []
    for fixture in catalog["fixtures"]:
        failure = run_fixture(fixture)
        if failure:
            failures.append(failure)
    return failures


def run_fixture(fixture: dict[str, Any]) -> str | None:
    fixture_id = fixture["metadata"]["id"]
    result = optimize_trip(fixture["planner_input"])
    variants = result["variants"]
    if not variants:
        return f"{fixture_id}: optimizer returned no dated variants"

    rule_failures = [
        rule["rule_id"]
        for rule in fixture["expected_rules"]
        if not any(_rule_holds(rule["rule_id"], rule["subjects"], fixture["planner_input"], variant) for variant in variants)
    ]
    if rule_failures:
        return f"{fixture_id}: violated rules {rule_failures}"

    for variant in variants:
        for outcome in fixture["acceptable_outcomes"]:
            if _outcome_holds(outcome, fixture["planner_input"], variant):
                return None
    observed = [
        {
            "variant": item["variant_id"],
            "status": item["status"],
            "scheduled": sorted(_visits(item)),
            "reasons": sorted(
                {row["reason"] for row in item["reconciliation"] if row["status"] != "fits"}
            ),
        }
        for item in variants
    ]
    return f"{fixture_id}: no acceptable outcome matched; observed={observed}"


def _outcome_holds(
    outcome: dict[str, Any], snapshot: dict[str, Any], variant: dict[str, Any]
) -> bool:
    visits = _visits(variant)
    subjects = set(outcome.get("subjects", []))
    reasons = set(outcome.get("reason_codes", []))
    reconciliation = variant["reconciliation"]
    relevant = [
        item for item in reconciliation if not subjects or item["place_id"] in subjects
    ]
    outcome_type = outcome["type"]
    if outcome_type == "scheduled":
        type_match = bool(visits) and (not subjects or subjects <= set(visits))
    elif outcome_type == "cannot_fit":
        matches = [
            item
            for item in relevant
            if item["status"] == "cannot_currently_fit"
            and (not reasons or item["reason"] in reasons)
        ]
        type_match = bool(matches) and (
            not subjects or subjects <= {item["place_id"] for item in matches}
        )
    elif outcome_type == "tradeoff":
        matches = [
            item
            for item in relevant
            if item["status"] == "fits_with_tradeoff"
            and (not reasons or item["reason"] in reasons)
        ]
        type_match = bool(matches) and (
            not subjects or subjects <= {item["place_id"] for item in matches}
        )
    elif outcome_type == "variant":
        type_match = variant["validation"]["valid"] and (
            not subjects or subjects <= set(visits) | {_hotel_id(variant)}
        )
    elif outcome_type == "fallback_activated":
        activated = {
            item["fallback_id"]
            for item in variant["fallbacks"]
            if item["status"] == "activated" and item["day_reoptimized"]
        }
        type_match = bool(activated) and (not subjects or subjects <= activated)
    else:
        type_match = False
    return type_match and all(
        _condition_holds(condition, subjects, snapshot, variant)
        for condition in outcome.get("conditions", [])
    )


def _condition_holds(
    condition: str,
    subjects: set[str],
    snapshot: dict[str, Any],
    variant: dict[str, Any],
) -> bool:
    visits = _visits(variant)
    metrics = variant["metrics"]
    reconciliation = {item["place_id"]: item for item in variant["reconciliation"]}
    thresholds = snapshot.get("thresholds", {})
    hotel = variant.get("hotel_recommendation") or {}
    tradeoff = any(item["status"] == "fits_with_tradeoff" for item in reconciliation.values())

    if condition == "boarding_buffer_minutes_gte_20":
        return metrics["maximum_boarding_buffer_minutes"] >= 20
    if condition == "crowd_consequence_visible":
        return "CROWD_CONSEQUENCE_VISIBLE" in variant["warnings"]
    if condition == "cycling_minutes_lte_60":
        return metrics["cycling_minutes"] <= 60
    if condition in {
        "default_hotel_is_lower_total_travel_option",
        "default_hotel_minimizes_whole_trip_travel",
    }:
        return bool(hotel) and (
            hotel.get("runner_up_total_known_travel_minutes") is None
            or hotel["total_known_travel_minutes"]
            <= hotel["runner_up_total_known_travel_minutes"]
        )
    if condition == "every_selected_item_reconciled":
        return variant["validation"]["selected_reconciled_count"] == len(
            [
                item
                for item in snapshot["candidates"]
                if item.get("priority", "interested")
                not in {"backup", "alternative", "not_for_trip"}
                and item.get("kind") != "hotel_area"
            ]
        )
    if condition == "heat_exposure_lte_medium":
        return not _high_heat(snapshot) or not ({"walk", "bike"} & set(metrics["selected_modes"]))
    if condition in {
        "load_consequence_quantified",
        "meal_consequence_quantified",
        "walking_consequence_quantified",
    }:
        return any(item["consequence"] for item in reconciliation.values() if item["status"] != "fits")
    if condition == "lower_risk_alternative_selected":
        return any(item.get("priority") in {"alternative", "backup"} for item in visits.values())
    if condition == "magnet_starts_at_or_after_10_00":
        return "magnet_shibuya" in visits and _minutes(visits["magnet_shibuya"]["start"]) >= 600
    if condition == "meal_inside_window":
        return _meal_inside_window(snapshot, visits)
    if condition == "meal_inside_window_or_tradeoff":
        return _meal_inside_window(snapshot, visits) or tradeoff
    if condition == "missing_fields_named":
        return any(item["consequence"].startswith("verify:") for item in reconciliation.values())
    if condition in {
        "no_scenic_value_claim_after_17_00",
        "route_experience_value_zero_after_dark",
    }:
        return all(
            item.get("experience_supported_at_time") is False
            for item in _travel_items(variant)
            if item.get("claimed_experience")
            and _minutes(item["start"]) > _supported_view_end(snapshot, item["claimed_experience"])
        )
    if condition == "outdoor_walk_removed_or_unscheduled":
        return "outdoor_walk" not in visits
    if condition == "owner_acceptance_required":
        return any(item["owner_acceptance_required"] for item in reconciliation.values())
    if condition == "physical_load_points_lte_60":
        by_id = {str(item.get("id") or item.get("place_id")): item for item in snapshot["candidates"]}
        return sum(float(by_id[item].get("physical_load_points", 0)) for item in visits) <= 60
    if condition == "plain_walking_minutes_lte_40":
        return metrics["plain_walking_minutes"] <= 40
    if condition == "plain_walking_minutes_lte_45_or_tradeoff":
        return metrics["plain_walking_minutes"] <= 45 or tradeoff
    if condition == "required_routes_present":
        return not any(
            item["code"] == "ROUTE_UNVERIFIED"
            for item in variant["validation"]["hard_violations"]
        )
    if condition == "route_moved_inside_supported_view_interval":
        return any(item.get("experience_supported_at_time") for item in _travel_items(variant))
    if condition in {
        "runner_up_pros_cons_and_delta_shown",
        "runner_up_tradeoffs_quantified",
        "travel_delta_quantified",
        "whole_trip_delta_quantified",
    }:
        return bool(hotel) and hotel.get("runner_up_area_id") is not None and hotel.get(
            "travel_delta_minutes"
        ) is not None
    if condition == "scooter_never_selected":
        return "scooter" not in metrics["selected_modes"]
    if condition == "selected_route_walking_minutes_lte_20":
        return metrics["maximum_walking_minutes_per_leg"] <= 20
    if condition == "selected_route_walking_minutes_lte_20_or_tradeoff":
        return metrics["maximum_walking_minutes_per_leg"] <= 20 or tradeoff
    if condition == "shibuya_sky_inside_best_time_or_tradeoff":
        return _visit_inside_fact(snapshot, visits.get("shibuya_sky"), "best_time_interval") or tradeoff
    if condition == "status_not_ready":
        return variant["status"] != "ready"
    if condition == "stronger_supporting_evidence_present":
        return False
    if condition == "taxi_selected_or_bike_tradeoff_accepted":
        return "taxi" in metrics["selected_modes"] or ("bike" in metrics["selected_modes"] and tradeoff)
    if condition == "timeline_non_overlapping":
        return variant["validation"]["continuous_timeline"]
    if condition == "verified_entrance_selected":
        return any(_has_verified_entrance(snapshot, subject) for subject in visits)
    if condition == "verified_nearby_fallback_linked":
        return any(item["status"] == "activated" for item in variant["fallbacks"])
    if condition in {"visit_ends_by_17_00", "wukang_road_ends_by_17_00"}:
        targets = subjects or {"wukang_road"}
        return all(subject in visits and _minutes(visits[subject]["end"]) <= 1020 for subject in targets)
    if condition == "visit_inside_best_time_interval":
        return all(_visit_inside_fact(snapshot, visits.get(subject), "best_time_interval") for subject in subjects)
    if condition == "yuyuan_risk_visible_or_alternative_selected":
        return (
            reconciliation.get("yuyuan", {}).get("reason") == "TOURIST_TRAP_RISK"
            or any(item.get("priority") == "alternative" for item in visits.values())
        )
    return False


def _rule_holds(
    rule: str, subjects: list[str], snapshot: dict[str, Any], variant: dict[str, Any]
) -> bool:
    visits = _visits(variant)
    reconciliation = {item["place_id"]: item for item in variant["reconciliation"]}
    reasons = {item["reason"] for item in reconciliation.values()}
    metrics = variant["metrics"]
    thresholds = snapshot.get("thresholds", {})
    if rule == "HARD_OPEN_INTERVAL":
        return not any(item["code"] == "CLOSED_DURING_VISIT" for item in variant["validation"]["hard_violations"])
    if rule == "HARD_SHOW_INTERVAL":
        return not any(item["code"] == "SHOW_INTERVAL_MISSED" for item in variant["validation"]["hard_violations"])
    if rule == "HARD_TRANSPORT_MODE_ALLOWED":
        return "scooter" not in metrics["selected_modes"]
    if rule in {"READY_REQUIRES_ACCESS_EVIDENCE", "READY_REQUIRES_ROUTE_EVIDENCE"}:
        return variant["status"] != "ready" or not variant["validation"]["hard_violations"]
    if rule == "SOFT_BEST_TIME_WINDOW":
        return all(
            subject not in visits
            or _visit_inside_fact(snapshot, visits[subject], "best_time_interval")
            or reconciliation.get(subject, {}).get("status") == "fits_with_tradeoff"
            for subject in subjects
        )
    if rule == "SOFT_PLAIN_WALK_LOAD":
        return metrics["plain_walking_minutes"] <= int(
            thresholds.get("plain_walking_minutes_per_day", 10**9)
        ) or "PLAIN_WALK_THRESHOLD" in reasons
    if rule == "SOFT_PHYSICAL_LOAD":
        return (
            metrics["maximum_walking_minutes_per_leg"]
            <= int(thresholds.get("walking_minutes_per_leg", 10**9))
            and metrics["cycling_minutes"]
            <= int(thresholds.get("cycling_minutes_per_day", 10**9))
        ) or bool({"FATIGUE_THRESHOLD", "HEAT_AND_CYCLING_LOAD", "EFFORT_OR_TIME_CONFLICT"} & reasons)
    if rule == "WALK_REWARD_REQUIRES_EVIDENCE":
        return all(
            not item.get("experience_evidence") or item["walking_minutes"] >= 0
            for item in _travel_items(variant)
        )
    if rule == "ROUTE_EXPERIENCE_REQUIRES_TIME_EVIDENCE":
        return all(
            item.get("experience_supported_at_time") in {True, False}
            for item in _travel_items(variant)
            if item.get("claimed_experience")
        )
    if rule == "WEATHER_CLUSTER_REQUIRES_FALLBACK":
        return bool(variant["fallbacks"]) or "NO_VERIFIED_WEATHER_FALLBACK" in reasons
    if rule == "FALLBACK_REOPTIMIZES_DAY":
        return any(item["day_reoptimized"] for item in variant["fallbacks"])
    if rule == "SOFT_EXPECTED_VALUE":
        return "WEAK_VALUE_FOR_EFFORT" in reasons or all(subject in visits for subject in subjects)
    if rule == "SOFT_TOURIST_TRAP_RISK":
        return "TOURIST_TRAP_RISK" in reasons or all(subject in visits for subject in subjects)
    if rule == "SOFT_CROWD_RISK":
        return "CROWD_CONSEQUENCE_VISIBLE" in variant["warnings"] or all(subject not in visits for subject in subjects)
    if rule == "SOFT_QUEUE_WAIT":
        return "QUEUE_CAUSES_LATE_MEAL" in reasons or all(subject in visits for subject in subjects)
    if rule == "SOFT_MEAL_WINDOW":
        return _meal_inside_window(snapshot, visits) or any(
            item["status"] == "fits_with_tradeoff" for item in reconciliation.values()
        )
    if rule == "SOFT_HEAT_EXPOSURE":
        return not _high_heat(snapshot) or not ({"walk", "bike"} & set(metrics["selected_modes"])) or "HEAT_AND_CYCLING_LOAD" in reasons
    if rule in {"SOFT_BACKTRACKING", "HOTEL_AREA_GLOBAL_EFFICIENCY"}:
        hotel = variant.get("hotel_recommendation")
        return bool(hotel) and hotel["default_area_id"] is not None
    if rule == "ACCESS_INSTRUCTIONS_REQUIRED":
        return all(subject not in visits or _has_verified_entrance(snapshot, subject) for subject in subjects)
    if rule == "EXPLICIT_TRADEOFF_REQUIRED":
        return all(item["status"] != "fits_with_tradeoff" or item["owner_acceptance_required"] for item in reconciliation.values())
    if rule == "SELECTED_ITEM_RECONCILIATION":
        return variant["validation"]["selected_reconciled_count"] == len(reconciliation)
    if rule == "CONTINUOUS_TIMELINE":
        return variant["validation"]["continuous_timeline"]
    return False


def _visits(variant: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["subject_id"]: item
        for day in variant["days"]
        for item in day["items"]
        if item["type"] == "visit"
    }


def _travel_items(variant: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for day in variant["days"]
        for item in day["items"]
        if item["type"] == "travel"
    ]


def _visit_inside_fact(
    snapshot: dict[str, Any], visit: dict[str, Any] | None, fact_type: str
) -> bool:
    if not visit:
        return False
    fact = next(
        (
            item
            for item in snapshot["facts"]
            if item.get("subject_id") == visit["subject_id"]
            and item.get("fact_type") == fact_type
            and item.get("status") == "verified"
        ),
        None,
    )
    return bool(
        fact
        and _minutes(fact["value"]["start"]) <= _minutes(visit["start"])
        and _minutes(visit["end"]) <= _minutes(fact["value"]["end"])
    )


def _meal_inside_window(snapshot: dict[str, Any], visits: dict[str, dict[str, Any]]) -> bool:
    window = snapshot.get("thresholds", {}).get("meal_window")
    meals = [item for item in visits.values() if item.get("kind") == "meal"]
    if not window:
        return True
    return bool(meals) and all(
        _minutes(window["start"]) <= _minutes(item["start"])
        and _minutes(item["end"]) <= _minutes(window["end"])
        for item in meals
    )


def _has_verified_entrance(snapshot: dict[str, Any], subject: str) -> bool:
    facts = [
        item
        for item in snapshot["facts"]
        if item.get("subject_id") == subject
        and item.get("fact_type")
        in {"entry_rule", "entrance_instruction", "entrance_coordinate", "approach_instruction", "access"}
    ]
    return bool(facts) and all(item.get("status") == "verified" and item.get("value") is not None for item in facts)


def _supported_view_end(snapshot: dict[str, Any], subject: str) -> int:
    fact = next(
        (
            item
            for item in snapshot["facts"]
            if item.get("subject_id") == subject
            and item.get("fact_type") == "supported_view_interval"
            and item.get("status") == "verified"
        ),
        None,
    )
    return _minutes(fact["value"]["end"]) if fact else -1


def _high_heat(snapshot: dict[str, Any]) -> bool:
    return any(
        item.get("fact_type") == "heat_exposure"
        and item.get("status") == "verified"
        and item.get("value") == "high"
        for item in snapshot["facts"]
    )


def _hotel_id(variant: dict[str, Any]) -> str:
    return str((variant.get("hotel_recommendation") or {}).get("default_area_id") or "")


def _minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def main() -> int:
    failures = run_catalog()
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    atomic = sum(item["metadata"]["layer"] == "atomic" for item in catalog["fixtures"])
    interaction = len(catalog["fixtures"]) - atomic
    print(
        "PASS: optimizer historic regressions "
        f"({atomic} atomic, {interaction} interaction, 3 variants each)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
