"""Low-volume worldwide place discovery from OpenStreetMap."""

from __future__ import annotations

from difflib import SequenceMatcher
from time import monotonic, sleep
import json
import re
from math import asin, ceil, cos, radians, sin, sqrt
import os
from pathlib import Path
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
    # Seconds between the two discovery blocks, so the first query's slot is released
    # before the second asks for one. Small on purpose: it is paid on every discovery
    # and the pair still has to finish inside the webapp's 120s RPC abort.
    BLOCK_PAUSE_SECONDS = 3
    # A failure this quick never reached the query engine — it is a gateway or a spent
    # slot, not a timeout — so it is worth asking again. Anything slower died of the
    # 60-90s budget the query itself declares, and a retry would only spend it twice.
    FAST_FAILURE_SECONDS = 20
    RETRY_PAUSE_SECONDS = 6
    # The ceiling for one discovery, retries included, under `client.ts`'s 120s abort.
    # A pair that outlives the page waiting for it fails the same way it would have
    # anyway, having spent the time.
    DISCOVERY_BUDGET_SECONDS = 100

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

    def _overpass_elements(self, query: str) -> list[Any]:
        """One Overpass request. Raises rather than returning a truncated answer."""

        payload = self._request_json(
            Request(
                self.overpass_url,
                data=urlencode({"data": query}).encode("utf-8"),
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
        # Overpass reports a server-side timeout as a `remark` beside a partial
        # element list, never as an HTTP error. Treated as a failure of *this* block.
        if payload.get("remark"):
            raise ProviderUnavailable(f"OpenStreetMap query incomplete: {payload['remark']}")
        return elements

    def _attempt_block(self, query: str, deadline: float) -> list[Any]:
        """One block, retried once if it failed *fast* and there is budget for it.

        `overpass-api.de` balances across backends and an unhealthy one answers 504 in
        seconds. Measured 2026-08-08 on Singapore: both blocks 504 at 9.0s and 9.5s with
        both slots free, and the identical query returned 200 a minute later — so the
        owner got an empty catalog for a fault that had already passed.

        Only a **fast** failure is retried, and that distinction is the whole safety of
        this. A block that died at 90s died of the server-side timeout, and asking again
        would spend another 90s to fail the same way — while a block that died at 9s
        never reached the query engine at all. The shared deadline is what keeps the pair
        inside the webapp's 120s RPC abort no matter how the retries fall.
        """

        started = monotonic()
        try:
            return self._overpass_elements(query)
        except ProviderUnavailable as error:
            elapsed = monotonic() - started
            retryable = "HTTP 5" in str(error) and elapsed <= self.FAST_FAILURE_SECONDS
            if not retryable or monotonic() + self.RETRY_PAUSE_SECONDS >= deadline:
                raise
        sleep(self.RETRY_PAUSE_SECONDS)
        return self._overpass_elements(query)

    def _discover_bbox(self, bbox: list[float], *, geocoded_name: str) -> dict[str, Any]:
        # Two requests, sequential, each best-effort.
        #
        # As one query this failed outright on a dense city: Tokyo's Nominatim boundary
        # is capped to the 0.60-degree window, and the *unindexed* family block scanning
        # 66km of it exceeded `[timeout:90]` at lines 14 and 16 — measured 2026-08-07 at
        # 91s and 93s across two attempts. Overpass has no partial result, so a timeout
        # in the cheap half discarded the expensive half too and the screen showed no
        # attractions at all.
        #
        # Splitting them means a city can lose the noisy half and keep its landmarks. The
        # `["wikipedia"]`-indexed block is the valuable one — every one of City Icons'
        # top 20 comes from it — and it is also the one that never timed out. Sequential,
        # so this still occupies one of Overpass's two slots at a time.
        blocks = (
            ("landmarks", self._landmark_query(bbox)),
            ("baseline", self._baseline_query(bbox)),
        )
        deadline = monotonic() + self.DISCOVERY_BUDGET_SECONDS
        returned_elements: list[Any] = []
        incomplete: dict[str, str] = {}
        for index, (name, query) in enumerate(blocks):
            # Overpass grants two slots and answers 504 the instant they are spent, so
            # firing the second block the moment the first returns loses it to a rate
            # limit rather than to a timeout. Measured: back to back, the baseline came
            # back `Provider HTTP 504` while the landmarks succeeded. That matters most
            # for a *small* city, where little carries a Wikipedia article and the
            # unindexed block is where nearly every place comes from.
            if index:
                sleep(self.BLOCK_PAUSE_SECONDS)
            try:
                returned_elements.extend(self._attempt_block(query, deadline))
            except ProviderUnavailable as error:
                incomplete[name] = str(error)[:240]
        if not returned_elements:
            raise ProviderUnavailable(
                "; ".join(incomplete.values())
                or "OpenStreetMap returned an empty baseline; retry later"
            )
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
                # Named per block, because "some of the catalog is missing" and "which
                # half" are different facts and the screen can only report what it is told.
                "incomplete_blocks": sorted(incomplete),
                "known_gaps": [
                    "OpenStreetMap is uneven and not an exhaustive attraction catalog.",
                    "This baseline does not verify live events, crowds, ratings, transit, best time, or holiday opening hours.",
                    "Unreferenced attraction families have bounded quotas so one dense category cannot consume the whole catalog.",
                    *(f"{name}: {reason}" for name, reason in sorted(incomplete.items())),
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

    # The seven attraction families, as Overpass tag selectors. One list, so the
    # indexed and unindexed blocks cannot drift apart.
    FAMILY_SELECTORS = (
        '["tourism"~"^(attraction|museum|gallery|viewpoint|artwork|theme_park|zoo|aquarium)$"]',
        '["historic"]',
        '["amenity"~"^(place_of_worship|marketplace|theatre|arts_centre)$"]',
        '["leisure"~"^(park|garden|nature_reserve|water_park|sports_centre|spa)$"]',
        '["natural"~"^(beach|peak)$"]',
        '["shop"~"^(mall|department_store)$"]',
        '["man_made"="tower"]',
    )

    def _landmark_query(self, bbox: list[float]) -> str:
        """Wikipedia-referenced landmarks. Indexed, cheap, and the half worth keeping."""

        bounds = ",".join(map(str, bbox))
        lines = "\n".join(
            f'  nwr["name"]{selector}["wikipedia"]({bounds});'
            for selector in self.FAMILY_SELECTORS
        )
        return f"[out:json][timeout:90];\n(\n{lines}\n);\nout center qt;"

    def _baseline_query(self, bbox: list[float]) -> str:
        """The balanced family baseline. Unindexed, and the half that times out on a
        dense city — Tokyo exceeded 90s here while the landmark block returned fine.

        Its budget is **60s, not the landmark block's 90s**, and that is a browser
        constraint rather than an Overpass one. Two requests can now run back to back,
        and `web/src/api/client.ts` aborts an RPC at 120s: at 90s each the pair could
        outlive the page waiting for it, which would look exactly like the failure this
        split exists to remove. Measured Tokyo end to end at 85.8s before this and it
        still gave 3082 landmarks, so the margin is what changed, not the outcome —
        and Taipei's whole two-block query takes ~34s, so nothing there comes near 60.
        """

        bounds = ",".join(map(str, bbox))
        lines = "\n".join(
            f'nwr["name"]{selector}({bounds});' for selector in self.FAMILY_SELECTORS
        )
        return (
            f"[out:json][timeout:60];\n(\n{lines}\n);\n"
            f"out center qt {self.result_limit};"
        )


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


def visible_text(html: str, *, limit: int = 6000) -> str:
    """Readable text from an HTML page, scripts and styles removed, whitespace collapsed.

    Capped because a notice sits near the top of a landing page and the rest is
    navigation — and because the cap is what keeps a page from deciding how much of the
    owner's money one call spends.
    """

    stripped = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()[:limit]


class VenueNoticeProvider:
    """A venue's own page, read for a dated closure notice the weekly hours cannot carry.

    `WF-044`. An opening fact is a **weekly pattern**, so nothing the app stores can say
    "closed 1 January" — and the pilot spans 31 December and 1 January. Google will not
    fill that: its snapshot is a weekday timetable.

    **This never becomes a fact.** It is stored as `place_evidence` of kind
    `venue_notice`, which `actions._optimizer_input` does not read, so an extracted notice
    cannot remove a place from a plan, narrow a window, or change a single scheduled
    minute. That is the bar the ticket set, and it is met structurally rather than by
    care: the optimizer has no code path to this data.

    The reason for that severity is measured. Asking a model for weekly closed days in
    `WF-046` produced 7 claims of which **2 were invented**. And the one page most worth
    reading is a trap: Sun Yat-sen Memorial Hall publishes a 休館公告 — literally "closure
    announcement" — dated 2026-08-06 that is about a **server-room migration affecting its
    website**, not the hall shutting. An extractor that acted on that would silently
    delete a landmark.

    So the output is a *quote and a link*, for a person who reads Chinese to judge. Two
    mechanical guards make that trustworthy:

    - **The quote must appear verbatim in the fetched page.** A model that paraphrases or
      invents fails a substring check and the notice is discarded. This is the one
      hallucination test that needs no judgement.
    - **No page, no answer.** A failed fetch raises; the model is never asked to recall
      what a site says.
    """

    name = "venue_notice"
    operation = "openai:venue_notice"
    kind = "venue_notice"
    # Notices are the most perishable thing the app reads -- a holiday announcement
    # appears weeks before the date. Short on purpose.
    cache_ttl_days = 14
    PAGE_LIMIT = 6000

    SYSTEM_PROMPT = (
        "You are given the visible text of one venue's own web page. Find any notice "
        "about the venue being CLOSED TO VISITORS on specific dates, or its visitor "
        "opening hours changing on specific dates. "
        "Copy the sentence you relied on into `quote`, character for character, from the "
        "page text you were given -- never paraphrase, translate or shorten it. "
        "A notice about a website, an online system, a phone line, a single exhibition, "
        "or building works that do not shut the venue is NOT a closure: set found to "
        "false. If you are unsure, set found to false. "
        "Never state regular weekly hours; only dated exceptions to them."
    )
    RESPONSE_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["found", "quote", "summary"],
        "properties": {
            "found": {"type": "boolean"},
            "quote": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
        },
    }

    def __init__(self) -> None:
        self.url = os.environ.get(
            "TOURIST_OPENAI_URL", "https://api.openai.com/v1/responses"
        )
        self.model = os.environ.get("TOURIST_OPENAI_MODEL", "gpt-5.6-luna")
        self.user_agent = os.environ.get(
            "TOURIST_USER_AGENT", "TouristPlannerPersonalPOC/0.2 (local personal use)"
        )

    # Named `read_page`, not `fetch`. `web/src/api/client.ts`'s `rpc` calls the browser's
    # `fetch()`, and extraction conflated the two into an edge claiming TypeScript calls
    # this method -- clustering dropped it and the endpoint-pair guard then demanded a
    # false edge survive. Same collision class as the `def rpc` one `AGENTS.md` records.
    def read_page(self, website: str) -> str:
        request = Request(
            website,
            headers={"User-Agent": self.user_agent, "Accept": "text/html,*/*"},
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - owner's own venue list
                raw = response.read(2_000_000)
                charset = response.headers.get_content_charset() or "utf-8"
        except HTTPError as error:
            raise ProviderUnavailable(f"Venue page returned HTTP {error.code}") from None
        except (URLError, TimeoutError, OSError) as error:
            raise ProviderUnavailable(
                f"Venue page unreachable: {type(error).__name__}"
            ) from None
        return visible_text(raw.decode(charset, errors="replace"), limit=self.PAGE_LIMIT)

    def notice(self, *, name: str, website: str) -> dict[str, Any]:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise ProviderUnavailable("OPENAI_API_KEY is not configured")
        page = self.read_page(website)
        if not page:
            return {"found": False, "reason": "PAGE_HAS_NO_TEXT", "source_url": website}

        body = json.dumps(
            {
                "model": self.model,
                "store": False,
                "input": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"Venue: {name}\n\nPage text:\n{page}"},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "venue_notice",
                        "strict": True,
                        "schema": self.RESPONSE_SCHEMA,
                    }
                },
            }
        ).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed API URL
                raw = json.load(response)
        except HTTPError as error:
            raise ProviderUnavailable(f"Model returned HTTP {error.code}") from None
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ProviderUnavailable(f"Model unreachable: {type(error).__name__}") from None

        parsed = OpenAIOpeningWindowProvider._parse(raw)
        if not parsed.get("found"):
            return {"found": False, "reason": "NO_NOTICE_ON_PAGE", "source_url": website}
        quote = str(parsed.get("quote") or "").strip()
        if not quote or not self.quotes_the_page(quote, page):
            # The one hallucination test that needs no judgement. A quote that is not on
            # the page is either invented or paraphrased, and either way the owner cannot
            # check it against the source -- which is the whole product here.
            return {"found": False, "reason": "QUOTE_NOT_ON_PAGE", "source_url": website}
        return {
            "found": True,
            "quote": quote,
            "summary": str(parsed.get("summary") or "").strip() or None,
            "source_url": website,
            "model": self.model,
        }

    @staticmethod
    def quotes_the_page(quote: str, page: str) -> bool:
        """Verbatim, allowing only whitespace to differ.

        Whitespace is forgiven because it is an artefact of stripping tags, not of the
        model's honesty. Nothing else is: no case folding, no punctuation normalising, no
        prefix matching -- each would let a paraphrase through, and a paraphrase is
        exactly what cannot be checked against the source.
        """

        squeeze = lambda value: re.sub(r"\s+", "", value)  # noqa: E731
        return squeeze(quote) in squeeze(page)


class OpenAIOpeningWindowProvider:
    """A better *assumption* about opening hours than a hardcoded constant. `WF-046`.

    This does not produce evidence and must never be read as such. When a place has no
    verified hours and the trip is `explore_first`, `actions._optimizer_input` has always
    emitted an assumed window — a flat **09:00–21:00** for every place on earth. This
    replaces the constant with a model's recollection of that specific place, and the fact
    keeps `status: "assumed"` either way. Nothing is upgraded; one guess is swapped for a
    better one.

    **Measured against Google's verified hours for the pilot's 13 places, 2026-08-07:**

    | | Window ends after real closing | By |
    |---|---|---|
    | this provider | 5 of 13 | 30–60 min |
    | the 09:00–21:00 constant | 6 of 13 | 180–270 min |

    Five of thirteen matched both ends exactly. Overshooting closing time is the failure
    that matters, because it is what schedules a visit that cannot happen — the pilot had
    one at 17:17–19:32 against real hours ending 17:30, and it passed validation. On that
    place this provider is 30 minutes wrong where the constant was 210.

    **Closures are deliberately not requested.** The same benchmark asked for weekly
    closed days and got 7 claims, of which **2 were invented** — Huashan 1914 and Taipei
    Zoo, neither closed on any trip date. A false closure silently removes a place from a
    day, and 29 December is a Tuesday. Google supplies real closures anyway, so the risky
    half buys nothing. Do not add the field back without re-running the benchmark.

    It also cannot help with a **holiday** closure: "closed 1 January 2027" is after any
    training cutoff and venues publish it weeks ahead. That gap is `WF-044`, and this
    provider does not touch it.
    """

    name = "openai_opening_window"
    operation = "openai:opening_window"
    kind = "assumed_opening_window"
    schema_version = 1
    # An assumption about a building's habits, not a timetable. Long, because re-asking
    # cannot make a recollection fresher -- only a real lookup can.
    cache_ttl_days = 90

    # A window this wide or wider is discarded as a non-answer. The constant it would
    # replace is twelve hours, so anything approaching a full day is *less* constraining
    # than doing nothing -- and a visitor attraction genuinely open twenty hours a day is
    # rare enough that losing it to the constant costs almost nothing. Temples really do
    # open 06:00-22:00, sixteen hours, so the bar has to sit above that.
    DEGENERATE_SPAN_MINUTES = 20 * 60

    SYSTEM_PROMPT = (
        "You state the usual visitor opening hours of one named place. Answer only from "
        "what you actually know about that specific place. If you are not confident, set "
        "known to false and leave start and end null -- a refusal is more useful than a "
        "generic tourist schedule. Times are 24-hour HH:MM in the place's local time. "
        "Never state a holiday closure, a weekly closed day, a route, a fare or a price."
    )
    RESPONSE_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["known", "start", "end"],
        "properties": {
            "known": {"type": "boolean"},
            "start": {"type": ["string", "null"]},
            "end": {"type": ["string", "null"]},
        },
    }

    def __init__(self) -> None:
        self.url = os.environ.get(
            "TOURIST_OPENAI_URL", "https://api.openai.com/v1/responses"
        )
        self.model = os.environ.get("TOURIST_OPENAI_MODEL", "gpt-5.6-luna")

    # How many places go in one batched request. Bounded so a large trip cannot put an
    # unpredictable payload behind a single price, and so one bad reply loses one chunk
    # rather than the whole trip's answers.
    BATCH_SIZE = 20

    BATCH_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["places"],
        "properties": {
            "places": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["ref", "known", "start", "end"],
                    "properties": {
                        # The index it was asked about. Names are unreliable to match on --
                        # the model may translate or normalise one -- so the mapping back is
                        # an integer it is told to echo.
                        "ref": {"type": "integer"},
                        "known": {"type": "boolean"},
                        "start": {"type": ["string", "null"]},
                        "end": {"type": ["string", "null"]},
                    },
                },
            }
        },
    }

    def windows(self, places: list[dict[str, str]], *, destination: str) -> dict[int, dict[str, Any]]:
        """One call for many places, keyed by their index in `places`. `WF-047`.

        Verified hours cost US$0.025 each and cannot be batched -- Google's Text Search
        takes one query per place -- so a 40-place trip is US$1.00. This is the cheap
        alternative made properly cheap: one request instead of N, which at luna's rates
        is fractions of a cent for a whole trip.

        It is still an **assumption**, and batching does not change that. What it changes
        is that the honest comparison an owner is offered stops being "US$1.00 against
        US$0.02" and becomes "US$1.00 against a rounding error", which makes the
        *evidential* difference the only thing left to weigh.

        Results are matched by an echoed integer, never by name, and a reply that omits or
        invents an index simply yields no answer for that place -- the constant stands.
        """

        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise ProviderUnavailable("OPENAI_API_KEY is not configured")
        if not places:
            return {}
        listing = "\n".join(
            f"{index}. {item['name']}"
            + (f" ({item['local_name']})" if item.get("local_name") and item["local_name"] != item["name"] else "")
            for index, item in enumerate(places)
        )
        body = json.dumps(
            {
                "model": self.model,
                "store": False,
                "input": [
                    {"role": "system", "content": self.SYSTEM_PROMPT + self.BATCH_NOTE},
                    {
                        "role": "user",
                        "content": f"City: {destination}\n\nPlaces:\n{listing}",
                    },
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "opening_windows",
                        "strict": True,
                        "schema": self.BATCH_SCHEMA,
                    }
                },
            }
        ).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        try:
            with urlopen(request, timeout=120) as response:  # noqa: S310 - fixed API URL
                raw = json.load(response)
        except HTTPError as error:
            raise ProviderUnavailable(f"Model returned HTTP {error.code}") from None
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ProviderUnavailable(f"Model unreachable: {type(error).__name__}") from None

        parsed = self._parse(raw)
        found: dict[int, dict[str, Any]] = {}
        for entry in parsed.get("places") or []:
            try:
                ref = int(entry.get("ref"))
            except (TypeError, ValueError):
                continue
            if not 0 <= ref < len(places) or ref in found:
                continue  # invented or repeated index: no answer for it
            if not entry.get("known"):
                continue
            window = _clock_window(entry.get("start"), entry.get("end"))
            if window is None or _span_minutes(window) >= self.DEGENERATE_SPAN_MINUTES:
                continue
            found[ref] = {"known": True, **window, "model": self.model}
        return found

    BATCH_NOTE = (
        " You are given a numbered list. Answer with one entry per place, echoing its "
        "number in `ref`. Judge each place independently; do not copy one place's hours "
        "onto another because they are similar. Omit nothing: a place you are unsure of "
        "gets an entry with known set to false."
    )

    def window(self, *, name: str, local_name: str, destination: str) -> dict[str, Any]:
        """One window, or `known: false`. Raises rather than inventing on any failure."""

        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise ProviderUnavailable("OPENAI_API_KEY is not configured")
        asked = f"Place: {name}"
        if local_name and local_name != name:
            asked += f" ({local_name})"
        asked += f" in {destination}."
        body = json.dumps(
            {
                "model": self.model,
                "store": False,
                "input": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": asked},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "opening_window",
                        "strict": True,
                        "schema": self.RESPONSE_SCHEMA,
                    }
                },
            }
        ).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        try:
            with urlopen(request, timeout=45) as response:  # noqa: S310 - fixed API URL
                raw = json.load(response)
        except HTTPError as error:
            raise ProviderUnavailable(f"Model returned HTTP {error.code}") from None
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ProviderUnavailable(
                f"Model unreachable: {type(error).__name__}"
            ) from None

        parsed = self._parse(raw)
        if not parsed.get("known"):
            return {"known": False, "model": self.model, "asked": asked}
        window = _clock_window(parsed.get("start"), parsed.get("end"))
        if window is None:
            # A malformed or inverted pair is a refusal, not something to repair. Guessing
            # what was meant is how a bad assumption becomes an invisible one.
            return {"known": False, "model": self.model, "asked": asked}
        if _span_minutes(window) >= self.DEGENERATE_SPAN_MINUTES:
            # "Open all day" is not an opening time, it is the absence of one -- and it
            # permits *more* than the 09:00-21:00 constant it would replace, which
            # inverts the entire reason for asking. Measured: `gpt-5.6-luna` returned
            # 00:00-23:59 for Huashan 1914, whose real hours are 11:00-21:00.
            return {"known": False, "model": self.model, "asked": asked}
        return {"known": True, **window, "model": self.model, "asked": asked}

    @staticmethod
    def _parse(raw: dict[str, Any]) -> dict[str, Any]:
        if raw.get("status") == "incomplete":
            raise ProviderUnavailable("Model reply was cut short")
        for item in raw.get("output") or []:
            if item.get("type") == "refusal" or item.get("refusal"):
                raise ProviderUnavailable("The model refused this request")
            for part in item.get("content") or []:
                if part.get("type") == "refusal":
                    raise ProviderUnavailable("The model refused this request")
                text = part.get("text")
                if text:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        raise ProviderUnavailable("Model returned invalid JSON") from None
        raise ProviderUnavailable("Model returned no content")


def _span_minutes(window: dict[str, str]) -> int:
    def minutes(value: str) -> int:
        hour, minute = value.split(":")
        return int(hour) * 60 + int(minute)

    return minutes(window["end"]) - minutes(window["start"])


def _clock_window(start: Any, end: Any) -> dict[str, str] | None:
    """`{"start", "end"}` for a well-formed HH:MM pair that runs forwards, else None."""

    def minutes(value: Any) -> int | None:
        if not isinstance(value, str):
            return None
        match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", value.strip())
        if not match:
            return None
        return int(match.group(1)) * 60 + int(match.group(2))

    first, last = minutes(start), minutes(end)
    if first is None or last is None or first >= last:
        return None
    return {"start": f"{first // 60:02d}:{first % 60:02d}", "end": f"{last // 60:02d}:{last % 60:02d}"}


class OsmAreaAmenitiesProvider:
    """How many places to eat, drink late, and stay, within walking reach of a point.

    `WF-040`'s three inferred factors. Free, no key, and **one HTTP request for every
    point at once** — Overpass accepts many statements per query and prints an `out
    count` for each, so 8 areas x 3 categories is 24 statements and one round trip
    returning a few hundred bytes. That matters because the endpoint grants 2 concurrent
    slots and answers 504 the moment they are spent; a query per area would read as an
    outage that is really self-inflicted.

    Counting rather than listing is deliberate. The owner asked for "popular by tourist,
    so can infer that it has many choice", and a count is exactly that inference and no
    more. It cannot see price, room type or whether a family of three fits, so
    `areas.py` reports those as gaps instead of scoring them.

    Priced at zero like `openstreetmap:discover`, and priced rather than omitted,
    because an unpriced operation raises.
    """

    name = "osm_area_amenities"
    operation = "openstreetmap:areas"
    cache_version = "osm-areas-v1"
    # Shops and restaurants turn over, but not fast enough to re-query inside a week of
    # planning. Shorter than the metro's 30 days for exactly that reason.
    cache_ttl_days = 7

    # Walking reach used for every count. 600 m is about 7-8 minutes at the
    # `transit.WALK_METRES_PER_MINUTE` this app already assumes for a 51-year-old.
    RADIUS_METRES = 600

    # `nwr` rather than `node`: a restaurant or hotel is as often mapped as a building
    # way as a point, and counting only nodes under-reports dense blocks worst.
    CATEGORIES: tuple[tuple[str, str], ...] = (
        ("food_count", 'nwr["amenity"~"^(restaurant|cafe|fast_food|food_court)$"]'),
        ("after_dark_count", 'nwr["amenity"~"^(bar|pub|nightclub|cinema)$"]'),
        ("lodging_count", 'nwr["tourism"~"^(hotel|hostel|guest_house|apartment|motel)$"]'),
    )

    def __init__(self) -> None:
        self._osm = OpenStreetMapProvider()

    def cache_descriptor(self, points: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "operation": "area_amenities",
            "provider": self.name,
            "version": self.cache_version,
            "radius": self.RADIUS_METRES,
            # Not `_point_key`: these are areas, keyed by `area_id`, and rounding the
            # coordinates the same way is what makes a re-run hit the cache.
            "points": [
                {
                    "area_id": str(point["area_id"]),
                    "latitude": round(float(point["latitude"]), 5),
                    "longitude": round(float(point["longitude"]), 5),
                }
                for point in points
            ],
        }

    def amenities_query(self, points: list[dict[str, Any]]) -> str:
        lines = [f"[out:json][timeout:90];"]
        for point in points:
            for _, selector in self.CATEGORIES:
                latitude = float(point["latitude"])
                longitude = float(point["longitude"])
                lines.append(
                    f"{selector}(around:{self.RADIUS_METRES},{latitude},{longitude});"
                )
                lines.append("out count;")
        return "\n".join(lines) + "\n"

    def counts(self, points: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
        """Per-point counts, keyed by the point's `area_id`.

        Overpass returns one `count` element per `out count`, **in statement order**,
        which is the only thing tying a number back to the point that asked for it. So
        the length is checked rather than trusted: a short answer means the mapping has
        silently shifted, and a wrong count per area is worse than no recommendation.
        """

        if not points:
            return {}
        payload = self._osm._request_json(
            Request(
                self._osm.overpass_url,
                data=urlencode({"data": self.amenities_query(points)}).encode("utf-8"),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": self._osm.user_agent,
                },
                method="POST",
            )
        )
        elements = [
            item for item in (payload.get("elements") or []) if item.get("type") == "count"
        ]
        expected = len(points) * len(self.CATEGORIES)
        if len(elements) != expected:
            raise ProviderUnavailable(
                f"Overpass returned {len(elements)} counts for {expected} statements"
            )
        found: dict[str, dict[str, int]] = {}
        cursor = 0
        for point in points:
            counts: dict[str, int] = {}
            for key, _ in self.CATEGORIES:
                tags = elements[cursor].get("tags") or {}
                counts[key] = int(tags.get("total") or 0)
                cursor += 1
            found[str(point["area_id"])] = counts
        return found


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


class WikidataSummaryProvider:
    """A description and a photo per place, in both languages, for nothing.

    The owner's complaint was that `/places` told them nothing about a place: the
    `why_shown` codes explain the *mechanism* -- you matched a preference -- and its
    top two appear on 793 of 832 cards. What was missing is what the place **is**.

    Discovery already stores a `wikidata` QID for 373 of 832 Taipei candidates, and
    Wikidata answers with sitelinks for every language plus a `P18` image claim. So
    one call there and one Wikipedia summary call per language gives human-written
    prose in `en` and `th` and a photograph, at **US$0.00 and with no API key**.

    Why not an LLM, which the owner also asked about: it would cost money
    (`openai:interpret_revision` is US$0.002 a call) to generate something unsourced
    and worse than an encyclopedia article that already exists in both languages. An
    LLM earns its place only for gap-filling -- condensing, or translating where
    `thwiki` is absent -- which is generation from a cited source rather than recall.

    Going straight to Wikipedia does not work: OSM's own tags for Taipei are 333 `zh`
    against 12 `en`, so the article you reach is Chinese. Wikidata is the bridge.
    """

    name = "wikidata"
    operation = "wikidata:summary"
    kind = "place_summary"
    # v2 adds Commons geosearch. A stored summary carries the version it was written
    # under, so bumping this refetches every place once and no further -- without it a
    # place cached before geosearch existed keeps its empty gallery for the 60-day TTL,
    # which is what left cards blank after the source was added.
    cache_version = "wikidata-summary-v2"
    # An encyclopedia article changes slowly and a description is not a fact the
    # planner schedules against, so this can sit for a long time.
    cache_ttl_days = 60
    languages = ("en", "th")
    # `WF-005` requires "permitted imagery" on every card and the owner asked for a
    # tappable gallery. `prop=images` on the article gives one free list -- 27 for
    # Chiang Kai-shek Memorial Hall -- so a gallery costs one extra request and no
    # money. Capped because a card is not a photo album.
    gallery_limit = 6
    # Rasters only. SVG on a Wikipedia article is almost always an icon, a locator
    # map or a flag, never a photograph of the place.
    photo_suffixes = (".jpg", ".jpeg", ".png")
    # Wikimedia Commons geosearch: photographs *near* a coordinate. This is the third
    # source, and it exists because the first two need a Wikidata id and 61% of the
    # Taipei catalogue has none — those places were skipped outright, which is why so
    # many cards had no picture at all. Every candidate has coordinates, so this one
    # always applies.
    #
    # It answers "what is photographed at this spot", NOT "photographs of this place",
    # and the two are not the same: 300m around Taipei 101 returns a sunset over the
    # city and a street in Keelung. So the radius is tight, the result is used only
    # where nothing better exists, and it is stored flagged as nearby so the screen can
    # say so rather than implying the picture is of the place.
    nearby_radius_metres = 150
    nearby_limit = 6

    def __init__(self) -> None:
        self.wikidata_url = os.environ.get(
            "TOURIST_WIKIDATA_URL", "https://www.wikidata.org/w/api.php"
        )
        self.commons_url = os.environ.get(
            "TOURIST_COMMONS_URL", "https://commons.wikimedia.org/w/api.php"
        )
        self.user_agent = os.environ.get(
            "TOURIST_USER_AGENT", "TouristPlannerPersonalPOC/0.2 (local personal use)"
        )

    def cache_descriptor(self, qid: str) -> dict[str, Any]:
        return {
            "operation": "place_summary",
            "provider": self.name,
            "version": self.cache_version,
            "qid": str(qid),
        }

    # Wikimedia rate-limits bursts and asks for serial requests with a descriptive
    # agent. Eight of thirteen places came back HTTP 429 without this.
    pause_seconds = 0.4
    retries = 2

    def _json(self, url: str) -> Any:
        request = Request(
            url, headers={"Accept": "application/json", "User-Agent": self.user_agent}
        )
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            if attempt or self.pause_seconds:
                sleep(self.pause_seconds * (attempt + 1))
            try:
                return _request_json_shared(request)
            except ProviderUnavailable as error:
                last = error
                if "429" not in str(error):
                    raise
        raise last if last else ProviderUnavailable("Wikidata unreachable")

    def _gallery(self, sitelinks: dict[str, Any]) -> list[str]:
        """Photographs from whichever article exists, cheapest language first."""

        for code in self.languages:
            link = sitelinks.get(f"{code}wiki")
            if not link:
                continue
            try:
                listing = self._json(
                    f"https://{code}.wikipedia.org/w/api.php?action=query&format=json"
                    "&prop=images&imlimit=40&titles="
                    + quote(str(link["title"]).replace(" ", "_"))
                )
            except ProviderUnavailable:
                continue
            pages = list(((listing.get("query") or {}).get("pages") or {}).values())
            names = [
                str(item.get("title") or "")
                for page in pages
                for item in (page.get("images") or [])
            ]
            found = [
                "https://commons.wikimedia.org/wiki/Special:FilePath/"
                + quote(name.removeprefix("File:").replace(" ", "_"))
                + "?width=640"
                for name in names
                if name.lower().endswith(self.photo_suffixes)
            ]
            if found:
                return found
        return []

    def nearby_photos(self, latitude: float, longitude: float) -> list[str]:
        """Commons files photographed within `nearby_radius_metres` of a point.

        Returns direct thumbnail URLs, which are the file itself rather than the
        `Special:FilePath` redirect the other two sources use — so these load in one
        round trip instead of two.

        Never raises: this is a fallback for a place that already has no picture, and
        failing to find one is the state it was already in.
        """

        query = urlencode(
            {
                "action": "query",
                "format": "json",
                "generator": "geosearch",
                "ggscoord": f"{latitude}|{longitude}",
                "ggsradius": str(self.nearby_radius_metres),
                "ggslimit": str(self.nearby_limit),
                # Namespace 6 is File:. Without it geosearch returns articles.
                "ggsnamespace": "6",
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": "640",
            }
        )
        try:
            payload = self._json(f"{self.commons_url}?{query}")
        except ProviderUnavailable:
            return []
        pages = ((payload.get("query") or {}).get("pages") or {})
        found: list[str] = []
        for page in pages.values() if isinstance(pages, dict) else []:
            title = str(page.get("title") or "")
            if not title.lower().endswith(self.photo_suffixes):
                continue
            info = (page.get("imageinfo") or [{}])[0]
            url = str(info.get("thumburl") or info.get("url") or "")
            if url:
                found.append(url)
        # Deterministic: geosearch returns distance order, but the page map is a dict
        # keyed by page id, so without sorting the gallery reshuffles between runs.
        return sorted(found)

    def summary(self, qid: str) -> dict[str, Any]:
        """Titles, extracts and an image for one Wikidata entity.

        Returns whichever languages exist. A place with no article in either language
        yields empty `text`, which is a visible gap rather than an invented sentence.
        """

        sites = "|".join(f"{code}wiki" for code in self.languages)
        codes = "|".join(self.languages)
        entity = self._json(
            f"{self.wikidata_url}?action=wbgetentities&ids={quote(str(qid))}"
            # `labels` rides along in the request already being made, so an English name
            # for a Chinese-only place costs nothing extra. 61% of the Taipei catalogue
            # has no `name:en` in OpenStreetMap at all.
            f"&props=sitelinks|claims|labels&languages={codes}&sitefilter={sites}"
            f"&format=json"
        )
        found = ((entity.get("entities") or {}).get(str(qid))) or {}
        if not found or "missing" in found:
            raise ProviderUnavailable(f"Wikidata has no entity {qid}")
        sitelinks = found.get("sitelinks") or {}
        claims = found.get("claims") or {}

        image = None
        for claim in claims.get("P18") or []:
            filename = (claim.get("mainsnak") or {}).get("datavalue", {}).get("value")
            if filename:
                # Special:FilePath redirects to the current file, so no thumbnail URL
                # has to be constructed or kept in step with Wikimedia's layout.
                image = (
                    "https://commons.wikimedia.org/wiki/Special:FilePath/"
                    + quote(str(filename).replace(" ", "_"))
                    + "?width=640"
                )
                break

        gallery: list[str] = []
        if image:
            gallery.append(image)

        text: dict[str, str] = {}
        for code in self.languages:
            link = sitelinks.get(f"{code}wiki")
            if not link:
                continue
            title = quote(str(link["title"]).replace(" ", "_"))
            try:
                page = self._json(
                    f"https://{code}.wikipedia.org/api/rest_v1/page/summary/{title}"
                )
            except ProviderUnavailable:
                continue  # one missing language must not lose the other
            extract = (page.get("extract") or "").strip()
            if extract:
                text[code] = extract
            if image is None:
                image = ((page.get("thumbnail") or {}).get("source")) or None
                if image:
                    gallery.append(image)

        gallery.extend(self._gallery(sitelinks))

        # Wikidata's label is the entity's name in that language, which is exactly what a
        # place with no `name:en` is missing. Preferred over the Wikipedia article title
        # in `sitelinks`, which carries disambiguation a name should not -- "Zhongshan
        # (Taipei)" is an article title, not what anyone calls the place. The title is
        # the fallback where no label exists.
        names: dict[str, str] = {}
        for code in self.languages:
            label = ((found.get("labels") or {}).get(code) or {}).get("value")
            title = (sitelinks.get(f"{code}wiki") or {}).get("title")
            value = str(label or title or "").strip()
            if value:
                names[code] = value

        return {
            "qid": str(qid),
            "names": names,
            "text": text,
            "image_url": image or (gallery[0] if gallery else None),
            # First is the curated P18 where there is one, then article photographs.
            "image_urls": gallery[: self.gallery_limit],
            # Wikipedia and Commons are CC BY-SA. Recorded with the value so the
            # screen can attribute it without guessing.
            "licence": "CC BY-SA, Wikipedia and Wikimedia Commons",
            "source_urls": {
                code: f"https://{code}.wikipedia.org/wiki/"
                + quote(str((sitelinks.get(f"{code}wiki") or {}).get("title", "")).replace(" ", "_"))
                for code in self.languages
                if sitelinks.get(f"{code}wiki")
            },
        }


class OsmMetroProvider:
    """Transit legs from OpenStreetMap metro topology, when no timetable exists.

    `WF-038` chose GTFS, and Taipei's feed turned out to need a Taiwan mobile number
    or a manual identity review to obtain. This is the way in that needs no account
    at all: the app already queries Overpass for free, and OSM carries `route=subway`
    relations listing each line's stations in order.

    **It is weaker than GTFS and says so.** OSM publishes topology, not timetables,
    so the ride time comes from distance at an assumed metro speed and the wait from
    an assumed headway — both named constants in `transit.py`. Every route is
    `status: "estimated"` and carries `basis: "nominal"`, where a GTFS route carries
    `basis: "timetable"`. Prefer a feed when one exists; `PlannerActions` does.

    Priced at zero like `openstreetmap:discover`, and priced rather than omitted,
    because an unpriced operation raises and call counts must stay reconcilable.
    """

    name = "osm_metro"
    operation = "openstreetmap:metro"
    cache_version = "osm-metro-v1"
    # A metro network changes on the timescale of construction projects.
    cache_ttl_days = 30
    mode = "transit"

    def __init__(self, destination: str = "", graph: Any | None = None) -> None:
        self.destination = destination
        self._graph = graph
        self._osm = OpenStreetMapProvider()

    def metro_query(self, bbox: list[float]) -> str:
        """Stations and the relations that order them.

        `>;` after the relations pulls in their member nodes, which is what makes the
        ordered member list resolvable — without it the relations arrive with
        references to nodes that were never returned and every line yields no edges.
        """

        bounds = ",".join(map(str, bbox))
        return f"""[out:json][timeout:90];
(
  node["railway"="station"]["station"="subway"]({bounds});
  node["railway"="station"]["subway"="yes"]({bounds});
  relation["route"="subway"]({bounds});
);
(._;>;);
out body qt;
"""

    def build_graph(self) -> Any:
        from .transit import graph_from_osm

        if self._graph is None:
            if not self.destination:
                raise ProviderUnavailable("no destination to look up a metro network for")
            location = self._osm._find_destination(self.destination)
            bbox = self._osm._bounded_bbox(location)
            payload = self._osm._request_json(
                Request(
                    self._osm.overpass_url,
                    data=urlencode({"data": self.metro_query(bbox)}).encode("utf-8"),
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": self._osm.user_agent,
                    },
                    method="POST",
                )
            )
            graph = graph_from_osm(payload.get("elements") or [])
            if not graph.edges:
                raise ProviderUnavailable(
                    "OpenStreetMap has no usable subway topology for this destination"
                )
            self._graph = graph
        return self._graph

    def cache_descriptor(
        self, origin: dict[str, Any], destination: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "operation": "metro_route",
            "provider": self.name,
            "version": self.cache_version,
            "mode": self.mode,
            "destination": self.destination,
            "origin": _point_key(origin),
            "destination_point": _point_key(destination),
        }

    def route(
        self, origin: dict[str, Any], destination: dict[str, Any]
    ) -> dict[str, Any]:
        journey = self.build_graph().journey(
            origin=(float(origin["latitude"]), float(origin["longitude"])),
            destination=(float(destination["latitude"]), float(destination["longitude"])),
        )
        if journey is None:
            raise ProviderUnavailable(
                "no metro connection within walking reach of both places"
            )
        return {
            "origin_id": str(origin["place_id"]),
            "destination_id": str(destination["place_id"]),
            "mode": self.mode,
            "duration_minutes": journey.total_minutes,
            # Access and egress only; the ride is not walking. This is what lets a
            # cross-city leg pass a walking cap at all.
            "walking_minutes": journey.walking_minutes,
            "distance_m": None,
            "transfers": journey.transfers,
            "boarding_buffer_minutes": journey.waiting_minutes,
            "experience_evidence": [],
            # Topology plus assumed speed and headway. Never "verified".
            "status": "estimated",
            "provider": self.name,
        }


class GtfsTransitProvider:
    """Transit legs from a local GTFS feed, normalized like any other route.

    `WF-038`. The feed is a file on disk, so this makes no request, costs nothing,
    and works offline — which is why it is priced at zero rather than left
    unpriced. `usage.PRICES_USD` still carries an entry, because an unpriced
    operation raises rather than being assumed free.

    Two properties matter to the planner. The mode is `transit`, which the
    optimizer already tolerates: it special-cases only `walk` and `bike`, for heat
    and cycling limits. And `walking_minutes` counts **access and egress only**,
    never the ride — which is the whole point, because
    `maximum_walking_minutes_per_leg` measures `walking_minutes`, so a 40-minute
    ride with a 5-minute walk to the station passes a 25-minute walking cap that a
    40-minute walk could never pass.

    Routes are `status: "estimated"`, never `"verified"`: the journey is derived
    from the timetable rather than looked up in it, so it does not know that the
    last train has gone. `travel_planner/gtfs.py` states the model's limits.
    """

    name = "gtfs"
    operation = "gtfs:transit"
    cache_version = "gtfs-transit-v1"
    # Long, because the feed itself is the thing that goes stale, and replacing the
    # file is the deliberate act that should invalidate these.
    cache_ttl_days = 30
    mode = "transit"

    def __init__(self, feed: Any | None = None) -> None:
        self._feed = feed
        self._path = os.environ.get("TOURIST_GTFS_PATH", "data/gtfs/transit.zip")

    @property
    def feed(self) -> Any:
        """Loaded once and reused; parsing a city feed is not free in time."""

        if self._feed is None:
            from .gtfs import GtfsUnavailable, TransitFeed

            try:
                self._feed = TransitFeed(self._path)
            except GtfsUnavailable as error:
                raise ProviderUnavailable(f"GTFS feed unusable: {error}") from error
        return self._feed

    def cache_descriptor(
        self, origin: dict[str, Any], destination: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "operation": "transit_route",
            "provider": self.name,
            "version": self.cache_version,
            "mode": self.mode,
            "feed": Path(self._path).name,
            "origin": _point_key(origin),
            "destination": _point_key(destination),
        }

    def route(
        self, origin: dict[str, Any], destination: dict[str, Any]
    ) -> dict[str, Any]:
        journey = self.feed.journey(
            origin=(float(origin["latitude"]), float(origin["longitude"])),
            destination=(float(destination["latitude"]), float(destination["longitude"])),
        )
        if journey is None:
            raise ProviderUnavailable(
                "no transit connection within walking reach of both places"
            )
        return {
            "origin_id": str(origin["place_id"]),
            "destination_id": str(destination["place_id"]),
            "mode": self.mode,
            "duration_minutes": journey.total_minutes,
            # Access and egress only. The ride is not walking.
            "walking_minutes": journey.walking_minutes,
            # Straight-line: a transit journey's shape is the network's, not a
            # distance this provider can honestly report.
            "distance_m": None,
            "transfers": journey.transfers,
            "boarding_buffer_minutes": journey.waiting_minutes,
            # A ride between two stops is a transfer, not an experience.
            "experience_evidence": [],
            # Derived from the timetable, not looked up in it.
            "status": "estimated",
            "provider": self.name,
        }


def _request_json_shared(request: Request) -> Any:
    """The same refusal shape every provider here uses, without inheritance."""

    try:
        with urlopen(request, timeout=45) as response:  # noqa: S310 - fixed API URLs
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise ProviderUnavailable(f"Provider HTTP {error.code}") from error
    except (URLError, TimeoutError) as error:
        raise ProviderUnavailable("Provider unreachable") from error
    except json.JSONDecodeError as error:
        raise ProviderUnavailable("Provider returned invalid JSON") from error


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
    # Google returns at most five reviews from `places:searchText`, so this is its
    # ceiling rather than a limit chosen here. Asking for ten would not produce ten.
    REVIEW_LIMIT = 5
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
        # Every review the response carries, not the first three. `places:searchText`
        # returns at most five per place — that is Google's ceiling, not a cap chosen
        # here — and the call is already paid for by the time they are discarded.
        for raw in (match.get("reviews") or [])[: GooglePlacesCardProvider.REVIEW_LIMIT]:
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
        self.model = os.environ.get("TOURIST_OPENAI_MODEL", "gpt-5.6-luna")

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
