from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


from travel_planner.actions import MAX_ROUTE_REQUESTS, PlannerActions
from travel_planner.providers import (
    GoogleTimeZoneProvider,
    OpenRouteServiceMatrixProvider,
    OpenRouteServiceProvider,
    ProviderBudgetExceeded,
    ProviderUnavailable,
    WikidataSummaryProvider,
    photo_depicts_place,
)


class FakeRouteProvider:
    """Stands in for OpenRouteService; tests never touch the network."""

    name = "openrouteservice"
    operation = "openrouteservice:directions"
    cache_ttl_days = 14
    mode = "walk"

    def __init__(self, *, fail_for: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_for = fail_for or set()

    def route(self, origin: dict, destination: dict) -> dict:
        self.calls.append((origin["place_id"], destination["place_id"]))
        if destination["place_id"] in self.fail_for:
            raise ProviderUnavailable("OpenRouteService returned HTTP 503")
        return {
            "origin_id": origin["place_id"],
            "destination_id": destination["place_id"],
            "mode": "walk",
            "duration_minutes": 12,
            "walking_minutes": 12,
            "distance_m": 900,
            "transfers": 0,
            "boarding_buffer_minutes": 0,
            "experience_evidence": [],
            "status": "verified",
            "provider": "openrouteservice",
        }


class FakeMatrixProvider:
    """Every pair at once, the way OpenRouteService's matrix endpoint answers."""

    name = "openrouteservice_matrix"
    operation = "openrouteservice:matrix"
    cache_ttl_days = 14
    mode = "walk"
    MAX_LOCATIONS = 50

    def __init__(self, *, unavailable: bool = False) -> None:
        self.calls = 0
        self.unavailable = unavailable

    def covers(self, points: list[dict]) -> bool:
        return 2 <= len(points) <= self.MAX_LOCATIONS

    def matrix(self, points: list[dict]) -> list[dict]:
        self.calls += 1
        if self.unavailable:
            raise ProviderUnavailable("OpenRouteService is unreachable: URLError")
        return [
            {
                "origin_id": origin["place_id"],
                "destination_id": destination["place_id"],
                "mode": "walk",
                "duration_minutes": 9,
                "walking_minutes": 9,
                "distance_m": 700,
                "geometry": [],
                "transfers": 0,
                "boarding_buffer_minutes": 0,
                "experience_evidence": [],
                "status": "verified",
                "provider": self.name,
            }
            for origin in points
            for destination in points
            if origin["place_id"] != destination["place_id"]
        ]


class FakePlaceProvider:
    name = "fake_places"
    cache_ttl_days = 7

    def cache_descriptor(self, destination: str) -> dict:
        return {"provider": self.name, "destination": destination.casefold()}

    def discover(self, destination: str) -> dict:
        return {
            "items": [
                {
                    "provider_place_id": f"node/{index}",
                    "name": name,
                    "names": {"en": name},
                    "latitude": 25.03 + index / 100,
                    "longitude": 121.56 + index / 100,
                    "category": "viewpoint",
                    "opening_hours": "08:00-20:00",
                    "source_url": f"https://example.test/{index}",
                }
                for index, name in enumerate(("Tower", "Temple", "Market"), start=1)
            ],
            "coverage": {"bbox": [24.9, 121.4, 25.2, 121.7], "known_gaps": []},
            "attribution": "Fake",
        }


class NormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OpenRouteServiceProvider()
        self.origin = {"place_id": "a", "latitude": 25.0330, "longitude": 121.5654}
        self.destination = {"place_id": "b", "latitude": 25.0375, "longitude": 121.5600}

    def test_seconds_and_metres_become_planner_units(self) -> None:
        route = self.provider.normalize(
            {"features": [{"properties": {"summary": {"duration": 612.4, "distance": 842.7}}}]},
            origin=self.origin,
            destination=self.destination,
        )
        self.assertEqual(11, route["duration_minutes"])
        self.assertEqual(11, route["walking_minutes"])
        self.assertEqual(843, route["distance_m"])
        self.assertEqual("walk", route["mode"])
        self.assertEqual("verified", route["status"])
        # A machine-generated foot route is a plain transfer, not a rewarding walk.
        self.assertEqual([], route["experience_evidence"])

    def test_a_sub_minute_route_never_rounds_to_zero(self) -> None:
        route = self.provider.normalize(
            {"features": [{"properties": {"summary": {"duration": 20, "distance": 25}}}]},
            origin=self.origin,
            destination=self.destination,
        )
        self.assertEqual(1, route["duration_minutes"])

    def test_an_incomplete_payload_is_refused_rather_than_defaulted(self) -> None:
        for payload in (
            {"features": []},
            {},
            {"features": [{"properties": {}}]},
            {"features": [{"properties": {"summary": {"duration": 60}}}]},
        ):
            with self.assertRaises(ProviderUnavailable):
                self.provider.normalize(
                    payload, origin=self.origin, destination=self.destination
                )

    def test_a_missing_key_is_reported_without_calling_out(self) -> None:
        with patch.dict(os.environ, {"OPENROUTESERVICE_API_KEY": ""}):
            with self.assertRaisesRegex(ProviderUnavailable, "not configured"):
                self.provider.route(self.origin, self.destination)


class MatrixNormalizationTest(unittest.TestCase):
    """What the matrix endpoint really returns, and what must never be invented from it.

    Checked against the live endpoint while this was written: 23 points, 506 pairs, one
    request, 1.59 seconds. These pin the awkward shapes that probe cannot produce on
    demand.
    """

    def setUp(self) -> None:
        self.provider = OpenRouteServiceMatrixProvider()
        self.points = [
            {"place_id": name, "latitude": 25.0, "longitude": 121.5}
            for name in ("a", "b", "c")
        ]

    def test_a_null_cell_is_skipped_rather_than_defaulted(self) -> None:
        """`null` is the router saying it could not walk that pair — an island, a point
        it could not snap to a path. A fabricated duration is exactly what
        `ROUTE_UNVERIFIED` exists to stop the optimizer scheduling against."""

        routes = self.provider.normalize(
            {"durations": [[0, 60, None], [60, 0, 60], [None, 60, 0]]},
            points=self.points,
        )

        self.assertEqual(4, len(routes))
        self.assertNotIn(("a", "c"), [(r["origin_id"], r["destination_id"]) for r in routes])

    def test_a_missing_distance_costs_the_metres_and_not_the_route(self) -> None:
        routes = self.provider.normalize(
            {"durations": [[0, 60, 60], [60, 0, 60], [60, 60, 0]]}, points=self.points
        )

        self.assertEqual(6, len(routes))
        self.assertEqual({0}, {route["distance_m"] for route in routes})

    def test_a_sub_minute_pair_never_rounds_to_zero(self) -> None:
        """The same floor the directions path applies: a zero-minute leg reads as
        teleportation to the scheduler."""

        routes = self.provider.normalize(
            {"durations": [[0, 20], [20, 0]]}, points=self.points[:2]
        )

        self.assertEqual({1}, {route["duration_minutes"] for route in routes})

    def test_a_matrix_carries_no_path_and_says_so(self) -> None:
        routes = self.provider.normalize(
            {"durations": [[0, 60], [60, 0]]}, points=self.points[:2]
        )

        for route in routes:
            self.assertEqual([], route["geometry"])
            # Still `verified` — the router measured this walk, it just did not draw it.
            self.assertEqual("verified", route["status"])
            self.assertEqual("openrouteservice_matrix", route["provider"])

    def test_an_unusable_payload_is_refused_rather_than_defaulted(self) -> None:
        for payload in ({}, {"durations": [[0, 1]]}, {"durations": "no"}):
            with self.assertRaises(ProviderUnavailable):
                self.provider.normalize(payload, points=self.points)
        # A matrix where nothing at all could be measured is a refusal too, not an
        # empty success -- the caller would read zero stored as "already covered".
        with self.assertRaises(ProviderUnavailable):
            self.provider.normalize(
                {"durations": [[0, None], [None, 0]]}, points=self.points[:2]
            )

    def test_a_trip_too_large_for_one_request_is_declined_before_it_is_sent(self) -> None:
        """`covers` is what keeps the seed from becoming its own failure mode: past the
        endpoint's ceiling the directions sweep simply does the work as it always did."""

        many = [
            {"place_id": f"p{index}", "latitude": 25.0, "longitude": 121.5}
            for index in range(self.provider.MAX_LOCATIONS + 1)
        ]

        self.assertTrue(self.provider.covers(self.points))
        self.assertFalse(self.provider.covers(many))
        self.assertFalse(self.provider.covers(self.points[:1]))


class RouteRefreshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "routes.sqlite3"
        self.provider = FakeRouteProvider()
        self.actions = PlannerActions(
            self.path,
            place_provider=FakePlaceProvider(),
            route_provider=self.provider,
        )
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="ready_to_schedule"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date="2030-01-01",
            end_date="2030-01-03",
            accommodation_status="booked",
            confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        self.places = [
            item["place_id"]
            for item in self.actions.get_latest_discovery(
                self.trip.trip_id
            ).candidates.as_dict()["candidates"]
        ]
        for place_id in self.places:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=place_id, action="must_do"
            )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_both_directions_are_fetched_for_every_selected_pair(self) -> None:
        report = self.actions.refresh_routes(self.trip.trip_id)
        count = len(self.places)

        self.assertEqual(count, report["places"])
        self.assertEqual(count * (count - 1), report["pairs_needed"])
        self.assertEqual(report["pairs_needed"], report["fetched"])
        self.assertEqual(0, report["skipped_over_cap"])
        self.assertEqual(0, report["failed"])
        # Direction matters: the optimizer asks for a specific leg.
        self.assertIn((self.places[0], self.places[1]), self.provider.calls)
        self.assertIn((self.places[1], self.places[0]), self.provider.calls)

    def test_a_second_refresh_reads_the_cache_and_makes_no_call(self) -> None:
        self.actions.refresh_routes(self.trip.trip_id)
        calls_after_first = len(self.provider.calls)

        again = self.actions.refresh_routes(self.trip.trip_id)

        self.assertEqual(calls_after_first, len(self.provider.calls))
        self.assertEqual(0, again["fetched"])
        self.assertEqual(again["pairs_needed"], again["from_cache"])

        forced = self.actions.refresh_routes(self.trip.trip_id, force=True)
        self.assertEqual(forced["pairs_needed"], forced["fetched"])

    def test_free_tier_calls_are_counted_in_the_ledger(self) -> None:
        report = self.actions.refresh_routes(self.trip.trip_id)
        status = self.actions.paid_usage_status()
        bucket = status["by_operation"]["openrouteservice:directions"]

        self.assertEqual(report["fetched"], bucket["requests"])
        self.assertEqual(0.0, bucket["estimated_usd"])
        self.assertEqual(0.0, status["estimated_usd"])

    def test_a_provider_outage_leaves_the_other_legs_usable(self) -> None:
        actions = PlannerActions(
            self.path, route_provider=FakeRouteProvider(fail_for={self.places[2]})
        )
        report = actions.refresh_routes(self.trip.trip_id)

        self.assertGreater(report["fetched"], 0)
        self.assertEqual(2, report["failed"])
        self.assertIn("HTTP 503", report["provider_errors"][0])
        stored = {
            (route["origin_id"], route["destination_id"])
            for route in actions.list_routes(self.trip.trip_id)
        }
        self.assertNotIn((self.places[0], self.places[2]), stored)
        self.assertIn((self.places[0], self.places[1]), stored)

    def test_the_request_cap_reports_what_it_skipped(self) -> None:
        with patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 2):
            report = self.actions.refresh_routes(self.trip.trip_id)

        self.assertEqual(2, report["fetched"])
        self.assertEqual(report["pairs_needed"] - 2, report["skipped_over_cap"])
        self.assertEqual(2, report["request_cap"])

    def test_one_sweep_makes_every_pass_the_browser_used_to_make(self) -> None:
        """The passes moved to the server; the work and the spending did not.

        Each pass was an RPC, and on the deployment an RPC for slow work is a queued
        job — enqueue, poll at 1.5s, wait to be claimed, poll again. Twelve of those
        is minutes of round-trip before a single route is fetched, and it was the
        bulk of a ten-minute build. Looping here costs one job instead of twelve.
        """

        reached: list[int] = []
        with patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 2):
            single = self.actions.refresh_routes(self.trip.trip_id)
            sweep = self.actions.refresh_routes(
                self.trip.trip_id, max_passes=12, progress=reached.append
            )

        # One pass still means one pass, which is what every other caller asks for.
        self.assertEqual(2, single["fetched"])
        # The sweep finished the trip rather than stopping at the per-pass cap, and
        # said so pass by pass rather than only at the end.
        self.assertEqual(single["pairs_needed"] - 2, sweep["fetched"])
        self.assertEqual(0, sweep["skipped_over_cap"])
        self.assertGreater(sweep["passes_run"], 1)
        self.assertEqual(sweep["fetched"], reached[-1])
        self.assertEqual(sorted(reached), reached, "the count may only go up")

    def test_a_sweep_hands_the_worker_back_before_it_starves_the_queue(self) -> None:
        """One worker runs one job, so a long job is a queue-wide outage.

        Measured on the deployment: an 843-second sweep left `generate_plan_preview` —
        three seconds of work — waiting 482 seconds to be claimed, and the browser
        reported `job_timeout` on a build that had not started. Discovery waited 885.
        The sweep stops on its own clock and says what is left.
        """

        with patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 1), patch(
            "travel_planner.actions.ROUTE_SWEEP_SECONDS", 0.0
        ):
            stopped = self.actions.refresh_routes(self.trip.trip_id, max_passes=12)

        # A zero budget still does one pass -- the deadline is checked between passes,
        # so the job always makes progress rather than returning empty-handed.
        self.assertEqual(1, stopped["passes_run"])
        self.assertEqual(1, stopped["fetched"])
        # And it reports that asking again is worth doing.
        self.assertTrue(stopped["more_pairs"])

    def test_a_finished_sweep_does_not_ask_the_caller_to_come_back(self) -> None:
        with patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 2):
            done = self.actions.refresh_routes(self.trip.trip_id, max_passes=12)

        self.assertEqual(0, done["skipped_over_cap"])
        self.assertFalse(done["more_pairs"])

    def test_a_sweep_stops_rather_than_re_buying_what_force_already_bought(self) -> None:
        """`force` refetches cached pairs, so the pass list never shrinks.

        Looping on that would buy the same routes every pass until the ceiling — real
        money against a US$10 monthly cap, for nothing. One pass is the only honest
        reading of `force` here.
        """

        with patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 2):
            forced = self.actions.refresh_routes(
                self.trip.trip_id, force=True, max_passes=12
            )

        self.assertEqual(1, forced["passes_run"])
        self.assertEqual(2, forced["fetched"])

    def test_the_cap_limits_one_run_and_not_what_a_trip_can_ever_know(self) -> None:
        """Repeated runs must reach pairs beyond the cap.

        The cache check used to sit inside the fetch loop while the cap sliced a
        fixed sort of *all* pairs, so every run attempted the same first N and the
        N+1th pair was unreachable however many times this ran. On the real Taipei
        trip that pinned route coverage at 60 of 1640 pairs and left every plan
        variant `unavailable` for want of evidence.
        """

        with patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 2):
            first = self.actions.refresh_routes(self.trip.trip_id)
            second = self.actions.refresh_routes(self.trip.trip_id)
            third = self.actions.refresh_routes(self.trip.trip_id)

        self.assertEqual(2, first["fetched"])
        # The point: the later runs fetch *new* pairs rather than re-reporting the
        # first two as cached.
        self.assertEqual(2, second["fetched"])
        self.assertEqual(0, second["from_cache"])
        self.assertEqual(first["pairs_needed"] - 2, second["pairs_needed"])
        stored = {
            (route["origin_id"], route["destination_id"])
            for route in self.actions.list_routes(self.trip.trip_id)
        }
        self.assertEqual(6, len(stored))
        self.assertEqual(third["pairs_needed"] - 2, third["skipped_over_cap"])

    def test_the_cap_spends_itself_on_the_nearest_pairs_first(self) -> None:
        """Under the cap, the pairs most likely to be walked must win.

        Ordering by `place_id` spent 340 free calls on arbitrary pairs of the real
        Taipei trip while every pair the plan actually used stayed unmeasured. A
        missing route falls back to a pessimistic estimate, so the plan showed
        68-minute walks between places a kilometre apart and failed validation on
        them; fetching the same pairs by proximity turned those legs into 14, 10
        and 9 minutes.
        """

        from travel_planner.ranking import _distance_metres

        located = self.actions._route_points(self.trip.trip_id)
        with patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 2):
            self.actions.refresh_routes(self.trip.trip_id)

        by_id = {point["place_id"]: point for point in located}
        fetched = [
            _distance_metres(by_id[route["origin_id"]], by_id[route["destination_id"]])
            for route in self.actions.list_routes(self.trip.trip_id)
        ]
        every_pair = [
            _distance_metres(left, right)
            for left in located
            for right in located
            if left["place_id"] != right["place_id"]
        ]
        # Both fetched legs are among the closest pairs available, not simply the
        # first two by identifier.
        self.assertEqual(2, len(fetched))
        self.assertLessEqual(max(fetched), sorted(every_pair)[1])

    def test_one_pass_reaches_every_place_before_it_refines_any(self) -> None:
        """Coverage is what the cap must buy first, and it must buy it in one pass.

        `served` was read once from the stored routes, so on a trip's first sweep the
        flag was `False` for every pair and the order collapsed to pure nearest-first.
        Four places in one district and one on the edge of the city therefore spend the
        whole cap downtown, and the outlier waits for a *later* sweep to be seen as
        starved. Measured on the owner's Tokyo trip, that cost one extra sweep of ~128
        seconds: burst one reached 22 of 23 places, burst two the last. The other eight
        sweeps of that twenty-minute build were the loop's stop condition, not this.

        The cap here is eight requests against twenty ordered pairs: exactly enough to
        reach all five places both ways -- four promotions of two directions each --
        and nowhere near enough to measure them all.
        """

        cluster = [
            {"place_id": f"near_{index}", "latitude": 25.03 + index / 10_000,
             "longitude": 121.56 + index / 10_000}
            for index in range(4)
        ]
        outlier = {"place_id": "far", "latitude": 25.21, "longitude": 121.72}
        points = cluster + [outlier]

        with patch.object(self.actions, "_route_points", return_value=points), \
                patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 8):
            report = self.actions.refresh_routes(self.trip.trip_id)

        reached = {place_id for call in self.provider.calls for place_id in call}
        self.assertEqual({point["place_id"] for point in points}, reached)
        # The far place is measured in *both* directions, because `_best_route` reads a
        # stored leg one way only — arriving somewhere the plan cannot leave is still a
        # broken segment.
        self.assertIn("far", [origin for origin, _ in self.provider.calls])
        self.assertIn("far", [destination for _, destination in self.provider.calls])
        # And the sweep says the plan is unblocked while plenty of pairs remain, which is
        # the pair of facts `collectRouteEvidence` stops on.
        self.assertEqual(0, report["places_unserved"])
        self.assertGreater(report["skipped_over_cap"], 0)

    def test_one_matrix_request_measures_every_pair_and_unblocks_the_plan(self) -> None:
        """The twenty-minute build, answered in one request.

        The directions endpoint takes one call per ordered pair at ~2.1s each, so the
        owner's Tokyo trip spent nine queued jobs and 1200 seconds on 554 of its 506
        pairs. The matrix endpoint measures them all at once, and coverage is what the
        browser's loop stops on -- so the plan is buildable before the drawn lines are.
        """

        matrix = FakeMatrixProvider()
        self.actions.matrix_provider = matrix
        count = len(self.places)

        report = self.actions.refresh_routes(self.trip.trip_id)

        self.assertEqual(1, matrix.calls)
        self.assertEqual(count * (count - 1), report["seeded_from_matrix"])
        # Nobody is left ROUTE_UNVERIFIED, which is the fact `collectRouteEvidence` stops
        # on, and it cost one request rather than one per pair.
        self.assertEqual(0, report["places_unserved"])
        self.assertEqual(count * (count - 1), len(self.actions.list_routes(self.trip.trip_id)))

    def test_the_directions_sweep_upgrades_a_matrix_row_to_a_drawn_line(self) -> None:
        """A matrix row is a time with no path, so it is fresh and still upgradeable.

        Treating it as cached would seed every pair once and leave the map drawing
        straight lines for ever; treating a *drawn* route that way is correct, and
        `test_a_second_refresh_reads_the_cache_and_makes_no_call` pins that half.
        """

        matrix = FakeMatrixProvider()
        self.actions.matrix_provider = matrix
        # Two requests a pass against six pairs, so the upgrade takes three sweeps and
        # can be watched happening rather than completing inside the seeding call.
        with patch("travel_planner.actions.MAX_ROUTE_REQUESTS", 2):
            first = self.actions.refresh_routes(self.trip.trip_id)
            self.assertEqual(6, first["seeded_from_matrix"])
            self.assertEqual(2, len(self.provider.calls))

            second = self.actions.refresh_routes(self.trip.trip_id)
            # Nothing left to seed; every later sweep is the directions endpoint
            # replacing matrix rows with real paths, two at a time.
            self.assertEqual(1, matrix.calls)
            self.assertEqual(0, second["seeded_from_matrix"])
            self.assertEqual(4, len(self.provider.calls))

            self.actions.refresh_routes(self.trip.trip_id)
            self.assertEqual(6, len(self.provider.calls))
            # And once every pair carries a drawn line they are genuinely cached.
            self.actions.refresh_routes(self.trip.trip_id)
            self.assertEqual(6, len(self.provider.calls))

    def test_an_unreachable_matrix_leaves_the_directions_sweep_doing_the_work(self) -> None:
        """Degrade, never refuse: the worst case is the behaviour that came before."""

        matrix = FakeMatrixProvider(unavailable=True)
        self.actions.matrix_provider = matrix

        report = self.actions.refresh_routes(self.trip.trip_id)

        self.assertEqual(1, matrix.calls)
        self.assertEqual(0, report["seeded_from_matrix"])
        self.assertEqual(report["pairs_needed"], report["fetched"])
        self.assertEqual(0, report["places_unserved"])

    def test_the_sweep_clock_stops_a_pass_and_not_only_a_new_pass(self) -> None:
        """`ROUTE_SWEEP_SECONDS` bounded the wrong thing and therefore bounded nothing.

        It was read only where a *new pass* would start, and one pass of sixty at the
        provider's measured ~2.1s a route is about 128 seconds — so the sixty-second
        budget was always already spent by the first check, every job was exactly one
        pass, and the multi-pass sweep it was added to bound never ran a second pass in
        production. Read inside the request loop it does what its docstring says.

        The clock here is a fake that jumps past the deadline after two routes.
        """

        # First call sets the deadline at 0 + 60. The next two are the loop's checks at
        # index 1 and 2, so route 1 and route 2 go out and route 3 finds the clock spent.
        ticks = iter([0.0, 0.0, 0.0])
        with patch("travel_planner.actions.monotonic", lambda: next(ticks, 1e6)):
            report = self.actions.refresh_routes(self.trip.trip_id)

        self.assertEqual(3, len(self.provider.calls))

        # It stopped early, and it did not lie about what is left: the pairs it never
        # asked for come back as outstanding rather than vanishing from the count.
        self.assertLess(len(self.provider.calls), report["pairs_needed"])
        self.assertEqual(
            report["pairs_needed"] - report["fetched"], report["skipped_over_cap"]
        )
        self.assertTrue(report["more_pairs"])

    def test_the_first_request_of_a_pass_always_goes_out(self) -> None:
        """Otherwise a spent clock means a job that claims the worker and does nothing,
        and the caller's loop turns into a spin."""

        # The deadline is set from the first tick and every later read is past it, so
        # only the index-0 request — the one the guard deliberately exempts — goes out.
        ticks = iter([0.0])
        with patch("travel_planner.actions.monotonic", lambda: next(ticks, 1e6)):
            report = self.actions.refresh_routes(self.trip.trip_id)

        self.assertEqual(1, len(self.provider.calls))
        self.assertEqual(1, report["fetched"])

    def test_routing_needs_two_located_places(self) -> None:
        empty = PlannerActions(
            Path(self.directory.name) / "empty.sqlite3", route_provider=self.provider
        )
        trip = empty.create_trip(name="Bare", destination="Osaka")
        with self.assertRaises(ValueError) as raised:
            empty.refresh_routes(trip.trip_id)
        self.assertEqual("insufficient_geocoded_places", str(raised.exception))

    def test_routes_clear_the_capability_gap_and_reach_the_optimizer(self) -> None:
        before = self.actions._optimizer_input(self.trip.trip_id)
        self.assertIn("ROUTE_SNAPSHOT_MISSING", before["trip"]["capability_gaps"])
        self.assertEqual([], before["routes"])

        self.actions.refresh_routes(self.trip.trip_id)
        after = self.actions._optimizer_input(self.trip.trip_id)

        self.assertNotIn("ROUTE_SNAPSHOT_MISSING", after["trip"]["capability_gaps"])
        self.assertEqual(len(self.places) * (len(self.places) - 1), len(after["routes"]))
        self.assertEqual({"verified"}, {route["status"] for route in after["routes"]})
        # The timezone gap is untouched by routing.
        self.assertIn("DESTINATION_TIMEZONE_UNVERIFIED", after["trip"]["capability_gaps"])

    def test_an_expired_route_is_reported_stale_and_stops_counting(self) -> None:
        self.actions.refresh_routes(self.trip.trip_id)
        with self.actions.store.connect() as connection:
            connection.execute(
                "UPDATE route_snapshots SET expires_at = '2000-01-01T00:00:00+00:00'"
            )

        routes = self.actions.list_routes(self.trip.trip_id)
        self.assertEqual({"stale"}, {route["status"] for route in routes})
        gaps = self.actions._optimizer_input(self.trip.trip_id)["trip"]["capability_gaps"]
        self.assertIn("ROUTE_SNAPSHOT_MISSING", gaps)

    def test_a_budget_stop_aborts_routing_rather_than_half_reporting(self) -> None:
        self.actions.record_paid_call(operation="google_places:details", count=600)
        with patch(
            "travel_planner.usage.PRICES_USD",
            {**__import__("travel_planner.usage", fromlist=["PRICES_USD"]).PRICES_USD,
             "openrouteservice:directions": 0.01},
        ):
            with self.assertRaises(ProviderBudgetExceeded):
                self.actions.refresh_routes(self.trip.trip_id)


if __name__ == "__main__":
    unittest.main()


class FakeTimeZoneProvider:
    name = "google_timezone"
    operation = "google_timezone:lookup"
    cache_ttl_days = 180
    kind = "destination_timezone"

    def __init__(self, *, payload: dict | None = None) -> None:
        self.calls: list[tuple[float, float]] = []
        self.payload = payload or {
            "status": "OK",
            "timeZoneId": "Asia/Taipei",
            "timeZoneName": "Taiwan Standard Time",
            "rawOffset": 28800,
            "dstOffset": 0,
        }

    def lookup(self, *, latitude: float, longitude: float, timestamp: int) -> dict:
        self.calls.append((latitude, longitude))
        return GoogleTimeZoneProvider().normalize(
            self.payload, latitude=latitude, longitude=longitude
        )


class TransitRouteTest(unittest.TestCase):
    """`WF-038`: transit legs from a local GTFS feed, no network and no cost."""

    FEED = Path(__file__).resolve().parent / "fixtures" / "synthetic_transit_gtfs.zip"

    def setUp(self) -> None:
        from travel_planner.providers import GtfsTransitProvider

        self.directory = TemporaryDirectory()
        self.actions = PlannerActions(
            Path(self.directory.name) / "transit.sqlite3",
            place_provider=FakePlaceProvider(),
            route_provider=FakeRouteProvider(),
            transit_provider=GtfsTransitProvider(),
        )
        # The provider reads its path at construction, so point it at the fixture.
        self.actions.transit_provider._path = str(self.FEED)
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="ready_to_schedule"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id, main_style=["sightseeing"],
            start_date="2030-01-01", end_date="2030-01-03",
            accommodation_status="booked", confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        # `_route_points` reads *selected* places, so a route pair only exists once
        # a choice does.
        for candidate in self.actions.get_latest_discovery(
            self.trip.trip_id
        ).candidates.as_dict()["candidates"]:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id,
                place_id=candidate["place_id"],
                action="must_do",
            )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_a_transit_leg_reports_only_access_walking(self) -> None:
        """The reason this ticket exists: a long ride with a short walk.

        `maximum_walking_minutes_per_leg` measures `walking_minutes`, so a 40-minute
        ride reached by a 2-minute walk passes a 25-minute walking cap that a
        40-minute walk never could. Without it a city trip cannot validate at all.
        """

        report = self.actions.refresh_transit_routes(self.trip.trip_id)
        self.assertEqual(0, report["failed"], report.get("provider_errors"))
        self.assertGreater(report["fetched"], 0)

        transit = [
            route
            for route in self.actions.list_routes(self.trip.trip_id)
            if route["mode"] == "transit"
        ]
        self.assertTrue(transit)
        longest = max(transit, key=lambda route: route["duration_minutes"])
        self.assertGreater(longest["duration_minutes"], 20)
        self.assertLess(longest["walking_minutes"], 10)
        # Derived from a timetable, not looked up in one.
        self.assertEqual("estimated", longest["status"])
        self.assertEqual("gtfs", longest["provider"])

    def test_transit_is_stored_beside_walking_rather_than_replacing_it(self) -> None:
        """The store keys by (origin, destination, mode), so both survive."""

        self.actions.refresh_routes(self.trip.trip_id)
        self.actions.refresh_transit_routes(self.trip.trip_id)
        modes = {route["mode"] for route in self.actions.list_routes(self.trip.trip_id)}
        self.assertEqual({"walk", "transit"}, modes)

    def test_a_transit_call_is_recorded_at_zero_rather_than_left_unpriced(self) -> None:
        self.actions.refresh_transit_routes(self.trip.trip_id)
        rows = [
            row
            for row in self.actions.store.list_paid_usage()
            if row["operation"] == "gtfs:transit"
        ]
        self.assertTrue(rows)
        self.assertEqual(0.0, sum(float(row["estimated_usd"]) for row in rows))

    def test_an_absent_feed_refuses_and_never_invents_a_journey(self) -> None:
        from travel_planner.providers import GtfsTransitProvider

        self.actions.transit_provider = GtfsTransitProvider()
        self.actions.transit_provider._path = str(
            Path(self.directory.name) / "not-a-feed.zip"
        )
        report = self.actions.refresh_transit_routes(self.trip.trip_id)
        self.assertEqual(0, report["fetched"])
        self.assertTrue(report["provider_errors"])
        self.assertIn("GTFS feed unusable", report["provider_errors"][0])


class OsmMetroTransitTest(unittest.TestCase):
    """`WF-038` fallback: metro topology from OpenStreetMap when no feed exists."""

    # Three stations on one line plus a crossing line, in the same place as the fake
    # discovery provider's Tower / Temple / Market.
    ELEMENTS = [
        # Tagged as real stations would be: the graph rejects untagged nodes, because
        # the Overpass recursion drags in every node of every track way.
        {"type": "node", "id": 1, "lat": 25.0405, "lon": 121.5705,
         "tags": {"name": "Tower", "name:en": "Tower Station",
                  "railway": "station", "station": "subway"}},
        {"type": "node", "id": 2, "lat": 25.0498, "lon": 121.5798,
         "tags": {"name": "Temple", "railway": "station", "station": "subway"}},
        {"type": "node", "id": 3, "lat": 25.0603, "lon": 121.5903,
         "tags": {"name": "Market", "railway": "station", "station": "subway"}},
        # Track geometry that must never become a boarding point.
        {"type": "node", "id": 4, "lat": 25.0450, "lon": 121.5750},
        {
            "type": "relation", "id": 90,
            "tags": {"route": "subway", "ref": "BR"},
            "members": [
                {"type": "node", "ref": 1}, {"type": "node", "ref": 2},
                {"type": "node", "ref": 3},
            ],
        },
    ]

    def graph(self):
        from travel_planner.transit import graph_from_osm

        return graph_from_osm(self.ELEMENTS)

    def test_an_english_station_name_is_carried_beside_the_local_one(self) -> None:
        """OSM tags `name:en` on 370 of Taipei's 437 stop nodes and the graph discarded
        every one, so `WF-040`'s stay areas rendered as 中山 and 西門 with nothing
        readable beside them. Empty rather than duplicated when the tag is absent, so a
        caller can tell "no English name" from "the same name"."""

        stops = self.graph().stops

        self.assertEqual("Tower Station", stops["n1"].name_en)
        self.assertEqual("Tower", stops["n1"].name)
        self.assertEqual("", stops["n2"].name_en)

    def test_a_relation_yields_both_directions(self) -> None:
        """A relation lists one direction; a metro runs both.

        Recording only the stated direction produced a graph where half the network
        was one-way, and journeys back towards the centre simply did not exist.
        """

        graph = self.graph()
        self.assertEqual(3, len(graph.stops))
        self.assertEqual(4, len(graph.edges))
        there = graph.journey(origin=(25.0405, 121.5705), destination=(25.0603, 121.5903))
        back = graph.journey(origin=(25.0603, 121.5903), destination=(25.0405, 121.5705))
        self.assertIsNotNone(there)
        self.assertIsNotNone(back)
        self.assertEqual(there.total_minutes, back.total_minutes)

    def test_it_reports_nominal_basis_where_gtfs_reports_timetable(self) -> None:
        """The whole point of carrying a basis: this data is weaker and says so."""

        from travel_planner.gtfs import TransitFeed

        osm = self.graph().journey(
            origin=(25.0405, 121.5705), destination=(25.0603, 121.5903)
        )
        self.assertEqual("nominal", osm.basis)
        feed = TransitFeed(
            Path(__file__).resolve().parent / "fixtures" / "synthetic_transit_gtfs.zip"
        )
        timetabled = feed.journey(
            origin=(25.040, 121.570), destination=(25.060, 121.590)
        )
        self.assertEqual("timetable", timetabled.basis)

    def test_a_metro_leg_walks_only_to_the_station(self) -> None:
        journey = self.graph().journey(
            origin=(25.0405, 121.5705), destination=(25.0603, 121.5903)
        )
        self.assertGreater(journey.total_minutes, journey.walking_minutes)
        self.assertLess(journey.walking_minutes, 5)

    def test_topology_without_a_usable_relation_refuses(self) -> None:
        """Stations alone are not a network, and inventing edges would be worse."""

        from travel_planner.providers import OsmMetroProvider, ProviderUnavailable
        from travel_planner.transit import graph_from_osm

        stations_only = graph_from_osm([e for e in self.ELEMENTS if e["type"] == "node"])
        self.assertEqual(3, len(stations_only.stops), "untagged track node must be dropped")
        self.assertEqual({}, stations_only.edges)
        provider = OsmMetroProvider(destination="Nowhere", graph=stations_only)
        with self.assertRaises(ProviderUnavailable):
            provider.route(
                {"place_id": "a", "latitude": 25.0405, "longitude": 121.5705},
                {"place_id": "b", "latitude": 25.0603, "longitude": 121.5903},
            )

    def test_the_provider_normalizes_like_any_other_route(self) -> None:
        from travel_planner.providers import OsmMetroProvider

        provider = OsmMetroProvider(destination="Taipei", graph=self.graph())
        route = provider.route(
            {"place_id": "tower", "latitude": 25.0405, "longitude": 121.5705},
            {"place_id": "market", "latitude": 25.0603, "longitude": 121.5903},
        )
        self.assertEqual("transit", route["mode"])
        self.assertEqual("estimated", route["status"])
        self.assertEqual("osm_metro", route["provider"])
        self.assertLess(route["walking_minutes"], route["duration_minutes"])
        self.assertGreaterEqual(route["boarding_buffer_minutes"], 1)

    def test_the_metro_query_pulls_relation_members(self) -> None:
        """`>;` is what makes the ordered member list resolvable.

        Without it the relations arrive referring to nodes that were never returned,
        and every line yields no edges at all.
        """

        from travel_planner.providers import OsmMetroProvider

        query = OsmMetroProvider(destination="Taipei").metro_query([25.0, 121.5, 25.1, 121.6])
        self.assertIn('relation["route"="subway"]', query)
        self.assertIn("(._;>;);", query)


class PlaceSummaryTest(unittest.TestCase):
    """Free descriptions and photos from Wikidata, in both languages."""

    class FakeWikidataPlaces(FakePlaceProvider):
        """The shared fake carries no `wikidata` signal, so nothing would be asked.

        Left as a subclass rather than changing the shared fake: a wikidata signal
        earns +0.5 in `_evidence_score`, so adding it there would move every ranking
        test's numbers for no reason.
        """

        def discover(self, destination: str) -> dict:
            payload = super().discover(destination)
            for index, item in enumerate(payload["items"], start=1):
                # `discovery.normalize` reads a nested `signals` map, not a
                # top-level key.
                item["signals"] = {"wikidata": f"Q{index}00", "wikipedia": f"en:Place {index}"}
            return payload

    class FakeSummaryProvider:
        name = "wikidata"
        operation = "wikidata:summary"
        kind = "place_summary"
        cache_ttl_days = 60

        def __init__(self) -> None:
            self.asked: list[str] = []

        def summary(self, qid: str) -> dict:
            self.asked.append(qid)
            if qid == "Q_MISSING":
                from travel_planner.providers import ProviderUnavailable

                raise ProviderUnavailable(f"Wikidata has no entity {qid}")
            return {
                "qid": qid,
                "names": {"en": f"Name of {qid}"},
                "text": {"en": f"A description of {qid}.", "th": f"คำบรรยายของ {qid}"},
                "image_url": f"https://commons.example/{qid}.jpg?width=640",
                "licence": "CC BY-SA, Wikipedia and Wikimedia Commons",
                "source_urls": {"en": f"https://en.wikipedia.org/wiki/{qid}"},
            }

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.provider = self.FakeSummaryProvider()
        self.actions = PlannerActions(
            Path(self.directory.name) / "summaries.sqlite3",
            place_provider=self.FakeWikidataPlaces(),
            summary_provider=self.provider,
        )
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="explore_first"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id, main_style=["sightseeing"],
            start_date="2030-01-01", end_date="2030-01-03",
            accommodation_status="booked", confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        self.candidates = self.actions.get_latest_discovery(
            self.trip.trip_id
        ).candidates.as_dict()["candidates"]
        for candidate in self.candidates:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=candidate["place_id"], action="must_do"
            )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_a_wikidata_label_becomes_an_english_name(self) -> None:
        """61% of the Taipei catalogue has no OSM `name:en`, and for the places that
        carry a QID the label is a real English name rather than a translation:
        三井物產株式會社舊廈 is "Mitsui & Co., Ltd. Old Building". Parsed here against the
        real API shape, because the parse is what a `props=` typo would break silently.
        """

        from travel_planner.providers import WikidataSummaryProvider

        provider = WikidataSummaryProvider()
        provider._json = lambda url: (  # type: ignore[method-assign]
            {
                "entities": {
                    "Q1": {
                        "labels": {"en": {"language": "en", "value": "Mitsui Old Building"}},
                        # No article in either language, so `text` stays empty -- the
                        # name still has to survive.
                        "sitelinks": {},
                        "claims": {},
                    }
                }
            }
            if "wbgetentities" in url
            else {}
        )

        summary = provider.summary("Q1")

        self.assertEqual({"en": "Mitsui Old Building"}, summary["names"])
        self.assertEqual({}, summary["text"])

    def test_the_label_request_asks_for_labels_in_both_languages(self) -> None:
        """A `props=` that omits `labels` returns no error, just no names."""

        from travel_planner.providers import WikidataSummaryProvider

        provider = WikidataSummaryProvider()
        asked: list[str] = []
        provider._json = lambda url: (asked.append(url), {"entities": {"Q1": {}}})[1]  # type: ignore[method-assign]

        with self.assertRaises(Exception):
            provider.summary("Q1")

        self.assertIn("labels", asked[0])
        self.assertIn("descriptions", asked[0])
        self.assertIn("languages=en|th", asked[0])

    def test_a_disambiguation_page_is_not_a_description(self) -> None:
        """OpenStreetMap's `wikidata` tag is sometimes wrong, and one way it is wrong is
        pointing at a disambiguation page. Busan's 국립해양박물관 carries **Q1195337**,
        which is "National Maritime Museum (disambiguation)" — so the card said "The
        National Maritime Museum is in Greenwich, United Kingdom." about a museum in
        Korea. Wikipedia labels these itself, so this reads upstream's marker rather
        than guessing from the prose.
        """

        from travel_planner.providers import WikidataSummaryProvider

        provider = WikidataSummaryProvider()

        def answer(url: str):
            if "wbgetentities" in url:
                return {
                    "entities": {
                        "Q1": {
                            "labels": {},
                            "descriptions": {},
                            "sitelinks": {"enwiki": {"title": "National Maritime Museum (disambiguation)"}},
                            "claims": {},
                        }
                    }
                }
            if "rest_v1/page/summary" in url:
                return {
                    "type": "disambiguation",
                    "extract": "The National Maritime Museum is in Greenwich, United Kingdom.",
                }
            return {}

        provider._json = answer  # type: ignore[method-assign]

        summary = provider.summary("Q1")

        self.assertEqual({}, summary["text"])

    def test_a_place_with_no_article_still_says_what_it_is(self) -> None:
        """Measured on the owner's own file: 27 of 64 stored summaries carried a
        photograph and no words at all, and every one of the 27 had a QID — they simply
        have no Wikipedia article, which is the only thing `text` is filled from.
        Wikidata's own description rides along in the request already being made.

        Kept out of `text`: an extract is CC BY-SA prose and this is a CC0 phrase, so
        the screen has to be able to credit the right one.
        """

        from travel_planner.providers import WikidataSummaryProvider

        provider = WikidataSummaryProvider()
        provider._json = lambda url: (  # type: ignore[method-assign]
            {
                "entities": {
                    "Q1": {
                        "labels": {"en": {"value": "Mount Tenno"}},
                        "descriptions": {
                            "en": {"value": "mountain in Oyamazaki, Kyoto, Japan"},
                            "th": {"value": "ภูเขาในเกียวโต"},
                        },
                        "sitelinks": {},
                        "claims": {},
                    }
                }
            }
            if "wbgetentities" in url
            else {}
        )

        summary = provider.summary("Q1")

        self.assertEqual({}, summary["text"])
        self.assertEqual(
            {"en": "mountain in Oyamazaki, Kyoto, Japan", "th": "ภูเขาในเกียวโต"},
            summary["description"],
        )

    def test_an_article_title_stands_in_where_there_is_no_label(self) -> None:
        from travel_planner.providers import WikidataSummaryProvider

        provider = WikidataSummaryProvider()
        provider._json = lambda url: (  # type: ignore[method-assign]
            {
                "entities": {
                    "Q1": {
                        "labels": {},
                        "sitelinks": {"enwiki": {"title": "Some Temple"}},
                        "claims": {},
                    }
                }
            }
            if "wbgetentities" in url
            else {"extract": ""}
        )

        self.assertEqual({"en": "Some Temple"}, provider.summary("Q1")["names"])

    def test_a_summary_can_be_dropped_without_touching_the_paid_evidence(self) -> None:
        """Deselecting a place leaves its evidence behind, which is deliberate for the
        paid half: an `opening_hours` row cost US$0.025 and is the reason this cache
        outlives a change of mind. Measured on the pilot on 2026-08-07 — 14 orphaned
        rows, 1 free summary and 13 paid hours worth US$0.325.

        So `kind` is required and a summary cleanup cannot reach the hours.
        """

        self.actions.refresh_place_summaries(self.trip.trip_id)
        place_id = self.candidates[0]["place_id"]
        self.actions.store.upsert_place_evidence(
            trip_id=self.trip.trip_id,
            place_id=place_id,
            kind="opening_hours",
            value={"place_id": place_id, "weekly": []},
            provider="google_places",
            retrieved_at="2030-01-01T00:00:00+00:00",
            expires_at="2030-12-31T00:00:00+00:00",
        )

        removed = self.actions.store.delete_place_evidence(
            self.trip.trip_id, place_id, "place_summary"
        )

        self.assertEqual(1, removed)
        self.assertNotIn(place_id, self.actions.list_place_summaries(self.trip.trip_id))
        self.assertEqual(
            [place_id],
            [
                item["place_id"]
                for item in self.actions.store.list_place_evidence(
                    self.trip.trip_id, "opening_hours"
                )
            ],
        )
        # Removing something already gone is not an error, so a tidy-up is idempotent.
        self.assertEqual(
            0,
            self.actions.store.delete_place_evidence(
                self.trip.trip_id, place_id, "place_summary"
            ),
        )

    def test_a_summary_is_stored_per_place_in_both_languages(self) -> None:
        report = self.actions.refresh_place_summaries(self.trip.trip_id)
        self.assertEqual(0, report["failed"], report.get("provider_errors"))
        self.assertGreater(report["fetched"], 0)

        stored = self.actions.list_place_summaries(self.trip.trip_id)
        self.assertEqual(report["fetched"], len(stored))
        for place_id, value in stored.items():
            # The id must live inside the value: list_place_evidence returns the
            # stored snapshot and does not add it back.
            self.assertEqual(place_id, value["place_id"])
            self.assertIn("en", value["text"])
            self.assertIn("th", value["text"])
            self.assertTrue(value["image_url"])
            self.assertIn("CC BY-SA", value["licence"])

    def test_it_reads_the_wikidata_id_from_the_selected_place(self) -> None:
        """`_selected_places` had to start carrying `signals`.

        Without it every place was skipped for want of a Wikidata id and the report
        said `fetched: 0` while reporting no failure — a silent no-op that reads as
        success.
        """

        self.actions.refresh_place_summaries(self.trip.trip_id)
        expected = {
            (c.get("signals") or {}).get("wikidata")
            for c in self.candidates
            if (c.get("signals") or {}).get("wikidata")
        }
        self.assertTrue(expected, "the fake discovery must supply a wikidata id")
        self.assertEqual(expected, set(self.provider.asked))

    def test_commons_photographs_join_the_gallery_rather_than_replacing_it(self) -> None:
        """A card with one picture stayed a card with one picture.

        `named_photos` finds Commons files whose title names the place and whose
        coordinates agree — pictures *of* it, not merely near it — but it ran only where
        the encyclopedia had produced nothing at all. So the places that do carry a
        Wikidata id, which is 31 of the owner's 487 Kyoto candidates, got exactly what
        Wikipedia held and no more.

        Geosearch is deliberately not treated this way: it answers "what was
        photographed at this spot", which is why it stays a substitute and is flagged.
        """

        self.provider.named_photos = lambda name, lat, lon: [  # type: ignore[attr-defined]
            "https://commons.example/named-one.jpg",
            "https://commons.example/named-two.jpg",
        ]

        self.actions.refresh_place_summaries(self.trip.trip_id, force=True)

        stored = self.actions.list_place_summaries(self.trip.trip_id)
        self.assertTrue(stored)
        for value in stored.values():
            gallery = value["image_urls"]
            # The encyclopedia's own picture still leads.
            self.assertTrue(gallery[0].startswith("https://commons.example/Q"))
            self.assertIn("https://commons.example/named-one.jpg", gallery)
            self.assertIn("https://commons.example/named-two.jpg", gallery)
            # Named files are of the place, so the nearby caption must not be claimed.
            self.assertFalse(value.get("photos_are_nearby"))

    def test_a_second_run_uses_the_cache_and_spends_nothing_new(self) -> None:
        first = self.actions.refresh_place_summaries(self.trip.trip_id)
        second = self.actions.refresh_place_summaries(self.trip.trip_id)
        self.assertEqual(first["fetched"], second["from_cache"])
        self.assertEqual(0, second["fetched"])

    def test_it_is_recorded_at_zero_rather_than_left_unpriced(self) -> None:
        self.actions.refresh_place_summaries(self.trip.trip_id)
        rows = [
            row
            for row in self.actions.store.list_paid_usage()
            if row["operation"] == "wikidata:summary"
        ]
        self.assertTrue(rows)
        self.assertEqual(0.0, sum(float(row["estimated_usd"]) for row in rows))

    def test_a_place_without_an_article_is_left_blank_not_invented(self) -> None:
        self.provider.summary = lambda qid: {  # type: ignore[method-assign]
            "qid": qid, "text": {}, "image_url": None,
            "licence": "CC BY-SA, Wikipedia and Wikimedia Commons", "source_urls": {},
        }
        self.actions.refresh_place_summaries(self.trip.trip_id, force=True)
        stored = self.actions.list_place_summaries(self.trip.trip_id)
        self.assertTrue(stored)
        for value in stored.values():
            self.assertEqual({}, value["text"])
            self.assertIsNone(value["image_url"])


class NearbyPhotoMatchTest(unittest.TestCase):
    """A geosearch photograph is only used when its own file name names the place.

    Every case here was returned by Wikimedia Commons for the real coordinates of the
    real Taipei place beside it, sampled on 2026-08-09. They are kept verbatim because
    the rule is a judgement about real data and a paraphrase would not hold it.
    """

    #: (Commons file title, names the catalogue holds, should it be shown)
    MEASURED = (
        # The case that started this: a city bus, returned for a hill. The catalogue's
        # own name for the hill is `Yuanshan`, which the bus station's name contains --
        # so containment alone passes it and only the coverage test rejects it.
        ("File:KKMT_470-FY_right_side_at_Yuanshan_Bus_Station_(Yumen)_20250822.jpg",
         ["Yuanshan", "圓山"], False),
        ("File:Yuanshan Bus Station platform.jpg", ["Yuanshan", "圓山"], False),
        ("File:Daan Forest Park 大安森林公園 - panoramio (6).jpg", ["Da-an Forest Park"], True),
        ("File:介壽公園 Jieshou Park - panoramio.jpg", ["Jieshou Park"], True),
        # Same place, a different photograph a hundred metres away.
        ("File:Dongmen by night 20230508 185948.jpg", ["Jieshou Park"], False),
        ("File:永和保福宮正面照.jpg", ["(原新生市場）家家土雞阿定海魚"], False),
        ("File:陽明山美國在臺協會（原美援會）宿舍 5193.jpg", ["Floriculture Experiment Center"], False),
        ("File:20200929163337-隱藏在樹叢中的中和瑞穗配水池牆面.jpg", ["Mantoushan"], False),
        ("File:Lotus, Taipei, Taiwan (8468946883).jpg", ["Central Art Park"], False),
        # The local spelling matches where the English one would not.
        ("File:大安森林公園夜景.jpg", ["Da-an Forest Park", "大安森林公園"], True),
    )

    def test_the_measured_cases_are_judged_as_they_were_judged_by_hand(self) -> None:
        for title, names, expected in self.MEASURED:
            with self.subTest(title=title):
                self.assertEqual(expected, photo_depicts_place(title, names))

    def test_the_same_words_in_the_file_match_even_when_something_sits_between_them(
        self,
    ) -> None:
        """Measured on the owner's Da Nang catalogue, 2026-08-17.

        Commons held **nine** files within 150 m of Thành Điện Hải and every one was
        rejected, because the citadel is filed as `Thành cổ Điện Hải` — one word inserted
        into the middle of the name — and a contiguous containment test cannot see past
        it. Requiring every word, in any order, catches it; requiring *any* word would be
        the loose rule this filter exists to avoid.
        """

        self.assertTrue(
            photo_depicts_place("File:Thành cổ Điện Hải 2.jpeg", ["Thành Điện Hải"])
        )

    def test_a_parenthetical_alias_is_not_part_of_the_name(self) -> None:
        """`Trieu Chau (Chaozhou) Assembly Hall` is filed on Commons without the alias,
        so carrying it into the match made the hall's own photographs unmatchable."""

        self.assertTrue(
            photo_depicts_place(
                "File:Hội An, Trieu Chau Assembly Hall, 2020-01 CN-02.jpg",
                ["Trieu Chau (Chaozhou) Assembly Hall"],
            )
        )

    def test_the_bus_is_still_refused_after_the_words_rule(self) -> None:
        """The case the whole filter was written for, re-pinned against the looser rule.
        `Yuanshan` is one word and appears in the file, so an any-word test would accept
        a city bus as the photograph of a hill."""

        self.assertFalse(
            photo_depicts_place(
                "File:KKMT_470-FY_right_side_at_Yuanshan_Bus_Station.jpg", ["Yuanshan"]
            )
        )

    def test_a_one_word_place_name_cannot_sweep_a_city(self) -> None:
        """The stated danger of matching by words: a catalogue whose names begin with the
        city must not accept every street scene. The coverage rule is what stops it."""

        self.assertFalse(
            photo_depicts_place("File:Taipei 101 from Elephant Mountain.jpg", ["Taipei"])
        )

    def test_a_real_photograph_is_lost_where_only_part_of_the_name_is_in_the_file(self) -> None:
        """The documented cost of requiring the whole name, pinned so it stays a
        decision rather than becoming a surprise. This photograph really is of the
        place; matching single words instead would accept any `Taipei` street scene for
        the majority of the catalogue, which begins with the city's name."""

        self.assertFalse(
            photo_depicts_place("File:Herbarium 植物園蠟業館 - panoramio.jpg",
                                ["Herbarium of Taipei Botanical Garden"])
        )

    def test_a_verbose_file_name_loses_its_place(self) -> None:
        """The cost of the coverage rule, pinned like the cost of the whole-name rule.
        This photograph is of Jieshou Park, but the name recites the country, city and
        district first, so the park accounts for a seventh of it. Such places generally
        carry a plainer file as well, which is why this is affordable."""

        self.assertFalse(
            photo_depicts_place(
                "File:TW 台灣 Taiwan TPE 台北市 Taipei 中正區 Zhongzheng tour 中山南路 "
                "Zhongshan South Road 1442pm 介壽公園 Jieshou Park.jpg",
                ["Jieshou Park"],
            )
        )

    def test_a_name_too_short_to_be_distinctive_matches_nothing(self) -> None:
        # 圓山 is a substring of 圓山站, 圓山公園 and 圓山大飯店 alike.
        self.assertFalse(photo_depicts_place("File:圓山大飯店.jpg", ["圓山"]))
        self.assertFalse(photo_depicts_place("File:Park bench.jpg", ["Ark"]))

    def test_an_osm_commons_category_becomes_a_gallery(self) -> None:
        provider = WikidataSummaryProvider()
        provider._json = lambda url: {  # type: ignore[method-assign]
            "query": {
                "categorymembers": [
                    {"title": "File:Temple front.jpg"},
                    {"title": "File:Temple plan.svg"},
                ]
            }
        }

        found = provider.category_photos("Category:Example Temple")

        self.assertEqual(1, len(found))
        self.assertIn("Temple_front.jpg", found[0])

    def test_geosearch_returns_only_the_files_that_name_the_place(self) -> None:
        provider = WikidataSummaryProvider()
        provider._json = lambda url: {  # type: ignore[method-assign]
            "query": {
                "pages": {
                    "1": {"title": "File:Daan Forest Park at dusk.jpg",
                          "imageinfo": [{"thumburl": "https://example.invalid/right.jpg"}]},
                    "2": {"title": "File:Bus 470-FY at the station.jpg",
                          "imageinfo": [{"thumburl": "https://example.invalid/wrong.jpg"}]},
                }
            }
        }

        found = provider.nearby_photos(25.03, 121.54, ["Daan Forest Park"])

        self.assertEqual(["https://example.invalid/right.jpg"], found)

    def test_a_named_search_needs_the_location_to_agree(self) -> None:
        """What makes a *global* text search safe. Searching Commons for `Central Art
        Park` really returns six photographs of Central Park in Vinnytsya, Ukraine, and
        not one of them carries coordinates — so a file with no location is refused
        rather than trusted, and one with a location has to agree."""

        provider = WikidataSummaryProvider()
        provider._json = lambda url: {  # type: ignore[method-assign]
            "query": {
                "pages": {
                    "1": {  # Right name, right place.
                        "title": "File:Shilin Presidential Residence Park.jpg",
                        "coordinates": [{"lat": 25.0934, "lon": 121.5308}],
                        "imageinfo": [{"thumburl": "https://example.invalid/right.jpg"}],
                    },
                    "2": {  # Right name, wrong continent.
                        "title": "File:Shilin Presidential Residence Park.jpg",
                        "coordinates": [{"lat": 49.23, "lon": 28.47}],
                        "imageinfo": [{"thumburl": "https://example.invalid/ukraine.jpg"}],
                    },
                    "3": {  # Right name, no location at all.
                        "title": "File:Shilin Presidential Residence Park.jpg",
                        "imageinfo": [{"thumburl": "https://example.invalid/nowhere.jpg"}],
                    },
                }
            }
        }

        found = provider.named_photos("Shilin Presidential Residence Park", 25.0934, 121.5308)

        self.assertEqual(["https://example.invalid/right.jpg"], found)

    def test_a_named_search_still_applies_the_name_rule(self) -> None:
        provider = WikidataSummaryProvider()
        provider._json = lambda url: {  # type: ignore[method-assign]
            "query": {
                "pages": {
                    "1": {
                        "title": "File:A bus at the station.jpg",
                        "coordinates": [{"lat": 25.0934, "lon": 121.5308}],
                        "imageinfo": [{"thumburl": "https://example.invalid/bus.jpg"}],
                    }
                }
            }
        }
        self.assertEqual([], provider.named_photos("Shilin Presidential Residence Park", 25.0934, 121.5308))

    def test_a_place_with_no_name_gets_no_photograph_rather_than_a_guess(self) -> None:
        provider = WikidataSummaryProvider()
        called: list[str] = []
        provider._json = lambda url: called.append(url) or {}  # type: ignore[method-assign]

        self.assertEqual([], provider.nearby_photos(25.03, 121.54, []))
        self.assertEqual([], provider.nearby_photos(25.03, 121.54, [""]))
        # Nothing can match, so nothing is asked -- Commons is a public service.
        self.assertEqual([], called)


class TimeZoneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "tz.sqlite3"
        self.provider = FakeTimeZoneProvider()
        self.actions = PlannerActions(
            self.path,
            place_provider=FakePlaceProvider(),
            timezone_provider=self.provider,
        )
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="ready_to_schedule"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date="2030-01-01",
            end_date="2030-01-03",
            accommodation_status="booked",
            confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_a_status_other_than_ok_is_never_a_fallback_zone(self) -> None:
        provider = GoogleTimeZoneProvider()
        for payload in (
            {"status": "ZERO_RESULTS"},
            {"status": "REQUEST_DENIED"},
            {},
            {"status": "OK", "timeZoneId": ""},
        ):
            with self.assertRaises(ProviderUnavailable):
                provider.normalize(payload, latitude=25.0, longitude=121.0)

    def test_the_free_provider_reads_the_zone_open_meteo_already_echoes(self) -> None:
        """The zone is verified by default now, and by default it costs nothing.

        `GoogleTimeZoneProvider` is US$0.005 and needs `GOOGLE_MAPS_SERVER_KEY`, so a
        machine without one carried `DESTINATION_TIMEZONE_UNVERIFIED` for the whole life
        of every trip. Open-Meteo returns the resolved zone whenever `timezone=auto` is
        sent, which both weather providers already send — so the same evidence record
        comes from a free, keyless service this app already calls.
        """

        from travel_planner.providers import OpenMeteoTimeZoneProvider

        value = OpenMeteoTimeZoneProvider().normalize(
            {
                "timezone": "Asia/Tokyo",
                "timezone_abbreviation": "GMT+9",
                "utc_offset_seconds": 32400,
            },
            latitude=34.685,
            longitude=135.833,
        )

        self.assertEqual("Asia/Tokyo", value["timezone"])
        self.assertEqual("verified", value["status"])
        self.assertEqual("open_meteo_timezone", value["provider"])
        # Same kind as the paid provider, so either can satisfy the same gap.
        self.assertEqual("destination_timezone", value["kind"])

    def test_the_free_provider_never_invents_a_zone_either(self) -> None:
        """`WF-002`: a zone is stated by a provider or it is unverified. `auto` coming
        back is the service failing to resolve it, not an answer."""

        from travel_planner.providers import OpenMeteoTimeZoneProvider

        provider = OpenMeteoTimeZoneProvider()
        for payload in ({}, {"timezone": ""}, {"timezone": "auto"}):
            with self.assertRaises(ProviderUnavailable):
                provider.normalize(payload, latitude=25.0, longitude=121.0)

    def test_the_zone_is_recorded_with_its_provenance(self) -> None:
        result = self.actions.refresh_timezone(self.trip.trip_id)

        self.assertEqual("Asia/Taipei", result["timezone"])
        self.assertEqual("google_timezone", result["provider"])
        self.assertEqual("verified", result["status"])
        self.assertEqual(28800, result["raw_offset_seconds"])
        self.assertFalse(result["from_cache"])
        # Queried at the centre of the discovered coverage box.
        latitude, longitude = self.provider.calls[0]
        self.assertAlmostEqual(25.05, latitude, places=2)
        self.assertAlmostEqual(121.55, longitude, places=2)

    def test_a_second_lookup_is_served_from_evidence_at_no_cost(self) -> None:
        self.actions.refresh_timezone(self.trip.trip_id)
        again = self.actions.refresh_timezone(self.trip.trip_id)

        self.assertTrue(again["from_cache"])
        self.assertEqual(1, len(self.provider.calls))
        bucket = self.actions.paid_usage_status()["by_operation"]["google_timezone:lookup"]
        # One paid request, one cached read recorded at zero.
        self.assertEqual(1, bucket["requests"])
        self.assertEqual(0.005, bucket["estimated_usd"])

    def test_the_zone_clears_its_capability_gap_and_reaches_the_optimizer(self) -> None:
        for place_id in [
            item["place_id"]
            for item in self.actions.get_latest_discovery(
                self.trip.trip_id
            ).candidates.as_dict()["candidates"]
        ]:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=place_id, action="must_do"
            )

        before = self.actions._optimizer_input(self.trip.trip_id)
        self.assertIn("DESTINATION_TIMEZONE_UNVERIFIED", before["trip"]["capability_gaps"])
        self.assertIsNone(before["trip"]["timezone"])

        self.actions.refresh_timezone(self.trip.trip_id)
        after = self.actions._optimizer_input(self.trip.trip_id)

        self.assertNotIn("DESTINATION_TIMEZONE_UNVERIFIED", after["trip"]["capability_gaps"])
        self.assertEqual("Asia/Taipei", after["trip"]["timezone"])

    def test_an_expired_zone_stops_counting_as_verified(self) -> None:
        self.actions.refresh_timezone(self.trip.trip_id)
        with self.actions.store.connect() as connection:
            connection.execute(
                "UPDATE trip_evidence SET expires_at = '2000-01-01T00:00:00+00:00'"
            )

        self.assertEqual("stale", self.actions.get_timezone_evidence(self.trip.trip_id)["status"])
        self.actions.save_candidate_choice(
            trip_id=self.trip.trip_id,
            place_id=self.actions.get_latest_discovery(self.trip.trip_id)
            .candidates.as_dict()["candidates"][0]["place_id"],
            action="must_do",
        )
        gaps = self.actions._optimizer_input(self.trip.trip_id)["trip"]["capability_gaps"]
        self.assertIn("DESTINATION_TIMEZONE_UNVERIFIED", gaps)

    def test_a_lookup_needs_a_discovered_destination(self) -> None:
        bare = PlannerActions(
            Path(self.directory.name) / "bare.sqlite3", timezone_provider=self.provider
        )
        trip = bare.create_trip(name="Bare", destination="Nowhere")
        with self.assertRaises(ValueError) as raised:
            bare.refresh_timezone(trip.trip_id)
        self.assertEqual("discovery_missing", str(raised.exception))

    def test_the_cap_stops_the_paid_lookup(self) -> None:
        self.actions.record_paid_call(operation="google_places:details", count=600)
        with self.assertRaises(ProviderBudgetExceeded):
            self.actions.refresh_timezone(self.trip.trip_id)
        self.assertEqual([], self.provider.calls)

