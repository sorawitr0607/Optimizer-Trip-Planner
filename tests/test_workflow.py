from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from streamlit.testing.v1 import AppTest

from tests.test_opening import FakeHoursProvider, TRIP_DATES
from tests.test_routes import FakePlaceProvider, FakeRouteProvider, FakeTimeZoneProvider
from travel_planner.actions import PlannerActions
from travel_planner.exporters import (
    checklist_ics,
    plan_workbook_xlsx,
)


ROOT = Path(__file__).resolve().parents[1]


class FullWorkflowTest(unittest.TestCase):
    def test_owner_can_go_from_new_trip_to_every_export(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "full-workflow.sqlite3"
            actions = PlannerActions(
                path,
                place_provider=FakePlaceProvider(),
                route_provider=FakeRouteProvider(),
                timezone_provider=FakeTimeZoneProvider(),
                hours_provider=FakeHoursProvider(),
            )

            trip = actions.create_trip(
                name="Taipei test journey",
                destination="Taipei, Taiwan",
                planning_mode="ready_to_schedule",
            )
            actions.save_setup(
                trip_id=trip.trip_id,
                owner_age=26,
                main_style=["sightseeing", "culture"],
                also_enjoy=["photography"],
                travellers=[
                    {"label": "Traveller", "age": 19, "tags": ["night_view"]},
                    {"label": "Mother", "age": 50, "tags": ["culture", "nature"]},
                ],
                start_date=TRIP_DATES[0],
                end_date=TRIP_DATES[-1],
                arrival_time="09:00",
                departure_time="21:00",
                accommodation_status="booked",
                confirmed=True,
            )
            discovery = actions.discover_places(trip_id=trip.trip_id)
            ranking = actions.rank_candidates(trip.trip_id)
            self.assertEqual(
                len(discovery.candidates.as_dict()["candidates"]),
                len(ranking["lanes"]["browse_all"]),
            )
            for place_id in ranking["lanes"]["browse_all"]:
                actions.save_candidate_choice(
                    trip_id=trip.trip_id, place_id=place_id, action="must_do"
                )

            actions.refresh_opening_hours(trip.trip_id)
            actions.refresh_routes(trip.trip_id)
            actions.refresh_timezone(trip.trip_id)
            self.assertEqual([], actions._optimizer_input(trip.trip_id)["trip"]["capability_gaps"])

            with patch.dict(os.environ, {"TOURIST_DB_PATH": str(path)}):
                app = AppTest.from_file(ROOT / "app.py", default_timeout=20)
                app.switch_page("views/evidence.py")
                app.run()
                app.button(key=f"continue_optimize_{trip.trip_id}").click().run()
                self.assertFalse(app.exception)
                self.assertIn("Whole-trip optimizer", [item.value for item in app.subheader])

                # AppTest retains widgets from the page that called switch_page;
                # a fresh harness mirrors the clean browser-page run.
                app = AppTest.from_file(ROOT / "app.py", default_timeout=20)
                app.switch_page("views/optimize.py")
                app.run()
                app.button(key=f"generate_plan_{trip.trip_id}").click().run()
                self.assertFalse(app.exception)
                app.button(
                    key=f"activate_plan_{trip.trip_id}_best_balance"
                ).click().run()
                self.assertFalse(app.exception)
                self.assertIn("Active plan", [item.value for item in app.subheader])

            version = actions.get_active_plan(trip.trip_id)
            self.assertIsNotNone(version)
            actions.apply_checklist_proposal(trip.trip_id)
            snapshot = actions.build_export_snapshot(trip.trip_id).as_dict()

            # The reference workbooks are complete trip timetables, not only
            # attraction lists.  The shared result must therefore carry the
            # recurring operational rows seen across those four trips.
            timeline = [
                item for day in snapshot["days"] for item in day["items"]
            ]
            kinds = {item.get("kind") for item in timeline}
            self.assertTrue(
                {
                    "pack_bags",
                    "airport_arrival",
                    "accommodation_check_in",
                    "breakfast",
                    "lunch",
                    "dinner",
                    "pack_and_check_out",
                    "airport_departure",
                }.issubset(kinds)
            )
            for item in timeline:
                if item["type"] in {"preparation", "meal", "logistics"}:
                    self.assertTrue(item["display_name"])
                    self.assertTrue(item["notes"])
            for day in snapshot["days"]:
                self.assertEqual(
                    [item["end"] for item in day["items"][:-1]],
                    [item["start"] for item in day["items"][1:]],
                )

            workbook = plan_workbook_xlsx(snapshot)
            calendar = checklist_ics(snapshot)
            self.assertTrue(zipfile.is_zipfile(BytesIO(workbook)))
            archive = zipfile.ZipFile(BytesIO(workbook))
            workbook_text = archive.read("xl/sharedStrings.xml").decode("utf-8")
            for expected in (
                "Pack bags for the forecast and planned activities",
                "Arrival terminal: immigration, baggage and essentials",
                "Breakfast near the base or first stop",
                "Lunch near the surrounding stops",
                "Dinner near the evening route",
                "Pack, room sweep, check out and collect bags",
                "Operational notes",
            ):
                self.assertIn(expected, workbook_text)
            self.assertTrue(calendar.startswith(b"BEGIN:VCALENDAR"))
            self.assertEqual(version.version_id, snapshot["stamp"]["plan_version_id"])
            self.assertEqual("ready", snapshot["readiness"]["state"])

            with patch.dict(os.environ, {"TOURIST_DB_PATH": str(path)}):
                app = AppTest.from_file(ROOT / "app.py", default_timeout=20)
                for page in (
                    "views/setup.py",
                    "views/places.py",
                    "views/evidence.py",
                    "views/optimize.py",
                    "views/itinerary.py",
                    "views/readiness.py",
                    "views/costs.py",
                    "views/revise.py",
                ):
                    app.switch_page(page)
                    app.run()
                    self.assertFalse(app.exception, page)


if __name__ == "__main__":
    unittest.main()
