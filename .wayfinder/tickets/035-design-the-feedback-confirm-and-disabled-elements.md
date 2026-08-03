---
id: WF-035
title: Design the feedback, confirm, and disabled elements Auto-Bill never had
status: closed
labels:
  - "wayfinder:prototype"
parent: WF-MAP-002
assignee: user-and-root
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

## Resolution comments

### 2026-08-03 — Prototyped and accepted, all seven calls confirmed

Prototype: [`035-feedback-element-family.html`](../artifacts/035-feedback-element-family.html) — eight
sections, EN/TH, light/dark, and a working confirm dialog. Throwaway per the map. Every element in it is
**new**: the donor has no banner, no field error, no `:disabled` rule and no confirm element.

**Two counts in this ticket were measured lower than stated.** The planner emits **68** status calls — 10
`st.success`, 23 `st.error`, 15 `st.warning`, 20 `st.info` — not 59; and it disables a primary action in
**10** places, not 5. The donor has **27** `alert()` calls, not 33, with `window.confirm()` at 5 exactly as
stated and **zero** `:disabled` rules. So the gap is wider than charted: 68 inline conditions facing a
feedback model made entirely of blocking dialogs.

**All seven calls were confirmed**, so the family stands as built:

1. **Four levels named Saved / Cannot / Check / Note** — not Success / Error / Warning / Info, because those
   name a severity to a developer while these name what happened to the owner.
2. **No icon at all; the level word is the carrier.** Exports strip pictographs, so any glyph would vanish.
3. **Disabled = 45% opacity, no shadow, plus a mandatory reason line.** Losing the shadow matters more than
   the grey in this visual language — the hard offset shadow is what makes a thing look pressable, so removing
   it says "not pressable" directly. The donor's nearest precedent is its own filter dimming at 40%.
4. **Paid actions state cost on the button and spend beside it**, in three states: allowed, near the cap at
   US$8, refused at US$10. Only the refused one is disabled.
5. **"Requires network" is deliberately not a disabled state** — the action is allowed, it just cannot succeed
   offline, and the owner may be about to reconnect.
6. **Confirm names the consequence** instead of asking "are you sure?", and the destructive button carries the
   verb. It lists what dies — 3 plan versions, 5 places, 4 discovery runs, 50 paid-call records — and notes
   that deleting a trip is the one action that can remove otherwise-permanent history.
7. **The missing-copy fallback is deliberately ugly** (`⚠ ACCESS_UNVERIFIED`), shown beside the old prettified
   version. It will occasionally be seen, and that is the point: the pretty version hid 24 missing English
   strings for months.

**§8 encodes the rule the codebase learned three separate times** — a word-valued state is a text line with a
pill, a number is a tile — with the real failure (`unavaila…` clipped in a quarter-width column) shown beside
the fix.

**Rejected while building:** toasts, because most of these messages are *conditions* rather than events and a
stale preview is still stale in ten seconds; a colour-only severity system, which fails the export path,
colour-blind readers, and the app's own colour-is-never-the-only-signal rule; reusing the donor's
`.manual-validation-panel` for field errors, since it reports the whole form in one block; a generic
"are you sure?", which transfers no information; prettifying an unknown code, rejected on evidence; and an
`alert()`-style modal for status, which blocks the page for something needing no acknowledgement.
