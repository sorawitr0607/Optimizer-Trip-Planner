"""Low-volume worldwide place discovery from OpenStreetMap."""

from __future__ import annotations

from difflib import SequenceMatcher
import json
from math import asin, ceil, cos, radians, sin, sqrt
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from . import interpret


class ProviderUnavailable(RuntimeError):
    pass


class ProviderBudgetExceeded(RuntimeError):
    """The monthly paid cap would be crossed; this is a budget stop, not an outage."""


CARD_PHOTO_LIMIT = 5


class OpenStreetMapProvider:
    name = "openstreetmap"
    cache_version = "osm-baseline-v6"
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

    def geocode(self, query: str) -> dict[str, Any]:
        """Resolve one owner-entered accommodation name or address."""

        location = self._find_destination(query)
        try:
            latitude = float(location["lat"])
            longitude = float(location["lon"])
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderUnavailable(
                "Accommodation lookup returned no usable coordinates"
            ) from error
        return {
            "name": query.strip(),
            "address": str(location.get("display_name") or query).strip(),
            "latitude": latitude,
            "longitude": longitude,
            "status": "owner_confirmed",
            "provider": self.name,
        }

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
        returned_elements = payload.get("elements") if isinstance(payload, dict) else None
        if not isinstance(returned_elements, list):
            raise ProviderUnavailable("OpenStreetMap discovery returned no element list")
        if payload.get("remark"):
            raise ProviderUnavailable(f"OpenStreetMap query incomplete: {payload['remark']}")
        if not returned_elements:
            raise ProviderUnavailable("OpenStreetMap returned an empty baseline; retry later")
        # The same referenced landmark can appear in both the priority and family
        # query blocks. Keep one provider record instead of inflating coverage and
        # candidate aliases with identical copies.
        unique_elements: dict[tuple[Any, Any], Any] = {}
        for index, element in enumerate(returned_elements):
            if isinstance(element, dict):
                provider_key = (element.get("type"), element.get("id"))
                key = provider_key if all(value is not None for value in provider_key) else ("raw", index)
                unique_elements.setdefault(key, element)
        elements = list(unique_elements.values())
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
                    "Unreferenced attraction families have bounded quotas so one dense category cannot consume the whole catalog.",
                ],
                "query_strategy": "referenced_landmarks_then_balanced_families",
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
        # One global `out ... 500` let dense minor peaks and temples consume the
        # entire Taipei response before major landmarks appeared. Emit selective,
        # indexed Wikipedia matches first, then one bounded balanced baseline.
        return f"""[out:json][timeout:90];
(
  nwr[\"name\"][\"tourism\"~\"^(attraction|museum|gallery|viewpoint|artwork|theme_park|zoo|aquarium)$\"][\"wikipedia\"]({bounds});
  nwr[\"name\"][\"historic\"][\"wikipedia\"]({bounds});
  nwr[\"name\"][\"amenity\"~\"^(place_of_worship|marketplace|theatre|arts_centre)$\"][\"wikipedia\"]({bounds});
  nwr[\"name\"][\"leisure\"~\"^(park|garden|nature_reserve|water_park|sports_centre|spa)$\"][\"wikipedia\"]({bounds});
  nwr[\"name\"][\"natural\"~\"^(beach|peak)$\"][\"wikipedia\"]({bounds});
  nwr[\"name\"][\"shop\"~\"^(mall|department_store)$\"][\"wikipedia\"]({bounds});
  nwr[\"name\"][\"man_made\"=\"tower\"][\"wikipedia\"]({bounds});
);
out center qt;
(
nwr[\"name\"][\"tourism\"~\"^(attraction|museum|gallery|viewpoint|artwork|theme_park|zoo|aquarium)$\"]({bounds});
nwr[\"name\"][\"historic\"]({bounds});
nwr[\"name\"][\"amenity\"~\"^(place_of_worship|marketplace|theatre|arts_centre)$\"]({bounds});
nwr[\"name\"][\"leisure\"~\"^(park|garden|nature_reserve|water_park|sports_centre|spa)$\"]({bounds});
nwr[\"name\"][\"natural\"~\"^(beach|peak)$\"]({bounds});
nwr[\"name\"][\"shop\"~\"^(mall|department_store)$\"]({bounds});
nwr[\"name\"][\"man_made\"=\"tower\"]({bounds});
);
out center qt 500;"""

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
    cache_version = "google-places-hours-v2"
    normalizer_version = 2
    cache_ttl_days = 3
    kind = "opening_hours"
    FIELD_MASK = (
        "places.id,places.displayName,places.location,places.primaryType,"
        "places.regularOpeningHours"
    )

    def __init__(self) -> None:
        self.url = os.environ.get(
            "TOURIST_PLACES_URL", "https://places.googleapis.com/v1/places:searchText"
        )

    def opening_hours(self, place: dict[str, Any]) -> dict[str, Any]:
        key = os.environ.get("GOOGLE_MAPS_SERVER_KEY", "").strip()
        if not key:
            raise ProviderUnavailable("GOOGLE_MAPS_SERVER_KEY is not configured")
        destination = str(place.get("destination") or "").strip()
        query = (
            f"{_place_search_name(place)} "
            f"{str(place.get('category') or 'attraction').replace('_', ' ')}"
        )
        if destination:
            query = f"{query}, {destination}"
        body = json.dumps(
            {
                "textQuery": query,
                "pageSize": 5,
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
        hours_matches = [
            match for match in places if "regularOpeningHours" in match
        ]
        try:
            match, distance = _best_nearby_match(hours_matches, place)
        except ProviderUnavailable:
            # Preserve the more useful distinction between an exact place with
            # no published schedule and no compatible place at all.
            match, distance = _best_nearby_match(places, place)
        hours = match.get("regularOpeningHours") or {}
        periods = hours.get("periods") or []
        if not periods:
            raise ProviderUnavailable("Places returned no opening hours for this place")
        return {
            "kind": self.kind,
            "normalizer_version": self.normalizer_version,
            "place_id": str(place["place_id"]),
            "provider_place_id": str(match.get("id") or ""),
            "matched_name": str((match.get("displayName") or {}).get("text") or ""),
            "match_distance_metres": round(distance),
            "weekly_periods": _weekly_periods(periods),
            "weekday_descriptions": list(hours.get("weekdayDescriptions") or []),
            "provider": self.name,
            "status": "verified",
        }


class GooglePlacesCardProvider:
    """One owner-triggered live card overlay: photo, rating, and reviews.

    The response is deliberately never cached or persisted. Google content is
    displayed only in the current Streamlit session; ranking and exports keep
    using the durable provider-neutral candidate record.
    """

    name = "google_places"
    details_operation = "google_places:card_details"
    photo_operation = "google_places:photo"
    FIELD_MASK = (
        "places.id,places.displayName,places.location,places.primaryType,places.googleMapsUri,"
        "places.photos,places.rating,places.userRatingCount,places.reviews,"
        "places.reviewSummary"
    )

    def __init__(self) -> None:
        self.search_url = os.environ.get(
            "TOURIST_PLACES_URL", "https://places.googleapis.com/v1/places:searchText"
        )
        self.photo_url_base = os.environ.get(
            "TOURIST_PLACE_PHOTO_URL", "https://places.googleapis.com/v1"
        ).rstrip("/")

    def details(
        self,
        place: dict[str, Any],
        *,
        destination: str,
        language: str,
    ) -> dict[str, Any]:
        key = os.environ.get("GOOGLE_MAPS_SERVER_KEY", "").strip()
        if not key:
            raise ProviderUnavailable("GOOGLE_MAPS_SERVER_KEY is not configured")
        category = str(place.get("category") or "attraction")
        qualifier = (
            "tourist attraction" if category == "attraction" else category.replace("_", " ")
        )
        body = json.dumps(
            {
                "textQuery": f"{_place_search_name(place)} {qualifier}, {destination}",
                "pageSize": 5,
                "languageCode": language,
                "locationBias": {
                    "circle": {
                        "center": {
                            "latitude": float(place["latitude"]),
                            "longitude": float(place["longitude"]),
                        },
                        "radius": 750.0,
                    }
                },
            }
        ).encode("utf-8")
        request = Request(
            self.search_url,
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
            raise ProviderUnavailable(f"Places card details returned HTTP {error.code}") from None
        except (URLError, TimeoutError) as error:
            raise ProviderUnavailable(
                f"Places card details are unreachable: {type(error).__name__}"
            ) from None
        except json.JSONDecodeError:
            raise ProviderUnavailable("Places card details returned invalid JSON") from None
        return self.normalize(payload, place=place)

    def photo_uri(self, photo_name: str) -> str:
        """Resolve one photo resource without exposing the server key to the UI."""

        key = os.environ.get("GOOGLE_MAPS_SERVER_KEY", "").strip()
        if not key:
            raise ProviderUnavailable("GOOGLE_MAPS_SERVER_KEY is not configured")
        if not photo_name.startswith("places/") or "/photos/" not in photo_name:
            raise ProviderUnavailable("Places returned an invalid photo reference")
        query = urlencode(
            {"maxWidthPx": 1200, "skipHttpRedirect": "true", "key": key}
        )
        url = f"{self.photo_url_base}/{quote(photo_name, safe='/')}/media?{query}"
        try:
            with urlopen(url, timeout=30) as response:
                payload = json.load(response)
        except HTTPError as error:
            raise ProviderUnavailable(f"Place photo returned HTTP {error.code}") from None
        except (URLError, TimeoutError) as error:
            raise ProviderUnavailable(
                f"Place photo is unreachable: {type(error).__name__}"
            ) from None
        except json.JSONDecodeError:
            raise ProviderUnavailable("Place photo returned invalid JSON") from None
        uri = str(payload.get("photoUri") or "").strip()
        if not uri.startswith("https://"):
            raise ProviderUnavailable("Place photo returned no usable image")
        return uri

    @staticmethod
    def normalize(payload: dict[str, Any], *, place: dict[str, Any]) -> dict[str, Any]:
        matches = payload.get("places") or []
        if not matches:
            raise ProviderUnavailable("Places returned no live match for this place")
        match, distance = _best_nearby_match(matches, place)

        reviews = []
        for raw in (match.get("reviews") or [])[:3]:
            text = str(((raw.get("text") or {}).get("text")) or "").strip()
            original = str(((raw.get("originalText") or {}).get("text")) or "").strip()
            if not text and not original:
                continue
            author = raw.get("authorAttribution") or {}
            reviews.append(
                {
                    "text": text or original,
                    "original_text": original or None,
                    "rating": float(raw["rating"]) if raw.get("rating") is not None else None,
                    "published": str(raw.get("relativePublishTimeDescription") or "") or None,
                    "author": str(author.get("displayName") or "") or None,
                    "author_uri": str(author.get("uri") or "") or None,
                    "review_uri": str(raw.get("googleMapsUri") or "") or None,
                }
            )

        summary = match.get("reviewSummary") or {}
        photos = [
            {
                "name": str(raw.get("name") or ""),
                "authors": [
                    {
                        "name": str(item.get("displayName") or "") or None,
                        "uri": str(item.get("uri") or "") or None,
                    }
                    for item in raw.get("authorAttributions") or []
                ],
            }
            for raw in (match.get("photos") or [])[:CARD_PHOTO_LIMIT]
            if raw.get("name")
        ]
        return {
            "provider": "Google Maps",
            "provider_place_id": str(match.get("id") or ""),
            "matched_name": str((match.get("displayName") or {}).get("text") or ""),
            "matched_primary_type": str(match.get("primaryType") or "") or None,
            "match_distance_metres": round(distance),
            "rating": float(match["rating"]) if match.get("rating") is not None else None,
            "user_rating_count": int(match.get("userRatingCount") or 0),
            "google_maps_uri": str(match.get("googleMapsUri") or "") or None,
            "review_summary": {
                "text": str(((summary.get("text") or {}).get("text")) or "").strip(),
                "disclosure": str(
                    ((summary.get("disclosureText") or {}).get("text")) or ""
                ).strip(),
                "reviews_uri": str(summary.get("reviewsUri") or "") or None,
                "flag_uri": str(summary.get("flagContentUri") or "") or None,
            }
            if summary
            else None,
            "reviews": reviews,
            "photos": photos,
            "photo": photos[0] if photos else None,
        }


def _distance_metres(
    left_latitude: float,
    left_longitude: float,
    right_latitude: float,
    right_longitude: float,
) -> float:
    lat1, lon1 = radians(left_latitude), radians(left_longitude)
    lat2, lon2 = radians(right_latitude), radians(right_longitude)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 12_742_000 * asin(sqrt(value))


def _name_similarity(left: str, right: str) -> float:
    left_key = "".join(character for character in left.casefold() if character.isalnum())
    right_key = "".join(character for character in right.casefold() if character.isalnum())
    if not left_key or not right_key:
        return 0.0
    if min(len(left_key), len(right_key)) >= 5 and (
        left_key in right_key or right_key in left_key
    ):
        return 0.8
    return SequenceMatcher(None, left_key, right_key).ratio()


def _category_accepts_primary_type(category: str, primary_type: str) -> bool:
    conflicting_types = {
        "buddhist_temple": {"place_of_worship"},
        "cafe": set(),
        "church": {"place_of_worship"},
        "department_store": {"department_store", "mall"},
        "hiking_area": {"attraction", "nature_reserve", "park", "peak", "viewpoint"},
        "hotel": set(),
        "hindu_temple": {"place_of_worship"},
        "lodging": set(),
        "mosque": {"place_of_worship"},
        "mountain_peak": {"attraction", "nature_reserve", "peak", "viewpoint"},
        "restaurant": set(),
        "shopping_mall": {"department_store", "mall", "marketplace"},
        "synagogue": {"place_of_worship"},
    }
    allowed_categories = conflicting_types.get(primary_type)
    return allowed_categories is None or category in allowed_categories


def _place_search_name(place: dict[str, Any]) -> str:
    """Use the provider's local-script identity before a weak transliteration."""

    names = place.get("names") or {}
    return str(names.get("local") or place.get("name") or "").strip()


def _best_nearby_match(
    matches: list[dict[str, Any]], place: dict[str, Any]
) -> tuple[dict[str, Any], float]:
    """Select one name-, type-, and coordinate-compatible Google result."""

    candidate_names = [str(place.get("name") or "")]
    candidate_names.extend(str(value) for value in (place.get("names") or {}).values())
    ranked = []
    for match in matches:
        location = match.get("location") or {}
        matched_name = str((match.get("displayName") or {}).get("text") or "")
        try:
            distance = _distance_metres(
                float(place["latitude"]),
                float(place["longitude"]),
                float(location["latitude"]),
                float(location["longitude"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        similarity = max(
            (_name_similarity(name, matched_name) for name in candidate_names),
            default=0.0,
        )
        if (
            distance <= 1_500
            and similarity >= 0.46
            and _category_accepts_primary_type(
                str(place.get("category") or "attraction"),
                str(match.get("primaryType") or ""),
            )
        ):
            ranked.append((similarity, -distance, match, distance))
    if not ranked:
        raise ProviderUnavailable(
            "No exact Google Maps match was found nearby; the location map and "
            "open-data source are still available."
        )
    _, _, match, distance = max(ranked, key=lambda item: (item[0], item[1]))
    return match, distance


def _weekly_periods(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize Google periods, whose day 0 is Sunday, into plain records."""

    result = []
    for period in periods:
        opens = period.get("open") or {}
        if "day" not in opens:
            continue
        closes = period.get("close")
        if closes is None:
            # Places encodes 24/7 as Sunday 00:00 with no close. It describes
            # the whole week, not only Sunday.
            days = (
                range(7)
                if int(opens["day"]) == 0
                and int(opens.get("hour", 0)) == 0
                and int(opens.get("minute", 0)) == 0
                else (int(opens["day"]),)
            )
            result.extend(
                {
                    "day": day,
                    "start": "00:00",
                    "end": "23:59",
                    "all_day": True,
                    "overnight": False,
                }
                for day in days
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
