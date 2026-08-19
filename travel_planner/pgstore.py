"""The same store, speaking Postgres.

`SQLiteStore` holds all 63 storage methods and all 65 statements, and every one
of them goes through `self.connect()`. That single chokepoint is why this file is
small: `PostgresStore` subclasses it and replaces the connection, so not one query
is rewritten and the two backends cannot drift apart in behaviour.

Only three things genuinely differ, and each is handled here rather than in the
queries:

- **Placeholders.** SQLite writes `?`, Postgres writes `%s`. Translated on the way
  through, outside string literals only.
- **Row access.** `sqlite3.Row` supports both `row["col"]` and `row[0]`. The store
  uses the named form 83 times and the positional form exactly once, inside
  `_initialize`, which is overridden below — so dict rows are enough.
- **The schema version.** `PRAGMA user_version` has no equivalent; it lives in a
  `schema_meta` row.

The Postgres DDL is *derived from* `store.SCHEMA` at import rather than
maintained beside it. A second hand-written schema is a second source of truth,
and the two would drift the first time a column was added to one of them.
"""

from __future__ import annotations

import re
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from .store import SCHEMA, SCHEMA_VERSION, SQLiteStore

# A trigger body in SQLite; Postgres needs a function call instead. Both the
# `CREATE TRIGGER` form and the bare `DROP TRIGGER IF EXISTS name;` form appear in
# SCHEMA, and the bare drop is invalid here because Postgres wants `ON table`.
_TRIGGER = re.compile(
    r"CREATE TRIGGER (?:IF NOT EXISTS )?(\w+)\s*\n(BEFORE \w+) ON (\w+)\s*\n"
    r"(WHEN[\s\S]*?\n)?BEGIN\s*\n\s*SELECT RAISE\(ABORT, '(.*?)'\);\s*\nEND;"
)
_BARE_DROP = re.compile(r"(?m)^DROP TRIGGER IF EXISTS \w+;\s*$")

_FUNCTIONS = """
CREATE OR REPLACE FUNCTION refuse_write() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '%', TG_ARGV[0];
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION refuse_write_unless_trip_deleting() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM trip_deletions WHERE trip_id = OLD.trip_id) THEN
        RAISE EXCEPTION '%', TG_ARGV[0];
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;
"""

_META = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key text PRIMARY KEY,
    value text NOT NULL
);
"""


def postgres_schema() -> str:
    """Translate `store.SCHEMA` into Postgres DDL.

    Mechanical throughout. Note what is deliberately *not* translated: SQLite
    writes booleans as `INTEGER CHECK (col IN (0, 1))` because it has no boolean
    type, and it is tempting to promote those to a real `boolean` here. That was
    tried and it breaks — `store.py` binds `int(flag)`, and Postgres refuses a
    smallint for a boolean column. Since the point of this port is that not one of
    the 65 statements changes, the column keeps the shape the code writes. A real
    boolean is a change to `store.py`, not to the schema, and it is not worth it.

    Anything not recognised here is left exactly as written, so an untranslatable
    construct fails loudly at apply time rather than silently becoming something
    else.
    """
    triggers = _TRIGGER.findall(SCHEMA)
    tables = _BARE_DROP.sub("", _TRIGGER.sub("", SCHEMA))
    tables = re.sub(r"\bTEXT\b", "text", tables)
    tables = re.sub(r"\bREAL\b", "double precision", tables)
    tables = re.sub(r"\bINTEGER\b", "bigint", tables)
    tables = re.sub(r"\n{3,}", "\n\n", tables)

    parts = [_META, tables, _FUNCTIONS]
    for name, timing, table, guard, message in triggers:
        function = "refuse_write_unless_trip_deleting" if guard else "refuse_write"
        parts.append(
            f"DROP TRIGGER IF EXISTS {name} ON {table};\n"
            f"CREATE TRIGGER {name} {timing} ON {table}\n"
            f"    FOR EACH ROW EXECUTE FUNCTION {function}('{message}');\n"
        )
    return "\n".join(parts)


def _to_pg_placeholders(sql: str) -> str:
    """`?` becomes `%s`, and every literal `%` is doubled.

    Both halves are load-bearing and both were got wrong before being measured.

    `?` is translated outside quoted strings only, or a literal question mark in
    copy would be read as a parameter and fail with a count mismatch, far from the
    edit that caused it.

    `%` is doubled **everywhere, including inside string literals, and regardless
    of whether this particular statement binds anything**. psycopg scans the whole
    query for placeholders whenever a parameters argument is passed, and
    `_Connection.execute` always passes one even when it is empty. So `LIKE
    '%abc%'` raises "only '%s', '%b', '%t' are allowed as placeholders, got '%a'",
    and a bare `100 % 7` raises "incomplete placeholder". Doubling unconditionally
    is the only rule that satisfies both; a version conditional on having
    parameters was tried and broke the second case.
    """
    out: list[str] = []
    in_string = False
    for character in sql:
        if character == "'":
            in_string = not in_string
            out.append(character)
        elif character == "?" and not in_string:
            out.append("%s")
        elif character == "%":
            out.append("%%")
        else:
            out.append(character)
    return "".join(out)


class _Connection:
    """Enough of the sqlite3 connection surface for the 65 statements above."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def execute(self, sql: str, parameters: tuple | list = ()) -> Any:
        cursor = self._raw.cursor()
        cursor.execute(_to_pg_placeholders(sql), tuple(parameters))
        return cursor

    def executescript(self, sql: str) -> None:
        self._raw.cursor().execute(sql)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()


class PostgresStore(SQLiteStore):
    """The store against a hosted Postgres, over a pooled connection.

    Opening a connection per operation is nearly free against a local file and
    ruinous over a network: measured against Neon from this machine, a single
    connect costs **2.58 seconds** of DNS, TCP, TLS and authentication. `store.py`
    calls `connect()` once per operation by design, so deleting 96 trips spent
    about four minutes doing nothing but handshakes. The pool pays that once and
    every later operation borrows an open connection — measured at 2580ms to
    788ms per read, and confirmed reusing: 16 requests over 2 physical
    connections.

    **What the pool cannot fix, and what to do about it.** Once the handshake is
    gone the remaining cost is distance. A round trip on an already-open
    connection to us-east-1 from here measures **278ms**, so any operation issuing
    five statements costs about a second and a half before the database has done
    any work. No amount of pooling touches that number; the only fix is to put the
    database and whatever calls it in the same region, and near the people using
    it. Treat the region as a performance decision, not a default.
    """

    #: Small on purpose. This is one local process, and Neon's free tier does not
    #: have connections to spare; the win is reuse, not concurrency.
    MIN_SIZE = 1
    MAX_SIZE = 8

    def __init__(self, url: str) -> None:
        self.url = url
        self._pool: Any = None
        self._pool_lock = threading.Lock()
        # F3: `SQLiteStore.__init__` sets `self.path`, and several inherited
        # methods reach for it. Both that use it here are overridden, so nothing
        # breaks today — but a method added upstream tomorrow would fail with an
        # AttributeError far from its cause. The attribute exists and says what it
        # is instead.
        self.path = f"<postgres {url.rsplit('@', 1)[-1].split('?')[0]}>"
        self._initialize()

    def _ensure_pool(self) -> Any:
        # Checked twice around a lock. `api/` serves on a threading server, so two
        # requests really can arrive here together; unlocked, both would see None
        # and each build a pool, and one of them would then be leaked with its
        # connections still open.
        if self._pool is not None:
            return self._pool
        with self._pool_lock:
            if self._pool is not None:
                return self._pool
            return self._build_pool()

    def _build_pool(self) -> Any:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(
            self.url,
            min_size=self.MIN_SIZE,
            max_size=self.MAX_SIZE,
            open=True,
            timeout=30,
            # `prepare_threshold=None` disables psycopg's automatic prepared
            # statements. They are a real speedup on a direct connection and they
            # break on a pooled one: pgbouncer in transaction mode hands the next
            # statement to a different backend session, which has never seen the
            # prepared name. Neon publishes both a pooled and a direct endpoint and
            # the caller may pass either, so this has to be safe for both.
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
        )
        return self._pool

    @contextmanager
    def connect(self) -> Iterator[Any]:
        pool = self._ensure_pool()
        with pool.connection() as raw:
            connection = _Connection(raw)
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()
            # No close: the connection goes back to the pool, which is the whole
            # point. `_Connection.close` stays for the non-pooled path only.

    def close(self) -> None:
        """Give the connections back. A long-lived process should call this on the
        way out; a short one can leave it to interpreter shutdown."""
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(postgres_schema())
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            version = int(row["value"]) if row else 0
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema {version} is newer than supported {SCHEMA_VERSION}"
                )
            if 0 < version < SCHEMA_VERSION:
                self._copy_before_bump(version)
            connection.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (str(SCHEMA_VERSION),),
            )

    def _copy_before_bump(self, version: int) -> None:
        """Refuse, rather than pretend a hosted database was copied.

        `SQLiteStore` copies the file before an irreversible bump, and that copy is
        the only way back. A hosted database is not a file: the equivalent is a
        branch or a dump, and which one is an operating decision nobody can take
        from inside this process. Refusing is the honest failure; migrating and
        claiming a backup exists is not.
        """
        raise RuntimeError(
            f"Refusing to migrate a hosted database from schema {version} to "
            f"{SCHEMA_VERSION}: take a branch or a dump first, then set "
            f"schema_meta.schema_version by hand."
        )
