from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image
from streamlit.testing.v1 import AppTest

from travel_planner import exporters
from travel_planner.actions import PlannerActions
from travel_planner.core import new_optimization_preview
from travel_planner.exporters import day_poster_png, plan_pdf, plan_workbook_xlsx
from travel_planner.exports import build_export_snapshot
from travel_planner.optimizer import optimize_trip

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads(
    (ROOT / "tests" / "fixtures" / "historic_regressions.json").read_text(
        encoding="utf-8"
    )
)
FIXTURE_ID = "ix-jp-shibuya-hours-view-walk"
LOCAL_NAMES = {
    "shibuya_sky": {"local": "渋谷スカイ", "en": "Shibuya Sky", "th": "ชิบูยะสกาย"},
}


def planner_input(*, with_names: bool = False, with_coordinates: bool = False) -> dict:
    fixture = next(
        item for item in CATALOG["fixtures"] if item["metadata"]["id"] == FIXTURE_ID
    )
    snapshot = json.loads(json.dumps(fixture["planner_input"]))
    for index, candidate in enumerate(snapshot["candidates"]):
        if with_names and candidate["id"] in LOCAL_NAMES:
            candidate["names"] = LOCAL_NAMES[candidate["id"]]
        if with_coordinates:
            candidate["latitude"] = 35.658 + index / 1000
            candidate["longitude"] = 139.701 + index / 1000
    return snapshot


def plan_payload(snapshot: dict, variant_id: str = "best_balance") -> dict:
    proposal = optimize_trip(snapshot)
    variant = next(
        item for item in proposal["variants"] if item["variant_id"] == variant_id
    )
    return {
        "schema_version": 1,
        "optimizer_version": proposal["optimizer_version"],
        "input_sha256": proposal["input_sha256"],
        "optimizer_input": snapshot,
        "variant": variant,
    }


class ExportSnapshotTest(unittest.TestCase):
    def test_active_plan_exports_reconciled_chronological_items(self) -> None:
        snapshot = planner_input()
        proposal = optimize_trip(snapshot)
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "export.sqlite3")
            trip = actions.create_trip(name="Ready", destination="Tokyo")
            actions.store.save_optimization_preview(
                new_optimization_preview(
                    trip_id=trip.trip_id, optimizer_input=snapshot, proposal=proposal
                )
            )
            with patch.object(actions, "_optimizer_input", return_value=snapshot):
                version = actions.activate_plan_preview(
                    trip_id=trip.trip_id, variant_id="best_balance"
                )

            export = actions.build_export_snapshot(trip.trip_id).as_dict()

        variant = version.snapshot.as_dict()["variant"]
        self.assertEqual(version.version_id, export["stamp"]["plan_version_id"])
        self.assertTrue(export["stamp"]["is_active_plan"])
        self.assertEqual("THB", export["stamp"]["base_currency"])
        self.assertEqual("whole-trip-v1", export["stamp"]["optimizer_version"])

        # Every optimizer item appears exactly once, in chronological order.
        exported = [item for day in export["days"] for item in day["items"]]
        source = [item for day in variant["days"] for item in day["items"]]
        self.assertEqual(len(source), len(exported))
        self.assertEqual(len(exported), len({item["item_id"] for item in exported}))
        for day in export["days"]:
            times = [item["start"] for item in day["items"]]
            self.assertEqual(sorted(times), times)
            self.assertEqual(
                [item["end"] for item in day["items"][:-1]],
                [item["start"] for item in day["items"][1:]],
            )

        # Map stop numbering follows timeline visit order.
        for day in export["days"]:
            visits = [item for item in day["items"] if item["type"] == "visit"]
            self.assertEqual(
                list(range(1, len(visits) + 1)),
                [item["stop_number"] for item in visits],
            )
            self.assertEqual(
                [item["stop_number"] for item in visits],
                [stop["stop_number"] for stop in day["stops"]],
            )

        # Totals reconcile with the optimizer's own metrics.
        for key, value in export["totals"].items():
            self.assertEqual(variant["metrics"][key], value, key)
        self.assertEqual(
            export["totals"]["walking_minutes"],
            export["totals"]["plain_walking_minutes"]
            + export["totals"]["rewarding_walking_minutes"],
        )

    def test_language_changes_display_text_only(self) -> None:
        plan = plan_payload(planner_input(with_names=True))
        common = {
            "trip": {"trip_id": "t1", "name": "Trip", "destination": "Tokyo"},
            "plan": plan,
            "version_id": "plan_1",
            "active_version_id": "plan_1",
            "exported_at": "2030-01-01T00:00:00+00:00",
        }
        english = build_export_snapshot(**common, language="en")
        thai = build_export_snapshot(**common, language="th")

        def visits(export: dict) -> list[dict]:
            return [
                item
                for day in export["days"]
                for item in day["items"]
                if item["type"] == "visit"
            ]

        self.assertIn("Shibuya Sky", [item["display_name"] for item in visits(english)])
        self.assertIn("ชิบูยะสกาย", [item["display_name"] for item in visits(thai)])
        self.assertEqual(
            [(item["subject_id"], item["start"], item["end"]) for item in visits(english)],
            [(item["subject_id"], item["start"], item["end"]) for item in visits(thai)],
        )
        self.assertEqual(english["totals"], thai["totals"])
        for item in visits(thai):
            if item["subject_id"] in LOCAL_NAMES:
                self.assertEqual("渋谷スカイ", item["local_name"])

    def test_totals_that_disagree_with_the_optimizer_are_refused(self) -> None:
        plan = plan_payload(planner_input())
        visit = next(
            item
            for day in plan["variant"]["days"]
            for item in day["items"]
            if item["type"] == "visit"
        )
        visit["duration_minutes"] += 5

        with self.assertRaisesRegex(ValueError, "do not reconcile"):
            build_export_snapshot(
                trip={"trip_id": "t1", "name": "Trip", "destination": "Tokyo"},
                plan=plan,
                version_id="plan_1",
                active_version_id="plan_1",
                language="en",
                exported_at="2030-01-01T00:00:00+00:00",
            )

    def test_unsupported_language_and_non_optimizer_plan_are_rejected(self) -> None:
        plan = plan_payload(planner_input())
        arguments = {
            "trip": {"trip_id": "t1", "name": "Trip", "destination": "Tokyo"},
            "version_id": "plan_1",
            "active_version_id": "plan_1",
            "exported_at": "2030-01-01T00:00:00+00:00",
        }
        with self.assertRaisesRegex(ValueError, "Unsupported language"):
            build_export_snapshot(**arguments, plan=plan, language="ja")
        with self.assertRaisesRegex(ValueError, "optimizer variant"):
            build_export_snapshot(
                **arguments, plan={"variant": "best_balance"}, language="en"
            )

    def test_superseded_version_exports_but_is_not_marked_active(self) -> None:
        plan = plan_payload(planner_input())
        with TemporaryDirectory() as directory:
            actions = PlannerActions(Path(directory) / "history.sqlite3")
            trip = actions.create_trip(name="History", destination="Tokyo")
            first = actions.save_plan_version(
                trip_id=trip.trip_id, snapshot=plan, cause="optimizer:best_balance"
            )
            second = actions.save_plan_version(
                trip_id=trip.trip_id, snapshot=plan, cause="reoptimize"
            )

            old = actions.build_export_snapshot(
                trip.trip_id, version_id=first.version_id
            ).as_dict()
            current = actions.build_export_snapshot(trip.trip_id).as_dict()

            unplanned = actions.create_trip(name="No plan", destination="Osaka")
            with self.assertRaisesRegex(ValueError, "Activate a plan"):
                actions.build_export_snapshot(unplanned.trip_id)

        self.assertFalse(old["stamp"]["is_active_plan"])
        self.assertTrue(current["stamp"]["is_active_plan"])
        self.assertEqual(second.version_id, current["stamp"]["plan_version_id"])
        self.assertEqual(old["totals"], current["totals"])


class ArtifactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.export = build_export_snapshot(
            trip={"trip_id": "t1", "name": "Tokyo day", "destination": "Tokyo"},
            plan=plan_payload(planner_input(with_names=True, with_coordinates=True)),
            version_id="plan_abcdef123456",
            active_version_id="plan_abcdef123456",
            language="th",
            exported_at="2030-01-01T00:00:00+00:00",
        )

    def test_poster_is_a_readable_nine_by_sixteen_png(self) -> None:
        png = day_poster_png(self.export, self.export["days"][0]["date"])
        image = Image.open(BytesIO(png))

        self.assertEqual("PNG", image.format)
        self.assertEqual((1080, 1920), image.size)
        self.assertAlmostEqual(9 / 16, image.size[0] / image.size[1], places=4)
        # Text actually rendered: more than one colour reached the canvas.
        self.assertGreater(len(image.convert("RGB").getcolors(maxcolors=1 << 16)), 1)

        with self.assertRaisesRegex(ValueError, "no day 2999-01-01"):
            day_poster_png(self.export, "2999-01-01")

    def test_pdf_keeps_each_day_and_the_version_stamp(self) -> None:
        pdf = plan_pdf(self.export)

        self.assertTrue(pdf.startswith(b"%PDF-"))
        # Cover + one page per day + unscheduled (if any) + checklist/sources page.
        expected_minimum = 2 + len(self.export["days"])
        self.assertGreaterEqual(pdf.count(b"/Type /Page\n"), expected_minimum)
        self.assertGreater(len(pdf), 20_000)

    def test_workbook_has_the_six_agreed_sheets_and_working_formulas(self) -> None:
        xlsx = plan_workbook_xlsx(self.export)
        archive = zipfile.ZipFile(BytesIO(xlsx))
        names = archive.read("xl/workbook.xml").decode("utf-8")
        summary = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        strings = archive.read("xl/sharedStrings.xml").decode("utf-8")

        for sheet in (
            "Summary",
            "Timeline",
            "Choices &amp; Backups",
            "Checklist",
            "Costs",
            "Sources",
        ):
            self.assertIn(f'name="{sheet}"', names)
        self.assertEqual(
            6, sum(1 for item in archive.namelist() if "worksheets/sheet" in item)
        )
        self.assertTrue(any("chart" in item for item in archive.namelist()))
        self.assertIn("SUMIFS(Timeline!", summary)
        self.assertIn("COUNTIFS(Timeline!", summary)
        self.assertIn(self.export["stamp"]["input_sha256"], strings)
        self.assertIn(self.export["stamp"]["plan_version_id"], strings)
        # Timeline carries one row per exported item plus the header.
        timeline = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        items = sum(len(day["items"]) for day in self.export["days"])
        self.assertEqual(items + 1, timeline.count("<row "))
        self.assertIn("autoFilter", timeline)

    def test_summary_formulas_point_at_the_real_timeline_columns(self) -> None:
        xlsx = plan_workbook_xlsx(self.export)
        archive = zipfile.ZipFile(BytesIO(xlsx))
        summary = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        headers = [name for name, _ in exporters.TIMELINE_COLUMNS]

        duration = chr(ord("A") + headers.index("Duration (min)"))
        walking = chr(ord("A") + headers.index("Walking (min)"))
        kind = chr(ord("A") + headers.index("Type"))
        self.assertIn(f"SUMIFS(Timeline!${duration}$2", summary)
        self.assertIn(f"SUMIFS(Timeline!${walking}$2", summary)
        self.assertIn(f"Timeline!${kind}$2", summary)
        # Cached values match the snapshot, so the file reads correctly unopened.
        for value in (
            self.export["totals"]["walking_minutes"],
            self.export["totals"]["visit_minutes"],
        ):
            self.assertIn(f"<v>{value}</v>", summary)

    def test_workbook_keeps_english_thai_and_local_names_side_by_side(self) -> None:
        archive = zipfile.ZipFile(BytesIO(plan_workbook_xlsx(self.export)))
        strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
        headers = [name for name, _ in exporters.TIMELINE_COLUMNS]

        for column in ("Name (EN)", "Name (TH)", "Local name"):
            self.assertIn(column, headers)
        # The snapshot language is Thai, yet English and local script survive.
        self.assertEqual("th", self.export["stamp"]["language"])
        for name in LOCAL_NAMES["shibuya_sky"].values():
            self.assertIn(name, strings)

    def test_status_wording_survives_when_its_icon_cannot_be_drawn(self) -> None:
        labels = {"state_confirmed": "✅ Confirmed", "state_locked": "🔒 Locked"}
        words = exporters._labels(labels)

        self.assertEqual("Confirmed", words["state_confirmed"])
        self.assertEqual("Locked", words["state_locked"])
        for text in ("ชิบูยะสกาย", "渋谷スカイ", "09:00–10:30 · 90 min"):
            self.assertEqual(text, exporters.PICTOGRAPHS.sub("", text))
        # The document still builds and still names the state.
        self.assertTrue(plan_pdf(self.export, labels).startswith(b"%PDF-"))

    def test_missing_export_font_is_a_precise_error(self) -> None:
        with patch.dict(os.environ, {"TOURIST_EXPORT_FONT": "/nowhere/none.ttf"}):
            with patch.object(exporters, "FONT_CANDIDATES", ()):
                with self.assertRaisesRegex(ValueError, "TOURIST_EXPORT_FONT"):
                    exporters.resolve_font()


class ActivePlanViewTest(unittest.TestCase):
    def test_active_plan_renders_timeline_and_map_in_both_languages(self) -> None:
        plan = plan_payload(planner_input(with_names=True, with_coordinates=True))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "view.sqlite3"
            actions = PlannerActions(path)
            trip = actions.create_trip(name="Tokyo day", destination="Tokyo")
            actions.save_plan_version(
                trip_id=trip.trip_id, snapshot=plan, cause="optimizer:best_balance"
            )

            with patch.dict(os.environ, {"TOURIST_DB_PATH": str(path)}):
                app = AppTest.from_file(ROOT / "app.py", default_timeout=20).run()
                self.assertFalse(app.exception)
                self.assertIn("Active plan", [item.value for item in app.subheader])
                english = _text(app)
                self.assertIn("Shibuya Sky", english)
                self.assertIn("Stop 1", english)
                self.assertIn("✅ Confirmed", english)
                self.assertNotIn("No plan is active yet", english)

                app.radio[0].set_value("th").run()
                self.assertFalse(app.exception)
                self.assertIn("แผนที่ใช้งาน", [item.value for item in app.subheader])
                thai = _text(app)
                self.assertIn("ชิบูยะสกาย", thai)
                self.assertIn("จุดที่ 1", thai)

    def test_trip_without_active_plan_says_so(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "empty.sqlite3"
            actions = PlannerActions(path)
            actions.create_trip(name="No plan", destination="Osaka")

            with patch.dict(os.environ, {"TOURIST_DB_PATH": str(path)}):
                app = AppTest.from_file(ROOT / "app.py", default_timeout=20).run()

            self.assertFalse(app.exception)
            self.assertIn("No plan is active yet", _text(app))


def _text(app: AppTest) -> str:
    return "\n".join(
        str(item.value)
        for group in (app.markdown, app.caption, app.info, app.warning)
        for item in group
    )


if __name__ == "__main__":
    unittest.main()
