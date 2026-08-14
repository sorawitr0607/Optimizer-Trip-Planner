from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from tests.test_opening import FakeHoursProvider, TRIP_DATES
from tests.test_routes import FakePlaceProvider, FakeRouteProvider, FakeTimeZoneProvider
from travel_planner.actions import PlannerActions
from travel_planner.exporters import (
    checklist_ics,
    plan_workbook_xlsx,
)


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

            # The POC drove these two steps by clicking generate and then
            # activate. Those buttons only ever called these two methods, and
            # this is the real path rather than a fixture: the preview is built
            # from the trip's own setup, discovery, choices and evidence above.
            preview = actions.generate_plan_preview(trip.trip_id)
            self.assertEqual(trip.trip_id, preview.trip_id)
            actions.activate_plan_preview(trip_id=trip.trip_id, variant_id="best_balance")

            version = actions.get_active_plan(trip.trip_id)
            self.assertIsNotNone(version)
            # The board is populated by activation itself now. Pressing Apply on
            # `/readiness` was the only way to fill it before, so an owner who never
            # visited that screen exported a workbook with no readiness in it.
            self.assertTrue(
                actions.list_checklist_items(trip.trip_id),
                "activating a plan must leave a readiness board behind",
            )
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

            # This test used to end by walking all eight POC pages and asserting
            # no exception. Its React replacement is not a unittest: the 36
            # screen baselines drive a real trip through all nine routes over
            # the real socket, and `web/src/routes.test.tsx` asserts the table
            # those routes come from. Both run inside `scripts/check.py`.


if __name__ == "__main__":
    unittest.main()
