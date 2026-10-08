"""Import an owner-authored tour guide through the existing planner contracts.

The supported layout is the reference timetable's Time/Activity/Area/Transport/
Route/Duration/Priority/Meal/Plan B columns. This is deliberately not a general
Excel interpreter. Images and formula evaluation are not needed for planning.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import re
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from . import checklist, costs
from .core import freeze_snapshot, new_candidate_choice, new_discovery_run, new_setup_draft
from .optimizer import optimize_trip, validate_variant

EVIDENCE_KIND = "imported_tour_guide"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
PRIORITIES = {"MUST": "must_do", "STRONG": "interested", "FLEX": "maybe"}


def read_workbook(path: Path) -> dict[str, list[dict[str, str]]]:
    """Read values, including cached formulas, without evaluating workbook code."""
    with ZipFile(path) as archive:
        paths = [item for item in archive.infolist() if item.filename.startswith("xl/") and item.filename.endswith(".xml") and "/media/" not in item.filename]
        if sum(item.file_size for item in paths) > 32_000_000:
            raise ValueError("Workbook XML exceeds the 32 MB import limit")
        strings = ["".join(t.text or "" for t in item.findall(".//s:t", NS)) for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))] if "xl/sharedStrings.xml" in archive.namelist() else []
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        result = {}
        for sheet in ET.fromstring(archive.read("xl/workbook.xml")).find("s:sheets", NS):
            target = targets[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            rows = []
            for row in ET.fromstring(archive.read(target)).findall(".//s:sheetData/s:row", NS):
                values = {"_row": row.attrib["r"]}
                for cell in row:
                    value = cell.findtext("s:v", "", NS)
                    if cell.attrib.get("t") == "s":
                        value = strings[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        value = "".join(t.text or "" for t in cell.findall(".//s:t", NS))
                    values[re.sub(r"\d", "", cell.attrib["r"])] = value
                if len(values) > 1:
                    rows.append(values)
            result[sheet.attrib["name"]] = rows
        return result


def _english(name: str) -> str:
    if name.startswith("ตื่น"):
        return "Wake / prepare"
    if name.startswith("中正橋"):
        return "Zhongzheng Bridge Viewpoint / golden hour"
    # Keep official English text; Thai/local-language instructions remain in notes.
    return re.split(r"[\u0e00-\u0e7f\u3400-\u9fff]", name)[0].strip(" /—-") or name


def _interval(value: str) -> tuple[int, int] | None:
    parts = re.split("[–—]", value)
    if len(parts) != 2:
        return None
    start = re.search(r"(\d{1,2}):(\d{2})", parts[0])
    end = re.search(r"(\d{1,2}):(\d{2})", parts[1])
    if not start or not end:
        return None
    a, b = (int(match[1]) * 60 + int(match[2]) for match in (start, end))
    if any(int(match[2]) >= 60 or int(match[1]) >= 24 for match in (start, end)):
        raise ValueError(f"Invalid local time: {value}")
    return a, b + (1440 if b <= a else 0)


def _clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def choice_signature(actions: list[dict[str, Any]]) -> str:
    return freeze_snapshot({"choices": sorted((item["place_id"], item["action"]) for item in actions)}).sha256


def prepare_import(path: Path, *, setup: dict[str, Any], destination: str, locations: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Compile before writing anything. All source schedules remain provisional."""
    sheets = read_workbook(path)
    rows = sheets.get("ตารางเวลา", [])
    if not any(row.get("A") == "เวลา" and "กิจกรรม" in row.get("B", "") for row in rows):
        raise ValueError("Expected the tour-guide timetable columns on ตารางเวลา")
    source = {"filename": path.name, "sha256": sha256(path.read_bytes()).hexdigest()}
    taipei, bangkok = ZoneInfo("Asia/Taipei"), ZoneInfo("Asia/Bangkok")
    days: dict[str, list[dict[str, Any]]] = {}
    purposes, venues, journeys, annotations, notices = {}, {}, [], [], []
    current, home = None, False
    meal_windows: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        header = re.search(r"(\d+)\s+(ธ\.ค\.|ม\.ค\.)\s+(\d{4})", row.get("A", ""))
        if header:
            current = f"{header[3]}-{'12' if header[2] == 'ธ.ค.' else '01'}-{int(header[1]):02d}"
            purposes[current] = row.get("A", "").split("|", 2)[-1].strip()
            home = current == setup["trip_basics"]["start_date"]
            continue
        if not current or not row.get("B"):
            continue
        times = _interval(row.get("A", ""))
        name = _english(row["B"])
        if not times or current < setup["trip_basics"]["start_date"]:
            annotations.append({"date": current, "title": name, "note": " | ".join(row.get(key, "") for key in ("A", "C", "E", "F", "I") if row.get(key))})
            continue
        day = current
        # The crowd exit belongs to the previous evening, not to the recovery day.
        if times[0] < 120 and "2027-01-01" == current:
            day = (datetime.fromisoformat(current) - timedelta(days=1)).date().isoformat()
            times = times[0] + 1440, times[1] + 1440
        midnight = datetime.fromisoformat(day).replace(tzinfo=bangkok if home else taipei)
        starts, ends = (midnight + timedelta(minutes=value) for value in times)
        flight = bool(re.match(r"(?:TG|FD)\d+\b", name))
        if flight and "BKK → TPE" in name:
            ends = ends.replace(tzinfo=taipei)
        elif flight and "TPE → BKK" in name:
            ends = ends.replace(tzinfo=bangkok)
        starts_local, ends_local = starts.astimezone(taipei), ends.astimezone(taipei)
        local_midnight = datetime.fromisoformat(day).replace(tzinfo=taipei)
        a, b = (round((value - local_midnight).total_seconds() / 60) for value in (starts_local, ends_local))
        duration = b - a
        if duration <= 0:
            raise ValueError(f"Nonpositive elapsed duration at timetable row {row['_row']}")
        priority = PRIORITIES.get(row.get("G"), "interested")
        is_meal = row.get("G") == "MEAL" or any(word in name.lower() for word in ("proper lunch", "dinner", "breakfast", "brunch"))
        rail = any(word in row.get("D", "").lower() for word in ("tra", "thsr", "ferry"))
        kind = "logistics" if flight else "travel" if rail or row.get("G") == "TRANSIT" else "logistics" if row.get("G") in {"FIXED", "CHECKPOINT"} else "preparation" if row.get("G") == "PREP" else "buffer" if row.get("G") == "BUFFER" else "meal" if is_meal else "visit"
        role = "dinner" if "dinner" in name.lower() else "breakfast" if "breakfast" in name.lower() or "brunch" in name.lower() else "lunch" if "lunch" in name.lower() else None
        if role and kind in {"meal", "visit"}:
            meal_windows.setdefault(day, {})[role] = {"start": _clock(a), "end": _clock(b)}
        mode = "walk" if row.get("D") in {"Walk", "Hike"} else "taxi" if any(word in row.get("D", "").lower() for word in ("taxi", "grab", "aot")) and not any(word in row.get("D", "").lower() for word in ("mrt", "lrt")) else "transit"
        source_row = f"{path.name} · ตารางเวลา!{row['_row']}"
        note = " | ".join(row.get(key, "") for key in ("C", "D", "E", "H", "I") if row.get(key) and row[key] != "—")
        note += f" | Source time: {row.get('A')}; target, check actual booking/service."
        item = {"name": name, "type": kind, "duration_minutes": duration, "preferred_interval": {"start": _clock(a), "end": _clock(b)},
                "walking_minutes": duration if kind == "travel" and mode == "walk" else 0,
                "mode": mode, "meal_role": role, "kind": role or kind,
                "priority": priority, "sources": [], "source_reference": source_row, "note": note,
                "status": "assumed", "alternative": row.get("I", ""), "reason": row.get("H") or row.get("I") or source_row,
                "latitude": None, "longitude": None}
        if kind == "travel":
            endpoints = name.split("→")
            item.update(status="estimated", sightseeing_walk=row.get("D") == "Hike", from_name=endpoints[0].strip(), to_name=endpoints[-1].strip(),
                        route_codes=[row.get("E") or row.get("D")], transfers=1 if "→" in row.get("D", "") or "+" in row.get("D", "") else 0)
        if kind in {"visit", "meal"} and row.get("G") in PRIORITIES:
            identifier = "guide_" + sha256(f"{day}:{name}".encode()).hexdigest()[:20]
            point = (locations or {}).get(name, {})
            item.update(place_id=identifier, latitude=point.get("latitude"), longitude=point.get("longitude"))
            venues[identifier] = {"id": identifier, "place_id": identifier, "name": name, "names": {"en": name}, "kind": "attraction", "category": "attraction",
                                  "priority": priority, "score": {"must_do": 80, "interested": 60, "maybe": 30}[priority], "duration_minutes": duration,
                                  "requires_opening_evidence": True, "requires_route_evidence": True, "operational_status": "needs_verification",
                                  "latitude": point.get("latitude"), "longitude": point.get("longitude"), "address": row.get("C"),
                                  "planned_date": day, "planned_interval": item["preferred_interval"], "reason": note, "alternative": row.get("I", "")}
            venues[identifier]["operational_evidence"] = {field: {"value": None, "state": "unconfirmed"} for field in ("opening_hours", "best_time", "access")}
        if flight:
            notices.append(f"{name}: local clocks {starts.strftime('%H:%M %z')} → {ends.strftime('%H:%M %z')}; elapsed {duration} min (not the clock difference).")
            item["note"] += " | " + notices[-1]
        # Outbound pre-arrival and the complete departure day are fixed journey
        # operations. Others are steps of the owner's coherent daily route.
        if flight or (current == setup["trip_basics"]["start_date"] and home) or current == setup["trip_basics"]["end_date"]:
            identifier = "journey_" + sha256(source_row.encode()).hexdigest()[:16]
            if kind == "travel":
                item.update(origin_id=identifier + "_origin", destination_id=identifier + "_destination")
            journeys.append({**item, "id": identifier, "name": name, "starts_at": starts.isoformat(), "ends_at": ends.isoformat(), "origin": row.get("C"), "destination": row.get("E"), "role": "arrival" if flight and "BKK → TPE" in name else "departure" if flight and "TPE → BKK" in name else "transfer"})
        else:
            days.setdefault(day, []).append(item)
        if flight and "BKK → TPE" in name:
            home = False
        elif flight and "TPE → BKK" in name:
            home = True
    if not venues:
        raise ValueError("No timed venues found in the reference timetable")
    groups, windows = [], []
    dates = sorted(set(days) | {item["starts_at"][:10] for item in journeys})
    first, last = (datetime.fromisoformat(setup["trip_basics"][key]).date() for key in ("start_date", "end_date"))
    expected_dates = [(first + timedelta(days=offset)).isoformat() for offset in range((last - first).days + 1)]
    if dates != expected_dates:
        raise ValueError("The reference must cover exactly the trip's local dates")
    for day in dates:
        steps = days.get(day, [])
        if not steps:
            windows.append({"date": day, "start": "00:00", "end": "24:00"})
            continue
        parent = next((item.get("place_id") for item in steps if item["type"] == "visit" and item.get("place_id")), None)
        if parent is None:
            raise ValueError(f"Route for {day} has no anchor venue")
        total = sum(item["duration_minutes"] for item in steps)
        group = {**venues[parent], "name": purposes[day], "names": {"en": purposes[day]}, "steps": steps,
                 "duration_bounds": {"minimum_minutes": total, "ideal_minutes": total, "maximum_minutes": total},
                 "duration_basis": "owner_authored", "requires_opening_evidence": False, "requires_route_evidence": False,
                 "fixed_event": True, "scheduled_date": day, "preferred_interval": {"start": steps[0]["preferred_interval"]["start"], "end": steps[-1]["preferred_interval"]["end"]},
                 "priority": "must_do", "group": purposes[day], "reason": "Owner-authored route; booking and service times still require confirmation."}
        groups.append(group)
        for step in steps:
            if step.get("place_id") and step["place_id"] != parent:
                venues[step["place_id"]]["group_parent_id"] = parent
        windows.append({"date": day, **group["preferred_interval"]})
    candidates = [{**venue, "requires_route_evidence": False} for venue in venues.values() if venue["id"] not in {group["id"] for group in groups}] + groups
    original = deepcopy(setup)
    original.setdefault("planning", {})
    arrival = next(item for item in journeys if item["role"] == "arrival")
    departure = next(item for item in journeys if item["role"] == "departure")
    original["trip_basics"].update(arrival_time=datetime.fromisoformat(arrival["ends_at"]).astimezone(taipei).strftime("%H:%M"), departure_time=datetime.fromisoformat(departure["starts_at"]).astimezone(taipei).strftime("%H:%M"))
    original["planning"].update(complete_trip=True, brief="Owner-authored family tour guide: preserve must-see anchors, proper meals, regional corridors, protected entry targets, daylight-to-night experiences and family hike default. Challenging hike stays optional.\n" + "\n".join(purposes.values()))
    original["planning"]["day_preferences"] = [{"date": window["date"], "start": window["start"], "end": _clock(int(window["end"].split(":")[0]) % 24 * 60 + int(window["end"].split(":")[1])), "purpose": purposes.get(window["date"], "")} for window in windows if window["date"] in days]
    original["planning"]["journey_legs"] = [{key: item.get(key) for key in ("id", "name", "starts_at", "ends_at", "origin", "destination", "role")} for item in journeys if re.match(r"(?:TG|FD)\d+\b", item["name"])]
    source_input = {"schema_version": 2, "trip": {"destination": destination, "timezone": "Asia/Taipei", "local_dates": dates, "usable_windows": windows,
                    "complete_trip": True, "include_operational_timeline": False, "allow_provisional_assumptions": True, "provisional": True,
                    "requires_route_evidence": False, "journey_legs": journeys, "meal_windows_by_date": meal_windows,
                    "day_purposes": purposes, "capability_gaps": ["owner_authored_times_and_routes_need_confirmation", "ordinary_venue_walking_not_measured"], "reference_source": source},
                    "travellers": [{"id": "owner", **setup["owner"]}] + [{"id": member["traveller_id"], **member} for member in setup["travellers"]],
                    "candidates": candidates, "facts": [], "routes": [], "locks": [], "weights": {}, "thresholds": {}}
    source_input["trip"]["reference_guidance"] = {"annotations": annotations, "notices": notices, "sections": {key: sheets.get(key, []) for key in ("START HERE", "Transport Guide", "Special Day Plans", "Food & Shopping")}}
    proposal = optimize_trip(source_input)
    for variant in proposal["variants"]:
        result = validate_variant(source_input, variant)
        if not result["valid"] or any(item["status"] == "cannot_currently_fit" for item in variant["reconciliation"]):
            raise ValueError(f"Reference does not pass independent validation: {result}; reconciliation={variant['reconciliation']}")
    return {"source": source, "setup": original, "optimizer_input": source_input, "proposal": proposal, "venues": list(venues.values()),
            "annotations": annotations, "sheets": sheets, "notices": notices}


def apply_import(actions: Any, trip_id: str, prepared: dict[str, Any]) -> Any:
    """Publish only a prepared, independently valid plan; old versions stay intact."""
    if actions.store.get_trip(trip_id) is None:
        raise ValueError("Unknown trip")
    active = actions.get_active_plan(trip_id)
    if active and (active.snapshot.as_dict().get("reference_source") or active.snapshot.as_dict().get("optimizer_input", {}).get("trip", {}).get("reference_source")) == prepared["source"]:
        return active
    native = deepcopy(prepared["optimizer_input"])
    proposal = prepared["proposal"]
    variant = proposal["variants"][0]
    if freeze_snapshot(native).sha256 != proposal["input_sha256"] or not validate_variant(native, variant)["valid"] or any(item["status"] == "cannot_currently_fit" for item in variant["reconciliation"]):
        raise ValueError("Prepared plan changed since validation")
    # Parse and validate auxiliary values before the first write as well.
    for row in prepared["sheets"].get("ค่าใช้จ่าย", []):
        if int(row["_row"]) >= 14 and row.get("E") and row.get("F"):
            amount = float(row["E"]) * float(row["F"])
            freeze_snapshot({"amount": amount})  # rejects NaN/Infinity
            costs.validate_cost({"label": row.get("C"), "category": "other", "original_amount": amount, "original_currency": "TWD", "payment_state": "estimate"})
    for sheet, first in (("Booking & To-Do", 5), ("Things to Bring", 9)):
        for row in prepared["sheets"].get(sheet, []):
            if int(row["_row"]) >= first and row.get("B"):
                checklist.validate_item({"title": row["B"], "category": "packing", "requirement_level": "recommended", "timing": "do_now", "progress": "to_do", "evidence_state": "verification_needed"})
    settings = {row["A"]: row.get("B") for row in prepared["sheets"].get("ค่าใช้จ่าย", []) if row.get("A")}
    if settings.get("NT$ → THB (ประมาณ)"):
        costs.new_rate_snapshot(rates={"TWD": settings["NT$ → THB (ประมาณ)"]}, as_of=datetime.now(timezone.utc).date().isoformat(), source="Owner's workbook estimate", buffer_percent=100 * float(settings.get("Buffer (%)", 0)))
    existing_tasks = actions.list_checklist_items(trip_id)
    setup = actions.store.save_setup(new_setup_draft(trip_id=trip_id, payload=prepared["setup"], confirmed=True))
    cards = prepared["venues"]
    discovery = actions.store.add_discovery_run(new_discovery_run(trip_id=trip_id, setup_sha256=setup.snapshot.sha256, provider="owner_tour_guide", status="stale", candidates={"candidates": cards}, report={"reference_source": prepared["source"]}))
    for choice in actions.store.list_candidate_actions(trip_id):
        actions.clear_candidate_choice(trip_id=trip_id, place_id=choice["place_id"])
    for card in cards:
        actions.store.save_candidate_choice(new_candidate_choice(trip_id=trip_id, place_id=card["place_id"], discovery_run_id=discovery.run_id, action=card["priority"], reason="Imported from the owner's final tour guide", candidate=card))
    now = datetime.now(timezone.utc).isoformat()
    held = {"source": prepared["source"], "optimizer_input": native, "setup_sha256": setup.snapshot.sha256,
            "choices_sha256": choice_signature(actions.store.list_candidate_actions(trip_id))}
    actions.store.upsert_trip_evidence(trip_id=trip_id, kind=EVIDENCE_KIND, value=held, provider="owner_tour_guide", retrieved_at=now, expires_at="2099-01-01T00:00:00+00:00")
    for sheet_name, category, first_row, title_column in (("Booking & To-Do", "reservations", 5, "B"), ("Things to Bring", "packing", 9, "B")):
        for row in prepared["sheets"].get(sheet_name, []):
            if int(row["_row"]) < first_row or not row.get(title_column):
                continue
            key = f"guide:{sheet_name}:{row['_row']}"
            payload = {"title": row[title_column], "category": category, "requirement_level": "recommended", "timing": "do_now" if category == "reservations" else "24_hours_before",
                       "progress": "to_do", "evidence_state": "verification_needed", "origin": "generated", "generated_key": key,
                       "note": " | ".join(row.get(column, "") for column in ("A", "C", "F", "G", "H") if row.get(column)), "source_url": row.get("G") if category == "reservations" else None}
            deadline = re.search(r"(\d+)(?:[–-]\d+)? (Dec|Jan)", row.get("A", "")) if category == "reservations" else None
            if deadline:
                year = prepared["setup"]["trip_basics"]["start_date"][:4] if deadline[2] == "Dec" else prepared["setup"]["trip_basics"]["end_date"][:4]
                payload["due_date"] = f"{year}-{'12' if deadline[2] == 'Dec' else '01'}-{int(deadline[1]):02d}"
            previous = next((item for item in existing_tasks if item.get("generated_key") == key), None)
            if previous:
                payload.update({field: previous.get(field) for field in ("progress", "evidence_state", "authority_type", "last_checked_at", "dismissed")})
            actions.save_checklist_item(trip_id=trip_id, item=payload)
    selected_ids = {card["place_id"] for card in cards}
    for task in existing_tasks:
        if task.get("origin") == "generated" and task.get("progress") == "to_do" and str(task.get("generated_key", "")).startswith("place_booking:place:") and str(task["generated_key"]).split("place_booking:place:", 1)[1] not in selected_ids:
            actions.set_checklist_dismissed(trip_id=trip_id, item_id=task["item_id"], dismissed=True)
    for row in prepared["sheets"].get("ค่าใช้จ่าย", []):
        if int(row["_row"]) < 14 or not row.get("E") or not row.get("F"):
            continue
        category = {"Transport": "transport", "Taxi": "transport", "Activities": "activity", "Food": "food"}.get(row.get("B"), "other")
        actions.save_cost_item(trip_id=trip_id, cost_id="guide_cost_" + sha256(f"{trip_id}:{row['_row']}".encode()).hexdigest()[:20],
                               item={"label": row.get("C"), "category": category, "original_amount": float(row["E"]) * float(row["F"]), "original_currency": "TWD", "payment_state": "estimate", "actual_thb": None,
                                     "note": f"{prepared['source']['filename']} · ค่าใช้จ่าย!{row['_row']} | {row.get('M', '')} | Units: {row['F']}; shared by {row.get('G')}"})
    settings = {row["A"]: row.get("B") for row in prepared["sheets"].get("ค่าใช้จ่าย", []) if row.get("A")}
    if settings.get("NT$ → THB (ประมาณ)"):
        actions.save_rate_snapshot(trip_id=trip_id, rates={"TWD": float(settings["NT$ → THB (ประมาณ)"])}, as_of=now[:10], source="Owner's workbook estimate", buffer_percent=100 * float(settings.get("Buffer (%)", 0)))
    # Keep the supporting guides accessible with the active itinerary as well as
    # native bookings/packing/cost rows. No private source workbook is committed.
    # Freeze the same current facts, preferences and acceptances that rebuild and
    # drift checks read, after the new setup and choices have been installed.
    native = actions._optimizer_input(trip_id)
    proposal = optimize_trip(native)
    variant = proposal["variants"][0]
    if not variant["validation"]["valid"] or any(item["status"] == "cannot_currently_fit" for item in variant["reconciliation"]):
        raise ValueError("Current trip evidence conflicts with the imported timetable")
    plan = {"schema_version": 1, "optimizer_version": proposal["optimizer_version"], "input_sha256": proposal["input_sha256"],
            "optimizer_input": native, "variant": variant, "accepted_provisional": True, "reference_source": prepared["source"]}
    version = actions.save_plan_version(trip_id=trip_id, snapshot=plan, cause="import:owner_tour_guide")
    actions.store.delete_optimization_preview(trip_id)
    return version
