# The evidence screen — the gap no slice owned

Built 2026-08-04, between S5 and S6.

## Why this exists outside the slice plan

Every one of artifact 033's seven slice rows was checked: **none of them owns the `/evidence` screen.** It
was the last stub, and it was the reason a **newly created trip could not be planned in the webapp at all** —
route and opening evidence are hard optimizer constraints, and until now only the Streamlit POC could
satisfy them. That is why S4's gate had to use the *saved* Taipei trip, and why S4's notes recorded
"fresh-trip route evidence" as a known limit.

Building it before S6 matters because **S6 deletes the POC**. Shipping S6 with `/evidence` still a stub
would have left no way to plan a new trip anywhere, and it would have baked a stub into the 36 approved
screen baselines.

## What it does

Five cards, each self-contained, ported from `views/evidence.py` (130 lines):

| Card | Cost | Notes |
|---|---|---|
| Accommodation base | Free | Geocodes through OpenStreetMap; resolves `ACCOMMODATION_BASE_UNCONFIRMED` |
| Destination time zone | **US$0.005** | Shows the verified zone instead of a button once evidence exists |
| Opening hours | **US$0.025 per place** | Plus a free owner-confirmed window per resolvable place |
| Walking routes | **Free tier** | `openrouteservice` is priced at 0.0, so it states no cost |
| Monthly cap | — | Raise the US$10 cap, behind a disclosure |

Above all of them sits the spend meter against the cap, so the budget is known *before* any paid button is
in reach. When the cap is reached both paid buttons refuse and the free route button stays available.

## The rule this screen exists to honour

**Element 16: every paid action states its cost immediately before the button that spends money, one card
per action.** The inventory recorded why — *"stacked full-width buttons with the costs in between read as a
single wall in which nothing said what it would charge for."*

`evidence.test.tsx` asserts the ordering by string position rather than by eye: the cost text must appear
before its own button, and the route card must contain **no** cost line at all, because a cost statement
there would be a lie. That last assertion is the one most likely to rot if someone "helpfully" adds a
uniform cost caption to every card.

## Two cleanups this made possible

- **`gated()` and `StagePage` are gone.** With `/evidence` real, all nine routes have real screens, so the
  stub wrapper had no callers. `StagePage.tsx` is deleted.
- **`stage_stub` is gone from the catalogue.** "This stage lands in a later slice" was added in S1 for the
  stubs and is now dead in both languages. The catalogue is 595 keys.

## Verified

328 Python and **46** web tests, all 8 `scripts/check.py` stages green. **No new copy keys** — all 44
strings this screen needs already existed, which is the third slice in a row where `WF-027`'s one-catalogue
decision paid for itself. No new allowlisted method either: the screen composes eleven reads and writes that
S1 already exposed.

Walked live on a copy of `data/tourist.sqlite3`, never the original. The real trip shows `Asia/Taipei`
verified, 0 places with a usable window, 4 owner-fixable places named individually, 12 stored routes, and
both capability gaps rendered as prose rather than codes. Captures in `captures/` cover the paid cards, the
routes and gaps, and the whole screen in Thai.

No paid button was pressed: they spend real money and nothing here requires it.

## What this does not fix

A fresh trip can now *acquire* route and opening evidence through the webapp, but **that path has not been
walked end to end for a brand-new trip**, because doing so spends money on the opening-hours lookup and
needs live provider credentials. The free half — accommodation base and walking routes — is reachable at
zero cost. Whether the pilot walks the paid half before 1 November is an owner decision about spend, not a
missing surface.
