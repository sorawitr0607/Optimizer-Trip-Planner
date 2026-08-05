# Transit feeds

`WF-038`. Drop a GTFS zip here as `transit.zip`, or point `TOURIST_GTFS_PATH`
somewhere else. `travel_planner/gtfs.py` reads it with the standard library, so
there is nothing to install and no request is made — `refresh_transit_routes` is
free and works offline.

**Taipei is not in the open catalogues.** Checked 2026-08-05: Taiwan's official TDX
platform returns HTTP 401 without a free account, and the MobilityData catalogue
holds nine Taiwan feeds — Changhua, Miaoli, Nantou, Taichung, Yunlin — and none for
Taipei. All 2,146 catalogue objects were scanned.

**TDX is parked by owner decision, 2026-08-05.** Registration needs a Taiwan mobile
phone number; without one it means emailing an identity statement to
`tdx@motc.gov.tw` and waiting for manual approval. Disproportionate for one personal
trip.

So there is no feed here yet, and `refresh_transit_routes` refuses with "GTFS feed
unusable" and writes nothing. The transit code is built, tested and idle — dropping a
zip in is the only step left. `WF-038` lists the routes in that avoid TDX, including
deriving a timetable-free metro graph from OpenStreetMap, which the app already
queries for free.

Feeds are gitignored: they are large, they go stale, and they are not this
repository's to redistribute.

## What the reader needs

`stops.txt` with coordinates, `trips.txt`, and `stop_times.txt`. `routes.txt` is
read for nothing yet. A feed expressing service only through `frequencies.txt`
rather than `stop_times.txt` will load but yield no edges, and says so.
