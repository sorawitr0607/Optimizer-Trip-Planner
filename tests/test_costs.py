from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from streamlit.testing.v1 import AppTest

from travel_planner import costs
from travel_planner.actions import PlannerActions
from travel_planner.exporters import plan_workbook_xlsx
from travel_planner.optimizer import optimize_trip

ROOT = Path(__file__).resolve().parents[1]


def rates(**overrides) -> dict:
    return costs.new_rate_snapshot(
        rates={"CNY": 5.0, "JPY": 0.24, **overrides.pop("rates", {})},
        as_of=overrides.pop("as_of", "2026-12-01"),
        source=overrides.pop("source", "Bank of Thailand reference rate"),
        buffer_percent=overrides.pop("buffer_percent", 0.0),
    )


class RateSnapshotTest(unittest.TestCase):
    def test_snapshot_needs_a_date_and_a_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "as-of date"):
            costs.new_rate_snapshot(rates={"CNY": 5}, as_of=" ", source="Bank")
        with self.assertRaisesRegex(ValueError, "source"):
            costs.new_rate_snapshot(rates={"CNY": 5}, as_of="2026-12-01", source="")
        with self.assertRaisesRegex(ValueError, "between 0 and 50"):
            costs.new_rate_snapshot(
                rates={}, as_of="2026-12-01", source="Bank", buffer_percent=80
            )
        with self.assertRaisesRegex(ValueError, "must be positive"):
            costs.new_rate_snapshot(rates={"CNY": 0}, as_of="2026-12-01", source="Bank")
        with self.assertRaisesRegex(ValueError, "three-letter ISO"):
            costs.new_rate_snapshot(rates={"yuan": 5}, as_of="2026-12-01", source="Bank")

    def test_baht_is_always_present_at_par(self) -> None:
        snapshot = rates()
        self.assertEqual(1.0, snapshot["rates"]["THB"])
        self.assertEqual("2026-12-01", snapshot["as_of"])


class ConversionTest(unittest.TestCase):
    def test_original_amount_and_currency_survive_conversion(self) -> None:
        items = [
            costs.validate_cost(
                {
                    "label": "Cable car",
                    "category": "activity",
                    "original_amount": 120,
                    "original_currency": "cny",
                    "payment_state": "estimate",
                }
            )
        ]
        resolved = costs.apply_rates(items, rates())[0]

        self.assertEqual(120.0, resolved["original_amount"])
        self.assertEqual("CNY", resolved["original_currency"])
        self.assertEqual(5.0, resolved["applied_rate"])
        self.assertEqual("2026-12-01", resolved["applied_rate_date"])
        self.assertEqual(600.0, resolved["converted_thb"])
        self.assertEqual(600.0, resolved["reported_thb"])
        self.assertFalse(resolved["rate_missing"])

    def test_buffer_applies_to_foreign_currency_only(self) -> None:
        foreign = costs.validate_cost(
            {
                "label": "Tickets",
                "category": "activity",
                "original_amount": 100,
                "original_currency": "CNY",
                "payment_state": "estimate",
            }
        )
        domestic = {**foreign, "original_currency": "THB", "original_amount": 100}
        resolved = costs.apply_rates([foreign, domestic], rates(buffer_percent=10))

        self.assertEqual(550.0, resolved[0]["converted_thb"])
        self.assertEqual(10.0, resolved[0]["applied_buffer_percent"])
        # Baht is already the reporting currency; buffering it would inflate it.
        self.assertEqual(100.0, resolved[1]["converted_thb"])
        self.assertEqual(0.0, resolved[1]["applied_buffer_percent"])

    def test_a_paid_charge_is_locked_against_later_rates(self) -> None:
        paid = costs.validate_cost(
            {
                "label": "Hotel",
                "category": "accommodation",
                "original_amount": 1000,
                "original_currency": "CNY",
                "payment_state": "paid",
                "actual_thb": 4800,
            }
        )
        at_five = costs.apply_rates([paid], rates())[0]
        at_six = costs.apply_rates([paid], rates(rates={"CNY": 6.0}))[0]

        # The conversion moves; what was actually charged does not.
        self.assertEqual(5000.0, at_five["converted_thb"])
        self.assertEqual(6000.0, at_six["converted_thb"])
        self.assertEqual(4800.0, at_five["reported_thb"])
        self.assertEqual(4800.0, at_six["reported_thb"])

    def test_a_missing_rate_stays_a_visible_gap(self) -> None:
        item = costs.validate_cost(
            {
                "label": "Ferry",
                "category": "transport",
                "original_amount": 40,
                "original_currency": "TWD",
                "payment_state": "estimate",
            }
        )
        resolved = costs.apply_rates([item], rates())[0]

        self.assertTrue(resolved["rate_missing"])
        self.assertIsNone(resolved["converted_thb"])
        self.assertIsNone(resolved["reported_thb"])
        summary = costs.totals([resolved])
        self.assertEqual(1, summary["unconvertible_rows"])
        self.assertEqual(["TWD"], summary["missing_rates"])
        self.assertEqual(0.0, summary["total_thb"])

    def test_no_snapshot_converts_nothing_rather_than_guessing(self) -> None:
        item = costs.validate_cost(
            {
                "label": "Bus",
                "category": "transport",
                "original_amount": 30,
                "original_currency": "CNY",
                "payment_state": "estimate",
            }
        )
        resolved = costs.apply_rates([item], None)[0]
        self.assertTrue(resolved["rate_missing"])
        self.assertIsNone(resolved["reported_thb"])

    def test_totals_split_estimated_from_paid(self) -> None:
        rows = [
            costs.validate_cost(
                {
                    "label": "Train",
                    "category": "transport",
                    "original_amount": 200,
                    "original_currency": "THB",
                    "payment_state": "estimate",
                }
            ),
            costs.validate_cost(
                {
                    "label": "Museum",
                    "category": "activity",
                    "original_amount": 100,
                    "original_currency": "CNY",
                    "payment_state": "paid",
                    "actual_thb": 480,
                }
            ),
        ]
        summary = costs.totals(costs.apply_rates(rows, rates()))

        self.assertEqual(200.0, summary["estimated_thb"])
        self.assertEqual(480.0, summary["paid_thb"])
        self.assertEqual(680.0, summary["total_thb"])
        self.assertEqual({"activity": 480.0, "transport": 200.0}, summary["by_category"])

    def test_contract_violations_are_rejected(self) -> None:
        base = {
            "label": "Ticket",
            "category": "activity",
            "original_amount": 10,
            "original_currency": "THB",
            "payment_state": "estimate",
        }
        with self.assertRaisesRegex(ValueError, "needs a label"):
            costs.validate_cost({**base, "label": " "})
        with self.assertRaisesRegex(ValueError, "Unsupported cost category"):
            costs.validate_cost({**base, "category": "souvenirs"})
        with self.assertRaisesRegex(ValueError, "Unsupported payment state"):
            costs.validate_cost({**base, "payment_state": "maybe"})
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            costs.validate_cost({**base, "original_amount": -5})
        with self.assertRaisesRegex(ValueError, "needs its actual THB charge"):
            costs.validate_cost({**base, "payment_state": "paid"})


class CostPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "costs.sqlite3"
        self.actions = PlannerActions(self.path)
        self.trip = self.actions.create_trip(name="Dali", destination="Dali")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_costs_and_rates_survive_a_reopen_and_convert(self) -> None:
        self.actions.save_rate_snapshot(
            trip_id=self.trip.trip_id,
            rates={"CNY": 5.0},
            as_of="2026-12-01",
            source="Bank of Thailand",
            buffer_percent=5,
        )
        self.actions.save_cost_item(
            trip_id=self.trip.trip_id,
            item={
                "label": "Erhai cycling",
                "category": "activity",
                "original_amount": 80,
                "original_currency": "CNY",
                "payment_state": "estimate",
            },
        )
        resumed = PlannerActions(self.path)
        items = resumed.list_cost_items(self.trip.trip_id)

        self.assertEqual(1, len(items))
        self.assertEqual(420.0, items[0]["reported_thb"])
        self.assertEqual(5.0, items[0]["applied_rate"])
        self.assertEqual(
            420.0, resumed.cost_totals(self.trip.trip_id)["estimated_thb"]
        )

    def test_editing_and_removing_a_cost(self) -> None:
        saved = self.actions.save_cost_item(
            trip_id=self.trip.trip_id,
            item={
                "label": "Hotel",
                "category": "accommodation",
                "original_amount": 900,
                "original_currency": "THB",
                "payment_state": "estimate",
            },
        )
        updated = self.actions.save_cost_item(
            trip_id=self.trip.trip_id,
            cost_id=saved["cost_id"],
            item={
                "label": "Hotel",
                "category": "accommodation",
                "original_amount": 900,
                "original_currency": "THB",
                "payment_state": "paid",
                "actual_thb": 875,
            },
        )
        self.assertEqual(saved["cost_id"], updated["cost_id"])
        items = self.actions.list_cost_items(self.trip.trip_id)
        self.assertEqual(1, len(items))
        self.assertEqual(875.0, items[0]["reported_thb"])

        self.actions.delete_cost_item(trip_id=self.trip.trip_id, cost_id=saved["cost_id"])
        self.assertEqual([], self.actions.list_cost_items(self.trip.trip_id))

    def test_rates_and_costs_reach_the_workbook(self) -> None:
        catalog = json.loads(
            (ROOT / "tests" / "fixtures" / "historic_regressions.json").read_text(
                encoding="utf-8"
            )
        )
        planner_input = json.loads(
            json.dumps(
                next(
                    item
                    for item in catalog["fixtures"]
                    if item["metadata"]["id"] == "ix-dali-hotel-whole-trip"
                )["planner_input"]
            )
        )
        proposal = optimize_trip(planner_input)
        self.actions.save_plan_version(
            trip_id=self.trip.trip_id,
            snapshot={
                "schema_version": 1,
                "optimizer_version": proposal["optimizer_version"],
                "input_sha256": proposal["input_sha256"],
                "optimizer_input": planner_input,
                "variant": proposal["variants"][0],
            },
            cause="optimizer:best_balance",
        )
        self.actions.save_rate_snapshot(
            trip_id=self.trip.trip_id,
            rates={"CNY": 5.0},
            as_of="2026-12-01",
            source="Bank of Thailand",
        )
        self.actions.save_cost_item(
            trip_id=self.trip.trip_id,
            item={
                "label": "Cable car ticket",
                "category": "activity",
                "original_amount": 120,
                "original_currency": "CNY",
                "payment_state": "estimate",
            },
        )
        self.actions.save_cost_item(
            trip_id=self.trip.trip_id,
            item={
                "label": "Guest house",
                "category": "accommodation",
                "original_amount": 600,
                "original_currency": "CNY",
                "payment_state": "paid",
                "actual_thb": 2900,
            },
        )

        snapshot = self.actions.build_export_snapshot(self.trip.trip_id).as_dict()
        archive = zipfile.ZipFile(BytesIO(plan_workbook_xlsx(snapshot)))
        strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
        costs_sheet = archive.read("xl/worksheets/sheet5.xml").decode("utf-8")
        summary = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

        self.assertIn("Cable car ticket", strings)
        self.assertIn("Bank of Thailand", strings)
        self.assertIn("Estimated THB", strings)
        self.assertIn("autoFilter", costs_sheet)
        self.assertNotIn("No cost evidence is available yet.", strings)
        # 120 CNY at 5.0 converts; the paid room reports its locked charge.
        self.assertIn("<v>600</v>", costs_sheet)
        self.assertIn("<v>2900</v>", costs_sheet)
        # Summary carries the split totals.
        self.assertIn("<v>600</v>", summary)
        self.assertIn("<v>2900</v>", summary)
        totals = snapshot["costs"]["totals"]
        self.assertEqual(600.0, totals["estimated_thb"])
        self.assertEqual(2900.0, totals["paid_thb"])


class CostViewTest(unittest.TestCase):
    def test_costs_section_renders_and_saves(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "view.sqlite3"
            actions = PlannerActions(path)
            trip = actions.create_trip(name="Dali", destination="Dali")
            actions.save_rate_snapshot(
                trip_id=trip.trip_id,
                rates={"CNY": 5.0},
                as_of="2026-12-01",
                source="Bank of Thailand",
            )
            actions.save_cost_item(
                trip_id=trip.trip_id,
                item={
                    "label": "Cable car",
                    "category": "activity",
                    "original_amount": 120,
                    "original_currency": "CNY",
                    "payment_state": "estimate",
                },
            )

            with patch.dict(os.environ, {"TOURIST_DB_PATH": str(path)}):
                app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
                self.assertFalse(app.exception)
                self.assertIn("Costs", [item.value for item in app.subheader])
                text = "\n".join(
                    str(item.value)
                    for group in (app.markdown, app.caption, app.info, app.warning)
                    for item in group
                )
                self.assertIn("Cable car", text)
                self.assertIn("600.00 THB", text)
                self.assertIn("Total THB 600.00", text)

                app.radio[0].set_value("th").run()
                self.assertFalse(app.exception)
                self.assertIn("ค่าใช้จ่าย", [item.value for item in app.subheader])


if __name__ == "__main__":
    unittest.main()
