from __future__ import annotations

import unittest

from travel_planner import costs, split


TRAVELLERS = ("owner", "member_1", "member_2")


def rates(**overrides) -> dict:
    return costs.new_rate_snapshot(
        rates={"TWD": 1.12, **overrides.pop("rates", {})},
        as_of=overrides.pop("as_of", "2026-12-28"),
        source=overrides.pop("source", "Bank of Thailand reference rate"),
        buffer_percent=overrides.pop("buffer_percent", 0.0),
    )


def row(*, roster: tuple[str, ...] | None = TRAVELLERS, **overrides) -> dict:
    payload = {
        "label": "Hotel · night 1",
        "mode": "equal_all",
        "paid_by": "owner",
        "participants": list(TRAVELLERS),
        "tag": "accommodation",
        "original_amount": 100.0,
        "original_currency": "THB",
    }
    payload.update(overrides)
    return split.validate_row(payload, roster)


def resolved(*rows: dict, snapshot: dict | None = None) -> list[dict]:
    return split.apply_rates(list(rows), snapshot or rates())


def summary(*rows: dict, cardholder: str = "owner", settled: dict | None = None) -> dict:
    return split.summary(
        list(rows), travellers=TRAVELLERS, cardholder=cardholder, settled=settled
    )


class RoundingTest(unittest.TestCase):
    def test_the_remainder_lands_on_the_documented_participant(self) -> None:
        shares = split.shares(resolved(row(original_amount=100.0))[0])
        self.assertEqual([33.34, 33.33, 33.33], list(shares.values()))
        # The absorber is the row's own first participant, not whoever sorts first.
        self.assertEqual(33.34, shares["owner"])
        self.assertEqual(100.0, round(sum(shares.values()), 2))

    def test_the_remainder_spreads_one_satang_at_a_time(self) -> None:
        people = [f"member_{index}" for index in range(1, 7)]
        shares = split.shares(
            resolved(row(participants=people, paid_by="member_1", roster=tuple(people)))[0]
        )
        amounts = sorted(shares.values())
        self.assertEqual(100.0, round(sum(amounts), 2))
        # Four take 16.67 and two take 16.66; nobody is over-charged by more
        # than one satang, which is what spreading buys over dumping on one.
        self.assertEqual(0.01, round(amounts[-1] - amounts[0], 2))
        self.assertEqual(4, sum(1 for amount in amounts if amount == 16.67))

    def test_satang_always_sum_to_the_row_exactly(self) -> None:
        for amount in (0.01, 0.02, 10.0, 99.99, 100.0, 1240.55, 8400.0):
            for count in range(1, 9):
                portions = split._split_satang(amount, count)
                self.assertEqual(round(amount * 100), sum(portions), (amount, count))

    def test_a_single_payer_row_bears_the_whole_amount(self) -> None:
        shares = split.shares(
            resolved(row(mode="single_payer", participants=["member_2"]))[0]
        )
        self.assertEqual({"member_2": 100.0}, shares)


class SettlementTest(unittest.TestCase):
    def test_settlement_is_a_star_through_the_cardholder(self) -> None:
        result = summary(*resolved(row(original_amount=300.0)))
        self.assertEqual(["member_1", "member_2"], [
            entry["traveller_id"] for entry in result["settlement"]
        ])
        for entry in result["settlement"]:
            self.assertEqual("traveller_pays_cardholder", entry["direction"])
            self.assertEqual(100.0, entry["amount_thb"])
        # The cardholder never appears as one end of their own payment.
        self.assertNotIn("owner", [entry["traveller_id"] for entry in result["settlement"]])

    def test_fronted_cash_reverses_the_direction(self) -> None:
        # member_1 fronts a 900 taxi shared three ways: their own share is 300,
        # so the cardholder ends up owing them 600.
        result = summary(
            *resolved(row(original_amount=900.0, paid_by="member_1", tag="transport"))
        )
        reversed_entry = next(
            entry for entry in result["settlement"] if entry["traveller_id"] == "member_1"
        )
        self.assertEqual("cardholder_pays_traveller", reversed_entry["direction"])
        self.assertEqual(600.0, reversed_entry["amount_thb"])
        self.assertEqual(-600.0, reversed_entry["net_thb"])
        self.assertEqual(900.0, reversed_entry["paid_out_thb"])

    def test_fronted_cash_is_netted_off_rather_than_listed_separately(self) -> None:
        result = summary(
            *resolved(
                row(original_amount=300.0),
                row(original_amount=120.0, paid_by="member_1", tag="food"),
            )
        )
        member = next(
            entry for entry in result["settlement"] if entry["traveller_id"] == "member_1"
        )
        # shares 100 + 40 = 140, paid out 120, so one net payment of 20.
        self.assertEqual(140.0, member["shares_thb"])
        self.assertEqual(120.0, member["paid_out_thb"])
        self.assertEqual(20.0, member["amount_thb"])
        self.assertEqual("traveller_pays_cardholder", member["direction"])

    def test_a_zero_balance_produces_no_suggested_payment(self) -> None:
        result = summary(
            *resolved(row(original_amount=300.0, participants=["member_1"], paid_by="member_1"))
        )
        self.assertEqual([], result["settlement"])

    def test_the_settled_marker_goes_stale_when_the_balance_moves(self) -> None:
        rows = resolved(row(original_amount=300.0))
        marked = summary(*rows, settled={"member_1": 100.0})
        self.assertTrue(
            next(e for e in marked["settlement"] if e["traveller_id"] == "member_1")["settled"]
        )
        # Adding a row that includes them changes the arithmetic, so the marker
        # no longer describes the balance and silently stops applying.
        moved = summary(
            *resolved(
                row(original_amount=300.0),
                row(original_amount=60.0, tag="food"),
            ),
            settled={"member_1": 100.0},
        )
        self.assertFalse(
            next(e for e in moved["settlement"] if e["traveller_id"] == "member_1")["settled"]
        )


class RateTest(unittest.TestCase):
    def test_the_estimate_buffer_is_skipped_for_split_rows(self) -> None:
        snapshot = rates(buffer_percent=10.0)
        item = {"original_amount": 100.0, "original_currency": "TWD", "payment_state": "estimate"}
        cost = costs.apply_rates([item], snapshot)[0]
        spent = split.apply_rates([row(original_amount=100.0, original_currency="TWD")], snapshot)[0]
        self.assertEqual(123.2, cost["converted_thb"])
        self.assertEqual(112.0, spent["reported_thb"])

    def test_a_recorded_actual_thb_is_never_reconverted(self) -> None:
        spent = split.apply_rates(
            [row(original_amount=100.0, original_currency="TWD", actual_thb=3000.0)],
            rates(),
        )[0]
        self.assertEqual(3000.0, spent["reported_thb"])
        # Known THB needs no rate provenance, so it is not a visible gap.
        self.assertFalse(spent["rate_missing"])

    def test_a_missing_rate_stays_a_gap_rather_than_a_guess(self) -> None:
        result = summary(*split.apply_rates([row(original_currency="JPY")], rates()))
        self.assertEqual(0.0, result["actual_thb"])
        self.assertEqual(1, result["unconvertible_rows"])
        self.assertEqual(["JPY"], result["missing_rates"])


class LedgerTest(unittest.TestCase):
    def test_a_voided_row_leaves_the_totals_but_stays_visible(self) -> None:
        result = summary(
            *resolved(row(original_amount=300.0), row(original_amount=224.0, voided=True))
        )
        self.assertEqual(300.0, result["actual_thb"])
        self.assertEqual(2, result["rows"])
        self.assertEqual(1, result["voided_rows"])

    def test_tags_map_onto_the_seven_categories(self) -> None:
        self.assertEqual("food", split.category_for_tag("Food"))
        self.assertEqual("other", split.category_for_tag("souvenirs for Mum"))
        self.assertEqual("other", split.category_for_tag(None))
        result = summary(*resolved(row(tag="Disney tickets", original_amount=300.0)))
        self.assertEqual({"other": 300.0}, result["by_category"])


class ValidationTest(unittest.TestCase):
    def test_a_row_needs_a_label_a_mode_a_payer_and_participants(self) -> None:
        with self.assertRaisesRegex(ValueError, "label"):
            row(label="  ")
        with self.assertRaisesRegex(ValueError, "split mode"):
            row(mode="weighted")
        with self.assertRaisesRegex(ValueError, "who paid"):
            row(paid_by="")
        with self.assertRaisesRegex(ValueError, "at least one participant"):
            row(participants=[])

    def test_a_repeated_participant_is_refused_rather_than_deduped(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot repeat"):
            row(participants=["member_1", "member_1"])

    def test_single_payer_refuses_more_than_one_participant(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one traveller"):
            row(mode="single_payer", participants=["member_1", "member_2"])

    def test_a_participant_must_be_an_existing_traveller(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown traveller ids: mum"):
            row(participants=["owner", "mum"])
        # Without the roster the shape still validates: setup is where the
        # roster lives, so membership is only checkable there.
        self.assertEqual(
            ["owner", "mum"],
            split.validate_row({**row(), "participants": ["owner", "mum"]})["participants"],
        )

    def test_negative_money_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "original_amount cannot be negative"):
            row(original_amount=-1)
        with self.assertRaisesRegex(ValueError, "actual_thb cannot be negative"):
            row(actual_thb=-1)

    def test_a_currency_must_be_a_three_letter_code(self) -> None:
        with self.assertRaisesRegex(ValueError, "three-letter ISO code"):
            row(original_currency="baht")

    def test_optional_links_normalize_to_none_rather_than_empty_text(self) -> None:
        clean = row(cost_id="", plan_day="", place_id="")
        self.assertIsNone(clean["cost_id"])
        self.assertIsNone(clean["plan_day"])
        self.assertIsNone(clean["place_id"])


if __name__ == "__main__":
    unittest.main()
