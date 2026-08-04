"""Application actions coordinating the domain core and SQLite adapter."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any

from .core import (
    PLANNING_MODES,
    CandidateChoice,
    DiscoveryRun,
    FrozenSnapshot,
    OptimizationPreview,
    PlanVersion,
    ProviderCacheEntry,
    SetupDraft,
    Trip,
    freeze_snapshot,
    new_candidate_choice,
    new_checklist_item,
    new_discovery_run,
    new_optimization_preview,
    new_plan_version,
    new_setup_draft,
    new_trip,
)
from . import checklist, costs, destinations, exports, interpret, opening, revision, split, usage
from . import setup as setup_module
from .discovery import build_candidate_catalog
from .optimizer import date_range, optimize_trip
from .providers import (
    CARD_PHOTO_LIMIT,
    GooglePlacesCardProvider,
    GooglePlacesOpeningHoursProvider,
    OpenAIRevisionInterpreter,
    RevisionInterpretationUnavailable,
    GoogleTimeZoneProvider,
    OpenRouteServiceProvider,
    OpenStreetMapProvider,
    ProviderBudgetExceeded,
    ProviderUnavailable,
)
from .ranking import build_ranking, validate_choice
from .setup import build_setup_payload
from .store import SQLiteStore


"""Fields a generated checklist item takes from its template on every apply.

Everything else on the item is owner state: progress, note, evidence, source,
authority, last-checked time, and dismissal.
"""
CHECKLIST_TEMPLATE_FIELDS = (
    "template_id",
    "consequence_code",
    "title",
    "title_args",
    "consequence",
    "category",
    "requirement_level",
    "timing",
    "due_date",
    "expected_authority",
    "applies_to",
    "nationality",
    "related_component",
)


# ponytail: a sparse matrix, capped. Every skipped pair is reported, never
# silently dropped, so a thin route set is visible rather than assumed complete.
MAX_ROUTE_REQUESTS = 60


class PlannerRefusal(ValueError):
    """An owner-visible refusal with a stable, translatable code."""

    def __init__(self, code: str, **detail: Any) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


class PlannerActions:
    def __init__(
        self,
        database_path: str | Path,
        *,
        place_provider: Any = None,
        route_provider: Any = None,
        timezone_provider: Any = None,
        hours_provider: Any = None,
        card_provider: Any = None,
        interpreter: Any = None,
    ) -> None:
        self.store = SQLiteStore(database_path)
        self.place_provider = place_provider
        self.route_provider = route_provider
        self.timezone_provider = timezone_provider
        self.hours_provider = hours_provider
        self.card_provider = card_provider
        self.interpreter = interpreter

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

    def journey(self, trip_id: str) -> dict[str, Any]:
        """Return the server-owned stage gates and attention stage for one trip."""

        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        setup = self.store.get_setup(trip_id)
        discovery = self.store.get_latest_discovery(trip_id)
        choices = [
            choice
            for choice in self.store.list_candidate_choices(trip_id)
            if choice.action in {"must_do", "interested", "maybe"}
        ]
        active = self.store.get_active_plan(trip_id)
        gaps: list[str] = []
        if setup is not None and setup.confirmed and discovery is not None and choices:
            try:
                gaps = list(self._optimizer_input(trip_id)["trip"]["capability_gaps"])
            except PlannerRefusal:
                gaps = ["INPUT_NOT_READY"]
        stages = [
            {"key": "setup", "done": bool(setup and setup.confirmed), "blocked_by": None},
            {
                "key": "places",
                "done": bool(discovery is not None and choices),
                "blocked_by": None if setup and setup.confirmed else "setup",
            },
            {
                "key": "evidence",
                "done": bool(choices and (not gaps or trip.planning_mode == "explore_first")),
                "blocked_by": None if discovery is not None and choices else "places",
            },
            {
                "key": "optimize",
                "done": active is not None,
                "blocked_by": None if choices else "places",
            },
            {
                "key": "itinerary",
                "done": active is not None,
                "blocked_by": None if active is not None else "optimize",
            },
        ]
        return {
            "stages": stages,
            "next": next((stage["key"] for stage in stages if not stage["done"]), "itinerary"),
            "capability_gaps": gaps,
            "has_active_plan": active is not None,
            "choice_count": len(choices),
        }

    def delete_trip(self, trip_id: str) -> None:
        if self.store.get_trip(trip_id) is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        self.store.delete_trip(trip_id)

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
        owner_nationality: str | None = None,
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
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        payload = build_setup_payload(
            planning_mode=trip.planning_mode,
            owner_age=owner_age,
            main_style=main_style,
            also_enjoy=also_enjoy,
            avoid=avoid,
            comfort=comfort,
            owner_description=owner_description,
            owner_must_respect=owner_must_respect,
            owner_nationality=owner_nationality,
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

    def setup_vocabulary(self) -> dict[str, Any]:
        """Every list the setup form offers, as stable codes plus picker data.

        Both language labels ship in one payload so switching language never
        refetches: a refetch is a chance for a stored value to move, and
        switching language must never change one. Preference-tag and
        accommodation display text still comes from the copy catalogue -- these
        are codes, not copy.

        The country and city tables are **picker convenience only**. Both fields
        accept a typed value, so a destination absent from this table stays
        reachable; the worldwide acceptance check requires it.
        """

        # Both of these are frozensets in the core, which is right for
        # validation and useless for a radio group: a picker needs a stable
        # order, and these two carry meaning in their order. Planning mode leads
        # with the less committed option, accommodation runs from least to most
        # certain. Asserted against the core sets so a new member cannot be
        # added there and silently miss the form.
        modes = ("explore_first", "ready_to_schedule")
        statuses = ("unknown", "not_booked", "booked")
        assert set(modes) == set(PLANNING_MODES)
        assert set(statuses) == set(setup_module.ACCOMMODATION_STATUSES)
        return {
            "planning_modes": list(modes),
            "accommodation_statuses": list(statuses),
            "tag_groups": {
                "main_style": list(setup_module.MAIN_STYLE_TAGS),
                "also_enjoy": list(setup_module.ALSO_ENJOY_TAGS),
                "avoid": list(setup_module.AVOID_TAGS),
                "comfort": list(setup_module.COMFORT_TAGS),
            },
            "countries": [
                {
                    "code": country,
                    "label": {
                        "en": destinations.country_label(country, "en"),
                        "th": destinations.country_label(country, "th"),
                    },
                    "cities": list(destinations.city_options(country)),
                }
                for country in destinations.country_options()
            ],
        }

    def discover_places(self, *, trip_id: str, force_refresh: bool = False) -> DiscoveryRun:
        trip = self.store.get_trip(trip_id)
        setup = self.store.get_setup(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        if setup is None or not setup.confirmed:
            raise PlannerRefusal("setup_not_confirmed")

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
            raise PlannerRefusal("unknown_candidate", place_id=place_id)
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
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
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

    def enrich_place_card(
        self, trip_id: str, place_id: str, *, language: str = "en"
    ) -> dict[str, Any]:
        """Fetch a session-only photo/rating/review overlay for one visible card."""

        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        _, _, candidates = self._current_choice_inputs(trip_id)
        candidate = next(
            (item for item in candidates if item["place_id"] == place_id), None
        )
        if candidate is None:
            raise PlannerRefusal("unknown_candidate", place_id=place_id)

        provider = self.card_provider or GooglePlacesCardProvider()
        self._spend(
            operation=provider.details_operation,
            count=1,
            trip_id=trip_id,
            detail={"place_id": place_id},
        )
        details = provider.details(
            candidate,
            destination=trip.destination,
            language="th" if language == "th" else "en",
        )
        details = {**details, "retrieved_at": datetime.now(timezone.utc).isoformat()}
        photos = details.get("photos") or (
            [details["photo"]] if details.get("photo") else []
        )
        gallery = []
        for photo in photos[:CARD_PHOTO_LIMIT]:
            try:
                self._spend(
                    operation=provider.photo_operation,
                    count=1,
                    trip_id=trip_id,
                    detail={"place_id": place_id},
                )
                uri = provider.photo_uri(photo["name"])
            except (ProviderBudgetExceeded, ProviderUnavailable) as error:
                details["photo_error"] = str(error)[:160]
                break
            gallery.append({**photo, "uri": uri})
        details["photo_gallery"] = gallery
        details["photo_uri"] = gallery[0]["uri"] if gallery else None
        return details

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
            raise PlannerRefusal("preview_missing")
        current_input = freeze_snapshot(self._optimizer_input(trip_id))
        if current_input.sha256 != preview.optimizer_input.sha256:
            raise PlannerRefusal("preview_stale")
        proposal = preview.proposal.as_dict()
        variant = next(
            (item for item in proposal.get("variants", []) if item["variant_id"] == variant_id),
            None,
        )
        if variant is None:
            raise PlannerRefusal("unknown_plan_variant", variant_id=variant_id)
        trip = self.store.get_trip(trip_id)
        provisional_allowed = bool(
            trip
            and trip.planning_mode == "explore_first"
            and variant["status"] == "provisional"
        )
        if not variant["validation"]["valid"] or (
            variant["status"] != "ready" and not provisional_allowed
        ):
            raise PlannerRefusal(
                "variant_not_ready", variant_id=variant_id, status=variant["status"]
            )
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
            raise PlannerRefusal("setup_not_confirmed")
        if discovery is None:
            raise PlannerRefusal("discovery_missing")
        if discovery.setup_sha256 != setup.snapshot.sha256:
            raise PlannerRefusal("discovery_stale")
        candidates = discovery.candidates.as_dict().get("candidates", [])
        if not candidates:
            raise PlannerRefusal("discovery_empty")
        return setup, discovery, candidates

    def _optimizer_input(self, trip_id: str) -> dict[str, Any]:
        setup, discovery, current_candidates = self._current_choice_inputs(trip_id)
        trip = self.store.get_trip(trip_id)
        setup_payload = setup.snapshot.as_dict()
        allow_provisional_assumptions = setup_payload["planning_mode"] == "explore_first"
        choices = [
            choice
            for choice in self.store.list_candidate_choices(trip_id)
            if choice.action in {"must_do", "interested", "maybe"}
        ]
        if not choices:
            raise PlannerRefusal("no_places_chosen", purpose="planning", minimum=1)
        ranking = self.rank_candidates(trip_id)
        cards = ranking["cards"]
        basics = setup_payload["trip_basics"]
        start_date, end_date = basics.get("start_date"), basics.get("end_date")
        local_dates = date_range(start_date, end_date) if start_date and end_date else []
        usable_windows = []
        for index, local_date in enumerate(local_dates):
            # The reference trips routinely begin before 09:00 and end after
            # 21:00 once breakfast, hotel transitions, and the trip back to the
            # base are represented. Arrival/departure still tighten their own
            # day rather than silently becoming attraction time.
            start = "08:00"
            end = "22:00"
            if index == 0 and basics.get("arrival_time"):
                start = basics["arrival_time"]
            if index == len(local_dates) - 1 and basics.get("departure_time"):
                end = basics["departure_time"]
            if start >= end:
                raise PlannerRefusal("no_planning_time", local_date=local_date)
            usable_windows.append({"date": local_date, "start": start, "end": end})

        candidates = []
        facts = []
        opening_missing = False
        opening_evidence = self.opening_intervals(trip_id)
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
            provider_hours = opening_evidence.get(choice.place_id) or {}
            if provider_hours.get("interval"):
                facts.append(
                    {
                        "subject_id": choice.place_id,
                        "fact_type": "opening_interval",
                        "value": provider_hours["interval"],
                        "status": "verified",
                        "source": provider_hours.get("provider") or "provider_hours",
                        "retrieved_at": provider_hours.get("retrieved_at"),
                        # The reduction across trip dates, recorded for audit.
                        "applies_to_dates": local_dates,
                    }
                )
                continue
            operational = current.get("operational_evidence", {})
            hours = operational.get("opening_hours", {})
            interval = _simple_interval(hours.get("value"))
            if hours.get("state") in {"official_confirmed", "current_provider"} and interval:
                facts.append(
                    {
                        "subject_id": choice.place_id,
                        "fact_type": "opening_interval",
                        "value": interval,
                        "status": "verified",
                        "source": "normalized_discovery",
                    }
                )
                continue
            if local_dates:
                opening_missing = True
                if allow_provisional_assumptions and provider_hours.get("reason") in {
                    "OPENING_NOT_FETCHED",
                    "NO_PUBLISHED_HOURS",
                    "EVIDENCE_EXPIRED",
                    "EVIDENCE_NORMALIZER_OUTDATED",
                }:
                    facts.append(
                        {
                            "subject_id": choice.place_id,
                            "fact_type": "opening_interval",
                            "value": {"start": "09:00", "end": "21:00"},
                            "status": "assumed",
                            "source": "explore_first_planning_assumption",
                            "applies_to_dates": local_dates,
                        }
                    )

        accommodation_base = self.get_accommodation_base(trip_id)
        if accommodation_base:
            candidates.append(
                {
                    "id": "booked_accommodation_base",
                    "name": accommodation_base["name"],
                    "names": {"en": accommodation_base["name"]},
                    "kind": "hotel_area",
                    "priority": "alternative",
                    "score": 0,
                    "latitude": accommodation_base["latitude"],
                    "longitude": accommodation_base["longitude"],
                    "planning_basis": "booked_accommodation",
                }
            )
        elif allow_provisional_assumptions and basics.get("accommodation_status") != "booked":
            located = [
                item
                for item in candidates
                if item.get("latitude") is not None and item.get("longitude") is not None
            ]
            if located:
                candidates.append(
                    {
                        "id": "provisional_accommodation_base",
                        "name": "Provisional base around the selected-place center",
                        "names": {
                            "en": "Provisional base around the selected-place center",
                            "th": "ฐานที่พักชั่วคราวบริเวณกึ่งกลางสถานที่ที่เลือก",
                        },
                        "kind": "hotel_area",
                        "priority": "alternative",
                        "score": 0,
                        "latitude": round(
                            sum(float(item["latitude"]) for item in located) / len(located),
                            6,
                        ),
                        "longitude": round(
                            sum(float(item["longitude"]) for item in located) / len(located),
                            6,
                        ),
                        "planning_basis": "selected_place_centroid",
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
        active_base_id = (
            "booked_accommodation_base"
            if accommodation_base
            else (
                "provisional_accommodation_base"
                if any(item.get("id") == "provisional_accommodation_base" for item in candidates)
                else None
            )
        )
        accommodation_ids = {
            "booked_accommodation_base",
            "provisional_accommodation_base",
        }
        routes = [
            route
            for route in self.list_routes(trip_id)
            if route.get("status") == "verified"
            and all(
                endpoint not in accommodation_ids or endpoint == active_base_id
                for endpoint in (route.get("origin_id"), route.get("destination_id"))
            )
        ]
        zone = self.get_timezone_evidence(trip_id)
        verified_zone = zone["timezone"] if zone and zone.get("status") == "verified" else None
        accommodation_confirmed = bool(accommodation_base) or basics.get(
            "accommodation_status"
        ) == "booked"
        capability_gaps = []
        if not verified_zone:
            capability_gaps.append("DESTINATION_TIMEZONE_UNVERIFIED")
        if not routes:
            capability_gaps.append("ROUTE_SNAPSHOT_MISSING")
        if not accommodation_confirmed:
            capability_gaps.append("ACCOMMODATION_BASE_UNCONFIRMED")
        if opening_missing:
            capability_gaps.append("OPENING_EVIDENCE_MISSING")
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
                "destination": trip.destination if trip else "",
                "planning_mode": setup_payload["planning_mode"],
                "allow_provisional_assumptions": allow_provisional_assumptions,
                "include_operational_timeline": True,
                "arrival_time": basics.get("arrival_time"),
                "departure_time": basics.get("departure_time"),
                "accommodation_base_id": (
                    "booked_accommodation_base" if accommodation_base else None
                ),
                "timezone": verified_zone,
                "local_dates": local_dates,
                "usable_windows": usable_windows,
                # Setup speaks unknown/not_booked/booked; the optimizer and the
                # frozen fixtures speak unbooked.  Translate at this boundary so
                # hotel-area recommendations actually fire.
                "accommodation_status": (
                    "booked" if accommodation_confirmed else "unbooked"
                ),
                # Derived, not assumed: an approximate arrival or departure, or an
                # unbooked base, keeps the plan provisional as decided. Once the
                # owner confirms all three, a validated variant may become Ready.
                "provisional": bool(
                    not accommodation_confirmed
                    or not basics.get("arrival_time")
                    or not basics.get("departure_time")
                ),
                "requires_route_evidence": True,
                "capability_gaps": capability_gaps,
            },
            "travellers": travellers,
            "candidates": candidates,
            "facts": facts,
            "routes": routes,
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
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
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
            raise PlannerRefusal(
                "unknown_plan_version", trip_id=trip_id, version_id=version_id
            )
        return self.save_plan_version(
            trip_id=trip_id,
            snapshot=target.snapshot.as_dict(),
            cause=f"restore:{target.version_id}",
        )

    def get_active_plan(self, trip_id: str) -> PlanVersion | None:
        return self.store.get_active_plan(trip_id)

    def checklist_vocabulary(self) -> dict[str, Any]:
        """Every list the readiness board offers, as stable codes.

        Display text comes from the copy catalogue -- these are codes, not copy.
        The orders are explicit rather than derived: `TIMING_BUCKETS` carries
        meaning in its order (soonest first) and the rest need a stable one for
        a picker. Each is asserted against the core tuple so a new member cannot
        be added in `checklist.py` and silently miss the board.
        """

        categories = (
            "entry_requirements",
            "immigration_customs",
            "money",
            "connectivity",
            "insurance_health",
            "transport_setup",
            "reservations",
            "registrations",
            "packing",
            "local_rules",
            "emergency",
            "accommodation",
        )
        assert set(categories) == set(checklist.CATEGORIES)
        assert categories == checklist.CATEGORIES, "category order drifted from the core"
        return {
            "categories": list(categories),
            # Ordered by how binding each level is, not alphabetically.
            "requirement_levels": list(checklist.REQUIREMENT_LEVELS),
            # Soonest first; the board groups by this.
            "timing_buckets": list(checklist.TIMING_BUCKETS),
            "progress_states": list(checklist.PROGRESS_STATES),
            "evidence_states": list(checklist.EVIDENCE_STATES),
            "authority_types": list(checklist.AUTHORITY_TYPES),
            # Requirement level and evidence state move independently, and a
            # verified `required` item with no responsible authority is refused.
            "closed_states": sorted(checklist.CLOSED_STATES),
        }

    def propose_checklist(self, trip_id: str) -> dict[str, Any]:
        """Preview the generated board against what is already saved."""

        trip = self.store.get_trip(trip_id)
        setup = self.store.get_setup(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        if setup is None:
            raise PlannerRefusal("setup_missing")
        proposed = checklist.propose_items(
            destination=trip.destination,
            setup=setup.snapshot.as_dict(),
            choices=[
                {
                    "place_id": choice.place_id,
                    "action": choice.action,
                    "candidate": choice.candidate.as_dict(),
                }
                for choice in self.store.list_candidate_choices(trip_id)
            ],
            facts=self._checklist_facts(trip_id),
        )
        current = self.list_checklist_items(trip_id)
        return {"proposed": proposed, **checklist.diff_proposal(current, proposed)}

    def apply_checklist_proposal(self, trip_id: str) -> dict[str, int]:
        """Apply the previewed changes. A removal is dismissed, never deleted."""

        preview = self.propose_checklist(trip_id)
        saved = {
            item["generated_key"]: item
            for item in self.list_checklist_items(trip_id)
            if item.get("generated_key")
        }
        for item in preview["additions"]:
            self.store.upsert_checklist_item(
                new_checklist_item(
                    trip_id=trip_id,
                    payload=checklist.validate_item(item),
                    generated_key=item["generated_key"],
                    origin="generated",
                )
            )
        # Refresh template-derived wording and grounds on the items already
        # saved, keeping owner state. Without this, a template change or a new
        # language never reaches a board that was applied earlier.
        refreshed = 0
        for item in preview["proposed"]:
            existing = saved.get(item["generated_key"])
            if existing is None:
                continue
            merged = {
                **existing,
                **{key: item[key] for key in CHECKLIST_TEMPLATE_FIELDS if key in item},
            }
            if merged != existing:
                self._write_checklist_item(trip_id, merged)
                refreshed += 1
        for item in preview["removals"]:
            self._write_checklist_item(trip_id, {**item, "dismissed": True})
        return {
            "added": len(preview["additions"]),
            "refreshed": refreshed,
            "deadlines_changed": len(preview["deadline_changes"]),
            "dismissed": len(preview["removals"]),
        }

    def list_checklist_items(self, trip_id: str) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self.store.list_checklist_items(trip_id)]

    def save_checklist_item(
        self, *, trip_id: str, item: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Add or edit one board item, generated or owner-authored."""

        payload = dict(item)
        payload.setdefault("origin", "manual")
        payload.setdefault("progress", "to_do")
        payload.setdefault("evidence_state", "verification_needed")
        payload.setdefault("timing", "do_now")
        payload.setdefault("category", "packing")
        payload.setdefault("requirement_level", "optional")
        payload.setdefault("owner", "owner")
        payload.setdefault("applies_to", [])
        payload.setdefault("dismissed", False)
        if payload.get("timing") and not payload.get("due_date"):
            setup = self.store.get_setup(trip_id)
            basics = (setup.snapshot.as_dict().get("trip_basics", {}) if setup else {})
            payload["due_date"] = checklist.due_date_for(
                payload["timing"], basics.get("start_date")
            )
        return self._write_checklist_item(trip_id, payload)

    def set_checklist_progress(
        self, *, trip_id: str, item_id: str, progress: str, note: str | None = None
    ) -> dict[str, Any]:
        item = self._checklist_item(trip_id, item_id)
        return self._write_checklist_item(
            trip_id, {**item, "progress": progress, "note": note or item.get("note")}
        )

    def record_checklist_evidence(
        self,
        *,
        trip_id: str,
        item_id: str,
        source_url: str,
        authority_type: str,
        checked_at: str | None = None,
    ) -> dict[str, Any]:
        """Move an item to verified by recording its official source."""

        item = self._checklist_item(trip_id, item_id)
        return self._write_checklist_item(
            trip_id,
            {
                **item,
                "evidence_state": "verified",
                "source_url": source_url,
                "authority_type": authority_type,
                "last_checked_at": checked_at or datetime.now(timezone.utc).isoformat(),
            },
        )

    def set_checklist_dismissed(
        self, *, trip_id: str, item_id: str, dismissed: bool
    ) -> dict[str, Any]:
        item = self._checklist_item(trip_id, item_id)
        return self._write_checklist_item(trip_id, {**item, "dismissed": bool(dismissed)})

    def checklist_readiness(self, trip_id: str, *, today: str | None = None) -> dict[str, Any]:
        stamp = today or datetime.now(timezone.utc).date().isoformat()
        setup = self.store.get_setup(trip_id)
        basics = setup.snapshot.as_dict().get("trip_basics", {}) if setup else {}
        items = self.list_checklist_items(trip_id)
        for item in items:
            if checklist.needs_recheck(
                item, today=stamp, start_date=basics.get("start_date")
            ):
                item["evidence_state"] = "verification_needed"
                item["stale"] = True
        return checklist.readiness(items, today=stamp)

    def _checklist_item(self, trip_id: str, item_id: str) -> dict[str, Any]:
        stored = self.store.get_checklist_item(item_id)
        if stored is None or stored.trip_id != trip_id:
            raise PlannerRefusal("unknown_checklist_item", item_id=item_id)
        return stored.as_dict()

    def _write_checklist_item(
        self, trip_id: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        clean = checklist.validate_item(dict(payload))
        stored = self.store.upsert_checklist_item(
            new_checklist_item(
                trip_id=trip_id,
                payload={
                    key: value
                    for key, value in clean.items()
                    if key not in {"item_id", "updated_at"}
                },
                generated_key=clean.get("generated_key"),
                origin=clean.get("origin", "manual"),
            )
        )
        return stored.as_dict()

    def _checklist_facts(self, trip_id: str) -> list[dict[str, Any]]:
        """Verified operational facts that justify a booking or access task."""

        active = self.store.get_active_plan(trip_id)
        if active is None:
            return []
        snapshot = active.snapshot.as_dict()
        planner_input = snapshot.get("optimizer_input")
        if not isinstance(planner_input, dict):
            return []
        return list(planner_input.get("facts", []))

    def refresh_opening_hours(self, trip_id: str, *, force: bool = False) -> dict[str, Any]:
        """Fetch opening hours for the selected places, one paid call each."""

        trip = self.store.get_trip(trip_id)
        setup = self.store.get_setup(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        if setup is None:
            raise PlannerRefusal("setup_missing")
        places = self._selected_places(trip_id)
        if not places:
            raise PlannerRefusal("no_places_chosen", purpose="opening_hours", minimum=1)

        provider = self.hours_provider or GooglePlacesOpeningHoursProvider()
        now = datetime.now(timezone.utc)
        existing = {
            item["place_id"]: item
            for item in self.store.list_place_evidence(trip_id, provider.kind)
        }
        fetched = cached = failed = 0
        errors: list[str] = []
        for place in places:
            current = existing.get(place["place_id"])
            if (
                not force
                and current
                and current["expires_at"] > now.isoformat()
                and int(current.get("normalizer_version") or 0)
                >= GooglePlacesOpeningHoursProvider.normalizer_version
            ):
                cached += 1
                self.record_paid_call(
                    operation=provider.operation,
                    count=1,
                    trip_id=trip_id,
                    outcome="cached",
                )
                continue
            try:
                self._spend(
                    operation=provider.operation,
                    count=1,
                    trip_id=trip_id,
                    detail={"place_id": place["place_id"]},
                )
                value = provider.opening_hours(place)
            except ProviderBudgetExceeded:
                raise
            except ProviderUnavailable as error:
                failed += 1
                message = str(error)[:160]
                if message not in errors:
                    errors.append(message)
                continue
            self.store.upsert_place_evidence(
                trip_id=trip_id,
                place_id=place["place_id"],
                kind=provider.kind,
                value=value,
                provider=str(provider.name),
                retrieved_at=now.isoformat(),
                expires_at=(
                    now + timedelta(days=int(getattr(provider, "cache_ttl_days", 3)))
                ).isoformat(),
            )
            fetched += 1

        usable = self.opening_intervals(trip_id)
        return {
            "places": len(places),
            "fetched": fetched,
            "from_cache": cached,
            "failed": failed,
            "provider_errors": errors,
            "usable_intervals": len(
                [item for item in usable.values() if item["interval"]]
            ),
            "unusable": {
                place_id: item["reason"]
                for place_id, item in usable.items()
                if not item["interval"]
            },
        }

    def opening_intervals(self, trip_id: str) -> dict[str, Any]:
        """The interval valid on every trip date, per place, with its reason."""

        setup = self.store.get_setup(trip_id)
        basics = setup.snapshot.as_dict().get("trip_basics", {}) if setup else {}
        start, end = basics.get("start_date"), basics.get("end_date")
        local_dates = date_range(start, end) if start and end else []
        now = datetime.now(timezone.utc).isoformat()
        result: dict[str, Any] = {
            place["place_id"]: {
                "interval": None,
                "reason": "OPENING_NOT_FETCHED",
                "retrieved_at": None,
                "provider": None,
            }
            for place in self._selected_places(trip_id)
        }
        for evidence in self.store.list_place_evidence(
            trip_id, GooglePlacesOpeningHoursProvider.kind
        ):
            if (
                int(evidence.get("normalizer_version") or 0)
                < GooglePlacesOpeningHoursProvider.normalizer_version
            ):
                result[evidence["place_id"]] = {
                    "interval": None,
                    "reason": "EVIDENCE_NORMALIZER_OUTDATED",
                    "retrieved_at": evidence["retrieved_at"],
                    "provider": evidence.get("provider"),
                }
                continue
            if evidence["expires_at"] <= now:
                result[evidence["place_id"]] = {
                    "interval": None,
                    "reason": "EVIDENCE_EXPIRED",
                    "retrieved_at": evidence["retrieved_at"],
                }
                continue
            reduced = opening.common_interval(
                evidence.get("weekly_periods") or [], local_dates
            )
            result[evidence["place_id"]] = {
                **reduced,
                "retrieved_at": evidence["retrieved_at"],
                "provider": evidence.get("provider"),
            }
        return result

    def confirm_opening_window(
        self,
        trip_id: str,
        place_id: str,
        *,
        start: str,
        end: str,
    ) -> dict[str, Any]:
        """Store a planning window the owner says they independently checked."""

        places = {item["place_id"]: item for item in self._selected_places(trip_id)}
        place = places.get(place_id)
        if place is None:
            raise PlannerRefusal("place_not_chosen", place_id=place_id)
        interval = _simple_interval(f"{start}-{end}")
        if interval is None:
            raise PlannerRefusal("invalid_time_window", start=start, end=end)
        now = datetime.now(timezone.utc)
        value = {
            "kind": GooglePlacesOpeningHoursProvider.kind,
            "normalizer_version": GooglePlacesOpeningHoursProvider.normalizer_version,
            "place_id": place_id,
            "provider_place_id": None,
            "matched_name": place["name"],
            "weekly_periods": [
                {
                    "day": day,
                    "start": interval["start"],
                    "end": interval["end"],
                    "all_day": False,
                    "overnight": False,
                }
                for day in range(7)
            ],
            "weekday_descriptions": [],
            "provider": "owner_confirmation",
            "status": "owner_confirmed",
        }
        return self.store.upsert_place_evidence(
            trip_id=trip_id,
            place_id=place_id,
            kind=GooglePlacesOpeningHoursProvider.kind,
            value=value,
            provider="owner_confirmation",
            retrieved_at=now.isoformat(),
            expires_at=(now + timedelta(days=365)).isoformat(),
        )

    def get_accommodation_base(self, trip_id: str) -> dict[str, Any] | None:
        return self.store.get_trip_evidence(trip_id, "accommodation_base")

    def confirm_accommodation_base(self, trip_id: str, query: str) -> dict[str, Any]:
        """Geocode one owner-entered booked stay and keep it as the routing base."""

        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        name = query.strip()
        if not name:
            raise PlannerRefusal("accommodation_query_missing")
        provider = (
            self.place_provider
            if self.place_provider is not None and hasattr(self.place_provider, "geocode")
            else OpenStreetMapProvider()
        )
        search = (
            name
            if trip.destination.casefold() in name.casefold()
            else f"{name}, {trip.destination}"
        )
        value = {**provider.geocode(search), "name": name}
        now = datetime.now(timezone.utc)
        self.store.upsert_trip_evidence(
            trip_id=trip_id,
            kind="accommodation_base",
            value=value,
            provider=str(provider.name),
            retrieved_at=now.isoformat(),
            expires_at=(now + timedelta(days=3650)).isoformat(),
        )
        return value

    def _selected_places(self, trip_id: str) -> list[dict[str, Any]]:
        trip = self.store.get_trip(trip_id)
        places = []
        for choice in self.store.list_candidate_choices(trip_id):
            if choice.action not in {"must_do", "interested", "maybe"}:
                continue
            candidate = choice.candidate.as_dict()
            if candidate.get("latitude") is None or candidate.get("longitude") is None:
                continue
            places.append(
                {
                    "place_id": choice.place_id,
                    "name": candidate.get("name") or choice.place_id,
                    "names": candidate.get("names") or {},
                    "category": candidate.get("category") or "attraction",
                    "destination": trip.destination if trip else "",
                    "latitude": float(candidate["latitude"]),
                    "longitude": float(candidate["longitude"]),
                }
            )
        return sorted(places, key=lambda item: item["place_id"])

    def refresh_timezone(self, trip_id: str, *, force: bool = False) -> dict[str, Any]:
        """Look up the destination's IANA zone once, from its discovered centre."""

        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        provider = self.timezone_provider or GoogleTimeZoneProvider()
        now = datetime.now(timezone.utc)
        existing = self.store.get_trip_evidence(trip_id, provider.kind)
        if not force and existing and existing["expires_at"] > now.isoformat():
            self.record_paid_call(
                operation=provider.operation, count=1, trip_id=trip_id, outcome="cached"
            )
            return {**existing, "from_cache": True}

        centre = self._destination_centre(trip_id)
        self._spend(
            operation=provider.operation,
            count=1,
            trip_id=trip_id,
            detail={"latitude": centre["latitude"], "longitude": centre["longitude"]},
        )
        value = provider.lookup(
            latitude=centre["latitude"],
            longitude=centre["longitude"],
            timestamp=int(now.timestamp()),
        )
        self.store.upsert_trip_evidence(
            trip_id=trip_id,
            kind=provider.kind,
            value=value,
            provider=str(provider.name),
            retrieved_at=now.isoformat(),
            expires_at=(
                now + timedelta(days=int(getattr(provider, "cache_ttl_days", 180)))
            ).isoformat(),
        )
        return {**value, "from_cache": False, "retrieved_at": now.isoformat()}

    def get_timezone_evidence(self, trip_id: str) -> dict[str, Any] | None:
        """Unexpired zone evidence, or None. An expired zone is not verified."""

        evidence = self.store.get_trip_evidence(trip_id, GoogleTimeZoneProvider.kind)
        if evidence is None:
            return None
        if evidence["expires_at"] <= datetime.now(timezone.utc).isoformat():
            return {**evidence, "status": "stale"}
        return evidence

    def _destination_centre(self, trip_id: str) -> dict[str, float]:
        """The centre of the discovered coverage box, or a selected place."""

        discovery = self.store.get_latest_discovery(trip_id)
        if discovery is not None:
            # The discovery report records the searched window as query_boundary,
            # in the provider's [south, west, north, east] order.
            bbox = discovery.report.as_dict().get("query_boundary")
            if isinstance(bbox, list) and len(bbox) == 4:
                south, west, north, east = (float(value) for value in bbox)
                return {
                    "latitude": round((south + north) / 2, 6),
                    "longitude": round((west + east) / 2, 6),
                }
        points = self._route_points(trip_id)
        if points:
            return {
                "latitude": points[0]["latitude"],
                "longitude": points[0]["longitude"],
            }
        raise PlannerRefusal("discovery_missing")

    def refresh_routes(self, trip_id: str, *, force: bool = False) -> dict[str, Any]:
        """Fetch walking routes between the selected places, sparsely and capped."""

        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        points = self._route_points(trip_id)
        if len(points) < 2:
            raise PlannerRefusal("insufficient_geocoded_places", minimum=2)

        provider = self.route_provider or OpenRouteServiceProvider()
        now = datetime.now(timezone.utc)
        existing = {
            (route["origin_id"], route["destination_id"], route["mode"]): route
            for route in self.store.list_route_snapshots(trip_id)
        }
        pairs = [
            (origin, destination)
            for origin in points
            for destination in points
            if origin["place_id"] != destination["place_id"]
        ]
        pairs.sort(key=lambda pair: (pair[0]["place_id"], pair[1]["place_id"]))
        attempted, skipped = pairs[:MAX_ROUTE_REQUESTS], pairs[MAX_ROUTE_REQUESTS:]

        fetched = cached = failed = 0
        errors: list[str] = []
        for origin, destination in attempted:
            key = (origin["place_id"], destination["place_id"], provider.mode)
            if not force and key in existing and existing[key]["expires_at"] > now.isoformat():
                cached += 1
                continue
            try:
                self._spend(
                    operation=provider.operation,
                    count=1,
                    trip_id=trip_id,
                    detail={"origin": key[0], "destination": key[1], "mode": key[2]},
                )
                route = provider.route(origin, destination)
            except ProviderBudgetExceeded:
                raise
            except ProviderUnavailable as error:
                failed += 1
                message = str(error)[:160]
                if message not in errors:
                    errors.append(message)
                continue
            self.store.upsert_route_snapshot(
                trip_id=trip_id,
                route=route,
                provider=str(provider.name),
                retrieved_at=now.isoformat(),
                expires_at=(
                    now + timedelta(days=int(getattr(provider, "cache_ttl_days", 14)))
                ).isoformat(),
            )
            fetched += 1

        return {
            "places": len(points),
            "pairs_needed": len(pairs),
            "fetched": fetched,
            "from_cache": cached,
            "failed": failed,
            "skipped_over_cap": len(skipped),
            "request_cap": MAX_ROUTE_REQUESTS,
            "provider_errors": errors,
            "routes_available": len(self.store.list_route_snapshots(trip_id)),
        }

    def list_routes(self, trip_id: str) -> list[dict[str, Any]]:
        """Unexpired normalized routes; an expired leg is no longer verified."""

        now = datetime.now(timezone.utc).isoformat()
        routes = []
        for route in self.store.list_route_snapshots(trip_id):
            fresh = route["expires_at"] > now
            routes.append(
                {
                    **{k: v for k, v in route.items() if k not in {"expires_at", "retrieved_at"}},
                    "status": route.get("status") if fresh else "stale",
                    "retrieved_at": route["retrieved_at"],
                    "expires_at": route["expires_at"],
                }
            )
        return routes

    def _route_points(self, trip_id: str) -> list[dict[str, Any]]:
        """Selected places that carry coordinates, deterministically ordered."""

        points = []
        for choice in self.store.list_candidate_choices(trip_id):
            if choice.action not in {"must_do", "interested", "maybe"}:
                continue
            candidate = choice.candidate.as_dict()
            latitude, longitude = candidate.get("latitude"), candidate.get("longitude")
            if latitude is None or longitude is None:
                continue
            points.append(
                {
                    "place_id": choice.place_id,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                }
            )
        accommodation = self.get_accommodation_base(trip_id)
        trip = self.store.get_trip(trip_id)
        setup = self.store.get_setup(trip_id)
        basics = setup.snapshot.as_dict().get("trip_basics", {}) if setup else {}
        if accommodation:
            points.append(
                {
                    "place_id": "booked_accommodation_base",
                    "latitude": float(accommodation["latitude"]),
                    "longitude": float(accommodation["longitude"]),
                }
            )
        elif (
            trip
            and trip.planning_mode == "explore_first"
            and basics.get("accommodation_status") != "booked"
            and points
        ):
            points.append(
                {
                    "place_id": "provisional_accommodation_base",
                    "latitude": round(
                        sum(item["latitude"] for item in points) / len(points), 6
                    ),
                    "longitude": round(
                        sum(item["longitude"] for item in points) / len(points), 6
                    ),
                }
            )
        return sorted(points, key=lambda item: item["place_id"])

    def paid_usage_status(self, *, month: str | None = None) -> dict[str, Any]:
        """This month's paid spend against the cap, with per-operation counts."""

        now = datetime.now(timezone.utc).isoformat()
        window = month or usage.month_of(now)
        entries = self.store.list_paid_usage()
        summary = usage.totals(entries, month=window)
        cap = self.store.get_paid_cap() or usage.CAP_USD
        return {
            **summary,
            **usage.status(summary["estimated_usd"], cap_usd=cap),
            "cap_is_owner_raised": cap != usage.CAP_USD,
        }

    def set_paid_cap(self, cap_usd: float) -> float:
        """Only the owner may raise the stop threshold."""

        if float(cap_usd) < 0:
            raise PlannerRefusal("invalid_paid_cap", cap_usd=float(cap_usd))
        return self.store.set_paid_cap(
            cap_usd=float(cap_usd), now=datetime.now(timezone.utc).isoformat()
        )

    def check_paid_call(self, *, operation: str, count: int = 1) -> dict[str, Any]:
        """Judge a prospective paid call. Callers must honour `allowed`."""

        current = self.paid_usage_status()
        return usage.check_allowed(
            operation=operation,
            count=count,
            spent_usd=current["estimated_usd"],
            cap_usd=current["cap_usd"],
        )

    def record_paid_call(
        self,
        *,
        operation: str,
        count: int = 1,
        trip_id: str | None = None,
        outcome: str = "success",
        detail: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.store.add_paid_usage(
            usage.new_entry(
                operation=operation,
                count=count,
                created_at=datetime.now(timezone.utc).isoformat(),
                trip_id=trip_id,
                outcome=outcome,
                detail=dict(detail or {}),
            )
        )

    def _spend(
        self, *, operation: str, count: int, trip_id: str | None, detail: Mapping[str, Any]
    ) -> None:
        """Refuse a call that would cross the cap, then record what it cost."""

        decision = self.check_paid_call(operation=operation, count=count)
        if not decision["allowed"]:
            raise ProviderBudgetExceeded(decision["reason"])
        self.record_paid_call(
            operation=operation, count=count, trip_id=trip_id, detail=detail
        )

    def save_rate_snapshot(
        self,
        *,
        trip_id: str,
        rates: Mapping[str, Any],
        as_of: str,
        source: str,
        buffer_percent: float = 0.0,
    ) -> dict[str, Any]:
        """Record the sourced, timestamped rates costs convert against."""

        if self.store.get_trip(trip_id) is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        snapshot = costs.new_rate_snapshot(
            rates=dict(rates), as_of=as_of, source=source, buffer_percent=buffer_percent
        )
        return self.store.save_rate_snapshot(
            trip_id=trip_id,
            snapshot=freeze_snapshot(snapshot),
            now=datetime.now(timezone.utc).isoformat(),
        )

    def get_rate_snapshot(self, trip_id: str) -> dict[str, Any] | None:
        return self.store.get_rate_snapshot(trip_id)

    def save_cost_item(
        self, *, trip_id: str, item: Mapping[str, Any], cost_id: str | None = None
    ) -> dict[str, Any]:
        if self.store.get_trip(trip_id) is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        payload = {
            "label": "",
            "category": "other",
            "original_amount": 0,
            "original_currency": costs.BASE_CURRENCY,
            "payment_state": "estimate",
            "actual_thb": None,
            "payer": "owner",
            "share": None,
            "related_item_id": None,
            "note": None,
            **dict(item),
        }
        clean = costs.validate_cost(payload)
        return self.store.upsert_cost_item(
            item_id=cost_id or clean.get("cost_id"),
            trip_id=trip_id,
            snapshot=freeze_snapshot(
                {k: v for k, v in clean.items() if k not in {"cost_id", "updated_at"}}
            ),
            now=datetime.now(timezone.utc).isoformat(),
        )

    def list_cost_items(self, trip_id: str) -> list[dict[str, Any]]:
        """Cost rows with their THB value resolved against the rate snapshot."""

        return costs.apply_rates(
            self.store.list_cost_items(trip_id), self.store.get_rate_snapshot(trip_id)
        )

    def delete_cost_item(self, *, trip_id: str, cost_id: str) -> None:
        self.store.delete_cost_item(trip_id, cost_id)

    def cost_totals(self, trip_id: str) -> dict[str, Any]:
        """Planned versus actual, read across both ledgers per artifact 023."""

        return costs.totals(
            self.list_cost_items(trip_id),
            self.list_split_rows(trip_id),
            len(self._roster(trip_id)),
        )

    # ponytail: the owner is the cardholder. Auto-Bill made it selectable, but
    # this app is owner-led and single-card, and every line of artifact 031's
    # wording says "you" -- store a setting only if that stops being true.
    CARDHOLDER = "owner"

    def _roster(self, trip_id: str) -> tuple[str, ...]:
        """Traveller ids a split row may name: the owner plus recorded members."""

        setup = self.store.get_setup(trip_id)
        if setup is None:
            return (self.CARDHOLDER,)
        return (
            self.CARDHOLDER,
            *(
                str(member["traveller_id"])
                for member in setup.snapshot.as_dict().get("travellers", ())
            ),
        )

    def save_split_row(
        self, *, trip_id: str, row: Mapping[str, Any], split_id: str | None = None
    ) -> dict[str, Any]:
        """Record or correct one bill that was actually paid."""

        if self.store.get_trip(trip_id) is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        roster = self._roster(trip_id)
        payload = {
            "label": "",
            "mode": "equal_all",
            "paid_by": self.CARDHOLDER,
            "participants": list(roster),
            "tag": split.DEFAULT_CATEGORY,
            "original_amount": 0,
            "original_currency": costs.BASE_CURRENCY,
            "actual_thb": None,
            "cost_id": None,
            "plan_day": None,
            "place_id": None,
            "voided": False,
            **dict(row),
        }
        clean = split.validate_row(payload, roster)
        return self.store.upsert_split_row(
            row_id=split_id or clean.get("split_id"),
            trip_id=trip_id,
            snapshot=freeze_snapshot(
                {k: v for k, v in clean.items() if k not in {"split_id", "updated_at"}}
            ),
            now=datetime.now(timezone.utc).isoformat(),
        )

    def list_split_rows(self, trip_id: str) -> list[dict[str, Any]]:
        """Split rows in THB, resolved without the estimate buffer."""

        return split.apply_rates(
            self.store.list_split_rows(trip_id), self.store.get_rate_snapshot(trip_id)
        )

    def set_split_voided(
        self, *, trip_id: str, split_id: str, voided: bool = True
    ) -> dict[str, Any]:
        """Remove a row by voiding it, so a total that moved stays explainable."""

        stored = {row["split_id"]: row for row in self.store.list_split_rows(trip_id)}
        row = stored.get(split_id)
        if row is None:
            raise PlannerRefusal("unknown_split_row", split_id=split_id)
        return self.save_split_row(
            trip_id=trip_id,
            split_id=split_id,
            row={
                **{k: v for k, v in row.items() if k not in {"split_id", "updated_at"}},
                "voided": bool(voided),
            },
        )

    def split_summary(self, trip_id: str) -> dict[str, Any]:
        """Actual group spend, per-traveller balances, and the star settlement."""

        return split.summary(
            self.list_split_rows(trip_id),
            travellers=self._roster(trip_id),
            cardholder=self.CARDHOLDER,
            settled=self.store.list_settled_markers(trip_id),
        )

    def set_split_settled(
        self, *, trip_id: str, traveller_id: str, settled: bool = True
    ) -> dict[str, Any]:
        """Mark a balance settled, or drop the marker.

        The marker records the balance the owner called settled, not a payment,
        so any later change to that balance silently supersedes it.
        """

        if traveller_id not in self._roster(trip_id):
            raise PlannerRefusal("unknown_traveller", traveller_id=traveller_id)
        if not settled:
            self.store.clear_settled_marker(trip_id, traveller_id)
            return self.split_summary(trip_id)
        current = next(
            (
                entry
                for entry in self.split_summary(trip_id)["balances"]
                if entry["traveller_id"] == traveller_id
            ),
            {},
        )
        self.store.save_settled_marker(
            trip_id=trip_id,
            traveller_id=traveller_id,
            net_thb=float(current.get("net_thb") or 0.0),
            now=datetime.now(timezone.utc).isoformat(),
        )
        return self.split_summary(trip_id)

    def quick_actions(self, trip_id: str) -> list[dict[str, Any]]:
        """Actions offered for the active plan. None of them needs a model."""

        active = self.store.get_active_plan(trip_id)
        if active is None:
            return []
        variant = active.snapshot.as_dict().get("variant") or {}
        planner_input = active.snapshot.as_dict().get("optimizer_input") or {}
        scheduled = [
            item["subject_id"]
            for day in variant.get("days", [])
            for item in day.get("items", [])
            if item.get("type") == "visit"
        ]
        locked = {
            str(lock.get("subject_id")) for lock in planner_input.get("locks", [])
        }
        offered: list[dict[str, Any]] = [
            {"operation": "explain", "arguments": {}},
            {"operation": "fully_reoptimize", "arguments": {}},
        ]
        metrics = variant.get("metrics") or {}
        if metrics.get("walking_minutes"):
            offered.append({"operation": "reduce_walking", "arguments": {"factor": 0.7}})
        if metrics.get("scheduled_visits", 0) > 1:
            offered.append(
                {"operation": "reduce_daily_load", "arguments": {"factor": 0.7}}
            )
        if not (planner_input.get("thresholds") or {}).get("meal_window"):
            offered.append(
                {
                    "operation": "fix_meal_timing",
                    "arguments": {"start": "12:00", "end": "13:30"},
                }
            )
        for place_id in scheduled:
            if place_id in locked:
                offered.append(
                    {"operation": "unlock_item", "arguments": {"place_id": place_id}}
                )
            else:
                offered.append(
                    {"operation": "lock_item", "arguments": {"place_id": place_id}}
                )
        return offered

    def propose_revision(
        self,
        *,
        trip_id: str,
        operation: Mapping[str, Any],
        request_text: str = "",
        replace_pending: bool = False,
        interpreted_by: str = "quick_action",
        interpretation: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the one pending preview. The active plan is never touched here."""

        active = self.store.get_active_plan(trip_id)
        if active is None:
            raise PlannerRefusal("no_active_plan")
        pending = self.store.get_revision_draft(trip_id)
        if pending and not replace_pending and pending["operation"] != str(
            operation.get("operation")
        ):
            raise PlannerRefusal(
                "revision_already_pending", pending_operation=pending["operation"]
            )

        stored = active.snapshot.as_dict()
        base_input = stored["optimizer_input"]
        before_variant = stored["variant"]
        applied = revision.apply_operation(base_input, dict(operation))
        clean = revision.validate_operation(dict(operation))
        # Model-supplied defaults are shown beside the operation's own assumptions.
        applied["assumptions"] = list(
            (interpretation or {}).get("assumed_defaults") or []
        ) + applied["assumptions"]

        if not clean["changes_plan"]:
            draft = {
                "schema_version": revision.SCHEMA_VERSION,
                "operation": clean["operation"],
                "arguments": clean["arguments"],
                "request_text": str(request_text or ""),
                "assumptions": applied["assumptions"],
                "explanation": self._explain_plan(stored),
                "consequences": None,
                "proposal": None,
                "can_apply": False,
                "interpreted_by": interpreted_by,
                "interpretation": dict(interpretation or {}),
            }
            return self.store.save_revision_draft(
                trip_id=trip_id,
                base_version_id=active.version_id,
                draft=draft,
                now=datetime.now(timezone.utc).isoformat(),
            )

        proposal = optimize_trip(applied["snapshot"])
        after_variant = next(
            (
                item
                for item in proposal["variants"]
                if item["variant_id"] == before_variant["variant_id"]
            ),
            proposal["variants"][0] if proposal["variants"] else None,
        )
        if after_variant is None:
            raise PlannerRefusal("revision_no_variant")
        change = revision.consequences(before_variant, after_variant)
        draft = {
            "schema_version": revision.SCHEMA_VERSION,
            "operation": clean["operation"],
            "arguments": clean["arguments"],
            "request_text": str(request_text or ""),
            "assumptions": applied["assumptions"],
            "explanation": None,
            "consequences": change,
            "proposal": {
                "optimizer_version": proposal["optimizer_version"],
                "input_sha256": proposal["input_sha256"],
                "optimizer_input": applied["snapshot"],
                "variant": after_variant,
            },
            "can_apply": change["can_apply"],
            "interpreted_by": interpreted_by,
            "interpretation": dict(interpretation or {}),
        }
        return self.store.save_revision_draft(
            trip_id=trip_id,
            base_version_id=active.version_id,
            draft=draft,
            now=datetime.now(timezone.utc).isoformat(),
        )

    def interpret_revision(
        self,
        *,
        trip_id: str,
        request_text: str,
        language: str = "en",
        replace_pending: bool = False,
    ) -> dict[str, Any]:
        """One model call turns free text into a typed operation, then previews it.

        Every failure path leaves the active plan and the revision history
        untouched, and names why interpretation was unavailable.
        """

        active = self.store.get_active_plan(trip_id)
        if active is None:
            raise PlannerRefusal("no_active_plan")
        payload = interpret.build_payload(
            plan=active.snapshot.as_dict(),
            request_text=request_text,
            language=language,
        )
        provider = self.interpreter or OpenAIRevisionInterpreter()
        decision = self.check_paid_call(operation=provider.operation, count=1)
        if not decision["allowed"]:
            raise ProviderBudgetExceeded(decision["reason"])

        try:
            result = provider.interpret(payload)
        except RevisionInterpretationUnavailable as error:
            # Record the attempt so the ledger reconciles, then report the cause.
            self.record_paid_call(
                operation=provider.operation,
                count=1,
                trip_id=trip_id,
                outcome="error",
                detail={"cause": error.cause},
            )
            raise
        self.record_paid_call(
            operation=provider.operation,
            count=1,
            trip_id=trip_id,
            detail={"model": str(result.get("model") or "")},
        )

        try:
            typed = interpret.interpret_response(result["response"], payload=payload)
        except ValueError as error:
            raise RevisionInterpretationUnavailable(
                str(error), cause="invalid_reply"
            ) from None

        if not typed["supported"]:
            return {
                "supported": False,
                "operation": None,
                "clarification": typed["clarification"],
                "unsupported_reason": typed["unsupported_reason"],
                "model": result.get("model"),
                "draft": None,
            }
        draft = self.propose_revision(
            trip_id=trip_id,
            operation={
                "operation": typed["operation"],
                "arguments": typed["arguments"],
            },
            request_text=request_text,
            replace_pending=replace_pending,
            interpreted_by="ai",
            interpretation={
                "model": result.get("model"),
                "intent_schema_version": result.get("schema_version"),
                "clarification": typed["clarification"],
                "assumed_defaults": typed.get("assumptions") or [],
            },
        )
        return {
            "supported": True,
            "operation": typed["operation"],
            "clarification": typed["clarification"],
            "unsupported_reason": None,
            "model": result.get("model"),
            "draft": draft,
        }

    def get_revision_draft(self, trip_id: str) -> dict[str, Any] | None:
        return self.store.get_revision_draft(trip_id)

    def discard_revision_draft(self, trip_id: str) -> None:
        self.store.delete_revision_draft(trip_id)

    def apply_revision(self, trip_id: str) -> PlanVersion:
        """Apply the pending preview as a new immutable version, with history."""

        draft = self.store.get_revision_draft(trip_id)
        if draft is None:
            raise PlannerRefusal("no_pending_revision")
        if not draft.get("can_apply") or not draft.get("proposal"):
            raise PlannerRefusal("revision_not_applicable")
        active = self.store.get_active_plan(trip_id)
        if active is None or active.version_id != draft["base_version_id"]:
            raise PlannerRefusal(
                "revision_base_moved",
                base_version_id=draft["base_version_id"],
                active_version_id=active.version_id if active else None,
            )
        proposal = draft["proposal"]
        version = self.save_plan_version(
            trip_id=trip_id,
            snapshot={
                "schema_version": 1,
                "optimizer_version": proposal["optimizer_version"],
                "input_sha256": proposal["input_sha256"],
                "optimizer_input": proposal["optimizer_input"],
                "variant": proposal["variant"],
            },
            cause=f"revision:{draft['operation']}",
        )
        self.store.add_plan_revision(
            trip_id=trip_id,
            record={
                "schema_version": revision.SCHEMA_VERSION,
                "operation": draft["operation"],
                "arguments": draft["arguments"],
                "request_text": draft.get("request_text") or "",
                "assumptions": draft.get("assumptions") or [],
                "consequences": draft["consequences"],
                "from_version_id": draft["base_version_id"],
                "to_version_id": version.version_id,
                "interpreted_by": draft.get("interpreted_by") or "quick_action",
                "interpretation": draft.get("interpretation") or {},
            },
            now=datetime.now(timezone.utc).isoformat(),
        )
        self.store.delete_revision_draft(trip_id)
        return version

    def list_revisions(self, trip_id: str) -> list[dict[str, Any]]:
        return self.store.list_plan_revisions(trip_id)

    def _explain_plan(self, stored: dict[str, Any]) -> dict[str, Any]:
        """Deterministic reasons for the active plan. No model involved."""

        variant = stored["variant"]
        planner_input = stored["optimizer_input"]
        return {
            "variant_id": variant["variant_id"],
            "status": variant["status"],
            "metrics": variant.get("metrics", {}),
            "warnings": sorted(set(variant.get("warnings", []))),
            "objective": variant.get("objective", {}),
            "beats_greedy_baseline": bool(
                variant.get("objective_improved_or_equal_to_greedy")
            ),
            "thresholds": planner_input.get("thresholds", {}),
            "locks": [
                str(lock.get("subject_id")) for lock in planner_input.get("locks", [])
            ],
            "unscheduled": [
                {
                    "place_id": item["place_id"],
                    "reason": item["reason"],
                    "consequence": item["consequence"],
                }
                for item in variant.get("reconciliation", [])
                if item["status"] == "cannot_currently_fit"
            ],
        }

    def build_export_snapshot(
        self, trip_id: str, *, version_id: str | None = None, language: str | None = None
    ) -> FrozenSnapshot:
        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        active = self.store.get_active_plan(trip_id)
        version = (
            self.store.get_plan_version(version_id) if version_id else active
        )
        if version is None or version.trip_id != trip_id:
            raise PlannerRefusal("no_active_plan")
        return freeze_snapshot(
            exports.build_export_snapshot(
                trip={
                    "trip_id": trip.trip_id,
                    "name": trip.name,
                    "destination": trip.destination,
                },
                plan=version.snapshot.as_dict(),
                version_id=version.version_id,
                active_version_id=active.version_id if active else None,
                language=language or trip.language,
                exported_at=datetime.now(timezone.utc).isoformat(),
                checklist_items=self.list_checklist_items(trip_id),
                checklist_readiness=self.checklist_readiness(trip_id),
                cost_items=self.list_cost_items(trip_id),
                cost_totals=self.cost_totals(trip_id),
                rate_snapshot=self.store.get_rate_snapshot(trip_id),
            )
        )

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
