#!/usr/bin/env python3
"""Validate the historic itinerary regression fixture catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "tests/fixtures/historic_regressions.json"

REQUIRED_HISTORY_REFS = {
    "japan.day1.uniqlo_closed",
    "japan.day2.plain_walking",
    "japan.day2.magnet_closed",
    "japan.day2.shibuya_sky_morning",
    "japan.day4.teamlab_odaiba_walk",
    "japan.day4.dark_train_view",
    "japan.last_day.rain_no_backup",
    "fukuoka.day1.hakata_low_value",
    "fukuoka.day1.yatai_tourist_trap",
    "fukuoka.day2.port_fatigue",
    "fukuoka.day3.canal_show_late",
    "kunming.day1.university_access",
    "dali.day2.hotel_backtracking",
    "erhai.day3.scooter_prohibited",
    "erhai.day3.bike_heat",
    "shanghai.day1.sukiyaki_queue",
    "shanghai.day2.yuyuan_tourist_trap",
    "shanghai.day2.wukang_after_dark",
    "shanghai.day4.ferry_crowd",
    "shanghai.day4.ferry_access",
}
REQUIRED_SOURCE_TRIPS = {"Japan", "Fukuoka", "Kunming/Dali", "Shanghai"}
FIXTURE_SECTIONS = {
    "metadata",
    "planner_input",
    "expected_rules",
    "acceptable_outcomes",
}
METADATA_FIELDS = {
    "id",
    "schema_version",
    "layer",
    "failure_class",
    "source_trip",
    "history_refs",
}
PLANNER_INPUT_FIELDS = {
    "trip",
    "travellers",
    "candidates",
    "facts",
    "routes",
    "locks",
    "weights",
    "thresholds",
}
ALLOWED_LAYERS = {"atomic", "interaction"}
ALLOWED_OUTCOMES = {
    "scheduled",
    "cannot_fit",
    "tradeoff",
    "variant",
    "fallback_activated",
}
ALLOWED_FACT_STATUSES = {"verified", "unavailable", "stale", "conflicting", "error"}
FORBIDDEN_KEYS = {"api_key", "secret", "raw_provider_response", "live_provider_call"}


def find_forbidden_keys(value: Any, path: str = "catalog") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key.lower() in FORBIDDEN_KEYS:
                errors.append(f"{child_path}: forbidden key")
            errors.extend(find_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(find_forbidden_keys(child, f"{path}[{index}]"))
    return errors


def validate(catalog: Any) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    counts = {"rules": 0, "fixtures": 0, "atomic": 0, "interaction": 0}
    if not isinstance(catalog, dict):
        return ["catalog: expected an object"], counts
    if catalog.get("catalog_version") != 1:
        errors.append("catalog_version: expected 1")

    registry = catalog.get("rule_registry")
    fixtures = catalog.get("fixtures")
    if not isinstance(registry, dict) or not registry:
        errors.append("rule_registry: expected a non-empty object")
        registry = {}
    if not isinstance(fixtures, list) or not fixtures:
        errors.append("fixtures: expected a non-empty list")
        fixtures = []
    counts["rules"] = len(registry)
    counts["fixtures"] = len(fixtures)

    fixtures_by_id: dict[str, dict[str, Any]] = {}
    atomic_history_refs: set[str] = set()
    source_trips: set[str] = set()

    for index, fixture in enumerate(fixtures):
        label = f"fixtures[{index}]"
        if not isinstance(fixture, dict):
            errors.append(f"{label}: expected an object")
            continue
        if set(fixture) != FIXTURE_SECTIONS:
            errors.append(f"{label}: expected exactly {sorted(FIXTURE_SECTIONS)}")

        metadata = fixture.get("metadata", {})
        planner_input = fixture.get("planner_input", {})
        expected_rules = fixture.get("expected_rules", [])
        outcomes = fixture.get("acceptable_outcomes", [])
        if not isinstance(metadata, dict):
            errors.append(f"{label}.metadata: expected an object")
            continue
        missing_metadata = METADATA_FIELDS - set(metadata)
        if missing_metadata:
            errors.append(f"{label}.metadata: missing {sorted(missing_metadata)}")

        fixture_id = metadata.get("id")
        layer = metadata.get("layer")
        history_refs = metadata.get("history_refs")
        if not isinstance(fixture_id, str) or not fixture_id:
            errors.append(f"{label}.metadata.id: expected a non-empty string")
        elif fixture_id in fixtures_by_id:
            errors.append(f"{label}.metadata.id: duplicate {fixture_id!r}")
        else:
            fixtures_by_id[fixture_id] = fixture
        if metadata.get("schema_version") != 1:
            errors.append(f"{label}.metadata.schema_version: expected 1")
        if layer not in ALLOWED_LAYERS:
            errors.append(f"{label}.metadata.layer: expected atomic or interaction")
        else:
            counts[layer] += 1
        if not isinstance(history_refs, list) or not history_refs or not all(
            isinstance(ref, str) and ref for ref in history_refs
        ):
            errors.append(f"{label}.metadata.history_refs: expected non-empty strings")
        elif layer == "atomic":
            atomic_history_refs.update(history_refs)
        source_trip = metadata.get("source_trip")
        if isinstance(source_trip, str):
            source_trips.add(source_trip)

        if not isinstance(planner_input, dict):
            errors.append(f"{label}.planner_input: expected an object")
        else:
            missing_input = PLANNER_INPUT_FIELDS - set(planner_input)
            if missing_input:
                errors.append(f"{label}.planner_input: missing {sorted(missing_input)}")
            facts = planner_input.get("facts", [])
            if not isinstance(facts, list):
                errors.append(f"{label}.planner_input.facts: expected a list")
            else:
                for fact_index, fact in enumerate(facts):
                    status = fact.get("status") if isinstance(fact, dict) else None
                    if status not in ALLOWED_FACT_STATUSES:
                        errors.append(
                            f"{label}.planner_input.facts[{fact_index}].status: "
                            f"unexpected {status!r}"
                        )

        if not isinstance(expected_rules, list) or not expected_rules:
            errors.append(f"{label}.expected_rules: expected a non-empty list")
        else:
            for rule_index, rule in enumerate(expected_rules):
                rule_id = rule.get("rule_id") if isinstance(rule, dict) else None
                if rule_id not in registry:
                    errors.append(
                        f"{label}.expected_rules[{rule_index}].rule_id: unknown {rule_id!r}"
                    )
        if not isinstance(outcomes, list) or not outcomes:
            errors.append(f"{label}.acceptable_outcomes: expected a non-empty list")
        else:
            for outcome_index, outcome in enumerate(outcomes):
                outcome_type = outcome.get("type") if isinstance(outcome, dict) else None
                if outcome_type not in ALLOWED_OUTCOMES:
                    errors.append(
                        f"{label}.acceptable_outcomes[{outcome_index}].type: "
                        f"unexpected {outcome_type!r}"
                    )

    atomic_ids = {
        fixture_id
        for fixture_id, fixture in fixtures_by_id.items()
        if fixture.get("metadata", {}).get("layer") == "atomic"
    }
    for fixture_id, fixture in fixtures_by_id.items():
        metadata = fixture.get("metadata", {})
        if metadata.get("layer") != "interaction":
            continue
        covered = metadata.get("covers_fixture_ids")
        if not isinstance(covered, list) or not covered:
            errors.append(f"{fixture_id}.metadata.covers_fixture_ids: expected atomic fixture IDs")
            continue
        unknown = set(covered) - atomic_ids
        if unknown:
            errors.append(
                f"{fixture_id}.metadata.covers_fixture_ids: unknown/non-atomic {sorted(unknown)}"
            )

    missing_history = REQUIRED_HISTORY_REFS - atomic_history_refs
    if missing_history:
        errors.append(f"atomic fixtures: missing history refs {sorted(missing_history)}")
    missing_trips = REQUIRED_SOURCE_TRIPS - source_trips
    if missing_trips:
        errors.append(f"fixtures: missing source trips {sorted(missing_trips)}")
    if counts["atomic"] < 20:
        errors.append("fixtures: expected at least 20 atomic cases")
    if counts["interaction"] < 7:
        errors.append("fixtures: expected at least 7 interaction cases")
    errors.extend(find_forbidden_keys(catalog))
    return errors, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", nargs="?", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args()
    try:
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1

    errors, counts = validate(catalog)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(
        "PASS: historic regression catalog "
        f"({counts['rules']} rules, {counts['atomic']} atomic, "
        f"{counts['interaction']} interaction)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
