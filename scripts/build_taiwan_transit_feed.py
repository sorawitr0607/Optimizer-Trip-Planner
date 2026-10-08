#!/usr/bin/env python3
"""Build a bounded Taipei regional feed from an extracted TDX national feed.

Includes metro, Taipei–Ruifang/Pingxi rail and buses 849/965, plus their published
service calendars. No fares or shapes. It never claims future timetable coverage.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import zipfile


def rows(root: Path, name: str):
    path = root / name
    if path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            yield from csv.DictReader(handle)


def build(root: Path, target: Path) -> dict[str, int]:
    routes = list(rows(root, "routes.txt"))
    selected_routes = {row["route_id"] for row in routes if row.get("route_type") == "1" or
                       (row.get("route_type") == "3" and (row.get("route_short_name", "").startswith(("849", "965")))) or
                       (row.get("route_type") == "2" and any(word in (row.get("route_long_name", "") + row.get("route_short_name", "")) for word in ("平溪", "Pingxi", "臺北", "台北", "瑞芳", "Taipei", "Ruifang")))}
    trips = [row for row in rows(root, "trips.txt") if row.get("route_id") in selected_routes]
    wanted_trips = {row["trip_id"] for row in trips}
    services = {row["service_id"] for row in trips}
    served = set()
    target.parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    temporary = target.with_suffix(".building.zip")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            def write(name, values):
                import io
                count = 0
                with archive.open(name, "w") as raw, io.TextIOWrapper(raw, encoding="utf-8", newline="") as handle:
                    writer = None
                    for row in values:
                        if writer is None:
                            writer = csv.DictWriter(handle, fieldnames=list(row))
                            writer.writeheader()
                        writer.writerow(row)
                        count += 1
                counts[name] = count
            def times():
                for row in rows(root, "stop_times.txt"):
                    if row.get("trip_id") in wanted_trips:
                        served.add(row["stop_id"])
                        yield row
            write("stop_times.txt", times())
            write("stops.txt", (row for row in rows(root, "stops.txt") if row.get("stop_id") in served))
            write("routes.txt", (row for row in routes if row["route_id"] in selected_routes))
            write("trips.txt", trips)
            write("translations.txt", (row for row in rows(root, "translations.txt") if row.get("language", "").startswith("en") and (row.get("record_id") in served or row.get("record_id") in selected_routes)))
            for name in ("calendar.txt", "calendar_dates.txt", "frequencies.txt"):
                write(name, (row for row in rows(root, name) if row.get("service_id") in services or row.get("trip_id") in wanted_trips))
        if not counts.get("stop_times.txt") or not counts.get("stops.txt"):
            raise ValueError("No usable regional timetable rows")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/gtfs/transit.zip"))
    args = parser.parse_args()
    print(build(args.source, args.output))
