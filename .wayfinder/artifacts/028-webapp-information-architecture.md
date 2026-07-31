# Webapp information architecture — routes, gating, navigation

Resolves `Map every Streamlit stage to its webapp screen and route` (WF-028).

Decided 2026-07-31 through the IA interview. Measured against the checkout at `e904ff1`. Paths are
repo-relative.

## Counts up front

| Measure | Value |
|---|---|
| Stage routes | **9** (8 ported + `/split`) |
| Gate keys those 9 routes resolve to | **5** (`setup`, `places`, `evidence`, `optimize`, `itinerary`) |
| Navigation sections | 2 — BUILD (4) and USE (5) |
| Routes that redirect | **1** (`/` only) |
| Setup steps on one route | 5 |
| Auto-Bill step-indicator steps, hardcoded in class names | **4** |

## The route table

```
/                             -> the most recently created trip's attention stage
                                 (or /trips when no trip exists)
/trips                        trip picker and create

/trips/:tripId/setup          BUILD   gate: —            (entry)
/trips/:tripId/places         BUILD   gate: places
/trips/:tripId/evidence       BUILD   gate: evidence
/trips/:tripId/optimize       BUILD   gate: optimize
/trips/:tripId/itinerary      USE     gate: itinerary
/trips/:tripId/readiness      USE     gate: setup
/trips/:tripId/costs          USE     gate: setup
/trips/:tripId/split          USE     gate: setup        (new)
/trips/:tripId/revise         USE     gate: itinerary
```

The eight ported paths keep the slugs `st.navigation` already assigns via `url_path=key`, so the stage
segment of every URL is unchanged from the POC. `/split` joins the USE section because it records money
that has already moved, and it gates on `setup` for the same reason `/costs` does — a split row's
participants are traveller ids, and travellers come from setup.

**One judgement call, made rather than asked:** `/` resolves to the **most recently created** trip's
attention stage. Today `LANDING = journey["next"] if trip is not None else "setup"` with an ambient
selected trip, and a returning owner lands on their plan rather than a picker — that behaviour is worth
preserving, and `list_trips()` already carries `created_at`, so it needs no new field. Ordering by *last
used* would need one, so it is deliberately not done.

## Trip identity lives in the path

Every one of the 51 allowlisted methods takes `trip_id`, so the frontend must always know it. Reading it
from `useParams` rather than from ambient context buys three things:

1. **It prevents a whole bug class.** TanStack Query keys must include the trip id; taking it from the
   route is the standard pattern. With ambient state, ~51 query keys each have to *remember* to include
   it, and forgetting one serves another trip's cached data — silent and severe.
2. **Refresh and deep links work with no persistence layer.** The alternative invents a localStorage
   mechanism to replace what a URL gives free.
3. Multiple trips genuinely exist, so "which trip" is a real question the URL should answer.

Accepted costs: the URL shape gains a level the POC does not have, every link carries the trip id, and a
trip-less route family (`/`, `/trips`) sits beside the trip-scoped one.

## Gating: one wrapper, and exactly one redirect

```tsx
<Route path="places" element={<StageGate stage="places"><Places/></StageGate>} />
```

`StageGate` reads the `journey()` query and either renders the blocked explanation **in place** or renders
its children. It never decides anything — `journey()` already answered.

> **This reproduces two Phase 1 decisions that a router would otherwise quietly break.**
>
> `shared.require()` **does not redirect.** It renders one clear next step and returns False, so a view
> explains itself instead of erroring. A blocked route that redirected would explain nothing: the owner
> asked for evidence and silently arrived at places, with the address bar disagreeing with the click.
>
> The attention-based landing **is** a redirect, but only from `/`. `journey["next"]` picks it, exactly as
> `app.py` does today.

The 9 routes map onto 5 gate keys declaratively — `readiness`, `costs` and `split` pass `setup`; `revise`
passes `itinerary`. Accepted costs: a wrapper on every stage route is boilerplate and omitting it on a
future route silently removes the gate, and the journey query must resolve before any stage renders, so
there is a loading state to design.

The blocked-state element itself has no Auto-Bill counterpart — it belongs to `Design the feedback,
confirm, and disabled elements Auto-Bill never had`.

## Setup: one route, five steps

`/trips/:tripId/setup` holds all five steps with the step index in component state, inside Auto-Bill's
wizard shell (element 6) and step indicator (element 7).

`WF-026` already decided the draft is **one object sent whole**, so five steps are five views over one
piece of state — splitting the route would not split the data, and would invite a deep link to step 5
against an empty draft, requiring guards the single-route version never needs. The country-to-city
dependency is just a derived render.

Two concrete adaptations the inventory pins down:

- **The step indicator hardcodes four steps in its class names** — `.wizard-progress-4`,
  `.progress-step-4`, `.step-num-4`, `.step-label-4`, `.progress-line-4`. The planner has five, so the
  whole family must be renamed or generalised. This is unavoidable in any option.
- **Clicking a step navigates backwards only** (`step >= n ? setStep(n) : null`). That happens to suit a
  wizard whose later steps depend on earlier answers, so it is kept rather than "fixed".

Accepted cost: no deep link to a step, the back button leaves setup entirely, and a refresh restarts at
step 1 unless the step is persisted.

## Costs and split are two screens, cross-linked

The owner's distinction, which this decision is built on:

> `costs` is the **estimated** cost that might occur for this **drafted plan**. `split` is the function
> that splits the bill for **actual cost that happened**. Some values can be linked and edited for
> convenience, and Auto-Bill's add / edit / delete and other functions must still exist.

So they are different in purpose, in time direction, and in record shape — estimates belong to a plan,
splits belong to money that already moved:

```
/trips/:tripId/costs   estimates for the drafted plan
/trips/:tripId/split   actual bills, split per person
        \__ "record this as actually spent" __/   (explicit, editable result)
```

The split screen therefore gets Auto-Bill's full surface — `TransactionModal.jsx` (694 lines), participant
chips, the settlement grid, the main-cardholder selector, per-person meters — without an estimates table
competing for the same space.

> **One overlap is flagged, not resolved here.** `costs.py` is *not* purely estimates:
> `PAYMENT_STATES = ("estimate", "committed", "paid")`, and a `paid` row locks its `actual_thb` and
> "reports itself, never a re-conversion" (`costs.py:147`). So a paid cost row is already actual money.
> Where that boundary falls is `Decide cost-and-split reconciliation rules`, which is on the frontier.
> This ticket decides only that the two live on separate routes with an explicit link action between them.

Accepted costs: a 9th destination in a navigation with no Auto-Bill precedent for eight, and comparing
estimate against actual means moving between two screens.

### Removing a split row voids it, and the button still says remove

`WF-018` decided rows are editable and that removing one **voids rather than deletes**, with voided rows
staying visible "so a total remains explainable". The owner's request that Auto-Bill's actions survive is
honoured at the level that matters — **add, edit and remove all exist, and the modal is lifted intact** —
while the underlying record is voided rather than destroyed.

That keeps `WF-018` intact for its stated reason (corrections happen constantly during a trip, and the
voided row is *why* a total that moved can be explained) and follows the readiness board's existing
dismiss-not-delete precedent in this repo.

Two consequences to design for: voided rows accumulate over a long trip and need a hide/show control, and
a "Remove" that does not remove must be visually obvious or it reads as a bug.

## Navigation: Auto-Bill's sidebar shell, with navigation inside it

```
SIDEBAR (.sidebar, element 17)     BUILD  setup · places · evidence · optimize
                                   USE    itinerary · readiness · costs · split · revise
                                   ─────
                                   trip selector
                                   language
```

The shell already exists as element 17 (`index.css:902`) with the signature 1px border and hard-offset
shadow, and Auto-Bill's sidebar already carries interactive quick actions (element 21) — so an
interactive sidebar is in-language. Only its *content* changes. `WF-021` found that of 18 planner elements
with no counterpart, **only the numbered map falls outside what the visual language can reach**, so
navigation is reachable.

This also preserves today's exact information architecture, all of it Phase 1 decisions: two sections,
the trip context directly under the stages, the language control at the foot.

> **The one real gap:** at `992px`, `.sidebar` loses `height: 100vh` and `position: sticky` and goes
> static. For an informational sidebar that is fine; for **navigation** it means a nine-item list sitting
> above the content on every phone screen. A drawer or collapse must be **designed**, not lifted — Auto-Bill
> has no precedent because it never needed one.

Auto-Bill's own architecture — wizard until setup completes, then one dashboard forever
(`App.jsx:108`) — was rejected outright: it destroys the journey model, since `journey()` picks a landing
**stage** and `require()` gates per stage, both of which assume stages are destinations. Folding eight
stages (including a 570-line `places` and a 201-line `itinerary`) into one dashboard would rebuild the
donor's 2,183-line `Dashboard.jsx` by construction.

## Consequences for other tickets

| Ticket | Consequence |
|---|---|
| `Prototype the merged cost and split screen` | **Its premise changes: there is no merged screen.** Its substance — payment states, the rate snapshot, settlement, balance-as-suggestion, the reversible owe-direction — all survives, now across two screens plus the link action. The title is now misleading. A dated note has been added to its Context |
| `Design the feedback, confirm, and disabled elements Auto-Bill never had` | Owns the blocked-stage explanation element that `StageGate` renders, and the void/hide-show control |
| `Define the visual parity gate for the Tailwind rebuild` | Must cover the sidebar-shell adaptation and the `.*-4` → five-step indicator rename, both of which change lifted CSS |
| `Decide cost-and-split reconciliation rules` | Owns the paid-cost-row overlap above, and defines what "linked" means for the cross-link action |
| `Decide the bilingual copy pipeline for the webapp` | Nine stage labels, two section labels, and the blocked-stage message are all existing `ui/text.py` keys (`stage_*`, `section_build`, `section_use`, `journey_blocked`, `journey_needs_trip`) |
| `Lock the Phase 2 slice plan and validation scorecard` | Sequencing input: the inventory rates `costs`, the app chrome, `optimize` and the `setup` shell as nearly free, and `places` and `itinerary` as nearly all-new. `/split` now joins the nearly-free group, since it is lifted from Auto-Bill wholesale |

## Explicitly not decided here

- The phone drawer/collapse mechanism for the sidebar below 992px.
- What the blocked-stage explanation looks like as an element.
- Whether the step index is persisted across a refresh.
- What "linked" means precisely for the costs↔split link action.
- The trip picker's own layout.
