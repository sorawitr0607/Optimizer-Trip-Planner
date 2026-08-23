from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

import scripts.capture_screen_baselines as capture
import scripts.check_screen_baselines as gate


class StaleCaptureGuardTest(unittest.TestCase):
    """`WF-025`. A green gate that compared nothing is worse than a red one.

    Capturing is manual — it needs a running server and headless Chrome — so this stage
    compares whatever was last written to `screen-current`. Three times on 2026-08-07
    that was an image taken before the frontend changed, and it printed PASS having
    compared images that did not show the current code.
    """

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.current = self.root / "current"
        self.source = self.root / "web" / "src"
        self.current.mkdir(parents=True)
        self.source.mkdir(parents=True)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def run_guard(self) -> list[str]:
        with patch.object(gate, "ROOT", self.root), patch.object(
            gate, "CURRENT", self.current
        ), patch.object(gate, "SOURCE", self.source):
            return gate.stale_sources()

    def test_a_source_edited_after_the_capture_is_named(self) -> None:
        (self.current / "places-light-en.png").write_bytes(b"x")
        time.sleep(0.01)
        (self.source / "PlacesPage.tsx").write_text("edited after the photograph")

        self.assertEqual(["web/src/PlacesPage.tsx"], self.run_guard())

    def test_a_capture_newer_than_every_source_is_clean(self) -> None:
        (self.source / "PlacesPage.tsx").write_text("edited first")
        time.sleep(0.01)
        (self.current / "places-light-en.png").write_bytes(b"x")

        self.assertEqual([], self.run_guard())

    def test_it_compares_against_the_oldest_capture_not_the_newest(self) -> None:
        """The 36 images are written over about a minute. An edit landing mid-run would
        otherwise be judged against whichever screens happened to be shot after it."""

        (self.current / "first.png").write_bytes(b"x")
        time.sleep(0.01)
        (self.source / "PlacesPage.tsx").write_text("edited during the capture run")
        time.sleep(0.01)
        (self.current / "last.png").write_bytes(b"x")

        self.assertEqual(["web/src/PlacesPage.tsx"], self.run_guard())

    def test_only_frontend_sources_count(self) -> None:
        (self.current / "places-light-en.png").write_bytes(b"x")
        time.sleep(0.01)
        # A screenshot cannot show a change to these, so they must not fail the gate.
        (self.source / "notes.md").write_text("not rendered")
        (self.source / "fixture.json").write_text("{}")

        self.assertEqual([], self.run_guard())

    def test_no_captures_means_nothing_to_call_stale(self) -> None:
        (self.source / "PlacesPage.tsx").write_text("edited")

        self.assertEqual([], self.run_guard())


class UncomparedScreenTest(unittest.TestCase):
    """An approved screen with no capture must fail, not be mentioned in passing.

    It used to append a note and `continue`, so a screen that was never photographed
    left the gate green — `stable_capture` declines to write an image it cannot
    settle, which is exactly how a flaky screen would drop out of the comparison
    without anyone noticing. Same family as the owner-token defect above: the gate
    reported on the screens it happened to look at, not on the set it approved.
    """

    def _run(self, capture_names: tuple[str, ...]) -> int:
        from PIL import Image

        with TemporaryDirectory() as directory:
            root = Path(directory)
            baselines, current = root / "baselines", root / "current"
            baselines.mkdir(), current.mkdir()
            for name in ("setup-light-en.png", "places-light-en.png"):
                Image.new("RGB", (8, 8), "white").save(baselines / name)
            for name in capture_names:
                Image.new("RGB", (8, 8), "white").save(current / name)
            with patch.object(gate, "BASELINES", baselines), patch.object(
                gate, "CURRENT", current
            ), patch.object(gate, "stale_sources", return_value=[]):
                return gate.main()

    def test_a_screen_that_was_not_captured_fails_the_gate(self) -> None:
        self.assertEqual(1, self._run(("setup-light-en.png",)))

    def test_a_complete_matching_set_passes(self) -> None:
        self.assertEqual(
            0, self._run(("setup-light-en.png", "places-light-en.png"))
        )


class CaptureOwnerSessionTest(unittest.TestCase):
    """Every screen in one run must be the *same owner*, and must be an owner.

    The first half of that was already asserted and was not enough. Trips are keyed
    to a random `localStorage` token, a shared throwaway Chrome profile mints no
    token at all, and so 52 of 56 baselines photographed the unknown-trip recovery
    screen. Both sets agreed, the gate passed, and it covered nothing — a whole
    round of "the baselines are green" rested on an error page compared against
    itself. One shared profile is necessary and says nothing about whose it is.
    """

    def _run(self) -> tuple[list[str], list[str], list[int]]:
        """Capture one view: the profiles used, the URLs asked for, and the budgets."""

        view = capture.View("", (500, 844), (capture.Screen("setup", "/setup"),))
        profiles: list[str] = []
        urls: list[str] = []

        budgets: list[int] = []

        def record(*args, **kwargs) -> bool:
            urls.append(args[1])
            profiles.append(args[4])
            budgets.append(kwargs.get("budget"))
            return True

        with TemporaryDirectory() as directory, patch.object(
            capture, "ROOT", Path(directory)
        ), patch.object(
            capture, "CURRENT", Path(directory) / "current"
        ), patch.object(capture, "VIEWS", (view,)), patch.object(
            capture, "THEMES", ("light", "dark")
        ), patch.object(capture, "LANGUAGES", ("en",)), patch.object(
            capture, "alive", return_value=True
        ), patch.object(capture, "chrome", return_value="chrome"), patch.object(
            capture, "stable_capture", side_effect=record
        ), patch(
            "sys.argv",
            [
                "capture_screen_baselines.py",
                "--trip", "trip_test",
                "--owner", "owner-token-1",
            ],
        ):
            self.assertEqual(0, capture.main())
        return profiles, urls, budgets

    def test_one_browser_profile_is_reused_for_the_whole_capture_set(self) -> None:
        profiles, _, _ = self._run()

        self.assertEqual(2, len(profiles))
        self.assertEqual(1, len(set(profiles)))

    def test_every_screen_is_asked_for_as_the_trip_owner(self) -> None:
        _, urls, _ = self._run()

        self.assertEqual(2, len(urls))
        for url in urls:
            self.assertIn("baseline_owner=owner-token-1", url)

    def test_each_screen_carries_its_own_virtual_time_budget(self) -> None:
        # `/places` needs 15000 and every other screen must not pay for it: raising the
        # budget globally tripled a 128-image run. The fixture screen is "setup", so the
        # default is what should arrive here.
        _, _, budgets = self._run()

        self.assertEqual([5000, 5000], budgets)
        places = next(
            screen for view in capture.VIEWS for screen in view.screens
            if screen.name == "places"
        )
        self.assertEqual(capture.PLACES_BUDGET, places.budget)
        self.assertGreater(capture.PLACES_BUDGET, 5000)

    def test_the_owner_token_is_required(self) -> None:
        # Optional, it would go on being omitted, and the failure is silent: the
        # images are written, the gate compares them, and every one is the same
        # recovery screen.
        with patch(
            "sys.argv", ["capture_screen_baselines.py", "--trip", "trip_test"]
        ), self.assertRaises(SystemExit):
            capture.main()

if __name__ == "__main__":
    unittest.main()
