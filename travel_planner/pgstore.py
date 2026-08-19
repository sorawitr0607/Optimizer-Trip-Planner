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
    """`?` becomes `%s`, but never inside a quoted string.

    A literal question mark in copy would otherwise be read as a parameter and the
    statement would fail with a count mismatch — confusing, and far from the edit
    that caused it. `%` is doubled for the same reason, since psycopg reads it as
    the start of a placeholder.
    """
    out: list[str] = []
    in_string = False
    for character in sql:
        if character == "'":
            in_string = not in_string
            out.append(character)
        elif character == "?" and not in_string:
            out.append("%s")
        elif character == "%" and not in_string:
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
    def __init__(self, url: str) -> None:
        self.url = url
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[Any]:
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(self.url, connect_timeout=20, row_factory=dict_row)
        connection = _Connection(raw)
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

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
