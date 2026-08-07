from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from travel_planner.actions import PlannerActions, PlannerRefusal
from travel_planner.providers import (
    OpenAIOpeningWindowProvider,
    ProviderUnavailable,
    _clock_window,
)
from tests.test_opening import FakeHoursProvider
from tests.test_routes import FakePlaceProvider


class WindowParsingTest(unittest.TestCase):
    """`WF-046`. A malformed pair is a refusal, not something to repair."""

    def test_only_a_well_formed_forward_pair_survives(self) -> None:
        self.assertEqual({"start": "09:00", "end": "18:00"}, _clock_window("09:00", "18:00"))
        # Zero-padded, because a fact is compared as a string elsewhere.
        self.assertEqual({"start": "09:00", "end": "18:00"}, _clock_window("9:00", "18:00"))
        for start, end in (
            ("18:00", "09:00"),   # backwards
            ("09:00", "09:00"),   # empty
            ("24:00", "25:00"),   # not a clock time
            ("bad", "18:00"),
            (None, "18:00"),
            ("09:00", None),
        ):
            with self.subTest(start=start, end=end):
                self.assertIsNone(_clock_window(start, end))

    def test_the_request_never_asks_for_a_closure(self) -> None:
        """The benchmark asked for weekly closed days and 2 of 7 came back invented --
        Huashan 1914 and Taipei Zoo, neither closed on any trip date. A false closure
        silently removes a place from a day, so the field is not requested at all."""

        provider = OpenAIOpeningWindowProvider()

        self.assertEqual(
            {"known", "start", "end"}, set(provider.RESPONSE_SCHEMA["properties"])
        )
        self.assertFalse(provider.RESPONSE_SCHEMA["additionalProperties"])
        self.assertIn("Never state a holiday closure", provider.SYSTEM_PROMPT)

    def test_a_declined_answer_is_reported_not_repaired(self) -> None:
        provider = OpenAIOpeningWindowProvider()
        provider.url = "https://example.invalid/unused"

        def reply(payload):
            return {"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]}

        # known but with an unusable pair: still a refusal.
        self.assertFalse(
            provider._parse(reply({"known": True, "start": "nonsense", "end": "18:00"}))
            .get("start") == "18:00"
        )
        self.assertEqual(
            {"known": True, "start": "nonsense", "end": "18:00"},
            provider._parse(reply({"known": True, "start": "nonsense", "end": "18:00"})),
        )

    def test_an_all_day_window_is_discarded_as_a_non_answer(self) -> None:
        """"Open all day" permits *more* than the 09:00-21:00 constant it would replace,
        which inverts the whole reason for asking. Measured: `gpt-5.6-luna` returned
        00:00-23:59 for Huashan 1914, whose real hours are 11:00-21:00."""

        provider = OpenAIOpeningWindowProvider()
        provider._parse = lambda raw: raw  # type: ignore[method-assign]
        calls = {}

        def fake_open(request, timeout=None):
            calls["asked"] = True
            raise AssertionError("unused")

        # Exercise the span rule directly rather than the transport.
        from travel_planner.providers import _span_minutes

        self.assertGreaterEqual(
            _span_minutes({"start": "00:00", "end": "23:59"}),
            provider.DEGENERATE_SPAN_MINUTES,
        )
        # A temple really does open 06:00-22:00, so the bar must sit above sixteen hours.
        self.assertLess(
            _span_minutes({"start": "06:00", "end": "22:00"}),
            provider.DEGENERATE_SPAN_MINUTES,
        )
        # And the constant itself must never be discarded by its own rule.
        self.assertLess(
            _span_minutes({"start": "09:00", "end": "21:00"}),
            provider.DEGENERATE_SPAN_MINUTES,
        )

    def test_a_refusal_in_the_reply_raises(self) -> None:
        provider = OpenAIOpeningWindowProvider()
        with self.assertRaises(ProviderUnavailable):
            provider._parse({"output": [{"type": "refusal"}]})
        with self.assertRaises(ProviderUnavailable):
            provider._parse({"status": "incomplete"})


class FakeWindowProvider:
    name = "fake_window"
    operation = "openai:opening_window"
    kind = "assumed_opening_window"
    cache_ttl_days = 90

    def __init__(self, *, answer=None, fail: bool = False) -> None:
        self.answer = answer or {"known": True, "start": "09:00", "end": "18:00", "model": "fake-1"}
        self.fail = fail
        self.asked: list[str] = []
        self.calls = 0

    BATCH_SIZE = 20

    def window(self, *, name: str, local_name: str, destination: str):
        self.asked.append(name)
        if self.fail:
            raise ProviderUnavailable("Model returned HTTP 429")
        return {**self.answer, "asked": f"{name} in {destination}"}

    def windows(self, places, *, destination: str):
        """`WF-047`. One call for many places, keyed by index."""

        self.calls += 1
        for item in places:
            self.asked.append(item["name"])
        if self.fail:
            raise ProviderUnavailable("Model returned HTTP 429")
        if not self.answer.get("known"):
            return {}
        return {index: dict(self.answer) for index in range(len(places))}


def build(
    directory: str, filename: str, *, mode: str, provider, hours=None
) -> tuple[PlannerActions, str]:
    actions = PlannerActions(
        Path(directory) / filename,
        place_provider=FakePlaceProvider(),
        opening_window_provider=provider,
        hours_provider=hours,
    )
    trip = actions.create_trip(name="Taipei", destination="Taipei", planning_mode=mode)
    actions.save_setup(
        trip_id=trip.trip_id,
        main_style=["sightseeing"],
        start_date="2030-01-01",
        end_date="2030-01-02",
        accommodation_status="booked",
        confirmed=True,
    )
    actions.discover_places(trip_id=trip.trip_id)
    for item in actions.get_latest_discovery(trip.trip_id).candidates.as_dict()["candidates"]:
        actions.save_candidate_choice(
            trip_id=trip.trip_id, place_id=item["place_id"], action="must_do"
        )
    return actions, trip.trip_id


class AssumedWindowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def opening_facts(self, actions: PlannerActions, trip_id: str) -> list[dict]:
        return [
            f
            for f in actions._optimizer_input(trip_id)["facts"]
            if f.get("fact_type") == "opening_interval"
        ]

    def test_without_a_stored_window_the_constant_is_still_used(self) -> None:
        actions, trip_id = build(
            self.directory.name, "a.sqlite3", mode="explore_first", provider=FakeWindowProvider()
        )

        facts = self.opening_facts(actions, trip_id)

        self.assertTrue(facts)
        for fact in facts:
            self.assertEqual({"start": "09:00", "end": "21:00"}, fact["value"])
            self.assertEqual("explore_first_planning_assumption", fact["source"])

    def test_a_recalled_window_replaces_the_constant_and_stays_assumed(self) -> None:
        """The point is a better guess, not a stronger claim."""

        actions, trip_id = build(
            self.directory.name, "b.sqlite3", mode="explore_first", provider=FakeWindowProvider()
        )

        report = actions.refresh_assumed_windows(trip_id)
        facts = self.opening_facts(actions, trip_id)

        self.assertGreater(report["stored"], 0)
        self.assertEqual(0, report["failed"])
        for fact in facts:
            self.assertEqual({"start": "09:00", "end": "18:00"}, fact["value"])
            # Never upgraded. An assumption that reads as evidence is the whole risk.
            self.assertEqual("assumed", fact["status"])
            self.assertEqual("model_recalled_window:fake-1", fact["source"])

    def test_the_window_is_read_from_storage_and_never_fetched_on_read(self) -> None:
        """`_optimizer_input` runs on every read; a network call there would be a bill."""

        provider = FakeWindowProvider()
        actions, trip_id = build(
            self.directory.name, "c.sqlite3", mode="explore_first", provider=provider
        )
        actions.refresh_assumed_windows(trip_id)
        asked_after_refresh = len(provider.asked)

        for _ in range(3):
            actions._optimizer_input(trip_id)

        self.assertEqual(asked_after_refresh, len(provider.asked))

    def test_a_declined_answer_leaves_the_constant_in_place(self) -> None:
        provider = FakeWindowProvider(answer={"known": False, "model": "fake-1"})
        actions, trip_id = build(
            self.directory.name, "d.sqlite3", mode="explore_first", provider=provider
        )

        report = actions.refresh_assumed_windows(trip_id)

        self.assertEqual(0, report["stored"])
        self.assertGreater(report["model_declined"], 0)
        for fact in self.opening_facts(actions, trip_id):
            self.assertEqual({"start": "09:00", "end": "21:00"}, fact["value"])

    def test_a_ready_to_schedule_trip_refuses_rather_than_spending(self) -> None:
        provider = FakeWindowProvider()
        actions, trip_id = build(
            self.directory.name, "e.sqlite3", mode="ready_to_schedule", provider=provider
        )

        with self.assertRaises(PlannerRefusal) as caught:
            actions.refresh_assumed_windows(trip_id)

        self.assertEqual("assumptions_not_used_by_this_trip", caught.exception.code)
        self.assertEqual([], provider.asked)

    def test_a_place_with_verified_hours_is_never_asked_about(self) -> None:
        """The money-saver and the honesty rule in one. There is nothing an assumption
        can add to evidence, and asking would invite comparing them as equals."""

        provider = FakeWindowProvider()
        actions, trip_id = build(
            self.directory.name,
            "verified.sqlite3",
            mode="explore_first",
            provider=provider,
            hours=FakeHoursProvider(),
        )
        actions.refresh_opening_hours(trip_id)
        verified = [
            f["subject_id"]
            for f in self.opening_facts(actions, trip_id)
            if f["status"] == "verified"
        ]
        self.assertTrue(verified, "fixture must produce verified hours to test the skip")

        report = actions.refresh_assumed_windows(trip_id)

        self.assertEqual([], provider.asked)
        self.assertEqual(0, report["asked"])
        self.assertEqual(len(verified), report["skipped_verified_or_held"])
        # And the verified facts are untouched: still evidence, not an assumption.
        for fact in self.opening_facts(actions, trip_id):
            self.assertEqual("verified", fact["status"])

    def test_the_preflight_prices_both_paths_and_shows_the_batching(self) -> None:
        """`WF-047`. The owner asked for a rule that switches when Google gets expensive.
        The trade is reported rather than taken, because the two are not the same kind of
        thing -- and after batching the money is no longer the interesting part."""

        provider = FakeWindowProvider()
        actions, trip_id = build(
            self.directory.name, "pre.sqlite3", mode="explore_first", provider=provider
        )

        options = actions.opening_evidence_options(trip_id)

        self.assertEqual(3, options["needing_hours"])
        self.assertEqual(0, options["with_verified_hours"])
        # Google: one query per place, and it cannot be batched.
        self.assertEqual(3, options["verified"]["calls"])
        self.assertFalse(options["verified"]["batchable"])
        self.assertEqual("verified", options["verified"]["status"])
        # The model: one request for all three.
        self.assertEqual(1, options["assumed"]["calls"])
        self.assertTrue(options["assumed"]["batchable"])
        self.assertEqual("assumed", options["assumed"]["status"])
        self.assertLess(options["assumed"]["estimate_usd"], options["verified"]["estimate_usd"])
        # The error rate travels with the price, so the cheap option is never chosen
        # without it in view.
        self.assertEqual(1, options["assumed"]["measured"]["ends_after_real_closing"])
        self.assertTrue(options["assumed_is_usable"])

    def test_the_preflight_says_an_assumption_is_unusable_when_it_would_be(self) -> None:
        """A `ready_to_schedule` trip never reads an assumed fact, so offering the cheap
        path there would be selling something that does nothing."""

        actions, trip_id = build(
            self.directory.name,
            "ready.sqlite3",
            mode="ready_to_schedule",
            provider=FakeWindowProvider(),
        )

        self.assertFalse(actions.opening_evidence_options(trip_id)["assumed_is_usable"])

    def test_the_preflight_stops_counting_places_already_covered(self) -> None:
        provider = FakeWindowProvider()
        actions, trip_id = build(
            self.directory.name, "covered.sqlite3", mode="explore_first", provider=provider
        )
        before = actions.opening_evidence_options(trip_id)

        actions.refresh_assumed_windows(trip_id)
        after = actions.opening_evidence_options(trip_id)

        self.assertEqual(0, before["already_assumed"])
        self.assertEqual(before["needing_hours"], after["already_assumed"])
        # Still needing *verified* hours: an assumption does not satisfy that.
        self.assertEqual(before["needing_hours"], after["needing_hours"])

    def test_the_ledger_is_charged_per_call_not_per_place(self) -> None:
        """`WF-047`. This is the whole saving, so it is pinned.

        Verified hours cost US$0.025 *each* and cannot be batched -- Google's Text Search
        takes one query per place -- so the assumption has to be charged per request or the
        comparison an owner is offered is wrong.
        """

        provider = FakeWindowProvider()
        actions, trip_id = build(
            self.directory.name, "f.sqlite3", mode="explore_first", provider=provider
        )

        report = actions.refresh_assumed_windows(trip_id)
        status = actions.paid_usage_status()

        self.assertGreater(report["asked"], 1, "fixture must have several places")
        self.assertEqual(1, provider.calls, "one request for the whole chunk")
        self.assertEqual(
            1, status["by_operation"]["openai:opening_window"]["requests"]
        )

    def test_a_trip_larger_than_one_chunk_makes_one_call_per_chunk(self) -> None:
        provider = FakeWindowProvider()
        provider.BATCH_SIZE = 2
        actions, trip_id = build(
            self.directory.name, "chunks.sqlite3", mode="explore_first", provider=provider
        )

        report = actions.refresh_assumed_windows(trip_id)

        # Three fake places at a chunk size of two: two requests, not three.
        self.assertEqual(3, report["asked"])
        self.assertEqual(2, provider.calls)

    def test_a_second_run_does_not_re_ask(self) -> None:
        provider = FakeWindowProvider()
        actions, trip_id = build(
            self.directory.name, "g.sqlite3", mode="explore_first", provider=provider
        )
        actions.refresh_assumed_windows(trip_id)
        first = len(provider.asked)

        again = actions.refresh_assumed_windows(trip_id)

        self.assertEqual(first, len(provider.asked))
        self.assertEqual(0, again["asked"])
        self.assertGreater(again["skipped_verified_or_held"], 0)

    def test_a_failing_model_leaves_every_fact_untouched(self) -> None:
        actions, trip_id = build(
            self.directory.name,
            "h.sqlite3",
            mode="explore_first",
            provider=FakeWindowProvider(fail=True),
        )

        report = actions.refresh_assumed_windows(trip_id)

        self.assertEqual(0, report["stored"])
        self.assertGreater(report["failed"], 0)
        for fact in self.opening_facts(actions, trip_id):
            self.assertEqual({"start": "09:00", "end": "21:00"}, fact["value"])


if __name__ == "__main__":
    unittest.main()
