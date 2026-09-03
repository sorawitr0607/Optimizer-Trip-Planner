# Postgres migration — where this actually stands

The owner chose the hosted route (Vercel + a Postgres, currently Neon). This
directory holds the database half of it. **Read the status honestly before
relying on any of it.**

## Done, and verified against a real database

The hosted database is **Supabase Postgres 17.6 in `ap-southeast-1`**. It began on
Neon in `us-east-1` and was moved for one measured reason, recorded below.

- `schema.sql` carries all **22 tables** and **8 triggers** at `SCHEMA_VERSION 14`,
  and is generated from `travel_planner.pgstore.postgres_schema()` so it cannot
  drift from `store.SCHEMA`.
- `PostgresStore` subclasses `SQLiteStore` and replaces only `connect()`, so none
  of the 65 statements is rewritten and the backends cannot diverge in behaviour.
- **The data is migrated and content-verified**: 7023 `paid_usage` rows and 293
  `provider_cache` rows, sha256 digests over every column identical to the SQLite
  source, ledger exactly US$5.0745.
- The append-only contract was tested against the live database rather than
  reasoned about: UPDATE and DELETE on the ledger are refused with the original
  message, and a guarded delete succeeds once a `trip_deletions` marker exists.

## Live recovery snapshot

The exact deployed `public` structure is backed up at
`backups/supabase-public-schema-2026-08-28.sql`, with its checksum and recovery procedure
in `backups/README.md`. Unlike generated `schema.sql`, this snapshot also contains the
runtime `jobs` queue, `trips.owner_token`, and their indexes. It is schema-only and safe
to commit: it contains no rows, credentials, owners, or grants.

This discharges **structure recovery only**. It does not preserve trips, cached provider
responses, or any other row data; a private data dump remains a separate decision and
must never be committed to this public repository.

## The quota ran out, 2026-09-03 — and what that means for the region table below

Supabase restricted the project: **20.2 GB of egress against a 5.5 GB allowance**, requests
dropped until 19 September. Two thirds of that was the `paid_usage` full-table read fixed on
28 August; the rest was the candidate catalogue, at 807 KB a read.

**The region table below compares Supabase `ap-southeast-1` with Neon `us-east-1`, so its
Neon column is distance and not vendor.** The like-for-like measurement was taken on
2026-09-03, same machine, same pool, and it settles the question:

| operation | Supabase `ap-southeast-1` | Neon `us-east-1` | **Neon `ap-southeast-1`** |
|---|---|---|---|
| connection handshake | 472 ms | 2580 ms | **365 ms** |
| round trip, open connection | 42 ms | 278 ms | **37 ms** |
| read | 108 ms | 788 ms | **38 ms** |

Neon in the same region is as fast or faster on every figure. The 278 ms was Bangkok to
Virginia.

## The move to Neon `ap-southeast-1`, 2026-09-03

Done and verified: 19,099 rows into 16 tables, every table's count equal to the dump, trip
ids unique, all 11 owner tokens present, ledger US$9.3160, `schema_version` 14. The app was
run against it before anything was pointed at it — `list_trips` and `journey` both 200 with
no server error.

**Two things a generated schema cannot see, and the restore has to add them.**
`postgres_schema()` covers neither the `jobs` queue (its own idempotent DDL, deliberately
outside `SCHEMA_VERSION`) nor `trips.owner_token` (an additive `ALTER` in `owners.py`). A
restore that applies only the generated schema produces a database the dump will not load
into — `COPY` matched by position and failed with "extra data after last expected column".

**`jobs` is not restored, and should not be.** Its docstring is the argument: a queue holds
no planning truth and can be dropped and rebuilt. Every row in a dump is a finished job
carrying `result_json` — 57 MB of the 79 MB database. It also cannot be restored positionally
anyway: `progress` was added by a later `ALTER`, so on an older database it sits last while
`jobs.DDL` declares it twelfth, and the load fails on the type mismatch. `--include-transient`
exists for anyone who needs to try; column lists in the dump are the durable fix and nothing
needs them yet.

**No trigger needs disabling.** All eight immutability triggers are `BEFORE UPDATE` or
`BEFORE DELETE`; `COPY` is an insert and never fires one. The first version of the script set
`session_replication_role = replica` out of caution and failed on Neon, whose `neondb_owner`
is not superuser — the fix was to check what the triggers guard rather than to find a way
round the permission.

The migration path is short because structure comes from code:

1. `scripts/restore_hosted_database.py --url … --rows data/…sql.gz` applies
   `postgres_schema()` and loads the rows, parents first, with the immutability triggers
   held off for the load only.
2. Point `TOURIST_DB_URL` at the new host.

The database is **79 MB**, which fits every free tier. Row dumps are gitignored and must
stay that way: they carry trips, owner tokens, addresses and ages, and this repository is
public. `backups/` holds structure only, which is why it is committable.

**Moving host without shrinking the catalogue only moves the problem** — Neon's free tier
is also 5 GB of egress a month.

### Region is a performance decision, not a default

Measured from the owner's machine, same code, same pool, only the region differs:

| operation | Supabase `ap-southeast-1` | Neon `us-east-1` |
|---|---|---|
| connection handshake | 472 ms | 2580 ms |
| round trip, open connection | **42 ms** | **278 ms** |
| read | 108 ms | 788 ms |
| write | 110 ms | 777 ms |
| delete (5 statements) | 922 ms | 6242 ms |

Connection pooling was added first and was worth it — it removed a 2.58s
handshake from every single operation, since `store.py` calls `connect()` once per
operation by design. But pooling cannot touch distance. Once the handshake is
gone, every statement still costs one round trip, so a five-statement operation
from Bangkok to Virginia could never beat about 1.4 seconds. Moving the database
to the same continent as its users was worth more than any code change here.

## Three translations that are judgement, not syntax

1. **`PRAGMA user_version` has no equivalent.** The version lives in a
   `schema_meta` row. The consequence is bigger than the storage: `store.py`
   refuses a schema bump unless it can first copy the database, and that copy is
   the only way back. Against a hosted database it cannot be a file copy — it has
   to be a branch or a dump, and that is an operating decision the owner has to
   make. **Until it is made, do not bump the schema against a hosted database.**
2. **Booleans.** SQLite writes them as `INTEGER CHECK (col IN (0,1))`. Postgres
   has the real type and this schema uses it, so every read path in `store.py`
   comparing a flag to `0`/`1` has to be checked.
3. **`RAISE(ABORT, …)`** becomes a PL/pgSQL function per rule, raising the same
   message.

## Historical pre-deployment gaps — retained for the implementation record

The bullets below describe the state before the hosted port landed. They are history,
not the current release status above.

- **`store.py` still speaks SQLite only.** 65 statements and 179 `?` placeholders
  (Postgres wants `%s`). The good news is the seam is real: `sqlite3` is imported
  in exactly one file, `actions.py` touches no SQL, and the whole surface is 63
  functions. The port is mechanical but it is not trivial, and it must keep the
  **27 optimizer regressions byte-identical** and all 538 tests green.
- **The long operations do not fit a serverless request.** A full proposal takes
  ~52s and a measured end-to-end flow took 210s; discovery is 30-90s of Overpass.
  These need a job table and a worker, which is a design change to `actions.py`'s
  callers, not a deployment setting.
- **No data has been migrated.** The schema is empty. `data/tourist.sqlite3` is
  the owner's real trip and has not been touched.
- **`psycopg` is currently a dev dependency.** Python runtime dependencies are
  capped at one (`xlsxwriter`) by decision; making the app talk to Postgres in
  production makes psycopg the second, which is a decision to take deliberately.

## An incident worth keeping

While building the port, `TOURIST_DB_URL` was exported in the shell that ran the
test suite. `open_store` selects Postgres from that variable and **ignores the
path it was handed**, so all 544 tests silently redirected onto the hosted
database: 96 test trips with their child rows, and seven fabricated rows in the
append-only ledger including `google_places` charges at US$0.025 that were never
made. The ledger read US$5.1505 against a true US$5.0745.

Everything was removed and the ledger restored, which required dropping the
unconditional delete guard for exactly one statement and putting it straight back
— recorded because a ledger must never be quietly edited.

`tests/__init__.py` now clears `TOURIST_DB_URL`, exactly as it already clears
`TOURIST_LOCAL_SECRETS`, and for the same reason: a test must not be able to reach
a real one. Verified by running the full suite with the variable exported and
finding zero rows written.

## Secrets

No connection string or key is committed anywhere in this repository. Everything
was passed through the shell for the session that needed it. The Supabase
`service_role` key and JWT secret in particular bypass row-level security and sign
tokens respectively; if they have ever been pasted somewhere they should be
rotated in Supabase → Settings → API.
