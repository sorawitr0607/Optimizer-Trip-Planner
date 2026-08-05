"""Transit journey times from a local GTFS feed.

Pure like the rest of the planning core: **no HTTP, no SQLite, no provider, no
Streamlit**. It reads one zip off disk and answers "how long from here to there by
public transport". `providers.GtfsTransitProvider` is what wraps it for the route
cache; nothing here knows the cache exists.

`WF-038` chose GTFS over a paid routing API and over OpenTripPlanner: a feed is a
file, so it costs nothing per call, works with the aeroplane mode on, and adds no
runtime dependency — GTFS is a zip of CSVs and the standard library reads both.
That matters more than it sounds: the alternative priced at US$0.005 a leg would
cost US$8.20 for one 41-place trip against a US$10 monthly cap.

## What this models, and what it does not

For each pair of consecutive stops on a trip, the feed states a ride time. Taking
the **minimum across every trip** serving that pair gives an optimistic edge, and
Dijkstra over those edges gives a route. Waiting is not free, so each boarding
adds **half the mean headway** measured from how many trips actually serve the
edge across the service day, and each change of route adds a transfer penalty.

So a journey here is *schedule-derived but not schedule-bound*: it does not depend
on the clock, and it will not tell you that the last train has gone. That is a
deliberate simplification and it is why every route this produces is marked
`status: "estimated"` rather than `"verified"`. The planner already distinguishes
those, and `WF-002`'s rule that the app never asserts an unverified fact as
verified is what makes the distinction load-bearing rather than cosmetic.

A consequence worth stating plainly: **do not use these times to catch a flight.**
They are for deciding whether two places belong in the same day.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from heapq import heappop, heappush
from io import TextIOWrapper
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any, Iterator
import zipfile


# Walking speed for access and egress, metres per minute. 80 m/min is 4.8 km/h,
# the same order the reference workbooks' own walking legs imply and slower than
# the 5 km/h a fit adult manages, because this trip has a 51-year-old on it.
WALK_METRES_PER_MINUTE = 80.0

# How far someone will walk to reach transit at either end. Beyond this, transit
# stops being the sensible answer and the walk itself is the journey.
MAX_ACCESS_METRES = 900.0

# Changing route costs more than the arithmetic: finding the platform, reading the
# sign, the chance of missing one. Charged per change, on top of headway waiting.
TRANSFER_PENALTY_MINUTES = 4.0

# Headway is trips-per-edge over the span the feed actually covers, and the span is
# measured rather than assumed. Assuming an 18-hour service day inferred a 90-minute
# wait from six trips that in fact ran 15 minutes apart, because the assumption only
# holds for a feed whose trips really do spread across the day. A measured span is
# right for both a full city feed and a small one.
DEFAULT_SERVICE_MINUTES = 18 * 60
# No feed offers a useful vehicle less than a minute apart, and none is worth
# waiting an hour for in a day plan.
MIN_HEADWAY_WAIT_MINUTES = 1.0
MAX_HEADWAY_WAIT_MINUTES = 30.0


@dataclass(frozen=True)
class Stop:
    stop_id: str
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Journey:
    """One transit answer. Minutes are whole; walking excludes riding and waiting."""

    total_minutes: int
    walking_minutes: int
    waiting_minutes: int
    transfers: int
    boarded_routes: tuple[str, ...]
    origin_stop: str
    destination_stop: str


class GtfsUnavailable(RuntimeError):
    """The feed is absent, unreadable, or missing a file this needs."""


def _metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a1, o1, a2, o2 = radians(lat1), radians(lon1), radians(lat2), radians(lon2)
    value = sin((a2 - a1) / 2) ** 2 + cos(a1) * cos(a2) * sin((o2 - o1) / 2) ** 2
    return 12_742_000 * asin(sqrt(value))


def _seconds(value: str) -> int | None:
    """GTFS times may exceed 24 hours for trips running past midnight."""

    parts = value.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        hours, minutes, seconds = (int(part) for part in parts)
    except ValueError:
        return None
    return hours * 3600 + minutes * 60 + seconds


def _rows(archive: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    if name not in archive.namelist():
        raise GtfsUnavailable(f"GTFS feed has no {name}")
    with archive.open(name) as raw:
        # utf-8-sig: feeds published from spreadsheets routinely carry a BOM, and
        # a BOM on the first header turns `stop_id` into `﻿stop_id`, which
        # silently yields zero usable stops.
        yield from csv.DictReader(TextIOWrapper(raw, encoding="utf-8-sig"))


class TransitFeed:
    """A GTFS zip, indexed for repeated origin/destination questions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise GtfsUnavailable(f"no GTFS feed at {self.path}")
        self.stops: dict[str, Stop] = {}
        # (from_stop, to_stop) -> [minimum ride minutes, trips serving it, route_id]
        self._edges: dict[tuple[str, str], list[Any]] = {}
        self._earliest: int | None = None
        self._latest: int | None = None
        self._load()

    @property
    def service_minutes(self) -> float:
        """The span the feed's own timetable covers, in minutes."""

        if self._earliest is None or self._latest is None:
            return float(DEFAULT_SERVICE_MINUTES)
        measured = (self._latest - self._earliest) / 60
        return float(measured) if measured > 0 else float(DEFAULT_SERVICE_MINUTES)

    def _load(self) -> None:
        try:
            archive = zipfile.ZipFile(self.path)
        except zipfile.BadZipFile as error:
            raise GtfsUnavailable(f"{self.path.name} is not a zip") from error
        with archive:
            for row in _rows(archive, "stops.txt"):
                try:
                    latitude = float(row["stop_lat"])
                    longitude = float(row["stop_lon"])
                except (KeyError, TypeError, ValueError):
                    continue  # a stop without coordinates cannot be walked to
                stop_id = (row.get("stop_id") or "").strip()
                if not stop_id:
                    continue
                self.stops[stop_id] = Stop(
                    stop_id=stop_id,
                    name=(row.get("stop_name") or stop_id).strip(),
                    latitude=latitude,
                    longitude=longitude,
                )
            route_of_trip = {
                (row.get("trip_id") or "").strip(): (row.get("route_id") or "").strip()
                for row in _rows(archive, "trips.txt")
            }
            self._load_edges(archive, route_of_trip)
        if not self.stops:
            raise GtfsUnavailable(f"{self.path.name} has no stops with coordinates")
        if not self._edges:
            raise GtfsUnavailable(f"{self.path.name} has no usable stop_times")

    def _load_edges(
        self, archive: zipfile.ZipFile, route_of_trip: dict[str, str]
    ) -> None:
        """Consecutive stops within each trip become edges, keeping the fastest.

        stop_times.txt is the largest file in a feed by far, so this streams it and
        holds only the current trip. It relies on rows for one trip being
        contiguous, which the specification requires and real feeds honour; a feed
        that interleaves trips would produce too few edges rather than wrong ones.
        """

        trip_id: str | None = None
        previous: tuple[str, int] | None = None
        for row in _rows(archive, "stop_times.txt"):
            current_trip = (row.get("trip_id") or "").strip()
            stop_id = (row.get("stop_id") or "").strip()
            arrival = _seconds(row.get("arrival_time") or "")
            moment = arrival if arrival is not None else _seconds(row.get("departure_time") or "")
            if current_trip != trip_id:
                trip_id, previous = current_trip, None
            if stop_id not in self.stops or moment is None:
                previous = None
                continue
            self._earliest = moment if self._earliest is None else min(self._earliest, moment)
            self._latest = moment if self._latest is None else max(self._latest, moment)
            if previous is not None:
                from_stop, left_at = previous
                ride = max(1, round((moment - left_at) / 60))
                if moment >= left_at:
                    key = (from_stop, stop_id)
                    edge = self._edges.get(key)
                    if edge is None:
                        self._edges[key] = [ride, 1, route_of_trip.get(current_trip, "")]
                    else:
                        edge[0] = min(edge[0], ride)
                        edge[1] += 1
            leaves_at = _seconds(row.get("departure_time") or "") or moment
            previous = (stop_id, leaves_at)

    # -- queries ---------------------------------------------------------

    def near(self, latitude: float, longitude: float) -> list[tuple[Stop, float]]:
        """Stops within walking reach, nearest first, with their distance."""

        found = [
            (stop, distance)
            for stop in self.stops.values()
            if (distance := _metres(latitude, longitude, stop.latitude, stop.longitude))
            <= MAX_ACCESS_METRES
        ]
        found.sort(key=lambda pair: (pair[1], pair[0].stop_id))
        return found

    def journey(
        self,
        *,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> Journey | None:
        """Fastest transit answer, or None when transit does not help.

        Dijkstra over stop edges. State carries the route last boarded so a change
        can be charged; waiting is charged on every boarding, including the first,
        because the first vehicle has to arrive too.
        """

        access = self.near(*origin)
        egress = {stop.stop_id: distance for stop, distance in self.near(*destination)}
        if not access or not egress:
            return None

        def walk_minutes(metres: float) -> float:
            return metres / WALK_METRES_PER_MINUTE

        # (cost, stop_id, route_last_boarded, walking, waiting, transfers,
        #  routes, first_stop_boarded_from)
        queue: list[
            tuple[float, str, str, float, float, int, tuple[str, ...], str]
        ] = []
        for stop, distance in access:
            walking = walk_minutes(distance)
            heappush(queue, (walking, stop.stop_id, "", walking, 0.0, 0, (), stop.stop_id))
        best: dict[tuple[str, str], float] = {}
        outgoing: dict[str, list[tuple[str, list[Any]]]] = {}
        for (from_stop, to_stop), edge in self._edges.items():
            outgoing.setdefault(from_stop, []).append((to_stop, edge))

        answer: Journey | None = None
        while queue:
            (
                cost, stop_id, boarded, walking, waiting, transfers, routes, from_first
            ) = heappop(queue)
            if answer is not None and cost >= answer.total_minutes:
                break
            if stop_id in egress and boarded:
                # Only an answer once something has actually been ridden; otherwise
                # this is a walk dressed as a journey.
                final_walk = walking + walk_minutes(egress[stop_id])
                total = cost + walk_minutes(egress[stop_id])
                candidate = Journey(
                    total_minutes=max(1, round(total)),
                    walking_minutes=max(0, round(final_walk)),
                    waiting_minutes=max(0, round(waiting)),
                    transfers=transfers,
                    boarded_routes=routes,
                    origin_stop=from_first,
                    destination_stop=stop_id,
                )
                if answer is None or candidate.total_minutes < answer.total_minutes:
                    answer = candidate
                continue
            key = (stop_id, boarded)
            if key in best and best[key] <= cost:
                continue
            best[key] = cost
            for to_stop, (ride, trips, route_id) in outgoing.get(stop_id, ()):
                headway_wait = min(
                    MAX_HEADWAY_WAIT_MINUTES,
                    max(
                        MIN_HEADWAY_WAIT_MINUTES,
                        self.service_minutes / (2.0 * max(1, trips)),
                    ),
                )
                change = route_id != boarded
                penalty = (TRANSFER_PENALTY_MINUTES if boarded else 0.0) if change else 0.0
                wait = headway_wait if change else 0.0
                heappush(
                    queue,
                    (
                        cost + ride + wait + penalty,
                        to_stop,
                        route_id,
                        walking,
                        waiting + wait,
                        transfers + (1 if change and boarded else 0),
                        routes + (route_id,) if change else routes,
                        from_first,
                    ),
                )
        return answer
