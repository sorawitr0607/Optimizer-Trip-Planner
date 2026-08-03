---
id: WF-032
title: Prototype the itinerary day screen in the new design
status: closed
labels:
  - "wayfinder:prototype"
parent: WF-MAP-002
assignee: user-and-root
blocked_by:
  - WF-025
  - WF-028
---

# Prototype the itinerary day screen in the new design

## Question

What does the active plan's day view look like in the Auto-Bill visual language — day summary, activity and
leg timeline, numbered map, and variant or version context — when Auto-Bill has no element resembling any of
them?

## Context

The second highest-risk screen, and the one the owner looks at most during the trip. Throwaway prototype; the
question is arrangement and legibility, not code.

- What exists today: `views/itinerary.py` renders a phone-first day summary, an activity-and-leg timeline, and
  a numbered map, all read from `build_export_snapshot()` so the screen and the exports cannot disagree. The
  poster is 9:16 by decision, so the phone layout and the poster already share a shape worth reusing.
- The optimizer returns three variants — `best_balance`, `relaxed`, `more_highlights` — each independently
  revalidated, and with no trip dates it returns a stay recommendation instead of a timetable. The screen must
  handle both, plus the labelled-valid-incumbent case when the solver hits its time limit.
- Plans are append-only: `active_plans` holds exactly one version per trip, restoring an old plan creates a new
  version, and `revision.py` keeps at most one pending draft while showing before-and-after consequences. Some
  of that history and preview context belongs on or beside this screen.
- Auto-Bill's nearest elements are the hero banner, stat cards, and list rows — none of which is a timeline or
  a map. Note that the hero banner has **no** `3 / 1` aspect ratio: its README claims one, but `aspect-ratio`
  appears nowhere. The real rule is a locked `260px` height with `minmax(320px, 34%) minmax(0, 1fr)` columns
  (`index.css:460-484`). Port the fixed height, not a ratio.
- The element inventory found the numbered map to be the **one** planner element the Auto-Bill visual language
  cannot reach — it has no spatial primitive, no map dependency, and no analogous visual anywhere. So this
  prototype also has to answer what draws the map, and the offline asset policy ticket has to answer whether
  its tiles can exist on a plane. Marker colours are duplicated as text labels today for accessibility; that
  is a load-bearing behaviour, not decoration. The Not-yet-specified list already flags that new elements must be
  designed inside the existing visual rules rather than imported from elsewhere.
- Status labels carry emoji in the current UI, and `_labels()` strips pictographs on the export path because no
  Unicode font covers them; the wording alone must still carry the state. The same constraint applies to any
  status chip designed here.

Produce a throwaway prototype and link it from this ticket, along with what was rejected.

## Resolution comments

### 2026-08-03 — Prototyped, revised once, accepted

Prototype: [`032-day-screen-prototype.html`](../artifacts/032-day-screen-prototype.html) — one self-contained
file, EN/TH, light/dark, phone width, a no-dates toggle and a China toggle. Throwaway per the map, so nothing
landed in `web/`.

**The row model is six types, not the three the element inventory described.** `visit`, `travel`, `buffer`, and
a trio — `meal` / `preparation` / `logistics` — that share one renderer (`ui/shared.py:468`–`530`), plus
bordered `fallback` blocks interleaved per half-day.

**Eight calls were put up, and six drew changes.** Recording what was reacted against, per the ticket:

1. **The type rail was too weak to read.** 4px was not enough to tell a category apart at a glance. Now a
   **10px rail, a matching background wash, and a type label on every row** — three channels for type. Status
   still lives only in words, because exports strip pictographs.
2. **The timeline had gaps, and detail was wanted.** It did: 11:30–12:00, 13:15–14:00, 16:30–17:00, and the
   whole evening were missing. Now **every minute from 07:30 to 22:00 is drawn** — the implied travel legs and
   buffers are explicit, each half-day header states its span, and an unscheduled evening block is shown rather
   than omitted. Verified continuous: 14 rows, no gaps. Details were also deepened — metro line names, fares,
   distances, transfer counts, queue allowances, verified-hours dates, the ranking weights, and why a warned row
   is still shown.
3. **Text was too small.** Enlarged throughout: body 15→16px, clock 11.5→13px with the duration on its own
   line, titles 13.5→15px, captions and details 11.5→13px, chips 9.5→11px.
4. Details collapsed by default — kept, with one row opened as a demonstration.
5. Fallback inline after the rows it affects — kept.
6. **The header should be `3/1`.** Applied. Worth recording precisely: the donor's CSS has a locked `260px` and
   **no `aspect-ratio` anywhere** — `3/1` is what its README claims — so this deviates from the donor's *code*
   toward its *documentation*. Registered as **D10** in
   [`025-visual-parity-gate.md`](../artifacts/025-visual-parity-gate.md); the column rule is unchanged.
7. **Variants should look like buttons.** They are real buttons now, with a working pressed state.
8. **A map was wanted.** Built as a **coordinate plot with no tiles** — stops at true relative geometry,
   longitude scaled by `cos(25.04°)` so nothing is distorted, route in visit order, scale bar. It makes the
   useful fact immediate: stops 1 and 2 are 70 m apart while Taipei 101 is 6.5 km east. **Accepted, so
   `Decide the offline asset policy for the webapp` is NOT reopened** — the plot honours all three of its
   grounds: no network, no tile licence, and Pillow can draw the same figure so the PDF and poster match.

**One addition beyond the eight: outbound map links.** Every stop links out, and the whole day links as a
transit route. This follows a pattern the planner already uses — it redirects to TripAdvisor and Wikimedia
Commons rather than faking richer content — so it extends existing behaviour rather than adding a dependency,
and it covers the want-real-streets case by handing off to an app that already has them, offline caches
included.

> **Two traps the implementation must not walk into**, both surfaced while building this and easy to get wrong:
> **Amap takes longitude first** (`position=lon,lat`), the reverse of Google's `query=lat,lon`; and **Amap
> expects GCJ-02 while our coordinates are WGS-84** from OpenStreetMap, so handing them over unconverted lands
> the pin **100–500 m away** — the wrong block in a dense city. Only **mainland China** switches provider;
> Taiwan and Hong Kong keep Google Maps, and all three are in `destinations.COUNTRIES`.

**Rejected while building**, as the ticket asks:

- **A proportional time-axis timeline.** Reads well on desktop, collapses on a phone, and makes a 15-minute
  buffer nearly invisible while a 150-minute stop wastes space.
- **Colour-coding status on the rail as well as type.** Two meanings on one channel, and it would have made
  the type distinction unreadable on exactly the rows that matter most.
- **Tabs for morning / afternoon.** The donor has no tab element at all — its four `*-tab-view` classes carry
  no styling — and hiding half a day defeats a screen you check while walking.
- **A per-row map thumbnail.** No tiles ship, so it would have been an empty box.
- **Emoji status chips.** Exports strip pictographs, so the chip would vanish in the PDF.

Fidelity limits recorded on the page: **Plus Jakarta Sans and JetBrains Mono are substituted by a system
stack**, since the woff2 files are not in the repo yet (`WF-034`) and the artifact runtime blocks font CDNs; and
fares, queue times and the evening suggestion are plausible placeholders rather than provider data.
