from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from travel_planner.actions import PlannerActions
from travel_planner.core import freeze_snapshot


ROOT = Path(__file__).resolve().parents[1]


class FoundationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "tourist.sqlite3"
        self.actions = PlannerActions(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_trip_resume_and_immutable_plan_history(self) -> None:
        trip = self.actions.create_trip(
            name="Taipei New Year",
            destination="Taipei",
            planning_mode="ready_to_schedule",
            language="en",
        )
        resumed = PlannerActions(self.database_path)
        self.assertEqual([trip], resumed.list_trips())

        first = resumed.save_plan_version(
            trip_id=trip.trip_id,
            snapshot={"days": [], "variant": "best_balance"},
            cause="initial_generation",
        )
        second = resumed.save_plan_version(
            trip_id=trip.trip_id,
            snapshot={"variant": "relaxed", "days": []},
            cause="accepted_revision",
        )
        restored = resumed.restore_plan_version(
            trip_id=trip.trip_id,
            version_id=first.version_id,
        )

        self.assertEqual(first.version_id, second.parent_version_id)
        self.assertEqual(second.version_id, restored.parent_version_id)
        self.assertEqual(first.snapshot, restored.snapshot)
        self.assertEqual(restored, resumed.get_active_plan(trip.trip_id))
        self.assertEqual(3, len(resumed.list_plan_versions(trip.trip_id)))
        self.assertEqual(
            freeze_snapshot({"variant": "best_balance", "days": []}),
            first.snapshot,
        )

        connection = sqlite3.connect(self.database_path)
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    "UPDATE plan_versions SET cause = 'changed' WHERE id = ?",
                    (first.version_id,),
                )
        finally:
            connection.close()

    def test_secret_bearing_snapshot_is_rejected(self) -> None:
        trip = self.actions.create_trip(name="", destination="Taipei")
        with self.assertRaisesRegex(ValueError, "not allowed"):
            self.actions.save_plan_version(
                trip_id=trip.trip_id,
                snapshot={"OPENAI_API_KEY": "must-not-persist"},
                cause="invalid_test",
            )
        self.assertEqual([], self.actions.list_plan_versions(trip.trip_id))

    def test_streamlit_entry_point_renders(self) -> None:
        with patch.dict(os.environ, {"TOURIST_DB_PATH": str(self.database_path)}):
            app = AppTest.from_file(ROOT / "app.py", default_timeout=10).run()
            self.assertFalse(app.exception)
            self.assertEqual("Personal Travel Planner", app.title[0].value)

            app.text_input(key="trip_name").input("Taipei New Year")
            app.text_input(key="destination").input("Taipei")
            app.selectbox(key="planning_mode").select("ready_to_schedule")
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual("Trip saved.", app.success[0].value)
            selected_id = app.selectbox(key="resume_trip").value
            self.assertEqual("Taipei", self.actions.get_trip(selected_id).destination)

            app.radio[0].set_value("th").run()
            self.assertFalse(app.exception)
            self.assertEqual("ตัวช่วยวางแผนท่องเที่ยวส่วนตัว", app.title[0].value)
            app.text_input(key="destination").input("")
            app.button[0].click().run()
            self.assertEqual("กรุณาระบุจุดหมายปลายทาง", app.error[0].value)

        saved = self.actions.list_trips()
        self.assertEqual(1, len(saved))
        self.assertEqual("Taipei", saved[0].destination)


if __name__ == "__main__":
    unittest.main()
