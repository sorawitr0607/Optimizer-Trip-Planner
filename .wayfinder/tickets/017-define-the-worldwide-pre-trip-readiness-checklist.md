---
id: WF-017
title: Define the worldwide pre-trip readiness checklist
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-001
assignee: user-and-root
blocked_by:
  - WF-001
  - WF-004
---

# Define the worldwide pre-trip readiness checklist

## Question

What minimum city-independent readiness board turns traveller, passport, destination, transit-country, activity, and booking context into an actionable checklist for entry requirements, immigration/customs forms, money, connectivity, insurance/health, transport setup, reservations, registrations, packing, local rules, and emergency preparation without presenting stale or AI-invented legal advice?

## Confirmed boundary

The user wants post-planning tasks such as visa checks, destination immigration registration, cash exchange, and attraction-specific registration. Phase 1 should include a local checklist with owner, due date, status, evidence link, last-checked time, and trip applicability. Worldwide rules remain generic; destination-specific requirements come from current responsible government or operator sources, and uncertain legal/entry requirements require manual confirmation rather than model guessing.

## Confirmed decisions

- Generate the initial checklist automatically from destination, travel dates, passport nationality, residence when relevant, transit locations, and selected attractions or activities.
- Do not request or store passport numbers in Phase 1.
- Let the user add, edit, dismiss, restore, and complete every generated item. A dismissed generated requirement remains visible in history so it cannot silently disappear.
- Recompute proposed checklist changes when itinerary facts change, but preview additions, removals, and deadline changes before applying them.
- Use one shared trip checklist. Each item has an owner and `applies_to` traveller tags; shared tasks appear once, while the planner creates separate items only when requirements differ between travellers.
- Make timing the primary checklist grouping: `Do now / before booking`, `30 days before`, `7 days before`, `24 hours before`, and `Departure / arrival day`. An exact deadline from an authoritative source overrides these defaults; topic categories remain available as filters.
- Summarize trip readiness as `Ready`, `Action needed`, or `Verification needed`. Incomplete, overdue, uncertain, or stale required items create prominent warnings but never block access to the itinerary or its exports.
- Only responsible government, embassy, immigration, customs, health authority, transport operator, or attraction operator sources may support a `Required` item. Blogs and reviews may provide clearly separated practical tips, never legal or entry requirements.
- Check time-sensitive requirements when the plan is created and again at the trip's 30-day, 7-day, and 24-hour refresh points. Record the official URL and `last_checked_at`; if verification fails or the evidence is ambiguous, retain the item as `Verification needed` and request manual confirmation instead of guessing.
- Generate preparation tasks from selected attractions, transport, accommodation, and other booked or proposed plan components. Each generated item states whether it is `Required`, `Recommended`, or `Optional`, its deadline, and the consequence of skipping it; examples include timed-entry reservations, official apps or accounts, seat bookings, and cash preparation.
- Keep progress states to `To do`, `Waiting`, `Done`, and `Not applicable`; choosing `Not applicable` requires a short reason. Evidence state is separate, so an unfinished item may simultaneously carry a `Verification needed` warning.
- Put the full editable board in a `Trip Readiness` app tab and show its readiness summary on the home page. The PDF contains a short front summary plus a detailed appendix, Excel contains a filterable `Checklist` sheet, and each daily poster shows only tasks needed on that day.
- In Phase 1, show overdue and due-soon tasks whenever the local app opens and provide a one-click `.ics` calendar export. Custom email, LINE, and push notification delivery belongs to the future hosted phase.

## Minimum item contract

Each item records its title, category, requirement level, progress status, owner, applicable travellers, due date or milestone, related trip component, consequence if skipped, source URL and authority type, evidence state, last-checked time, and completion or not-applicable note. The UI may combine these fields visually, but exports preserve them as separate columns.

## Acceptance checks

- Shared tasks are deduplicated, while traveller-specific entry requirements can remain separate.
- Changing destination, transit, travellers, or selected plan components produces a preview of checklist additions, removals, and deadline changes; nothing silently disappears.
- A selected timed or registered attraction produces its supported booking tasks, while an unrelated destination does not receive destination-specific tasks such as Visit Japan Web.
- Missing or stale official evidence produces `Verification needed`, never an invented legal conclusion.
- An incomplete required item changes readiness to `Action needed` without preventing itinerary viewing, PDF/Excel export, or calendar export.
- The app, PDF, Excel, and relevant daily poster expose the agreed checklist information at their appropriate detail levels.

## Resolution summary

Phase 1 includes a city-independent, automatically generated but fully editable trip-readiness board. It combines shared and traveller-specific preparation, official-source evidence, timed refreshes, booking consequences, simple progress states, exportable deadlines, and non-blocking readiness warnings without storing passport numbers or building a custom notification service.
