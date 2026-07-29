---
id: WF-016
title: Define the constrained GenAI plan revision assistant
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-001
assignee: user-and-root
blocked_by:
  - WF-006
  - WF-009
---

# Define the constrained GenAI plan revision assistant

## Question

What minimum post-plan AI interaction lets the owner request natural-language changes, receive useful suggestions and explanations in English or Thai, compare consequences, accept or undo revisions, and replan safely while leaving live facts, hard constraints, route calculations, and final schedule validity under deterministic evidence and optimizer control?

## Confirmed boundary

The user wants a GenAI section after plan generation for fixing and revising the itinerary. GenAI interprets requests and explains alternatives; it never invents place facts or directly overwrites the itinerary. Every proposal becomes structured constraint changes, is validated against evidence, reruns the cross-day optimizer, and displays a before/after consequence preview before the owner accepts it.

## Confirmed decisions

### 2026-07-28 — AI proposes; verified systems and the owner control changes

- A revision request is converted into structured intent and constraint changes; GenAI output is never accepted as an opening time, route, fare, closure, reservation rule, or other operational fact.
- Current evidence providers verify affected facts and the deterministic optimizer rebuilds the cross-day schedule.
- Before applying anything, show the original and proposed plan plus moved, added, shortened, or removed places and all travel, walking, meal, cost, confidence, and member-comfort consequences.
- The owner chooses `Apply`, `Edit request`, or `Cancel`; every applied revision has undo. The saved plan is never overwritten directly by model text.
- The minimal interface is one revision box, useful quick actions, a consequence preview, and undo—not an autonomous multi-agent chat system.

## Current implementation evidence

- Use the OpenAI Responses API with a strict function/Structured Outputs schema for revision interpretation. The model returns typed intent operations; application code validates them before any evidence refresh or optimizer run.
- Keep provider facts, route computation, plan mutation, and final validation outside model-generated text. A refusal, schema/parse failure, unavailable API, or unsupported intent leaves the active plan unchanged.

## Supported Phase 1 intents

- Add, remove, or replace a place.
- Move a place or swap day/half-day clusters across the trip.
- Reduce walking, transfers, crowds, or daily load.
- Adjust supported visit duration or meal timing.
- Activate a weather/closure fallback.
- Lock or unlock an item with explicit confirmation.
- Reconsider an unbooked hotel area; a booked hotel remains locked unless the owner deliberately unlocks it.
- Fully re-optimize the trip.
- Explain the current plan, a warning, a rejection, or a consequence without changing anything.

Requests outside this typed operation set produce one focused clarification or an unsupported-request explanation; they never become arbitrary schedule instructions.

## Clarification boundary

- Proceed directly when the requested intent and target are clear.
- When a small non-material assumption is safe, include that assumption visibly in the consequence preview rather than interrupting the owner.
- Ask one short clarification only when different interpretations would materially change days, locks, bookings, hard constraints, group comfort, or cost.
- If the request is infeasible, show the binding constraint and nearest supported alternatives instead of asking repeated questions.

## Evidence refresh boundary

- Reuse evidence that remains valid for the affected trip date and refresh only the places, routes, dates, and operational facts touched by the proposed intent.
- Query responsible official or free sources first; use paid providers only when needed, allowed, and within the existing quota/budget policy. Never re-enrich the full city for an isolated revision.
- If a required opening, access, route, booking, or other hard fact cannot be verified, return an inspectable draft with the exact gap. Do not enable `Apply as active plan` until deterministic validation succeeds or the owner supplies acceptable confirming evidence.

## AI call boundary

- Quick actions map directly to typed operations and require no model call.
- A free-text request normally uses one model call to interpret the request into strict structured intent. Evidence refresh, optimization, validation, metrics, and the consequence table are application work.
- A second model call occurs only when the owner explicitly requests a natural-language explanation or continues the free-text conversation. Never spend a second call merely to restate the deterministic change set.

## Contextual quick actions

Show only actions relevant to the selected day, place, warning, or route. Every action first produces the same consequence preview as a free-text revision; none changes the active plan immediately.

- `Make this day easier`: reduce the day's load, preserve locked/must-do places, add rest, or move a lower-priority stop to a better day.
- `Reduce walking`: reorder nearby stops, use supported transit/taxi, or offer a nearby replacement, while showing the time and cost tradeoff.
- `Avoid crowds`: use available evidence to suggest a better time or alternative; never claim live crowd conditions without live evidence.
- `Fix meal timing`: move meals into the group's preferred windows and rebuild surrounding activities and travel.
- `Replace this place`: suggest similar nearby choices with fit, route, evidence, and pros/cons; never silently discard the original selection.
- `Use weather backup`: activate the prepared half-day fallback and rerun its transport, meal, and timing details.
- `Fully re-optimize`: rebuild the whole trip across days while respecting locks, bookings, hard facts, and member thresholds.
- `Explain why`: show the deterministic reasons, constraints, and tradeoffs without changing the plan. This is free by default; an optional `Explain naturally with AI` action may use one model call.

Quick actions, including the default `Explain why`, remain available when GenAI is disabled.

## Consequence preview

- Show changed days by default, with a `View full trip` option; include every day affected by a cross-day move even if the request named only one day.
- Display the parsed request, visible assumptions, added/removed/moved/shortened items, and before/after walking, travel, transfers, day length, meal timing, cost, member comfort, warnings, displaced selections, refreshed evidence, and remaining gaps.
- The only terminal actions are `Apply`, `Edit request`, and `Cancel`. `Apply` remains unavailable until the proposed plan passes the confirmed deterministic validity gates.

## Revision history

- Keep the complete applied revision history locally for the life of the trip: original request, typed intent, visible assumptions, before/after change set and consequences, plan/evidence versions, and timestamp.
- Restoring an earlier plan creates a new active version referencing the restored snapshot; it never deletes later history or silently rewrites an export.
- Store only useful structured records and user-visible explanations, never hidden model reasoning.

## Pending revision draft

- Keep only one pending revision preview in Phase 1; the active itinerary remains unchanged until the owner presses `Apply`.
- A related follow-up modifies the same pending preview and reruns its affected evidence, optimization, validation, and consequence comparison.
- Before an unrelated request replaces the pending preview, ask the owner to confirm discarding it.
- Do not build branching draft histories for the POC. Applied plan versions remain restorable through revision history.

## Language behaviour

- Understand English, Thai, and mixed-language revision requests. Reply in the request language when clear, otherwise use the current app language.
- Preserve local-script place, station, exit, and entrance names in the UI and preview.
- Store parsed intents with stable entity IDs and language-neutral operation values so switching language cannot change the requested plan mutation.

## Model requirement

- Do not hard-code a model name in this product-contract ticket. The architecture ticket selects and tests one configurable OpenAI model that supports the Responses API, strict structured intent output, reliable English/Thai interpretation, and the shared cost limit.
- Record the configured model and intent-schema version with each AI-assisted revision for diagnosis and reproducibility.
- Do not silently change or fall back to another model. A deliberate model change must pass the same revision-intent and failure-safety checks.

## Privacy boundary

- Use the Responses API with `store: false` and keep user-visible conversation/revision history locally. The UI discloses that standard API abuse-monitoring retention may still apply.
- Send only the request, affected active-plan slice, necessary preference/constraint values, and stable entity IDs. Exclude passport data, booking documents, API keys, unrelated member detail, and restricted provider review text.
- Let the owner disable GenAI completely without disabling the optimizer, structured controls, quick actions, or existing plan access.

## Unavailable-AI behaviour

- Existing plans, quick actions, manual structured edits, optimization, validation, and exports remain usable without OpenAI.
- Free-text revision reports whether it is unavailable because of missing credentials, offline state, quota, budget, or API failure. Retry one transient failure at most; never loop, spend repeatedly, or switch models/providers silently.
- Any refusal, timeout, invalid schema, parse error, or unavailable service leaves the active plan and revision history unchanged, with a retry or manual-action path.

## Shared paid-API budget

- OpenAI usage shares the confirmed US$10 monthly cap with every other paid provider; it is not a separate allowance.
- Warn at US$8 estimated monthly spend and stop new paid calls at US$10. The owner must deliberately raise the global cap before paid calls resume.
- Spend priority is: operational fact and route verification, one free-text revision interpretation, then optional natural-language explanation.
- Quick actions, deterministic explanations, structured edits, optimization, validation, existing plans, and exports continue after the paid-call stop.
- Show estimated monthly spend before an optional AI explanation and update visible usage after every paid call. A call is allowed only when its conservative estimated maximum fits within the remaining cap.

## Acceptance checks

- Clear English, Thai, and mixed-language requests map to the same typed operations and stable place IDs; local-script names remain visible.
- Each contextual quick action works with GenAI disabled, first produces a preview, and never changes the active itinerary directly.
- Requests such as `reduce Day 2 walking`, `move Wukang Road before dark`, `avoid a tourist-trap stop`, `fix the late meal`, `use the rainy-day backup`, and `fully re-optimize` exercise the historical failure classes without embedding city-specific rules in the core.
- Model text cannot introduce an opening time, route, fare, closure, crowd level, or reservation fact. Missing, stale, conflicting, or unverified hard evidence keeps `Apply` disabled and names the exact gap.
- A cross-day change respects locks and bookings, includes every affected day, and shows before/after walking, travel, transfers, duration, meal timing, cost, member comfort, warnings, displaced selections, and evidence status.
- Before `Apply`, the active plan and exports remain unchanged. Applying creates a versioned record; undo or restore creates another active version without deleting history.
- A related follow-up updates the one pending preview. An unrelated request cannot discard it without confirmation.
- Refusal, timeout, invalid schema, unsupported intent, offline state, missing credentials, quota exhaustion, and budget exhaustion all leave the plan and revision history unchanged and expose a manual or retry path.
- A normal free-text revision uses at most one AI interpretation call. Deterministic preview work uses none; natural-language restatement uses another call only when explicitly requested.
- At the warning and hard-stop thresholds, the UI reports shared paid-API usage, prioritizes operational verification, and preserves all non-AI planning functions.
- The outbound AI payload contains only the affected plan slice and needed constraints, excluding passport data, booking documents, secrets, unrelated member details, and restricted review text.

## Resolution summary

Phase 1 uses one optional, tightly constrained revision assistant: free text becomes a strict typed intent, affected facts are refreshed, and the deterministic cross-day optimizer produces an inspectable consequence preview. The owner alone applies changes; one pending draft, versioned history, restore, bilingual handling, privacy minimization, shared-budget enforcement, and non-AI quick actions keep the planner safe and useful when AI is unavailable. The exact model remains a tested architecture configuration rather than a permanent product rule.
