# Live Supabase structure backups

These are schema-only recovery artifacts captured from the live `public` schema. They
are not the schema source of truth: application DDL still comes from `store.SCHEMA` via
`travel_planner.pgstore.postgres_schema()` and generates `supabase/schema.sql`.

## Current snapshot

`supabase-public-schema-2026-08-28.sql` was read from Supabase PostgreSQL 17.6 with
`pg_dump` 18.6. It contains the deployed structure that the generated schema cannot see:

- 24 tables, including the hosted-only `jobs` queue;
- `trips.owner_token` and its index;
- 3 indexes, 8 immutability triggers, and 2 trigger functions;
- primary keys, unique constraints, checks, and foreign keys.

It contains **no table rows, passwords, connection strings, owners, grants, Supabase
Auth/Storage schemas, or extensions outside `public`**. Consequently, it can rebuild an
empty planner database but cannot recover trips or provider-cache contents.

Verify the committed artifact before using it:

```bash
shasum -a 256 -c supabase/backups/SHA256SUMS
```

## Refresh the snapshot

The command reads `POSTGRES_URL_NON_POOLING` from the ignored `.env` file and passes its
components to `pg_dump` through `PG*` environment variables, keeping the password out of
the command line and dump. Install the client once with `brew install libpq`, then run:

```bash
uv run --locked python scripts/backup_supabase_schema.py
```

Review the resulting SQL, update `SHA256SUMS`, and commit it after each live structural
change. The script refuses a dump missing the core tables, job queue, or trigger function,
and refuses to save one containing the database password.

## Restore into a new database

Configure the target as a libpq service named `target`, then restore into a **new, empty
database only**:

```bash
PGSERVICE=target /opt/homebrew/opt/libpq/bin/psql \
  --set ON_ERROR_STOP=1 \
  --single-transaction \
  --command 'DROP SCHEMA public CASCADE' \
  --file supabase/backups/supabase-public-schema-2026-08-28.sql
```

The `DROP SCHEMA` is destructive. It is required because PostgreSQL creates `public` in a
new database and the dump recreates it. Never run this command against the current live
project. After restoring, start the app once so it records the current `schema_version`.
