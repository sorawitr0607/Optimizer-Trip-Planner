from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from travel_planner import checklist
from travel_planner.actions import PlannerActions

ROOT = Path(__file__).resolve().parents[1]
TODAY = "2026-11-01"


def setup_payload(**overrides) -> dict:
    payload = {
        "trip_basics": {
            "start_date": "2026-12-29",
            "end_date": "2027-01-04",
            "accommodation_status": "not_booked",
        },
        "owner": {"nationality": "Thailand"},
        "travellers": [
            {"traveller_id": "member_1", "nationality": "Thailand"},
            {"traveller_id": "member_2", "nationality": "Thailand"},
        ],
    }
    payload.update(overrides)
    return payload


class ChecklistGenerationTest(unittest.TestCase):
    def test_board_is_generic_and_asserts_no_legal_conclusion(self) -> None:
        items = checklist.propose_items(destination="Taipei", setup=setup_payload())

        self.assertTrue(items)
        for item in items:
            # Nothing may claim a verified requirement without an official source.
            self.assertEqual("verification_needed", item["evidence_state"])
            self.assertIsNone(item["source_url"])
            self.assertIsNone(item["authority_type"])
            self.assertIsNone(item["last_checked_at"])
            self.assertEqual("to_do", item["progress"])
            self.assertIn(item["timing"], checklist.TIMING_BUCKETS)
            self.assertIn(item["category"], checklist.CATEGORIES)
            self.assertTrue(item["consequence"])
            checklist.validate_item(item)

        titles = " ".join(item["title"] for item in items)
        self.assertIn("Taipei", titles)
        # A generic board must not invent a destination-specific rule.
        for invented in ("Visit Japan Web", "visa-free", "ESTA", "K-ETA"):
            self.assertNotIn(invented, titles)

    def test_unrelated_destination_gets_no_destination_specific_task(self) -> None:
        taipei = checklist.propose_items(destination="Taipei", setup=setup_payload())
        osaka = checklist.propose_items(destination="Osaka", setup=setup_payload())

        self.assertEqual(
            [item["generated_key"] for item in taipei],
            [item["generated_key"] for item in osaka],
        )
        self.assertIn("Osaka", " ".join(item["title"] for item in osaka))
        self.assertNotIn("Taipei", " ".join(item["title"] for item in osaka))

    def test_shared_tasks_deduplicate_but_split_on_differing_nationality(self) -> None:
        shared = checklist.propose_items(destination="Taipei", setup=setup_payload())
        entry_shared = [
            item for item in shared if item["template_id"] == "entry_requirements"
        ]
        self.assertEqual(1, len(entry_shared))
        self.assertEqual(
            ["member_1", "member_2", "owner"], entry_shared[0]["applies_to"]
        )

        mixed = checklist.propose_items(
            destination="Taipei",
            setup=setup_payload(
                travellers=[
                    {"traveller_id": "member_1", "nationality": "Thailand"},
                    {"traveller_id": "member_2", "nationality": "Japan"},
                ]
            ),
        )
        entry_mixed = [
            item for item in mixed if item["template_id"] == "entry_requirements"
        ]
        self.assertEqual(2, len(entry_mixed))
        self.assertEqual(
            {"Japan", "Thailand"}, {item["nationality"] for item in entry_mixed}
        )
        japan = next(item for item in entry_mixed if item["nationality"] == "Japan")
        self.assertEqual(["member_2"], japan["applies_to"])
        # Non-entry tasks stay shared even when nationalities differ.
        self.assertEqual(
            1, len([item for item in mixed if item["template_id"] == "money"])
        )

    def test_milestones_resolve_against_the_trip_start(self) -> None:
        items = {
            item["template_id"]: item
            for item in checklist.propose_items(
                destination="Taipei", setup=setup_payload()
            )
        }
        self.assertIsNone(items["entry_requirements"]["due_date"])
        self.assertEqual("2026-11-29", items["insurance_health"]["due_date"])
        self.assertEqual("2026-12-22", items["money"]["due_date"])
        self.assertEqual("2026-12-28", items["emergency"]["due_date"])
        self.assertEqual("2026-12-29", items["departure_recheck"]["due_date"])

        undated = checklist.propose_items(
            destination="Taipei",
            setup=setup_payload(trip_basics={"accommodation_status": "booked"}),
        )
        self.assertEqual({None}, {item["due_date"] for item in undated})

    def test_booked_accommodation_drops_its_task(self) -> None:
        unbooked = checklist.propose_items(destination="Taipei", setup=setup_payload())
        booked = checklist.propose_items(
            destination="Taipei",
            setup=setup_payload(
                trip_basics={"start_date": "2026-12-29", "accommodation_status": "booked"}
            ),
        )
        self.assertIn(
            "accommodation_base", [item["template_id"] for item in unbooked]
        )
        self.assertNotIn("accommodation_base", [item["template_id"] for item in booked])

    def test_selected_place_produces_a_booking_task_and_timed_evidence_raises_it(self) -> None:
        choices = [
            {"place_id": "p1", "action": "must_do", "candidate": {"name": "Tower"}},
            {"place_id": "p2", "action": "maybe", "candidate": {"name": "Park"}},
        ]
        plain = checklist.propose_items(
            destination="Taipei", setup=setup_payload(), choices=choices
        )
        tower = next(item for item in plain if item["related_component"] == "p1")
        self.assertEqual("recommended", tower["requirement_level"])
        self.assertIn("Tower", tower["title"])
        # An unselected place gets no task.
        self.assertEqual([], [i for i in plain if i["related_component"] == "p2"])

        timed = checklist.propose_items(
            destination="Taipei",
            setup=setup_payload(),
            choices=choices,
            facts=[
                {"subject_id": "p1", "fact_type": "show_intervals", "status": "verified"}
            ],
        )
        raised = next(item for item in timed if item["related_component"] == "p1")
        self.assertEqual("required", raised["requirement_level"])
        self.assertEqual("reservations", raised["category"])
        self.assertEqual("attraction_operator", raised["expected_authority"])


class ChecklistDiffAndReadinessTest(unittest.TestCase):
    def test_preview_reports_additions_removals_and_deadline_changes(self) -> None:
        first = checklist.propose_items(destination="Taipei", setup=setup_payload())
        current = [{**item, "origin": "generated"} for item in first]

        # Booking the hotel removes one task; moving the trip shifts every deadline.
        moved = checklist.propose_items(
            destination="Taipei",
            setup=setup_payload(
                trip_basics={
                    "start_date": "2027-01-15",
                    "end_date": "2027-01-20",
                    "accommodation_status": "booked",
                }
            ),
        )
        preview = checklist.diff_proposal(current, moved)

        self.assertEqual([], preview["additions"])
        self.assertEqual(
            ["accommodation_base:shared"],
            [item["generated_key"] for item in preview["removals"]],
        )
        self.assertTrue(preview["deadline_changes"])
        change = next(
            item
            for item in preview["deadline_changes"]
            if item["generated_key"] == "money:shared"
        )
        self.assertEqual("2026-12-22", change["from"]["due_date"])
        self.assertEqual("2027-01-08", change["to"]["due_date"])

    def test_dismissed_item_is_not_reported_as_a_removal_again(self) -> None:
        proposed = checklist.propose_items(destination="Taipei", setup=setup_payload())
        current = [
            {**item, "origin": "generated", "dismissed": item["template_id"] == "packing"}
            for item in proposed
        ]
        remaining = [item for item in proposed if item["template_id"] != "packing"]

        preview = checklist.diff_proposal(current, remaining)

        self.assertEqual([], preview["removals"])

    def test_readiness_states_and_warnings_never_block(self) -> None:
        base = checklist.propose_items(destination="Taipei", setup=setup_payload())
        unverified = checklist.readiness(base, today=TODAY)
        self.assertEqual(checklist.VERIFICATION_NEEDED, unverified["state"])
        self.assertFalse(unverified["blocks_itinerary"])
        self.assertGreater(unverified["counts"]["unverified_required"], 0)

        # Verify every required item: an incomplete required item is now the issue.
        verified = [
            {
                **item,
                "evidence_state": "verified",
                "source_url": "https://example.gov/entry",
                "authority_type": "government",
            }
            if item["requirement_level"] == "required"
            else item
            for item in base
        ]
        self.assertEqual(
            checklist.ACTION_NEEDED, checklist.readiness(verified, today=TODAY)["state"]
        )

        done = [
            {**item, "progress": "done"}
            if item["requirement_level"] == "required"
            else item
            for item in verified
        ]
        summary = checklist.readiness(done, today=TODAY)
        self.assertEqual(checklist.READY, summary["state"])
        self.assertEqual(0, summary["counts"]["required_open"])

    def test_overdue_and_due_soon_are_surfaced(self) -> None:
        items = checklist.propose_items(destination="Taipei", setup=setup_payload())
        summary = checklist.readiness(items, today="2026-12-23")

        overdue_keys = {item["generated_key"] for item in summary["overdue"]}
        self.assertIn("insurance_health:shared", overdue_keys)
        self.assertIn("money:shared", overdue_keys)
        self.assertGreaterEqual(summary["counts"]["overdue"], 2)
        self.assertNotIn(
            "departure_recheck:shared",
            overdue_keys,
        )

    def test_verified_item_needing_a_refresh_point_is_flagged(self) -> None:
        item = {
            "evidence_state": "verified",
            "last_checked_at": "2026-11-01T00:00:00+00:00",
            "dismissed": False,
        }
        # The 30-day point (2026-11-29) falls between the check and today.
        self.assertTrue(
            checklist.needs_recheck(item, today="2026-12-05", start_date="2026-12-29")
        )
        self.assertFalse(
            checklist.needs_recheck(item, today="2026-11-10", start_date="2026-12-29")
        )
        self.assertFalse(
            checklist.needs_recheck(
                {**item, "evidence_state": "verification_needed"},
                today="2026-12-05",
                start_date="2026-12-29",
            )
        )

    def test_contract_violations_are_rejected(self) -> None:
        good = checklist.propose_items(destination="Taipei", setup=setup_payload())[0]

        with self.assertRaisesRegex(ValueError, "needs a title"):
            checklist.validate_item({**good, "title": "  "})
        with self.assertRaisesRegex(ValueError, "Unsupported checklist category"):
            checklist.validate_item({**good, "category": "vibes"})
        with self.assertRaisesRegex(ValueError, "Unsupported authority type"):
            checklist.validate_item({**good, "authority_type": "a_travel_blog"})
        with self.assertRaisesRegex(ValueError, "needs a short reason"):
            checklist.validate_item({**good, "progress": "not_applicable", "note": ""})
        with self.assertRaisesRegex(ValueError, "official source URL"):
            checklist.validate_item({**good, "evidence_state": "verified"})
        with self.assertRaisesRegex(ValueError, "responsible authority"):
            checklist.validate_item(
                {
                    **good,
                    "requirement_level": "required",
                    "evidence_state": "verified",
                    "source_url": "https://example.gov/entry",
                    "authority_type": None,
                }
            )


class ChecklistPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "checklist.sqlite3"
        self.actions = PlannerActions(self.path)
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="ready_to_schedule"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            owner_nationality="Thailand",
            travellers=[{"label": "Teen", "age": 19, "nationality": "Thailand"}],
            start_date="2026-12-29",
            end_date="2027-01-04",
            accommodation_status="not_booked",
            confirmed=True,
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_apply_is_idempotent_and_survives_a_reopen(self) -> None:
        preview = self.actions.propose_checklist(self.trip.trip_id)
        self.assertTrue(preview["additions"])
        self.assertEqual([], preview["removals"])

        first = self.actions.apply_checklist_proposal(self.trip.trip_id)
        again = self.actions.apply_checklist_proposal(self.trip.trip_id)

        self.assertEqual(len(preview["additions"]), first["added"])
        self.assertEqual({"added": 0, "deadlines_changed": 0, "dismissed": 0}, again)

        resumed = PlannerActions(self.path).list_checklist_items(self.trip.trip_id)
        self.assertEqual(first["added"], len(resumed))
        self.assertEqual({"generated"}, {item["origin"] for item in resumed})

    def test_owner_edits_progress_evidence_and_dismissal_with_history(self) -> None:
        self.actions.apply_checklist_proposal(self.trip.trip_id)
        items = self.actions.list_checklist_items(self.trip.trip_id)
        target = next(item for item in items if item["template_id"] == "money")

        waiting = self.actions.set_checklist_progress(
            trip_id=self.trip.trip_id, item_id=target["item_id"], progress="waiting"
        )
        self.assertEqual("waiting", waiting["progress"])

        entry = next(item for item in items if item["template_id"] == "entry_requirements")
        verified = self.actions.record_checklist_evidence(
            trip_id=self.trip.trip_id,
            item_id=entry["item_id"],
            source_url="https://example.gov/entry",
            authority_type="immigration",
            checked_at="2026-11-01T00:00:00+00:00",
        )
        self.assertEqual("verified", verified["evidence_state"])
        self.assertEqual("immigration", verified["authority_type"])

        dismissed = self.actions.set_checklist_dismissed(
            trip_id=self.trip.trip_id, item_id=target["item_id"], dismissed=True
        )
        self.assertTrue(dismissed["dismissed"])
        # A dismissed generated requirement stays visible in history.
        keys = [item["item_id"] for item in self.actions.list_checklist_items(self.trip.trip_id)]
        self.assertIn(target["item_id"], keys)

        restored = self.actions.set_checklist_dismissed(
            trip_id=self.trip.trip_id, item_id=target["item_id"], dismissed=False
        )
        self.assertFalse(restored["dismissed"])

    def test_not_applicable_needs_a_reason_and_manual_items_persist(self) -> None:
        self.actions.apply_checklist_proposal(self.trip.trip_id)
        items = self.actions.list_checklist_items(self.trip.trip_id)
        target = items[0]

        with self.assertRaisesRegex(ValueError, "needs a short reason"):
            self.actions.set_checklist_progress(
                trip_id=self.trip.trip_id,
                item_id=target["item_id"],
                progress="not_applicable",
            )
        skipped = self.actions.set_checklist_progress(
            trip_id=self.trip.trip_id,
            item_id=target["item_id"],
            progress="not_applicable",
            note="Already held",
        )
        self.assertEqual("not_applicable", skipped["progress"])

        manual = self.actions.save_checklist_item(
            trip_id=self.trip.trip_id,
            item={
                "title": "Buy a power adapter",
                "category": "packing",
                "requirement_level": "optional",
                "timing": "7_days_before",
                "consequence": "Cannot charge devices",
            },
        )
        self.assertEqual("manual", manual["origin"])
        self.assertEqual("2026-12-22", manual["due_date"])
        self.assertIn(
            manual["item_id"],
            [item["item_id"] for item in self.actions.list_checklist_items(self.trip.trip_id)],
        )

    def test_readiness_reflects_saved_state(self) -> None:
        self.actions.apply_checklist_proposal(self.trip.trip_id)
        summary = self.actions.checklist_readiness(self.trip.trip_id, today=TODAY)
        self.assertEqual(checklist.VERIFICATION_NEEDED, summary["state"])
        self.assertFalse(summary["blocks_itinerary"])

        for item in self.actions.list_checklist_items(self.trip.trip_id):
            if item["requirement_level"] == "required":
                self.actions.record_checklist_evidence(
                    trip_id=self.trip.trip_id,
                    item_id=item["item_id"],
                    source_url="https://example.gov/rule",
                    authority_type="government",
                    checked_at=f"{TODAY}T00:00:00+00:00",
                )
                self.actions.set_checklist_progress(
                    trip_id=self.trip.trip_id, item_id=item["item_id"], progress="done"
                )
        self.assertEqual(
            checklist.READY,
            self.actions.checklist_readiness(self.trip.trip_id, today=TODAY)["state"],
        )

    def test_items_are_hash_verified_on_read(self) -> None:
        self.actions.apply_checklist_proposal(self.trip.trip_id)
        connection = sqlite3.connect(self.path)
        try:
            connection.execute(
                "UPDATE checklist_items SET snapshot_json = ?"
                " WHERE id = (SELECT id FROM checklist_items LIMIT 1)",
                ('{"title":"tampered"}',),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(RuntimeError, "Checklist item"):
            self.actions.list_checklist_items(self.trip.trip_id)


class ChecklistViewTest(unittest.TestCase):
    def test_board_renders_previews_and_applies_in_both_languages(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "board.sqlite3"
            actions = PlannerActions(path)
            trip = actions.create_trip(
                name="Taipei", destination="Taipei", planning_mode="ready_to_schedule"
            )
            actions.save_setup(
                trip_id=trip.trip_id,
                main_style=["sightseeing"],
                owner_nationality="Thailand",
                start_date="2026-12-29",
                end_date="2027-01-04",
                accommodation_status="not_booked",
                confirmed=True,
            )

            with patch.dict(os.environ, {"TOURIST_DB_PATH": str(path)}):
                app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
                self.assertFalse(app.exception)
                self.assertIn("Trip readiness checklist", [i.value for i in app.subheader])
                text = _text(app)
                # Additions are previewed, not applied silently.
                self.assertIn("➕ Verify entry requirements for Taipei", text)
                self.assertIn("➕ Confirm accommodation and record its address", text)
                self.assertEqual([], actions.list_checklist_items(trip.trip_id))

                app.button(key=f"apply_checklist_{trip.trip_id}").click().run()
                self.assertFalse(app.exception)
                applied = _text(app)
                self.assertIn("Do now / before booking", applied)
                self.assertIn("Verification needed", applied)
                self.assertIn("The board matches the current trip.", applied)

                app.radio[0].set_value("th").run()
                self.assertFalse(app.exception)
                self.assertIn("รายการเตรียมตัวก่อนเดินทาง", [i.value for i in app.subheader])
                self.assertIn("ทำทันที / ก่อนจอง", _text(app))

            saved = actions.list_checklist_items(trip.trip_id)
            self.assertTrue(saved)
            self.assertEqual(
                {"verification_needed"}, {item["evidence_state"] for item in saved}
            )

    def test_trip_without_setup_explains_the_board_is_unavailable(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "nosetup.sqlite3"
            PlannerActions(path).create_trip(name="Blank", destination="Osaka")

            with patch.dict(os.environ, {"TOURIST_DB_PATH": str(path)}):
                app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()

            self.assertFalse(app.exception)
            self.assertIn("Save the trip setup first", _text(app))


def _text(app: AppTest) -> str:
    groups = (app.markdown, app.caption, app.info, app.warning, app.success)
    return "\n".join(str(item.value) for group in groups for item in group)


if __name__ == "__main__":
    unittest.main()
