from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from travel_planner import review, usage
from travel_planner.actions import PlannerActions, PlannerRefusal
from travel_planner.optimizer import optimize_trip
from travel_planner.providers import (
    OpenAIPlanReviewer,
    OpenAIRevisionInterpreter,
    RevisionInterpretationUnavailable,
)
from tests.test_revision import planner_input


def model_reply(*suggestions: dict) -> dict:
    return {"suggestions": list(suggestions)}


def suggestion(operation: str, place_id: str | None, **kwargs) -> dict:
    return {
        "operation": operation,
        "arguments": {"place_id": place_id, "minutes": kwargs.get("minutes")},
        "rationale": kwargs.get("rationale", "Shorter fits the day better."),
    }


class FakeReviewer:
    name = "openai"
    operation = "openai:plan_review"
    schema_version = 1

    def __init__(self, reply=None, *, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.reply = reply if reply is not None else model_reply()
        self.error = error
        self.model = "fake-model"

    def interpret(self, payload: dict, *, retry: bool = True) -> dict:
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        return {
            "response": self.reply,
            "model": self.model,
            "schema_version": self.schema_version,
        }


class PayloadTest(unittest.TestCase):
    def setUp(self) -> None:
        snapshot = planner_input()
        self.plan = {
            "optimizer_input": snapshot,
            "variant": optimize_trip(snapshot)["variants"][0],
        }
        self.payload = review.build_payload(plan=self.plan, language="en")

    def test_the_payload_carries_the_plan_slice_and_no_secrets(self) -> None:
        text = json.dumps(self.payload)

        self.assertTrue(self.payload["plan"]["days"])
        self.assertIn("thresholds", self.payload["plan"])
        self.assertEqual(["adjust_duration", "drop_place", "lock_item"],
                         self.payload["supported_operations"])
        for excluded in ("travellers", "owner", "passport", "photo_reference", "api_key"):
            self.assertNotIn(excluded, text)

    def test_unknown_language_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported language"):
            review.build_payload(plan=self.plan, language="ja")

    def test_the_schema_offers_only_the_review_operations(self) -> None:
        enum = review.response_schema()["properties"]["suggestions"]["items"][
            "properties"
        ]["operation"]["enum"]
        self.assertEqual(["adjust_duration", "drop_place", "lock_item"], sorted(enum))
        arguments = review.response_schema()["properties"]["suggestions"]["items"][
            "properties"
        ]["arguments"]["properties"]
        # No time, date, route, hour, fare or closure for the model to fill in.
        self.assertEqual({"place_id", "minutes"}, set(arguments))


class ReplyTest(unittest.TestCase):
    def setUp(self) -> None:
        snapshot = planner_input()
        plan = {
            "optimizer_input": snapshot,
            "variant": optimize_trip(snapshot)["variants"][0],
        }
        self.payload = review.build_payload(plan=plan, language="en")
        days = self.payload["plan"]["days"]
        self.place_id = days[0]["items"][0]["place_id"]

    def test_valid_suggestions_pass_with_rationales(self) -> None:
        result = review.validate_reply(
            model_reply(
                suggestion("adjust_duration", self.place_id, minutes=30),
                suggestion("drop_place", self.place_id),
            ),
            payload=self.payload,
        )

        self.assertEqual(0, result["dropped"])
        self.assertEqual("adjust_duration", result["suggestions"][0]["operation"])
        self.assertEqual(30, result["suggestions"][0]["arguments"]["minutes"])
        self.assertEqual("drop_place", result["suggestions"][1]["operation"])
        self.assertTrue(result["suggestions"][0]["rationale"])

    def test_a_long_rationale_is_capped_not_fatal(self) -> None:
        result = review.validate_reply(
            model_reply(
                suggestion("drop_place", self.place_id, rationale="x" * 500)
            ),
            payload=self.payload,
        )

        self.assertEqual(1, len(result["suggestions"]))
        self.assertEqual(review.MAX_RATIONALE_CHARS,
                         len(result["suggestions"][0]["rationale"]))

    def test_unknown_operations_foreign_places_and_valueless_durations_drop(self) -> None:
        result = review.validate_reply(
            model_reply(
                {"operation": "delete_everything", "arguments": {}, "rationale": None},
                suggestion("drop_place", "place_that_was_never_shown"),
                suggestion("adjust_duration", self.place_id),
                suggestion("lock_item", self.place_id),
            ),
            payload=self.payload,
        )

        # Only the lock survives: the op is unknown, the place was never shown,
        # and a duration without minutes is unactionable.
        self.assertEqual(3, result["dropped"])
        self.assertEqual(["lock_item"], [item["operation"] for item in result["suggestions"]])

    def test_a_reply_with_no_list_is_malformed(self) -> None:
        with self.assertRaisesRegex(ValueError, "no suggestions list"):
            review.validate_reply({"suggestions": None}, payload=self.payload)
        with self.assertRaisesRegex(ValueError, "not an object"):
            review.validate_reply([], payload=self.payload)

    def test_an_empty_list_is_a_clean_bill_not_an_error(self) -> None:
        result = review.validate_reply(model_reply(), payload=self.payload)

        self.assertEqual([], result["suggestions"])
        self.assertEqual(0, result["dropped"])


class ReviewerContractTest(unittest.TestCase):
    def test_the_reviewer_is_wired_to_its_own_schema_and_priced_operation(self) -> None:
        reviewer = OpenAIPlanReviewer()

        self.assertEqual("openai:plan_review", reviewer.operation)
        self.assertEqual("plan_review", reviewer.schema_name)
        self.assertEqual(review.response_schema(), reviewer.request_schema())
        self.assertNotEqual(
            OpenAIRevisionInterpreter.SYSTEM_PROMPT, reviewer.SYSTEM_PROMPT
        )
        # Priced, so the paid gate sees the call before it is made.
        self.assertGreater(usage.price_for("openai:plan_review"), 0)


class ReviewFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "review.sqlite3"
        self.snapshot = planner_input()
        proposal = optimize_trip(self.snapshot)
        self.actions = PlannerActions(self.path)
        self.trip = self.actions.create_trip(name="Tokyo", destination="Tokyo")
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
        days = proposal["variants"][0]["days"]
        self.place_id = next(
            item["subject_id"]
            for day in days
            for item in day["items"]
            if item["type"] == "visit"
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _run(self, reply=None, *, error=None):
        self.actions.reviewer = FakeReviewer(reply, error=error)
        return self.actions.review_plan(trip_id=self.trip.trip_id)

    def test_suggestions_come_back_typed_and_nothing_is_applied(self) -> None:
        result = self._run(
            model_reply(suggestion("adjust_duration", self.place_id, minutes=30))
        )

        self.assertEqual(1, len(result["suggestions"]))
        self.assertEqual("adjust_duration", result["suggestions"][0]["operation"])
        self.assertEqual(30, result["suggestions"][0]["arguments"]["minutes"])
        self.assertEqual("fake-model", result["model"])
        # Still nothing proposed, previewed or applied.
        self.assertEqual(
            self.version.version_id,
            self.actions.get_active_plan(self.trip.trip_id).version_id,
        )
        self.assertEqual([], self.actions.list_revisions(self.trip.trip_id))
        self.assertIsNone(self.actions.get_revision_draft(self.trip.trip_id))

    def test_exactly_one_model_call_per_review(self) -> None:
        self.actions.reviewer = FakeReviewer(
            model_reply(suggestion("drop_place", self.place_id))
        )
        self.actions.review_plan(trip_id=self.trip.trip_id)

        self.assertEqual(1, len(self.actions.reviewer.calls))
        bucket = self.actions.paid_usage_status()["by_operation"]["openai:plan_review"]
        self.assertEqual(1, bucket["requests"])

    def test_a_provider_error_records_and_leaves_the_plan_untouched(self) -> None:
        with self.assertRaises(RevisionInterpretationUnavailable):
            self._run(
                error=RevisionInterpretationUnavailable("boom", cause="offline")
            )

        # The attempt is still recorded, so the ledger reconciles.
        bucket = self.actions.paid_usage_status()["by_operation"]["openai:plan_review"]
        self.assertEqual(1, bucket["requests"])
        self.assertEqual(
            self.version.version_id,
            self.actions.get_active_plan(self.trip.trip_id).version_id,
        )

    def test_no_active_plan_is_a_refusal_before_any_spend(self) -> None:
        other = self.actions.create_trip(name="Empty", destination="Kyoto")

        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.review_plan(trip_id=other.trip_id)
        self.assertEqual("no_active_plan", str(caught.exception))
        self.assertNotIn(
            "openai:plan_review", self.actions.paid_usage_status()["by_operation"]
        )


if __name__ == "__main__":
    unittest.main()
