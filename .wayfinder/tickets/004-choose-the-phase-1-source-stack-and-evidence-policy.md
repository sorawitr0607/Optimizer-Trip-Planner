---
id: WF-004
title: Choose the Phase 1 source stack and evidence policy
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-001
assignee: user-and-root
blocked_by:
  - WF-002
  - WF-003
  - WF-015
---

# Choose the Phase 1 source stack and evidence policy

## Question

Given verified availability, costs, field limits, attribution rules, and countdown evidence gaps, which sources should Phase 1 use for each fact, how should conflicts be resolved, and what confidence and refresh states must users see?

## Resolution comments

### 2026-07-28 — Use an open official base with narrow licensed overlays

**Decision:** Phase 1 uses durable official/open Taipei data as its local catalog, enriches only visible or selected candidates with paid Google data, and keeps provider-restricted review/photo content out of durable exports. Operational facts remain evidence-bearing records with explicit confidence and refresh state.

#### Source roles

- **Taipei Travel Open API and Taiwan TDX Tourism V2** form the durable local attraction, restaurant, hotel, event, and transport catalog. Store permitted fields with agency attribution and preserve the source URL, provider ID, retrieval time, applicable date, and licence.
- **Responsible official sources**—venue pages, Taipei City, Taipei Metro and other transport operators, event organizers, and Taiwan's Central Weather Administration—control holiday hours, access, showtimes, closures, legal transport rules, countdown operations, and Taiwan weather/warnings.
- **Google Places** expands discovery gaps and supplies current business status, hours, source-specific ratings, limited reviews, and photos only for visible or selected cards. Use narrow field masks and required attribution; persist stable place IDs, not unrestricted provider content.
- **Google Routes** supplies transit/walking detail and route costs only for shortlisted itinerary stops and likely useful edges. Never build route matrices across the full discovered catalog or call paid APIs inside the optimizer search loop.
- **Google Weather** is a fallback when official CWA products do not cover a required structured field or when the product later expands beyond Taiwan.
- **OpenAI API** is optional for owner-text tag extraction, English/Thai translation, and summaries of user-authored or open-licensed content. Do not send Google, Tripadvisor, Tabelog, or other restricted review text to a model without explicit permission.
- **Tripadvisor and Tabelog** remain clearly labelled outbound references in Phase 1. Direct integration, caching, translation, AI summarization, or combined ranking requires separately verified written permission. Their ratings are never blended with Google or official-source signals.
- Tourist recommendations may contribute candidates when their reuse terms permit it, but they never override current operational facts.

#### Evidence and conflict policy

Every time-sensitive fact displays one of these states:

- `Official confirmed`: current applicable evidence from the responsible authority or operator.
- `Current provider`: a current licensed API result with retrieval time and attribution.
- `Regular schedule only`: normal hours or service exist, but the trip date's exception is not yet verified.
- `Historical only`: prior-year or climate evidence informs risk, not the current instruction.
- `Conflicting`: material sources disagree; retain both and require recheck or owner acknowledgement.
- `Unconfirmed`: no current reliable evidence supports the claim.

For operational conflicts, the newest applicable event-year notice from the responsible official source wins over official open-data snapshots, which win over current licensed-provider data, which wins over reviews or guides. Preserve the losing evidence and explain the conflict; never silently overwrite it. Ratings remain source-specific rather than averaged.

#### Refresh, export, and cost policy

- Refresh at plan creation and the confirmed 30-day, 7-day, and 24-hour gates, plus an owner-triggered same-day refresh. A future date outside a provider's special-hours or forecast window remains `Regular schedule only` or `Unconfirmed`.
- The live interface may show licensed Google content only with required branding, attribution, author/source links, and Google-map rules.
- Excel, PDF, and real-photo posters use owner content or content whose licence permits durable reuse. Restricted reviews/photos remain live links or attributed UI overlays until export permission is established.
- Stay below the US$10 monthly ceiling through staged enrichment, narrow field requests, sparse route edges, hard provider quotas, restricted keys, a local cost ledger, and graceful fallback to permitted open data and manual verification.

### 2026-07-28 — Reopened after correcting worldwide scope

The user rejected the Taiwan-first base as inconsistent with the destination. Taipei Travel and TDX may enrich the Taipei pilot, but the core candidate, place, route, weather, evidence, optimizer, and export contracts must work in a city with no dedicated local API. The ticket remains open pending global-provider research and a corrected decision.

### 2026-07-28 — Confirmed worldwide core with optional destination enrichment

**Decision:** Phase 1 has one city-independent source pipeline. OpenStreetMap supplies the durable place base, openrouteservice supplies export-safe non-transit routes, and Open-Meteo supplies weather. Google is a narrowly called live overlay for selected-place quality, current details, maps, and transit where supported. Official destination sources such as Taipei Travel and TDX are optional evidence enrichments, not APIs that a user must configure for every city.

- Starting a trip in a new city never requires writing or configuring a city-specific adapter.
- With no local adapter, discovery, ranking, non-transit routing, weather, optimization, and export must still work from the worldwide core.
- A configured local adapter can add candidates or raise confidence in operational facts through the same source-neutral evidence records; it cannot add optimizer-required fields or change the core ranking contract.
- Missing worldwide transit or operational evidence is shown as unavailable or unverified, with an external/manual check where useful. The planner never invents a subway route or silently treats normal hours as holiday confirmation.
- Ratings stay provider-specific. Restricted Google reviews, photos, and route content stay in the attributed live interface; durable Excel, PDF, poster, and optimizer data use export-permitted sources.
- Paid calls remain outside optimizer search loops and behind staged enrichment, hard quotas, a local usage ledger, and graceful open/manual fallback under the US$10 monthly ceiling.
- Taipei is the deep pilot. A later non-Taiwan, no-local-adapter smoke test validates that the worldwide contract actually works; it does not claim exhaustive global coverage.
