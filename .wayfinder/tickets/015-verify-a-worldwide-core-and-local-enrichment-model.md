---
id: WF-015
title: Verify a worldwide core and local enrichment model
status: closed
labels:
  - "wayfinder:research"
parent: WF-MAP-001
assignee: /root/global_source_research
blocked_by:
  - WF-002
---

# Verify a worldwide core and local enrichment model

## Question

Which currently supported global place, route, transit, weather, map, and multilingual evidence providers can form a city-independent Phase 1 core within the US$10 personal ceiling; what coverage and licensing gaps remain; and how can optional official local sources such as Taipei Travel and TDX enrich a destination without becoming required for the planner to function?

## Resolution comments

Resolved 2026-07-28.

### Recommendation: worldwide open base, licensed live overlay

Phase 1 should use one city-independent contract and this minimum stack:

| Need | Worldwide core | Required behavior |
| --- | --- | --- |
| Durable places | OpenStreetMap POIs through [bounded Overpass queries](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html) or a replaceable OSM provider | Store source IDs, local names, coordinates, categories, licence, and retrieval time. OSM is global but uneven and not exhaustive. Public Nominatim is only for low-volume user-triggered lookup: its [usage policy](https://operations.osmfoundation.org/policies/nominatim/) forbids autocomplete and downloading all POIs in an area. |
| Current place quality | Google Places, requested only for visible or shortlisted candidates | Use narrow field masks for status, hours, rating, review count, and at most the provider-returned review sample. Store Google Place IDs, not a local Google catalog. Ratings and reviews remain Google-labelled live evidence. |
| Export-safe route costs | openrouteservice for walking, cycling, wheelchair, and driving matrices/routes | Its service [covers the globe](https://openrouteservice.org/services/), the Standard plan is [free with daily limits](https://account.heigit.org/info/plans), and API results are CC BY 4.0 with required attribution under its [terms](https://openrouteservice.org/terms-of-service/). It has no public-transit mode. |
| Public transit | Google Routes as a live capability where available; official/local transport data as enrichment | Transit is not universal. Google says Routes supports its transit partners except Japan and Indian Railways in its [Maps FAQ](https://developers.google.com/maps/faq#directions_countries), while its coverage table explicitly omits transit coverage. Missing transit must produce `Transit unavailable/unverified`, not an invented subway route. |
| Weather | Open-Meteo primary; responsible national weather authority optional enrichment | The free endpoint is for non-commercial use, up to 10,000 calls/day with no SLA; data are CC BY 4.0 with attribution under its [pricing](https://open-meteo.com/en/pricing) and [licence](https://open-meteo.com/en/license). It supplies global forecasts up to 16 days. Google Weather is an optional fallback, not required. |
| Interactive map | Google Maps JavaScript when Google Places or Routes content is shown | Google Places/Routes content must not be placed on a non-Google map. An OSM-map fallback may exist only as a separate Google-free mode; public OSM tiles are best-effort, require attribution/caching, and prohibit prefetch/offline use under the [tile policy](https://operations.osmfoundation.org/policies/tiles/). |
| English/Thai/local language | App-owned English/Thai UI plus preserved local-script names; provider localization only for live provider fields | Google Place Details accepts `languageCode`, but may fall back or return mixed language, per its [localization rules](https://developers.google.com/maps/documentation/places/web-service/place-details#optional-parameters). Mark provider-translated reviews as translated. Translate only user-authored or open-licensed text; do not send restricted Google reviews to another AI. |

Every candidate and operational fact uses the same source-neutral records: local ID, provider ID, field/value, source URL, authority type, retrieved time, valid date range, language, licence/export permission, and confidence state. Ratings remain separate records per provider. A local adapter may add records but cannot introduce fields the optimizer requires or change the core ranking formula.

### Material limits

- There is no provider that guarantees every attraction, complete ratings/reviews, live crowds, queues, entrance instructions, holiday hours, showtimes, or legal local transport rules worldwide. Google current opening hours cover only the next seven days, as documented in the [Place resource](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places#Place.FIELDS.current_opening_hours). Those facts still need a responsible official source or explicit manual verification.
- Google is a live overlay, not the durable/export base. Its current [Terms](https://cloud.google.com/maps-platform/terms#3.-license.) prohibit storing business names, addresses, reviews, route results, creating content from Google Maps content, and exporting that content outside the service; Places/Routes policies generally allow stable IDs and only stated temporary caching exceptions. Excel, PDF, posters, and durable optimizer inputs must therefore use owner-authored, OSM/openrouteservice/Open-Meteo, or separately permitted official/local data. Google content stays in the attributed live UI or links. A broader use requires written permission/legal confirmation.
- OSM is reusable under ODbL with attribution and database share-alike duties; exports must follow the [OSM copyright and attribution requirements](https://www.openstreetmap.org/copyright). Open data can still be stale or sparse. openrouteservice walking/cycling results require a safety warning and cannot substitute for official accessibility, closure, or vehicle rules.
- Transit is the largest global gap. If Google transit is absent and no local official feed/adapter exists, Phase 1 can optimize walking/driving with openrouteservice and offer an external/manual transit check, but it cannot claim a verified subway itinerary.

### US$10 ceiling

Expected personal Phase 1 provider cost is US$0 while use remains inside the current free caps. Google currently includes 10,000 monthly Dynamic Maps and Routes Essentials events, 5,000 Places Pro searches/details, and 1,000 Enterprise/Atmosphere details or photos; rates and caps are in the official [pricing table](https://developers.google.com/maps/billing-and-pricing/pricing). Keep the US$10 ceiling with provider quotas below those caps, restricted keys, a local usage ledger, staged details, sparse route edges, and no paid calls inside the optimizer loop. Billing alerts are not the stop mechanism; the app must stop enrichment and fall back to open/manual evidence before its quota.

### Optional local enrichment

Taipei Travel and TDX can add official candidates, Traditional Chinese names, events, transport/disruption facts, and exportable operational evidence through the same records. They may raise confidence and fill transit gaps for Taipei, but disabling both must not break discovery, ranking, optimization, weather, or export. The same rule applies to future city/country adapters.

### Required second smoke test

After Taipei, test a **three-day/two-night non-Taiwan city with no local adapter**, chosen later by the user. Select a city with a different language/script and currency, meaningful public transit, one timed reservation, one crowded landmark, one weak-transit edge, one weather replacement, and one venue whose official information conflicts with a provider. The test passes only if the app generates and replans the trip, exposes missing transit/operational evidence honestly, preserves local names, and produces English/Thai Excel/PDF using only export-permitted data. This validates worldwide architecture without pretending one second city proves worldwide coverage.
