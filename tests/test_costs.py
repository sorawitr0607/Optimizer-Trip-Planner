from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile


from travel_planner import costs, split
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


class ReconciliationTest(unittest.TestCase):
    """Artifact 023: planned versus actual across the two linked ledgers."""

    TRAVELLERS = ("owner", "member_1", "member_2")

    def cost(self, **overrides) -> dict:
        payload = {
            "cost_id": "cost_hotel",
            "label": "Hotel · 5 nights",
            "category": "accommodation",
            "original_amount": 1200.0,
            "original_currency": "THB",
            "payment_state": "paid",
            "actual_thb": 1150.0,
        }
        payload.update(overrides)
        return costs.validate_cost(payload) | {"cost_id": payload["cost_id"]}

    def spend(self, **overrides) -> dict:
        payload = {
            "label": "Hotel · night 1",
            "mode": "equal_all",
            "paid_by": "owner",
            "participants": list(self.TRAVELLERS),
            "tag": "accommodation",
            "original_amount": 600.0,
            "original_currency": "THB",
        }
        payload.update(overrides)
        return split.validate_row(payload, self.TRAVELLERS)

    def totals(self, cost_rows, split_rows=(), headcount=None) -> dict:
        snapshot = rates()
        return costs.totals(
            costs.apply_rates(list(cost_rows), snapshot),
            split.apply_rates(list(split_rows), snapshot),
            headcount,
        )

    def test_a_claimed_cost_row_contributes_its_actual_exactly_once(self) -> None:
        # The cost row locked 1,150; the split rows that claim it total 1,000.
        # Whichever side wins, the answer must be one of them and never the sum.
        result = self.totals(
            [self.cost()],
            [
                self.spend(cost_id="cost_hotel", original_amount=600.0),
                self.spend(cost_id="cost_hotel", original_amount=400.0),
            ],
        )
        self.assertEqual(1000.0, result["actual_thb"])
        self.assertEqual(["cost_hotel"], result["claimed_cost_ids"])
        self.assertEqual(0, result["unclaimed_paid_rows"])

    def test_an_unclaimed_paid_row_supplies_its_own_actual(self) -> None:
        result = self.totals([self.cost()])

        self.assertEqual(1150.0, result["actual_thb"])
        self.assertEqual(1, result["unclaimed_paid_rows"])
        self.assertEqual([], result["claimed_cost_ids"])

    def test_voiding_the_claim_hands_the_cost_row_back(self) -> None:
        result = self.totals(
            [self.cost()],
            [self.spend(cost_id="cost_hotel", original_amount=600.0, voided=True)],
        )
        # Never 1,750 (both sides) and never 0 (neither): a voided claim
        # releases the cost row, so exactly one side supplies the actual.
        self.assertEqual(1150.0, result["actual_thb"])
        self.assertEqual(1, result["unclaimed_paid_rows"])

    def test_planned_keeps_every_row_including_the_ones_later_paid(self) -> None:
        result = self.totals([self.cost()])

        self.assertEqual(1200.0, result["planned_thb"])
        self.assertEqual(1150.0, result["actual_thb"])
        # The existing key still means "still to pay", so a paid row is absent
        # from it. That is why planned_thb had to be added rather than reused.
        self.assertEqual(0.0, result["estimated_thb"])

    def test_no_existing_total_changes_meaning(self) -> None:
        rows = [
            self.cost(),
            self.cost(cost_id="cost_ticket", label="Taipei 101", category="activity",
                      original_amount=1800.0, payment_state="estimate", actual_thb=None),
        ]
        before = costs.totals(costs.apply_rates(rows, rates()))
        after = self.totals(rows, [self.spend(cost_id="cost_hotel")])

        for key in ("estimated_thb", "paid_thb", "total_thb", "by_category", "rows"):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(1150.0, before["paid_thb"])
        self.assertEqual(1800.0, before["estimated_thb"])

    def test_a_category_with_spend_and_no_plan_is_not_a_zero(self) -> None:
        result = self.totals(
            [self.cost()],
            [self.spend(tag="food", original_amount=880.0, cost_id=None)],
        )
        comparison = result["by_category_comparison"]
        self.assertEqual(["food"], result["categories_without_plan"])
        self.assertFalse(comparison["food"]["planned"])
        self.assertTrue(comparison["food"]["actual"])
        self.assertEqual(880.0, comparison["food"]["actual_thb"])
        # Accommodation planned 1,200 and the unclaimed paid row supplied 1,150.
        self.assertEqual(-50.0, comparison["accommodation"]["difference_thb"])

    def test_planned_per_person_divides_by_headcount(self) -> None:
        result = self.totals([self.cost()], headcount=3)

        self.assertEqual(400.0, result["planned_per_person_thb"])
        # The trap named in artifact 023: group_preference_weights gives the
        # owner 0.5 and would charge them half the trip regardless of headcount.
        self.assertNotEqual(600.0, result["planned_per_person_thb"])

    def test_a_trip_with_no_members_divides_by_one(self) -> None:
        self.assertEqual(1200.0, self.totals([self.cost()], headcount=1)["planned_thb"])
        self.assertEqual(
            1200.0, self.totals([self.cost()], headcount=0)["planned_per_person_thb"]
        )

    def test_an_empty_split_ledger_leaves_the_actual_at_the_cost_side(self) -> None:
        # The ledger starts empty by decision, so this is the state on day one.
        result = self.totals([self.cost(payment_state="estimate", actual_thb=None)])
        self.assertEqual(1200.0, result["planned_thb"])
        self.assertEqual(0.0, result["actual_thb"])
        self.assertEqual(0, result["unclaimed_paid_rows"])


if __name__ == "__main__":
    unittest.main()


class EditableCategoryTest(unittest.TestCase):
    """Artifact 023 fixed the vocabulary at seven; the donor let a trip edit it.

    A trip that hires skis or pays a visa agent otherwise has nowhere to put that
    but `other` -- the category meaning "unclassified" -- which loses the very
    grouping the sheet exists for.
    """

    def setUp(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from travel_planner.actions import PlannerActions

        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.actions = PlannerActions(Path(directory.name) / "cats.sqlite3")
        self.trip = self.actions.create_trip(name="Niseko", destination="Niseko, Japan")

    def codes(self) -> list[str]:
        return [entry["code"] for entry in self.actions.cost_categories(self.trip.trip_id)]

    def test_a_trip_starts_with_the_seven(self) -> None:
        self.assertEqual(list(costs.CATEGORIES), self.codes())
        self.assertTrue(
            all(entry["built_in"] for entry in self.actions.cost_categories(self.trip.trip_id))
        )

    def test_a_custom_category_is_added_and_carries_its_own_label(self) -> None:
        """A code the owner invented has no catalogue entry, so without a stored
        label it would render as `⚠ ski_hire` in both languages."""

        self.actions.set_cost_categories(
            trip_id=self.trip.trip_id, categories=[{"code": "Ski hire", "label": "Ski hire"}]
        )

        entry = self.actions.cost_categories(self.trip.trip_id)[-1]
        self.assertEqual("ski_hire", entry["code"])
        self.assertEqual("Ski hire", entry["label"])
        self.assertFalse(entry["built_in"])
        # And it is now a category a cost row may actually use.
        self.actions.save_cost_item(
            trip_id=self.trip.trip_id,
            item={"label": "Skis", "category": "ski_hire", "original_amount": 4000},
        )

    def test_the_seven_survive_any_edit(self) -> None:
        """They are what an unrecognised tag falls back to, what `validate_cost`
        accepts with no trip in hand, and what the reference workbooks match."""

        self.actions.set_cost_categories(trip_id=self.trip.trip_id, categories=[])

        self.assertEqual(list(costs.CATEGORIES), self.codes())

    def test_a_category_still_on_a_row_cannot_be_removed(self) -> None:
        """Dropping it would leave rows pointing at a category the trip no longer
        has, and `category_for_tag` would silently re-file them under `other` --
        moving someone's money between groups without saying so."""

        from travel_planner.actions import PlannerRefusal

        self.actions.set_cost_categories(
            trip_id=self.trip.trip_id, categories=[{"code": "ski_hire", "label": "Ski hire"}]
        )
        self.actions.save_split_row(
            trip_id=self.trip.trip_id,
            row={"label": "Skis", "original_amount": 4000, "tag": "ski_hire"},
        )

        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.set_cost_categories(trip_id=self.trip.trip_id, categories=[])

        self.assertEqual("category_still_in_use", caught.exception.code)
        self.assertIn("ski_hire", self.codes())

    def test_a_custom_category_without_a_label_is_refused(self) -> None:
        from travel_planner.actions import PlannerRefusal

        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.set_cost_categories(
                trip_id=self.trip.trip_id, categories=[{"code": "ski_hire"}]
            )

        self.assertEqual("category_label_missing", caught.exception.code)

    def test_a_tag_outside_the_trip_vocabulary_still_falls_to_other(self) -> None:
        self.actions.save_split_row(
            trip_id=self.trip.trip_id,
            row={"label": "Souvenirs", "original_amount": 100, "tag": "gifts for Mum"},
        )

        row = self.actions.list_split_rows(self.trip.trip_id)[0]
        self.assertEqual("other", row["category"])
