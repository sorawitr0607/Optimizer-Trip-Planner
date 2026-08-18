# Postgres migration — where this actually stands

The owner chose the hosted route (Vercel + a Postgres, currently Neon). This
directory holds the database half of it. **Read the status honestly before
relying on any of it.**

## Done, and verified against a real database

- `schema.sql` translates all **22 tables** and **8 triggers** from
  `travel_planner/store.py` at `SCHEMA_VERSION 14`.
- Applied cleanly to Postgres 17.10.
- The append-only contract was tested against the live database, not reasoned
  about: updating a plan version is refused, deleting one is refused, and
  deleting it *does* succeed once a `trip_deletions` marker exists. **3 of 3
  behaviours match the SQLite contract**, including the identical error text, so
  any caller matching on that message keeps working.

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

## Not done — and none of this is small

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

## Left alone on purpose

The database already contained an unrelated `quiz_results` table. Nothing here
touches it. "Replace all the data" was taken to mean this project's tables, not
somebody else's.
