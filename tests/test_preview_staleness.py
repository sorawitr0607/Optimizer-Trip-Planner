"""A preview goes stale when the plan changes, not when evidence is re-read.

`activate_plan_preview` compared a digest of the whole optimizer input, and that
input carries `retrieved_at` on every provider-sourced fact. The free build path
refreshes opening hours and routes, each write stamps a new time, and so a preview
built seconds earlier refused as `preview_stale` with an empty detail -- reported as
"it always says stale", which was accurate and impossible to act on.

The guard still has to bite. These check both directions: provenance is ignored, and
anything that could move a stop is not.

**Every test below the digest ones is here because the digest ones were not enough.**
They exercise `_plan_digest` on synthetic dicts, and the real defect was in what the two
real `_optimizer_input` calls disagreed about -- which no unit test of the comparison
function can reach, and which the one end-to-end activation test could not either,
because it patches `_optimizer_input` to return the same snapshot twice.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from travel_planner.actions import (
    PlannerActions,
    PlannerRefusal,
    _changed_sections,
    _plan_digest,
    _without_volatile,
)


def _input(*, start: str = "09:00", fetched: str = "2026-08-20T04:36:22", places=("a",)):
    return {
        "facts": [
            {
                "subject_id": place,
                "fact_type": "opening_interval",
                "value": {"start": start, "end": "18:00"},
                "retrieved_at": fetched,
                "expires_at": "2026-09-20T00:00:00",
            }
            for place in places
        ],
        "thresholds": {"walking_minutes_per_leg": 25},
        "trip": {"usable_windows": [{"start": "08:00", "end": "20:00"}]},
    }


class PlanDigestTest(unittest.TestCase):
    def test_re_reading_the_same_evidence_is_not_a_change(self):
        self.assertEqual(
            _plan_digest(_input(fetched="2026-08-20T04:36:22")),
            _plan_digest(_input(fetched="2026-08-20T05:11:03")),
        )

    def test_a_moved_window_is_a_change(self):
        self.assertNotEqual(_plan_digest(_input(start="09:00")), _plan_digest(_input(start="10:00")))

    def test_an_added_place_is_a_change(self):
        self.assertNotEqual(
            _plan_digest(_input(places=("a",))), _plan_digest(_input(places=("a", "b")))
        )

    def test_a_changed_threshold_is_a_change(self):
        tighter = _input()
        tighter["thresholds"] = {"walking_minutes_per_leg": 15}
        self.assertNotEqual(_plan_digest(_input()), _plan_digest(tighter))

    def test_a_changed_trip_window_is_a_change(self):
        later = _input()
        later["trip"] = {"usable_windows": [{"start": "10:00", "end": "20:00"}]}
        self.assertNotEqual(_plan_digest(_input()), _plan_digest(later))

    def test_provenance_is_stripped_at_every_depth(self):
        stripped = _without_volatile(_input())
        self.assertNotIn("retrieved_at", stripped["facts"][0])
        self.assertNotIn("expires_at", stripped["facts"][0])
        # And nothing else went with it.
        self.assertEqual({"start": "09:00", "end": "18:00"}, stripped["facts"][0]["value"])
        self.assertEqual("opening_interval", stripped["facts"][0]["fact_type"])

    def test_the_refusal_can_name_what_moved(self):
        self.assertEqual({"facts"}, _changed_sections(_input(), _input(start="10:00")))
        self.assertEqual(set(), _changed_sections(_input(), _input(fetched="2026-08-21T00:00:00")))


class ProvisionalActivationTest(unittest.TestCase):
    """Build a preview the real way and activate it the real way.

    The defect this covers: `resolve_default_terminal` was called only by the browser,
    from three separate `/optimize` mutations, one of which swallows its failure. So a
    build could freeze `trip.terminal: None`, a later visit could resolve the airport,
    and activation compared the two inputs and refused `preview_stale` with
    `changed=['trip']` -- reported as "after click this button got warning the plan
    preview is stale, I don't know happen". Confirmed against production: the Porto
    preview built 2026-09-02T06:56 held `terminal: None` against a live input carrying a
    resolved airport.

    `generate_plan_preview` resolves it before freezing now, so the freeze and the
    resolve are one operation rather than two a client is trusted to order. **The
    terminal is deliberately not excluded from the digest** -- it puts real arrival and
    departure rows on the plan, so a genuine change to it must still invalidate a
    preview.
    """

    def _trip(self, directory, *, terminal: bool):
        from tests.test_setup_discovery import FakePlaceProvider
        from tests.test_opening import TRIP_DATES, FakeHoursProvider
        from tests.test_routes import FakeRouteProvider, FakeTimeZoneProvider

        class TerminalProvider(FakePlaceProvider):
            """Answers the airport query the way Nominatim does, near the destination."""

            def geocode(self, query: str):
                if "airport" in query:
                    if not terminal:
                        from travel_planner.providers import ProviderUnavailable

                        raise ProviderUnavailable("geocoder declined")
                    return {
                        "address": "Taipei Songshan Airport",
                        "latitude": 25.0665,
                        "longitude": 121.5549,
                        "provider": self.name,
                    }
                return super().geocode(query)

        actions = PlannerActions(
            Path(directory) / "activate.sqlite3",
            place_provider=TerminalProvider(),
            hours_provider=FakeHoursProvider(),
        )
        trip = actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="explore_first"
        )
        actions.save_setup(
            trip_id=trip.trip_id,
            main_style=["sightseeing"],
            start_date=TRIP_DATES[0],
            end_date=TRIP_DATES[-1],
            accommodation_status="not_booked",
            confirmed=True,
        )
        actions.discover_places(trip_id=trip.trip_id)
        for item in actions.get_latest_discovery(trip.trip_id).candidates.as_dict()[
            "candidates"
        ]:
            actions.save_candidate_choice(
                trip_id=trip.trip_id, place_id=item["place_id"], action="must_do"
            )
        actions.refresh_opening_hours(trip.trip_id)
        actions.route_provider = FakeRouteProvider()
        actions.refresh_routes(trip.trip_id)
        actions.timezone_provider = FakeTimeZoneProvider()
        actions.refresh_timezone(trip.trip_id)
        return actions, trip

    def _activate(self, actions, trip):
        preview = actions.get_plan_preview(trip.trip_id)
        provisional = [
            item
            for item in preview.proposal.as_dict()["variants"]
            if item["status"] == "provisional"
        ]
        self.assertTrue(provisional, "no provisional variant to activate")
        return actions.activate_plan_preview(
            trip_id=trip.trip_id, variant_id=provisional[0]["variant_id"]
        )

    def test_a_preview_activates_without_the_browser_resolving_the_terminal(self):
        """The reported failure. Nothing here calls `resolve_default_terminal`."""

        with TemporaryDirectory() as directory:
            actions, trip = self._trip(directory, terminal=True)
            actions.generate_plan_preview(trip.trip_id)

            # The build resolved it itself, which is the fix.
            self.assertIsNotNone(actions.store.get_trip_evidence(trip.trip_id, "default_terminal"))
            frozen = actions.get_plan_preview(trip.trip_id).optimizer_input.as_dict()
            self.assertIsNotNone(frozen["trip"].get("terminal"))

            version = self._activate(actions, trip)
            self.assertEqual(version, actions.get_active_plan(trip.trip_id))

    def test_a_geocoder_that_will_not_answer_does_not_block_activation(self):
        """Best-effort, both times. A terminal that cannot be resolved stays absent in
        the freeze *and* in the activation, so the two still agree."""

        with TemporaryDirectory() as directory:
            actions, trip = self._trip(directory, terminal=False)
            actions.generate_plan_preview(trip.trip_id)

            frozen = actions.get_plan_preview(trip.trip_id).optimizer_input.as_dict()
            # `_optimizer_input` omits the key rather than writing None, so absent is
            # the shape both sides see and the digest stays consistent.
            self.assertIsNone(frozen["trip"].get("terminal"))

            version = self._activate(actions, trip)
            self.assertEqual(version, actions.get_active_plan(trip.trip_id))

    def test_the_guard_still_refuses_when_the_owner_changes_the_plan(self):
        """The fix must not have disarmed the thing it lives inside."""

        with TemporaryDirectory() as directory:
            actions, trip = self._trip(directory, terminal=True)
            actions.generate_plan_preview(trip.trip_id)

            # A real change to the plan: drop a chosen place.
            kept = actions.store.list_candidate_actions(trip.trip_id)
            actions.save_candidate_choice(
                trip_id=trip.trip_id,
                place_id=kept[0]["place_id"],
                action="not_for_trip",
                reason=None,
            )

            with self.assertRaises(PlannerRefusal) as caught:
                self._activate(actions, trip)
            self.assertEqual("preview_stale", caught.exception.code)
            self.assertIn("candidates", caught.exception.detail["changed"])


if __name__ == "__main__":
    unittest.main()
