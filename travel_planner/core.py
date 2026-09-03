"""Language-neutral domain records with no UI, database, or provider imports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4


PLANNING_MODES = frozenset({"explore_first", "ready_to_schedule"})
LANGUAGES = frozenset({"en", "th"})
#: Google `businessStatus` values that keep a place out of the plan. Temporary
#: counts too: the evidence expires in three days, so a stale temporary flag
#: cannot haunt a trip, and the reconciliation entry names the refresh that
#: clears it. Canonical home: `optimizer` reads facts and stays stdlib-only, so
#: it matches these two strings with a pointer back here rather than importing.
CLOSED_BUSINESS_STATUSES = frozenset({"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"})
FORBIDDEN_SNAPSHOT_KEYS = frozenset(
    {
        "api_key",
        "access_token",
        "refresh_token",
        "authorization",
        "password",
        "passport_number",
        "passport_document",
        "booking_document",
        # The provider keys this project actually configures. Neither ends in
        # `_api_key`, so the suffix rules below would have let them through.
        "google_maps_server_key",
        "google_maps_browser_key",
        "client_secret",
        "private_key",
    }
)
# Credential-shaped suffixes. A bare `_key` is deliberately absent: legitimate
# fields such as `generated_key` and `name_key` end that way.
FORBIDDEN_SNAPSHOT_SUFFIXES = ("_api_key", "_secret", "_token", "_credential")


@dataclass(frozen=True, slots=True)
class Trip:
    trip_id: str
    name: str
    destination: str
    planning_mode: str
    language: str
    created_at: str


@dataclass(frozen=True, slots=True)
class FrozenSnapshot:
    canonical_json: str
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


@dataclass(frozen=True, slots=True)
class PlanVersion:
    version_id: str
    trip_id: str
    parent_version_id: str | None
    cause: str
    snapshot: FrozenSnapshot
    created_at: str


@dataclass(frozen=True, slots=True)
class SetupDraft:
    trip_id: str
    snapshot: FrozenSnapshot
    confirmed: bool
    updated_at: str


@dataclass(frozen=True, slots=True)
class ProviderCacheEntry:
    provider: str
    request_fingerprint: str
    snapshot: FrozenSnapshot
    retrieved_at: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class DiscoveryRun:
    run_id: str
    trip_id: str
    setup_sha256: str
    provider: str
    status: str
    candidates: FrozenSnapshot
    report: FrozenSnapshot
    created_at: str


@dataclass(frozen=True, slots=True)
class CandidateChoice:
    trip_id: str
    place_id: str
    discovery_run_id: str
    action: str
    reason: str | None
    candidate: FrozenSnapshot
    updated_at: str


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    item_id: str
    trip_id: str
    generated_key: str | None
    origin: str
    snapshot: FrozenSnapshot
    dismissed: bool
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.snapshot.as_dict(),
            "item_id": self.item_id,
            "generated_key": self.generated_key,
            "origin": self.origin,
            "dismissed": self.dismissed,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class OptimizationPreview:
    trip_id: str
    optimizer_input: FrozenSnapshot
    proposal: FrozenSnapshot
    created_at: str


def new_trip(
    *,
    name: str,
    destination: str,
    planning_mode: str,
    language: str,
) -> Trip:
    clean_destination = _required_text(destination, "destination")
    clean_name = name.strip() or clean_destination
    if planning_mode not in PLANNING_MODES:
        raise ValueError(f"Unsupported planning mode: {planning_mode}")
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    return Trip(
        trip_id=f"trip_{uuid4().hex}",
        name=clean_name,
        destination=clean_destination,
        planning_mode=planning_mode,
        language=language,
        created_at=_utc_now(),
    )


def new_plan_version(
    *,
    trip_id: str,
    payload: Mapping[str, Any],
    cause: str,
    parent_version_id: str | None,
) -> PlanVersion:
    return PlanVersion(
        version_id=f"plan_{uuid4().hex}",
        trip_id=_required_text(trip_id, "trip_id"),
        parent_version_id=parent_version_id,
        cause=_required_text(cause, "cause"),
        snapshot=freeze_snapshot(payload),
        created_at=_utc_now(),
    )


def new_setup_draft(
    *, trip_id: str, payload: Mapping[str, Any], confirmed: bool
) -> SetupDraft:
    return SetupDraft(
        trip_id=_required_text(trip_id, "trip_id"),
        snapshot=freeze_snapshot(payload),
        confirmed=bool(confirmed),
        updated_at=_utc_now(),
    )


def new_discovery_run(
    *,
    trip_id: str,
    setup_sha256: str,
    provider: str,
    status: str,
    candidates: Mapping[str, Any],
    report: Mapping[str, Any],
) -> DiscoveryRun:
    if status not in {"verified", "stale", "unavailable", "error"}:
        raise ValueError(f"Unsupported discovery status: {status}")
    return DiscoveryRun(
        run_id=f"discovery_{uuid4().hex}",
        trip_id=_required_text(trip_id, "trip_id"),
        setup_sha256=_required_text(setup_sha256, "setup_sha256"),
        provider=_required_text(provider, "provider"),
        status=status,
        candidates=freeze_snapshot(candidates),
        report=freeze_snapshot(report),
        created_at=_utc_now(),
    )


def new_candidate_choice(
    *,
    trip_id: str,
    place_id: str,
    discovery_run_id: str,
    action: str,
    reason: str | None,
    candidate: Mapping[str, Any],
) -> CandidateChoice:
    return CandidateChoice(
        trip_id=_required_text(trip_id, "trip_id"),
        place_id=_required_text(place_id, "place_id"),
        discovery_run_id=_required_text(discovery_run_id, "discovery_run_id"),
        action=_required_text(action, "action"),
        reason=reason,
        candidate=freeze_snapshot(candidate),
        updated_at=_utc_now(),
    )


def new_checklist_item(
    *,
    trip_id: str,
    payload: Mapping[str, Any],
    generated_key: str | None,
    origin: str,
) -> ChecklistItem:
    if origin not in {"generated", "manual"}:
        raise ValueError(f"Unsupported checklist origin: {origin}")
    now = _utc_now()
    return ChecklistItem(
        item_id=f"task_{uuid4().hex}",
        trip_id=_required_text(trip_id, "trip_id"),
        generated_key=generated_key,
        origin=origin,
        snapshot=freeze_snapshot(payload),
        dismissed=bool(payload.get("dismissed")),
        created_at=now,
        updated_at=now,
    )


def new_optimization_preview(
    *,
    trip_id: str,
    optimizer_input: Mapping[str, Any],
    proposal: Mapping[str, Any],
) -> OptimizationPreview:
    return OptimizationPreview(
        trip_id=_required_text(trip_id, "trip_id"),
        optimizer_input=freeze_snapshot(optimizer_input),
        proposal=freeze_snapshot(proposal),
        created_at=_utc_now(),
    )


def freeze_snapshot(payload: Mapping[str, Any]) -> FrozenSnapshot:
    if not isinstance(payload, Mapping):
        raise ValueError("Plan snapshot must be an object")
    _reject_forbidden_keys(payload)
    try:
        canonical = json.dumps(
            dict(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"Plan snapshot is not valid JSON: {error}") from error
    return FrozenSnapshot(canonical, sha256(canonical.encode("utf-8")).hexdigest())


def _reject_forbidden_keys(value: Any, path: str = "snapshot") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains a non-text key")
            normalized = key.casefold().replace("-", "_")
            if normalized in FORBIDDEN_SNAPSHOT_KEYS or normalized.endswith(
                FORBIDDEN_SNAPSHOT_SUFFIXES
            ):
                raise ValueError(f"{path}.{key} is not allowed in a plan snapshot")
            _reject_forbidden_keys(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_forbidden_keys(child, f"{path}[{index}]")


def _required_text(value: str, field: str) -> str:
    clean = value.strip()
    if not clean:
        raise ValueError(f"{field} is required")
    return clean


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
