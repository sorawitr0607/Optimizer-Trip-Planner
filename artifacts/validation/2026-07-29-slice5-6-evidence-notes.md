# Slice 5, readiness checklist, live evidence and slice 6 — retained notes

Moved out of ticket 012 so the ticket stays an index. Bundles under `artifacts/validation/` hold each run's manifest.

### Slice 5 and readiness-checklist implementation evidence — 2026-07-29

Detail and retained files live in their validation bundles under `artifacts/validation/`, per the retention rule above. Summary only here:

- Slice 5 built the shared export snapshot, the phone-first active-plan view with hotel and locked anchors and per-half-day fallbacks, the 9:16 poster, the trip PDF, and the six-sheet workbook. Every output reads one snapshot, whose totals must reconcile with the optimizer's own metrics or the export is refused.
- Phone UI gate: [`2026-07-29-slice5-phone-390`](../../artifacts/validation/2026-07-29-slice5-phone-390/manifest.json) — 390-pixel viewport, no sideways scroll.
- Poster/PDF/Excel gate: [`2026-07-29-slice5-pdf-review`](../../artifacts/validation/2026-07-29-slice5-pdf-review/manifest.json) and [`2026-07-29-slice5-excel-recalc`](../../artifacts/validation/2026-07-29-slice5-excel-recalc/manifest.json). Reading the PDF found clipped poster text and raw optimizer codes; both were fixed. The workbook recalculates correctly in Excel and in an independent engine.
- The readiness board generates city-independent tasks, previews additions, removals, and deadline moves, dismisses rather than deletes, and summarizes as Ready, Action needed, or Verification needed without ever gating the itinerary. No provider supplies official entry rules, so an item names what to verify and stays `verification_needed` until the owner records an official source. Generated wording follows the selected language through template codes.
- Checklist gate: [`2026-07-29-checklist-board-390`](../../artifacts/validation/2026-07-29-checklist-board-390/manifest.json).
- Costs are recorded by the owner in their original currency and converted to Thai baht against a sourced, timestamped rate snapshot the owner may edit and buffer. A paid expense locks its actual THB charge, so a later rate cannot rewrite what was spent; a currency with no rate stays a visible gap rather than a guess. The `Costs` sheet carries the agreed columns with split estimated and paid totals, and `Summary` reports both. A provider fare would add rows; it was never required for the sheet to work.
- Still open. Destination-specific requirements, transit-country tasks, and the mandatory 30-day, 7-day, and 24-hour verification runs need official sources no configured provider supplies. `st.map` draws no basemap offline.

### Live evidence implementation evidence — 2026-07-29

The three capability gaps that kept every plan provisional are now closed from real provider evidence, and a live trip reached `Ready` for the first time. Bundles: [`live-walking-routes`](../../artifacts/validation/2026-07-29-live-walking-routes/manifest.json), [`live-destination-timezone`](../../artifacts/validation/2026-07-29-live-destination-timezone/manifest.json), [`live-ready-plan`](../../artifacts/validation/2026-07-29-live-ready-plan/manifest.json).

- The paid ledger came first, because adding provider calls without it would have meant paid calls with no cap. `usage.py` prices each operation, warns at US$8, stops at US$10, and only the owner raises the stop. Free and cached calls are recorded at zero so counts reconcile. Rows are append-only.
- Walking routes come from OpenRouteService, both directions per selected pair, capped at 60 requests with skipped pairs named. An expired leg reports itself stale and the gap returns.
- The destination time zone comes from a coordinate lookup at the discovered coverage centre, never guessed from a country. Any status other than OK is unverified rather than a fallback zone.
- Opening hours come from a licensed live overlay and are reduced to the interval valid on every trip date, which is the only interval a date-less fact can honestly assert. A place closed on a trip date, or with no window common to all dates, produces no verified fact and stays unschedulable rather than being placed into a closed day.
- `provisional` is now derived rather than hardcoded: an approximate arrival or departure, or an unbooked base, keeps a plan provisional as decided.
- Live result on a copy of the live database: 26 provider requests for US$0.13 against the US$10 cap; capability gaps went from three to none; all three variants reached `ready`; the activated plan validated with zero hard violations and its buffer ends exactly at the 12:00 opening interval derived from the provider, so the timetable honours real evidence.
- Real-world data gaps this exposed, honestly reported rather than filled: three of five selected places publish no opening hours at all, and one is closed on a trip date. Only one place could be scheduled. Coverage of opening evidence, not the pipeline, is now the limit.
- Still open. The optimizer's fact model carries no applicable date, so a per-date opening window cannot be expressed and the conservative intersection stands in. Transit routes, fares, crowd and best-time evidence remain unsourced.

### Slice 6 implementation evidence — 2026-07-29

Revision and acceptance, non-AI first as the build order requires, then the one interpretation call. Bundle: [`live-revision-interpretation`](../../artifacts/validation/2026-07-29-live-revision-interpretation/manifest.json).

- [`travel_planner/revision.py`](../../travel_planner/revision.py) holds the whole typed operation set. Every operation is a constraint change on the optimizer input, never a schedule instruction, so nothing in the revision path can write an opening time, route, fare or closure. The deterministic optimizer rebuilds the plan and `consequences()` reports added, removed, moved, shortened and lengthened items, every affected date including cross-day moves, metric deltas, new and cleared warnings, and displaced selections with the optimizer's own reason.
- Exactly one pending preview per trip. `Apply` stays closed unless the rebuilt variant is `ready` and valid, and refuses again if the active plan moved behind the preview. Applying writes a new immutable version plus an append-only history row; restore creates another version and deletes nothing.
- [`travel_planner/interpret.py`](../../travel_planner/interpret.py) builds the strict structured-output schema from the operation set itself, so a model can only choose a supported operation and may name only a `place_id` it was sent. The outbound payload carries the plan slice and the request; a payload holding travellers, documents or credentials is refused before it is sent. One call per request, `store: false`, one retry at most, and each failure names its cause while leaving the plan and history untouched. GenAI is off by default and every other function works without it.
- Verified live in English and Thai. `please cut down the walking on this trip` and `ลดการเดินให้น้อยลง` produced the identical typed operation; `lock harajuku so it cannot move` bound to the real place id; `why is this plan like this?` became `explain`; `make lunch happen between 11:30 and 13:00` carried the exact times; `book me a flight to Paris` came back unsupported with a reason. Eight interpretation calls for about US$0.016.
- Reading the live replies found a defect: the model returned `factor: null` for a request with no magnitude and validation rejected it, so a reasonable request failed. The app now supplies a documented default and shows it as a visible assumption, and asks one clarification where the value is the point of the request.
- Still open. The optional natural-language explanation call is priced and reserved but not wired; only the deterministic `explain` exists. Add, replace and swap operations, and the day/half-day cluster move, are not in the operation set yet.

