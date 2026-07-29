---
id: WF-001
title: Set the Phase 1 destination and pilot rules
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-001
assignee: user-and-root
blocked_by: []
---

# Set the Phase 1 destination and pilot rules

## Question

What exactly must Phase 1 prove, for whom, and under what product boundaries before implementation starts?

## Resolution comments

### 2026-07-28 — Confirmed through the destination and breadth-first interview

- Plan first, then build and validate Phase 1 after the Wayfinder map is decision-complete.
- Phase 1 is a local functional prototype, not a throwaway demo: live data and strong optimization are required.
- The product is designed for any city, with Taipei as the first validation pilot for 29 December 2026 through 4 January 2027.
- The pilot group is an owner aged 26, a second traveller aged 19, and their mother aged 50. Arrival around 17:00 and departure around 11:00 remain provisional.
- The owner supplies the detailed trip purpose and selects places. Member detail is optional, but every supplied hard constraint is mandatory. Separate member voting is deferred to the future roadmap.
- Free-text profiles become editable preference tags and explicit thresholds. Inferred thresholds must be confirmed before optimization. Age alone never implies fitness.
- Hard constraints override all choices. Soft preferences are balanced, with the owner's trip purpose acting as the tie-breaker among feasible choices.
- The owner profile prefers balanced pacing, sightseeing, culture, local street food, worthwhile landmarks, and rewarding walks; it avoids tourist traps, unrewarding walking, missed opening times, and poor visit timing.
- The 19-year-old profile prefers breathtaking views and impressive attractions, balanced pacing, and rewarding walks; meals should not be late.
- The mother's profile prefers temples, culture, nature, and photography; food detours must justify their travel effort. No physical limitation is inferred from age.
- Normal lunch starts from 11:30 to 13:30 and dinner from 17:30 to 19:30. A deliberately selected special dinner may start from 19:30 to 21:00 with owner confirmation, an earlier snack, and a stated justification.
- New Year countdown attendance is a fixed must-do; the viewing location remains selectable. Its crowd is an accepted exception. Other peak crowds should be avoided or explained, with quieter alternatives and entry/exit plans.
- The trip supports up to three weighted vibes and optional day-level adjustments.
- Attraction selection uses Must do, Interested, Maybe, and Not for this trip. Cards show fit, best time, source-specific ratings/reviews, effort, price, pros, cons, and reliability.
- Discovery retains every candidate returned by configured sources, offers Browse all and manual additions, reports source/category/area coverage, and never claims exhaustive real-world coverage.
- Ratings remain source-specific. Official venue information wins for hours, entry rules, and showtimes. No unapproved scraping is allowed.
- Core paid services may include Google Places, Routes, and Weather, with optional OpenAI text processing. Tabelog is link-only unless permitted integration access is verified.
- Phase 1 API spend is capped at US$10 monthly using quotas and caching. Optimization runs locally and must not call paid APIs inside its search loop.
- The optimizer works across the full trip, may move flexible places between days, and preserves locked activities and reservations. One hotel is preferred; a split stay appears only when its benefit exceeds moving effort.
- It generates Best balance, Relaxed, and More highlights variants, all within confirmed personal thresholds.
- Feasibility is never hidden: Ready, Possible with trade-offs, and Not workable at this time remain visible. Illegal or physically impossible choices cannot be scheduled unchanged.
- Same-day replanning changes only future unlocked items, preserves fixed commitments, and explains every change.
- Strong-optimization acceptance requires no silent hard conflicts, realistic transfer buffers, threshold-compliant effort, time-aware experiences, minimized or explained backtracking, daily fallbacks, score explanations, and regression coverage for prior-trip failures.
- Plan facts refresh when the local app is opened at 30 days, 7 days, and 24 hours before relevant visits. Hosted background alerts are future work.
- Outputs include a local responsive interface, real-photo daily poster, detailed timeline, route map, PDF, and Excel. English/Thai switching covers generated content and exports; Traditional Chinese names and addresses remain visible.
- Data remains local, members may use nicknames, external calls receive only needed fields, secrets never enter exports, and trips can be deleted locally.
- The initial technical direction is Python, Streamlit, and SQLite. Core optimizer/data modules should remain reusable when the interface later becomes a hosted PWA.
