# Post-mortem: the queue that starved on a stale variable, 2026-09-14

Production "find places" presses failed after ~5 min with `job_timeout`
while the Mac worker sat silent on `draining PostgresStore`. No code had
changed. The full ledger is B1–B23 in the session handoff; this records the
shape of the failure and what now prevents it.

## Timeline (all 2026-09-14)

- Worker started in the foreground, connected (`draining PostgresStore`),
  never printed another line across presses.
- Browser: `job_timeout` on every press — 5 min of silence, meaning no worker
  ever claimed the job (a claim writes `progress 0` immediately).
- `rows=0` from the jobs-peek against the worker's own URL: the Mac database
  had never seen a job, while production presses demonstrably existed.
  A stray worker or a stranded `RUNNING` row would both have left rows
  behind — both ruled out by that one number.
- Owner confirmed: Vercel Production had **both** `TOURIST_DB_URL` (old
  Supabase) and `STORAGE_2_POSTGRES_URL` (Neon) set. The resolver is
  first-wins, so every press enqueued into Supabase while the worker drained
  Neon. The Mac `.env` had already been moved to Neon — correct, and exactly
  why its queue read empty.
- Fix: deleted the stale `TOURIST_DB_URL` from Vercel, redeployed (env edits
  do nothing until a redeploy), one press → claimed in seconds,
  `rows=1 ... status: done, attempts: 1, progress: 4`.

## Why it was silent

First-wins precedence is tested contract (`test_the_deliberate_one_wins`:
`TOURIST_DB_URL` is the escape hatch), and nothing anywhere said which
variable won. `draining PostgresStore` proved *a* Postgres, never *which*
one. The failure therefore read as "worker idle, queue broken" on both
sides with nothing disagreeing in any log.

## What now prevents it

- `store.hosted_database_conflict()` reports two variables holding
  *different* URLs (equal values stay a legal mirror). Names only cross the
  boundary — never values, which carry credentials.
- `api/rpc.py:_planner()` raises it as `ConfigurationError`, so the
  deployment answers 503 `not_configured` naming both variables instead of
  routing by precedence.
- `travel_planner/worker.py` prints `FAILED:` and exits 2 rather than
  draining the wrong database looking healthy.
- Precedence itself is unchanged: the escape-hatch contract still passes
  untouched.

## Stale things removed, and one kept

- Removed: the unused `SUPABASE_*` template block in `.env.example`
  (nothing reads those keys), and the `MIGRATION.md` step that advised
  hand-pointing `TOURIST_DB_URL` at a new host — that advice caused this.
- Kept: `supabase/backups/`, `schema.sql`, and the backup script plus its
  test. That is the only committed structure recovery, and the script reads
  `POSTGRES_URL_NON_POOLING`, so it already works against Neon.

## Follow-ups

- `tests.test_rpc` (23 existing + 2 new tests) was verified 2026-09-14 on
  the owner's Mac: 25 tests, OK. The sandbox denies loopback binds, so it
  had errored here with the 11 other pre-existing socket errors; the
  conflict logic itself was additionally verified socket-free.
- The orphaned rows on the old Supabase project need no cleanup: no worker
  drains it, and fresh presses land on Neon.
