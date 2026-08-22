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


class CaptureOwnerSessionTest(unittest.TestCase):
    """Every screen in one run must carry the same browser owner token."""

    def test_one_browser_profile_is_reused_for_the_whole_capture_set(self) -> None:
        view = capture.View("", (500, 844), (capture.Screen("setup", "/setup"),))
        profiles: list[str] = []

        def record(*args) -> bool:
            profiles.append(args[4])
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
            "sys.argv", ["capture_screen_baselines.py", "--trip", "trip_test"]
        ):
            self.assertEqual(0, capture.main())

        self.assertEqual(2, len(profiles))
        self.assertEqual(1, len(set(profiles)))

if __name__ == "__main__":
    unittest.main()
