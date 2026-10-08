"""The owner's timetable survives import, rebuild and native export."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from travel_planner.actions import PlannerActions
from travel_planner.core import freeze_snapshot
from travel_planner.exporters import plan_workbook_xlsx
from travel_planner.optimizer import optimize_trip, validate_variant
from travel_planner.tour_guide import apply_import, prepare_import, read_workbook


def source_rows():
    rows = [{"A": "เวลา", "B": "กิจกรรม"}]
    def heading(day, month="ธ.ค.", year=2026):
        rows.append({"A": f"{day} {month} {year} | Family route"})
    def item(time, name, priority="MUST", mode="Walk"):
        rows.append({"A": time, "B": name, "G": priority, "D": mode})
    heading(29)
    item("08:45–10:20", "TG260 HDY → BKK", "FIXED", "Flight")
    item("10:20–12:40", "Connection", "BUFFER", "Airport")
    item("12:40–17:20", "TG634 BKK → TPE", "FIXED", "Flight")
    item("20:25–21:10", "Longshan Temple")
    item("22:05–22:50", "Simple dinner", "MEAL")
    heading(30)
    item("09:30–10:40", "Shifen Waterfall")
    heading(31)
    item("23:30–00:10", "Countdown + fireworks")
    heading(1, "ม.ค.", 2027)
    item("00:10–01:30", "Crowd exit and return", "TRANSIT", "MRT")
    item("18:00–20:00", "Xpark Aquarium")
    heading(2, "ม.ค.", 2027)
    item("11:00–12:30", "Mundo Pixar Experience")
    heading(3, "ม.ค.", 2027)
    item("11:10–11:55", "Elephant Mountain", "MUST", "Hike")
    item("16:00–17:45", "Taipei 101 Observatory")
    item("OPTION ONLY", "95 Peak challenge", "FLEX", "Hike")
    heading(4, "ม.ค.", 2027)
    item("13:55–16:50", "TG633 TPE → BKK", "FIXED", "Flight")
    item("20:10–21:40", "FD3112 DMK → HDY", "FIXED", "Flight")
    for index, row in enumerate(rows, 1):
        row["_row"] = str(index)
    return {"ตารางเวลา": rows, "Transport Guide": [{"_row": "1", "A": "=Do not execute"}],
            "Booking & To-Do": [{"_row": "5", "B": "Reserve entry", "G": "https://example.com"}],
            "Things to Bring": [{"_row": "9", "B": "Passport"}],
            "ค่าใช้จ่าย": [{"_row": "5", "A": "NT$ → THB (ประมาณ)", "B": "1.06"},
                          {"_row": "6", "A": "Buffer (%)", "B": "0.1"},
                          {"_row": "14", "B": "Activities", "C": "Entry estimate", "E": "600", "F": "4", "G": "4"}]}


class TourGuideTest(unittest.TestCase):
    def test_native_import_rebuild_history_costs_and_export(self):
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "trip.sqlite3")
            trip = actions.create_trip(name="Real trip", destination="Taipei, Taiwan", planning_mode="ready_to_schedule")
            setup = actions.save_setup(trip_id=trip.trip_id, owner_age=26, main_style=["family"],
                start_date="2026-12-29", end_date="2027-01-04", arrival_time="17:20", departure_time="13:55", confirmed=True)
            old = actions.save_plan_version(trip_id=trip.trip_id, snapshot={"old": True}, cause="old")
            path = Path(directory) / "guide.xlsx"
            path.write_bytes(b"synthetic owner source")
            with patch("travel_planner.tour_guide.read_workbook", return_value=source_rows()):
                prepared = prepare_import(path, setup=setup.snapshot.as_dict(), destination=trip.destination)
            native = prepared["optimizer_input"]
            flights = {item["name"].split()[0]: item for item in native["trip"]["journey_legs"] if item["name"].startswith(("TG", "FD"))}
            self.assertEqual(220, flights["TG634"]["duration_minutes"])
            self.assertEqual(235, flights["TG633"]["duration_minutes"])
            self.assertTrue(flights["TG634"]["starts_at"].endswith("+07:00"))
            self.assertTrue(flights["TG633"]["ends_at"].endswith("+07:00"))
            first = prepared["proposal"]["variants"][0]
            nye = next(day for day in first["days"] if day["date"] == "2026-12-31")
            self.assertTrue(any(item["end"] == "25:30" for item in nye["items"]))
            self.assertFalse(any("95 Peak" in item.get("name", "") for day in first["days"] for item in day["items"]))
            self.assertTrue(any("95 Peak" in item["title"] for item in prepared["annotations"]))
            bad = deepcopy(first)
            flight = next(item for day in bad["days"] for item in day["items"] if item.get("fixed_commitment") and item["name"].startswith("TG634"))
            flight["name"] = "Wrong flight"
            self.assertFalse(validate_variant(native, bad)["valid"])
            broken = deepcopy(prepared)
            broken["optimizer_input"]["trip"]["destination"] = "Different"
            with self.assertRaises(ValueError):
                apply_import(actions, trip.trip_id, broken)
            self.assertEqual(old.version_id, actions.get_active_plan(trip.trip_id).version_id)
            version = apply_import(actions, trip.trip_id, prepared)
            self.assertEqual(old.version_id, version.parent_version_id)
            self.assertEqual(version.version_id, apply_import(actions, trip.trip_id, prepared).version_id)
            rebuilt = actions._optimizer_input(trip.trip_id)
            self.assertEqual(native["trip"]["reference_guidance"], rebuilt["trip"]["reference_guidance"])
            self.assertEqual(native["trip"]["meal_windows_by_date"], rebuilt["trip"]["meal_windows_by_date"])
            self.assertTrue(all(v["validation"]["valid"] for v in optimize_trip(rebuilt)["variants"]))
            self.assertEqual(2, len(actions.list_checklist_items(trip.trip_id)))
            costs = actions.store.list_cost_items(trip.trip_id)
            self.assertEqual(2400, costs[0]["original_amount"])
            self.assertEqual("estimate", costs[0]["payment_state"])
            self.assertIsNone(costs[0]["actual_thb"])
            export = actions.build_export_snapshot(trip.trip_id).as_dict()
            self.assertEqual([], export["unscheduled"])
            self.assertTrue(all(item["status"] != "verified" for day in export["days"] for item in day["items"] if item["type"] == "visit"))
            from io import BytesIO
            with ZipFile(BytesIO(plan_workbook_xlsx(export))) as archive:
                self.assertIn("Transport Guide", archive.read("xl/workbook.xml").decode())
                self.assertNotIn(b"<f>", archive.read("xl/worksheets/sheet8.xml"))
                self.assertIn(b"=Do not execute", archive.read("xl/sharedStrings.xml"))
            chosen = actions.store.list_candidate_actions(trip.trip_id)[0]
            actions.clear_candidate_choice(trip_id=trip.trip_id, place_id=chosen["place_id"])
            self.assertNotIn("reference_source", actions._optimizer_input(trip.trip_id)["trip"])

    def test_known_closing_and_bad_meal_window_still_block(self):
        from tests.test_experience_planning import snapshot, place
        native = snapshot()
        native["trip"].update(allow_provisional_assumptions=True, meal_windows_by_date={"2026-12-31": {"dinner": {"start": "22:05", "end": "22:50"}}})
        native["candidates"] = [{**place("group"), "fixed_event": True, "scheduled_date": "2026-12-31", "preferred_interval": {"start": "11:50", "end": "13:00"}, "duration_minutes": 70,
            "steps": [{"type": "visit", "place_id": "group", "name": "Anchor", "duration_minutes": 10, "preferred_interval": {"start": "11:50", "end": "12:00"}}, {"type": "visit", "place_id": "child", "name": "Child", "duration_minutes": 60, "preferred_interval": {"start": "12:00", "end": "13:00"}}]},
            {**place("child"), "group_parent_id": "group", "requires_opening_evidence": True}]
        good = optimize_trip(native)["variants"][0]
        self.assertTrue(good["validation"]["valid"])
        self.assertTrue(all(item["status"] == "fits" for item in good["reconciliation"]))
        native["facts"] = [{"subject_id": "child", "fact_type": "opening_interval", "status": "verified", "value": {"start": "09:00", "end": "11:00"}}]
        self.assertFalse(validate_variant(native, good)["valid"])
        native["trip"]["meal_windows_by_date"]["2026-12-31"]["dinner"]["end"] = "22:99"
        with self.assertRaises(ValueError):
            optimize_trip(native)

    def test_reader_uses_values_and_does_not_execute_formulas(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "book.xlsx"
            with ZipFile(path, "w") as archive:
                archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="ตารางเวลา" r:id="r1"/></sheets></workbook>')
                archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
                archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1"><f>1+2</f><v>3</v></c></row></sheetData></worksheet>')
            self.assertEqual("3", read_workbook(path)["ตารางเวลา"][0]["A"])
