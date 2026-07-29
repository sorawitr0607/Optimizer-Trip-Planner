"""Application actions coordinating the domain core and SQLite adapter."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any

from .core import (
    CandidateChoice,
    DiscoveryRun,
    OptimizationPreview,
    PlanVersion,
    ProviderCacheEntry,
    SetupDraft,
    Trip,
    freeze_snapshot,
    new_candidate_choice,
    new_discovery_run,
    new_optimization_preview,
    new_plan_version,
    new_setup_draft,
    new_trip,
)
from .discovery import build_candidate_catalog
from .optimizer import date_range, optimize_trip
from .providers import OpenStreetMapProvider, ProviderUnavailable
from .ranking import build_ranking, validate_choice
from .setup import build_setup_payload
from .store import SQLiteStore


class PlannerActions:
    def __init__(self, database_path: str | Path, *, place_provider: Any = None) -> None:
        self.store = SQLiteStore(database_path)
        self.place_provider = place_provider

    def create_trip(
        self,
        *,
        name: str,
        destination: str,
        planning_mode: str = "explore_first",
        language: str = "en",
    ) -> Trip:
        return self.store.add_trip(
            new_trip(
                name=name,
                destination=destination,
                planning_mode=planning_mode,
                language=language,
            )
        )

    def list_trips(self) -> list[Trip]:
        return self.store.list_trips()

    def get_trip(self, trip_id: str) -> Trip | None:
        return self.store.get_trip(trip_id)

    def save_setup(
        self,
        *,
        trip_id: str,
        owner_age: int | None = None,
        main_style: Iterable[str] = (),
        also_enjoy: Iterable[str] = (),
        avoid: Iterable[str] = (),
        comfort: Iterable[str] = (),
        owner_description: str = "",
        owner_must_respect: Iterable[str] | str = (),
        travellers: Sequence[Mapping[str, Any]] = (),
        start_date: str | None = None,
        end_date: str | None = None,
        arrival_time: str | None = None,
        departure_time: str | None = None,
        accommodation_status: str = "unknown",
        confirmed: bool = False,
    ) -> SetupDraft:
        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise ValueError(f"Unknown trip: {trip_id}")
        payload = build_setup_payload(
            planning_mode=trip.planning_mode,
            owner_age=owner_age,
            main_style=main_style,
            also_enjoy=also_enjoy,
            avoid=avoid,
            comfort=comfort,
            owner_description=owner_description,
            owner_must_respect=owner_must_respect,
            travellers=travellers,
            start_date=start_date,
            end_date=end_date,
            arrival_time=arrival_time,
            departure_time=departure_time,
            accommodation_status=accommodation_status,
            confirmed=confirmed,
        )
        return self.store.save_setup(
            new_setup_draft(trip_id=trip_id, payload=payload, confirmed=confirmed)
        )

    def get_setup(self, trip_id: str) -> SetupDraft | None:
        return self.store.get_setup(trip_id)

    def discover_places(self, *, trip_id: str, force_refresh: bool = False) -> DiscoveryRun:
        trip = self.store.get_trip(trip_id)
        setup = self.store.get_setup(trip_id)
        if trip is None:
            raise ValueError(f"Unknown trip: {trip_id}")
        if setup is None or not setup.confirmed:
            raise ValueError("Confirm the trip setup before discovery")

        provider = self.place_provider or OpenStreetMapProvider()
        provider_name = str(provider.name)
        request = provider.cache_descriptor(trip.destination)
        request_fingerprint = freeze_snapshot(request).sha256
        cache = self.store.get_provider_cache(provider_name, request_fingerprint)
        cached_payload = cache.snapshot.as_dict() if cache else None
        now = datetime.now(timezone.utc)
        cache_is_fresh = bool(
            cache
            and cached_payload
            and cached_payload.get("items")
            and datetime.fromisoformat(cache.expires_at) > now
        )
        provider_error: str | None = None
        from_cache = False

        if cache_is_fresh and not force_refresh:
            payload = cache.snapshot.as_dict()
            retrieved_at = cache.retrieved_at
            expires_at = cache.expires_at
            status = "verified"
            from_cache = True
        else:
            try:
                refresh = getattr(provider, "refresh", None)
                payload = (
                    refresh(trip.destination, cached_payload)
                    if cache and refresh and cached_payload
                    else provider.discover(trip.destination)
                )
                if not isinstance(payload, Mapping):
                    raise ValueError("Provider result must be an object")
            except ProviderUnavailable as error:
                provider_error = str(error)[:240]
                status = "unavailable"
                payload = {"items": [], "coverage": {"known_gaps": [provider_error]}}
            except Exception as error:  # provider boundary must leave a usable local draft
                provider_error = f"{type(error).__name__}: {str(error)[:200]}"
                status = "error"
                payload = {"items": [], "coverage": {"known_gaps": [provider_error]}}
            else:
                status = "verified"

            if status == "verified":
                retrieved_at = now.isoformat()
                expires_at = (
                    now + timedelta(days=int(getattr(provider, "cache_ttl_days", 7)))
                ).isoformat()
                self.store.put_provider_cache(
                    ProviderCacheEntry(
                        provider=provider_name,
                        request_fingerprint=request_fingerprint,
                        snapshot=freeze_snapshot(payload),
                        retrieved_at=retrieved_at,
                        expires_at=expires_at,
                    )
                )
            elif cache:
                payload = cache.snapshot.as_dict()
                retrieved_at = cache.retrieved_at
                expires_at = cache.expires_at
                status = "stale"
                from_cache = True
            else:
                retrieved_at = now.isoformat()
                expires_at = now.isoformat()

        candidates, report = build_candidate_catalog(
            dict(payload), provider=provider_name, retrieved_at=retrieved_at, status=status
        )
        report.update(
            {
                "request": request,
                "request_fingerprint": request_fingerprint,
                "from_cache": from_cache,
                "cache_expires_at": expires_at,
                "provider_error": provider_error,
            }
        )
        return self.store.add_discovery_run(
            new_discovery_run(
                trip_id=trip_id,
                setup_sha256=setup.snapshot.sha256,
                provider=provider_name,
                status=status,
                candidates=candidates,
                report=report,
            )
        )

    def get_latest_discovery(self, trip_id: str) -> DiscoveryRun | None:
        return self.store.get_latest_discovery(trip_id)

    def list_discovery_runs(self, trip_id: str) -> list[DiscoveryRun]:
        return self.store.list_discovery_runs(trip_id)

    def save_candidate_choice(
        self,
        *,
        trip_id: str,
        place_id: str,
        action: str,
        reason: str | None = None,
    ) -> CandidateChoice:
        setup, discovery, candidates = self._current_choice_inputs(trip_id)
        del setup
        candidate = next(
            (item for item in candidates if item["place_id"] == place_id), None
        )
        if candidate is None:
            raise ValueError(f"Unknown candidate in current discovery: {place_id}")
        clean_action, clean_reason = validate_choice(action, reason)
        return self.store.save_candidate_choice(
            new_candidate_choice(
                trip_id=trip_id,
                place_id=place_id,
                discovery_run_id=discovery.run_id,
                action=clean_action,
                reason=clean_reason,
                candidate=candidate,
            )
        )

    def clear_candidate_choice(self, *, trip_id: str, place_id: str) -> None:
        if self.store.get_trip(trip_id) is None:
            raise ValueError(f"Unknown trip: {trip_id}")
        self.store.delete_candidate_choice(trip_id, place_id)

    def list_candidate_choices(self, trip_id: str) -> list[CandidateChoice]:
        return self.store.list_candidate_choices(trip_id)

    def rank_candidates(self, trip_id: str) -> dict[str, Any]:
        setup, discovery, candidates = self._current_choice_inputs(trip_id)
        choices = [
            {
                "place_id": choice.place_id,
                "action": choice.action,
                "reason": choice.reason,
                "candidate": choice.candidate.as_dict(),
            }
            for choice in self.store.list_candidate_choices(trip_id)
        ]
        return build_ranking(
            setup=setup.snapshot.as_dict(),
            candidates=candidates,
            choices=choices,
            discovery_status=discovery.status,
        )

    def generate_plan_preview(
        self, trip_id: str, *, time_limit_seconds: float = 30.0
    ) -> OptimizationPreview:
        optimizer_input = self._optimizer_input(trip_id)
        proposal = optimize_trip(
            optimizer_input, time_limit_seconds=time_limit_seconds
        )
        return self.store.save_optimization_preview(
            new_optimization_preview(
                trip_id=trip_id,
                optimizer_input=optimizer_input,
                proposal=proposal,
            )
        )

    def get_plan_preview(self, trip_id: str) -> OptimizationPreview | None:
        return self.store.get_optimization_preview(trip_id)

    def activate_plan_preview(
        self, *, trip_id: str, variant_id: str
    ) -> PlanVersion:
        preview = self.store.get_optimization_preview(trip_id)
        if preview is None:
            raise ValueError("Generate a plan preview before activation")
        current_input = freeze_snapshot(self._optimizer_input(trip_id))
        if current_input.sha256 != preview.optimizer_input.sha256:
            raise ValueError("Plan preview is stale; optimize the current choices again")
        proposal = preview.proposal.as_dict()
        variant = next(
            (item for item in proposal.get("variants", []) if item["variant_id"] == variant_id),
            None,
        )
        if variant is None:
            raise ValueError(f"Unknown plan variant: {variant_id}")
        if variant["status"] != "ready" or not variant["validation"]["valid"]:
            raise ValueError("Only a fully validated Ready variant can become active")
        version = self.save_plan_version(
            trip_id=trip_id,
            snapshot={
                "schema_version": 1,
                "optimizer_version": proposal["optimizer_version"],
                "input_sha256": proposal["input_sha256"],
                "optimizer_input": preview.optimizer_input.as_dict(),
                "variant": variant,
            },
            cause=f"optimizer:{variant_id}",
        )
        self.store.delete_optimization_preview(trip_id)
        return version

    def _current_choice_inputs(
        self, trip_id: str
    ) -> tuple[SetupDraft, DiscoveryRun, list[dict[str, Any]]]:
        setup = self.store.get_setup(trip_id)
        discovery = self.store.get_latest_discovery(trip_id)
        if setup is None or not setup.confirmed:
            raise ValueError("Confirm the trip setup before ranking")
        if discovery is None:
            raise ValueError("Discover candidates before ranking")
        if discovery.setup_sha256 != setup.snapshot.sha256:
            raise ValueError("Discovery belongs to an older setup; discover again before ranking")
        candidates = discovery.candidates.as_dict().get("candidates", [])
        if not candidates:
            raise ValueError("Current discovery has no candidates to rank")
        return setup, discovery, candidates

    def _optimizer_input(self, trip_id: str) -> dict[str, Any]:
        setup, discovery, current_candidates = self._current_choice_inputs(trip_id)
        setup_payload = setup.snapshot.as_dict()
        choices = [
            choice
            for choice in self.store.list_candidate_choices(trip_id)
            if choice.action in {"must_do", "interested", "maybe"}
        ]
        if not choices:
            raise ValueError("Choose at least one Must do, Interested, or Maybe place")
        ranking = self.rank_candidates(trip_id)
        cards = ranking["cards"]
        basics = setup_payload["trip_basics"]
        start_date, end_date = basics.get("start_date"), basics.get("end_date")
        local_dates = date_range(start_date, end_date) if start_date and end_date else []
        usable_windows = []
        for index, local_date in enumerate(local_dates):
            start = "09:00"
            end = "21:00"
            if index == 0 and basics.get("arrival_time"):
                start = max(start, basics["arrival_time"])
            if index == len(local_dates) - 1 and basics.get("departure_time"):
                end = min(end, basics["departure_time"])
            if start >= end:
                raise ValueError(f"No usable planning time remains on {local_date}")
            usable_windows.append({"date": local_date, "start": start, "end": end})

        candidates = []
        facts = []
        current_by_id = {item["place_id"]: item for item in current_candidates}
        for choice in choices:
            candidate = choice.candidate.as_dict()
            current = current_by_id.get(choice.place_id, candidate)
            card = cards.get(choice.place_id)
            duration = (card or {}).get("duration_estimate", {})
            minimum = int(duration.get("minimum_minutes", 45))
            maximum = int(duration.get("maximum_minutes", 120))
            candidates.append(
                {
                    "id": choice.place_id,
                    "name": candidate["name"],
                    "names": candidate.get("names", {}),
                    "kind": candidate.get("category", "attraction"),
                    "priority": choice.action,
                    "score": float((card or {}).get("total_score", 50)),
                    "latitude": candidate.get("latitude"),
                    "longitude": candidate.get("longitude"),
                    "duration_bounds": {
                        "minimum_minutes": minimum,
                        "ideal_minutes": round((minimum + maximum) / 2),
                        "maximum_minutes": maximum,
                    },
                    "requires_opening_evidence": True,
                    "requires_route_evidence": True,
                    "requires_access_evidence": False,
                }
            )
            operational = current.get("operational_evidence", {})
            opening = operational.get("opening_hours", {})
            interval = _simple_interval(opening.get("value"))
            if opening.get("state") in {"official_confirmed", "current_provider"} and interval:
                facts.append(
                    {
                        "subject_id": choice.place_id,
                        "fact_type": "opening_interval",
                        "value": interval,
                        "status": "verified",
                        "source": "normalized_discovery",
                    }
                )

        owner = setup_payload["owner"]
        travellers = [
            {
                "id": "owner",
                "constraints": owner.get("must_respect", []),
                "preferences": {"dislikes": owner.get("avoid", [])},
            }
        ]
        travellers.extend(
            {
                "id": member["traveller_id"],
                "constraints": member.get("must_respect", []),
                "preferences": {"tags": member.get("tags", [])},
            }
            for member in setup_payload.get("travellers", [])
        )
        capability_gaps = ["ROUTE_SNAPSHOT_MISSING", "DESTINATION_TIMEZONE_UNVERIFIED"]
        if basics.get("accommodation_status") != "booked":
            capability_gaps.append("ACCOMMODATION_BASE_UNCONFIRMED")
        if any(person.get("constraints") for person in travellers):
            capability_gaps.append("FREE_TEXT_HARD_CONSTRAINT_NEEDS_STRUCTURED_CONFIRMATION")
        return {
            "schema_version": 1,
            "source": {
                "setup_sha256": setup.snapshot.sha256,
                "discovery_run_id": discovery.run_id,
                "discovery_status": discovery.status,
            },
            "trip": {
                "timezone": None,
                "local_dates": local_dates,
                "usable_windows": usable_windows,
                "accommodation_status": basics.get("accommodation_status"),
                "provisional": True,
                "requires_route_evidence": True,
                "capability_gaps": capability_gaps,
            },
            "travellers": travellers,
            "candidates": candidates,
            "facts": facts,
            "routes": [],
            "locks": [],
            "weights": setup_payload.get("group_preference_weights", {}),
            "thresholds": _comfort_thresholds(owner),
        }

    def save_plan_version(
        self,
        *,
        trip_id: str,
        snapshot: Mapping[str, Any],
        cause: str,
        activate: bool = True,
    ) -> PlanVersion:
        if self.store.get_trip(trip_id) is None:
            raise ValueError(f"Unknown trip: {trip_id}")
        active = self.store.get_active_plan(trip_id)
        version = new_plan_version(
            trip_id=trip_id,
            payload=snapshot,
            cause=cause,
            parent_version_id=active.version_id if active else None,
        )
        return self.store.add_plan_version(version, activate=activate)

    def restore_plan_version(self, *, trip_id: str, version_id: str) -> PlanVersion:
        target = self.store.get_plan_version(version_id)
        if target is None or target.trip_id != trip_id:
            raise ValueError(f"Unknown plan version for trip: {version_id}")
        return self.save_plan_version(
            trip_id=trip_id,
            snapshot=target.snapshot.as_dict(),
            cause=f"restore:{target.version_id}",
        )

    def get_active_plan(self, trip_id: str) -> PlanVersion | None:
        return self.store.get_active_plan(trip_id)

    def list_plan_versions(self, trip_id: str) -> list[PlanVersion]:
        return self.store.list_plan_versions(trip_id)


def _simple_interval(value: Any) -> dict[str, str] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"\s*((?:[01]\d|2[0-3]):[0-5]\d)\s*-\s*"
        r"((?:[01]\d|2[0-3]):[0-5]\d|24:00)\s*",
        value,
    )
    if not match or match.group(1) >= match.group(2):
        return None
    return {"start": match.group(1), "end": match.group(2)}


def _comfort_thresholds(owner: dict[str, Any]) -> dict[str, Any]:
    avoid = set(owner.get("avoid", []))
    comfort = set(owner.get("comfort", []))
    thresholds: dict[str, Any] = {}
    if "low_walking" in comfort:
        thresholds.update(
            {"walking_minutes_per_leg": 15, "plain_walking_minutes_per_day": 35}
        )
    elif "plain_long_walks" in avoid:
        thresholds.update(
            {"walking_minutes_per_leg": 20, "plain_walking_minutes_per_day": 45}
        )
    elif "balanced_pace" in comfort:
        thresholds.update(
            {"walking_minutes_per_leg": 25, "plain_walking_minutes_per_day": 60}
        )
    return thresholds
