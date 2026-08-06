"""Ranking places to stay, for an owner who has not booked yet.

Pure: no Streamlit, SQLite, provider, exporter, or model imports.

`WF-040` found that `optimizer._hotel_recommendation` can never recommend anything,
because it only ever has one candidate — the base already recorded, or the centroid of
whatever is selected. Its `runner_up_area_id` and `travel_delta_minutes` are dead by
construction. This module is the answer to the question that function's field names
promise: *given the places I chose, where should I stay?*

**The unit is a transit station, not a hotel and not an administrative district.**
Three reasons, in order of weight:

- It is how the owner already thinks. Their words while looking for a family room were
  "it only near ximenting station", and in a metro city that is how accommodation is
  searched, listed and described.
- The app can measure it exactly. A station's travel time to every selected place comes
  from the graph `WF-038` already builds, for free, with no new provider.
- District names do not generalise. Taipei's OSM addresses carry `中正區` on 278 of 832
  candidates, so parsing a district would be a Chinese-only regex over a third of the
  data, in an app whose acceptance check is worldwide. A station name is already
  bilingual in OSM and needs no parsing.

**What this refuses to do is claim quality.** Price, room type, family capacity,
cleanliness and real safety are not in any free source the app reads, so they are
returned as named gaps rather than silently folded into a score. The owner's own case
is the argument: the district that fits their plan best is still one where the only
family room is on Airbnb, and no amount of OpenStreetMap counting would have known
that. This ranks *where*, and the owner books *what*.
"""

from __future__ import annotations

from math import log1p
from typing import Any


# The five factors, with the weight each contributes to a 100-point total. Travel time
# dominates on purpose: it is the only one measured rather than inferred, and it is the
# one that changes every day of the trip. The other four are proxies and are weighted
# like proxies.
FACTOR_WEIGHTS: dict[str, float] = {
    "travel_time": 45.0,
    "metro_access": 20.0,
    "food_nearby": 15.0,
    "after_dark": 10.0,
    "lodging_choice": 10.0,
}

# Counts at or above these are full marks. Set from what Taipei actually returns, not
# from intuition: the eight shortlisted stations came back with 150-586 places to eat,
# 1-31 open after dark and 1-114 listed beds within 600 m. A first pass used 30 for food
# and every station scored a flat 15 of 15 -- the factor was a constant wearing a score's
# clothes. These ceilings are set where the numbers stop meaning anything more.
SATURATION: dict[str, int] = {
    "food_nearby": 400,
    "after_dark": 25,
    "lodging_choice": 60,
    # An interchange is the point; a fourth line adds little a third has not.
    "line_count": 3,
}

# Walking minutes to the station itself. Zero is full marks and this is nothing; the
# area *is* the station, so this measures how spread out its exits are.
GOOD_ACCESS_MINUTES = 6.0

# What no free source can tell the owner. Reported on every area, every time, because a
# ranking that stays silent about them reads as a complete recommendation.
NOT_EVALUATED: tuple[str, ...] = (
    "AREA_PRICE_NOT_EVALUATED",
    "AREA_ROOM_TYPE_AND_FAMILY_CAPACITY_NOT_EVALUATED",
    "AREA_CLEANLINESS_NOT_EVALUATED",
    "AREA_SAFETY_NOT_EVALUATED",
)


def _saturating(count: int, saturation: int) -> float:
    """0.0 at nothing, 1.0 at saturation, with diminishing returns between.

    Logarithmic, because these counts span an order of magnitude and the difference
    between 5 and 50 places to eat is the difference between "nowhere" and "plenty",
    while 450 against 586 is no difference at all. Straight division would spend most of
    the scale on distinctions nobody can act on and flatten the one that matters.
    """

    if saturation <= 0:
        return 0.0
    return min(1.0, log1p(max(0, count)) / log1p(saturation))


def _travel_fraction(minutes: float, best: float) -> float:
    """The quickest area's time as a share of this one's: 1.0 for the best.

    A **ratio** against the best, not a rank between best and worst. Stretching the
    scores across the observed range sounds fairer and manufactures precision: measured
    on the real Taipei trip the eight shortlisted stations averaged 20 to 22 minutes to
    the whole plan, and rank-scaling turned that two-minute spread into a 45-point gap,
    so the top area looked decisive when the honest answer is "these are all much the
    same, pick on price". A ratio gives 20/22 = 0.91 and says so.
    """

    if minutes <= 0:
        return 1.0
    return min(1.0, best / minutes)


def score_areas(
    areas: list[dict[str, Any]],
    *,
    place_count: int,
) -> dict[str, Any]:
    """Rank candidate stay-areas. Deterministic, and ties break on area id.

    Each area needs `area_id`, `name`, `names`, `total_travel_minutes`,
    `reachable_place_count`, `access_walk_minutes`, `line_count`, and the three counts
    `food_count`, `after_dark_count`, `lodging_count`.

    An area that cannot reach every selected place is **not** dropped -- it is scored on
    what it does reach and carries `AREA_DOES_NOT_REACH_EVERY_PLACE`, because an owner
    is entitled to see that a well-placed neighbourhood misses one outlying stop.
    """

    usable = [
        area
        for area in areas
        if area.get("reachable_place_count") and area.get("total_travel_minutes") is not None
    ]
    if not usable:
        return {
            "areas": [],
            "not_evaluated": list(NOT_EVALUATED),
            "reason": "NO_AREA_REACHES_ANY_SELECTED_PLACE",
            "place_count": place_count,
        }

    # Compared per reachable place, or an area that reaches three nearby stops would beat
    # one that reaches all thirteen purely by having a smaller sum.
    def per_place(area: dict[str, Any]) -> float:
        return float(area["total_travel_minutes"]) / int(area["reachable_place_count"])

    best = min(per_place(area) for area in usable)

    scored = []
    for area in usable:
        fractions = {
            "travel_time": _travel_fraction(per_place(area), best),
            "metro_access": max(
                0.0,
                1.0 - float(area.get("access_walk_minutes", 0.0)) / GOOD_ACCESS_MINUTES,
            )
            * 0.6
            + _saturating(int(area.get("line_count", 0)), SATURATION["line_count"]) * 0.4,
            "food_nearby": _saturating(
                int(area.get("food_count", 0)), SATURATION["food_nearby"]
            ),
            "after_dark": _saturating(
                int(area.get("after_dark_count", 0)), SATURATION["after_dark"]
            ),
            "lodging_choice": _saturating(
                int(area.get("lodging_count", 0)), SATURATION["lodging_choice"]
            ),
        }
        factors = {
            key: {
                "score": round(FACTOR_WEIGHTS[key] * value, 1),
                "max": FACTOR_WEIGHTS[key],
            }
            for key, value in fractions.items()
        }
        notes = []
        if int(area["reachable_place_count"]) < place_count:
            notes.append("AREA_DOES_NOT_REACH_EVERY_PLACE")
        if not int(area.get("food_count", 0)):
            notes.append("AREA_NO_FOOD_FOUND_NEARBY")
        if not int(area.get("lodging_count", 0)):
            notes.append("AREA_NO_LISTED_LODGING_NEARBY")
        scored.append(
            {
                "area_id": area["area_id"],
                "name": area.get("name") or area["area_id"],
                "names": area.get("names", {}),
                "latitude": area.get("latitude"),
                "longitude": area.get("longitude"),
                "total_score": round(sum(item["score"] for item in factors.values()), 1),
                "factors": factors,
                "median_travel_minutes": round(per_place(area)),
                "total_travel_minutes": int(area["total_travel_minutes"]),
                "reachable_place_count": int(area["reachable_place_count"]),
                # The raw counts travel with the score so the screen can show what the
                # inferred factors were inferred *from*. A bare 15/15 for food is not
                # something an owner can check; "482 places to eat" is.
                "counts": {
                    key: int(area.get(key, 0))
                    for key in ("food_count", "after_dark_count", "lodging_count")
                },
                "notes": notes,
            }
        )

    scored.sort(key=lambda item: (-item["total_score"], item["area_id"]))
    return {
        "areas": scored,
        "not_evaluated": list(NOT_EVALUATED),
        "reason": None,
        "place_count": place_count,
    }
