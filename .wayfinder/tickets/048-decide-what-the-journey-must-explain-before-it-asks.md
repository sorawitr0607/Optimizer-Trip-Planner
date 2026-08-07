---
id: WF-048
title: Decide what the journey must explain before it asks
status: closed
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide what the journey must explain before it asks

## The owner walked the whole journey and could not use it

Reported 2026-08-07, from the self-test the previous session predicted. The complaint is
not that anything computed the wrong answer — every gate was green and the pilot plan was
valid. It is that the interface never says what it is, what it wants, or what it did.

The owner's own framing is the requirement, and it is worth keeping in their words:

> the user should be like the one that doesn't know anything about this website, explain
> and give examples or placeholder

Four findings, one per stage. Each turned out to have a mechanical cause, not a taste
disagreement, which is why this ticket is closed with code rather than with a style guide.

## The landing page asked for a destination it never explained

It was a heading, a trip list, and two unlabelled text inputs. Nothing on it said the app
finds places, builds a timetable, or exports a workbook — so the first decision asked of a
new owner was to type a geocoder query blind, with no way to know that is what it was.

**Decided: the first screen states what the app produces before it asks for anything, and
the destination is picked, not typed.** `web/src/stages/TripsPage.tsx` is a new file; the
route table in `web/src/routes.tsx` goes back to being the data it is documented as.

The two dropdowns read `setup_vocabulary`, which has carried countries with both language
labels and their cities since S3 — **no method was added**, and the setup form and the
landing page now agree about what a destination is because they read the same list.

Two constraints survive intact. The canonical latin name stays the stable value on both
dropdowns, because it becomes the geocoder query and localizing it would let a language
switch change which place is searched. And both keep an **"Another … — type it"** option:
`travel_planner/destinations.py` is a picker convenience, and the worldwide-acceptance
check requires that a city absent from that table still completes setup.

The assembled string is `"City, Country"`, which is what the pilot trip already holds. That
is not a coincidence to leave undocumented — it is the format `AppShell.countrySlug()`
needs, since it splits on the comma and takes the last segment to set the destination
accent. A city-only string silently loses the accent mapping.

## The setup wizard opened on a form and never said what for

Step 1 was a date checkbox. A first-time owner met an input before any statement of what
the wizard covers, how long it runs, or that answers can be changed later. Three specific
gaps below that:

- **The accommodation dropdown was three words with no consequence attached.** Unknown,
  not booked and booked change what every day of the plan is anchored on — the last one
  builds days out from a real address, the other two from the centre of the chosen places.
  Nothing anywhere on the screen said so.
- **The free-text boxes never said what happens to what you type.** "Extra detail or
  nuance (optional)" reads as a comment field nobody reads. It is parsed for constraints
  when the plan is built.
- **The travellers step gave no reason to fill it in**, and no hint that travelling alone
  means leaving it at zero.

**Decided: a step that asks nothing, and a consequence beside every control that has one.**
The wizard is six steps; step 1 explains the other five and says it takes about five
minutes. `STEP_COUNT` is a constant change rather than a component change, because S3
already decided the step indicator would be step-count-agnostic — the donor's `.*-4` class
family hardcoded four and renaming it to `-5` would only have hardcoded the next wrong
number. That decision paid for itself here.

**A returning owner opens on step 2.** The intro is worth reading once, not on every
visit, so the opening step depends on whether a draft is stored. It stays reachable by
walking back, because the indicator already goes backwards.

The five step titles lost their embedded `1 · `, `2 · ` prefixes. They were correct for a
five-step wizard and would now disagree with the numeral rendered beside them; the badge
and the intro list both number these already, so carrying a third copy of the number was
what made it wrong.

## The swipe did not work, and the threshold was not why

`WF-036` built the deck with the gesture as an accelerant and the buttons as the
mechanism, which is what made it testable and accessible. The gesture itself never worked.
Four causes, all mechanical, none of them `SWIPE_THRESHOLD`:

- **No pointer capture.** A drag that left the element never delivered its `pointerup` —
  and a swipe that commits is, by definition, a drag that leaves. Most gestures died
  silently.
- **No `touch-action`.** The browser claimed the gesture for scrolling and sent
  `pointercancel`, so on a touchscreen or trackpad it could not complete at all.
- **No feedback.** The card never moved, so nothing told an owner the gesture existed, was
  being recognised, or had passed the threshold.
- **`pointerdown` was bound to the whole card, buttons included**, so pressing a control
  started a drag and a drag over a control ended in a click.

**Decided: a dedicated drag surface that stops above the action row**, with live
translate-and-rotate and the pending action named while the card is still in hand. The
arrow keys were re-pointed at the same four directions, so one mental model covers both —
they used to move a cursor, which was a second, conflicting idea of what left and right
mean. Every action still has a real button, so `renderToStaticMarkup` still tests the
whole contract.

## Photographs were slow because nothing asked for them

The reported symptom was slow images. The measured cause was mostly not the network:

- The visible photograph carried **`loading="lazy"`**, which delays the one image the
  owner is waiting on. It is the card; it is never below the fold.
- A card with no summary yet showed a **button asking the owner to fetch its own
  description**, one place at a time. Until pressed, there was no image to load.
- Nothing warmed the next card. Every Wikimedia URL here is a `Special:FilePath`
  redirect, so a cold image costs two round trips at exactly the moment the card turns
  over.

**Decided: the window ahead of the deck is fetched while the current card is being read.**
Six places in one call, sliding as decisions are made, plus the next photograph and the
next card's first photograph warmed in the browser. Free — Wikidata and Wikipedia, no key
and no charge — so this buys latency with no ledger entry.

**And a place the encyclopedia has nothing for now says so.** Offering the fetch button
again for a place with no Wikidata entry is a control that cannot work, which reads as the
app being broken rather than as the source being empty.

## Nothing showed what had been kept, or what the plan assumed

Two gaps that are really the same gap — the app knew something the screen did not say.

**On places**, the deck consumed the queue and showed nothing for it. `web/src/stages/PlacesPage.tsx`
now carries a shortlist grouped by must-do, interested and maybe, and a totals block:
places kept, visiting time, days available. **Totals only, deliberately.** Dividing them
into days would need a copy of the optimizer's pacing constants in TypeScript, and two
copies of a number is how the screen and the workbook start disagreeing — the same
argument `WF-018` makes about rounding.

**On optimize**, the owner said they could not see a plan without strict input. The
planner does not in fact refuse on thin evidence: it fills the hole and carries on. What
was missing was any statement of which holes it filled, so a plan built on a flat
09:00–21:00 guess looked exactly like one built on fetched hours.

`web/src/stages/OptimizePage.tsx` now reads the assumptions **out of the frozen
`optimizer_input` the draft was actually built from** — assumed opening windows with a
count, estimated rather than looked-up routes, a centroid accommodation base, and no trip
dates. The snapshot's own `capability_gaps` are appended rather than recomputed, and that
is the load-bearing choice: the snapshot already records its own gaps, and a second
opinion derived beside it could disagree with the plan it claims to describe.

The five gap codes already had copy, so this surfaced an existing vocabulary rather than
inventing one.

Colour was added to the five choice actions, which had been five identical grey buttons
with the destructive one sitting between two keeps. Solid green through amber to a red
outline, so the row reads as a scale and dropping a place is the only action not filled.

## What was deliberately not done

- **The deck is still fed `main_queue`.** Its top 20 have no Wikidata id and therefore no
  photograph, which is a large part of why images seemed slow — `PlacesPage` already opens
  its *list* on City Icons for exactly this reason, and the deck never was. Changing which
  lane feeds the deck is `WF-005`'s design, not a UX repair, and it needs its own ticket.
- **The 1440×900 viewport is unchanged**, so the four features `WF-025` cannot see remain
  invisible to the screen gate, and the three added by this ticket join them.
- **Two baselines drift on their own and were left alone.** `/evidence` renders the running
  paid-usage counter and `/itinerary` the export timestamp, so eight of the 36 images move
  with the clock and the ledger rather than with the code. `/evidence` crosses the 0.1%
  tolerance unaided; `/itinerary` stays under it. Excluding a region from a baseline is a
  `WF-025` decision and is not taken here.

## Tests and gates

`i18n/copy.json` gains **79 codes**, both languages, and five existing step titles were
edited; `TEXT` holds 735. Web tests go 66 to 69 — the deck's drag surface and action
colours, the eager photograph, and the first-run intro on a trip with no stored setup. Two
existing setup tests were rewritten rather than deleted: they asserted "step 1 of 5" and
the draft loading on the opening step, which is the behaviour this ticket changed, and both
assertions survive against the new opening step.

420 Python tests, 69 web tests, and all 12 `check.py` stages pass. The token gate and
element parity needed no widening: the new elements declare donor ancestors — element 5's
hero, element 4's landing grid, element 6's card, element 7's step numeral, element 18's
summary box and element 36's info callout — and every colour is a token.

**20 of the 36 screen baselines were re-approved.** Twelve are this ticket's work — setup,
places and optimize across both themes and both languages — and eight are the self-drifting
pair described above.

The graph rebuild this ticket required **failed the first time and had to be paid for
anyway**: extraction emitted `travel_planner_destinationspy` and `web_src_routestsx`
beside the real nodes, and `SOURCE_SUFFIX_IDS` listed only the `_py` / `_ts` spelling, so
the pair guard demanded eight edges survive to nodes clustering had correctly collapsed.
`scripts/build_project_graph.py` now carries both spellings, generated from one extension
list so they cannot drift apart, and **prints every fold** — a fold that happens quietly is
indistinguishable from the guard being weakened. Two tests pin it, including the negative
one: a word merely ending in an extension does not fold, because the stem must itself be a
node. The retry cost nothing, the semantic cache being fully warm.

## Related

- `WF-036` — built the deck with buttons as the mechanism and the gesture as an
  accelerant. That decision is why the gesture could be rebuilt here without touching what
  the tests assert.
- `WF-025` — the viewport, the tolerance and the deviation register this work had to stay
  inside.
- `WF-005` — the swipe-queue design, including the lane the deck reads, which this ticket
  leaves alone.
