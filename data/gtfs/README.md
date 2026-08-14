# Transit feeds

`WF-038`. Drop a GTFS zip here as `transit.zip`, or point `TOURIST_GTFS_PATH`
somewhere else. `travel_planner/gtfs.py` reads it with the standard library, so
there is nothing to install and no request is made — `refresh_transit_routes` is
free and works offline.

**Taipei is in no open catalogue**, which is why this needed an account at all. Checked
2026-08-05: MobilityData holds nine Taiwan feeds — Changhua, Miaoli, Nantou, Taichung,
Yunlin — and none for Taipei, across all 2,146 catalogue objects.

**TDX was parked on 2026-08-05 and the owner registered anyway on 2026-08-13**, so
`transit.zip` is now a real feed rather than a missing one.

**It is the metro subset, not the national feed.** TDX's whole-of-Taiwan download is
**7.1 GB extracted** across 402 agencies — and 6.5 GB of that is `fare_leg_rules.txt`
and `fare_products.txt`, which this reader never opens. Of 6,198,885 `stop_times` rows,
**161,612 (2.6%) belong to the five metro operators**: TRTC (Taipei), NTMC (New Taipei),
TYMC (Taoyuan), TMRT (Taichung), KRTC (Kaohsiung). Filtered to those and zipped, the feed
is **3.7 MB** and loads in under a second.

Bus is left out deliberately. It is 97.4% of the file for a planner that schedules
*days*, and a 420 MB feed re-parsed on every server start is a real cost. Rebuilding with
the buses is the same filter without the agency check.

Verified end to end: 捷運西門站 → 捷運台北101/世貿站 resolves to a 25-minute journey,
one transfer, `basis: "timetable"` — the real thing rather than the OSM nominal fallback.

**The feed only helps a Taiwan trip.** Measured coverage: 636 stops within reach of
Taipei 101, **zero** for Busan or Fukuoka. Elsewhere the app falls back to OSM metro
topology, which says so with `basis: "nominal"`.

`/gtfs/` — an extracted download — is gitignored alongside `data/gtfs/*.zip`. Both are
gigabytes of someone else's data and neither is this repository's to redistribute.

## What the reader needs

`stops.txt` with coordinates, `trips.txt`, and `stop_times.txt`. `routes.txt` is
read for nothing yet. A feed expressing service only through `frequencies.txt`
rather than `stop_times.txt` will load but yield no edges, and says so.
