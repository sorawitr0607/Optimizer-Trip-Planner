from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from scripts.backup_supabase_schema import REQUIRED_OBJECTS, connection_environment


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "supabase/backups/supabase-public-schema-2026-08-28.sql"


class SupabaseSchemaBackupTest(unittest.TestCase):
    def test_connection_secret_stays_in_pg_environment(self) -> None:
        values = connection_environment(
            "postgresql://planner:p%40ss@db.example:6543/postgres?sslmode=require"
        )

        self.assertEqual("db.example", values["PGHOST"])
        self.assertEqual("6543", values["PGPORT"])
        self.assertEqual("planner", values["PGUSER"])
        self.assertEqual("p@ss", values["PGPASSWORD"])
        self.assertEqual("require", values["PGSSLMODE"])

    def test_committed_backup_is_complete_secret_free_and_checksummed(self) -> None:
        text = BACKUP.read_text(encoding="utf-8")
        for name in (*REQUIRED_OBJECTS, "owner_token", "CREATE INDEX jobs_claimable"):
            self.assertIn(name, text)
        for forbidden in (
            "postgresql://",
            "postgres://",
            "supabase.co",
            "COPY public.",
            "INSERT INTO public.",
            " GRANT ",
            " OWNER TO ",
        ):
            self.assertNotIn(forbidden, text)

        expected = (ROOT / "supabase/backups/SHA256SUMS").read_text().split()[0]
        self.assertEqual(expected, hashlib.sha256(BACKUP.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
