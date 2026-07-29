"""SQLite adapter for authoritative local planner state."""

from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
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
)


SCHEMA_VERSION = 6
SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    destination TEXT NOT NULL,
    planning_mode TEXT NOT NULL CHECK (planning_mode IN ('explore_first', 'ready_to_schedule')),
    language TEXT NOT NULL CHECK (language IN ('en', 'th')),
    created_at TEXT NOT NULL
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

CREATE TRIGGER IF NOT EXISTS plan_versions_no_update
BEFORE UPDATE ON plan_versions
BEGIN
    SELECT RAISE(ABORT, 'plan versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS plan_versions_no_delete
BEFORE DELETE ON plan_versions
BEGIN
    SELECT RAISE(ABORT, 'plan versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS discovery_runs_no_update
BEFORE UPDATE ON discovery_runs
BEGIN
    SELECT RAISE(ABORT, 'discovery runs are immutable');
END;

CREATE TRIGGER IF NOT EXISTS discovery_runs_no_delete
BEFORE DELETE ON discovery_runs
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
            connection.executescript(SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

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
