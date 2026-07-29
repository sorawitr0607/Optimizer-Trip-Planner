---
id: WF-008
title: Inspect the reference itinerary workbooks
status: closed
labels:
  - "wayfinder:task"
parent: WF-MAP-001
assignee: user-and-root
blocked_by:
  - WF-013
---

# Inspect the reference itinerary workbooks

## Question

Inspect all four workbooks in `data/reference-itineraries/` with the required spreadsheet workflow, recording their sheets, timetable fields, visual patterns, useful content, and every structure implicated by the reported trip failures so later output and regression decisions use the actual examples rather than guesses.

The required spreadsheet runtime was unavailable during map charting; resolving that access is part of this prerequisite task.

## Inspected source set

All four `.xlsx` files and the user-provided timetable PDF exports in `data/reference-itineraries/` were inspected read-only. The PDFs cover six rendered pages: Japan and Kunming use two pages each; Fukuoka and Shanghai use one page each.

## Sheet inventory

| Workbook | Sheets | Useful structure |
| --- | --- | --- |
| Japan | `ตารางเวลา`, `Transport`, `ค่าใช้จ่าย`, `♢ To-Do List`, `☺ Things to Bring` | Six-day timetable; a separate detailed transport table with passes, routes, modes, line/station codes, intermediate stops, platforms, and approximate times; planned costs; booking tasks; document, packing, and shopping lists. |
| Fukuoka | `ตารางเวลา`, `ค่าใช้จ่าย`, `♢ To-Do List`, `☺ Things to Bring` | Four-day timetable integrating time range, activity, mode, origin, destination, and notes; planned/per-person costs; to-do and packing templates. |
| Kunming | `ตารางเวลา`, `ค่าใช้จ่าย`, `☺ Things to Bring` | Five-day timetable with time range, activity, mode, and notes; planned costs plus an actual expense ledger; packing and shopping template; no dedicated to-do sheet. |
| Shanghai | `ตารางเวลา`, `Disney`, `ค่าใช้จ่าย`, `♢ To-Do List`, `☺ Things to Bring` | Five-day timetable integrating route fields; a separate detailed Disney day with timed activities, transport, advice, and prohibited-item notes; split/per-person/paid costs; to-do and packing templates. |

## Visual and data patterns

- Dates and day themes create strong visual sections. Attraction, meal, and long-transfer rows use background colours, while photos and occasional maps provide quick context.
- Fukuoka and Shanghai have the strongest timetable schema: `time`, `activity`, `mode`, `from`, `to`, and `notes`. Japan holds richer transit detail in a separate sheet; Kunming usually records only the mode.
- Operational notes such as station codes, exits, platforms, passes, airport meeting points, conditional cuts, ticket advice, and local-language names are valuable and must be preserved.
- Hyperlinks are plentiful in Japan, Fukuoka, and Shanghai, but they are untyped links to a mixture of official sites, maps, restaurants, videos, social posts, and reviews. They have no authority label, fact association, or last-checked time. Kunming's timetable has no hyperlinks.
- Time values are heterogeneous: Excel time fractions and date serials are mixed with multiple free-text formats. Some rows contain several places or actions, so neither duration nor opening/access validity can be checked per place.
- The PDF presentation compresses an entire trip and a large image rail into one main page, making the timetable too small. Japan prints comment URLs on an otherwise blank second page, and Kunming spills final rows onto a second page. Evidence links and comments must not become uncontrolled print footnotes.
- Checklist sheets use unexplained `0/1` values and copied templates. Fukuoka's to-do list still names Shanghai, Disney, Chinese apps, and immigration; its packing sheet still says China Migration and UnionPay. Kunming has no to-do sheet. This directly supports context-generated checklist items instead of destination copies.

## Failure-to-structure trace

| Reported failure | Structure that allowed it |
| --- | --- |
| Japan: Uniqlo was closed on arrival | Uniqlo is embedded inside the 21:00 multi-place Asakusa row, with no separate place identity, opening interval, last-entry check, or closed-arrival warning. |
| Japan: day-two walking was too long; MAGNET was not open; Shibuya Sky was poorly timed | Multiple Shibuya/Harajuku stops share rows; walking is free text without cumulative distance, effort, or route rewards; opening and best-viewing windows are not structured facts. |
| Japan: teamLab to Odaiba was too far and the train view had little value after dark | The timetable records only a transfer start, while the detailed transport sheet leaves part of the connection incomplete; there is no door-to-door walking load, daylight/view window, or route-value field. |
| Japan: rain left no last-day alternative | There is no linked weather-sensitive half-day cluster, activation condition, or verified indoor fallback. |
| Fukuoka: Hakata Old Town felt empty and yatai felt touristy | Candidate quality, crowd/tourist-trap risk, evidence confidence, and personalized consequence are absent; both appear as fixed schedule text. |
| Fukuoka: Hakata Port was too much when tired | `If tired, cut Hakata Port` exists only as a note after an already long day, not as a fatigue threshold, optional priority, or automatic replan rule. |
| Fukuoka: the expected Canal City fountain show was unavailable at the actual late time | A calendar link and fixed timetable slot exist, but show type, exact valid interval, last useful arrival, source freshness, and delay consequence are not structured. |
| Kunming: Yunnan University lacked entry and walking detail | It is a single place row with no gate, access rule, entrance landmark, internal route, or ordered highlights. |
| Kunming: the Dali hotel caused backtracking | Hotel location and repeated returns are schedule text rather than a whole-trip base-location cost considered before booking. |
| Kunming: the Erhai scooter route prohibited scooters and became a hot, tiring bicycle day | `Scooter` is assumed as the mode on several legs without permission evidence, route capability, heat exposure, physical-load estimate, or verified alternative. |
| Shanghai: New Sukiyaki had an excessive queue | The meal row has no reservation/queue evidence, crowd threshold, wait budget, or nearby backup. |
| Shanghai: Yuyuan felt like a tourist trap and Wukang was reached after its attractive light | Tourist-trap/crowd consequence, daylight, sunset, and best-viewing window are not inputs to ordering. |
| Shanghai: the ferry was crowded and its entrance was hard to find | Pier names and a map link exist, but the row lacks a verified entrance point, approach path, landmark/photo instruction, operating evidence, and crowd/boarding buffer. |

## Requirements handed downstream

- Keep the useful day themes, colour hierarchy, photos, operational notes, local names, transit detail, costs, checklist, and attraction-specific subplans.
- Normalize each visit, meal, rest, transfer, and fallback into its own time-bounded item; preserve `from`, `to`, mode, route duration, walking load, station/exit/entrance detail, and evidence separately.
- Attach opening, last-entry, show, reservation, access, crowd, best-time, weather, and route facts to the exact item they govern, including source authority and freshness.
- Make plain walking, rewarding sightseeing walking, total daily effort, meal timing, optional cuts, and fallback activation visible rather than burying them in notes.
- Preserve every selected place in the fit reconciliation, including the reason and consequence when it cannot fit safely or comfortably.
- Do not compress the primary PDF into one unreadable all-trip page or print raw comments as footnotes. Test a daily mobile/poster view, daily PDF pages, and a detailed appendix/Excel representation.
- Generate destination- and selection-aware readiness tasks; never reuse a stale destination template silently.

## Resolution summary

The four references contain valuable timetable, transit, cost, checklist, packing, visual, and attraction-specific content, but their free-text rows and copied templates cannot validate the facts that caused the reported failures. Later output, regression, and architecture work now has a concrete preservation list, defect list, field boundary, and failure mapping grounded in the actual files.
