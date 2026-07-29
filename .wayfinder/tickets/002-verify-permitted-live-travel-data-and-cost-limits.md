---
id: WF-002
title: Verify permitted live travel data and cost limits
status: closed
labels:
  - "wayfinder:research"
parent: WF-MAP-001
assignee: /root/api_source_research
blocked_by: []
---

# Verify permitted live travel data and cost limits

## Question

Which official APIs and permitted sources can Phase 1 use for place discovery, opening hours, ratings, reviews, photos, routes, transit, weather, translation, and operational evidence within a US$10 monthly ceiling, and what material gaps or usage restrictions remain?

## Resolution comments

Resolved 2026-07-28.

### Viable official sources

- **Google Maps Platform** can supply place discovery, identifiers, names/types, business status, opening hours, ratings, up to five relevance-sorted reviews, up to ten photo references, routes, transit routing, and short-range weather. Billing depends on the highest-cost field requested, so discovery and details should be separate calls with narrow field masks. In the current [Places field tiers](https://developers.google.com/maps/documentation/places/web-service/data-fields), hours and ratings are Enterprise fields; reviews are Enterprise + Atmosphere fields. The [Place resource](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places) does not expose supported popular-times, live crowd, or queue fields.
- **Tripadvisor Content API** officially covers hotels, restaurants, and attractions through search/nearby/details endpoints and returns up to five recent reviews and five photos per location. Its [overview](https://tripadvisor-content-api.readme.io/reference/overview) says a newer Terra API is forthcoming, so future availability and migration remain uncertain.
- **Taipei Travel Open API** provides official multilingual attractions, events, news, tours, themes, audio, and media from Taipei City; its endpoints are documented in the [official Swagger interface](https://www.travel.taipei/open-api/swagger/ui/index). The related [Taipei open-data licence](https://data.taipei/rule) permits reproduction and derivative use with source-agency attribution. Image rights must still be checked separately because the [Taipei Travel site](https://www.travel.taipei/en/) reserves photographer copyrights.
- **Taiwan TDX Tourism V2** offers authenticated official attractions, restaurants, hotels, service sites, trails, cycling routes, and events through the [Tourism V2 catalogue](https://tdx.transportdata.tw/api-service/swagger/tourism/0aed433a-9e95-404d-974c-4e70e29ae460). Tourism calls are marked as not consuming metered points. TDX also has transport and disruption data. Its [membership information](https://tdx.transportdata.tw/) states that guests receive 20 basic calls/day and registered basic members about 3,000 point-counted calls/month; applicants without a Taiwan phone may require manual email verification. Use V2 because Tourism V1 was [retired on 2025-12-31](https://tdx.transportdata.tw/news/detail/e2eb3999-d58d-4a8c-a7ed-218e7636520a).
- **Official venue and operator pages** are the authoritative layer for holiday hours, entrance instructions, closures, reservations, showtimes, legal bike/scooter rules, and New Year crowd routing. Taipei Metro publishes service updates in [web/RSS/XML/JSON formats](https://english.metro.taipei/cp.aspx?n=7CD020ABBEA76F02). These operational notices may arrive only days before an event, so the product needs dated verification checkpoints rather than treating early planning data as final.
- **OpenAI API is optional**, suitable for extracting tags or translating/summarising user-authored text and open-licensed official data. Current model prices are listed on the [official model page](https://developers.openai.com/api/docs/models). API content is not used for training by default, although standard abuse-monitoring retention can apply; use `store: false`, minimise personal data, and follow the [endpoint data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint). Do not send provider reviews into a model unless that provider licence explicitly permits it.

### Cost-cap implications

The US$10/month ceiling is feasible for a small personal proof of concept only with strict quotas, staged enrichment, and a local cost ledger. Under current [Google Maps global pricing](https://developers.google.com/maps/billing-and-pricing/pricing), representative monthly free caps include: 10,000 Dynamic Maps, Static Maps, Routes Essentials, Places Autocomplete, Geocoding, Place Details Essentials, and Weather calls; 5,000 Nearby Search Pro, Text Search Pro, and Place Details Pro calls; and 1,000 Place Details Enterprise, Enterprise + Atmosphere, and Place Photos calls. Overage rates differ sharply: Routes Essentials and Place Details Essentials are US$5/1,000, Text/Nearby Search Pro US$32/1,000, Enterprise Details US$20/1,000, Atmosphere US$25/1,000, and Photos US$7/1,000. A billing account and restricted API key are still required.

Route-matrix billing is per returned origin-destination element, not per HTTP request. For example, 50 candidates × 50 candidates × 2 modes creates 5,000 elements; three complete refreshes create 15,000, costing about US$25 after the 10,000-element free cap. Downstream design should therefore enrich only shortlisted places, compute sparse adjacent/likely route edges, reuse results only for the permitted period, and avoid all-pairs optimisation.

Tripadvisor’s [FAQ](https://tripadvisor-content-api.readme.io/reference/faq) gives 5,000 calls/month free, requires a card and daily budget, and returns HTTP 429 when that budget is reached; pay-as-you-go prices beyond the allowance are visible during signup/account management rather than in a stable public table. Google Cloud budget alerts do **not** stop spend; Google advises using quotas and key restrictions in its [cost-control guidance](https://developers.google.com/maps/billing-and-pricing/manage-costs). OpenAI supports project/organisation spend limits, but enforcement can lag slightly. The application must reserve headroom across all providers and degrade to open data, cached permitted identifiers, and manual verification when a cap is reached.

### Legal/caching/attribution constraints

- Google [Places policies](https://developers.google.com/maps/documentation/places/web-service/policies) generally prohibit prefetching, caching, or storing Places content except stated exceptions. Place IDs may be stored indefinitely and should be refreshed if older than 12 months. Current service terms allow Places/Routes latitude-longitude caching for up to 30 days. Google content requires Google Maps attribution; reviews/photos require author attribution and source links. Places shown on a map must use a Google map, not a non-Google map. Google AI summaries must retain supplied disclosure, links, and wording. Durable Excel/poster exports containing Google reviews, photos, or other provider content therefore need a specific compliance check rather than being assumed permitted.
- Tripadvisor’s [caching policy](https://tripadvisor-content-api.readme.io/reference/caching-policy) allows only `location_id` to be cached; other attributes cannot be stored or indexed. Its [display rules](https://tripadvisor-content-api.readme.io/reference/display-requirements) require branding, attribution, and links. Its [master terms](https://tripadvisor-content-api.readme.io/reference/api-master-terms-new) restrict AI/ML use, combining Tripadvisor licensed content with third-party user-generated content, altering Tripadvisor rankings, and selective review display. Consequently, AI review summaries, translated Tripadvisor reviews, and a merged Google/Tripadvisor review-ranking card are not supported under the standard terms without separate written permission.
- No current official public Tabelog developer API or signup documentation was established. Tabelog’s [official terms](https://tabelog.com/help/rules/) prohibit unauthorised reproduction, storage, translation/adaptation, and reuse of reviews. Treat it only as an outbound/manual reference unless Kakaku grants explicit access; it is also Japan-focused, not a primary Taipei source.
- Persist source URL, provider ID, retrieval timestamp, applicable date window, licence, and verification status for every operational fact. Keep provider-specific ratings separate; never present unlike scales or samples as one blended rating.

### Unsupported gaps

No verified source guarantees exhaustive attraction coverage. Google and Tripadvisor expose only small review samples, not a representative corpus. There is no supported live popular-times/queue field. Google special opening hours cover only today plus six days; Weather API forecasts reach only about ten days. Exact 2027 countdown exits, closures, transport extensions, and crowd controls will likely be published near the event. Entrance details, temporary closures, ticket availability, showtimes, and legal cycling restrictions remain fragmented across unstructured official pages. Photos may carry separate copyright even when metadata is open. Automated scraping of venue, Google, Tripadvisor, or Tabelog pages is not an approved fallback.

### Facts downstream must decide

The source-choice ticket must select which licensed provider, if any, is worth integrating; allocate the shared US$10 cap by SKU/provider; define shortlist and route-matrix sizes; choose which fields remain live overlays versus locally stored open data; and define 30-day, 7-day, 24-hour, and same-day rechecks. It must also decide an export policy for reviews/photos, a fallback when credentials or quotas fail, and whether Tripadvisor’s restrictions make it unsuitable for the planned personalised ranking flow. These are product choices; the evidence above does not select a provider.
