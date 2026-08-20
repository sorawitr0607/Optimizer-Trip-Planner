"""Which trips belong to whom, without accounts.

Ten people sharing one deployment need their trips kept apart. What they do not
need is a login: the product's promise is "no account", and a random token the
browser generates and keeps is enough to separate ten strangers' trips. It is not
a security boundary and is not offered as one -- someone who copies another
person's token gets their trips, exactly as someone who copies a share link does.
It stops the accidental case, which is the whole of the problem here: without it
`list_trips` returns everyone's trips and `/` opens inside whichever was newest.

**Additive, and outside `SCHEMA_VERSION` on purpose.** Bumping 14 to 15 would reach
`PostgresStore._copy_before_bump`, which refuses to migrate a hosted database
because the copy a SQLite bump makes has no hosted equivalent it can honestly
claim. A nullable column and an index need none of that ceremony, so this follows
the same route `jobs.py` takes: idempotent DDL, run once, version untouched.

A trip with no owner is nobody's. Those are the rows that existed before this, and
the first caller carrying a token adopts them -- which for a deployment whose owner
is the person deploying it is the right answer, and is why the site should be
opened once before the link is shared.
"""

from __future__ import annotations

from typing import Any

#: `ADD COLUMN IF NOT EXISTS` is Postgres-only -- SQLite rejects it outright -- so the
#: column is looked for first. `CREATE INDEX IF NOT EXISTS` both backends do accept.
_ADD_COLUMN = "ALTER TABLE trips ADD COLUMN owner_token TEXT"
_ADD_INDEX = "CREATE INDEX IF NOT EXISTS trips_owner_token ON trips (owner_token)"


def _columns(connection: Any) -> set[str]:
    """The column names of `trips`, asked in a way both backends answer.

    A cursor's `description` is the one place SQLite and psycopg agree without a
    dialect-specific catalogue query -- `PRAGMA table_info` against
    `information_schema.columns` would be two code paths for one question.
    """

    cursor = connection.execute("SELECT * FROM trips LIMIT 0")
    return {str(column[0]) for column in (cursor.description or ())}


def ensure_owner_column(store: Any) -> None:
    """Give `trips` its owner column. Safe to call on every open."""

    with store.connect() as connection:
        if "owner_token" in _columns(connection):
            return
        connection.execute(_ADD_COLUMN)
        connection.execute(_ADD_INDEX)


def claim_unowned(store: Any, owner: str) -> int:
    """Hand every ownerless trip to `owner`. Returns how many moved.

    Run once, by whoever arrives first with a token. A second caller finds nothing
    left to claim, which is what makes this safe to attempt on every request.
    """

    if not owner:
        return 0
    with store.connect() as connection:
        cursor = connection.execute(
            "UPDATE trips SET owner_token = ? WHERE owner_token IS NULL", (owner,)
        )
        return int(getattr(cursor, "rowcount", 0) or 0)
