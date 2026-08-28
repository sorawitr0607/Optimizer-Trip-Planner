from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from travel_planner import interpret
from travel_planner.actions import PlannerActions
from travel_planner.optimizer import optimize_trip
from travel_planner.providers import (
    OpenAIRevisionInterpreter,
    ProviderBudgetExceeded,
    RevisionInterpretationUnavailable,
)
from tests.test_revision import planner_input

ROOT = Path(__file__).resolve().parents[1]


def model_reply(operation: str, **arguments) -> dict:
    return {
        "operation": operation,
        "arguments": {
            key: arguments.get(key)
            for key in ("place_id", "factor", "minutes", "start", "end")
        },
        "clarification": None,
        "unsupported_reason": None,
    }


class FakeInterpreter:
    name = "openai"
    operation = "openai:interpret_revision"
    schema_version = 1

    def __init__(self, reply=None, *, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.reply = reply
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

    def test_the_payload_carries_only_the_plan_slice(self) -> None:
        payload = interpret.build_payload(
            plan=self.plan, request_text="reduce walking", language="en"
        )
        text = json.dumps(payload)

        self.assertEqual("reduce walking", payload["request"])
        self.assertTrue(payload["plan"]["days"])
        self.assertIn("thresholds", payload["plan"])
        # Nothing about the travellers, and no provider payload, reaches a model.
        for excluded in ("travellers", "owner", "passport", "photo_reference", "api_key"):
            self.assertNotIn(excluded, text)

    def test_a_payload_carrying_excluded_data_is_refused(self) -> None:
        plan = {
            "optimizer_input": {**self.plan["optimizer_input"], "travellers": [{"id": "owner"}]},
            "variant": self.plan["variant"],
        }
        # travellers never reach the slice, so build a direct violation instead.
        with self.assertRaisesRegex(ValueError, "never be sent to a model"):
            interpret._assert_clean({"plan": {"booking_document": "x"}})
        with self.assertRaisesRegex(ValueError, "never be sent to a model"):
            interpret._assert_clean({"nested": [{"openai_api_key": "x"}]})
        # The real builder drops them by construction.
        payload = interpret.build_payload(
            plan=plan, request_text="reduce walking", language="en"
        )
        self.assertNotIn("travellers", json.dumps(payload))

    def test_empty_text_or_unknown_language_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "needs some text"):
            interpret.build_payload(plan=self.plan, request_text="   ", language="en")
        with self.assertRaisesRegex(ValueError, "Unsupported language"):
            interpret.build_payload(plan=self.plan, request_text="x", language="ja")

    def test_the_schema_offers_exactly_the_supported_operations(self) -> None:
        from travel_planner import revision

        enum = interpret.response_schema()["properties"]["operation"]["enum"]
        self.assertEqual(sorted(revision.OPERATIONS) + ["unsupported"], enum)
        self.assertTrue(interpret.response_schema()["additionalProperties"] is False)


class ResponseValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        snapshot = planner_input()
        self.plan = {
            "optimizer_input": snapshot,
            "variant": optimize_trip(snapshot)["variants"][0],
        }
        self.payload = interpret.build_payload(
            plan=self.plan, request_text="reduce walking", language="en"
        )
        self.place_id = sorted(interpret.allowed_place_ids(self.payload))[0]

    def test_a_valid_reply_becomes_a_typed_operation(self) -> None:
        typed = interpret.interpret_response(
            model_reply("reduce_walking", factor=0.6), payload=self.payload
        )
        self.assertTrue(typed["supported"])
        self.assertEqual("reduce_walking", typed["operation"])
        self.assertEqual(0.6, typed["arguments"]["factor"])

    def test_an_unsupported_reply_changes_nothing_and_keeps_its_reason(self) -> None:
        typed = interpret.interpret_response(
            {
                "operation": "unsupported",
                "arguments": {},
                "clarification": None,
                "unsupported_reason": "Booking a flight is outside this planner",
            },
            payload=self.payload,
        )
        self.assertFalse(typed["supported"])
        self.assertIsNone(typed["operation"])
        self.assertIn("outside this planner", typed["unsupported_reason"])

    def test_a_place_the_model_was_not_shown_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the plan"):
            interpret.interpret_response(
                model_reply("lock_item", place_id="somewhere_invented"),
                payload=self.payload,
            )

    def test_a_place_from_the_plan_is_accepted(self) -> None:
        typed = interpret.interpret_response(
            model_reply("lock_item", place_id=self.place_id), payload=self.payload
        )
        self.assertEqual(self.place_id, typed["arguments"]["place_id"])

    def test_a_malformed_or_unknown_reply_is_refused(self) -> None:
        for bad in (
            None,
            "reduce walking",
            {},
            {"operation": "delete_everything", "arguments": {}},
            {"operation": "reduce_walking", "arguments": "loads"},
        ):
            with self.assertRaises(ValueError):
                interpret.interpret_response(bad, payload=self.payload)

    def test_a_missing_magnitude_uses_a_visible_default(self) -> None:
        """A live model returns factor: null for "cut down the walking"."""

        typed = interpret.interpret_response(
            model_reply("reduce_walking"), payload=self.payload
        )
        self.assertTrue(typed["supported"])
        self.assertEqual(0.7, typed["arguments"]["factor"])
        self.assertEqual(["ASSUMED_FACTOR_0.7"], typed["assumptions"])

        meal = interpret.interpret_response(
            model_reply("fix_meal_timing"), payload=self.payload
        )
        self.assertEqual("12:00", meal["arguments"]["start"])
        self.assertEqual(2, len(meal["assumptions"]))

    def test_a_value_that_cannot_be_assumed_asks_one_clarification(self) -> None:
        # A visit length is the whole point of the request, so it is not guessed.
        typed = interpret.interpret_response(
            model_reply("adjust_duration", place_id=self.place_id),
            payload=self.payload,
        )
        self.assertFalse(typed["supported"])
        self.assertEqual("NEEDS_CLARIFICATION", typed["unsupported_reason"])
        self.assertIn("minutes", typed["clarification"])

    def test_an_explicit_value_is_never_overridden_by_a_default(self) -> None:
        typed = interpret.interpret_response(
            model_reply("reduce_walking", factor=0.4), payload=self.payload
        )
        self.assertEqual(0.4, typed["arguments"]["factor"])
        self.assertEqual([], typed["assumptions"])

    def test_out_of_range_arguments_are_still_refused(self) -> None:
        # The typed contract applies to model output exactly as to a quick action.
        with self.assertRaisesRegex(ValueError, "factor must be"):
            interpret.interpret_response(
                model_reply("reduce_walking", factor=9.0), payload=self.payload
            )
        with self.assertRaisesRegex(ValueError, "must use HH:MM"):
            interpret.interpret_response(
                model_reply("fix_meal_timing", start="lunchtime", end="13:00"),
                payload=self.payload,
            )


class ExtractionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OpenAIRevisionInterpreter()

    def test_a_structured_reply_is_extracted(self) -> None:
        raw = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(model_reply("explain"))}],
                }
            ],
        }
        self.assertEqual("explain", self.provider.extract(raw)["operation"])

    def test_a_refusal_is_reported_as_a_refusal(self) -> None:
        raw = {"output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]}
        with self.assertRaises(RevisionInterpretationUnavailable) as caught:
            self.provider.extract(raw)
        self.assertEqual("refused", caught.exception.cause)

    def test_an_incomplete_or_empty_reply_is_reported(self) -> None:
        for raw, cause in (
            ({"status": "incomplete", "output": []}, "invalid_reply"),
            ({"output": []}, "invalid_reply"),
            ({"output": [{"content": [{"type": "output_text", "text": "not json"}]}]}, "invalid_reply"),
        ):
            with self.assertRaises(RevisionInterpretationUnavailable) as caught:
                self.provider.extract(raw)
            self.assertEqual(cause, caught.exception.cause)


class InterpretFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "ai.sqlite3"
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

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _run(self, reply=None, *, error=None, text="reduce the walking please"):
        self.actions.interpreter = FakeInterpreter(reply, error=error)
        return self.actions.interpret_revision(
            trip_id=self.trip.trip_id, request_text=text
        )

    def _unchanged(self) -> None:
        self.assertEqual(
            self.version.version_id,
            self.actions.get_active_plan(self.trip.trip_id).version_id,
        )
        self.assertEqual([], self.actions.list_revisions(self.trip.trip_id))

    def test_free_text_becomes_a_pending_preview_with_provenance(self) -> None:
        result = self._run(model_reply("reduce_walking", factor=0.6))

        self.assertTrue(result["supported"])
        self.assertEqual("reduce_walking", result["operation"])
        draft = self.actions.get_revision_draft(self.trip.trip_id)
        self.assertEqual("ai", draft["interpreted_by"])
        self.assertEqual("fake-model", draft["interpretation"]["model"])
        self.assertEqual(1, draft["interpretation"]["intent_schema_version"])
        self.assertEqual("reduce the walking please", draft["request_text"])
        # Still nothing applied.
        self._unchanged()

    def test_exactly_one_model_call_per_request(self) -> None:
        self.actions.interpreter = FakeInterpreter(model_reply("reduce_walking", factor=0.6))
        self.actions.interpret_revision(
            trip_id=self.trip.trip_id, request_text="less walking"
        )
        self.assertEqual(1, len(self.actions.interpreter.calls))
        bucket = self.actions.paid_usage_status()["by_operation"][
            "openai:interpret_revision"
        ]
        self.assertEqual(1, bucket["requests"])

    def test_an_unsupported_request_changes_nothing(self) -> None:
        result = self._run(
            {
                "operation": "unsupported",
                "arguments": {},
                "clarification": None,
                "unsupported_reason": "Booking flights is out of scope",
            }
        )
        self.assertFalse(result["supported"])
        self.assertIsNone(result["draft"])
        self.assertIsNone(self.actions.get_revision_draft(self.trip.trip_id))
        self._unchanged()

    def test_every_failure_cause_leaves_the_plan_untouched(self) -> None:
        for cause in ("missing_credentials", "offline", "refused", "invalid_reply",
                      "rate_limited", "api_error"):
            with self.assertRaises(RevisionInterpretationUnavailable) as caught:
                self._run(error=RevisionInterpretationUnavailable("failed", cause=cause))
            self.assertEqual(cause, caught.exception.cause)
            self.assertIsNone(self.actions.get_revision_draft(self.trip.trip_id))
            self._unchanged()

    def test_a_failed_attempt_is_still_recorded_in_the_ledger(self) -> None:
        with self.assertRaises(RevisionInterpretationUnavailable):
            self._run(error=RevisionInterpretationUnavailable("down", cause="offline"))
        entries = self.actions.store.list_paid_usage(limit=100)
        self.assertEqual(["error"], [item["outcome"] for item in entries])

    def test_a_model_naming_an_unknown_place_is_reported_not_applied(self) -> None:
        with self.assertRaises(RevisionInterpretationUnavailable) as caught:
            self._run(model_reply("lock_item", place_id="invented_place"))
        self.assertEqual("invalid_reply", caught.exception.cause)
        self._unchanged()

    def test_the_budget_stop_prevents_the_call_entirely(self) -> None:
        self.actions.record_paid_call(operation="google_places:details", count=600)
        self.actions.interpreter = FakeInterpreter(model_reply("explain"))
        with self.assertRaises(ProviderBudgetExceeded):
            self.actions.interpret_revision(
                trip_id=self.trip.trip_id, request_text="explain this"
            )
        self.assertEqual([], self.actions.interpreter.calls)
        self._unchanged()

    def test_an_interpreted_revision_can_be_applied_and_recorded_as_ai(self) -> None:
        place_id = sorted(
            item["subject_id"]
            for day in self.version.snapshot.as_dict()["variant"]["days"]
            for item in day["items"]
            if item["type"] == "visit"
        )[0]
        self._run(model_reply("lock_item", place_id=place_id), text="lock the first stop")
        applied = self.actions.apply_revision(self.trip.trip_id)

        history = self.actions.list_revisions(self.trip.trip_id)
        self.assertEqual(1, len(history))
        self.assertEqual("ai", history[0]["interpreted_by"])
        self.assertEqual("fake-model", history[0]["interpretation"]["model"])
        self.assertEqual("lock the first stop", history[0]["request_text"])
        self.assertEqual(applied.version_id, history[0]["to_version_id"])

    def test_an_assumed_default_reaches_the_visible_assumptions(self) -> None:
        self._run(model_reply("reduce_walking"), text="cut down the walking")
        draft = self.actions.get_revision_draft(self.trip.trip_id)

        self.assertIn("ASSUMED_FACTOR_0.7", draft["assumptions"])
        self.assertEqual(
            ["ASSUMED_FACTOR_0.7"], draft["interpretation"]["assumed_defaults"]
        )

    def test_a_clarification_leaves_no_pending_preview(self) -> None:
        place_id = sorted(
            item["subject_id"]
            for day in self.version.snapshot.as_dict()["variant"]["days"]
            for item in day["items"]
            if item["type"] == "visit"
        )[0]
        result = self._run(
            model_reply("adjust_duration", place_id=place_id),
            text="make that stop shorter",
        )
        self.assertFalse(result["supported"])
        self.assertEqual("NEEDS_CLARIFICATION", result["unsupported_reason"])
        self.assertIsNone(self.actions.get_revision_draft(self.trip.trip_id))
        self._unchanged()

    def test_thai_and_mixed_text_reach_the_same_typed_operation(self) -> None:
        for text in ("ลดการเดินหน่อย", "please ลดการเดิน on day 1"):
            self.actions.interpreter = FakeInterpreter(
                model_reply("reduce_walking", factor=0.6)
            )
            result = self.actions.interpret_revision(
                trip_id=self.trip.trip_id,
                request_text=text,
                language="th",
                replace_pending=True,
            )
            self.assertEqual("reduce_walking", result["operation"])
            self.assertEqual(text, self.actions.interpreter.calls[0]["request"])

    def test_interpreting_needs_an_active_plan(self) -> None:
        bare = PlannerActions(
            Path(self.directory.name) / "bare.sqlite3",
            interpreter=FakeInterpreter(model_reply("explain")),
        )
        trip = bare.create_trip(name="Bare", destination="Osaka")
        with self.assertRaises(ValueError) as raised:
            bare.interpret_revision(trip_id=trip.trip_id, request_text="explain")
        self.assertEqual("no_active_plan", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
