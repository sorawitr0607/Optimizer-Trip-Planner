---
id: WF-007
title: Prototype the owner-led setup and confirmation flow
status: closed
labels:
  - "wayfinder:prototype"
parent: WF-MAP-001
assignee: user-and-root
blocked_by: []
---

# Prototype the owner-led setup and confirmation flow

## Question

Does a concrete local interface let the owner describe the trip and optional members, review extracted tags and thresholds, choose weighted vibes, and set hard constraints without confusion or unnecessary input?

## Confirmed setup structure

Use five short, editable steps rather than one long form:

1. Trip basics and planning certainty.
2. Owner's trip purpose, style, pace, likes, and dislikes.
3. Travellers and their optional consideration notes.
4. Hard constraints, bookings, budget, meal timing, walking limits, and must-do places.
5. Review extracted values, assumptions, conflicts, and warnings before confirmation.

Attraction discovery begins only after the relevant setup review is confirmed, avoiding irrelevant place and route enrichment calls. The optional one-time GenAI tag extraction may run only when explicitly requested through `Analyse and continue` and remains subject to the shared paid-API budget. The owner can return to any setup step; a later change produces a visible impact preview before replacing an existing discovery result or plan.

## Planning-certainty modes

- `Explore first`: only the destination is required. Exact dates, duration, flights, arrival/departure times, and accommodation may remain unknown while the owner sets preferences and browses attractions.
- `Ready to schedule`: use known or approximate dates, duration, daily availability, transport bookings, and accommodation information to proceed toward a dated itinerary.
- Exploring without dates may produce attraction choices and rough geographic/day clusters, but these remain visibly `Not schedule-ready`; the tool must not present unverified date-specific hours, events, weather, or transport as final.
- After attraction choices exist, recommend `Minimum stay`, `Balanced stay` (default recommendation), and `Relaxed stay`. Each option shows what fits, what does not fit, expected daily effort, and pros/cons.
- When the owner later supplies dates or changes duration, refresh affected time-sensitive evidence and rerun the whole-trip optimizer before producing or updating the exact timetable.

## Timetable readiness before booking

- Permit a `Provisional timetable` before transport or accommodation is booked. Require a destination, travel date range or start date plus duration, approximate usable arrival/departure-day windows, confirmed owner preferences and traveller count, and all currently known fixed bookings or must-do constraints.
- An unknown flight or train is represented by owner-approved conservative first/last-day availability assumptions, never a fabricated arrival or departure.
- When accommodation is unbooked, use the optimizer's recommended hotel area as a visible provisional base; do not pretend that a specific hotel is selected.
- Adding or changing booked transport or accommodation later produces an impact preview, refreshes affected evidence and routes, and reruns the whole-trip optimizer.
- Distinguish `Explore only`, `Provisional timetable`, and `Validated active plan` so estimates are useful for choosing bookings without appearing final.

## Owner preference input

- Begin with predefined, city-independent tags grouped as `Main style`, `Also enjoy`, `Avoid`, and `Comfort needs`. Require at least one `Main style` tag so the trip always has a clear owner-led purpose.
- Follow the tags with an optional description box labelled as extra detail, examples, or nuance—not a request to repeat the selections.
- Extract structured details only when the owner chooses `Analyse and continue`, never on every keystroke. Manual tag selection remains usable when GenAI is disabled or unavailable.
- Merge manual and extracted values using stable taxonomy IDs and synonym normalization, so equivalent wording is deduplicated rather than shown as separate tags.
- Explicit manual tags take priority over inferred tags. Show contradictions for owner confirmation instead of silently choosing one interpretation.
- Preserve useful description detail that cannot safely map to a supported tag as a visible note; do not invent a new optimizer threshold from it.
- Use understandable priority groups rather than requiring numeric preference sliders. Internal weights and member thresholds remain inspectable in the final review.

## Traveller input

- The owner's confirmed tags and description define the main trip style.
- Each additional traveller uses a compact card: nickname or label, age, optional preference tags, optional short description, and explicit walking, accessibility, dietary, meal-time, or rest needs.
- Do not require members to complete an owner-sized profile; extra member detail remains optional and can be added later.
- Never infer interests, fitness, walking tolerance, pace, or food preferences from age. Age may support age-dependent ticket/readiness facts or prompt the owner to confirm a relevant comfort setting.
- Traveller preferences influence group-fit scores and editable soft thresholds; only items explicitly confirmed under `Must respect` become hard optimizer constraints.

## Preference and hard-constraint boundary

- Treat owner and traveller tags, descriptions, dislikes, comfort wishes, and derived thresholds as optimizer preferences by default; do not make the owner classify every item by strength.
- Put only genuine non-negotiable requirements in a separate `Must respect` section, including fixed bookings, confirmed accessibility limits, allergies or dietary prohibitions, and explicit maximum/minimum limits.
- If text contains language such as `must`, `cannot`, or an equivalent Thai phrase, propose the item for `Must respect` but require explicit owner confirmation before it becomes hard.
- Opening hours, access rules, routes, closures, and similar operational facts belong to the evidence layer, not the preference form.
- When preferences conflict, use the already confirmed group-fit weights and person-specific thresholds; expose the resulting tradeoff in discovery and plan previews rather than making the setup form repeat optimizer decisions.

## Interpretation review

- Before discovery or schedule generation, summarize the interpreted pace, maximum day length, rewarding-walk and plain-walk tolerance, daily and continuous walking comfort, meal windows and exceptions, rest needs, and `Must respect` constraints.
- Show the origin of each value as manual tag, description extraction, explicit constraint, or planner default.
- Keep the default view readable and expose actual threshold values under `Edit details`; every value remains editable before confirmation.
- When the setup lacks enough information, propose a clearly labelled city-independent default for owner acceptance or editing. Never derive it from age.
- Surface duplicate normalization, unresolved text notes, and contradictions on this review. Do not begin attraction enrichment or optimization while a material contradiction or unconfirmed proposed hard constraint remains.

## Reusable local traveller cards

- Save owner-approved traveller cards locally for reuse across trips without an account or cloud profile.
- A reusable card may retain nickname, normal comfort settings, dietary/accessibility needs, and optional general preferences.
- For each new trip, the owner chooses which saved travellers are joining, reconfirms age for the travel dates, and reviews reused information before it affects discovery or optimization.
- Do not automatically carry forward a previous trip's purpose, vibe, must-do places, temporary preferences, bookings, or accepted tradeoff exceptions.

## Optional trip budget input

- A trip may proceed without a budget. In that case, estimate supported costs and show tradeoffs, but never reject a candidate merely because it is expensive.
- When setting a budget, record the amount and original currency, whether it applies to the whole group or per traveller, and whether it includes flights, accommodation, and/or local-trip spending.
- Display and report the converted value primarily in Thai baht while retaining the entered currency under the agreed exchange-rate rules.
- Treat a `Target budget` as a soft optimizer preference. Only `Must not exceed`, explicitly confirmed under `Must respect`, becomes a hard limit.
- Unknown or unsupported costs remain visible gaps and cannot be treated as zero when validating a hard maximum.

## Known places and bookings

- Let the owner add flights, trains, accommodation, restaurants, events, and attractions through minimal structured fields or a pasted reference link.
- Use three understandable states: `Interested` for discovery consideration, `Must do` for highest scheduling priority with movable day/time, and `Booked / fixed` for a locked confirmed date, time, and location.
- Missing required booking fields create a visible warning and prevent a supposedly fixed item from being treated as fully verified.
- Keep document upload, email parsing, and automatic booking-account import in the future roadmap; Phase 1 retains only owner-entered structured details, notes, and links.

## Editing setup after planning

- Save cosmetic changes such as nickname, label, or interface language immediately when they do not alter any planner input.
- Treat changes to dates, duration, travellers, preferences, thresholds, budget, bookings, accommodation, or constraints as one pending revision using the already-defined revision/versioning flow.
- Before recalculation, show the likely affected attraction ranking, hotel area, scheduled days, costs, readiness checklist, evidence, paid refreshes, and active exports.
- Keep the active setup and plan unchanged until a valid recalculated preview is available and the owner presses `Apply`.
- A newly entered real-world booking that conflicts with the active plan raises an immediate prominent warning even while its replacement plan remains pending.

## Local draft and resume behaviour

- Autosave each completed setup step locally as a `Draft setup`; autosave itself performs no paid API call.
- The trip list shows the last completed step and resumes there while still allowing any earlier step to be edited.
- Allow multiple named trip drafts and require confirmation before deleting one.
- Keep `Draft setup`, `Explore only`, `Provisional timetable`, and `Validated active plan` visually distinct so an unfinished setup cannot be mistaken for an itinerary.

## Concrete bilingual text prototype

The actual interface shows one selected language at a time. Both labels are shown here to make the English/Thai contract explicit; switching language preserves stable IDs and entered values.

```text
[EN | ไทย]                         Draft saved locally / บันทึกร่างแล้ว

New trip / ทริปใหม่                                      Step 1 of 5
How far are you in planning? / ตอนนี้วางแผนถึงขั้นไหนแล้ว?
(•) Explore first / สำรวจก่อน
( ) Ready to schedule / พร้อมจัดตาราง

Destination / จุดหมาย            [ Taipei / 臺北市             ]
Dates / วันที่                     [ Not decided / ยังไม่กำหนด   ]
Trip length / จำนวนวัน            [ Recommend after choices      ]
Arrival and departure / ไป-กลับ   [ Unknown / ยังไม่ทราบ         ]
Accommodation / ที่พัก             [ Not booked / ยังไม่ได้จอง     ]
                                             [Save & continue / บันทึกและไปต่อ]
```

```text
Your trip style / สไตล์ทริปของคุณ                         Step 2 of 5
Main style / สไตล์หลัก — choose at least one
[Sightseeing ✓] [Culture ✓] [Nature] [Activity] [Shopping] [Chill]

Also enjoy / ชอบเพิ่มเติม
[Local street food ✓] [Photography] [Night view] [Markets]

Avoid / อยากหลีกเลี่ยง
[Tourist traps ✓] [Plain long walks ✓] [Crowds] [Late meals]

Comfort / ความสะดวก
[Balanced pace ✓] [Rewarding walks are OK ✓] [More rests]

Add details, examples, or exceptions / เพิ่มรายละเอียดหรือตัวอย่าง
[ Walking is fine when the route has worthwhile sights...                 ]
                                      [Analyse & continue / วิเคราะห์และไปต่อ]
```

```text
Travellers / ผู้ร่วมทริป                                  Step 3 of 5
[Owner, age 26 — main trip style]
[Traveller, age 19 — optional preferences and needs]
[Mother, age 50 — optional preferences and needs]
[Reuse saved traveller / ใช้ผู้ร่วมทริปที่บันทึกไว้]  [+ Add traveller / เพิ่มคน]
```

```text
Requirements / ข้อกำหนด                                  Step 4 of 5
Must respect / ข้อจำเป็นที่ต้องทำตาม       [None confirmed]
Known places and bookings / สถานที่และการจอง
[Interested] [Must do] [Booked / fixed]                  [+ Add]
Budget / งบประมาณ                          [Not set — optional]
                                               [Continue / ไปต่อ]
```

```text
Review / ตรวจสอบ                                           Step 5 of 5
Planning state: Explore only / สำรวจเท่านั้น
Trip purpose: Sightseeing + culture
Walking: balanced; reduce unrewarding transfers           [Edit details]
Meals: preferred window; special-dinner exception         [Edit details]
Travellers: 3; no ability inferred from age                [Review]
Must respect: none                                         [Review]

Assumptions and defaults / สมมติฐานและค่าเริ่มต้น          2 to review
Conflicts / ข้อมูลขัดแย้ง                                  None
Warnings / คำเตือน                                         Dates still unknown

                         [Confirm & explore attractions / ยืนยันและดูสถานที่]
```

For `Ready to schedule`, Step 1 exposes the date range, duration, approximate first/last-day availability, transport status, and accommodation status. Step 5 then labels the result `Provisional timetable` until dated evidence and all deterministic validity gates pass.

## Acceptance checks

- `Explore first` can complete with only a destination and at least one owner main-style tag; dates, duration, transport, and accommodation remain optional and no final timetable is implied.
- `Ready to schedule` accepts approximate first/last-day windows and an unbooked hotel, producing a clearly provisional base and timetable rather than blocking planning or fabricating bookings.
- After attraction selection, Minimum, Balanced, and Relaxed duration choices expose included and excluded selections, expected effort, and pros/cons before the owner chooses a stay length.
- Manual tags appear before the optional description. Extraction occurs only on explicit action, deduplicates synonyms by stable ID, preserves manual priority, and requires contradictions or proposed hard constraints to be resolved.
- The complete setup remains usable without GenAI through predefined tags and manual fields.
- Adding a traveller requires no detailed profile; age alone changes no interest, mobility, meal, or pace setting.
- Only owner-confirmed `Must respect` items become hard constraints. Operational facts remain evidence records, and missing hard-cost evidence is never treated as zero.
- Interested, Must do, and Booked/fixed items retain their distinct optimizer meanings and incomplete booking details remain visibly unverified.
- Optional budgets preserve group/per-person scope, included categories, original currency, THB conversion, and soft-target versus hard-maximum meaning.
- Every completed step resumes from a local draft without an autosave-triggered paid call; deleting a draft requires confirmation.
- Switching English/Thai preserves every stable tag, traveller, booking, threshold, and trip value.
- A planning-relevant edit after discovery or scheduling creates an impact/recalculation preview and cannot silently replace the active plan.
- The Taipei pilot can represent three travellers, approximate 17:00 arrival and 11:00 departure, unbooked accommodation, the confirmed preference profiles, and a fixed New Year anchor without a Taiwan-specific setup field.
- A different worldwide destination with no local adapter can complete the same setup and reach discovery while local evidence gaps remain explicit.

## Resolution summary

Phase 1 uses a five-step, bilingual, locally resumable setup with two certainty modes. Structured tags lead, optional text adds deduplicated nuance, the owner defines the main trip style, compact member cards adjust comfort without age stereotypes, and only confirmed non-negotiables become hard constraints. Unknown dates, duration, flights, or hotels do not block exploration; duration choices and provisional schedules remain transparent until dated evidence and validation make the plan active.
