"""Compact, source-backed experience research; scheduling stays deterministic."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .providers import ProviderUnavailable

RESEARCH_KIND = "experience_research"
RESEARCH_VERSION = 1


def research_key(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def valid_url(value: Any) -> bool:
    try:
        parsed = urlsplit(str(value))
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
    except ValueError:
        return False


def valid_interval(value: Any) -> bool:
    if value is None:
        return True
    try:
        clocks = [value[key].split(":") for key in ("start", "end")]
        if any(len(clock) != 2 or not 0 <= int(clock[1]) < 60 for clock in clocks):
            return False
        start, end = [int(clock[0]) * 60 + int(clock[1]) for clock in clocks]
        return 0 <= start < end <= 2880
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def normalize_research(raw: dict[str, Any], payload: dict[str, Any], sources: set[str]) -> dict[str, Any]:
    """Reject invented IDs, unsupported citations and unreasonable activity bounds."""
    known = {item["id"] for item in payload["places"]}
    dates = set(payload["dates"])
    experiences = []
    suggested = 0
    for index, item in enumerate(raw.get("experiences", [])[:40]):
        citations = [url for url in item.get("sources", []) if url in sources and valid_url(url)][:4]
        place_id = item.get("place_id")
        if not place_id:
            suggested += 1
            if suggested > 8:
                continue
        name = str(item.get("name") or "").strip()[:160]
        if not name or not citations or (place_id and place_id not in known):
            continue
        try:
            minimum, ideal, maximum = (int(item.get(field, 0)) for field in ("minimum_minutes", "ideal_minutes", "maximum_minutes"))
        except (TypeError, ValueError):
            continue
        if not 5 <= minimum <= ideal <= maximum <= 900:
            continue
        day = item.get("date")
        if day and day not in dates:
            continue
        interval = item.get("preferred_interval")
        if not valid_interval(interval):
            continue
        steps = []
        meal_index = 0
        for step in item.get("steps", [])[:16]:
            try:
                minutes = int(step["duration_minutes"])
                walking = min(minutes, max(0, int(step.get("walking_minutes") or 0)))
            except (KeyError, TypeError, ValueError):
                continue
            if step.get("type") not in {"visit", "travel", "meal", "buffer"} or not 1 <= minutes <= 240 or not valid_interval(step.get("preferred_interval")):
                continue
            role = step.get("meal_role")
            if step["type"] == "meal":
                roles = item.get("meal_roles", [])
                role = role if role in {"breakfast", "lunch", "dinner"} else (roles[meal_index] if meal_index < len(roles) else None)
                meal_index += 1
            if role not in {"breakfast", "lunch", "dinner"}:
                role = None
            steps.append({"meal_role": role, "name": str(step.get("name") or "")[:160], "type": step["type"], "duration_minutes": minutes,
                          "walking_minutes": walking,
                          "mode": step.get("mode", "walk"), "sources": citations,
                          "preferred_interval": step.get("preferred_interval"),
                          "place_id": step.get("place_id") if step.get("place_id") in known else None})
        # A group's inbound and hotel return belong to the router, not to its activity duration.
        while steps and (steps[0]["type"] == "travel" or (steps[0]["type"] == "buffer" and any(word in steps[0]["name"].casefold() for word in ("hotel", "breakfast")))):
            steps.pop(0)
        while steps and steps[-1]["type"] == "travel" and any(word in steps[-1]["name"].casefold() for word in ("return", "hotel", "ximen")):
            steps.pop()
        if steps and sum(step["duration_minutes"] for step in steps) > maximum:
            continue
        if steps:
            minimum, ideal = min(minimum, sum(step["duration_minutes"] for step in steps)), sum(step["duration_minutes"] for step in steps)
        last_known = next((step.get("place_id") for step in reversed(steps) if step["type"] == "visit" and step.get("place_id")), None)
        fixed_event = bool(item.get("fixed_event")) or any(word in name.casefold() for word in ("countdown", "fireworks"))
        experiences.append({
            "id": f"experience_{index}", "place_id": place_id, "name": name,
            "query": str(item.get("query") or name)[:200],
            "exit_query": str(item.get("exit_query") or "")[:200],
            "exit_place_id": last_known if last_known != place_id else None,
            "kind": str(item.get("kind") or "attraction")[:40],
            "daylight_exit": bool(item.get("daylight_exit")),
            "duration_bounds": {"minimum_minutes": minimum, "ideal_minutes": ideal, "maximum_minutes": maximum},
            "duration_basis": "researched_activity", "sources": citations,
            "scheduled_date": day if fixed_event else None, "proposed_date": day, "fixed_event": fixed_event,
            "preferred_interval": interval,
            "meal_roles": [role for role in item.get("meal_roles", []) if role in {"breakfast", "lunch", "dinner"}],
            "reason": str(item.get("reason") or "")[:600],
            "alternative": str(item.get("alternative") or "")[:400],
            "group": str(item.get("group") or "")[:120], "steps": steps,
        })
    return {"schema_version": RESEARCH_VERSION, "experiences": experiences,
            "day_purposes": {day: str(purpose)[:240] for day, purpose in (raw.get("day_purposes") or {}).items() if day in dates},
            "sources": sorted({url for item in experiences for url in item["sources"]}),
            "status": "researched", "operational_status": "needs_verification"}


class ExperienceResearchProvider:
    name = "openai_experience_research"
    operation = "openai:experience_research"

    def research(self, payload: dict[str, Any]) -> dict[str, Any]:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise ProviderUnavailable("OPENAI_API_KEY is not configured")
        prompt = """Design a coherent complete trip around the traveller's true anchors. Research official tourism, venue and transport sources using web search. Return a JSON object only with day_purposes (date: purpose) and experiences. Each experience has place_id (an existing id or null for a new suggestion), fixed_event (true only for a real event on an immovable date), name (official international English), query (precise entry venue/location for geocoding), exit_query (only for a connected one-way excursion/hike), kind, date (or null), minimum_minutes, ideal_minutes, maximum_minutes, preferred_interval ({start,end} HH:MM, hours may exceed 24 for overnight events, or null), meal_roles (breakfast/lunch/dinner), reason, alternative (simple attraction fallback for weather/queues/fatigue), group, sources (URLs actually read), steps (optional ordered composite steps: name,type visit/travel/meal/buffer,duration_minutes,walking_minutes,mode,preferred_interval (for a timed component),meal_role (for a meal),place_id (known id or null)). Include every existing anchor with its ID and suitable durations. Only group experiences that are one coherent excursion, neighborhood cluster, or connected trail. Never put a museum across town and a mountain hike in one group. Do not put inbound travel from the hotel or return to the hotel into composite steps: the router adds these separately. Begin each composite at its first venue and end at its final venue. Put a sunset/night experience into a timing window that actually reaches that period, including the preferred_interval on its individual composite step. Put a countdown component at 23:30–24:10 instead of treating it as ordinary evening sightseeing. Keep overnight events on their actual date and finish after midnight; an observatory visit and an outdoor countdown are distinct experiences. Prefer scheduling long hiking days separately from a late countdown day. Existing priorities are binding; never remove an anchor. Select complementary experiences based on distinct value, geography and time of day; leave breathing room. A market lunch or tea rest counts once. Group excursions and connected hikes, specify entry and exit, protect lunch before long hikes and daylight exit. Use daylight_exit=true for a connected hike; its last trail step must finish before dark. For night events, protect next-morning recovery. Arrival evening may have useful nearby activities. Use focused activity durations, not category templates. Do not add flights, flight backup advice, booking discrepancy warnings, or invented exact future transit schedules. Repeated venues are allowed only for distinct experiences, with place_id only on the first. Sources support recommendations; opening times and routes are independently validated by the application. Do not invent coordinates. Prefer at most 8 new experiences and 40 total. Composite steps must fit the duration bounds. Put all selected anchors within a composite into visit steps with their place_id; do not repeat those as standalone experiences. Use the first anchor as the parent place_id. Explicitly identify meal steps and meal_roles for composite groups. Fixed journey legs are commitments; do not schedule sightseeing over them."""
        body = json.dumps({"model": os.environ.get("TOURIST_OPENAI_MODEL", "gpt-5.6-luna"), "store": False,
                           "max_output_tokens": 12000, "max_tool_calls": 3, "tools": [{"type": "web_search"}],
                           "include": ["web_search_call.action.sources"],
                           "input": [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}).encode()
        request = Request(os.environ.get("TOURIST_OPENAI_URL", "https://api.openai.com/v1/responses"), data=body,
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=120) as response:
                reply = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ProviderUnavailable(f"Experience research unavailable: {type(error).__name__}") from None
        if reply.get("status") == "incomplete":
            raise ProviderUnavailable("Experience research was incomplete")
        sources: set[str] = set(payload.get("previous_sources", []))
        texts = []
        for output in reply.get("output", []):
            for source in (output.get("action") or {}).get("sources", []):
                if valid_url(source.get("url")):
                    sources.add(source["url"])
            for part in output.get("content", []):
                if part.get("type") == "output_text":
                    texts.append(part.get("text", ""))
                for annotation in part.get("annotations", []):
                    if valid_url(annotation.get("url")):
                        sources.add(annotation["url"])
        try:
            raw = json.loads("".join(texts).strip().removeprefix("```json").removesuffix("```").strip())
            return normalize_research(raw, payload, sources)
        except (ValueError, TypeError, AttributeError):
            raise ProviderUnavailable("Experience research returned invalid content") from None


def research_payload(snapshot: dict[str, Any], brief: str, journey_legs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"version": RESEARCH_VERSION, "destination": snapshot["trip"]["destination"],
            "dates": snapshot["trip"]["local_dates"], "timezone": snapshot["trip"].get("timezone"),
            "party_size": len(snapshot["travellers"]), "brief": brief,
            "preferences": snapshot["travellers"], "windows": snapshot["trip"]["usable_windows"],
            "journey_legs": journey_legs,
            "operational_allowances": {"arrival_settle_minutes": 60 + int(snapshot["trip"].get("terminal_transfer_minutes", 45)) + 30,
                                        "daily_preparation_minutes": 30, "breakfast_minutes": 45,
                                        "departure_reserved_minutes": 135 + int(snapshot["trip"].get("terminal_transfer_minutes", 45))},
            "places": [{key: item.get(key) for key in ("id", "name", "kind", "priority", "latitude", "longitude")} for item in snapshot["candidates"] if item.get("kind") != "hotel_area"]}


def apply_research(snapshot: dict[str, Any], evidence: dict[str, Any]) -> None:
    """Existing owner priorities survive research and recommendations remain flexible."""
    known = {item["id"]: item for item in snapshot["candidates"]}
    for experience in evidence.get("experiences", []):
        place_id = experience.get("place_id")
        if place_id in known:
            candidate = known[place_id]
            candidate["name"] = experience.get("name") or candidate.get("name")
            candidate["names"] = {**candidate.get("names", {}), "en": candidate["name"]}
            candidate["daylight_exit"] = experience.get("daylight_exit", False)
            candidate["proposed_date"] = experience.get("proposed_date")
            candidate["fixed_event"] = experience.get("fixed_event", False)
            candidate.update({key: experience[key] for key in ("duration_bounds", "duration_basis", "sources", "reason", "alternative", "group", "meal_roles", "preferred_interval", "scheduled_date", "steps")})
        elif experience.get("latitude") is not None:
            candidate = {**experience, "priority": "must_do" if experience.get("fixed_event") else "maybe", "score": 30,
                         "requires_route_evidence": True, "requires_opening_evidence": False,
                         "recommendation": True, "operational_status": "needs_verification"}
            if experience.get("exit_latitude") is not None:
                candidate["exit_id"] = experience["id"] + "_exit"
                snapshot["candidates"].append({"id": candidate["exit_id"], "name": experience["exit_query"], "kind": "group_exit",
                                               "priority": "alternative", "latitude": experience["exit_latitude"], "longitude": experience["exit_longitude"]})
            snapshot["candidates"].append(candidate)
        else:
            continue
        if experience.get("exit_latitude") is not None and place_id in known:
            candidate["exit_id"] = place_id + "_exit"
            snapshot["candidates"].append({"id": candidate["exit_id"], "name": experience["exit_query"], "kind": "group_exit", "priority": "alternative",
                                          "latitude": experience["exit_latitude"], "longitude": experience["exit_longitude"]})
        if experience.get("exit_place_id") in known:
            candidate["exit_id"] = experience["exit_place_id"]
        if experience.get("owner_priority"):
            candidate["priority"] = experience["owner_priority"]
        if candidate.get("steps"):
            for step in candidate["steps"]:
                member_id = step.get("place_id")
                if member_id and member_id != candidate["id"] and member_id in known:
                    known[member_id]["group_parent_id"] = candidate["id"]
                    if known[member_id].get("priority") == "must_do":
                        candidate["priority"] = "must_do"
    snapshot["trip"]["day_purposes"] = evidence.get("day_purposes", {})
    snapshot["trip"]["research_status"] = evidence.get("status", "unavailable")
    snapshot["trip"]["research_reason"] = evidence.get("reason", "")
    if any(item.get("recommendation") for item in snapshot["candidates"]):
        snapshot["trip"]["provisional"] = True
