"""The zoomed-in map window: buildings, roads, land use, rail and markers (`WF-048`).

The window guard is the whole safety of this: at the full city view a footprint is well
under a pixel and the road hierarchy is a smudge, so an ungated request fetches six
figures of geometry to draw nothing. These pin the guard, the layering of what comes
back, and the cache that keeps panning free.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from travel_planner.actions import PlannerActions, PlannerRefusal
from travel_planner.providers import OpenStreetMapProvider, ProviderUnavailable


class RecordingDetailProvider:
    """Answers `map_detail` without a socket, and counts how often it was asked."""

    name = "fake_places"
    cache_ttl_days = 7

    def __init__(self) -> None:
        self.calls: list[list[float]] = []

    def map_detail(self, bbox: list[float]) -> dict:
        self.calls.append(list(bbox))
        return {
            "bbox": bbox, "too_wide": False,
            "buildings": [[[1.0, 2.0], [1.0, 2.1], [1.1, 2.1]]],
            "roads": [], "areas": [], "rails": [], "markers": [],
        }


class MapDetailQueryTest(unittest.TestCase):
    """The provider half, which needs no database and no network."""

    def setUp(self) -> None:
        self.provider = OpenStreetMapProvider()

    def test_the_query_carries_the_window_and_the_limit(self) -> None:
        query = self.provider.map_detail_query([25.024, 121.554, 25.044, 121.574])
        self.assertIn("25.02400,121.55400,25.04400,121.57400", query)
        self.assertIn('way["building"]', query)
        self.assertIn(f"out geom {self.provider.detail_limit};", query)

    def test_a_window_wider_than_the_ceiling_is_refused_without_asking(self) -> None:
        # No stub is installed, so reaching the network at all would raise here — that
        # is the assertion. A too-wide window must be answered from the guard alone.
        result = self.provider.map_detail([24.9, 121.4, 25.2, 121.7])
        self.assertTrue(result["too_wide"])
        self.assertEqual([], result["buildings"])

    def test_the_ceiling_is_the_wider_of_the_two_spans(self) -> None:
        # Tall and narrow is still too big to draw: the guard takes the max, so a window
        # that is small in longitude cannot smuggle a huge latitude span past it.
        tall = self.provider.map_detail([25.0, 121.55, 25.09, 121.56])
        self.assertTrue(tall["too_wide"])

    def test_rings_are_rounded_deduped_and_dropped_when_too_short(self) -> None:
        tag = {"building": "yes"}
        elements = [
            # Two points is a line, not a footprint.
            {"tags": tag, "geometry": [{"lat": 1.0, "lon": 2.0}, {"lat": 1.0, "lon": 2.1}]},
            # Rounding collapses the first two onto each other; what survives is still
            # a triangle, so it is kept.
            {
                "tags": tag,
                "geometry": [
                    {"lat": 1.000001, "lon": 2.0},
                    {"lat": 1.000002, "lon": 2.0},
                    {"lat": 1.001, "lon": 2.0},
                    {"lat": 1.001, "lon": 2.001},
                ]
            },
            # Rounding leaves only two distinct points, so this one goes.
            {
                "tags": tag,
                "geometry": [
                    {"lat": 5.000001, "lon": 6.0},
                    {"lat": 5.000002, "lon": 6.0},
                    {"lat": 5.001, "lon": 6.0},
                ]
            },
            {"tags": tag, "geometry": []},
        ]
        self.provider._drawing_elements = lambda query, *, timeout=None: elements  # type: ignore[method-assign]
        result = self.provider.map_detail([1.0, 2.0, 1.01, 2.01])
        self.assertFalse(result["too_wide"])
        self.assertEqual([[[1.0, 2.0], [1.001, 2.0], [1.001, 2.001]]], result["buildings"])

    def test_each_element_lands_in_the_layer_it_belongs_to(self) -> None:
        """A map is read in layers, so the response arrives in them rather than as one
        pile the screen has to sort by tag."""

        line = [{"lat": 1.0, "lon": 2.0}, {"lat": 1.001, "lon": 2.0}, {"lat": 1.001, "lon": 2.001}]
        self.provider._drawing_elements = lambda query, *, timeout=None: [  # type: ignore[method-assign]
            {"tags": {"building": "yes"}, "geometry": line},
            {"tags": {"highway": "primary", "name": "中華路一段", "name:en": "Section 1, Zhonghua Road",
                      "oneway": "yes"}, "geometry": line},
            {"tags": {"leisure": "park"}, "geometry": line},
            {"tags": {"railway": "subway", "name": "Bannan"}, "geometry": line},
            {"type": "node", "tags": {"railway": "subway_entrance"}, "lat": 1.0, "lon": 2.0},
            {"type": "node", "tags": {"highway": "bus_stop"}, "lat": 1.0, "lon": 2.0},
            # A tag nothing draws is dropped rather than landing in a catch-all layer.
            {"tags": {"barrier": "fence"}, "geometry": line},
        ]
        result = self.provider.map_detail([1.0, 2.0, 1.01, 2.01])

        self.assertEqual(1, len(result["buildings"]))
        self.assertEqual(1, len(result["areas"]))
        self.assertEqual("park", result["areas"][0]["kind"])
        self.assertEqual(1, len(result["rails"]))
        self.assertEqual(["metro_entrance", "bus_stop"], [m["kind"] for m in result["markers"]])
        road = result["roads"][0]
        # Both spellings ride along, because the street sign carries one and the visitor
        # reads the other.
        self.assertEqual(("primary", "中華路一段", "Section 1, Zhonghua Road", True),
                         (road["class"], road["name"], road["name_en"], road["oneway"]))


class RefreshMapDetailTest(unittest.TestCase):
    """The coordinator half: refusals, the cache, and the free ledger row."""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "tourist.sqlite3"
        self.provider = RecordingDetailProvider()
        self.actions = PlannerActions(self.database_path, place_provider=self.provider)
        self.trip = self.actions.create_trip(
            name="Taipei New Year",
            destination="Taipei, Taiwan",
            planning_mode="ready_to_schedule",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_an_unknown_trip_is_refused(self) -> None:
        with self.assertRaises(PlannerRefusal) as caught:
            self.actions.refresh_map_detail("trip_missing", bbox=[1.0, 2.0, 1.01, 2.01])
        self.assertEqual("unknown_trip", caught.exception.code)

    def test_a_malformed_window_is_refused_with_its_own_code(self) -> None:
        for bad in ([1.0, 2.0, 3.0], "25,121,25,121", [], None):
            with self.subTest(bbox=bad):
                with self.assertRaises(PlannerRefusal) as caught:
                    self.actions.refresh_map_detail(self.trip.trip_id, bbox=bad)  # type: ignore[arg-type]
                self.assertEqual("bad_map_window", caught.exception.code)
        self.assertEqual([], self.provider.calls)

    def test_the_same_window_is_fetched_once_and_then_served_from_cache(self) -> None:
        first = self.actions.refresh_map_detail(self.trip.trip_id, bbox=[25.0241, 121.5541, 25.0441, 121.5741])
        second = self.actions.refresh_map_detail(self.trip.trip_id, bbox=[25.0242, 121.5542, 25.0442, 121.5742])
        self.assertEqual(first, second)
        # Both windows round to the same ~100 m key, so panning a few metres re-reads
        # the work rather than asking for it again.
        self.assertEqual(1, len(self.provider.calls))
        self.assertEqual([25.024, 121.554, 25.044, 121.574], self.provider.calls[0])

    def test_a_different_window_is_its_own_request(self) -> None:
        self.actions.refresh_map_detail(self.trip.trip_id, bbox=[25.024, 121.554, 25.044, 121.574])
        self.actions.refresh_map_detail(self.trip.trip_id, bbox=[25.064, 121.594, 25.084, 121.614])
        self.assertEqual(2, len(self.provider.calls))

    def test_the_call_is_recorded_at_zero_rather_than_left_off_the_ledger(self) -> None:
        # Free-tier operations are priced at zero rather than skipped, so call counts
        # stay reconcilable against the provider's own view.
        self.actions.refresh_map_detail(self.trip.trip_id, bbox=[25.024, 121.554, 25.044, 121.574])
        status = self.actions.paid_usage_status()
        self.assertIn("openstreetmap:map_detail", status["by_operation"])
        self.assertEqual(1, status["by_operation"]["openstreetmap:map_detail"]["requests"])
        self.assertEqual(0.0, status["spent_usd"])


class CountryOutlineTest(unittest.TestCase):
    """The country's own shape, which is what lets the map be zoomed out past its city."""

    def setUp(self) -> None:
        self.provider = OpenStreetMapProvider()

    def test_geojson_longitude_latitude_order_is_transposed_on_the_way_in(self) -> None:
        """GeoJSON is `[longitude, latitude]` and everything else here is the other way
        round. Getting this wrong puts a country in the sea and looks like a projection
        bug rather than a transposition, so it is pinned."""

        self.provider._request_json = lambda request: [  # type: ignore[method-assign]
            {"geojson": {"type": "Polygon", "coordinates": [[[121.5, 25.0], [121.6, 25.0], [121.6, 25.1]]]}}
        ]
        rings = self.provider.country_outline("Taiwan")["rings"]
        self.assertEqual([[[25.0, 121.5], [25.0, 121.6], [25.1, 121.6]]], rings)

    def test_a_multipolygon_becomes_one_flat_list_of_rings(self) -> None:
        # A country is rarely one island, and Taiwan's boundary is 21 rings.
        self.provider._request_json = lambda request: [  # type: ignore[method-assign]
            {
                "geojson": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[121.0, 25.0], [121.1, 25.0], [121.1, 25.1]]],
                        [[[119.0, 23.0], [119.1, 23.0], [119.1, 23.1]]],
                    ],
                }
            }
        ]
        self.assertEqual(2, len(self.provider.country_outline("Taiwan")["rings"]))

    def test_a_shape_too_small_to_be_a_ring_is_dropped(self) -> None:
        self.provider._request_json = lambda request: [  # type: ignore[method-assign]
            {"geojson": {"type": "Polygon", "coordinates": [[[121.0, 25.0], [121.1, 25.0]]]}}
        ]
        self.assertEqual([], self.provider.country_outline("Taiwan")["rings"])

    def test_a_country_with_no_boundary_yields_nothing_rather_than_raising(self) -> None:
        self.provider._request_json = lambda request: []  # type: ignore[method-assign]
        self.assertEqual([], self.provider.country_outline("Nowhere")["rings"])

    def test_the_request_asks_the_server_to_simplify(self) -> None:
        """The whole reason this is affordable: unsimplified, Taiwan's coastline is
        megabytes; at this threshold it is 137 points and 4 KB."""

        seen: list[str] = []

        def capture(request):
            seen.append(request.full_url)
            return []

        self.provider._request_json = capture  # type: ignore[method-assign]
        self.provider.country_outline("Taiwan")
        self.assertIn("polygon_geojson=1", seen[0])
        self.assertIn(f"polygon_threshold={self.provider.outline_threshold}", seen[0])


class DrawingRetryTest(unittest.TestCase):
    """A fast 5xx from a sick Overpass backend must not leave the map blank.

    Measured 2026-08-10 on a 1.5 km Taipei window: HTTP 504 at 8.5 s, then 200 at 8.5 s
    on the identical query. Discovery has retried this since `WF-048`; the drawing side
    did not, and the whole symptom was "I still don't see the detail".
    """

    def setUp(self) -> None:
        self.provider = OpenStreetMapProvider()
        self.provider.RETRY_PAUSE_SECONDS = 0

    def _answers(self, *outcomes):
        seen = {"n": 0}

        def call(query, timeout=None):
            outcome = outcomes[min(seen["n"], len(outcomes) - 1)]
            seen["n"] += 1
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        self.provider._overpass_elements = call  # type: ignore[method-assign]
        return seen

    def test_a_fast_five_hundred_is_asked_again(self) -> None:
        seen = self._answers(ProviderUnavailable("Provider HTTP 504"), [])
        self.assertEqual([], self.provider._drawing_elements("q", timeout=30))
        self.assertEqual(2, seen["n"])

    def test_a_four_hundred_is_not_retried(self) -> None:
        # A refusal is an answer. Asking again just spends another slot to hear it twice.
        seen = self._answers(ProviderUnavailable("Provider HTTP 429"))
        with self.assertRaises(ProviderUnavailable):
            self.provider._drawing_elements("q", timeout=30)
        self.assertEqual(1, seen["n"])

    def test_a_slow_failure_is_not_retried(self) -> None:
        """A request that spent its whole budget died of its own timeout, and asking
        again would spend the budget again to fail identically."""

        self.provider.FAST_FAILURE_SECONDS = -1
        seen = self._answers(ProviderUnavailable("Provider HTTP 504"))
        with self.assertRaises(ProviderUnavailable):
            self.provider._drawing_elements("q", timeout=30)
        self.assertEqual(1, seen["n"])

    def test_the_retry_reaches_map_detail_and_the_basemap(self) -> None:
        for name, call in (
            ("map_detail", lambda: self.provider.map_detail([25.03, 121.56, 25.04, 121.57])),
            ("basemap", lambda: self.provider.basemap([25.03, 121.56, 25.04, 121.57])),
        ):
            with self.subTest(name):
                seen = self._answers(ProviderUnavailable("Provider HTTP 504"), [])
                call()
                self.assertEqual(2, seen["n"])


if __name__ == "__main__":
    unittest.main()
