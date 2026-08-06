"""Deterministic, evidence-aware card ranking with no provider or database imports."""

from __future__ import annotations

from collections import Counter
from math import asin, cos, radians, sin, sqrt
from typing import Any

from .setup import AVOID_TAGS, COMFORT_TAGS


FORMULA_WEIGHTS = {
    "group_preference_fit": 30,
    "experience_value": 20,
    "reward_vs_effort": 20,
    "time_fit": 10,
    "route_compatibility": 15,
    "evidence_quality": 5,
}
CHOICE_ACTIONS = frozenset({"must_do", "interested", "maybe", "not_for_trip"})
REJECTION_REASONS = frozenset(
    {"too_crowded", "too_expensive", "too_tiring", "wrong_vibe", "weak_value", "already_seen"}
)

CATEGORY_TAGS = {
    "attraction": {"sightseeing", "photography"},
    "museum": {"sightseeing", "culture", "architecture"},
    "gallery": {"culture", "photography"},
    "viewpoint": {"sightseeing", "nature", "photography", "night_view"},
    "artwork": {"sightseeing", "culture", "photography"},
    "theme_park": {"activity"},
    "zoo": {"activity", "nature"},
    "aquarium": {"activity", "nature"},
    "historic": {"sightseeing", "culture", "architecture", "photography"},
    "place_of_worship": {"culture", "architecture", "photography"},
    "marketplace": {"markets", "local_street_food", "culture"},
    "theatre": {"culture", "activity", "night_view"},
    "arts_centre": {"culture", "activity"},
    "park": {"nature", "chill", "photography", "rewarding_walks"},
    "garden": {"nature", "chill", "photography", "rewarding_walks"},
    "nature_reserve": {"nature", "photography", "rewarding_walks"},
    "water_park": {"activity"},
    "sports_centre": {"activity"},
    "spa": {"chill"},
    "beach": {"nature", "chill", "photography"},
    "peak": {"nature", "sightseeing", "photography", "rewarding_walks"},
    "mall": {"shopping", "chill"},
    "department_store": {"shopping"},
    "tower": {"sightseeing", "architecture", "photography", "night_view"},
    "landmark": {"sightseeing", "architecture", "photography"},
}

CATEGORY_FAMILY = {
    "museum": "culture",
    "gallery": "culture",
    "artwork": "culture",
    "historic": "culture",
    "place_of_worship": "culture",
    "theatre": "culture",
    "arts_centre": "culture",
    "viewpoint": "view_nature",
    "park": "view_nature",
    "garden": "view_nature",
    "nature_reserve": "view_nature",
    "beach": "view_nature",
    "peak": "view_nature",
    "tower": "landmark",
    "landmark": "landmark",
    "attraction": "landmark",
    "marketplace": "market_food",
    "mall": "shopping",
    "department_store": "shopping",
    "theme_park": "activity",
    "zoo": "activity",
    "aquarium": "activity",
    "water_park": "activity",
    "sports_centre": "activity",
    "spa": "rest",
}

EXPERIENCE_PRIOR = {
    "viewpoint": 16,
    "peak": 16,
    "tower": 15,
    "theme_park": 15,
    "museum": 14,
    "historic": 14,
    "attraction": 14,
    "aquarium": 14,
    "zoo": 13,
    "place_of_worship": 13,
    "nature_reserve": 13,
    "theatre": 13,
    "marketplace": 12,
    "park": 12,
    "garden": 12,
    "gallery": 12,
    "water_park": 12,
    "arts_centre": 11,
    "artwork": 11,
    "beach": 11,
    "landmark": 11,
    "mall": 9,
    "department_store": 9,
    "sports_centre": 8,
    "spa": 8,
}

DURATION_ESTIMATES = {
    "museum": (90, 180),
    "gallery": (60, 120),
    "theme_park": (180, 360),
    "zoo": (120, 240),
    "aquarium": (90, 180),
    "historic": (45, 90),
    "place_of_worship": (30, 75),
    "marketplace": (45, 120),
    "theatre": (90, 180),
    "park": (45, 120),
    "garden": (45, 90),
    "nature_reserve": (90, 180),
    "viewpoint": (30, 75),
    "tower": (45, 90),
    "mall": (60, 180),
    "department_store": (60, 180),
}

ICON_CATEGORIES = frozenset(
    {
        "attraction",
        "museum",
        "viewpoint",
        "historic",
        "place_of_worship",
        "park",
        "garden",
        "peak",
        "tower",
        "landmark",
    }
)


def build_ranking(
    *,
    setup: dict[str, Any],
    candidates: list[dict[str, Any]],
    choices: list[dict[str, Any]],
    discovery_status: str,
) -> dict[str, Any]:
    choice_by_id = {choice["place_id"]: choice for choice in choices}
    base_weights, effective_weights = _group_weights(setup)
    selected_candidates = [
        choice["candidate"]
        for choice in choices
        if choice["action"] in {"must_do", "interested"}
    ]
    learned_categories = _learned_category_weights(choices)

    candidate_by_id = candidates_by_id(candidates)
    cards = {
        candidate["place_id"]: _score_candidate(
            candidate,
            setup=setup,
            effective_weights=effective_weights,
            selected_candidates=selected_candidates,
            choice=choice_by_id.get(candidate["place_id"]),
            learned_category_bonus=learned_categories.get(candidate["category"], 0.0),
            discovery_status=discovery_status,
        )
        for candidate in candidates
    }
    ordered_ids = sorted(
        cards,
        key=lambda place_id: (
            -cards[place_id]["total_score"],
            candidate_by_id[place_id]["name"].casefold(),
            place_id,
        ),
    )
    icon_ids = [place_id for place_id in ordered_ids if cards[place_id]["is_city_icon"]]
    unseen_normal = [
        place_id
        for place_id in ordered_ids
        if place_id not in choice_by_id and place_id not in set(icon_ids)
    ]
    main_queue = _protected_queue(unseen_normal, cards)
    for entry in main_queue:
        cards[entry["place_id"]]["queue_role"] = entry["role"]
        if entry["role"] == "protected_exploration":
            cards[entry["place_id"]]["why_shown"].append("protected_exploration")

    worth_it_if = [
        place_id
        for place_id in ordered_ids
        if cards[place_id]["experience_value"] >= 14
        and (
            "opening_unconfirmed" in cards[place_id]["cons"]
            or "route_not_verified" in cards[place_id]["cons"]
            or "possible_duplicate" in cards[place_id]["cons"]
        )
    ]
    local_alternatives = _local_alternatives(icon_ids, ordered_ids, cards)
    reconciliation = _reconciliation(choices, cards)

    if set(ordered_ids) != set(cards):
        raise RuntimeError("Browse All must retain every scored candidate")
    return {
        "schema_version": 1,
        "formula_weights": FORMULA_WEIGHTS,
        "base_group_weights": base_weights,
        "effective_group_weights": effective_weights,
        "learned_category_weights": dict(sorted(learned_categories.items())),
        "cards": cards,
        "lanes": {
            "main_queue": main_queue,
            "city_icons": icon_ids,
            "worth_it_if": worth_it_if,
            "local_alternatives": local_alternatives,
            "browse_all": ordered_ids,
        },
        "choices": [
            {
                "place_id": choice["place_id"],
                "action": choice["action"],
                "reason": choice.get("reason"),
            }
            for choice in sorted(choices, key=lambda item: item["place_id"])
        ],
        "reconciliation": reconciliation,
        "coverage": {
            "retrieved_candidates": len(candidates),
            "scored_candidates": len(cards),
            "browse_all_candidates": len(ordered_ids),
            "city_icons": len(icon_ids),
            "unseen_normal_cards": len(main_queue),
            "rated_cards": len(choice_by_id),
            "selected_missing_from_latest": sum(
                1
                for choice in choices
                if choice["action"] in {"must_do", "interested"}
                and choice["place_id"] not in cards
            ),
        },
        "feasibility_state": "not_evaluated_until_optimizer",
    }


def candidates_by_id(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {candidate["place_id"]: candidate for candidate in candidates}


def validate_choice(action: str, reason: str | None) -> tuple[str, str | None]:
    if action not in CHOICE_ACTIONS:
        raise ValueError(f"Unsupported candidate choice: {action}")
    clean_reason = reason.strip() if reason else None
    if action != "not_for_trip":
        return action, None
    if clean_reason and clean_reason not in REJECTION_REASONS:
        raise ValueError(f"Unsupported rejection reason: {clean_reason}")
    return action, clean_reason


def _score_candidate(
    candidate: dict[str, Any],
    *,
    setup: dict[str, Any],
    effective_weights: dict[str, float],
    selected_candidates: list[dict[str, Any]],
    choice: dict[str, Any] | None,
    learned_category_bonus: float,
    discovery_status: str,
) -> dict[str, Any]:
    category = candidate["category"]
    candidate_tags = set(CATEGORY_TAGS.get(category, {"sightseeing"}))
    preference, matched_tags, matched_people = _preference_fit(
        setup, candidate_tags, effective_weights
    )
    preference = min(30.0, preference + learned_category_bonus)
    city_icon, icon_basis = _city_icon(candidate)
    experience = min(
        20.0,
        float(EXPERIENCE_PRIOR.get(category, 10))
        + (1.0 if candidate.get("signals", {}).get("wikidata") else 0.0)
        + (1.0 if candidate.get("signals", {}).get("wikipedia") else 0.0),
    )
    reward_effort = 10.0
    time_fit = _time_fit(candidate)
    route_fit, route_distance = _route_fit(candidate, selected_candidates)
    evidence = _evidence_score(candidate, discovery_status)
    deductions: list[dict[str, Any]] = []
    if candidate.get("possible_duplicate"):
        deductions.append({"code": "possible_duplicate", "points": 2.0})
    if _redundant_near_selection(candidate, selected_candidates):
        deductions.append({"code": "near_selected_similar_experience", "points": 2.0})
    if choice and choice["action"] == "not_for_trip":
        deductions.append(
            {
                "code": choice.get("reason") or "owner_rejected_without_reason",
                "points": 2.0 if choice.get("reason") else 0.5,
            }
        )

    positive_total = preference + experience + reward_effort + time_fit + route_fit + evidence
    total = round(max(0.0, positive_total - sum(item["points"] for item in deductions)), 1)
    opening_state = candidate["operational_evidence"]["opening_hours"]["state"]
    why = []
    if matched_tags:
        why.append("group_preference_match")
    if matched_people:
        why.append("member_preferences_considered")
    if city_icon:
        why.append("city_icon_evidence")
    if learned_category_bonus:
        why.append("learned_from_choices")
    if experience >= 14:
        why.append("high_experience_potential")
    if not why:
        why.append("broad_baseline_candidate")

    pros = ["open_export_source"]
    if matched_tags:
        pros.append("preference_match")
    if city_icon:
        pros.append("city_icon")
    if opening_state == "regular_schedule_only":
        pros.append("regular_hours_present")
    if route_distance is not None and route_distance <= 3_000:
        pros.append("near_selected_cluster")
    cons = ["route_not_verified", "ratings_not_enriched", "best_time_unconfirmed"]
    if opening_state == "unconfirmed":
        cons.append("opening_unconfirmed")
    if candidate.get("possible_duplicate"):
        cons.append("possible_duplicate")
    if candidate["operational_evidence"]["access"]["state"] == "unconfirmed":
        cons.append("access_unconfirmed")

    duration = DURATION_ESTIMATES.get(category, (45, 120))
    dimensions = {
        "group_preference_fit": {"score": round(preference, 1), "max": 30},
        "experience_value": {"score": round(experience, 1), "max": 20},
        "reward_vs_effort": {"score": reward_effort, "max": 20},
        "time_fit": {"score": time_fit, "max": 10},
        "route_compatibility": {"score": route_fit, "max": 15},
        "evidence_quality": {"score": evidence, "max": 5},
    }
    return {
        "place_id": candidate["place_id"],
        "total_score": total,
        "dimensions": dimensions,
        "deductions": deductions,
        "candidate_tags": sorted(candidate_tags),
        "matched_tags": sorted(matched_tags),
        "matched_people": matched_people,
        "learned_category_bonus": learned_category_bonus,
        "experience_value": experience,
        "is_city_icon": city_icon,
        "city_icon_basis": icon_basis,
        "queue_role": None,
        "why_shown": why,
        "pros": pros,
        "cons": cons,
        "duration_estimate": {
            "minimum_minutes": duration[0],
            "maximum_minutes": duration[1],
            "origin": "planner_category_default",
        },
        "route_distance_to_selected_metres": route_distance,
        "effort_state": "route_and_walking_not_evaluated",
        "feasibility": {
            "state": "not_evaluated",
            "reason": "optimizer_not_run",
        },
        "ratings": [],
        "example_reviews": [],
        "choice_action": choice["action"] if choice else None,
    }


def _group_weights(setup: dict[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    owner = setup["owner"]
    members = setup.get("travellers", [])
    stored = setup.get("group_preference_weights", {})
    base = {"owner": float(stored.get("owner", 1.0 if not members else 0.5))}
    if members:
        default_member = (1.0 - base["owner"]) / len(members)
        for member in members:
            base[member["traveller_id"]] = float(
                stored.get(member["traveller_id"], default_member)
            )

    known = {"owner"} if _profile_has_preferences(owner, owner=True) else set()
    known.update(
        member["traveller_id"]
        for member in members
        if _profile_has_preferences(member, owner=False)
    )
    total = sum(weight for person, weight in base.items() if person in known)
    effective = (
        {person: round(weight / total, 6) for person, weight in base.items() if person in known}
        if total
        else {}
    )
    return base, effective


def _profile_has_preferences(profile: dict[str, Any], *, owner: bool) -> bool:
    if owner:
        return any(profile.get(key) for key in ("main_style", "also_enjoy", "avoid", "comfort"))
    return bool(profile.get("tags"))


def _breadth(candidate_tags: set[str]) -> int:
    """How many tags a candidate's category offers, capped. `WF-037`.

    Capped at four because beyond that the divisor stops discriminating and starts
    punishing richly-tagged categories, which is the mirror of the bug it fixes.
    Minimum one so a category with no tags cannot divide by zero.
    """

    return max(1, min(len(candidate_tags), 4))


def _preference_fit(
    setup: dict[str, Any], candidate_tags: set[str], effective_weights: dict[str, float]
) -> tuple[float, set[str], list[str]]:
    owner = setup["owner"]
    people: list[tuple[str, dict[str, Any], bool]] = [("owner", owner, True)]
    people.extend(
        (member["traveller_id"], member, False) for member in setup.get("travellers", [])
    )
    weighted = 0.0
    matched: set[str] = set()
    matched_people: list[str] = []
    for person_id, profile, is_owner in people:
        if person_id not in effective_weights:
            continue
        if is_owner:
            main = set(profile.get("main_style", []))
            also = set(profile.get("also_enjoy", []))
            comfort = set(profile.get("comfort", []))
            main_hit = candidate_tags & main
            also_hit = candidate_tags & also
            comfort_hit = candidate_tags & comfort
            person_fit = 0.1
            # `WF-037`. Divided by how many tags the *category* carries, not by how
            # many styles the owner named. The old denominator asked "how many of
            # your interests does this cover", which a category with more tags wins
            # for free: `peak` carries four tags and `attraction` -- where OSM puts
            # Taipei 101 -- carries two, so a nameless hill scored 27 of 30 against
            # Taipei 101's 12.8 and the top 50 of 832 came out as 49 peaks and one
            # park. Taipei 101 ranked 363rd, the National Palace Museum 269th.
            #
            # Asking instead "how much of what this place *is* matches what you
            # want" removes an advantage that belongs to the tag vocabulary rather
            # than to anywhere real. It also unblocks `learned_category_bonus`: the
            # owner's own 71 peak rejections could not outweigh a structural gap
            # that large, and now they can.
            person_fit += 0.65 * len(main_hit) / _breadth(candidate_tags)
            person_fit += 0.20 * len(also_hit) / _breadth(candidate_tags)
            person_fit += 0.05 * len(comfort_hit) / max(1, min(len(comfort), 2))
            hits = main_hit | also_hit | comfort_hit
        else:
            positive = set(profile.get("tags", [])) - set(AVOID_TAGS) - set(COMFORT_TAGS)
            hits = candidate_tags & positive
            person_fit = (
                0.15 + 0.85 * len(hits) / max(1, min(len(positive), 2))
                if positive
                else 0.5
            )
        person_fit = min(1.0, person_fit)
        weighted += effective_weights[person_id] * person_fit
        if hits:
            matched.update(hits)
            matched_people.append(person_id)
    return round(30 * weighted, 1), matched, matched_people


def _learned_category_weights(choices: list[dict[str, Any]]) -> Counter[str]:
    learned: Counter[str] = Counter()
    action_bonus = {"must_do": 2.0, "interested": 1.0, "maybe": 0.25}
    for choice in choices:
        bonus = action_bonus.get(choice["action"])
        if bonus:
            learned[choice["candidate"]["category"]] += bonus
    for category in list(learned):
        learned[category] = min(3.0, learned[category])
    return learned


def _city_icon(candidate: dict[str, Any]) -> tuple[bool, list[str]]:
    signals = candidate.get("signals", {})
    # A Wikidata ID is common even for minor peaks and neighborhood temples; it
    # proves identity, not global prominence. Wikipedia/heritage coverage is the
    # smallest honest open-data signal available for the protected landmark lane.
    basis = [key for key in ("wikipedia", "heritage", "unesco") if signals.get(key)]
    return bool(candidate["category"] in ICON_CATEGORIES and basis), basis


def _time_fit(candidate: dict[str, Any]) -> float:
    opening = candidate["operational_evidence"]["opening_hours"]["state"]
    opening_score = {"official_confirmed": 7.0, "current_provider": 6.0,
                     "regular_schedule_only": 5.0, "unconfirmed": 3.0,
                     "conflicting": 1.0}.get(opening, 2.0)
    best_time = candidate["operational_evidence"]["best_time"]["state"]
    return min(10.0, opening_score + (3.0 if best_time == "official_confirmed" else 0.0))


def _route_fit(
    candidate: dict[str, Any], selected: list[dict[str, Any]]
) -> tuple[float, int | None]:
    others = [item for item in selected if item["place_id"] != candidate["place_id"]]
    if not others:
        return 7.5, None
    distance = int(min(_distance_metres(candidate, item) for item in others))
    if distance <= 1_000:
        return 15.0, distance
    if distance <= 3_000:
        return 12.0, distance
    if distance <= 7_000:
        return 9.0, distance
    if distance <= 15_000:
        return 6.0, distance
    return 3.0, distance


def _evidence_score(candidate: dict[str, Any], discovery_status: str) -> float:
    score = {"verified": 2.0, "stale": 0.5, "conflicting": 0.25}.get(
        discovery_status, 0.0
    )
    if candidate["operational_evidence"]["opening_hours"]["state"] == "regular_schedule_only":
        score += 0.75
    names = candidate.get("names", {})
    if names.get("local") and names.get("en"):
        score += 0.75
    if candidate.get("website"):
        score += 0.5
    if len(candidate.get("provider_aliases", [])) > 1:
        score += 0.5
    if candidate.get("signals", {}).get("wikidata") or candidate.get("signals", {}).get(
        "wikipedia"
    ):
        score += 0.5
    return round(min(5.0, score), 1)


def _redundant_near_selection(
    candidate: dict[str, Any], selected: list[dict[str, Any]]
) -> bool:
    family = CATEGORY_FAMILY.get(candidate["category"], candidate["category"])
    return any(
        item["place_id"] != candidate["place_id"]
        and CATEGORY_FAMILY.get(item["category"], item["category"]) == family
        and _distance_metres(candidate, item) <= 300
        for item in selected
    )


def _protected_queue(
    ordered_ids: list[str], cards: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    remaining = list(ordered_ids)
    result: list[dict[str, str]] = []
    seen_families: Counter[str] = Counter()
    while remaining:
        for _ in range(4):
            if not remaining:
                break
            place_id = remaining.pop(0)
            result.append({"place_id": place_id, "role": "ranked"})
            seen_families[_family(cards[place_id])] += 1
        if remaining:
            place_id = min(
                remaining,
                key=lambda item: (
                    seen_families[_family(cards[item])],
                    -cards[item]["total_score"],
                    item,
                ),
            )
            remaining.remove(place_id)
            result.append({"place_id": place_id, "role": "protected_exploration"})
            seen_families[_family(cards[place_id])] += 1
    return result


def _family(card: dict[str, Any]) -> str:
    tags = card["candidate_tags"]
    for preferred in ("culture", "nature", "activity", "shopping", "markets", "chill"):
        if preferred in tags:
            return preferred
    return tags[0] if tags else "other"


def _local_alternatives(
    icon_ids: list[str], ordered_ids: list[str], cards: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    used: set[str] = set()
    for icon_id in icon_ids:
        icon = cards[icon_id]
        candidates = [
            place_id
            for place_id in ordered_ids
            if place_id not in used
            and not cards[place_id]["is_city_icon"]
            and cards[place_id]["choice_action"] != "not_for_trip"
            and _family(cards[place_id]) == _family(icon)
            and cards[place_id]["dimensions"]["group_preference_fit"]["score"]
            >= icon["dimensions"]["group_preference_fit"]["score"]
        ]
        if candidates:
            alternative = candidates[0]
            used.add(alternative)
            result.append(
                {
                    "place_id": alternative,
                    "alternative_to": icon_id,
                    "reason": "similar_style_equal_or_better_group_fit",
                }
            )
    return result


def _reconciliation(
    choices: list[dict[str, Any]], cards: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for choice in sorted(choices, key=lambda item: item["candidate"]["name"].casefold()):
        if choice["action"] not in {"must_do", "interested"}:
            continue
        place_id = choice["place_id"]
        result.append(
            {
                "place_id": place_id,
                "name": choice["candidate"]["name"],
                "choice": choice["action"],
                "status": "pending_optimizer",
                "reason": "no_timetable_or_route_validation_yet",
                "consequence": "kept_for_whole_trip_optimization",
                "present_in_latest_discovery": place_id in cards,
                "smallest_next_step": "run_slice_4_optimizer",
            }
        )
    return result


def _distance_metres(left: dict[str, Any], right: dict[str, Any]) -> float:
    lat1, lon1 = radians(left["latitude"]), radians(left["longitude"])
    lat2, lon2 = radians(right["latitude"]), radians(right["longitude"])
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 12_742_000 * asin(sqrt(value))
