"""Low-volume worldwide place discovery from OpenStreetMap."""

from __future__ import annotations

import json
from math import ceil
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import interpret


class ProviderUnavailable(RuntimeError):
    pass


class ProviderBudgetExceeded(RuntimeError):
    """The monthly paid cap would be crossed; this is a budget stop, not an outage."""


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
        # Taipei returned "Query timed out after 27 seconds" on every attempt at 25:
        # a dense city over a 0.6-degree window needs a larger budget. Still one
        # user-triggered request, so the endpoint sees no extra volume.
        return f"""[out:json][timeout:90];
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
            # Above the 90s the Overpass query itself declares, or the socket would
            # abort a query the server is still willing to finish.
            with urlopen(request, timeout=105) as response:  # noqa: S310 - fixed/configured API URLs
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


class OpenRouteServiceProvider:
    """Foot-walking routes from OpenRouteService, normalized for the planner.

    A route from here is a plain transfer: it carries no experience evidence, so
    the optimizer counts it as plain walking rather than a rewarding walk.
    """

    name = "openrouteservice"
    operation = "openrouteservice:directions"
    cache_version = "ors-foot-v1"
    cache_ttl_days = 14
    mode = "walk"

    def __init__(self) -> None:
        self.directions_url = os.environ.get(
            "TOURIST_ORS_URL",
            "https://api.openrouteservice.org/v2/directions/foot-walking",
        )
        self.user_agent = os.environ.get(
            "TOURIST_USER_AGENT", "TouristPlannerPersonalPOC/0.2 (local personal use)"
        )

    def cache_descriptor(self, origin: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        return {
            "operation": "walking_route",
            "provider": self.name,
            "version": self.cache_version,
            "mode": self.mode,
            "origin": _point_key(origin),
            "destination": _point_key(destination),
            "url": self.directions_url,
        }

    def route(self, origin: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        key = os.environ.get("OPENROUTESERVICE_API_KEY", "").strip()
        if not key:
            raise ProviderUnavailable("OPENROUTESERVICE_API_KEY is not configured")
        query = urlencode(
            {
                "start": f"{float(origin['longitude'])},{float(origin['latitude'])}",
                "end": f"{float(destination['longitude'])},{float(destination['latitude'])}",
            }
        )
        request = Request(
            f"{self.directions_url}?{query}",
            headers={"Authorization": key, "User-Agent": self.user_agent},
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except HTTPError as error:
            # Never let a URL or header carrying the key reach the message.
            raise ProviderUnavailable(
                f"OpenRouteService returned HTTP {error.code}"
            ) from None
        except (URLError, TimeoutError) as error:
            raise ProviderUnavailable(
                f"OpenRouteService is unreachable: {type(error).__name__}"
            ) from None
        except json.JSONDecodeError:
            raise ProviderUnavailable("OpenRouteService returned invalid JSON") from None
        return self.normalize(payload, origin=origin, destination=destination)

    def normalize(
        self, payload: dict[str, Any], *, origin: dict[str, Any], destination: dict[str, Any]
    ) -> dict[str, Any]:
        """Provider payload to one normalized route record, or a refusal."""

        features = payload.get("features") or []
        if not features:
            raise ProviderUnavailable("OpenRouteService returned no route")
        summary = (features[0].get("properties") or {}).get("summary") or {}
        seconds = summary.get("duration")
        metres = summary.get("distance")
        if seconds is None or metres is None:
            raise ProviderUnavailable("OpenRouteService route has no duration or distance")
        minutes = max(1, int(ceil(float(seconds) / 60)))
        return {
            "origin_id": str(origin["place_id"]),
            "destination_id": str(destination["place_id"]),
            "mode": self.mode,
            "duration_minutes": minutes,
            # A foot route is walking end to end.
            "walking_minutes": minutes,
            "distance_m": int(round(float(metres))),
            "transfers": 0,
            "boarding_buffer_minutes": 0,
            # Plain transfer: no evidence that the walk is worth doing for itself.
            "experience_evidence": [],
            "status": "verified",
            "provider": self.name,
        }


def _point_key(point: dict[str, Any]) -> dict[str, Any]:
    return {
        "place_id": str(point["place_id"]),
        "latitude": round(float(point["latitude"]), 5),
        "longitude": round(float(point["longitude"]), 5),
    }


class GoogleTimeZoneProvider:
    """The destination's IANA time zone, from coordinates.

    A paid, single-value lookup: one request per destination, cached for a long
    window because zone boundaries move rarely. The zone is recorded as evidence
    with its provider and retrieval time; it is never guessed from a country.
    """

    name = "google_timezone"
    operation = "google_timezone:lookup"
    cache_version = "google-tz-v1"
    cache_ttl_days = 180
    kind = "destination_timezone"

    def __init__(self) -> None:
        self.url = os.environ.get(
            "TOURIST_TIMEZONE_URL", "https://maps.googleapis.com/maps/api/timezone/json"
        )

    def lookup(self, *, latitude: float, longitude: float, timestamp: int) -> dict[str, Any]:
        key = os.environ.get("GOOGLE_MAPS_SERVER_KEY", "").strip()
        if not key:
            raise ProviderUnavailable("GOOGLE_MAPS_SERVER_KEY is not configured")
        query = urlencode(
            {
                "location": f"{float(latitude)},{float(longitude)}",
                "timestamp": int(timestamp),
                "key": key,
            }
        )
        try:
            with urlopen(f"{self.url}?{query}", timeout=20) as response:
                payload = json.load(response)
        except HTTPError as error:
            raise ProviderUnavailable(f"Time zone lookup returned HTTP {error.code}") from None
        except (URLError, TimeoutError) as error:
            raise ProviderUnavailable(
                f"Time zone service is unreachable: {type(error).__name__}"
            ) from None
        except json.JSONDecodeError:
            raise ProviderUnavailable("Time zone service returned invalid JSON") from None
        return self.normalize(payload, latitude=latitude, longitude=longitude)

    def normalize(
        self, payload: dict[str, Any], *, latitude: float, longitude: float
    ) -> dict[str, Any]:
        status = str(payload.get("status") or "")
        if status != "OK":
            # ZERO_RESULTS, REQUEST_DENIED and the rest are all "unverified",
            # never a fallback zone.
            raise ProviderUnavailable(f"Time zone lookup returned {status or 'no status'}")
        zone = str(payload.get("timeZoneId") or "").strip()
        if not zone:
            raise ProviderUnavailable("Time zone lookup returned no zone id")
        return {
            "kind": self.kind,
            "timezone": zone,
            "timezone_name": str(payload.get("timeZoneName") or "") or None,
            "raw_offset_seconds": int(payload.get("rawOffset") or 0),
            "dst_offset_seconds": int(payload.get("dstOffset") or 0),
            "queried_latitude": round(float(latitude), 5),
            "queried_longitude": round(float(longitude), 5),
            "provider": self.name,
            "status": "verified",
        }


class GooglePlacesOpeningHoursProvider:
    """Opening hours for one place, from a licensed live overlay.

    Text search carries the hours in the same response, so one request answers
    one place. The result is a live overlay: it is normalized into planner facts
    and cached briefly, never treated as durable open data.
    """

    name = "google_places"
    operation = "google_places:search_text"
    cache_version = "google-places-hours-v1"
    cache_ttl_days = 3
    kind = "opening_hours"
    FIELD_MASK = (
        "places.id,places.displayName,places.location,places.regularOpeningHours"
    )

    def __init__(self) -> None:
        self.url = os.environ.get(
            "TOURIST_PLACES_URL", "https://places.googleapis.com/v1/places:searchText"
        )

    def opening_hours(self, place: dict[str, Any]) -> dict[str, Any]:
        key = os.environ.get("GOOGLE_MAPS_SERVER_KEY", "").strip()
        if not key:
            raise ProviderUnavailable("GOOGLE_MAPS_SERVER_KEY is not configured")
        body = json.dumps(
            {
                "textQuery": str(place["name"]),
                "maxResultCount": 1,
                "locationBias": {
                    "circle": {
                        "center": {
                            "latitude": float(place["latitude"]),
                            "longitude": float(place["longitude"]),
                        },
                        "radius": 500.0,
                    }
                },
            }
        ).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": self.FIELD_MASK,
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except HTTPError as error:
            raise ProviderUnavailable(f"Places returned HTTP {error.code}") from None
        except (URLError, TimeoutError) as error:
            raise ProviderUnavailable(
                f"Places is unreachable: {type(error).__name__}"
            ) from None
        except json.JSONDecodeError:
            raise ProviderUnavailable("Places returned invalid JSON") from None
        return self.normalize(payload, place=place)

    def normalize(self, payload: dict[str, Any], *, place: dict[str, Any]) -> dict[str, Any]:
        """Provider payload to weekly opening periods, or a refusal."""

        places = payload.get("places") or []
        if not places:
            raise ProviderUnavailable("Places returned no match for this place")
        match = places[0]
        hours = match.get("regularOpeningHours") or {}
        periods = hours.get("periods") or []
        if not periods:
            raise ProviderUnavailable("Places returned no opening hours for this place")
        return {
            "kind": self.kind,
            "place_id": str(place["place_id"]),
            "provider_place_id": str(match.get("id") or ""),
            "matched_name": str((match.get("displayName") or {}).get("text") or ""),
            "weekly_periods": _weekly_periods(periods),
            "weekday_descriptions": list(hours.get("weekdayDescriptions") or []),
            "provider": self.name,
            "status": "verified",
        }


def _weekly_periods(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize Google periods, whose day 0 is Sunday, into plain records."""

    result = []
    for period in periods:
        opens = period.get("open") or {}
        if "day" not in opens:
            continue
        closes = period.get("close")
        if closes is None:
            # No close means open around the clock from that day.
            result.append(
                {
                    "day": int(opens["day"]),
                    "start": "00:00",
                    "end": "23:59",
                    "all_day": True,
                    "overnight": False,
                }
            )
            continue
        start = f"{int(opens.get('hour', 0)):02d}:{int(opens.get('minute', 0)):02d}"
        end = f"{int(closes.get('hour', 0)):02d}:{int(closes.get('minute', 0)):02d}"
        overnight = int(closes.get("day", opens["day"])) != int(opens["day"])
        result.append(
            {
                "day": int(opens["day"]),
                "start": start,
                # An overnight close belongs to the next day; for a single-day
                # visit window the usable part ends at midnight.
                "end": "23:59" if overnight else end,
                "all_day": False,
                "overnight": overnight,
            }
        )
    return sorted(result, key=lambda item: (item["day"], item["start"]))


class RevisionInterpretationUnavailable(RuntimeError):
    """Free-text interpretation is unavailable, with the reason named.

    `cause` is one of missing_credentials, offline, refused, invalid_reply,
    rate_limited or api_error, so the app can say which it is and offer the
    right path instead of a generic failure.
    """

    def __init__(self, message: str, *, cause: str) -> None:
        super().__init__(message)
        self.cause = cause


class OpenAIRevisionInterpreter:
    """One structured-output call that chooses a typed revision operation.

    The model never sees a key beyond the header, never gets stored context
    (`store: false`), and returns only a choice among the supported operations.
    """

    name = "openai"
    operation = "openai:interpret_revision"
    schema_version = 1
    SYSTEM_PROMPT = (
        "You convert a traveller's revision request into exactly one supported "
        "operation. Understand English, Thai and mixed text. Choose only from "
        "supported_operations and use only place_id values present in the plan. "
        "Never state an opening time, route, fare, closure or crowd level. If the "
        "request does not map onto a supported operation, answer with operation "
        "'unsupported' and a short reason. Ask for clarification only when two "
        "readings would change different days, locks or bookings."
    )

    def __init__(self) -> None:
        self.url = os.environ.get(
            "TOURIST_OPENAI_URL", "https://api.openai.com/v1/responses"
        )
        # Configurable, and recorded with every revision; never silently changed.
        self.model = os.environ.get("TOURIST_OPENAI_MODEL", "gpt-4.1-mini")

    def interpret(self, payload: dict[str, Any], *, retry: bool = True) -> dict[str, Any]:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise RevisionInterpretationUnavailable(
                "OPENAI_API_KEY is not configured", cause="missing_credentials"
            )
        body = json.dumps(
            {
                "model": self.model,
                "store": False,
                "input": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "revision_operation",
                        "strict": True,
                        "schema": interpret.response_schema(),
                    }
                },
            }
        ).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )
        try:
            with urlopen(request, timeout=45) as response:
                raw = json.load(response)
        except HTTPError as error:
            if error.code == 429 and retry:
                # One retry for a transient limit, then stop. Never loop.
                return self.interpret(payload, retry=False)
            cause = "rate_limited" if error.code == 429 else "api_error"
            raise RevisionInterpretationUnavailable(
                f"Interpretation returned HTTP {error.code}", cause=cause
            ) from None
        except (URLError, TimeoutError) as error:
            if retry:
                return self.interpret(payload, retry=False)
            raise RevisionInterpretationUnavailable(
                f"Interpretation service is unreachable: {type(error).__name__}",
                cause="offline",
            ) from None
        except json.JSONDecodeError:
            raise RevisionInterpretationUnavailable(
                "Interpretation returned invalid JSON", cause="invalid_reply"
            ) from None
        return {
            "response": self.extract(raw),
            "model": self.model,
            "schema_version": self.schema_version,
        }

    def extract(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Pull the structured object out of a Responses API reply."""

        if raw.get("status") == "incomplete":
            raise RevisionInterpretationUnavailable(
                "Interpretation was cut short", cause="invalid_reply"
            )
        for item in raw.get("output") or []:
            if item.get("type") == "refusal" or item.get("refusal"):
                raise RevisionInterpretationUnavailable(
                    "The model refused this request", cause="refused"
                )
            for part in item.get("content") or []:
                if part.get("type") == "refusal":
                    raise RevisionInterpretationUnavailable(
                        "The model refused this request", cause="refused"
                    )
                text = part.get("text")
                if text:
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        raise RevisionInterpretationUnavailable(
                            "Interpretation was not valid JSON", cause="invalid_reply"
                        ) from None
                    if not isinstance(parsed, dict):
                        raise RevisionInterpretationUnavailable(
                            "Interpretation was not an object", cause="invalid_reply"
                        )
                    return parsed
        raise RevisionInterpretationUnavailable(
            "Interpretation returned no content", cause="invalid_reply"
        )
