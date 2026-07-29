"""Low-volume worldwide place discovery from OpenStreetMap."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ProviderUnavailable(RuntimeError):
    pass


class OpenStreetMapProvider:
    name = "openstreetmap"
    cache_version = "osm-baseline-v3"
    cache_ttl_days = 7
    result_limit = 500

    def __init__(self) -> None:
        self.nominatim_url = os.environ.get(
            "TOURIST_NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"
        )
        self.overpass_url = os.environ.get(
            "TOURIST_OVERPASS_URL", "https://overpass-api.de/api/interpreter"
        )
        self.user_agent = os.environ.get(
            "TOURIST_USER_AGENT", "TouristPlannerPersonalPOC/0.2 (local personal use)"
        )

    def cache_descriptor(self, destination: str) -> dict[str, Any]:
        return {
            "operation": "baseline_place_discovery",
            "provider": self.name,
            "version": self.cache_version,
            "destination": destination.strip().casefold(),
            "nominatim_url": self.nominatim_url,
            "overpass_url": self.overpass_url,
        }

    def discover(self, destination: str) -> dict[str, Any]:
        location = self._find_destination(destination)
        bbox = self._bounded_bbox(location)
        return self._discover_bbox(
            bbox, geocoded_name=str(location.get("display_name") or destination)
        )

    def refresh(self, destination: str, cached_payload: dict[str, Any]) -> dict[str, Any]:
        coverage = cached_payload.get("coverage", {})
        bbox = coverage.get("bbox") if isinstance(coverage, dict) else None
        if not (
            isinstance(bbox, list)
            and len(bbox) == 4
            and all(isinstance(value, (int, float)) for value in bbox)
        ):
            return self.discover(destination)
        return self._discover_bbox(
            bbox, geocoded_name=str(coverage.get("geocoded_name") or destination)
        )

    def _discover_bbox(self, bbox: list[float], *, geocoded_name: str) -> dict[str, Any]:
        payload = self._request_json(
            Request(
                self.overpass_url,
                data=urlencode({"data": self._overpass_query(bbox)}).encode("utf-8"),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": self.user_agent,
                },
                method="POST",
            )
        )
        elements = payload.get("elements") if isinstance(payload, dict) else None
        if not isinstance(elements, list):
            raise ProviderUnavailable("OpenStreetMap discovery returned no element list")
        if payload.get("remark"):
            raise ProviderUnavailable(f"OpenStreetMap query incomplete: {payload['remark']}")
        if not elements:
            raise ProviderUnavailable("OpenStreetMap returned an empty baseline; retry later")
        items = [item for element in elements if (item := self._item(element))]
        return {
            "items": items,
            "coverage": {
                "bbox": bbox,
                "geocoded_name": geocoded_name,
                "raw_records": len(elements),
                "result_limit": self.result_limit,
                "result_limit_reached": len(elements) >= self.result_limit,
                "searched_categories": [
                    "city_icons",
                    "culture_history_religion",
                    "viewpoints_nature",
                    "neighborhoods_rewarding_walks",
                    "local_food_markets",
                    "shopping",
                    "interactive_activities",
                    "seasonal_events_night",
                    "rest_wellness",
                ],
                "known_gaps": [
                    "OpenStreetMap is uneven and not an exhaustive attraction catalog.",
                    "This baseline does not verify live events, crowds, ratings, transit, best time, or holiday opening hours.",
                ],
            },
            "attribution": "© OpenStreetMap contributors",
            "license": "ODbL",
            "license_url": "https://www.openstreetmap.org/copyright",
        }

    def _find_destination(self, destination: str) -> dict[str, Any]:
        query = urlencode({"q": destination, "format": "jsonv2", "limit": 1})
        payload = self._request_json(
            Request(
                f"{self.nominatim_url}?{query}",
                headers={"Accept": "application/json", "User-Agent": self.user_agent},
            )
        )
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            raise ProviderUnavailable(f"Destination not found: {destination}")
        return payload[0]

    @staticmethod
    def _bounded_bbox(location: dict[str, Any]) -> list[float]:
        try:
            south, north, west, east = map(float, location["boundingbox"])
            center_lat = float(location["lat"])
            center_lon = float(location["lon"])
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderUnavailable("Destination lookup returned an invalid boundary") from error

        # ponytail: one bounded city window protects the public endpoint; split by district
        # only when the coverage UI can coordinate and rate-limit those extra queries.
        lat_span = min(max(north - south, 0.15), 0.60)
        lon_span = min(max(east - west, 0.15), 0.60)
        return [
            round(center_lat - lat_span / 2, 6),
            round(center_lon - lon_span / 2, 6),
            round(center_lat + lat_span / 2, 6),
            round(center_lon + lon_span / 2, 6),
        ]

    def _overpass_query(self, bbox: list[float]) -> str:
        bounds = ",".join(map(str, bbox))
        return f"""[out:json][timeout:25];
(
  nwr[\"name\"][\"tourism\"~\"^(attraction|museum|gallery|viewpoint|artwork|theme_park|zoo|aquarium)$\"]({bounds});
  nwr[\"name\"][\"historic\"]({bounds});
  nwr[\"name\"][\"amenity\"~\"^(place_of_worship|marketplace|theatre|arts_centre)$\"]({bounds});
  nwr[\"name\"][\"leisure\"~\"^(park|garden|nature_reserve|water_park|sports_centre|spa)$\"]({bounds});
  nwr[\"name\"][\"natural\"~\"^(beach|peak)$\"]({bounds});
  nwr[\"name\"][\"shop\"~\"^(mall|department_store)$\"]({bounds});
  nwr[\"name\"][\"man_made\"=\"tower\"]({bounds});
);
out center qt {self.result_limit};"""

    @staticmethod
    def _item(element: Any) -> dict[str, Any] | None:
        if not isinstance(element, dict) or element.get("type") not in {
            "node",
            "way",
            "relation",
        }:
            return None
        tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
        center = element.get("center") if isinstance(element.get("center"), dict) else element
        try:
            latitude = float(center["lat"])
            longitude = float(center["lon"])
            provider_id = f"{element['type']}/{int(element['id'])}"
        except (KeyError, TypeError, ValueError):
            return None

        local_name = str(tags.get("name") or "").strip()
        names = {
            key: value
            for key, value in {
                "local": local_name,
                "en": str(tags.get("name:en") or "").strip(),
                "th": str(tags.get("name:th") or "").strip(),
            }.items()
            if value
        }
        return {
            "provider_place_id": provider_id,
            "names": names,
            "name": names.get("en") or local_name,
            "latitude": latitude,
            "longitude": longitude,
            "category": _category(tags),
            "address": _address(tags),
            "opening_hours": str(tags.get("opening_hours") or "").strip() or None,
            "website": str(tags.get("website") or tags.get("contact:website") or "").strip()
            or None,
            "signals": {
                key: str(tags.get(source) or "").strip()
                for key, source in {
                    "wikidata": "wikidata",
                    "wikipedia": "wikipedia",
                    "heritage": "heritage",
                    "unesco": "heritage:operator",
                }.items()
                if tags.get(source)
            },
            "photo_reference": str(
                tags.get("wikimedia_commons") or tags.get("image") or ""
            ).strip()
            or None,
            "source_url": f"https://www.openstreetmap.org/{provider_id}",
        }

    @staticmethod
    def _request_json(request: Request) -> Any:
        try:
            with urlopen(request, timeout=35) as response:  # noqa: S310 - fixed/configured API URLs
                return json.load(response)
        except HTTPError as error:
            raise ProviderUnavailable(f"Provider HTTP {error.code}") from error
        except (URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
            raise ProviderUnavailable(f"Provider unavailable: {str(error)[:160]}") from error


def _category(tags: dict[str, Any]) -> str:
    if tags.get("tourism"):
        return str(tags["tourism"])
    if tags.get("historic"):
        return "historic"
    if tags.get("amenity"):
        return str(tags["amenity"])
    if tags.get("leisure"):
        return str(tags["leisure"])
    if tags.get("natural"):
        return str(tags["natural"])
    if tags.get("shop"):
        return str(tags["shop"])
    return "landmark"


def _address(tags: dict[str, Any]) -> str | None:
    if tags.get("addr:full"):
        return str(tags["addr:full"])
    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:district"),
        tags.get("addr:city"),
    ]
    address = ", ".join(str(part) for part in parts if part)
    return address or None
