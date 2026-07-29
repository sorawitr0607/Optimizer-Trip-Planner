---
id: WF-MAP-001
title: Plan the personalized travel itinerary tool
status: closed
labels:
  - "wayfinder:map"
tracker: local-markdown
---

# Plan the personalized travel itinerary tool

## Destination

Reach a decision-complete, implementation-ready specification for a local Phase 1 personalized itinerary planner, validated against a Taipei New Year pilot and accompanied by a staged future-development roadmap. Implementation begins only after this map has no unresolved decisions.

## Notes

- Domain: owner-led, group-aware personal travel planning with live evidence, cross-day route optimization, resilient replanning, and multilingual exports.
- Pilot: Taipei, 29 December 2026 through 4 January 2027; three travellers aged 26, 19, and 50; provisional 17:00 arrival and 11:00 departure.
- Phase 1 target: local Python and Streamlit app with SQLite, paid API usage capped at US$10 monthly, English/Thai UI, and Traditional Chinese place details.
- Taipei is the full pilot, not a source-architecture boundary: the core planner must still run for a city that has no dedicated local tourism adapter.
- Users configure one worldwide provider stack, not a different API for every city; local official adapters are optional improvements only.
- Consult Wayfinder and Grilling for decision work; consult Spreadsheets before workbook inspection or Excel output work.
- Refer to tickets by linked title, never by a bare ID.

## Decisions so far

<!-- Closed-ticket index. The detailed decision belongs in its ticket. -->

- [Set the Phase 1 destination and pilot rules](tickets/001-set-phase-1-destination-and-pilot-rules.md) — Phase 1 is a local, owner-led Taipei prototype with live evidence, strong cross-day optimization, resilient replanning, multilingual outputs, and explicit future phases.
- [Verify permitted live travel data and cost limits](tickets/002-verify-permitted-live-travel-data-and-cost-limits.md) — A US$10 personal prototype is viable only with staged enrichment, sparse route matrices, hard quotas, export-permitted durable data, and licensed provider content treated as a constrained live overlay rather than freely cached or merged.
- [Establish Taipei New Year countdown evidence and refresh timing](tickets/003-establish-taipei-countdown-evidence-and-refresh-timing.md) — Treat the announced City Hall-area countdown as the anchor, while leaving all viewing, access, transit, closure, program, and weather details unconfirmed until mandatory 30-day, 7-day, and 24-hour evidence refreshes.
- [Verify a worldwide core and local enrichment model](tickets/015-verify-a-worldwide-core-and-local-enrichment-model.md) — Use an export-safe worldwide open-data base, add Google only as a constrained live overlay, and let destination-specific official adapters improve evidence without becoming required for planning.
- [Choose the Phase 1 source stack and evidence policy](tickets/004-choose-the-phase-1-source-stack-and-evidence-policy.md) — Configure one worldwide source pipeline for every city, keep local official APIs optional, expose unavailable evidence honestly, and reserve restricted provider content for its permitted live context.
- [Provision approved Phase 1 data access](tickets/014-provision-approved-phase-1-data-access.md) — The reusable worldwide provider keys, redacted live checks, key restrictions, conservative quotas, and budget alerts are configured; no destination-specific credential is required.
- [Define trustworthy attraction coverage and card ranking](tickets/005-define-trustworthy-attraction-coverage-and-card-ranking.md) — Discover broadly before personalizing, expose coverage gaps, preserve every candidate in Browse All, and use explainable group-fit, effort, timing, and route scores with protected landmarks, exploration, and tradeoff choices.
- [Prototype the owner-led setup and confirmation flow](tickets/007-prototype-the-owner-led-setup-and-confirmation-flow.md) — Use a bilingual five-step setup with Explore-first and Ready-to-schedule modes, tag-first personalization, compact reusable traveller cards, explicit non-negotiables, provisional planning before bookings, and confirmed impact previews for later changes.
- [Define the strong cross-day optimization contract](tickets/006-define-the-strong-cross-day-optimization-contract.md) — Solve the whole trip with city-independent hard constraints and ordered priorities, quantify all tradeoffs, preserve accepted-plan stability, and require deterministic validity, route, fallback, and historical-regression gates.
- [Make reference workbook inspection available](tickets/013-make-reference-workbook-inspection-available.md) — User-exported timetable PDFs now provide a verified, read-only visual inspection path for all four reference trips without modifying the source workbooks.
- [Define the worldwide pre-trip readiness checklist](tickets/017-define-the-worldwide-pre-trip-readiness-checklist.md) — Generate an editable shared checklist from trip and traveller context, ground required items in current official evidence, show deadlines and consequences across app/PDF/Excel/calendar outputs, and warn without locking the itinerary.
- [Inspect the reference itinerary workbooks](tickets/008-inspect-the-reference-itinerary-workbooks.md) — Preserve their useful timetable, transit, cost, checklist, packing, images, and detailed notes while replacing free-text facts, unreadable print layouts, and stale copied templates with structured, evidence-aware outputs and regression requirements.
- [Prototype the daily poster, timeline, map, PDF, and Excel](tickets/009-prototype-the-daily-poster-timeline-map-pdf-and-excel.md) — Use a phone-first day summary and activity/leg timeline linked to a numbered map, then export only the active plan as concise daily posters and detailed, versioned, offline-readable PDF and Excel snapshots.
- [Choose the minimal Phase 1 architecture and data contracts](tickets/011-choose-the-minimal-phase-1-architecture-and-data-contracts.md) — Build one reproducible local Streamlit application around a language-neutral planning core, SQLite truth, provider-neutral evidence, immutable versions, environment-only secrets, a pure deterministic optimizer, and snapshot-only exporters.
- [Turn historic trip failures into regression fixtures](tickets/010-turn-historic-trip-failures-into-regression-fixtures.md) — Protect all 20 reported mistakes with provider-independent atomic fixtures plus seven bounded interaction cases, one worldwide rule registry, and an executable structural validator.
- [Define the constrained GenAI plan revision assistant](tickets/016-define-the-constrained-genai-plan-revision-assistant.md) — Convert optional bilingual free text into typed intents, verify affected evidence, rerun the deterministic optimizer, preview every consequence, and let only the owner apply or restore versioned changes while non-AI controls remain available.
- [Lock the validation scorecard and implementation handoff](tickets/012-lock-the-validation-scorecard-and-implementation-handoff.md) — Separate an implementation-ready specification from a proven working MVP, retain reproducible validation bundles, and build six minimal vertical slices before certifying every hard runtime gate on the Taipei pilot.

## Intentionally deferred beyond Phase 1

- Exact sequencing for a hosted PWA, remote member voting, broader worldwide validation, and production polish. These are future roadmap candidates, not POC dependencies.
- Operational monitoring and background notifications for a hosted product; the local prototype can refresh only while running.

## Implementation-time evidence, not unresolved decisions

- The exact Taipei candidate set and generated seven-day itinerary must come from current source evidence, owner choices, and the implemented optimizer.
- Final countdown viewing, access, closure, transit, crowd, program, and weather instructions remain provisional until their mandatory evidence refreshes.
- Provider facts, ratings, reviews, photos, routes, exchange rates, costs, and legal/travel requirements must be rechecked according to their source and validity windows.

## Out of scope

- Treating this closed decision map as proof that the not-yet-built POC has passed runtime validation.
- Purchasing flights, accommodation, tickets, reservations, or paid subscriptions on the user's behalf.
- Claiming exhaustive real-world attraction coverage or guaranteed correctness for facts that no configured source can verify.
- Implementing future hosted and global phases during the Phase 1 build; their roadmap remains part of the destination.

## Resolution

All 17 decision tickets are closed. The specification is implementation-ready, the historic regression catalog validates, and the final project graph passes its integrity checks. Phase 1 may now be built in the order defined by the implementation handoff. The project becomes a `working MVP` only after the app exists and every applicable hard scorecard gate passes with retained evidence.
