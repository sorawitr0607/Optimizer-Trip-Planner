---
id: WF-035
title: Design the feedback, confirm, and disabled elements Auto-Bill never had
status: open
labels:
  - "wayfinder:prototype"
parent: WF-MAP-002
assignee:
blocked_by:
  - WF-020
---

# Design the feedback, confirm, and disabled elements Auto-Bill never had

## Question

What do a four-level status banner, a confirm dialog, a field error, and a disabled primary action look like in
the Auto-Bill visual language — given that Auto-Bill contains none of them?

## Context

Graduated from the element inventory, which found this to be the largest structural absence on the supply side
rather than a missing nicety.

- **Auto-Bill has no inline feedback element at all.** Zero toasts, zero banners, zero field-error components.
  Its stand-ins are 33 `window.alert()` and 5 `window.confirm()` calls, plus `.manual-validation-panel` as the
  only in-page success or error surface. Those alerts are on the dead-weight list: a modal dialog blocks the
  whole page, and in this environment a stray `alert()` also freezes browser automation.
- The planner emits **59** `st.success` / `st.error` / `st.warning` / `st.info` calls across eight views and
  `ui/shared.py`, and several are structural rather than cosmetic: `require()`'s blocked-stage panel that
  explains the one clear next step, the flash-after-write pattern in every stage, and the three-level paid-spend
  state that warns at US$8 and refuses at US$10.
- **`index.css` has no `:disabled` or `[disabled]` rule anywhere**, while the planner disables a primary action
  with an explanatory caption in five places. "A disabled action always says why" is on the must-survive
  behaviour list, so a disabled token is a hard prerequisite for every other screen — which is why this ticket
  blocks nothing but should be resolved early.
- The rule the codebase learned three separate times and should encode once here: **a word-valued state is a
  text line, never a metric** — a word gets a pill, a number gets a tile.
- Status labels currently carry emoji, and the export path strips pictographs because no Unicode font covers
  them, so the wording alone must carry the state. Any status element designed here inherits that constraint.
- Everything must read in both English and Thai, and the four levels must stay distinguishable in both themes
  using only the palette's `success` / `danger` / `warning` / accent pairs and their `-light` companions.

Produce a throwaway prototype of the family and link it from this ticket: the four banner levels, the confirm
dialog that replaces `window.confirm()`, an inline field error, the disabled-with-reason treatment, and the
blocked-stage panel. Record what was rejected.
