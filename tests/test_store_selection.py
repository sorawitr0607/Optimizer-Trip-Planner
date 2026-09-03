"""Which database a store opens, and the guard that keeps a test off a real one.

`open_store` ignores the path it is handed whenever a hosted URL is in the environment.
That is deliberate — it is how the worker and the serverless function reach Postgres — and
it is also how a suite reaches a live database by accident. It has happened: 96 test trips
plus their setups, choices, discovery runs and split rows were written into the owner's
hosted database while the port was being built, and a "Coverage probe" trip on the run that
found the same hole in `scripts/check.py`.

So the list of variables and the guard that clears them are asserted to be the same list.
Adding a name to one without the other is the whole failure mode.
"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from travel_planner.store import (
    HOSTED_URL_VARIABLES,
    SQLiteStore,
    forget_hosted_database,
    hosted_database_url,
    open_store,
)


class HostedUrlResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.held = {name: os.environ.get(name) for name in HOSTED_URL_VARIABLES}
        forget_hosted_database()

    def tearDown(self) -> None:
        for name, value in self.held.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_no_url_means_the_file_on_disk(self) -> None:
        with TemporaryDirectory() as directory:
            store = open_store(Path(directory) / "local.sqlite3")
            self.assertIsInstance(store, SQLiteStore)

    def test_every_name_is_honoured(self) -> None:
        """Each variable on its own selects the hosted database."""

        for name in HOSTED_URL_VARIABLES:
            forget_hosted_database()
            os.environ[name] = "postgresql://user:pw@example.invalid/db"
            self.assertEqual(
                "postgresql://user:pw@example.invalid/db",
                hosted_database_url(),
                f"{name} did not select the hosted database",
            )

    def test_the_deliberate_one_wins(self) -> None:
        """`TOURIST_DB_URL` is the escape hatch, so it outranks the integration's."""

        for name in HOSTED_URL_VARIABLES:
            os.environ[name] = f"postgresql://user:pw@{name}.invalid/db"
        self.assertIn("TOURIST_DB_URL", hosted_database_url())
        self.assertEqual("TOURIST_DB_URL", HOSTED_URL_VARIABLES[0])

    def test_blank_and_whitespace_are_not_a_url(self) -> None:
        # A variable that exists but is empty is not a destination, and treating it as
        # one fails somewhere less obvious than here.
        for value in ("", "   ", "\t"):
            forget_hosted_database()
            os.environ[HOSTED_URL_VARIABLES[0]] = value
            self.assertEqual("", hosted_database_url())

    def test_the_guard_clears_every_name_the_resolver_reads(self) -> None:
        """The assertion this file exists for.

        A guard that pops one name while `open_store` reads two is a suite that can be
        redirected to production by an exported variable. Checked by *behaviour* rather
        than by comparing two literals, so it holds however the guard is written.
        """

        for name in HOSTED_URL_VARIABLES:
            os.environ[name] = "postgresql://user:pw@example.invalid/db"
        forget_hosted_database()
        for name in HOSTED_URL_VARIABLES:
            self.assertIsNone(
                os.environ.get(name),
                f"{name} survives forget_hosted_database(), so a test could reach it",
            )
        self.assertEqual("", hosted_database_url())

    def test_the_suite_is_already_guarded(self) -> None:
        """`tests/__init__.py` runs the guard on import, so this is true right now."""

        import tests  # noqa: F401  -- the import is the thing being asserted

        self.held = {name: None for name in HOSTED_URL_VARIABLES}
        for name in HOSTED_URL_VARIABLES:
            self.assertIsNone(os.environ.get(name), f"{name} is set during the suite")


if __name__ == "__main__":
    unittest.main()
