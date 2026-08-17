from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import unittest.mock

from travel_planner.actions import PlannerActions
from travel_planner.providers import ProviderUnavailable, VenueNoticeProvider, visible_text
from tests.test_routes import FakePlaceProvider


class QuoteGuardTest(unittest.TestCase):
    """`WF-044`. The one hallucination test that needs no judgement."""

    PAGE = "公告 本館 配合工程 於 2027-01-01 休館 一日 敬請見諒"

    def test_a_verbatim_quote_passes_and_whitespace_is_forgiven(self) -> None:
        self.assertTrue(VenueNoticeProvider.quotes_the_page("於 2027-01-01 休館", self.PAGE))
        # Whitespace is an artefact of stripping tags, not of the model's honesty.
        self.assertTrue(VenueNoticeProvider.quotes_the_page("於2027-01-01休館", self.PAGE))

    def test_a_paraphrase_or_translation_is_rejected(self) -> None:
        for quote in (
            "The hall will be closed on 1 January 2027",  # translated
            "本館於 2027-01-02 休館",                       # plausible, wrong date
            "休館 兩日",                                     # plausible, not on the page
        ):
            with self.subTest(quote=quote):
                self.assertFalse(VenueNoticeProvider.quotes_the_page(quote, self.PAGE))

    def test_case_is_not_folded(self) -> None:
        """Folding case would let a rewritten sentence through, and a rewritten sentence
        is exactly what cannot be checked against the source."""

        self.assertFalse(VenueNoticeProvider.quotes_the_page("CLOSED", "closed on 1 Jan"))

    def test_visible_text_drops_scripts_and_caps_length(self) -> None:
        html = "<p>Hello</p><script>var closed = true;</script><p>world</p>"
        self.assertEqual("Hello world", visible_text(html))
        self.assertNotIn("var closed", visible_text(html))
        self.assertEqual(5, len(visible_text("<p>" + "x" * 100 + "</p>", limit=5)))

    def test_the_prompt_refuses_the_traps_that_were_measured(self) -> None:
        prompt = VenueNoticeProvider.SYSTEM_PROMPT
        # Sun Yat-sen's own 休館公告 is about a server-room migration affecting its
        # website. An extractor acting on that would delete a landmark.
        self.assertIn("website", prompt)
        self.assertIn("never paraphrase", prompt)
        self.assertIn("Never state regular weekly hours", prompt)

    def test_preview_accepts_twitter_metadata_and_relative_images(self) -> None:
        page = (
            b'<meta content="/media/card.jpg" name="twitter:image">'
            b'<meta name="twitter:description" content="The venue garden.">'
        )

        class Response:
            class Headers:
                @staticmethod
                def get_content_charset():
                    return "utf-8"

            headers = Headers()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return page[:limit]

        with unittest.mock.patch("travel_planner.providers.urlopen", return_value=Response()):
            preview = VenueNoticeProvider().preview("https://venue.example/about")

        self.assertEqual("https://venue.example/media/card.jpg", preview["image_url"])
        self.assertEqual("The venue garden.", preview["text"])


class NoticeWiringTest(unittest.TestCase):
    """`notice()` end to end with a stubbed transport.

    The pure `quotes_the_page` tests above do not prove the guard is *called*. Removing
    the call from `notice()` failed no test until this class existed.
    """

    PAGE = "公告 本館 配合工程 於 2027-01-01 休館 一日 敬請見諒"

    def build(self, reply: dict) -> VenueNoticeProvider:
        import json as _json
        from contextlib import contextmanager
        from unittest.mock import patch

        provider = VenueNoticeProvider()
        provider.read_page = lambda website: self.PAGE  # type: ignore[method-assign]
        body = {"output": [{"content": [{"type": "output_text", "text": _json.dumps(reply)}]}]}

        @contextmanager
        def fake_urlopen(request, timeout=None):
            class Response:
                def read(self, *a): return _json.dumps(body).encode()
                def __iter__(self): return iter(())
            import io
            yield io.BytesIO(_json.dumps(body).encode())

        self._patch = patch("travel_planner.providers.urlopen", fake_urlopen)
        return provider

    def run_notice(self, reply: dict) -> dict:
        import os
        provider = self.build(reply)
        with self._patch:
            with unittest.mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
                return provider.notice(name="Test Hall", website="https://example.test/")

    def test_a_verbatim_quote_survives(self) -> None:
        found = self.run_notice(
            {"found": True, "quote": "於 2027-01-01 休館", "summary": "closed one day"}
        )
        self.assertTrue(found["found"])
        self.assertEqual("於 2027-01-01 休館", found["quote"])

    def test_a_quote_that_is_not_on_the_page_is_discarded(self) -> None:
        """The guard must be *called*, not merely exist."""

        found = self.run_notice(
            {"found": True, "quote": "The hall closes on 2 January", "summary": "invented"}
        )
        self.assertFalse(found["found"])
        self.assertEqual("QUOTE_NOT_ON_PAGE", found["reason"])

    def test_found_false_needs_no_quote(self) -> None:
        found = self.run_notice({"found": False, "quote": None, "summary": None})
        self.assertFalse(found["found"])
        self.assertEqual("NO_NOTICE_ON_PAGE", found["reason"])


class FakeNoticeProvider:
    name = "venue_notice"
    operation = "openai:venue_notice"
    kind = "venue_notice"
    cache_ttl_days = 14

    def __init__(self, answer=None, *, fail: bool = False) -> None:
        self.answer = answer
        self.fail = fail
        self.asked: list[str] = []

    def notice(self, *, name: str, website: str):
        self.asked.append(name)
        if self.fail:
            raise ProviderUnavailable("Venue page returned HTTP 503")
        return self.answer or {"found": False, "reason": "NO_NOTICE_ON_PAGE", "source_url": website}


class FakeSiteProvider(FakePlaceProvider):
    """The catalogue's places, each with a website so notices can be scanned."""

    def discover(self, destination: str) -> dict:
        payload = super().discover(destination)
        for index, item in enumerate(payload["items"], start=1):
            item["website"] = f"https://example.test/venue/{index}"
        return payload


class VenueNoticeActionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.provider = FakeNoticeProvider(
            {
                "found": True,
                "quote": "本館於 2027-01-01 休館 一日",
                "summary": "Closed for one day on 1 January 2027",
                "source_url": "https://example.test/venue/1",
                "model": "fake-1",
            }
        )
        self.actions = PlannerActions(
            Path(self.directory.name) / "notices.sqlite3",
            place_provider=FakeSiteProvider(),
            venue_notice_provider=self.provider,
        )
        self.trip = self.actions.create_trip(
            name="Taipei", destination="Taipei", planning_mode="explore_first"
        )
        self.actions.save_setup(
            trip_id=self.trip.trip_id,
            main_style=["sightseeing"],
            start_date="2030-01-01",
            end_date="2030-01-02",
            accommodation_status="booked",
            confirmed=True,
        )
        self.actions.discover_places(trip_id=self.trip.trip_id)
        for item in self.actions.get_latest_discovery(
            self.trip.trip_id
        ).candidates.as_dict()["candidates"]:
            self.actions.save_candidate_choice(
                trip_id=self.trip.trip_id, place_id=item["place_id"], action="must_do"
            )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_a_notice_never_reaches_the_optimizer(self) -> None:
        """The bar the ticket set, met structurally rather than by care: there is no code
        path from a notice to the optimizer, so a false one cannot delete a landmark."""

        before = self.actions._optimizer_input(self.trip.trip_id)
        report = self.actions.scan_venue_notices(self.trip.trip_id)
        after = self.actions._optimizer_input(self.trip.trip_id)

        self.assertGreater(report["notices_found"], 0)
        self.assertEqual(before, after)
        self.assertNotIn(
            "venue_notice",
            {fact.get("fact_type") for fact in after["facts"]},
        )
        # And nothing in the snapshot quotes the page.
        self.assertNotIn("休館", str(after))

    def test_a_notice_is_stored_with_its_quote_and_source(self) -> None:
        self.actions.scan_venue_notices(self.trip.trip_id)

        stored = self.actions.list_venue_notices(self.trip.trip_id)

        self.assertTrue(stored)
        for value in stored.values():
            self.assertEqual("本館於 2027-01-01 休館 一日", value["quote"])
            self.assertTrue(value["source_url"].startswith("https://example.test/"))

    def test_no_notice_stores_nothing(self) -> None:
        actions = PlannerActions(
            Path(self.directory.name) / "quiet.sqlite3",
            place_provider=FakeSiteProvider(),
            venue_notice_provider=FakeNoticeProvider(),
        )
        trip = actions.create_trip(name="T", destination="Taipei")
        actions.save_setup(
            trip_id=trip.trip_id, main_style=["sightseeing"], start_date="2030-01-01",
            end_date="2030-01-02", accommodation_status="booked", confirmed=True,
        )
        actions.discover_places(trip_id=trip.trip_id)
        for item in actions.get_latest_discovery(trip.trip_id).candidates.as_dict()["candidates"]:
            actions.save_candidate_choice(
                trip_id=trip.trip_id, place_id=item["place_id"], action="must_do"
            )

        report = actions.scan_venue_notices(trip.trip_id)

        self.assertGreater(report["checked"], 0)
        self.assertEqual(0, report["notices_found"])
        self.assertEqual({}, actions.list_venue_notices(trip.trip_id))

    def test_a_place_with_no_website_is_skipped_not_guessed_about(self) -> None:
        """Two of the pilot's nine sites are temples that publish nothing. There is
        nothing to read, so there is nothing to say."""

        actions = PlannerActions(
            Path(self.directory.name) / "nosite.sqlite3",
            place_provider=FakePlaceProvider(),  # no website field
            venue_notice_provider=FakeNoticeProvider(),
        )
        trip = actions.create_trip(name="T", destination="Taipei")
        actions.save_setup(
            trip_id=trip.trip_id, main_style=["sightseeing"], start_date="2030-01-01",
            end_date="2030-01-02", accommodation_status="booked", confirmed=True,
        )
        actions.discover_places(trip_id=trip.trip_id)
        for item in actions.get_latest_discovery(trip.trip_id).candidates.as_dict()["candidates"]:
            actions.save_candidate_choice(
                trip_id=trip.trip_id, place_id=item["place_id"], action="must_do"
            )

        report = actions.scan_venue_notices(trip.trip_id)

        self.assertEqual(0, report["checked"])
        self.assertGreater(report["without_website_or_held"], 0)

    def test_an_unreachable_site_is_reported_not_invented(self) -> None:
        """Beitou Hot Spring Museum times out from here on every attempt."""

        actions = PlannerActions(
            Path(self.directory.name) / "down.sqlite3",
            place_provider=FakeSiteProvider(),
            venue_notice_provider=FakeNoticeProvider(fail=True),
        )
        trip = actions.create_trip(name="T", destination="Taipei")
        actions.save_setup(
            trip_id=trip.trip_id, main_style=["sightseeing"], start_date="2030-01-01",
            end_date="2030-01-02", accommodation_status="booked", confirmed=True,
        )
        actions.discover_places(trip_id=trip.trip_id)
        for item in actions.get_latest_discovery(trip.trip_id).candidates.as_dict()["candidates"]:
            actions.save_candidate_choice(
                trip_id=trip.trip_id, place_id=item["place_id"], action="must_do"
            )

        report = actions.scan_venue_notices(trip.trip_id)

        self.assertEqual(0, report["notices_found"])
        self.assertGreater(report["failed"], 0)
        self.assertTrue(report["provider_errors"])

    def test_a_second_scan_does_not_re_read(self) -> None:
        self.actions.scan_venue_notices(self.trip.trip_id)
        first = len(self.provider.asked)

        again = self.actions.scan_venue_notices(self.trip.trip_id)

        self.assertEqual(first, len(self.provider.asked))
        self.assertEqual(0, again["checked"])


if __name__ == "__main__":
    unittest.main()
