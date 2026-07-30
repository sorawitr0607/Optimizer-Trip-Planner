from __future__ import annotations

import json
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

    def test_delete_trip_removes_planning_data_but_keeps_paid_usage(self) -> None:
        victim = self.actions.create_trip(name="Delete me", destination="Taipei")
        keeper = self.actions.create_trip(name="Keep me", destination="Kyoto")
        self.actions.save_setup(
            trip_id=victim.trip_id, main_style=["culture"], confirmed=True
        )
        self.actions.save_setup(trip_id=keeper.trip_id, main_style=["nature"])
        self.actions.save_plan_version(
            trip_id=victim.trip_id,
            snapshot={"variant": "best_balance", "days": []},
            cause="deletion_test",
        )
        self.actions.record_paid_call(
            operation="google_places:details", trip_id=victim.trip_id
        )

        candidates = freeze_snapshot({"candidates": []})
        report = freeze_snapshot({"coverage": "test"})
        revision = freeze_snapshot({"request": "test"})
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                """
                INSERT INTO discovery_runs
                    (id, trip_id, setup_sha256, provider, status, candidates_json,
                     candidates_sha256, report_json, report_sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "discovery_delete_test",
                    victim.trip_id,
                    "setup-test",
                    "test",
                    "verified",
                    candidates.canonical_json,
                    candidates.sha256,
                    report.canonical_json,
                    report.sha256,
                    "2026-07-30T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO plan_revisions
                    (id, trip_id, snapshot_json, snapshot_sha256, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "revision_delete_test",
                    victim.trip_id,
                    revision.canonical_json,
                    revision.sha256,
                    "2026-07-30T00:00:00+00:00",
                ),
            )
            connection.commit()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    "DELETE FROM plan_versions WHERE trip_id = ?", (victim.trip_id,)
                )
        finally:
            connection.close()

        self.actions.delete_trip(victim.trip_id)

        self.assertIsNone(self.actions.get_trip(victim.trip_id))
        self.assertEqual([keeper], self.actions.list_trips())
        self.assertEqual(
            victim.trip_id, self.actions.store.list_paid_usage()[0]["trip_id"]
        )
        connection = sqlite3.connect(self.database_path)
        try:
            trip_tables = []
            for (table,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ):
                columns = {
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                }
                if "trip_id" in columns and table not in {"paid_usage", "trip_deletions"}:
                    trip_tables.append(table)
            for table in trip_tables:
                remaining = connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE trip_id = ?", (victim.trip_id,)
                ).fetchone()[0]
                self.assertEqual(0, remaining, table)
            self.assertEqual(
                0,
                connection.execute("SELECT COUNT(*) FROM trip_deletions").fetchone()[0],
            )
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, "Unknown trip"):
            self.actions.delete_trip(victim.trip_id)

    def test_secret_bearing_snapshot_is_rejected(self) -> None:
        trip = self.actions.create_trip(name="", destination="Taipei")
        # Every credential this project configures, plus credential-shaped names.
        for secret in (
            "OPENAI_API_KEY",
            "OPENROUTESERVICE_API_KEY",
            "GOOGLE_MAPS_SERVER_KEY",
            "GOOGLE_MAPS_BROWSER_KEY",
            "access_token",
            "client_secret",
            "session_token",
            "some_credential",
        ):
            with self.assertRaisesRegex(ValueError, "not allowed"):
                self.actions.save_plan_version(
                    trip_id=trip.trip_id,
                    snapshot={secret: "must-not-persist"},
                    cause="invalid_test",
                )
        # Legitimate fields that merely end in _key must still be allowed.
        allowed = self.actions.save_plan_version(
            trip_id=trip.trip_id,
            snapshot={"generated_key": "entry_requirements:shared", "name_key": "sky view"},
            cause="valid_test",
        )
        self.assertEqual(
            "entry_requirements:shared", allowed.snapshot.as_dict()["generated_key"]
        )
        self.assertEqual(1, len(self.actions.list_plan_versions(trip.trip_id)))

    def test_streamlit_entry_point_renders(self) -> None:
        with patch.dict(os.environ, {"TOURIST_DB_PATH": str(self.database_path)}):
            app = AppTest.from_file(ROOT / "app.py", default_timeout=10).run()
            self.assertFalse(app.exception)
            self.assertEqual("Personal Travel Planner", app.title[0].value)

            # Nothing is pre-selected, so an untouched form is the empty
            # destination the error exists for.
            app.button(key="create_trip").click().run()
            self.assertEqual("Destination is required.", app.error[0].value)

            app.text_input(key="trip_name").input("Taipei New Year")
            # Widget keys carry the language so a switch cannot leave a stale
            # label behind; see `shared.translated_selectbox`.
            app.selectbox(key="country__en").select("Taiwan")
            # The city list is built from the chosen country, so it needs the rerun.
            app.run()
            app.selectbox(key="city__en").select("Taipei")
            app.selectbox(key="planning_mode__en").select("ready_to_schedule")
            app.button(key="create_trip").click().run()
            self.assertFalse(app.exception)
            self.assertEqual("Trip saved.", app.success[0].value)
            selected_id = app.sidebar.selectbox(key="selected_trip_id").value
            self.assertEqual(
                "Taipei, Taiwan", self.actions.get_trip(selected_id).destination
            )

            app.radio[0].set_value("th").run()
            self.assertFalse(app.exception)
            self.assertEqual("ตัวช่วยวางแผนท่องเที่ยวส่วนตัว", app.title[0].value)
            # The Thai widget carries over the country chosen in English, so a
            # language switch changes the wording and nothing else.
            self.assertEqual("Taiwan", app.selectbox(key="country__th").value)
            self.assertEqual("Taipei", app.selectbox(key="city__th").value)

        saved = self.actions.list_trips()
        self.assertEqual(1, len(saved))
        self.assertEqual("Taipei, Taiwan", saved[0].destination)

    def test_trip_slots_create_switch_and_keep_drafts_independent(self) -> None:
        taiwan = self.actions.create_trip(
            name="Taiwan draft", destination="Taipei, Taiwan"
        )
        self.actions.save_setup(
            trip_id=taiwan.trip_id,
            main_style=["culture"],
            owner_description="Taiwan night markets",
            confirmed=True,
        )

        with patch.dict(os.environ, {"TOURIST_DB_PATH": str(self.database_path)}):
            app = AppTest.from_file(ROOT / "app.py", default_timeout=10)
            app.switch_page("views/setup.py")
            app.run()
            self.assertEqual(
                "Active trip slot",
                app.sidebar.selectbox(key="selected_trip_id").label,
            )

            app.sidebar.button(key="new_trip_slot").click().run()
            self.assertFalse(app.exception)
            app.text_input(key="trip_name").input("Kyoto ideas")
            app.selectbox(key="country__en").select("Japan")
            app.run()
            app.selectbox(key="city__en").select("Kyoto")
            app.button(key="create_trip").click().run()

            kyoto_id = app.sidebar.selectbox(key="selected_trip_id").value
            self.assertNotEqual(taiwan.trip_id, kyoto_id)
            self.assertEqual("Kyoto, Japan", self.actions.get_trip(kyoto_id).destination)
            self.actions.save_setup(
                trip_id=kyoto_id,
                main_style=["nature"],
                owner_description="Kyoto gardens",
            )

            # A confirmed Taiwan draft resumes at Places; the newer unfinished
            # Kyoto draft resumes at Setup. Neither switch needs a nav click.
            app.sidebar.selectbox(key="selected_trip_id").select(taiwan.trip_id).run()
            self.assertFalse(app.exception)
            self.assertIn(
                "Broad attraction discovery", [item.value for item in app.subheader]
            )
            app.sidebar.selectbox(key="selected_trip_id").select(kyoto_id).run()
            self.assertFalse(app.exception)
            self.assertIn(
                "Destination: Kyoto, Japan", [item.value for item in app.caption]
            )

            self.assertEqual(
                "Taiwan night markets",
                self.actions.get_setup(taiwan.trip_id).snapshot.as_dict()["owner"][
                    "description"
                ],
            )
            self.assertEqual(
                "Kyoto gardens",
                self.actions.get_setup(kyoto_id).snapshot.as_dict()["owner"][
                    "description"
                ],
            )

            delete_key = f"delete_trip_{kyoto_id}"
            self.assertTrue(app.button(key=delete_key).disabled)
            app.text_input(key=f"delete_trip_confirm_{kyoto_id}").input(
                "Kyoto ideas"
            ).run()
            self.assertFalse(app.button(key=delete_key).disabled)
            app.button(key=delete_key).click().run()
            self.assertFalse(app.exception)
            self.assertEqual(
                taiwan.trip_id,
                app.sidebar.selectbox(key="selected_trip_id").value,
            )
            self.assertIn(
                "Broad attraction discovery", [item.value for item in app.subheader]
            )

        self.assertEqual(
            "Taiwan night markets",
            self.actions.get_setup(taiwan.trip_id).snapshot.as_dict()["owner"][
                "description"
            ],
        )
        self.assertIsNone(self.actions.get_trip(kyoto_id))
        self.assertIsNone(self.actions.get_setup(kyoto_id))

    def test_deleting_the_last_trip_returns_to_first_trip_setup(self) -> None:
        trip = self.actions.create_trip(name="Only trip", destination="Taipei")
        with patch.dict(os.environ, {"TOURIST_DB_PATH": str(self.database_path)}):
            app = AppTest.from_file(ROOT / "app.py", default_timeout=10).run()
            app.text_input(key=f"delete_trip_confirm_{trip.trip_id}").input(
                trip.name
            ).run()
            app.button(key=f"delete_trip_{trip.trip_id}").click().run()

            self.assertFalse(app.exception)
            self.assertEqual([], list(app.sidebar.selectbox))
            self.assertEqual("Personal Travel Planner", app.title[0].value)
            self.assertIsNotNone(app.button(key="create_trip"))
        self.assertEqual([], self.actions.list_trips())

    def test_every_interface_string_exists_in_both_languages(self) -> None:
        """A missing `th` key is a KeyError in front of a Thai owner, not a typo."""

        from ui.text import TEXT

        self.assertEqual(set(TEXT["en"]), set(TEXT["th"]))


class LocalCredentialsTest(unittest.TestCase):
    """Keys may live in a gitignored file, but the environment still wins."""

    def _load(self, payload, environ):
        from travel_planner.credentials import load_local_credentials

        with TemporaryDirectory() as directory:
            path = Path(directory) / "secrets.local.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.dict(os.environ, environ, clear=True):
                names = load_local_credentials(path)
                return names, dict(os.environ)

    def test_file_values_reach_the_environment(self) -> None:
        names, environ = self._load({"OPENROUTESERVICE_API_KEY": "ors-value"}, {})
        self.assertEqual(["OPENROUTESERVICE_API_KEY"], names)
        self.assertEqual("ors-value", environ["OPENROUTESERVICE_API_KEY"])

    def test_an_exported_variable_is_never_overwritten(self) -> None:
        # Otherwise a stale file would silently beat the key the owner just set.
        names, environ = self._load(
            {"GOOGLE_MAPS_SERVER_KEY": "from-file"},
            {"GOOGLE_MAPS_SERVER_KEY": "from-export"},
        )
        self.assertEqual([], names)
        self.assertEqual("from-export", environ["GOOGLE_MAPS_SERVER_KEY"])

    def test_placeholders_and_non_strings_are_not_configuration(self) -> None:
        names, environ = self._load(
            {"A": "", "B": "  ", "C": "replace_me", "D": 7, "E": {"nested": "x"}}, {}
        )
        self.assertEqual([], names)
        for key in "ABCDE":
            self.assertNotIn(key, environ)

    def test_the_suite_switch_disables_loading_entirely(self) -> None:
        # This is what keeps real keys out of every test; see tests/__init__.py.
        names, environ = self._load(
            {"GOOGLE_MAPS_SERVER_KEY": "from-file"},
            {"TOURIST_LOCAL_SECRETS": "off"},
        )
        self.assertEqual([], names)
        self.assertNotIn("GOOGLE_MAPS_SERVER_KEY", environ)

    def test_a_missing_file_is_not_an_error(self) -> None:
        from travel_planner.credentials import load_local_credentials

        # clear=True drops the suite's own "off" switch, so the loader really runs.
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                [], load_local_credentials(Path(directory) / "absent.json")
            )

    def test_malformed_json_names_the_file_and_not_its_contents(self) -> None:
        from travel_planner.credentials import load_local_credentials

        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / "secrets.local.json"
            path.write_text('{"KEY": "abc', encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                load_local_credentials(path)
            self.assertIn("secrets.local.json", str(caught.exception))
            self.assertNotIn("abc", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
