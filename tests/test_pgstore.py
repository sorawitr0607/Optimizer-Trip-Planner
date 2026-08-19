"""The Postgres URL, before anything tries to connect with it.

No database is reached here. `normalise_url` is a pure string function, and the
one connection attempt goes to a host that does not resolve -- which is the
point: a *parameter* is rejected while the URI is parsed, before any socket, so
the two failures are distinguishable without a server.
"""

from __future__ import annotations

import unittest

import psycopg

from travel_planner.pgstore import normalise_url


class NormaliseUrlTest(unittest.TestCase):
    def test_the_provider_url_is_accepted_as_given(self):
        # This is POSTGRES_URL exactly as Supabase and Vercel present it. Copying
        # it into TOURIST_DB_URL is the obvious thing to do, and it failed every
        # request with "internal_error" because libpq rejects the Prisma flag.
        given = ("postgres://postgres.ref:pw@aws-0-ap-southeast-1.pooler.supabase.com"
                 ":6543/postgres?sslmode=require&pgbouncer=true")
        self.assertNotIn("pgbouncer", normalise_url(given))

    def test_sslmode_survives(self):
        # Dropping this would downgrade the connection silently, which is a worse
        # failure than the one being fixed.
        self.assertIn("sslmode=require", normalise_url(
            "postgres://u:p@h:6543/db?sslmode=require&pgbouncer=true"))

    def test_other_libpq_options_survive(self):
        out = normalise_url("postgres://u:p@h:5432/db?application_name=planner&connect_timeout=10")
        self.assertIn("application_name=planner", out)
        self.assertIn("connect_timeout=10", out)

    def test_a_url_with_no_query_is_untouched(self):
        plain = "postgres://u:p@h:5432/postgres"
        self.assertEqual(normalise_url(plain), plain)

    def test_psycopg_rejects_the_flag_and_accepts_it_once_removed(self):
        raw = "postgres://u:p@nowhere.invalid:6543/postgres?sslmode=require&pgbouncer=true"
        with self.assertRaises(psycopg.ProgrammingError):
            psycopg.connect(raw, connect_timeout=1)
        # Now it gets far enough to fail on the hostname, which is the proof that
        # the URI itself is valid.
        with self.assertRaises(psycopg.OperationalError):
            psycopg.connect(normalise_url(raw), connect_timeout=1)


if __name__ == "__main__":
    unittest.main()
