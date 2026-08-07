"""SQLite adapter for authoritative local planner state."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from hashlib import sha256
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4
from typing import Any, Iterator

from .core import (
    CandidateChoice,
    ChecklistItem,
    DiscoveryRun,
    FrozenSnapshot,
    OptimizationPreview,
    PlanVersion,
    ProviderCacheEntry,
    SetupDraft,
    Trip,
    freeze_snapshot,
)


SCHEMA_VERSION = 14
SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    destination TEXT NOT NULL,
    planning_mode TEXT NOT NULL CHECK (planning_mode IN ('explore_first', 'ready_to_schedule')),
    language TEXT NOT NULL CHECK (language IN ('en', 'th')),
    created_at TEXT NOT NULL
);

-- A transaction-scoped marker lets an intentional whole-trip deletion remove
-- otherwise immutable history without making ordinary row deletion possible.
CREATE TABLE IF NOT EXISTS trip_deletions (
    trip_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS plan_versions (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL,
    parent_version_id TEXT,
    cause TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (trip_id, id),
    FOREIGN KEY (trip_id) REFERENCES trips(id),
    FOREIGN KEY (trip_id, parent_version_id) REFERENCES plan_versions(trip_id, id)
);

CREATE TABLE IF NOT EXISTS active_plans (
    trip_id TEXT PRIMARY KEY,
    plan_version_id TEXT NOT NULL UNIQUE,
    FOREIGN KEY (trip_id, plan_version_id) REFERENCES plan_versions(trip_id, id)
);

CREATE TABLE IF NOT EXISTS trip_setups (
    trip_id TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    confirmed INTEGER NOT NULL CHECK (confirmed IN (0, 1)),
    updated_at TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

CREATE TABLE IF NOT EXISTS provider_cache (
    provider TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (provider, request_fingerprint)
);

CREATE TABLE IF NOT EXISTS discovery_runs (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL,
    setup_sha256 TEXT NOT NULL,
    provider TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified', 'stale', 'unavailable', 'error')),
    candidates_json TEXT NOT NULL,
    candidates_sha256 TEXT NOT NULL,
    report_json TEXT NOT NULL,
    report_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

CREATE TABLE IF NOT EXISTS candidate_choices (
    trip_id TEXT NOT NULL,
    place_id TEXT NOT NULL,
    discovery_run_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('must_do', 'interested', 'maybe', 'not_for_trip')),
    reason TEXT,
    candidate_json TEXT NOT NULL,
    candidate_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trip_id, place_id),
    FOREIGN KEY (trip_id) REFERENCES trips(id),
    FOREIGN KEY (discovery_run_id) REFERENCES discovery_runs(id)
);

CREATE TABLE IF NOT EXISTS optimization_previews (
    trip_id TEXT PRIMARY KEY,
    input_json TEXT NOT NULL,
    input_sha256 TEXT NOT NULL,
    proposal_json TEXT NOT NULL,
    proposal_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Readiness board items are editable, unlike plan versions. A dismissed
-- generated requirement is kept and flagged so it cannot silently disappear.
CREATE TABLE IF NOT EXISTS checklist_items (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL,
    generated_key TEXT,
    origin TEXT NOT NULL CHECK (origin IN ('generated', 'manual')),
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    dismissed INTEGER NOT NULL CHECK (dismissed IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (trip_id, generated_key),
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Owner-recorded costs and the rate snapshot they convert against. Editable,
-- like the readiness board; a paid row keeps its locked THB charge.
CREATE TABLE IF NOT EXISTS cost_items (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

CREATE TABLE IF NOT EXISTS exchange_rate_snapshots (
    trip_id TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Actual group spend. Deliberately no append-only triggers: corrections happen
-- constantly during a trip, so this follows the readiness board's mutable,
-- void-not-delete precedent rather than plan_versions' immutability. Data entry
-- is not a decision the optimizer produced.
CREATE TABLE IF NOT EXISTS split_rows (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- The owner's per-traveller "I consider this settled" marker. It stores the
-- balance that was settled, not a payment: comparing it to the current balance
-- is what makes a marker go stale the moment the arithmetic moves.
CREATE TABLE IF NOT EXISTS split_settled_markers (
    trip_id TEXT NOT NULL,
    traveller_id TEXT NOT NULL,
    settled_net_thb REAL NOT NULL,
    updated_at TEXT NOT NULL,
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
    trip_id TEXT NOT NULL,
    code TEXT NOT NULL,
    accepted_value REAL NOT NULL,
    threshold_value REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trip_id, code),
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Paid-provider ledger. Append-only: spend already made is history, and the
-- monthly cap is judged from it.
CREATE TABLE IF NOT EXISTS paid_usage (
    id TEXT PRIMARY KEY,
    trip_id TEXT,
    operation TEXT NOT NULL,
    provider TEXT NOT NULL,
    request_count INTEGER NOT NULL,
    estimated_usd REAL NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'error', 'cached')),
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paid_usage_cap (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cap_usd REAL NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS paid_usage_no_update
BEFORE UPDATE ON paid_usage
BEGIN
    SELECT RAISE(ABORT, 'paid usage entries are immutable');
END;

CREATE TRIGGER IF NOT EXISTS paid_usage_no_delete
BEFORE DELETE ON paid_usage
BEGIN
    SELECT RAISE(ABORT, 'paid usage entries are immutable');
END;

-- Normalized route snapshots per trip. Refreshing one replaces that leg; a plan
-- version keeps the exact routes it was built from inside its own snapshot.
CREATE TABLE IF NOT EXISTS route_snapshots (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL,
    origin_id TEXT NOT NULL,
    destination_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    provider TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE (trip_id, origin_id, destination_id, mode),
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Destination-level evidence keyed by kind, so a new governed fact needs no new
-- table. Each row carries its provider, retrieval time, and expiry.
CREATE TABLE IF NOT EXISTS trip_evidence (
    trip_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    provider TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (trip_id, kind),
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Per-place governed evidence, keyed by kind. A licensed live overlay is cached
-- briefly and refreshed, never kept as durable open data.
CREATE TABLE IF NOT EXISTS place_evidence (
    trip_id TEXT NOT NULL,
    place_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    provider TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (trip_id, place_id, kind),
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Exactly one pending revision preview per trip, per the Phase 1 decision. The
-- active plan is untouched until the owner applies it.
CREATE TABLE IF NOT EXISTS revision_drafts (
    trip_id TEXT PRIMARY KEY,
    base_version_id TEXT,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

-- Applied revision history, append-only: the request, the typed intent, the
-- consequences, and the plan versions either side of it.
CREATE TABLE IF NOT EXISTS plan_revisions (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (trip_id) REFERENCES trips(id)
);

CREATE TRIGGER IF NOT EXISTS plan_revisions_no_update
BEFORE UPDATE ON plan_revisions
BEGIN
    SELECT RAISE(ABORT, 'revision history is immutable');
END;

DROP TRIGGER IF EXISTS plan_revisions_no_delete;
CREATE TRIGGER plan_revisions_no_delete
BEFORE DELETE ON plan_revisions
WHEN NOT EXISTS (
    SELECT 1 FROM trip_deletions WHERE trip_id = OLD.trip_id
)
BEGIN
    SELECT RAISE(ABORT, 'revision history is immutable');
END;

CREATE TRIGGER IF NOT EXISTS plan_versions_no_update
BEFORE UPDATE ON plan_versions
BEGIN
    SELECT RAISE(ABORT, 'plan versions are immutable');
END;

DROP TRIGGER IF EXISTS plan_versions_no_delete;
CREATE TRIGGER plan_versions_no_delete
BEFORE DELETE ON plan_versions
WHEN NOT EXISTS (
    SELECT 1 FROM trip_deletions WHERE trip_id = OLD.trip_id
)
BEGIN
    SELECT RAISE(ABORT, 'plan versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS discovery_runs_no_update
BEFORE UPDATE ON discovery_runs
BEGIN
    SELECT RAISE(ABORT, 'discovery runs are immutable');
END;

DROP TRIGGER IF EXISTS discovery_runs_no_delete;
CREATE TRIGGER discovery_runs_no_delete
BEFORE DELETE ON discovery_runs
WHEN NOT EXISTS (
    SELECT 1 FROM trip_deletions WHERE trip_id = OLD.trip_id
)
BEGIN
    SELECT RAISE(ABORT, 'discovery runs are immutable');
END;
"""


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        if str(path) == ":memory:":
            raise ValueError("SQLiteStore requires a file path")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
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
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema {version} is newer than supported {SCHEMA_VERSION}"
                )
            # Version 0 is a database this call is creating, which has nothing
            # worth copying; an equal version is not a bump. Only a real
            # forward move is gated.
            if 0 < version < SCHEMA_VERSION:
                self._copy_before_bump(version)
            connection.executescript(SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _copy_before_bump(self, version: int) -> None:
        """Copy the database before an irreversible bump, or refuse to migrate.

        There is no downgrade tool and no restorable old checkout by decision,
        so this copy is the only way back. A failed copy therefore has to stop
        the migration rather than be warned about.
        """

        target = self.path.with_name(
            f"{self.path.stem}-pre-v{SCHEMA_VERSION}"
            f"-{date.today().isoformat()}{self.path.suffix}"
        )
        try:
            shutil.copy2(self.path, target)
        except OSError as error:
            raise RuntimeError(
                f"Refusing to migrate {self.path} from schema {version} to "
                f"{SCHEMA_VERSION}: the pre-bump copy to {target} failed ({error})"
            ) from error

    def add_trip(self, trip: Trip) -> Trip:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO trips (id, name, destination, planning_mode, language, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    trip.trip_id,
                    trip.name,
                    trip.destination,
                    trip.planning_mode,
                    trip.language,
                    trip.created_at,
                ),
            )
        return trip

    def list_trips(self) -> list[Trip]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trips ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [self._trip(row) for row in rows]

    def get_trip(self, trip_id: str) -> Trip | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        return self._trip(row) if row else None

    def delete_trip(self, trip_id: str) -> None:
        """Delete one trip and its saved planning data in one transaction.

        Paid usage is deliberately retained: a completed provider charge stays
        part of the monthly spend even when its trip is removed.
        """

        with self.connect() as connection:
            if connection.execute(
                "SELECT 1 FROM trips WHERE id = ?", (trip_id,)
            ).fetchone() is None:
                raise ValueError(f"Unknown trip: {trip_id}")
            connection.execute(
                "INSERT INTO trip_deletions (trip_id) VALUES (?)", (trip_id,)
            )
            # Children with cross-table foreign keys come first. A future
            # trip-scoped table fails this transaction safely until added here.
            for table in (
                "active_plans",
                "candidate_choices",
                "optimization_previews",
                "checklist_items",
                "cost_items",
                "exchange_rate_snapshots",
                "route_snapshots",
                "trip_evidence",
                "place_evidence",
                "revision_drafts",
                "plan_revisions",
                "plan_versions",
                "discovery_runs",
                "trip_setups",
            ):
                connection.execute(
                    f"DELETE FROM {table} WHERE trip_id = ?", (trip_id,)
                )
            connection.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
            connection.execute(
                "DELETE FROM trip_deletions WHERE trip_id = ?", (trip_id,)
            )

    def save_setup(self, setup: SetupDraft) -> SetupDraft:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO trip_setups
                    (trip_id, snapshot_json, snapshot_sha256, confirmed, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(trip_id) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    snapshot_sha256 = excluded.snapshot_sha256,
                    confirmed = excluded.confirmed,
                    updated_at = excluded.updated_at
                """,
                (
                    setup.trip_id,
                    setup.snapshot.canonical_json,
                    setup.snapshot.sha256,
                    int(setup.confirmed),
                    setup.updated_at,
                ),
            )
        return setup

    def get_setup(self, trip_id: str) -> SetupDraft | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM trip_setups WHERE trip_id = ?", (trip_id,)
            ).fetchone()
        if not row:
            return None
        return SetupDraft(
            trip_id=row["trip_id"],
            snapshot=self._verified_snapshot(
                row["snapshot_json"], row["snapshot_sha256"], f"setup {trip_id}"
            ),
            confirmed=bool(row["confirmed"]),
            updated_at=row["updated_at"],
        )

    def put_provider_cache(self, entry: ProviderCacheEntry) -> ProviderCacheEntry:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO provider_cache
                    (provider, request_fingerprint, snapshot_json, snapshot_sha256,
                     retrieved_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, request_fingerprint) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    snapshot_sha256 = excluded.snapshot_sha256,
                    retrieved_at = excluded.retrieved_at,
                    expires_at = excluded.expires_at
                """,
                (
                    entry.provider,
                    entry.request_fingerprint,
                    entry.snapshot.canonical_json,
                    entry.snapshot.sha256,
                    entry.retrieved_at,
                    entry.expires_at,
                ),
            )
        return entry

    def get_provider_cache(
        self, provider: str, request_fingerprint: str
    ) -> ProviderCacheEntry | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM provider_cache
                WHERE provider = ? AND request_fingerprint = ?
                """,
                (provider, request_fingerprint),
            ).fetchone()
        if not row:
            return None
        return ProviderCacheEntry(
            provider=row["provider"],
            request_fingerprint=row["request_fingerprint"],
            snapshot=self._verified_snapshot(
                row["snapshot_json"], row["snapshot_sha256"], "provider cache"
            ),
            retrieved_at=row["retrieved_at"],
            expires_at=row["expires_at"],
        )

    def add_discovery_run(self, run: DiscoveryRun) -> DiscoveryRun:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO discovery_runs
                    (id, trip_id, setup_sha256, provider, status, candidates_json,
                     candidates_sha256, report_json, report_sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.trip_id,
                    run.setup_sha256,
                    run.provider,
                    run.status,
                    run.candidates.canonical_json,
                    run.candidates.sha256,
                    run.report.canonical_json,
                    run.report.sha256,
                    run.created_at,
                ),
            )
        return run

    def get_latest_discovery(self, trip_id: str) -> DiscoveryRun | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM discovery_runs
                WHERE trip_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (trip_id,),
            ).fetchone()
        return self._discovery_run(row) if row else None

    def list_discovery_runs(self, trip_id: str) -> list[DiscoveryRun]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM discovery_runs
                WHERE trip_id = ?
                ORDER BY created_at, id
                """,
                (trip_id,),
            ).fetchall()
        return [self._discovery_run(row) for row in rows]

    def save_candidate_choice(self, choice: CandidateChoice) -> CandidateChoice:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO candidate_choices
                    (trip_id, place_id, discovery_run_id, action, reason,
                     candidate_json, candidate_sha256, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trip_id, place_id) DO UPDATE SET
                    discovery_run_id = excluded.discovery_run_id,
                    action = excluded.action,
                    reason = excluded.reason,
                    candidate_json = excluded.candidate_json,
                    candidate_sha256 = excluded.candidate_sha256,
                    updated_at = excluded.updated_at
                """,
                (
                    choice.trip_id,
                    choice.place_id,
                    choice.discovery_run_id,
                    choice.action,
                    choice.reason,
                    choice.candidate.canonical_json,
                    choice.candidate.sha256,
                    choice.updated_at,
                ),
            )
        return choice

    def delete_candidate_choice(self, trip_id: str, place_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM candidate_choices WHERE trip_id = ? AND place_id = ?",
                (trip_id, place_id),
            )

    def list_candidate_choices(self, trip_id: str) -> list[CandidateChoice]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM candidate_choices
                WHERE trip_id = ?
                ORDER BY updated_at, place_id
                """,
                (trip_id,),
            ).fetchall()
        return [self._candidate_choice(row) for row in rows]

    def upsert_checklist_item(self, item: ChecklistItem) -> ChecklistItem:
        with self.connect() as connection:
            existing = None
            if item.generated_key:
                existing = connection.execute(
                    "SELECT id, created_at FROM checklist_items"
                    " WHERE trip_id = ? AND generated_key = ?",
                    (item.trip_id, item.generated_key),
                ).fetchone()
            item_id = existing["id"] if existing else item.item_id
            created_at = existing["created_at"] if existing else item.created_at
            connection.execute(
                """
                INSERT INTO checklist_items (
                    id, trip_id, generated_key, origin, snapshot_json,
                    snapshot_sha256, dismissed, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    snapshot_sha256 = excluded.snapshot_sha256,
                    dismissed = excluded.dismissed,
                    updated_at = excluded.updated_at
                """,
                (
                    item_id,
                    item.trip_id,
                    item.generated_key,
                    item.origin,
                    item.snapshot.canonical_json,
                    item.snapshot.sha256,
                    int(item.dismissed),
                    created_at,
                    item.updated_at,
                ),
            )
        return ChecklistItem(
            item_id=item_id,
            trip_id=item.trip_id,
            generated_key=item.generated_key,
            origin=item.origin,
            snapshot=item.snapshot,
            dismissed=item.dismissed,
            created_at=created_at,
            updated_at=item.updated_at,
        )

    def list_checklist_items(self, trip_id: str) -> list[ChecklistItem]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM checklist_items WHERE trip_id = ?"
                " ORDER BY created_at, id",
                (trip_id,),
            ).fetchall()
        return [self._checklist_item(row) for row in rows]

    def get_checklist_item(self, item_id: str) -> ChecklistItem | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM checklist_items WHERE id = ?", (item_id,)
            ).fetchone()
        return self._checklist_item(row) if row else None

    def upsert_cost_item(
        self, *, item_id: str | None, trip_id: str, snapshot: FrozenSnapshot, now: str
    ) -> dict[str, Any]:
        with self.connect() as connection:
            existing = (
                connection.execute(
                    "SELECT id, created_at FROM cost_items WHERE id = ? AND trip_id = ?",
                    (item_id, trip_id),
                ).fetchone()
                if item_id
                else None
            )
            resolved = existing["id"] if existing else (item_id or f"cost_{uuid4().hex}")
            created = existing["created_at"] if existing else now
            connection.execute(
                """
                INSERT INTO cost_items (
                    id, trip_id, snapshot_json, snapshot_sha256, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    snapshot_sha256 = excluded.snapshot_sha256,
                    updated_at = excluded.updated_at
                """,
                (resolved, trip_id, snapshot.canonical_json, snapshot.sha256, created, now),
            )
        return {**snapshot.as_dict(), "cost_id": resolved, "updated_at": now}

    def list_cost_items(self, trip_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM cost_items WHERE trip_id = ? ORDER BY created_at, id",
                (trip_id,),
            ).fetchall()
        return [
            {
                **self._verified_snapshot(
                    row["snapshot_json"], row["snapshot_sha256"], "Cost item"
                ).as_dict(),
                "cost_id": row["id"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def delete_cost_item(self, trip_id: str, item_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM cost_items WHERE trip_id = ? AND id = ?", (trip_id, item_id)
            )

    def save_rate_snapshot(
        self, *, trip_id: str, snapshot: FrozenSnapshot, now: str
    ) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO exchange_rate_snapshots (
                    trip_id, snapshot_json, snapshot_sha256, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT (trip_id) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    snapshot_sha256 = excluded.snapshot_sha256,
                    updated_at = excluded.updated_at
                """,
                (trip_id, snapshot.canonical_json, snapshot.sha256, now),
            )
        return snapshot.as_dict()

    def get_rate_snapshot(self, trip_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM exchange_rate_snapshots WHERE trip_id = ?", (trip_id,)
            ).fetchone()
        if row is None:
            return None
        return self._verified_snapshot(
            row["snapshot_json"], row["snapshot_sha256"], "Exchange-rate snapshot"
        ).as_dict()

    # No delete_split_row by decision: removing a row voids it, so a total stays
    # explainable. Voiding is an ordinary upsert of the same row.
    def upsert_split_row(
        self, *, row_id: str | None, trip_id: str, snapshot: FrozenSnapshot, now: str
    ) -> dict[str, Any]:
        with self.connect() as connection:
            existing = (
                connection.execute(
                    "SELECT id, created_at FROM split_rows WHERE id = ? AND trip_id = ?",
                    (row_id, trip_id),
                ).fetchone()
                if row_id
                else None
            )
            resolved = existing["id"] if existing else (row_id or f"split_{uuid4().hex}")
            created = existing["created_at"] if existing else now
            connection.execute(
                """
                INSERT INTO split_rows (
                    id, trip_id, snapshot_json, snapshot_sha256, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    snapshot_sha256 = excluded.snapshot_sha256,
                    updated_at = excluded.updated_at
                """,
                (resolved, trip_id, snapshot.canonical_json, snapshot.sha256, created, now),
            )
        return {**snapshot.as_dict(), "split_id": resolved, "updated_at": now}

    def list_split_rows(self, trip_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM split_rows WHERE trip_id = ? ORDER BY created_at, id",
                (trip_id,),
            ).fetchall()
        return [
            {
                **self._verified_snapshot(
                    row["snapshot_json"], row["snapshot_sha256"], "Split row"
                ).as_dict(),
                "split_id": row["id"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def save_settled_marker(
        self, *, trip_id: str, traveller_id: str, net_thb: float, now: str
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO split_settled_markers (
                    trip_id, traveller_id, settled_net_thb, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT (trip_id, traveller_id) DO UPDATE SET
                    settled_net_thb = excluded.settled_net_thb,
                    updated_at = excluded.updated_at
                """,
                (trip_id, traveller_id, float(net_thb), now),
            )

    def clear_settled_marker(self, trip_id: str, traveller_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM split_settled_markers WHERE trip_id = ? AND traveller_id = ?",
                (trip_id, traveller_id),
            )

    def list_settled_markers(self, trip_id: str) -> dict[str, float]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT traveller_id, settled_net_thb FROM split_settled_markers"
                " WHERE trip_id = ?",
                (trip_id,),
            ).fetchall()
        return {row["traveller_id"]: float(row["settled_net_thb"]) for row in rows}

    def save_comfort_acceptance(
        self,
        *,
        trip_id: str,
        code: str,
        accepted_value: float,
        threshold_value: float,
        now: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO comfort_acceptances (
                    trip_id, code, accepted_value, threshold_value, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (trip_id, code) DO UPDATE SET
                    accepted_value = excluded.accepted_value,
                    threshold_value = excluded.threshold_value,
                    updated_at = excluded.updated_at
                """,
                (trip_id, code, float(accepted_value), float(threshold_value), now),
            )

    def clear_comfort_acceptance(self, trip_id: str, code: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM comfort_acceptances WHERE trip_id = ? AND code = ?",
                (trip_id, code),
            )

    def list_comfort_acceptances(self, trip_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT code, accepted_value, threshold_value, updated_at"
                " FROM comfort_acceptances WHERE trip_id = ? ORDER BY code",
                (trip_id,),
            ).fetchall()
        return [
            {
                "code": row["code"],
                "accepted_value": float(row["accepted_value"]),
                "threshold_value": float(row["threshold_value"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def save_revision_draft(
        self, *, trip_id: str, base_version_id: str | None, draft: dict[str, Any], now: str
    ) -> dict[str, Any]:
        snapshot = freeze_snapshot(draft)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO revision_drafts (
                    trip_id, base_version_id, snapshot_json, snapshot_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (trip_id) DO UPDATE SET
                    base_version_id = excluded.base_version_id,
                    snapshot_json = excluded.snapshot_json,
                    snapshot_sha256 = excluded.snapshot_sha256,
                    created_at = excluded.created_at
                """,
                (trip_id, base_version_id, snapshot.canonical_json, snapshot.sha256, now),
            )
        return {**draft, "base_version_id": base_version_id, "created_at": now}

    def get_revision_draft(self, trip_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM revision_drafts WHERE trip_id = ?", (trip_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            **self._verified_snapshot(
                row["snapshot_json"], row["snapshot_sha256"], "Revision draft"
            ).as_dict(),
            "base_version_id": row["base_version_id"],
            "created_at": row["created_at"],
        }

    def delete_revision_draft(self, trip_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM revision_drafts WHERE trip_id = ?", (trip_id,)
            )

    def add_plan_revision(
        self, *, trip_id: str, record: dict[str, Any], now: str
    ) -> dict[str, Any]:
        snapshot = freeze_snapshot(record)
        row_id = f"revision_{uuid4().hex}"
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO plan_revisions (
                    id, trip_id, snapshot_json, snapshot_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (row_id, trip_id, snapshot.canonical_json, snapshot.sha256, now),
            )
        return {**record, "revision_id": row_id, "created_at": now}

    def list_plan_revisions(self, trip_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM plan_revisions WHERE trip_id = ? ORDER BY created_at, id",
                (trip_id,),
            ).fetchall()
        return [
            {
                **self._verified_snapshot(
                    row["snapshot_json"], row["snapshot_sha256"], "Revision record"
                ).as_dict(),
                "revision_id": row["id"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def upsert_place_evidence(
        self,
        *,
        trip_id: str,
        place_id: str,
        kind: str,
        value: dict[str, Any],
        provider: str,
        retrieved_at: str,
        expires_at: str,
    ) -> dict[str, Any]:
        snapshot = freeze_snapshot(value)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO place_evidence (
                    trip_id, place_id, kind, snapshot_json, snapshot_sha256,
                    provider, retrieved_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (trip_id, place_id, kind) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    snapshot_sha256 = excluded.snapshot_sha256,
                    provider = excluded.provider,
                    retrieved_at = excluded.retrieved_at,
                    expires_at = excluded.expires_at
                """,
                (
                    trip_id,
                    place_id,
                    kind,
                    snapshot.canonical_json,
                    snapshot.sha256,
                    provider,
                    retrieved_at,
                    expires_at,
                ),
            )
        return value

    def delete_place_evidence(self, trip_id: str, place_id: str, kind: str) -> int:
        """Drop one cached evidence row. Returns how many rows went.

        `place_evidence` carries no append-only trigger because it is a cache, not
        history — but it is a cache of two very different things. A `place_summary` is
        free to fetch again from Wikidata; an `opening_hours` row cost US$0.025 at
        `google_places:search_text` and is the reason the table outlives a change of
        mind. So `kind` is **required**: there is no call that removes everything held
        for a place, and a tidy-up cannot reach the paid rows by accident.
        """

        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM place_evidence"
                " WHERE trip_id = ? AND place_id = ? AND kind = ?",
                (trip_id, place_id, kind),
            )
            return int(cursor.rowcount)

    def list_place_evidence(self, trip_id: str, kind: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM place_evidence WHERE trip_id = ? AND kind = ?"
                " ORDER BY place_id",
                (trip_id, kind),
            ).fetchall()
        return [
            {
                **self._verified_snapshot(
                    row["snapshot_json"], row["snapshot_sha256"], "Place evidence"
                ).as_dict(),
                "retrieved_at": row["retrieved_at"],
                "expires_at": row["expires_at"],
            }
            for row in rows
        ]

    def upsert_trip_evidence(
        self,
        *,
        trip_id: str,
        kind: str,
        value: dict[str, Any],
        provider: str,
        retrieved_at: str,
        expires_at: str,
    ) -> dict[str, Any]:
        snapshot = freeze_snapshot(value)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO trip_evidence (
                    trip_id, kind, snapshot_json, snapshot_sha256, provider,
                    retrieved_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (trip_id, kind) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    snapshot_sha256 = excluded.snapshot_sha256,
                    provider = excluded.provider,
                    retrieved_at = excluded.retrieved_at,
                    expires_at = excluded.expires_at
                """,
                (
                    trip_id,
                    kind,
                    snapshot.canonical_json,
                    snapshot.sha256,
                    provider,
                    retrieved_at,
                    expires_at,
                ),
            )
        return value

    def get_trip_evidence(self, trip_id: str, kind: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM trip_evidence WHERE trip_id = ? AND kind = ?",
                (trip_id, kind),
            ).fetchone()
        if row is None:
            return None
        return {
            **self._verified_snapshot(
                row["snapshot_json"], row["snapshot_sha256"], "Trip evidence"
            ).as_dict(),
            "retrieved_at": row["retrieved_at"],
            "expires_at": row["expires_at"],
        }

    def upsert_route_snapshot(
        self,
        *,
        trip_id: str,
        route: dict[str, Any],
        provider: str,
        retrieved_at: str,
        expires_at: str,
    ) -> dict[str, Any]:
        snapshot = freeze_snapshot(route)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO route_snapshots (
                    id, trip_id, origin_id, destination_id, mode, snapshot_json,
                    snapshot_sha256, provider, retrieved_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (trip_id, origin_id, destination_id, mode) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    snapshot_sha256 = excluded.snapshot_sha256,
                    provider = excluded.provider,
                    retrieved_at = excluded.retrieved_at,
                    expires_at = excluded.expires_at
                """,
                (
                    f"route_{uuid4().hex}",
                    trip_id,
                    route["origin_id"],
                    route["destination_id"],
                    route["mode"],
                    snapshot.canonical_json,
                    snapshot.sha256,
                    provider,
                    retrieved_at,
                    expires_at,
                ),
            )
        return route

    def list_route_snapshots(self, trip_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM route_snapshots WHERE trip_id = ?"
                " ORDER BY origin_id, destination_id, mode",
                (trip_id,),
            ).fetchall()
        return [
            {
                **self._verified_snapshot(
                    row["snapshot_json"], row["snapshot_sha256"], "Route snapshot"
                ).as_dict(),
                "retrieved_at": row["retrieved_at"],
                "expires_at": row["expires_at"],
            }
            for row in rows
        ]

    def add_paid_usage(self, entry: dict[str, Any]) -> dict[str, Any]:
        row_id = f"usage_{uuid4().hex}"
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO paid_usage (
                    id, trip_id, operation, provider, request_count,
                    estimated_usd, outcome, detail_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    entry.get("trip_id"),
                    entry["operation"],
                    entry["provider"],
                    int(entry["request_count"]),
                    float(entry["estimated_usd"]),
                    entry["outcome"],
                    freeze_snapshot(entry.get("detail") or {}).canonical_json,
                    entry["created_at"],
                ),
            )
        return {**entry, "usage_id": row_id}

    def list_paid_usage(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM paid_usage ORDER BY created_at, id"
            ).fetchall()
        return [
            {
                "usage_id": row["id"],
                "trip_id": row["trip_id"],
                "operation": row["operation"],
                "provider": row["provider"],
                "request_count": row["request_count"],
                "estimated_usd": row["estimated_usd"],
                "outcome": row["outcome"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_paid_cap(self) -> float | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT cap_usd FROM paid_usage_cap WHERE id = 1"
            ).fetchone()
        return None if row is None else float(row["cap_usd"])

    def set_paid_cap(self, *, cap_usd: float, now: str) -> float:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO paid_usage_cap (id, cap_usd, updated_at) VALUES (1, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    cap_usd = excluded.cap_usd, updated_at = excluded.updated_at
                """,
                (float(cap_usd), now),
            )
        return float(cap_usd)

    def save_optimization_preview(
        self, preview: OptimizationPreview
    ) -> OptimizationPreview:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO optimization_previews
                    (trip_id, input_json, input_sha256, proposal_json,
                     proposal_sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(trip_id) DO UPDATE SET
                    input_json = excluded.input_json,
                    input_sha256 = excluded.input_sha256,
                    proposal_json = excluded.proposal_json,
                    proposal_sha256 = excluded.proposal_sha256,
                    created_at = excluded.created_at
                """,
                (
                    preview.trip_id,
                    preview.optimizer_input.canonical_json,
                    preview.optimizer_input.sha256,
                    preview.proposal.canonical_json,
                    preview.proposal.sha256,
                    preview.created_at,
                ),
            )
        return preview

    def get_optimization_preview(self, trip_id: str) -> OptimizationPreview | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM optimization_previews WHERE trip_id = ?", (trip_id,)
            ).fetchone()
        if not row:
            return None
        return OptimizationPreview(
            trip_id=row["trip_id"],
            optimizer_input=self._verified_snapshot(
                row["input_json"], row["input_sha256"], f"optimizer input {trip_id}"
            ),
            proposal=self._verified_snapshot(
                row["proposal_json"], row["proposal_sha256"], f"optimizer proposal {trip_id}"
            ),
            created_at=row["created_at"],
        )

    def delete_optimization_preview(self, trip_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM optimization_previews WHERE trip_id = ?", (trip_id,)
            )

    def add_plan_version(self, version: PlanVersion, *, activate: bool = True) -> PlanVersion:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO plan_versions
                    (id, trip_id, parent_version_id, cause, snapshot_json,
                     snapshot_sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version.version_id,
                    version.trip_id,
                    version.parent_version_id,
                    version.cause,
                    version.snapshot.canonical_json,
                    version.snapshot.sha256,
                    version.created_at,
                ),
            )
            if activate:
                connection.execute(
                    """
                    INSERT INTO active_plans (trip_id, plan_version_id)
                    VALUES (?, ?)
                    ON CONFLICT(trip_id) DO UPDATE
                    SET plan_version_id = excluded.plan_version_id
                    """,
                    (version.trip_id, version.version_id),
                )
        return version

    def get_plan_version(self, version_id: str) -> PlanVersion | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM plan_versions WHERE id = ?", (version_id,)
            ).fetchone()
        return self._plan_version(row) if row else None

    def get_active_plan(self, trip_id: str) -> PlanVersion | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT plan_versions.*
                FROM active_plans
                JOIN plan_versions ON plan_versions.id = active_plans.plan_version_id
                WHERE active_plans.trip_id = ?
                """,
                (trip_id,),
            ).fetchone()
        return self._plan_version(row) if row else None

    def list_plan_versions(self, trip_id: str) -> list[PlanVersion]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM plan_versions
                WHERE trip_id = ?
                ORDER BY created_at, id
                """,
                (trip_id,),
            ).fetchall()
        return [self._plan_version(row) for row in rows]

    @staticmethod
    def _trip(row: sqlite3.Row) -> Trip:
        return Trip(
            trip_id=row["id"],
            name=row["name"],
            destination=row["destination"],
            planning_mode=row["planning_mode"],
            language=row["language"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _plan_version(row: sqlite3.Row) -> PlanVersion:
        snapshot = SQLiteStore._verified_snapshot(
            row["snapshot_json"], row["snapshot_sha256"], f"plan {row['id']}"
        )
        return PlanVersion(
            version_id=row["id"],
            trip_id=row["trip_id"],
            parent_version_id=row["parent_version_id"],
            cause=row["cause"],
            snapshot=snapshot,
            created_at=row["created_at"],
        )

    @staticmethod
    def _discovery_run(row: sqlite3.Row) -> DiscoveryRun:
        return DiscoveryRun(
            run_id=row["id"],
            trip_id=row["trip_id"],
            setup_sha256=row["setup_sha256"],
            provider=row["provider"],
            status=row["status"],
            candidates=SQLiteStore._verified_snapshot(
                row["candidates_json"],
                row["candidates_sha256"],
                f"discovery candidates {row['id']}",
            ),
            report=SQLiteStore._verified_snapshot(
                row["report_json"], row["report_sha256"], f"discovery report {row['id']}"
            ),
            created_at=row["created_at"],
        )

    @staticmethod
    def _candidate_choice(row: sqlite3.Row) -> CandidateChoice:
        return CandidateChoice(
            trip_id=row["trip_id"],
            place_id=row["place_id"],
            discovery_run_id=row["discovery_run_id"],
            action=row["action"],
            reason=row["reason"],
            candidate=SQLiteStore._verified_snapshot(
                row["candidate_json"],
                row["candidate_sha256"],
                f"candidate choice {row['trip_id']}:{row['place_id']}",
            ),
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _checklist_item(row: sqlite3.Row) -> ChecklistItem:
        return ChecklistItem(
            item_id=row["id"],
            trip_id=row["trip_id"],
            generated_key=row["generated_key"],
            origin=row["origin"],
            snapshot=SQLiteStore._verified_snapshot(
                row["snapshot_json"], row["snapshot_sha256"], "Checklist item"
            ),
            dismissed=bool(row["dismissed"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _verified_snapshot(canonical_json: str, expected: str, label: str) -> FrozenSnapshot:
        digest = sha256(canonical_json.encode("utf-8")).hexdigest()
        if digest != expected:
            raise RuntimeError(f"Snapshot hash mismatch for {label}")
        return FrozenSnapshot(canonical_json, digest)
