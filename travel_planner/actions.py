"""Application actions coordinating the domain core and SQLite adapter."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
import os
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
from . import areas, checklist, climate, costs, destinations, exports, interpret, opening, revision, split, usage
from . import setup as setup_module
from .discovery import build_candidate_catalog
from .optimizer import (
    COMFORT_RULES,
    DEPARTURE_LOGISTICS_MINUTES,
    date_range,
    optimize_trip,
    validate_variant,
)
from .providers import (
    CARD_PHOTO_LIMIT,
    GooglePlacesCardProvider,
    GooglePlacesOpeningHoursProvider,
    OpenAIOpeningWindowProvider,
    OpenAIRevisionInterpreter,
    OpenMeteoClimateProvider,
    RevisionInterpretationUnavailable,
    GoogleTimeZoneProvider,
    GtfsTransitProvider,
    OpenRouteServiceProvider,
    OsmAreaAmenitiesProvider,
    OsmMetroProvider,
    VenueNoticeProvider,
    WikidataSummaryProvider,
    OpenStreetMapProvider,
    ProviderBudgetExceeded,
    ProviderUnavailable,
)
from .ranking import build_ranking, validate_choice, _distance_metres
from .setup import build_setup_payload
from .store import SQLiteStore
from .transit import MAX_ACCESS_METRES, WALK_METRES_PER_MINUTE, metres as transit_metres


def _shift_clock(value: str, minutes: int) -> str:
    """Move an `HH:MM` local time, clamped to the same day at both ends."""

    hour, minute = value.split(":", 1)
    moved = min(24 * 60 - 1, max(0, int(hour) * 60 + int(minute) + minutes))
    return f"{moved // 60:02d}:{moved % 60:02d}"


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
        transit_provider: Any = None,
        area_amenities_provider: Any = None,
        opening_window_provider: Any = None,
        venue_notice_provider: Any = None,
        summary_provider: Any = None,
        climate_provider: Any = None,
        timezone_provider: Any = None,
        hours_provider: Any = None,
        card_provider: Any = None,
        interpreter: Any = None,
    ) -> None:
        self.store = SQLiteStore(database_path)
        self.place_provider = place_provider
        self.route_provider = route_provider
        # Injected the same way every other provider is, so a test can hand over a
        # small feed instead of reaching for a city-sized one.
        self.transit_provider = transit_provider
        self.area_amenities_provider = area_amenities_provider
        self.opening_window_provider = opening_window_provider
        self.venue_notice_provider = venue_notice_provider
        self.summary_provider = summary_provider
        self.climate_provider = climate_provider
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

        # A catalog missing one of its two query blocks is usable but not complete, and
        # calling it `verified` would overstate it. Applied after the cache branches so
        # a partial payload served from cache is not laundered into `verified` on the
        # next read. `stale` is the existing word for "use it, and be told".
        coverage = payload.get("coverage") if isinstance(payload, Mapping) else None
        if status == "verified" and isinstance(coverage, Mapping) and coverage.get("incomplete_blocks"):
            status = "stale"

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

    def list_venue_notices(self, trip_id: str) -> dict[str, dict[str, Any]]:
        """Stored venue notices by place id. `WF-044`. A read, and free."""

        return {
            str(row["place_id"]): dict(row)
            for row in self.store.list_place_evidence(trip_id, "venue_notice")
            if row.get("place_id")
        }

    def scan_venue_notices(self, trip_id: str, *, force: bool = False) -> dict[str, Any]:
        """Read each chosen place's own site for a dated closure the weekly hours cannot
        carry. `WF-044`.

        An opening fact is a **weekly pattern**, so nothing the app stores can express
        "closed 1 January" — and the trip spans 31 December and 1 January. Google will not
        fill that gap; its snapshot is a weekday timetable.

        **What comes back is a quote and a link, never a fact.** It is stored under a kind
        `_optimizer_input` does not read, so a notice cannot remove a place, narrow a
        window or move a single minute. The optimizer has no code path to it. That is
        deliberate and load-bearing: `WF-046` measured a model inventing 2 of 7 weekly
        closures, and Sun Yat-sen Memorial Hall's own site carries a 休館公告 about a
        server-room migration affecting its **website**, which an extractor acting on
        would turn into a deleted landmark.

        So this produces something for a person to check, and the readiness board already
        asks them to.
        """

        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        provider = self.venue_notice_provider or VenueNoticeProvider()
        held = self.list_venue_notices(trip_id)
        now = datetime.now(timezone.utc)
        candidates = {
            item["place_id"]: item
            for item in self.get_latest_discovery(trip_id).candidates.as_dict()["candidates"]
        }

        checked = found = skipped = failed = 0
        errors: list[str] = []
        notices: list[dict[str, Any]] = []
        for place in self._selected_places(trip_id):
            website = (candidates.get(place["place_id"]) or {}).get("website")
            standing = held.get(place["place_id"])
            if not website:
                skipped += 1
                continue
            if not force and standing and str(standing.get("expires_at") or "") > now.isoformat():
                skipped += 1
                continue
            try:
                self._spend(
                    operation=str(provider.operation),
                    count=1,
                    trip_id=trip_id,
                    detail={"place_id": place["place_id"]},
                )
                answer = provider.notice(name=str(place["name"]), website=str(website))
            except ProviderBudgetExceeded:
                raise
            except ProviderUnavailable as error:
                failed += 1
                message = str(error)[:160]
                if message not in errors:
                    errors.append(message)
                continue
            checked += 1
            if not answer.get("found"):
                continue
            found += 1
            value = {
                "place_id": place["place_id"],
                "name": place["name"],
                "quote": answer["quote"],
                "summary": answer.get("summary"),
                "source_url": answer["source_url"],
                "model": answer.get("model"),
            }
            self.store.upsert_place_evidence(
                trip_id=trip_id,
                place_id=place["place_id"],
                kind=str(provider.kind),
                value=value,
                provider=str(provider.name),
                retrieved_at=now.isoformat(),
                expires_at=(now + timedelta(days=int(provider.cache_ttl_days))).isoformat(),
            )
            notices.append(value)
        return {
            "checked": checked,
            "notices_found": found,
            "without_website_or_held": skipped,
            "failed": failed,
            "provider_errors": errors,
            "notices": notices,
        }

    def active_plan_drift(self, trip_id: str) -> dict[str, Any]:
        """Has the evidence under the activated plan moved, and did anything break?

        `WF-045`. Every existing gate guards the **forward** direction — activation
        refuses on a stale preview, discovery and ranking refuse on a stale setup hash.
        Nothing looked backwards, so buying one opening-hours lookup left a visit
        scheduled 17:17–19:32 against real hours ending 17:30 while the stored variant
        still reported `validation.valid: true`. That flag was computed when the plan was
        built and nothing recomputes it.

        Two steps, in that order, because each answers a different question cheaply:

        1. **Has anything moved?** The activated version stores its own `optimizer_input`,
           so re-freezing it and comparing hashes is the same check `activate_plan_preview`
           already makes, run the other way round. No optimizer work.
        2. **Did it matter?** Only when the hash moved, re-run `validate_variant` against
           today's snapshot. That distinguishes "the evidence moved and the plan still
           holds" from "these visits no longer work" — which is what stops this reporting
           churn for every hash change with no scheduling consequence.

        It reports and never repairs. Regenerating would rewrite a plan the owner may have
        printed or shared, so the offer belongs on the screen, not in this method.
        """

        active = self.get_active_plan(trip_id)
        if active is None:
            raise PlannerRefusal("no_active_plan")
        stored = active.snapshot.as_dict()
        stored_input = stored.get("optimizer_input") or {}
        variant = stored.get("variant") or {}
        current = self._optimizer_input(trip_id)
        stored_hash = freeze_snapshot(stored_input).sha256
        current_hash = freeze_snapshot(current).sha256

        moved = stored_hash != current_hash
        violations: list[dict[str, Any]] = []
        still_valid = True
        if moved:
            validation = validate_variant(current, variant)
            still_valid = bool(validation["valid"])
            violations = list(validation["hard_violations"])
        return {
            "version_id": active.version_id,
            "moved": moved,
            # What the plan claimed when it was built. Reported beside `still_valid` so
            # the two can be seen to disagree rather than one quietly overwriting it.
            "claimed_valid": bool((variant.get("validation") or {}).get("valid")),
            "still_valid": still_valid,
            "violations": violations,
            "stored_input_sha256": stored_hash,
            "current_input_sha256": current_hash,
        }

    def opening_evidence_options(self, trip_id: str) -> dict[str, Any]:
        """What hours for this trip would cost each way, and what the cheap way gives up.

        `WF-047`. The owner asked for a rule that switches to the model when Google gets
        expensive. This reports the trade instead of taking it, for a reason that is not
        squeamishness: the two are **not the same kind of thing**. Google returns
        `status: "verified"`; the model returns `status: "assumed"`, which a
        `ready_to_schedule` trip does not read at all, so switching there would spend money
        on a fact the optimizer ignores.

        There is no cheaper verified path to offer. `google_places:search_text` takes one
        query per place and cannot be batched, and the cheaper `places/{id}` Details
        endpoint needs a Google place id the catalogue does not hold — getting one costs
        the same search. So US$0.025 a place is the floor for evidence.

        What *has* changed is the other side: batching made the assumption cost one
        request for the whole trip rather than one per place. The comparison is therefore
        no longer about money at all, which is the honest way to put a choice between
        evidence and a guess.
        """

        snapshot = self._optimizer_input(trip_id)
        verified = {
            fact["subject_id"]
            for fact in snapshot["facts"]
            if fact.get("fact_type") == "opening_interval"
            and fact.get("status") == "verified"
        }
        held = self.list_assumed_windows(trip_id)
        places = self._selected_places(trip_id)
        needing = [p["place_id"] for p in places if p["place_id"] not in verified]
        hours_price = usage.PRICES_USD["google_places:search_text"]
        window_price = usage.PRICES_USD["openai:opening_window"]
        batch_size = int(getattr(OpenAIOpeningWindowProvider, "BATCH_SIZE", 20))
        calls = -(-len(needing) // batch_size) if needing else 0
        return {
            "places": len(places),
            "with_verified_hours": len(verified),
            "needing_hours": len(needing),
            "already_assumed": sum(1 for pid in needing if pid in held),
            "verified": {
                "operation": "google_places:search_text",
                "calls": len(needing),
                "estimate_usd": round(hours_price * len(needing), 6),
                "status": "verified",
                "batchable": False,
            },
            "assumed": {
                "operation": "openai:opening_window",
                "calls": calls,
                "estimate_usd": round(window_price * calls, 6),
                "status": "assumed",
                "batchable": True,
                # Measured 2026-08-07 against verified hours for all 13 pilot places, in
                # one batched call. Reported so the cheaper option is never chosen without
                # its error rate in view.
                "measured": {
                    "places": 11,
                    "of": 13,
                    "exact_both_ends": 8,
                    "ends_after_real_closing": 1,
                    "worst_overshoot_minutes": 30,
                },
            },
            # A trip that will not read an assumed fact should not be offered one.
            "assumed_is_usable": bool(
                snapshot["trip"].get("allow_provisional_assumptions")
            ),
        }

    def list_assumed_windows(self, trip_id: str) -> dict[str, dict[str, Any]]:
        """Stored model-recalled windows by place id. `WF-046`. Never fetches."""

        # `list_place_evidence` spreads the stored value flat and adds `retrieved_at` and
        # `expires_at`; there is no `value` key to unwrap. Expiry is deliberately not
        # filtered here — an assumption does not go stale the way a lookup does, and
        # dropping it would silently revert the fact to the flat constant. `refresh`
        # honours the TTL instead.
        return {
            str(row["place_id"]): dict(row)
            for row in self.store.list_place_evidence(trip_id, "assumed_opening_window")
            if row.get("place_id") and row.get("start") and row.get("end")
        }

    def refresh_assumed_windows(
        self, trip_id: str, *, force: bool = False
    ) -> dict[str, Any]:
        """Ask the model for an opening window for places that have no verified hours.

        `WF-046`. Owner-triggered and paid, like every other provider refresh, and scoped
        to the places that would otherwise fall back to a flat 09:00-21:00. A place with
        verified hours is **skipped** — there is nothing an assumption can add to
        evidence, and asking would invite someone to compare them as equals.

        Refuses on a `ready_to_schedule` trip: an assumed window is only ever consumed
        under `allow_provisional_assumptions`, so buying one there would spend money on a
        fact the optimizer will not read.
        """

        setup = self.store.get_setup(trip_id)
        if setup is None:
            raise PlannerRefusal("setup_missing")
        snapshot = self._optimizer_input(trip_id)
        if not snapshot["trip"].get("allow_provisional_assumptions"):
            raise PlannerRefusal("assumptions_not_used_by_this_trip")

        verified = {
            fact["subject_id"]
            for fact in snapshot["facts"]
            if fact.get("fact_type") == "opening_interval"
            and fact.get("status") == "verified"
        }
        provider = self.opening_window_provider or OpenAIOpeningWindowProvider()
        held = self.list_assumed_windows(trip_id)
        trip = self.store.get_trip(trip_id)
        destination = str(trip.destination) if trip else ""
        now = datetime.now(timezone.utc)

        wanted: list[dict[str, Any]] = []
        skipped = 0
        for place in self._selected_places(trip_id):
            standing = held.get(place["place_id"])
            if place["place_id"] in verified or (
                not force
                and standing
                and str(standing.get("expires_at") or "") > now.isoformat()
            ):
                skipped += 1
                continue
            wanted.append(place)

        asked = stored = unknown = failed = 0
        errors: list[str] = []
        size = int(getattr(provider, "BATCH_SIZE", 20))
        # `WF-047`. One request per chunk, not per place. Verified hours cost US$0.025
        # each and cannot be batched -- Google's Text Search takes one query per place --
        # so a 40-place trip is US$1.00. Batching the assumption makes the alternative a
        # rounding error, which leaves the *evidential* difference as the only thing to
        # weigh rather than the price.
        #
        # It also measured **more** accurate than asking one at a time: 8 of 11 exact on
        # both ends against 6 of 12, and one overshoot of real closing against four.
        for offset in range(0, len(wanted), size):
            chunk = wanted[offset : offset + size]
            try:
                self._spend(
                    operation=str(provider.operation),
                    count=1,
                    trip_id=trip_id,
                    detail={"places": len(chunk), "batched": True},
                )
                answers = provider.windows(
                    [
                        {
                            "name": str(place["name"]),
                            "local_name": str((place.get("names") or {}).get("local") or ""),
                        }
                        for place in chunk
                    ],
                    destination=destination,
                )
            except ProviderBudgetExceeded:
                raise
            except ProviderUnavailable as error:
                failed += len(chunk)
                message = str(error)[:160]
                if message not in errors:
                    errors.append(message)
                continue
            asked += len(chunk)
            for index, place in enumerate(chunk):
                answer = answers.get(index)
                if not answer:
                    # No entry, an unusable pair, or a window so wide it says nothing.
                    # The constant stands and nothing pretends to know more.
                    unknown += 1
                    continue
                self.store.upsert_place_evidence(
                    trip_id=trip_id,
                    place_id=place["place_id"],
                    kind=str(provider.kind),
                    value={
                        "place_id": place["place_id"],
                        "start": answer["start"],
                        "end": answer["end"],
                        "model": answer.get("model"),
                        "asked": f"{place['name']} in {destination}",
                    },
                    provider=str(provider.name),
                    retrieved_at=now.isoformat(),
                    expires_at=(
                        now + timedelta(days=int(provider.cache_ttl_days))
                    ).isoformat(),
                )
                stored += 1
        return {
            "asked": asked,
            "stored": stored,
            "model_declined": unknown,
            "skipped_verified_or_held": skipped,
            "model_calls": (len(range(0, 0)) if False else None),
            "failed": failed,
            "provider_errors": errors,
        }

    def comfort_tradeoffs(self, trip_id: str) -> dict[str, Any]:
        """What the current plan exceeds, what is agreed, and by how much. `WF-039`.

        One read for the screen, so it never has to know which metric belongs to which
        threshold — `optimizer.COMFORT_RULES` is the single source and this walks it.
        """

        snapshot = self._optimizer_input(trip_id)
        thresholds = snapshot["thresholds"]
        accepted = {item["code"]: item for item in snapshot["comfort_acceptances"]}
        active = self.get_active_plan(trip_id)
        variant = (
            active.snapshot.as_dict().get("variant", {}) if active is not None else {}
        )
        preview = self.get_plan_preview(trip_id)
        if not variant and preview is not None:
            variants = preview.proposal.as_dict().get("variants", [])
            variant = variants[0] if variants else {}
        metrics = variant.get("metrics", {})

        rules = []
        for rule in COMFORT_RULES:
            cap = thresholds.get(rule["threshold"])
            if cap is None:
                # No cap set for this budget, so there is nothing to accept. Reported
                # anyway: an owner who set no walking preference should see that, not
                # silently get no control.
                rules.append(
                    {"code": rule["reason"], "threshold": None, "measured": None,
                     "exceeds": False, "accepted_value": None, "covered": False}
                )
                continue
            measured = metrics.get(rule["metric"])
            if measured is None:
                measured = metrics.get(rule["fallback_metric"])
            agreed = accepted.get(rule["reason"])
            rules.append(
                {
                    "code": rule["reason"],
                    "threshold": int(cap),
                    "measured": None if measured is None else round(float(measured)),
                    "exceeds": measured is not None and float(measured) > int(cap),
                    "accepted_value": (
                        None if agreed is None else round(float(agreed["accepted_value"]))
                    ),
                    "covered": (
                        agreed is not None
                        and measured is not None
                        and float(measured) <= float(agreed["accepted_value"])
                    ),
                }
            )
        return {"rules": rules, "has_plan": bool(metrics)}

    def accept_comfort_tradeoff(
        self, trip_id: str, code: str, value: float
    ) -> dict[str, Any]:
        """Agree to exceed one comfort budget, up to `value`. `WF-039`.

        The value is required rather than inferred from the current plan, because an
        acceptance recorded as "yes" would go on applying to whatever the next replan
        produces. Recording the number the owner saw is what keeps consent attached to
        the thing consented to.
        """

        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        known = {rule["reason"] for rule in COMFORT_RULES}
        if code not in known:
            raise PlannerRefusal("unknown_comfort_code", comfort_code=code)
        try:
            accepted = float(value)
        except (TypeError, ValueError):
            raise PlannerRefusal("comfort_value_not_a_number", comfort_code=code) from None
        if accepted <= 0:
            raise PlannerRefusal("comfort_value_not_a_number", comfort_code=code)
        rule = next(item for item in COMFORT_RULES if item["reason"] == code)
        threshold = self._optimizer_input(trip_id)["thresholds"].get(rule["threshold"])
        if threshold is None:
            raise PlannerRefusal("no_comfort_threshold_set", comfort_code=code)
        if accepted <= float(threshold):
            # Nothing to accept: the plan is already inside the budget, and storing an
            # acceptance would leave a permission lying around for a later plan to use.
            raise PlannerRefusal(
                "comfort_value_within_threshold",
                comfort_code=code,
                threshold=int(threshold),
            )
        self.store.save_comfort_acceptance(
            trip_id=trip_id,
            code=code,
            accepted_value=accepted,
            threshold_value=float(threshold),
            now=datetime.now(timezone.utc).isoformat(),
        )
        return {"code": code, "accepted_value": accepted, "threshold_value": threshold}

    def withdraw_comfort_tradeoff(self, trip_id: str, code: str) -> dict[str, Any]:
        self.store.clear_comfort_acceptance(trip_id, code)
        return {"code": code, "withdrawn": True}

    def list_comfort_acceptances(self, trip_id: str) -> list[dict[str, Any]]:
        return self.store.list_comfort_acceptances(trip_id)

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
                # `WF-042`. The departure day owes fixed logistics before the flight
                # and they are not sightseeing, so the window has to open early
                # enough to hold them. It used to keep the 08:00 leisure start, which
                # for any flight before ~11:00 made the day infeasible -- and because
                # the optimizer accepts a placement only when every day builds clean,
                # that emptied the whole plan. Clamped at midnight: a pre-dawn flight
                # would owe the previous day, which is not modelled.
                start = min(start, _shift_clock(end, -DEPARTURE_LOGISTICS_MINUTES))
            if start >= end:
                raise PlannerRefusal("no_planning_time", local_date=local_date)
            usable_windows.append({"date": local_date, "start": start, "end": end})

        candidates = []
        facts = []
        opening_missing = False
        opening_evidence = self.opening_intervals(trip_id)
        assumed_windows = self.list_assumed_windows(trip_id)
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
                        # `WF-041`. The dates this window is actually good for, which
                        # excludes any the place is shut. It was every trip date, and
                        # the optimizer read it as nothing at all -- the field existed
                        # and no code consumed it, so a place closed on one day was
                        # unschedulable on all of them.
                        "applies_to_dates": provider_hours.get("open_dates") or local_dates,
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
                    # `WF-046`. A model's recollection of *this* place when one has been
                    # fetched and stored, otherwise the flat constant. Both are
                    # `status: "assumed"` -- the point is a better guess, not a stronger
                    # claim -- and `source` says which, so the evidence screen can tell
                    # them apart and an owner can see where a window came from.
                    #
                    # Read from storage, never fetched here: `_optimizer_input` runs on
                    # every read and must not make a network call.
                    recalled = assumed_windows.get(choice.place_id)
                    facts.append(
                        {
                            "subject_id": choice.place_id,
                            "fact_type": "opening_interval",
                            "value": (
                                {"start": recalled["start"], "end": recalled["end"]}
                                if recalled
                                else {"start": "09:00", "end": "21:00"}
                            ),
                            "status": "assumed",
                            "source": (
                                f"model_recalled_window:{recalled['model']}"
                                if recalled
                                else "explore_first_planning_assumption"
                            ),
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
        # `verified` always; `estimated` only for an Explore preview, which is the
        # same rule `optimizer._planning_fact` already applies to opening hours --
        # "a visible assumption allowed only for an Explore preview". A transit leg
        # is `estimated` by construction, derived from a timetable or from topology
        # rather than looked up, so without this the 162 metro routes `WF-038`
        # fetches never reach the optimizer and the whole ticket buys nothing.
        # A `ready_to_schedule` trip is unaffected and still demands verification.
        usable_route_statuses = (
            {"verified", "estimated"} if allow_provisional_assumptions else {"verified"}
        )
        routes = [
            route
            for route in self.list_routes(trip_id)
            if route.get("status") in usable_route_statuses
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
            # `WF-039`. Each carries the measurement it was agreed at, so the optimizer
            # can tell an accepted overage from a worse one that merely shares its code.
            "comfort_acceptances": self.store.list_comfort_acceptances(trip_id),
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
                # `list_place_evidence` returns the stored value and does not add the
                # id back, so it has to live inside -- the same convention the opening
                # hours evidence follows.
                value={**value, "place_id": place["place_id"]},
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
                    # Carried so `refresh_place_summaries` can find the Wikidata id.
                    # Without it that method skipped every place and reported success.
                    "signals": candidate.get("signals") or {},
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

    def travel_month_guide(self, trip_id: str, *, force: bool = False) -> dict[str, Any]:
        """Which months suit this destination, from measured weather and local holidays.

        Free on both sides and cached for `cache_ttl_days`: normals move over decades
        and holidays are published a year ahead, so this is one request pair per
        destination rather than one per visit.

        The coordinates come from the discovery run's own geocoded window, so this
        needs no new geocoder call and describes the box the places were found in.
        Without a discovery there is nothing to centre on, and it refuses rather than
        guessing a city from its name.
        """

        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        discovery = self.get_latest_discovery(trip_id)
        # `query_boundary` is the clamped window discovery actually searched, stored as
        # (south, west, north, east). Its centre is the city as this trip found it, so
        # the weather described is the weather over the places on the shortlist.
        box = (discovery.report.as_dict() if discovery else {}).get("query_boundary")
        if not (isinstance(box, list) and len(box) == 4):
            raise PlannerRefusal("discovery_required_for_climate", trip_id=trip_id)
        latitude = (float(box[0]) + float(box[2])) / 2
        longitude = (float(box[1]) + float(box[3])) / 2

        provider = self.climate_provider or OpenMeteoClimateProvider()
        now = datetime.now(timezone.utc)
        held = self.store.get_trip_evidence(trip_id, provider.kind)
        if not force and held and held.get("expires_at", "") > now.isoformat():
            return dict(held["value"])

        year = now.year - 1  # the last whole year the archive certainly holds
        self._spend(
            operation=provider.operation,
            count=1,
            trip_id=trip_id,
            detail={"latitude": round(latitude, 3), "longitude": round(longitude, 3)},
        )
        archive = provider.daily_archive(latitude, longitude, end_year=year)
        months = climate.monthly_normals(archive["daily"])

        country = (trip.destination.split(",")[-1]).strip()
        self._spend(
            operation=provider.holiday_operation, count=1, trip_id=trip_id,
            detail={"country": country, "year": year + 1},
        )
        published = provider.holidays(country, year + 1)
        # Which source answered, so the screen can attribute it and a future gap is
        # traceable to the right place rather than to "holidays".
        holiday_source = (
            None
            if published is None
            else ("google.calendar" if country in provider.google_calendars else "nager.date")
        )
        grouped = climate.holiday_months(published) if published is not None else {}
        ranked = climate.rank_months(
            months,
            holidays=grouped,
            holiday_source=holiday_source,
        )
        value = {
            "months": ranked,
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "observed_from": archive["from"],
            "observed_to": archive["to"],
            "country": country,
            "holiday_year": year + 1,
            # Named so the screen can say the crowd factor is unknown rather than
            # letting an absent holiday list read as a quiet month.
            "holiday_source": holiday_source,
            "sources": [
                "Open-Meteo archive (CC BY 4.0)",
                "Nager.Date public holidays",
            ],
        }
        self.store.upsert_trip_evidence(
            trip_id=trip_id,
            kind=provider.kind,
            value=value,
            provider=str(provider.name),
            retrieved_at=now.isoformat(),
            expires_at=(now + timedelta(days=int(provider.cache_ttl_days))).isoformat(),
        )
        return value

    def refresh_place_summaries(
        self,
        trip_id: str,
        *,
        place_ids: Sequence[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Fetch a description and photo per selected place, in both languages.

        Free: Wikidata and Wikipedia, no key, priced at zero and recorded anyway so
        call counts stay reconcilable. Replaces what `google_places:card_details`
        charged US$0.04 a place for, with human-written prose in `en` and `th`.

        A place with no Wikidata id, or none with an article in either language, is
        left without a summary rather than given an invented one -- the screen shows
        the gap.
        """

        if self.store.get_trip(trip_id) is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        provider = self.summary_provider or WikidataSummaryProvider()
        now = datetime.now(timezone.utc)
        # Tolerant of a row written before the id was stored inside the value: a
        # legacy row simply refetches rather than raising.
        existing = {
            row["place_id"]: row
            for row in self.store.list_place_evidence(trip_id, provider.kind)
            if row.get("place_id")
        }
        # Named places come from the whole discovered catalogue, not the selection:
        # `/places` browses 832 candidates and the owner wants a description for the
        # card in front of them, which is usually one they have not chosen yet.
        if place_ids is None:
            wanted = self._selected_places(trip_id)
        else:
            discovery = self.get_latest_discovery(trip_id)
            catalogue = {
                item["place_id"]: item
                for item in (discovery.candidates.as_dict()["candidates"] if discovery else [])
            }
            wanted = [catalogue[pid] for pid in place_ids if pid in catalogue]

        fetched = cached = skipped = failed = 0
        errors: list[str] = []
        for place in wanted:
            qid = (place.get("signals") or {}).get("wikidata")
            held = existing.get(place["place_id"])
            # The stored value carries the provider version it was written under, so a
            # capability added later (Commons geosearch, v2) refetches each place once
            # rather than waiting out the 60-day TTL with an empty gallery.
            current_version = str(getattr(provider, "cache_version", ""))
            fresh_enough = (
                held
                and held["expires_at"] > now.isoformat()
                and str(held.get("cache_version") or "") == current_version
            )
            if not force and fresh_enough:
                cached += 1
                continue
            if not qid:
                # No Wikidata id, which is 61% of the Taipei catalogue. These used to be
                # skipped outright and so had no picture at all. Commons geosearch works
                # from the coordinates every candidate has, and answers "what is
                # photographed here" rather than "photographs of this place" -- stored
                # flagged as nearby so the screen says which it is showing.
                photos = self._nearby_photos(provider, place)
                if not photos:
                    skipped += 1
                    continue
                self._store_summary(
                    trip_id=trip_id,
                    place_id=place["place_id"],
                    provider=provider,
                    now=now,
                    value={
                        "cache_version": current_version,
                        "qid": None,
                        "names": {},
                        "text": {},
                        "image_url": photos[0],
                        "image_urls": photos,
                        "photos_are_nearby": True,
                        "licence": "CC BY-SA or compatible, Wikimedia Commons",
                        "source_urls": {},
                    },
                )
                fetched += 1
                continue
            try:
                self._spend(
                    operation=provider.operation,
                    count=1,
                    trip_id=trip_id,
                    detail={"place_id": place["place_id"], "qid": str(qid)},
                )
                value = provider.summary(str(qid))
            except ProviderBudgetExceeded:
                raise
            except ProviderUnavailable as error:
                failed += 1
                message = str(error)[:160]
                if message not in errors:
                    errors.append(message)
                continue
            # An article with no photograph is still a place with coordinates, so the
            # nearby fallback applies here too rather than only where the id is missing.
            if not value.get("image_urls") and not value.get("image_url"):
                photos = self._nearby_photos(provider, place)
                if photos:
                    value = {
                        **value,
                        "image_url": photos[0],
                        "image_urls": photos,
                        "photos_are_nearby": True,
                    }
            self._store_summary(
                trip_id=trip_id,
                place_id=place["place_id"],
                provider=provider,
                now=now,
                value={**value, "cache_version": current_version},
            )
            fetched += 1
        return {
            "places": len(wanted),
            "fetched": fetched,
            "from_cache": cached,
            "without_wikidata_id": skipped,
            "failed": failed,
            "provider_errors": errors,
        }

    @staticmethod
    def _nearby_photos(provider: Any, place: dict[str, Any]) -> list[str]:
        """Commons photographs near a place, or nothing. Free, and never fatal."""

        latitude, longitude = place.get("latitude"), place.get("longitude")
        finder = getattr(provider, "nearby_photos", None)
        if latitude is None or longitude is None or finder is None:
            return []
        try:
            return list(finder(float(latitude), float(longitude)))
        except (ProviderUnavailable, TypeError, ValueError):
            return []

    def _store_summary(
        self,
        *,
        trip_id: str,
        place_id: str,
        provider: Any,
        now: datetime,
        value: dict[str, Any],
    ) -> None:
        self.store.upsert_place_evidence(
            trip_id=trip_id,
            place_id=place_id,
            kind=provider.kind,
            # `list_place_evidence` returns the stored value and does not add the id
            # back, so it has to live inside -- the same convention the opening hours
            # evidence follows.
            value={**value, "place_id": place_id},
            provider=str(provider.name),
            retrieved_at=now.isoformat(),
            expires_at=(now + timedelta(days=int(provider.cache_ttl_days))).isoformat(),
        )

    def list_place_summaries(self, trip_id: str) -> dict[str, Any]:
        """Stored descriptions and photos, keyed by place id. A read, so free."""

        provider = self.summary_provider or WikidataSummaryProvider()
        return {
            row["place_id"]: row
            for row in self.store.list_place_evidence(trip_id, provider.kind)
            if row.get("place_id")
        }

    def refresh_routes(self, trip_id: str, *, force: bool = False) -> dict[str, Any]:
        """Fetch walking routes between the selected places, sparsely and capped."""

        return self._refresh_routes_with(
            self.route_provider or OpenRouteServiceProvider(), trip_id, force=force
        )

    def refresh_transit_routes(
        self, trip_id: str, *, force: bool = False
    ) -> dict[str, Any]:
        """Fetch transit legs from the local GTFS feed. `WF-038`.

        Stored *alongside* the walking routes rather than replacing them, because
        the store keys a snapshot by (origin, destination, **mode**) and the
        optimizer takes the shortest route it holds for a pair. So a short hop keeps
        its walk and a cross-city hop gains a ride, and neither decision is made
        here.
        """

        return self._refresh_routes_with(
            self.transit_provider or self._default_transit_provider(trip_id),
            trip_id,
            force=force,
        )

    def _default_transit_provider(self, trip_id: str) -> Any:
        """A real timetable when one is on disk, otherwise OSM metro topology.

        Preference, not equivalence. GTFS states ride times and lets headway be
        measured; OSM states only which stations a line joins, so its times come
        from an assumed speed and headway and its routes carry `basis: "nominal"`.
        Falling back is better than refusing — a nominal metro time is far closer to
        the truth than the walking route it replaces, which is what
        `artifacts/validation/2026-08-05-gate-1/` measured as a 45-minute walk
        between districts.
        """

        feed = Path(os.environ.get("TOURIST_GTFS_PATH", "data/gtfs/transit.zip"))
        if feed.is_file():
            return GtfsTransitProvider()
        trip = self.store.get_trip(trip_id)
        return OsmMetroProvider(destination=str(trip.destination) if trip else "")

    # How many areas survive the free travel-time ranking and go on to be counted. One
    # Overpass request whatever this is -- 12 areas is 36 statements.
    #
    # It was 8, and 8 put the cut inside a dead heat. Measured on the pilot: the top
    # twelve Taipei stations span 21.5 to 24.6 minutes per place, and 台北車站 sat ninth
    # at 23.46 against 西門's 23.14 -- **0.32 minutes** out. That matters because the
    # shortlist is a prefilter on travel time alone, which is 45 of the 100 points, so an
    # area cut here never has its food, nightlife or lodging counted at all. 台北車站 has
    # 586 places to eat and 90 listed beds and ranked third overall on the run that
    # happened to include it.
    #
    # 12 does not remove that: it moves the boundary somewhere less crowded. A cut on one
    # factor is a real limit of this design and `recommend_areas` reports the boundary so
    # it is visible rather than silent.
    AREA_SHORTLIST = 12

    def recommend_areas(self, trip_id: str) -> dict[str, Any]:
        """Rank transit-station neighbourhoods as places to stay. `WF-040`.

        Three stages, cheapest first, because the expensive one should only ever see a
        shortlist:

        1. Every station in the transit graph is a candidate, and its travel time to
           every selected place is computed locally from that graph. Free, no request.
        2. The best `AREA_SHORTLIST` by time per reachable place go forward.
        3. **One** Overpass request counts food, after-dark venues and listed lodging
           around those, and `areas.score_areas` combines the five factors.

        Refuses rather than guesses when there is no metro graph for the destination:
        an area ranking with no travel times is a list of amenity counts pretending to
        be advice.
        """

        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        places = self._selected_places(trip_id)
        if not places:
            raise PlannerRefusal("no_places_chosen", purpose="area_recommendation", minimum=1)

        provider = self.transit_provider or self._default_transit_provider(trip_id)
        build_graph = getattr(provider, "build_graph", None)
        if build_graph is None:
            raise PlannerRefusal("no_transit_graph_for_areas")
        try:
            graph = build_graph()
        except ProviderUnavailable as error:
            raise PlannerRefusal("no_transit_graph_for_areas", detail=str(error)[:160])

        # One area per **named station**, not per graph stop. `transit.STOP_TAGS`
        # deliberately admits `stop_position` and `platform` so subway relations stay
        # resolvable, which means Taipei's 437 stops are really 138 stations -- six
        # platform nodes for 板橋 alone. Without grouping, the shortlist filled with
        # near-duplicates of two stations and 373 Dijkstras ran instead of 138.
        #
        # A stop with no name is skipped rather than merged: an area the app cannot name
        # is useless as advice, because the owner cannot search a booking site for it.
        grouped: dict[str, list[Any]] = {}
        for stop in graph.stops.values():
            if stop.name == stop.stop_id:
                continue
            grouped.setdefault(stop.name, []).append(stop)

        candidates = []
        for name, stops in grouped.items():
            latitude = sum(stop.latitude for stop in stops) / len(stops)
            longitude = sum(stop.longitude for stop in stops) / len(stops)
            total = 0.0
            reachable = 0
            for place in places:
                # Best of riding and walking. `TransitGraph.journey` answers only once
                # something has been ridden -- by design, or a walk would arrive wearing
                # a journey's clothes -- so a station across the road from a place
                # returns None, and taking that as "unreachable" would score the *best*
                # possible area worst. Walking is also genuinely quicker for a short hop.
                options = []
                journey = graph.journey(
                    origin=(latitude, longitude),
                    destination=(place["latitude"], place["longitude"]),
                )
                if journey is not None:
                    options.append(float(journey.total_minutes))
                gap = transit_metres(
                    latitude, longitude, place["latitude"], place["longitude"]
                )
                if gap <= MAX_ACCESS_METRES:
                    options.append(max(1.0, gap / WALK_METRES_PER_MINUTE))
                if not options:
                    continue
                total += min(options)
                reachable += 1
            if not reachable:
                continue
            ids = {stop.stop_id for stop in stops}
            # `en` was the Chinese string here until 2026-08-07, because the graph threw
            # `name:en` away — so every area rendered as 中山 / 西門 with no way to read
            # it. OSM carries an English name for 370 of Taipei's 437 stop nodes.
            english = next((stop.name_en for stop in stops if stop.name_en), "")
            candidates.append(
                {
                    "area_id": min(ids),
                    "name": name,
                    "names": {"local": name, **({"en": english} if english else {})},
                    "latitude": latitude,
                    "longitude": longitude,
                    "total_travel_minutes": round(total),
                    "reachable_place_count": reachable,
                    # The area *is* the station, so access is the walk to its own
                    # entrance. Zero until a finer stop geometry says otherwise.
                    "access_walk_minutes": 0.0,
                    "line_count": len(
                        {
                            edge.route_id
                            for (origin, _), edge in graph.edges.items()
                            if origin in ids
                        }
                    ),
                }
            )
        if not candidates:
            raise PlannerRefusal("no_area_reaches_any_place")

        candidates.sort(
            key=lambda item: (
                item["total_travel_minutes"] / item["reachable_place_count"],
                -item["reachable_place_count"],
                item["area_id"],
            )
        )
        shortlist = candidates[: self.AREA_SHORTLIST]

        counts, counted = self._area_amenity_counts(trip_id, shortlist)
        for area in shortlist:
            area.update(counts.get(area["area_id"], {}))
        report = areas.score_areas(shortlist, place_count=len(places))
        report["amenities_counted"] = counted
        report["considered_area_count"] = len(candidates)
        # The travel time of the first area that missed the cut, so a reader can see how
        # close the boundary was. `None` when nothing was cut.
        report["excluded_next_best_minutes"] = (
            round(
                candidates[self.AREA_SHORTLIST]["total_travel_minutes"]
                / candidates[self.AREA_SHORTLIST]["reachable_place_count"]
            )
            if len(candidates) > self.AREA_SHORTLIST
            else None
        )
        return report

    def _area_amenity_counts(
        self, trip_id: str, shortlist: list[dict[str, Any]]
    ) -> tuple[dict[str, dict[str, int]], bool]:
        """Cached Overpass counts, or zeros and `False` when the endpoint will not say.

        Degrading is right here and refusing is not: travel time and metro access are
        already measured locally, so a ranking without the three inferred factors is
        weaker but still true. The caller reports `amenities_counted: false` so the
        screen can say which half it is looking at.
        """

        provider = self.area_amenities_provider or OsmAreaAmenitiesProvider()
        request = provider.cache_descriptor(shortlist)
        fingerprint = freeze_snapshot(request).sha256
        cache = self.store.get_provider_cache(str(provider.name), fingerprint)
        now = datetime.now(timezone.utc)
        if cache and datetime.fromisoformat(cache.expires_at) > now:
            return dict(cache.snapshot.as_dict().get("counts") or {}), True
        try:
            counts = provider.counts(shortlist)
        except ProviderUnavailable:
            return {}, False
        self._spend(
            operation=str(provider.operation),
            count=1,
            trip_id=trip_id,
            detail={"areas": len(shortlist)},
        )
        self.store.put_provider_cache(
            ProviderCacheEntry(
                provider=str(provider.name),
                request_fingerprint=fingerprint,
                snapshot=freeze_snapshot({"counts": counts}),
                retrieved_at=now.isoformat(),
                expires_at=(
                    now + timedelta(days=int(provider.cache_ttl_days))
                ).isoformat(),
            )
        )
        return counts, True

    def _refresh_routes_with(
        self, provider: Any, trip_id: str, *, force: bool = False
    ) -> dict[str, Any]:
        trip = self.store.get_trip(trip_id)
        if trip is None:
            raise PlannerRefusal("unknown_trip", trip_id=trip_id)
        points = self._route_points(trip_id)
        if len(points) < 2:
            raise PlannerRefusal("insufficient_geocoded_places", minimum=2)

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
        # Nearest pairs first, because the cap bites long before 41 places' 1640
        # pairs are covered and a 17 km pair will never be walked whatever it
        # measures. Sorting by place_id spent 340 free calls on arbitrary pairs
        # while every pair the plan actually used stayed unmeasured -- and a
        # missing route falls back to a pessimistic estimate, so the plan showed
        # phantom 68-minute walks between places 1 km apart and failed validation
        # on them. Fetching the same 9 pairs by relevance turned those legs into
        # 14, 10 and 9 minutes and the plan went valid with no other change.
        # place_id stays as the final tiebreak so the order remains deterministic.
        pairs.sort(
            key=lambda pair: (
                _distance_metres(pair[0], pair[1]),
                pair[0]["place_id"],
                pair[1]["place_id"],
            )
        )
        # Already-cached pairs are removed *before* the cap, so `MAX_ROUTE_REQUESTS`
        # limits what one run fetches rather than what a trip can ever know. It
        # read as a total ceiling because the cache check lived inside the loop:
        # the slice always took the same first 60 pairs of a fixed sort, so the
        # 61st pair was unreachable however many times this ran. Measured on the
        # real Taipei trip at 41 selected places -- 1640 pairs needed, 60 fetched,
        # and re-running changed nothing, which left every variant `unavailable`
        # for want of route evidence. The names `request_cap` and
        # `skipped_over_cap` in the reply already described a per-run cap.
        if not force:
            fresh_now = now.isoformat()
            pairs = [
                pair
                for pair in pairs
                if not (
                    (key := (pair[0]["place_id"], pair[1]["place_id"], provider.mode)) in existing
                    and existing[key]["expires_at"] > fresh_now
                )
            ]
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
