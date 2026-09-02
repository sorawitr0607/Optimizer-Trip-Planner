"""A transit graph and the routing over it, independent of where it came from.

Pure like the rest of the planning core: no HTTP, no SQLite, no provider. Two
things build one of these — `gtfs.TransitFeed` from a timetable file, and
`graph_from_osm()` from an OpenStreetMap subway relation — and the routing below is
shared so there is exactly one Dijkstra to be wrong.

The split exists because `WF-038` produced two data sources with very different
quality. GTFS states real ride times and lets headway be measured. OpenStreetMap
states only topology: which stations a line joins, in order. Both answer "how long
from here to there", and the difference is entirely in how the edges are built —
which is why `Edge` carries `basis` and every route derived from here is
`status: "estimated"` rather than `"verified"`.
"""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import asin, cos, radians, sin, sqrt


# Walking speed for access and egress, metres per minute. 80 m/min is 4.8 km/h,
# slower than a fit adult's 5 km/h because this trip has a 51-year-old on it.
WALK_METRES_PER_MINUTE = 80.0

# How far someone will walk to reach transit at either end. Beyond this the walk is
# the journey and transit is not the answer.
MAX_ACCESS_METRES = 900.0

# Changing line costs more than the arithmetic: finding the platform, reading the
# sign, the chance of missing one. Charged per change, on top of waiting.
TRANSFER_PENALTY_MINUTES = 4.0


@dataclass(frozen=True)
class Stop:
    stop_id: str
    name: str
    latitude: float
    longitude: float
    # The `name:en` tag when OSM carries one, which for Taipei Metro is 370 of 437 stop
    # nodes. Kept beside `name` rather than replacing it: a traveller needs the local
    # name for signage and a taxi driver, and the English one to read. Empty when the
    # tag is absent, so a caller can tell "no English name" from "English name equals
    # the local one".
    name_en: str = ""


@dataclass(frozen=True)
class Edge:
    """One hop between adjacent stops on one route."""

    ride_minutes: float
    wait_minutes: float
    route_id: str
    # "timetable" when derived from stated times, "nominal" when from topology and
    # an assumed speed. Carried so a journey can say how much to trust it.
    basis: str


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
    basis: str


def metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a1, o1, a2, o2 = radians(lat1), radians(lon1), radians(lat2), radians(lon2)
    value = sin((a2 - a1) / 2) ** 2 + cos(a1) * cos(a2) * sin((o2 - o1) / 2) ** 2
    return 12_742_000 * asin(sqrt(value))


class TransitGraph:
    """Stops joined by directed per-route edges, with access and egress on foot."""

    def __init__(self, stops: dict[str, Stop], edges: dict[tuple[str, str], Edge]) -> None:
        self.stops = stops
        self.edges = edges
        self._outgoing: dict[str, list[tuple[str, Edge]]] = {}
        for (from_stop, to_stop), edge in edges.items():
            self._outgoing.setdefault(from_stop, []).append((to_stop, edge))

    @property
    def basis(self) -> str:
        """`timetable` only when every edge is; otherwise the weakest present."""

        found = {edge.basis for edge in self.edges.values()}
        return "timetable" if found == {"timetable"} else "nominal"

    def near(self, latitude: float, longitude: float) -> list[tuple[Stop, float]]:
        """Stops within walking reach, nearest first, with their distance."""

        found = [
            (stop, distance)
            for stop in self.stops.values()
            if (distance := metres(latitude, longitude, stop.latitude, stop.longitude))
            <= MAX_ACCESS_METRES
        ]
        found.sort(key=lambda pair: (pair[1], pair[0].stop_id))
        return found

    def journey(
        self, *, origin: tuple[float, float], destination: tuple[float, float]
    ) -> Journey | None:
        """Fastest answer, or None when transit does not help.

        Dijkstra over the stop edges. Waiting is charged on every boarding — the
        first vehicle has to arrive too — and a route change adds the transfer
        penalty on top. State carries the route last boarded, so the same stop is
        reachable twice with different histories and the cheaper one wins.
        """

        access = self.near(*origin)
        egress = {stop.stop_id: distance for stop, distance in self.near(*destination)}
        if not access or not egress:
            return None

        def walk(distance: float) -> float:
            return distance / WALK_METRES_PER_MINUTE

        queue: list[
            tuple[float, str, str, float, float, int, tuple[str, ...], str]
        ] = []
        for stop, distance in access:
            minutes = walk(distance)
            heappush(queue, (minutes, stop.stop_id, "", minutes, 0.0, 0, (), stop.stop_id))
        best: dict[tuple[str, str], float] = {}
        answer: Journey | None = None

        while queue:
            cost, stop_id, boarded, walking, waiting, transfers, routes, first = heappop(queue)
            if answer is not None and cost >= answer.total_minutes:
                break
            if boarded and stop_id in egress:
                # Only an answer once something has been ridden; otherwise this is a
                # walk wearing a journey's clothes.
                total = cost + walk(egress[stop_id])
                candidate = Journey(
                    total_minutes=max(1, round(total)),
                    walking_minutes=max(0, round(walking + walk(egress[stop_id]))),
                    waiting_minutes=max(0, round(waiting)),
                    transfers=transfers,
                    boarded_routes=routes,
                    origin_stop=first,
                    destination_stop=stop_id,
                    basis=self.basis,
                )
                if answer is None or candidate.total_minutes < answer.total_minutes:
                    answer = candidate
                continue
            key = (stop_id, boarded)
            if key in best and best[key] <= cost:
                continue
            best[key] = cost
            for to_stop, edge in self._outgoing.get(stop_id, ()):
                change = edge.route_id != boarded
                wait = edge.wait_minutes if change else 0.0
                penalty = TRANSFER_PENALTY_MINUTES if (change and boarded) else 0.0
                heappush(
                    queue,
                    (
                        cost + edge.ride_minutes + wait + penalty,
                        to_stop,
                        edge.route_id,
                        walking,
                        waiting + wait,
                        transfers + (1 if change and boarded else 0),
                        routes + (edge.route_id,) if change else routes,
                        first,
                    ),
                )
        return answer


# --- building a graph from OpenStreetMap topology -------------------------
#
# `WF-038` chose GTFS, and Taipei's feed turned out to need a Taiwan mobile number
# to obtain. OpenStreetMap needs no account and the app already queries Overpass for
# free, but it publishes *topology* only: a `route=subway` relation lists the
# stations a line joins, in order, and says nothing about when anything runs.
#
# So the ride time is computed from distance and an assumed speed, and the wait from
# an assumed headway. Both are stated here rather than hidden, because they are the
# entire difference in trustworthiness between this and a timetable.

# Metro speed including station dwell. Taipei's MRT averages roughly this once
# stopping time is counted; a fast suburban stretch beats it and a dense downtown
# stretch does not.
METRO_KM_PER_HOUR = 33.0

# Assumed headway. A metro at a five-minute headway means a mean wait of half that.
# Deliberately pessimistic against Taipei's ~2-3 minute peak service, because
# under-stating waiting is what makes a plan miss its own timings.
NOMINAL_HEADWAY_MINUTES = 6.0

# No adjacent-station hop is under a minute once dwell is counted.
MIN_HOP_MINUTES = 2.0

# Only these count as somewhere a person can board. The Overpass query recurses into
# relation members with `>;`, which is what makes the ordered member list resolvable
# -- and which also drags in every node of every track way. Taipei returned 6751
# nodes against 432 edges, so without this filter a place beside a random stretch of
# rail would be handed a walk to "a station" that is a point on a tunnel.
#
# `stop_position` and `platform` stay in deliberately: subway route relations
# generally order *stop positions*, not station nodes, so filtering down to
# `railway=station` alone would leave the relations unresolvable and the graph empty.
STOP_TAGS: tuple[tuple[str, frozenset[str]], ...] = (
    ("railway", frozenset({"station", "halt", "tram_stop"})),
    ("public_transport", frozenset({"station", "stop_position", "platform"})),
    ("station", frozenset({"subway", "light_rail"})),
    ("subway", frozenset({"yes"})),
)


def is_stop(tags: dict) -> bool:
    return any(str(tags.get(key, "")) in values for key, values in STOP_TAGS)


#: How far apart two platform nodes of the *same named* station may sit.
#:
#: A big interchange spreads a long way underground — Shibuya's Fukutoshin platforms are
#: a few hundred metres from its Ginza ones — so this is generous. It is bounded only
#: because a name is not unique: grouping on the name alone would weld together two
#: genuinely different stations that happen to share one, and invent a ride between them.
STATION_GROUP_METRES = 400.0


def _station_name_key(stop: Stop) -> str:
    """What counts as the same station's name. Case and spacing folded; `駅`/`Station`
    dropped, because one operator tags `渋谷` where the next tags `渋谷駅`."""

    name = (stop.name_en or stop.name).strip().lower()
    for suffix in ("station", "駅", "stn"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return "".join(character for character in name if character.isalnum())


def _station_of(stops: dict[str, Stop]) -> dict[str, str]:
    """Map every platform node to the one node standing for its station.

    **The graph had no interchanges at all, and that is why a metro city still walked.**
    A `route=subway` relation lists its own platform nodes, so two lines meeting at one
    station arrive as two unrelated ids with no edge between them. `journey`'s Dijkstra
    already charges `TRANSFER_PENALTY_MINUTES` for a route change and counts the transfer
    — it was simply never offered one, so every answer it could give was a single-line
    ride and everything needing a change came back `None`. Measured on live Overpass for
    Tokyo before this existed: 1489 stops, 2194 edges, **every** successful journey
    reporting `transfers=0`, and Hama-rikyu to Shibuya — 5.6 km across central Tokyo —
    answering "no metro connection", which is what left an 8.5 km walk in the owner's
    plan.

    Merging the nodes is the fix rather than adding transfer edges, because a transfer
    edge would have to spend its walk as `ride_minutes` — invisible to `walking_minutes`,
    which is the number the comfort cap measures, so a leg would pass a walking budget by
    hiding the walk. Sharing one node instead lets the existing penalty mean what it
    already says it means: finding the platform and reading the sign.

    Same normalised name, within `STATION_GROUP_METRES`, single-linkage. Conservative on
    purpose — an interchange whose two halves carry *different* names (Tokyo has several)
    stays unmerged, which loses a connection rather than inventing one.
    """

    groups: dict[str, list[Stop]] = {}
    for stop in stops.values():
        key = _station_name_key(stop)
        if key:
            groups.setdefault(key, []).append(stop)

    canonical = {stop_id: stop_id for stop_id in stops}
    for members in groups.values():
        if len(members) < 2:
            continue
        # Single-linkage within the radius: platforms chain across a long interchange
        # without letting one hop of 400 m become a licence for a kilometre.
        unassigned = sorted(members, key=lambda stop: stop.stop_id)
        while unassigned:
            seed = unassigned.pop(0)
            cluster, frontier = [seed], [seed]
            while frontier:
                current = frontier.pop()
                near = [
                    stop
                    for stop in unassigned
                    if metres(
                        current.latitude, current.longitude, stop.latitude, stop.longitude
                    )
                    <= STATION_GROUP_METRES
                ]
                for stop in near:
                    unassigned.remove(stop)
                    cluster.append(stop)
                    frontier.append(stop)
            for stop in cluster:
                canonical[stop.stop_id] = seed.stop_id
    return canonical


def graph_from_osm(elements: list[dict]) -> TransitGraph:
    """Build a graph from an Overpass answer for subway routes and stations.

    Expects the standard Overpass JSON shape: `node` elements for stations carrying
    `lat`/`lon`, and `relation` elements whose `members` list the stations in order.
    A relation with fewer than two resolvable station members contributes nothing,
    which is the common case for an incomplete line.
    """

    stops: dict[str, Stop] = {}
    for element in elements:
        if element.get("type") != "node":
            continue
        tags = element.get("tags") or {}
        if not is_stop(tags):
            continue  # track geometry, not somewhere anyone boards
        try:
            latitude = float(element["lat"])
            longitude = float(element["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        stop_id = f"n{element['id']}"
        stops[stop_id] = Stop(
            stop_id=stop_id,
            name=str(tags.get("name") or tags.get("name:en") or stop_id),
            latitude=latitude,
            longitude=longitude,
            name_en=str(tags.get("name:en") or "").strip(),
        )

    canonical = _station_of(stops)
    stops = {
        stop_id: stop for stop_id, stop in stops.items() if canonical[stop_id] == stop_id
    }

    edges: dict[tuple[str, str], Edge] = {}
    for element in elements:
        if element.get("type") != "relation":
            continue
        tags = element.get("tags") or {}
        route_id = str(tags.get("ref") or tags.get("name") or element.get("id"))
        ordered = [
            canonical[f"n{member['ref']}"]
            for member in element.get("members") or []
            if member.get("type") == "node" and f"n{member['ref']}" in canonical
        ]
        for left, right in zip(ordered, ordered[1:]):
            if left == right:
                continue
            gap = metres(
                stops[left].latitude, stops[left].longitude,
                stops[right].latitude, stops[right].longitude,
            )
            ride = max(MIN_HOP_MINUTES, (gap / 1000.0) / METRO_KM_PER_HOUR * 60.0)
            edge = Edge(
                ride_minutes=ride,
                wait_minutes=NOMINAL_HEADWAY_MINUTES / 2.0,
                route_id=route_id,
                basis="nominal",
            )
            # A relation lists one direction; a metro runs both. Recording the
            # reverse too avoids a graph where half the city is one-way, which is
            # what happened with the first test feed.
            edges.setdefault((left, right), edge)
            edges.setdefault((right, left), edge)

    return TransitGraph(stops, edges)
