-- Optimizer Trip Planner — Postgres schema.
--
-- GENERATED from `travel_planner.pgstore.postgres_schema()`, which derives it from
-- `store.SCHEMA`. Do not edit by hand: a second hand-written schema is a second
-- source of truth, and the two drift the first time a column is added to one.
-- Regenerate with:  uv run python -c "from travel_planner.pgstore import postgres_schema; print(postgres_schema())"
--
-- The one translation worth knowing is the one deliberately NOT made: SQLite has
-- no boolean and writes flags as `INTEGER CHECK (col IN (0,1))`. Promoting those
-- to a real `boolean` was tried and breaks, because `store.py` binds `int(flag)`
-- and Postgres refuses a smallint for a boolean column. The column keeps the shape
-- the code writes; a real boolean is a change to store.py, not to this file.


CREATE TABLE IF NOT EXISTS schema_meta (
    key text PRIMARY KEY,
    value text NOT NULL
);


CREATE TABLE IF NOT EXISTS trips (
    id text PRIMARY KEY,
    name text NOT NULL,
    destination text NOT NULL,
    planning_mode text NOT NULL CHECK (planning_mode IN ('explore_first', 'ready_to_schedule')),
    language text NOT NULL CHECK (language IN ('en', 'th')),
    created_at text NOT NULL
);

-- A transaction-scoped marker lets an intentional whole-trip deletion remove
-- otherwise immutable history without making ordinary row deletion possible.
CREATE TABLE IF NOT EXISTS trip_deletions (
    trip_id text PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS plan_versions (
    id text PRIMARY KEY,
    trip_id text NOT NULL,
    parent_version_id text,
    cause text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    created_at text NOT NULL,
    UNIQUE (trip_id, id),
    FOREIGN KEY (trip_id) REFERENCES trips(id),
    FOREIGN KEY (trip_id, parent_version_id) REFERENCES plan_versions(trip_id, id)
);

CREATE TABLE IF NOT EXISTS active_plans (
    trip_id text PRIMARY KEY,
    plan_version_id text NOT NULL UNIQUE,
    FOREIGN KEY (trip_id, plan_version_id) REFERENCES plan_versions(trip_id, id)
);

CREATE TABLE IF NOT EXISTS trip_setups (
    trip_id text PRIMARY KEY,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    confirmed bigint NOT NULL CHECK (confirmed IN (0, 1)),
    updated_at text NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

CREATE TABLE IF NOT EXISTS provider_cache (
    provider text NOT NULL,
    request_fingerprint text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    retrieved_at text NOT NULL,
    expires_at text NOT NULL,
    PRIMARY KEY (provider, request_fingerprint)
);

CREATE TABLE IF NOT EXISTS discovery_runs (
    id text PRIMARY KEY,
    trip_id text NOT NULL,
    setup_sha256 text NOT NULL,
    provider text NOT NULL,
    status text NOT NULL CHECK (status IN ('verified', 'stale', 'unavailable', 'error')),
    candidates_json text NOT NULL,
    candidates_sha256 text NOT NULL,
    report_json text NOT NULL,
    report_sha256 text NOT NULL,
    created_at text NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

CREATE TABLE IF NOT EXISTS candidate_choices (
    trip_id text NOT NULL,
    place_id text NOT NULL,
    discovery_run_id text NOT NULL,
    action text NOT NULL CHECK (action IN ('must_do', 'interested', 'maybe', 'not_for_trip')),
    reason text,
    candidate_json text NOT NULL,
    candidate_sha256 text NOT NULL,
    updated_at text NOT NULL,
    PRIMARY KEY (trip_id, place_id),
    FOREIGN KEY (trip_id) REFERENCES trips(id),
    FOREIGN KEY (discovery_run_id) REFERENCES discovery_runs(id)
);

CREATE TABLE IF NOT EXISTS optimization_previews (
    trip_id text PRIMARY KEY,
    input_json text NOT NULL,
    input_sha256 text NOT NULL,
    proposal_json text NOT NULL,
    proposal_sha256 text NOT NULL,
    created_at text NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Readiness board items are editable, unlike plan versions. A dismissed
-- generated requirement is kept and flagged so it cannot silently disappear.
CREATE TABLE IF NOT EXISTS checklist_items (
    id text PRIMARY KEY,
    trip_id text NOT NULL,
    generated_key text,
    origin text NOT NULL CHECK (origin IN ('generated', 'manual')),
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    dismissed bigint NOT NULL CHECK (dismissed IN (0, 1)),
    created_at text NOT NULL,
    updated_at text NOT NULL,
    UNIQUE (trip_id, generated_key),
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Owner-recorded costs and the rate snapshot they convert against. Editable,
-- like the readiness board; a paid row keeps its locked THB charge.
CREATE TABLE IF NOT EXISTS cost_items (
    id text PRIMARY KEY,
    trip_id text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

CREATE TABLE IF NOT EXISTS exchange_rate_snapshots (
    trip_id text PRIMARY KEY,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    updated_at text NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Actual group spend. Deliberately no append-only triggers: corrections happen
-- constantly during a trip, so this follows the readiness board's mutable,
-- void-not-delete precedent rather than plan_versions' immutability. Data entry
-- is not a decision the optimizer produced.
CREATE TABLE IF NOT EXISTS split_rows (
    id text PRIMARY KEY,
    trip_id text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- The owner's per-traveller "I consider this settled" marker. It stores the
-- balance that was settled, not a payment: comparing it to the current balance
-- is what makes a marker go stale the moment the arithmetic moves.
CREATE TABLE IF NOT EXISTS split_settled_markers (
    trip_id text NOT NULL,
    traveller_id text NOT NULL,
    settled_net_thb double precision NOT NULL,
    updated_at text NOT NULL,
    PRIMARY KEY (trip_id, traveller_id),
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- `WF-039`. One row per comfort threshold the owner has agreed to exceed, holding the
-- **measured value they agreed to**. Not a boolean: an acceptance of a 27-minute walking
-- leg must not silently bless a 90-minute one after a replan, so the value is the ceiling
-- and `validate_variant` compares against it.
--
-- Mutable and deletable like the split ledger, and for the same reason: withdrawing an
-- acceptance is a correction, not history worth keeping. No append-only trigger.
CREATE TABLE IF NOT EXISTS comfort_acceptances (
    trip_id text NOT NULL,
    code text NOT NULL,
    accepted_value double precision NOT NULL,
    threshold_value double precision NOT NULL,
    updated_at text NOT NULL,
    PRIMARY KEY (trip_id, code),
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Paid-provider ledger. Append-only: spend already made is history, and the
-- monthly cap is judged from it.
CREATE TABLE IF NOT EXISTS paid_usage (
    id text PRIMARY KEY,
    trip_id text,
    operation text NOT NULL,
    provider text NOT NULL,
    request_count bigint NOT NULL,
    estimated_usd double precision NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('success', 'error', 'cached')),
    detail_json text NOT NULL,
    created_at text NOT NULL
);

CREATE TABLE IF NOT EXISTS paid_usage_cap (
    id bigint PRIMARY KEY CHECK (id = 1),
    cap_usd double precision NOT NULL,
    updated_at text NOT NULL
);

-- Normalized route snapshots per trip. Refreshing one replaces that leg; a plan
-- version keeps the exact routes it was built from inside its own snapshot.
CREATE TABLE IF NOT EXISTS route_snapshots (
    id text PRIMARY KEY,
    trip_id text NOT NULL,
    origin_id text NOT NULL,
    destination_id text NOT NULL,
    mode text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    provider text NOT NULL,
    retrieved_at text NOT NULL,
    expires_at text NOT NULL,
    UNIQUE (trip_id, origin_id, destination_id, mode),
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Destination-level evidence keyed by kind, so a new governed fact needs no new
-- table. Each row carries its provider, retrieval time, and expiry.
CREATE TABLE IF NOT EXISTS trip_evidence (
    trip_id text NOT NULL,
    kind text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    provider text NOT NULL,
    retrieved_at text NOT NULL,
    expires_at text NOT NULL,
    PRIMARY KEY (trip_id, kind),
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Per-place governed evidence, keyed by kind. A licensed live overlay is cached
-- briefly and refreshed, never kept as durable open data.
CREATE TABLE IF NOT EXISTS place_evidence (
    trip_id text NOT NULL,
    place_id text NOT NULL,
    kind text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    provider text NOT NULL,
    retrieved_at text NOT NULL,
    expires_at text NOT NULL,
    PRIMARY KEY (trip_id, place_id, kind),
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Exactly one pending revision preview per trip, per the Phase 1 decision. The
-- active plan is untouched until the owner applies it.
CREATE TABLE IF NOT EXISTS revision_drafts (
    trip_id text PRIMARY KEY,
    base_version_id text,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    created_at text NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Applied revision history, append-only: the request, the typed intent, the
-- consequences, and the plan versions either side of it.
CREATE TABLE IF NOT EXISTS plan_revisions (
    id text PRIMARY KEY,
    trip_id text NOT NULL,
    snapshot_json text NOT NULL,
    snapshot_sha256 text NOT NULL,
    created_at text NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);



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

DROP TRIGGER IF EXISTS paid_usage_no_update ON paid_usage;
CREATE TRIGGER paid_usage_no_update BEFORE UPDATE ON paid_usage
    FOR EACH ROW EXECUTE FUNCTION refuse_write('paid usage entries are immutable');

DROP TRIGGER IF EXISTS paid_usage_no_delete ON paid_usage;
CREATE TRIGGER paid_usage_no_delete BEFORE DELETE ON paid_usage
    FOR EACH ROW EXECUTE FUNCTION refuse_write('paid usage entries are immutable');

DROP TRIGGER IF EXISTS plan_revisions_no_update ON plan_revisions;
CREATE TRIGGER plan_revisions_no_update BEFORE UPDATE ON plan_revisions
    FOR EACH ROW EXECUTE FUNCTION refuse_write('revision history is immutable');

DROP TRIGGER IF EXISTS plan_revisions_no_delete ON plan_revisions;
CREATE TRIGGER plan_revisions_no_delete BEFORE DELETE ON plan_revisions
    FOR EACH ROW EXECUTE FUNCTION refuse_write_unless_trip_deleting('revision history is immutable');

DROP TRIGGER IF EXISTS plan_versions_no_update ON plan_versions;
CREATE TRIGGER plan_versions_no_update BEFORE UPDATE ON plan_versions
    FOR EACH ROW EXECUTE FUNCTION refuse_write('plan versions are immutable');

DROP TRIGGER IF EXISTS plan_versions_no_delete ON plan_versions;
CREATE TRIGGER plan_versions_no_delete BEFORE DELETE ON plan_versions
    FOR EACH ROW EXECUTE FUNCTION refuse_write_unless_trip_deleting('plan versions are immutable');

DROP TRIGGER IF EXISTS discovery_runs_no_update ON discovery_runs;
CREATE TRIGGER discovery_runs_no_update BEFORE UPDATE ON discovery_runs
    FOR EACH ROW EXECUTE FUNCTION refuse_write('discovery runs are immutable');

DROP TRIGGER IF EXISTS discovery_runs_no_delete ON discovery_runs;
CREATE TRIGGER discovery_runs_no_delete BEFORE DELETE ON discovery_runs
    FOR EACH ROW EXECUTE FUNCTION refuse_write_unless_trip_deleting('discovery runs are immutable');
