from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from travel_planner import revision
from travel_planner.actions import PlannerActions
from travel_planner.optimizer import optimize_trip

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads(
    (ROOT / "tests" / "fixtures" / "historic_regressions.json").read_text(
        encoding="utf-8"
    )
)
FIXTURE_ID = "ix-jp-shibuya-hours-view-walk"


def planner_input() -> dict:
    fixture = next(
        item for item in CATALOG["fixtures"] if item["metadata"]["id"] == FIXTURE_ID
    )
    return json.loads(json.dumps(fixture["planner_input"]))


class OperationContractTest(unittest.TestCase):
    def test_an_unsupported_operation_is_refused(self) -> None:
        for bad in ({}, {"operation": "book_a_flight"}, {"operation": ""}):
            with self.assertRaisesRegex(ValueError, "Unsupported revision operation"):
                revision.validate_operation(bad)

    def test_missing_or_invalid_arguments_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "needs place_id"):
            revision.validate_operation({"operation": "lock_item", "arguments": {}})
        with self.assertRaisesRegex(ValueError, "factor must be"):
            revision.validate_operation(
                {"operation": "reduce_walking", "arguments": {"factor": 1.4}}
            )
        with self.assertRaisesRegex(ValueError, "minutes must be at least"):
            revision.validate_operation(
                {"operation": "adjust_duration",
                 "arguments": {"place_id": "p", "minutes": 5}}
            )
        with self.assertRaisesRegex(ValueError, "must use HH:MM"):
            revision.validate_operation(
                {"operation": "fix_meal_timing",
                 "arguments": {"start": "noon", "end": "13:00"}}
            )
        with self.assertRaisesRegex(ValueError, "start must be before end"):
            revision.validate_operation(
                {"operation": "fix_meal_timing",
                 "arguments": {"start": "14:00", "end": "13:00"}}
            )

    def test_an_operation_only_changes_constraints_never_facts(self) -> None:
        snapshot = planner_input()
        applied = revision.apply_operation(
            snapshot, {"operation": "reduce_walking", "arguments": {"factor": 0.5}}
        )["snapshot"]

        # Facts and routes are untouched: an operation cannot invent evidence.
        self.assertEqual(snapshot["facts"], applied["facts"])
        self.assertEqual(snapshot["routes"], applied["routes"])
        self.assertEqual(snapshot["candidates"], applied["candidates"])
        self.assertNotEqual(snapshot.get("thresholds"), applied["thresholds"])

    def test_the_original_snapshot_is_never_mutated(self) -> None:
        snapshot = planner_input()
        before = json.dumps(snapshot, sort_keys=True)
        revision.apply_operation(
            snapshot, {"operation": "reduce_walking", "arguments": {"factor": 0.5}}
        )
        self.assertEqual(before, json.dumps(snapshot, sort_keys=True))

    def test_reduce_walking_tightens_both_walking_thresholds(self) -> None:
        snapshot = planner_input()
        snapshot["thresholds"] = {
            "walking_minutes_per_leg": 40,
            "plain_walking_minutes_per_day": 100,
        }
        applied = revision.apply_operation(
            snapshot, {"operation": "reduce_walking", "arguments": {"factor": 0.5}}
        )
        self.assertEqual(20, applied["snapshot"]["thresholds"]["walking_minutes_per_leg"])
        self.assertEqual(
            50, applied["snapshot"]["thresholds"]["plain_walking_minutes_per_day"]
        )
        self.assertTrue(applied["assumptions"])

    def test_a_threshold_never_tightens_to_zero(self) -> None:
        snapshot = planner_input()
        snapshot["thresholds"] = {"walking_minutes_per_leg": 6}
        applied = revision.apply_operation(
            snapshot, {"operation": "reduce_walking", "arguments": {"factor": 0.1}}
        )
        self.assertGreaterEqual(
            applied["snapshot"]["thresholds"]["walking_minutes_per_leg"],
            revision.MIN_THRESHOLD_MINUTES,
        )

    def test_lock_and_unlock_round_trip(self) -> None:
        snapshot = planner_input()
        place_id = snapshot["candidates"][0]["id"]
        locked = revision.apply_operation(
            snapshot, {"operation": "lock_item", "arguments": {"place_id": place_id}}
        )["snapshot"]
        self.assertEqual(
            [place_id], [lock["subject_id"] for lock in locked["locks"]]
        )
        unlocked = revision.apply_operation(
            locked, {"operation": "unlock_item", "arguments": {"place_id": place_id}}
        )["snapshot"]
        self.assertEqual([], unlocked["locks"])
        with self.assertRaisesRegex(ValueError, "is not locked"):
            revision.apply_operation(
                unlocked,
                {"operation": "unlock_item", "arguments": {"place_id": place_id}},
            )

    def test_an_unknown_place_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a selected place"):
            revision.apply_operation(
                planner_input(),
                {"operation": "lock_item", "arguments": {"place_id": "nowhere"}},
            )

    def test_dropping_the_last_place_is_refused(self) -> None:
        snapshot = planner_input()
        snapshot["candidates"] = snapshot["candidates"][:1]
        with self.assertRaisesRegex(ValueError, "leave no selected place"):
            revision.apply_operation(
                snapshot,
                {
                    "operation": "drop_place",
                    "arguments": {"place_id": snapshot["candidates"][0]["id"]},
                },
            )

    def test_dropping_a_place_also_drops_its_lock(self) -> None:
        snapshot = planner_input()
        place_id = snapshot["candidates"][0]["id"]
        snapshot["locks"] = [{"subject_id": place_id}]
        applied = revision.apply_operation(
            snapshot, {"operation": "drop_place", "arguments": {"place_id": place_id}}
        )["snapshot"]
        self.assertEqual([], applied["locks"])
        self.assertNotIn(
            place_id, [item["id"] for item in applied["candidates"]]
        )


class ConsequenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = planner_input()
        self.before = optimize_trip(self.snapshot)["variants"][0]

    def test_an_unchanged_plan_reports_no_differences(self) -> None:
        change = revision.consequences(self.before, self.before)
        self.assertEqual([], change["added"])
        self.assertEqual([], change["removed"])
        self.assertEqual([], change["moved"])
        self.assertEqual([], change["changed_dates"])
        self.assertEqual(0, change["metrics"]["walking_minutes"]["delta"])
        self.assertEqual([], change["displaced"])

    def test_a_shorter_visit_is_reported_with_its_delta(self) -> None:
        place_id = [
            item["subject_id"]
            for day in self.before["days"]
            for item in day["items"]
            if item["type"] == "visit"
        ][0]
        applied = revision.apply_operation(
            self.snapshot,
            {"operation": "adjust_duration",
             "arguments": {"place_id": place_id, "minutes": 30}},
        )
        after = optimize_trip(applied["snapshot"])["variants"][0]
        change = revision.consequences(self.before, after)

        shortened = {item["place_id"] for item in change["shortened"]}
        self.assertIn(place_id, shortened)
        self.assertLess(change["metrics"]["visit_minutes"]["delta"], 0)
        self.assertTrue(change["changed_dates"])

    def test_tightening_walking_displaces_a_selection_and_names_the_reason(self) -> None:
        applied = revision.apply_operation(
            self.snapshot,
            {"operation": "reduce_walking", "arguments": {"factor": 0.2}},
        )
        after = optimize_trip(applied["snapshot"])["variants"][0]
        change = revision.consequences(self.before, after)

        self.assertTrue(change["removed"] or change["displaced"])
        if change["displaced"]:
            self.assertTrue(change["displaced"][0]["reason"])
        self.assertLessEqual(
            change["metrics"]["walking_minutes"]["after"],
            change["metrics"]["walking_minutes"]["before"],
        )

    def test_apply_is_closed_unless_the_proposal_is_ready_and_valid(self) -> None:
        ready = revision.consequences(
            self.before, {**self.before, "status": "ready"}
        )
        self.assertTrue(ready["can_apply"])
        for blocked in ({"status": "provisional"}, {"status": "unavailable"},
                        {"validation": {"valid": False}}):
            change = revision.consequences(self.before, {**self.before, **blocked})
            self.assertFalse(change["can_apply"], blocked)


class RevisionFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "revision.sqlite3"
        self.actions = PlannerActions(self.path)
        self.trip = self.actions.create_trip(name="Tokyo", destination="Tokyo")
        self.snapshot = planner_input()
        proposal = optimize_trip(self.snapshot)
        self.version = self.actions.save_plan_version(
            trip_id=self.trip.trip_id,
            snapshot={
                "schema_version": 1,
                "optimizer_version": proposal["optimizer_version"],
                "input_sha256": proposal["input_sha256"],
                "optimizer_input": self.snapshot,
                "variant": proposal["variants"][0],
            },
            cause="optimizer:best_balance",
        )
        self.place_id = self.snapshot["candidates"][0]["id"]

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_quick_actions_are_offered_without_any_model(self) -> None:
        offered = self.actions.quick_actions(self.trip.trip_id)
        names = {item["operation"] for item in offered}

        self.assertIn("explain", names)
        self.assertIn("fully_reoptimize", names)
        self.assertIn("lock_item", names)
        for item in offered:
            revision.validate_operation(item)

    def test_a_preview_leaves_the_active_plan_untouched(self) -> None:
        draft = self.actions.propose_revision(
            trip_id=self.trip.trip_id,
            operation={"operation": "lock_item", "arguments": {"place_id": self.place_id}},
        )

        self.assertEqual("lock_item", draft["operation"])
        self.assertIsNotNone(draft["consequences"])
        self.assertEqual(
            self.version.version_id, self.actions.get_active_plan(self.trip.trip_id).version_id
        )
        self.assertEqual([], self.actions.list_revisions(self.trip.trip_id))

    def test_applying_creates_a_new_version_and_a_history_record(self) -> None:
        self.actions.propose_revision(
            trip_id=self.trip.trip_id,
            operation={"operation": "lock_item", "arguments": {"place_id": self.place_id}},
        )
        applied = self.actions.apply_revision(self.trip.trip_id)

        self.assertNotEqual(self.version.version_id, applied.version_id)
        self.assertEqual(applied, self.actions.get_active_plan(self.trip.trip_id))
        self.assertEqual(f"revision:lock_item", applied.snapshot and "revision:lock_item")
        history = self.actions.list_revisions(self.trip.trip_id)
        self.assertEqual(1, len(history))
        self.assertEqual(self.version.version_id, history[0]["from_version_id"])
        self.assertEqual(applied.version_id, history[0]["to_version_id"])
        self.assertEqual("quick_action", history[0]["interpreted_by"])
        # The pending draft is consumed.
        self.assertIsNone(self.actions.get_revision_draft(self.trip.trip_id))

    def test_undo_restores_an_earlier_plan_without_deleting_history(self) -> None:
        self.actions.propose_revision(
            trip_id=self.trip.trip_id,
            operation={"operation": "lock_item", "arguments": {"place_id": self.place_id}},
        )
        applied = self.actions.apply_revision(self.trip.trip_id)
        restored = self.actions.restore_plan_version(
            trip_id=self.trip.trip_id, version_id=self.version.version_id
        )

        self.assertEqual(3, len(self.actions.list_plan_versions(self.trip.trip_id)))
        self.assertEqual(restored, self.actions.get_active_plan(self.trip.trip_id))
        self.assertEqual(
            self.version.snapshot.as_dict()["variant"],
            restored.snapshot.as_dict()["variant"],
        )
        # History survives the undo.
        self.assertEqual(1, len(self.actions.list_revisions(self.trip.trip_id)))
        self.assertEqual(applied.version_id, self.actions.list_revisions(self.trip.trip_id)[0]["to_version_id"])

    def test_only_one_pending_preview_and_an_unrelated_one_needs_confirmation(self) -> None:
        self.actions.propose_revision(
            trip_id=self.trip.trip_id,
            operation={"operation": "lock_item", "arguments": {"place_id": self.place_id}},
        )
        with self.assertRaises(ValueError) as raised:
            self.actions.propose_revision(
                trip_id=self.trip.trip_id,
                operation={"operation": "reduce_walking", "arguments": {"factor": 0.7}},
            )
        self.assertEqual("revision_already_pending", str(raised.exception))
        replaced = self.actions.propose_revision(
            trip_id=self.trip.trip_id,
            operation={"operation": "reduce_walking", "arguments": {"factor": 0.7}},
            replace_pending=True,
        )
        self.assertEqual("reduce_walking", replaced["operation"])
        # A related follow-up updates the same pending preview.
        follow_up = self.actions.propose_revision(
            trip_id=self.trip.trip_id,
            operation={"operation": "reduce_walking", "arguments": {"factor": 0.5}},
        )
        self.assertEqual(0.5, follow_up["arguments"]["factor"])

    def test_explain_changes_nothing_and_needs_no_proposal(self) -> None:
        draft = self.actions.propose_revision(
            trip_id=self.trip.trip_id, operation={"operation": "explain", "arguments": {}}
        )

        self.assertIsNone(draft["proposal"])
        self.assertFalse(draft["can_apply"])
        self.assertEqual("best_balance", draft["explanation"]["variant_id"])
        self.assertIn("metrics", draft["explanation"])
        with self.assertRaises(ValueError) as raised:
            self.actions.apply_revision(self.trip.trip_id)
        self.assertEqual("revision_not_applicable", str(raised.exception))
        self.assertEqual(
            self.version.version_id,
            self.actions.get_active_plan(self.trip.trip_id).version_id,
        )

    def test_a_preview_built_on_a_stale_active_plan_is_refused(self) -> None:
        self.actions.propose_revision(
            trip_id=self.trip.trip_id,
            operation={"operation": "lock_item", "arguments": {"place_id": self.place_id}},
        )
        # The active plan moves on behind the pending preview.
        self.actions.restore_plan_version(
            trip_id=self.trip.trip_id, version_id=self.version.version_id
        )
        with self.assertRaises(ValueError) as raised:
            self.actions.apply_revision(self.trip.trip_id)
        self.assertEqual("revision_base_moved", str(raised.exception))

    def test_revising_needs_an_active_plan(self) -> None:
        bare = PlannerActions(Path(self.directory.name) / "bare.sqlite3")
        trip = bare.create_trip(name="Bare", destination="Osaka")
        with self.assertRaises(ValueError) as raised:
            bare.propose_revision(
                trip_id=trip.trip_id, operation={"operation": "explain", "arguments": {}}
            )
        self.assertEqual("no_active_plan", str(raised.exception))

    def test_discarding_leaves_no_pending_preview(self) -> None:
        self.actions.propose_revision(
            trip_id=self.trip.trip_id, operation={"operation": "explain", "arguments": {}}
        )
        self.actions.discard_revision_draft(self.trip.trip_id)
        self.assertIsNone(self.actions.get_revision_draft(self.trip.trip_id))
        with self.assertRaises(ValueError) as raised:
            self.actions.apply_revision(self.trip.trip_id)
        self.assertEqual("no_pending_revision", str(raised.exception))

    def test_revision_history_is_immutable(self) -> None:
        self.actions.propose_revision(
            trip_id=self.trip.trip_id,
            operation={"operation": "lock_item", "arguments": {"place_id": self.place_id}},
        )
        self.actions.apply_revision(self.trip.trip_id)
        connection = sqlite3.connect(self.path)
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute("UPDATE plan_revisions SET snapshot_json = '{}'")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute("DELETE FROM plan_revisions")
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()


class RevisionViewTest(unittest.TestCase):
    def test_the_section_previews_and_applies_in_both_languages(self) -> None:
        import os
        from unittest.mock import patch

        from streamlit.testing.v1 import AppTest

        with TemporaryDirectory() as directory:
            path = Path(directory) / "view.sqlite3"
            actions = PlannerActions(path)
            trip = actions.create_trip(name="Tokyo", destination="Tokyo")
            snapshot = planner_input()
            proposal = optimize_trip(snapshot)
            actions.save_plan_version(
                trip_id=trip.trip_id,
                snapshot={
                    "schema_version": 1,
                    "optimizer_version": proposal["optimizer_version"],
                    "input_sha256": proposal["input_sha256"],
                    "optimizer_input": snapshot,
                    "variant": proposal["variants"][0],
                },
                cause="optimizer:best_balance",
            )

            with patch.dict(os.environ, {"TOURIST_DB_PATH": str(path)}):
                app = AppTest.from_file(ROOT / "app.py", default_timeout=40)
                app.switch_page("views/revise.py")
                app.run()
                self.assertFalse(app.exception)
                self.assertIn("Revise the plan", [item.value for item in app.subheader])

                # Preview a quick action; the active plan must not move.
                before = actions.get_active_plan(trip.trip_id).version_id
                app.button(key=f"run_action_{trip.trip_id}").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(before, actions.get_active_plan(trip.trip_id).version_id)
                self.assertIsNotNone(actions.get_revision_draft(trip.trip_id))
                text = "\n".join(
                    str(item.value)
                    for group in (app.markdown, app.caption, app.info, app.warning)
                    for item in group
                )
                self.assertIn("Pending revision", text)

                app.radio[0].set_value("th").run()
                self.assertFalse(app.exception)
                self.assertIn("แก้ไขแผน", [item.value for item in app.subheader])
