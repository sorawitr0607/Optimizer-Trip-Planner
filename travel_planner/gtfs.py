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
from datetime import date
from dataclasses import replace
from io import TextIOWrapper
from pathlib import Path
from typing import Any, Iterator
import zipfile

from .transit import Edge, Journey, Stop, TransitGraph, _station_of, metres


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


class GtfsUnavailable(RuntimeError):
    """The feed is absent, unreadable, or missing a file this needs."""


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

    def __init__(self, path: str | Path, *, service_date: str | None = None) -> None:
        self.service_date = service_date
        self.service_coverage: dict[str, str | None] = {"start": None, "end": None}
        self.route_names: dict[str, str] = {}
        self.bus_routes: set[str] = set()
        self.estimated_routes: set[str] = set()
        self.frequency_waits: dict[str, float] = {}
        self.path = Path(path)
        if not self.path.is_file():
            raise GtfsUnavailable(f"no GTFS feed at {self.path}")
        self.stops: dict[str, Stop] = {}
        # (from_stop, to_stop) -> [minimum ride minutes, trips serving it, route_id]
        self._edges: dict[tuple[str, str], list[Any]] = {}
        self._earliest: int | None = None
        self._latest: int | None = None
        self._graph: TransitGraph | None = None
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
            if "routes.txt" in archive.namelist():
                self.route_names = {row["route_id"]: row.get("route_short_name") or row.get("route_long_name") or row["route_id"] for row in _rows(archive, "routes.txt")}
                self.bus_routes = {row["route_id"] for row in _rows(archive, "routes.txt") if row.get("route_type") == "3"}
            if "translations.txt" in archive.namelist():
                for row in _rows(archive, "translations.txt"):
                    if not row.get("language", "").startswith("en"):
                        continue
                    identifier = row.get("record_id")
                    if row.get("table_name") == "stops" and identifier in self.stops:
                        self.stops[identifier] = replace(self.stops[identifier], name_en=row.get("translation"))
                    elif row.get("table_name") == "routes" and identifier in self.route_names:
                        self.route_names[identifier] = row.get("translation") or self.route_names[identifier]
            active = self._active_services(archive)
            route_of_trip = {
                (row.get("trip_id") or "").strip(): (row.get("route_id") or "").strip()
                for row in _rows(archive, "trips.txt")
                if active is None or row.get("service_id") in active
            }
            if "frequencies.txt" in archive.namelist():
                for row in _rows(archive, "frequencies.txt"):
                    try:
                        self.frequency_waits[row["trip_id"]] = float(row["headway_secs"]) / 120
                    except (KeyError, ValueError):
                        continue
            self._load_edges(archive, route_of_trip)
        if not self.stops:
            raise GtfsUnavailable(f"{self.path.name} has no stops with coordinates")
        if not self._edges:
            raise GtfsUnavailable(f"{self.path.name} has no usable stop_times")
        # TDX's metro subset still contains the national stops table. Only stops
        # on a metro edge can answer a route or establish feed coverage.
        served = {stop_id for pair in self._edges for stop_id in pair}
        self.stops = {stop_id: stop for stop_id, stop in self.stops.items() if stop_id in served}

    def _active_services(self, archive: zipfile.ZipFile) -> set[str] | None:
        calendars = list(_rows(archive, "calendar.txt")) if "calendar.txt" in archive.namelist() else []
        exceptions = list(_rows(archive, "calendar_dates.txt")) if "calendar_dates.txt" in archive.namelist() else []
        starts = [row["start_date"] for row in calendars if row.get("start_date")] + [row["date"] for row in exceptions if row.get("date")]
        ends = [row["end_date"] for row in calendars if row.get("end_date")] + [row["date"] for row in exceptions if row.get("date")]
        if starts:
            self.service_coverage = {"start": min(starts), "end": max(ends)}
        if not self.service_date or not starts:
            return None
        day = date.fromisoformat(self.service_date)
        value = day.strftime("%Y%m%d")
        # Outside published coverage, retain the topology as an explicitly provisional estimate.
        if value < min(starts) or value > max(ends):
            return None
        weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[day.weekday()]
        active = {row["service_id"] for row in calendars if row.get("start_date", "") <= value <= row.get("end_date", "") and row.get(weekday) == "1"}
        for row in exceptions:
            if row.get("date") == value:
                if row.get("exception_type") == "1":
                    active.add(row["service_id"])
                elif row.get("exception_type") == "2":
                    active.discard(row["service_id"])
        return active

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
            if current_trip not in route_of_trip:
                continue
            stop_id = (row.get("stop_id") or "").strip()
            arrival = _seconds(row.get("arrival_time") or "")
            moment = arrival if arrival is not None else _seconds(row.get("departure_time") or "")
            if current_trip != trip_id:
                trip_id, previous = current_trip, None
            if moment is None and previous and stop_id in self.stops and route_of_trip[current_trip] in self.bus_routes:
                left, right = self.stops[previous[0]], self.stops[stop_id]
                # ponytail: untimed bus topology uses 20 km/h, 1.4 road factor and one minute per stop; replace with published times when available.
                ride = max(1, round(metres(left.latitude, left.longitude, right.latitude, right.longitude) * 1.4 / 333)) + 1
                moment = previous[1] + ride * 60
                self.estimated_routes.add(route_of_trip[current_trip])
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
                        self._edges[key] = [ride, 1, route_of_trip.get(current_trip, ""), self.frequency_waits.get(current_trip)]
                    else:
                        edge[0] = min(edge[0], ride)
                        edge[1] += 1
                        wait = self.frequency_waits.get(current_trip)
                        if wait is not None:
                            edge[3] = min(edge[3], wait) if edge[3] is not None else wait
            leaves_at = _seconds(row.get("departure_time") or "") or moment
            previous = (stop_id, leaves_at)

    # -- the graph -------------------------------------------------------

    @property
    def graph(self) -> TransitGraph:
        """Built once from the parsed edges; the routing itself lives in transit.py.

        Headway becomes a per-edge wait here, because only GTFS can measure it:
        trips serving the edge over the span the feed actually covers.
        """

        if self._graph is None:
            # Different lines give the same station different stop IDs (Taipei Main
            # is TRTC_R10 and TRTC_BL12). Share the station node so a change of line
            # is reachable; TransitGraph already charges the transfer and next wait.
            station_of = _station_of(self.stops)
            edges = {}
            for (origin, destination), (ride, trips, route_id, frequency_wait) in self._edges.items():
                key = (station_of[origin], station_of[destination])
                if key[0] == key[1]:
                    continue
                edge = Edge(
                    ride_minutes=float(ride),
                    wait_minutes=min(
                        MAX_HEADWAY_WAIT_MINUTES,
                        max(
                            MIN_HEADWAY_WAIT_MINUTES,
                            frequency_wait if frequency_wait is not None else self.service_minutes / (2.0 * max(1, trips)),
                        ),
                    ),
                    route_id=route_id,
                    basis="timetable",
                )
                if key not in edges or edge.ride_minutes < edges[key].ride_minutes:
                    edges[key] = edge
            stops = {stop_id: stop for stop_id, stop in self.stops.items() if station_of[stop_id] == stop_id}
            self._graph = TransitGraph(stops, edges)
        return self._graph

    def near(self, latitude: float, longitude: float) -> list[tuple[Stop, float]]:
        return self.graph.near(latitude, longitude)

    def journey(
        self,
        *,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> Journey | None:
        journey = self.graph.journey(origin=origin, destination=destination)
        if journey and self.estimated_routes.intersection(journey.boarded_routes):
            return replace(journey, basis="bus_topology_estimate")
        return journey
