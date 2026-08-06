from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


from travel_planner.actions import PlannerActions
from travel_planner.core import freeze_snapshot


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
        with self.assertRaises(ValueError) as raised:
            self.actions.delete_trip(victim.trip_id)
        self.assertEqual("unknown_trip", str(raised.exception))

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

    def test_every_interface_string_exists_in_both_languages(self) -> None:
        """Every bilingual table is key-for-key; categories are derived in English."""

        # Was `ui.text`, a re-export shim that died with the POC. This is the
        # catalogue both renderers actually read.
        from travel_planner.copy import (
            ACCOMMODATION_TEXT,
            CATEGORY_TEXT,
            DIMENSION_TEXT,
            EXPLANATION_TEXT,
            OPTIMIZER_CODE_TEXT,
            REJECTION_TEXT,
            TAG_TEXT,
            TEXT,
        )

        for table in (
            TEXT,
            TAG_TEXT,
            EXPLANATION_TEXT,
            REJECTION_TEXT,
            DIMENSION_TEXT,
            ACCOMMODATION_TEXT,
            OPTIMIZER_CODE_TEXT,
        ):
            self.assertEqual(set(table["en"]), set(table["th"]))
        for category in CATEGORY_TEXT["th"]:
            rendered = CATEGORY_TEXT["en"].get(
                category, category.replace("_", " ").title()
            )
            self.assertNotIn(" Of ", rendered)

        # A refusal code must have Thai prose to render, which is the half of
        # `ui.shared.plain` worth keeping. Rendering it is no longer this test's
        # business: below Streamlit that is `exporters._code`, asserted with its
        # `⚠` fallback in `test_exports.py`, and on screen it is `copyFrom`.
        # The other half — escaping `$` so Streamlit's markdown stopped reading
        # money as LaTeX — has nothing left to protect against.
        self.assertTrue(OPTIMIZER_CODE_TEXT["th"]["setup_not_confirmed"])
        self.assertEqual(
            set(OPTIMIZER_CODE_TEXT["en"]), set(OPTIMIZER_CODE_TEXT["th"])
        )

    def test_every_refusal_code_raised_has_text_in_both_languages(self) -> None:
        """Key parity cannot catch a code missing from **both** tables.

        `unknown_split_row` and `unknown_traveller` were raised by the split ledger
        from S2 and had no entry in `en` or `th`, so every owner saw
        `⚠ unknown_split_row`. The parity test above passed the whole time, because
        both languages lacked the key equally — parity is symmetry, not coverage.

        This asserts coverage: every code the core actually raises must be sayable.
        """

        import ast

        from travel_planner.copy import OPTIMIZER_CODE_TEXT

        raised: set[str] = set()
        core = Path(__file__).resolve().parents[1] / "travel_planner"
        for path in sorted(core.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "PlannerRefusal"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    raised.add(str(node.args[0].value))

        self.assertGreater(len(raised), 20, "the AST scan must actually find the raises")
        for language in ("en", "th"):
            missing = sorted(code for code in raised if code not in OPTIMIZER_CODE_TEXT[language])
            self.assertEqual([], missing, f"refusal codes with no {language} text: {missing}")

    def test_copy_never_uses_a_pictograph_as_the_only_meaning(self) -> None:
        from travel_planner.copy import TABLE_NAMES, _CATALOGUE
        from travel_planner.exporters import PICTOGRAPHS

        for name in TABLE_NAMES:
            for words in _CATALOGUE[name].values():
                for value in words.values():
                    self.assertTrue(PICTOGRAPHS.sub("", value).strip())


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
