"""Provider-neutral candidate identity, conservative dedupe, and coverage reporting."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
from math import asin, cos, radians, sin, sqrt
import unicodedata
from typing import Any


def build_candidate_catalog(
    payload: dict[str, Any], *, provider: str, retrieved_at: str, status: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []
    candidates: list[dict[str, Any]] = []
    rejected = Counter()
    duplicate_count = 0

    # ponytail: discovery is bounded below roughly 1,000 records, so a readable
    # O(n²) match is cheaper than owning a spatial index; replace only if caps grow.
    for raw in sorted(raw_items, key=lambda item: str(item.get("provider_place_id", ""))):
        candidate, reason = _candidate(raw, provider, retrieved_at, status)
        if candidate is None:
            rejected[reason] += 1
            continue
        # Same name, same spot, one place -- whatever the two records were *tagged*.
        # Requiring an identical category as well let one attraction through twice
        # whenever OpenStreetMap disagreed with itself about what it is: Singapore's
        # "Jelutong Tower" arrived as `viewpoint` and as `landmark` 2026-08-08, so the
        # owner was asked about it in one lane having already answered in another.
        # An identical normalized name within 150m is the strong signal here; the
        # category is the weak one, and it was doing the deciding.
        match = next(
            (
                existing
                for existing in candidates
                if existing["_name_key"] == candidate["_name_key"]
                and _distance_metres(existing, candidate) <= 150
            ),
            None,
        )
        if match:
            _merge(match, candidate)
            duplicate_count += 1
            continue
        for existing in candidates:
            if (
                existing["_name_key"] == candidate["_name_key"]
                and _distance_metres(existing, candidate) <= 1_000
            ):
                existing["possible_duplicate"] = True
                candidate["possible_duplicate"] = True
        candidates.append(candidate)

    for candidate in candidates:
        candidate.pop("_name_key", None)
    candidates.sort(key=lambda item: (item["name"].casefold(), item["place_id"]))

    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    category_counts = Counter(item["category"] for item in candidates)
    report = {
        "schema_version": 1,
        "provider": provider,
        "status": status,
        "retrieved_at": retrieved_at,
        "raw_records": len(raw_items),
        "canonical_candidates": len(candidates),
        "duplicates_merged": duplicate_count,
        "rejected_records": dict(sorted(rejected.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "geographic_cells_with_candidates": _occupied_cells(candidates),
        "searched_categories": coverage.get("searched_categories", []),
        "query_boundary": coverage.get("bbox"),
        "result_limit_reached": bool(coverage.get("result_limit_reached")),
        "known_gaps": coverage.get("known_gaps", []),
        "broad_not_exhaustive": True,
        "personalization_applied": False,
        "attribution": payload.get("attribution"),
        "license": payload.get("license"),
        "license_url": payload.get("license_url"),
    }
    return {"schema_version": 1, "candidates": candidates}, report


def _candidate(
    raw: Any, provider: str, retrieved_at: str, status: str
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(raw, dict):
        return None, "invalid_record"
    name = str(raw.get("name") or "").strip()
    if not name:
        return None, "missing_name"
    provider_id = str(raw.get("provider_place_id") or "").strip()
    if not provider_id:
        return None, "missing_provider_id"
    try:
        latitude = float(raw["latitude"])
        longitude = float(raw["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, "invalid_coordinates"
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None, "invalid_coordinates"

    category = str(raw.get("category") or "attraction").strip()
    name_key = _name_key(name)
    place_id = "place_" + sha256(
        f"{name_key}|{latitude:.5f}|{longitude:.5f}|{category}".encode("utf-8")
    ).hexdigest()[:20]
    source_url = str(raw.get("source_url") or "").strip() or None
    opening_hours = raw.get("opening_hours")
    return (
        {
            "place_id": place_id,
            "name": name,
            "names": dict(raw.get("names") or {}),
            "latitude": latitude,
            "longitude": longitude,
            "category": category,
            "address": raw.get("address"),
            "website": raw.get("website"),
            "signals": dict(raw.get("signals") or {}),
            "photo_reference": raw.get("photo_reference"),
            "possible_duplicate": False,
            "provider_aliases": [
                {
                    "provider": provider,
                    "provider_place_id": provider_id,
                    "source_url": source_url,
                }
            ],
            "evidence": [
                {
                    "field": "catalog_record",
                    "provider": provider,
                    "provider_place_id": provider_id,
                    "source_url": source_url,
                    "authority_type": "open_data",
                    "retrieved_at": retrieved_at,
                    "language": "mul",
                    "license": "ODbL" if provider == "openstreetmap" else None,
                    "export_permission": "permitted_with_attribution",
                    "status": status,
                    "confidence": "current_provider" if status == "verified" else status,
                }
            ],
            "operational_evidence": {
                "opening_hours": {
                    "value": opening_hours,
                    "state": "regular_schedule_only" if opening_hours else "unconfirmed",
                },
                "best_time": {"value": None, "state": "unconfirmed"},
                "access": {"value": None, "state": "unconfirmed"},
            },
            "_name_key": name_key,
        },
        "",
    )


def _merge(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    target["provider_aliases"].extend(incoming["provider_aliases"])
    target["evidence"].extend(incoming["evidence"])
    for language, value in incoming["names"].items():
        target["names"].setdefault(language, value)
    if not target.get("address"):
        target["address"] = incoming.get("address")
    if not target.get("website"):
        target["website"] = incoming.get("website")
    for signal, value in incoming.get("signals", {}).items():
        target["signals"].setdefault(signal, value)
    if not target.get("photo_reference"):
        target["photo_reference"] = incoming.get("photo_reference")
    left = target["operational_evidence"]["opening_hours"]
    right = incoming["operational_evidence"]["opening_hours"]
    if left.get("value") and right.get("value") and left["value"] != right["value"]:
        left["state"] = "conflicting"


def _name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _distance_metres(left: dict[str, Any], right: dict[str, Any]) -> float:
    lat1, lon1 = radians(left["latitude"]), radians(left["longitude"])
    lat2, lon2 = radians(right["latitude"]), radians(right["longitude"])
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 12_742_000 * asin(sqrt(value))


def _occupied_cells(candidates: list[dict[str, Any]]) -> int:
    if not candidates:
        return 0
    latitudes = [item["latitude"] for item in candidates]
    longitudes = [item["longitude"] for item in candidates]
    lat_min, lat_max = min(latitudes), max(latitudes)
    lon_min, lon_max = min(longitudes), max(longitudes)

    def cell(value: float, low: float, high: float) -> int:
        return min(2, int(3 * (value - low) / (high - low))) if high > low else 1

    return len(
        {
            (
                cell(item["latitude"], lat_min, lat_max),
                cell(item["longitude"], lon_min, lon_max),
            )
            for item in candidates
        }
    )
