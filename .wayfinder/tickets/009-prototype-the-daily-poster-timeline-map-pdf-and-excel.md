---
id: WF-009
title: Prototype the daily poster, timeline, map, PDF, and Excel
status: closed
labels:
  - "wayfinder:prototype"
parent: WF-MAP-001
assignee: user-and-root
blocked_by:
  - WF-004
  - WF-008
  - WF-017
---

# Prototype the daily poster, timeline, map, PDF, and Excel

## Question

What minimum concrete output makes each day quickly understandable on a phone while preserving detailed time, duration, route, station and exit, effort, cost, source status, warnings, locks, and backups in PDF and Excel?

## Confirmed decisions

- Make the phone's primary working view a compact day summary followed by a scrollable chronological timeline. The summary shows day theme, weather, start/end time, walking load, transport time, and important warnings.
- Alternate activities and travel legs explicitly in the timeline so time spent at a place and time spent reaching it cannot be confused or omitted.
- Provide a map toggle linked to the timeline: selecting an item highlights its place or route.
- Treat the daily poster as an attractive highlight/share/export view, not the primary navigation surface.
- Use progressive disclosure on timeline items. Always show time range, duration, English/Thai and local place names, item type, opening/best-time state, critical warning, and for travel its mode, total duration, walking time/distance, station, and exit. Expand for route steps, transfers, entrance instructions, cost, booking, rating/review context, group-fit reason, sources and freshness, tradeoffs, and backup.
- Limit each daily poster to its date/theme, one main photo, three to five ordered highlights, a simple route line with transport icons, weather, total walking and travel time, one important warning or fallback, and trip/day identity. Minor stops and full operational detail remain in the working timeline and detailed exports.
- Keep personal photo handling permissive: any user-uploaded, pasted, or locally selected image may be used in posters and PDFs without a Phase 1 licence-filtering workflow. Preserve source/credit when supplied, but do not block a personal export for missing metadata.
- Automatic provider retrieval still follows the provider contract. In particular, restricted Google-fetched photos remain attributed live content rather than app-cached export assets; the owner can replace one with a supplied local image for export.
- Structure the PDF as: trip cover and readiness summary; one daily poster followed by that day's detailed timeline and map; selected-but-unscheduled choices with reasons and consequences; the full readiness checklist; and an evidence/source appendix. Never shrink the entire trip timetable onto one primary page or print raw comments as footnotes.
- Export one editable Excel workbook with six sheets: `Summary`, `Timeline`, `Choices & Backups`, `Checklist`, `Costs`, and `Sources`. Use filterable tables, frozen headers, bounded readable columns, and a Summary chart comparing daily walking and travel load; avoid decorative merged timetable layouts.
- In `Timeline`, represent every activity, meal, rest, and travel leg as its own row. Derived totals and cost splits remain formula-driven where practical, and separate columns preserve route, effort, warnings, locks, evidence, and source freshness.
- Let the app switch between English and Thai. Posters and PDFs use the currently selected interface language, while every place, station, exit, and entrance may retain its local-script name underneath. Excel preserves separate English, Thai, and local-name columns.
- Use Thai baht as the primary display and reporting currency. Every destination expense also preserves and may display its original amount and ISO currency, including different currencies in a multi-country or transit itinerary.
- Convert estimates using a sourced, timestamped exchange-rate snapshot that the owner may edit or buffer. Once paid, retain the original amount and lock the actual THB charge rather than rewriting it with later rates. Excel preserves original amount/currency, applied rate/date, converted THB, and actual THB where known.
- Give each day an overview map whose numbered stops match the timeline. Mark the hotel and locked anchors, distinguish modes by labelled colour/icon, show distance and time for every walking leg, and distinguish evidence-supported sightseeing walks from plain transfers.
- Selecting a map leg exposes its station, exit, entrance, transfer, and route details. The PDF carries a clean day overview; exact turn-by-turn navigation stays in the app or opens in an external map.
- Use text plus colour/icon for five output states: `Confirmed`, `Recheck`, `Tradeoff accepted`, `Unverified / conflict`, and `Locked`. Unverified or conflicting required facts prevent a `Ready` label. Day summaries surface the highest-risk items, while detailed cards and exports retain the explanation, consequence, source, and refresh date.
- Compare `Best balance`, `Relaxed`, and `More highlights` inside the app using walking, travel, highlights, meal timing, warnings, and tradeoffs. After the owner selects an active plan, posters, PDF, and Excel export only that plan; another variant is exported as its own separate file only on request.
- Keep the primary timeline clean and attach each weather/closure fallback beneath its affected half-day. Show the activation reason, latest decision time, replacement items, and changes to route, cost, walking, meals, and displaced selections. Activating it reruns the remaining day through the optimizer rather than swapping names in place.
- Treat PDF and Excel as offline snapshots: embed addresses, local names, station/exit/entrance instructions, and critical warnings as text rather than relying on links. Retain map, booking, and source links as shortcuts. Stamp every export with active plan/version, export time, language, base currency, and last evidence refresh; the app warns when an older export no longer matches the active plan.

## Concrete phone prototype

```text
Day/date/theme                         Timeline | Map
Weather · start-end · visit/travel/walk totals · readiness

09:00-10:20  [Visit] Place name / local name       Confirmed
              80 min · best-time note · key warning
       ↓
10:20-10:45  [Subway] A → B                         Recheck
              25 min · walk 6 min / 420 m · Exit 2
       ↓
10:45-12:00  [Visit] Next place                     Locked

Fallback for this half-day · trigger · decide by · View changes
```

The visible card remains compact; tapping it reveals the approved detailed fields. Map numbers use the same item order, and changing Timeline/Map does not lose the selected item.

## Minimum shared output fields

- Snapshot: trip and active-plan identifiers, plan version, selected variant, language, base currency, export time, and evidence-refresh time.
- Day: local date, theme, weather/risk, start/end, visit/travel/walking totals, rewarding versus plain walking, meal-window state, readiness, and highest warning.
- Timeline item: stable ID, order, type, start/end/duration, names in available languages, address/coordinates, status, lock, cost, booking state, warnings, and related source IDs.
- Visit/meal/rest detail: opening/last-entry/best-time state, visit-duration bounds, entrance/access, group-fit reason, rating/review context, meal window, reservation, and consequence.
- Travel detail: origin/destination, mode, duration/distance, walking portion, sightseeing-walk evidence, line/service, stations/stops, transfer, platform/exit/entrance, fare, and route evidence.
- Fallback/reconciliation: trigger, decision deadline, replacement, changed metrics, selection fit state, reason, consequence, and smallest supported alternative.

## Excel sheet contract

- `Summary`: trip, travellers, hotel/base, active plan/version, readiness, daily effort/travel KPIs and chart, estimated/paid THB totals, and exchange-rate snapshot.
- `Timeline`: the normalized active-plan rows and all operational fields needed offline.
- `Choices & Backups`: `Fits`, `Fits with tradeoff`, and `Cannot currently fit` reconciliation plus linked fallbacks, reasons, consequences, and alternatives.
- `Checklist`: the readiness-board contract from its closed ticket.
- `Costs`: original amount/currency, estimate or actual, rate/date, converted/actual THB, category, payer/share, payment state, and related plan item.
- `Sources`: evidence ID, governed field, provider/authority, URL, language, retrieved/valid dates, confidence/status, licence/export state, and last checked time.

## Acceptance checks

- At a 390-pixel phone width, the day summary and timeline require no horizontal scrolling; essential activity and transport facts remain visible without expansion.
- Every visit, meal, rest, buffer, and travel leg appears once in chronological order. Item durations and daily totals reconcile with the optimizer result.
- Every walking leg contributes to the displayed load, and only named/evidenced sightseeing walks receive experience value.
- Map stop numbering, timeline ordering, hotel/locked anchors, modes, and leg metrics agree exactly.
- The five status labels, warnings, source freshness, locks, and fallback state agree across app, poster, PDF, and Excel; colour is never the only signal.
- A 9:16 PNG poster remains readable and contains only the confirmed poster fields. Missing imagery does not suppress operational information.
- PDF pages remain legible at normal zoom, keep each day together as a section, contain no raw-comment overflow page, and retain offline-critical text.
- Excel contains only the active plan, has the six agreed sheets, filterable/frozen data tables, readable bounded widths, working formulas, reconciled cost totals, and no obvious formula errors.
- Switching English/Thai or exporting local-script names does not change identities, times, routes, status, or costs. Estimated and actual currency conversions follow the confirmed rules.
- An old snapshot remains openable but is labelled stale in the app after the active plan changes; no accepted-plan movement disappears between versions.

## Resolution summary

Phase 1 uses a phone-first day summary and explicit activity/leg timeline connected to a numbered map, plus a concise daily poster and detailed offline PDF/Excel snapshots. The outputs preserve operational route, effort, timing, cost, evidence, warning, lock, fallback, language, currency, readiness, and reconciliation detail without reproducing the dense, fragile all-trip spreadsheet layout.
