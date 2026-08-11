---
id: WF-049
title: Decide what the interface owes a reader who is not the owner
status: closed
labels:
  - "wayfinder:decision"
parent: WF-MAP-002
assignee:
blocked_by:
---

# Decide what the interface owes a reader who is not the owner

## Every screen was tuned by one person watching it work

`WF-048` rebuilt the journey's explanations after the owner walked the whole thing and
could not use it, and that channel has been the app's only source of interface evidence.
It is a good channel and it found real mechanical faults — a swipe that never worked, a
call to action pointing at an id that did not exist, a screen that cleared itself between
cards. But it can only report what one reader, on one machine, at one window size, using
a mouse, notices.

An external UX audit on 2026-08-10 measured the parts that channel cannot reach. It found
no Critical issues and scored functionality 9/10 — the product works. It scored
accessibility **5/10**, and the sixteen findings were mechanical rather than matters of
taste, in exactly the way `WF-048`'s were.

Three of them were worse than reported once reproduced against a copy of the pilot.

**The type was smaller than the token names suggest.** The audit said the default text
token is 13px. Measured on `/setup`, **36 of the 51 elements carrying their own text
rendered at 11px or less** — the `--text-xs` token, which has 44 uses, is where most of
the interface actually lives.

**Tailwind's preflight resets `h1`–`h6` to `font-size: inherit`.** Only the landing page
ever styled its own headings, so every stage title on all nine screens rendered at exactly
body size. The audit reported the symptom — "the landing page transitions into a much
denser, more administrative interface" — and read it as a design divergence. It is one
line of a vendor stylesheet, and it was invisible in review because the markup is correct:
the `<h1>` is there, on every screen, doing nothing.

**The contrast problem is structural, not a list of bad values.** The audit found six
destination accents failing 4.5:1 against the white text printed on them. The reason there
are six is that `--color-accent` does **two jobs** — it fills a button and it colours a
link — and the thirteen accents were chosen for the second on a cream background. Fixing
only the fill would leave the link, and vice versa.

One finding did not survive reproduction: "true 390px" could not be re-measured the same
way, because headless Chrome on macOS clamps its window and layout viewport to a 500px
minimum. That does not make the finding wrong — the `.plan-stop-maps` collapse it names is
real and reproduces at 500px — but it changes what the regression gate can honestly claim.

## Why the existing gates did not catch any of it

Every gate in `scripts/check.py` was green throughout, and each was doing what it was
asked:

- **`scripts/check_design_tokens.py`** reported contrast rather than failing on it, and its
  floor was **3:1** — correct for a large graphic, and not the bar for the words inside a
  button. It compared accents against the two page backgrounds only, so it never saw a
  semantic colour on its own `-light` tint, which is the lightest surface those colours are
  ever written on in dark and therefore the binding one.
- **`scripts/check_element_parity.py`** compares `borderRadius`, `boxShadow`, `fontWeight`,
  `textTransform` and `letterSpacing`. Font *size* is deliberately outside that set, because
  Tailwind lays out the rebuild differently by design.
- **`scripts/check_screen_baselines.py`** photographs one viewport, 1440×900, and catches
  drift only. Every responsive rule in `web/src/shell.css` was therefore unguarded — and a
  live regression was living in that gap: below 768px the stop-row grid drops to three
  columns and re-places `code`, but never re-placed `.plan-stop-maps`, so "Open in Maps"
  auto-flowed into the 10px status-dot column on every stop of every day.

None of these is a gate that failed. They are gates that were never pointed at a reader.

## What has to be decided

- **How the accent serves both of its roles.** Either a second token for accent-as-text, or
  one value per theme that is legible in both roles. The second is only possible because
  contrast is symmetric — but it means writing the other half of all thirteen accents.
- **Where the type floor sits, and whether the whole scale moves with it.** Lifting only the
  smallest steps is the smaller diff; five steps currently live between 11 and 15px, so it
  would also collapse distinctions the design uses.
- **Whether the sidebar may state journey progress.** It requires the nav to know which gate
  each of the nine routes waits on — a table that exists today only as literals on each
  `<StageGate>` in `web/src/routes.tsx`. A second copy in the shell would let the sidebar
  promise a screen the gate then refuses.
- **How much of the Places payload is worth changing.** The audit asks for lightweight lane
  summaries. `rank_candidates` is 1.16 MB and `get_latest_discovery` 860 KB on the pilot.
- **What viewport a phone regression gate can honestly claim**, given the 500px clamp.

## Decided and built 2026-08-10

**One accent per theme, because contrast is symmetric.** An accent legible as *text* on the
theme's lightest surface necessarily takes the opposite ink as a *fill*, so one rule covers
both roles and no text-accent token is needed. Light accents are dark enough to read on
`#f3f1ec` and carry white; dark accents are light enough to read on `#1c1c1c` and carry
`#1a1a1a`. All thirteen destinations now have a `:root.dark[data-country=…]` half rather
than the two that used to — an accent picked for a cream page is by definition wrong on
`#121212`, so the override is the other half of a pair, not a patch for two bad choices.
Six light accents moved: australia, eurozone, hong-kong, malaysia, taiwan and vietnam, at
2.94–4.10:1. Taiwan is the pilot's own.

**The gate fails at 4.5:1 and checks the tints.** `scripts/check_design_tokens.py` now
enumerates every foreground/background pair the stylesheet can produce, in both themes,
including each semantic colour against its own `-light` tint. That last part is what four
dark colours at 3.72–4.13:1 had been hiding behind. Translucent values are skipped rather
than measured wrongly against their own opaque channels. Negative-tested: restoring
`--text-muted: #737373` and taiwan's `#0d9488`, and deleting one dark half, reproduces the
audit's exact numbers and names the missing pair.

**The whole scale moved by about a fifth, and the headings got a size at all.** Body 16px,
supporting text 14–15px, 12px reserved for metadata — coordinates, plan-version tags, map
labels, unit suffixes. Sizes stay in `rem` so an OS text-size preference still scales them,
which is the audit's older-traveller case. Stage headings are styled explicitly in
`web/src/shell.css`, which is the actual fix for the landing-versus-journey complaint;
carried with it are a readable introduction at a 68ch measure, more card padding, and one
primary-action style, since `.setup-primary` had been a grey bordered button that only
became the accent inside two named containers.

**The tour is a native `<dialog>`.** `role="dialog" aria-modal="true"` says a thing is modal
without making it one. `showModal()` gives focus containment, background inertness and
Escape from the platform; fifty lines of hand-written listeners would have to stay right
about focus order forever. The platform does not choose where focus lands afterwards — it
restores to whatever had it before, which on a first visit is `<body>` — so the reopen
button is always rendered and explicitly refocused.

**The nav and the gate answer from one predicate.** `web/src/shared/stages.ts` holds the
nine-routes-to-five-gate-keys table; `web/src/routes.tsx` generates its children from it
and `web/src/shared/AppShell.tsx` reads it for Complete / Next / Available / Locked. A link
marked locked is therefore exactly a link the gate will block. A locked stage stays a link,
because `<StageGate>` explains in place rather than redirecting — what changed is that the
prerequisite is named *before* the click.

**The Places payload was deliberately not trimmed, and this is the interesting refusal.**
The DOM half was the measurable harm and it is fixed: `<details>` hides its contents but
does not avoid building them, so all 849 catalogue rows and the full provider JSON were
mounted on every visit. Rendering on first open plus a 50-row page took `/places` from
~4900 DOM nodes to **543**.

Trimming the *wire* is wrong rather than merely unattractive. `candidates` is a `Frozen`
snapshot and the client is handed its `sha256` alongside — shipping a narrowed `data` would
put a hash on the wire that does not describe its payload, which is the one contract the
whole design rests on. A lightweight read is therefore a **new method**, not a narrower old
one, and it needs a decision about how the deck prefetches without re-opening the
background-fetch bug `WF-048` already paid to fix. Left open with its numbers.

**The phone gate is 500×844 and says so.** Headless Chrome clamps below that, so
`--window-size=320,844` and `--window-size=450,844` both measure 500. A set named 390 would
be a 500px image with a false label, and the next person to correct it would get the same
500 back. Every `max-width: 768px` rule is still exercised; a true 320–390px reflow check
needs device emulation over the DevTools protocol and stays manual. The tour is reached
through a `?baseline_tour=open` seam that forces on the overlay `data-capture` suppresses
everywhere else — the inverse of the suppression, not a hole in it.

### One thing this ticket found that the audit did not

A capture was **writing**. Diffing all 23 tables across a full run found one
`open_meteo:forecast` row and one `provider_cache` row per capture — free, and invisible in
the images because the forecast is `covered: false` until the trip dates enter Open-Meteo's
16-day horizon. It is still the app being operated rather than observed, which is the rule
`WF-048` set after the summaries prefetch caused 13% drift on screens nobody had edited.
The forecast query is now disabled under the capture flag like the basemap before it. A
clean run over a byte-identical copy of the pilot now changes **no row in any table**.

### Evidence

All twelve `scripts/check.py` stages pass. 486 Python tests, 85 Vitest. The screen gate is
**56 images**: the 36 desktop baselines re-approved, plus 20 phone. Heading outlines were
walked in a real browser on all nine routes and the landing page — each starts at `h1`, has
exactly one, and skips no level. Overflow was checked on every route in **Thai**, the
longer language. `data/tourist.sqlite3` was never opened: every measurement ran against
copies, and the pilot is still `d91ac5ad…`.

Two things are explicitly **not** discharged. The Thai for roughly sixty rewritten strings
was authored here and wants a native reader. And the audit's own "Needs Verification" list —
real VoiceOver/Safari and NVDA/Firefox over the whole journey, 320px reflow, 200–400% zoom,
field Core Web Vitals on a deployed build — is untouched. DOM semantics are not a screen
reader, and this ticket only claims the semantics.

## Audit closure follow-up, 2026-08-11

The wire half is now reduced without violating the decision above. On the same isolated pilot copy,
`get_latest_discovery`, `rank_candidates` and `list_candidate_choices` measure 880,068 B, 1,187,918 B
and 151,727 B raw; the running server reduces them to 80,319 B, 61,755 B and 16,268 B — about **93% less**.
The server selects compression from `Accept-Encoding`; the decoded snapshots and their hashes are
unchanged, and a socket test decompresses and compares the real JSON shape.

The constrained revision surface is also complete. AI starts off, and the price, request/plan-slice
boundary and provider-retention qualification are visible before the textarea is enabled. One
interpretation may create the existing typed pending draft; it cannot alter the active plan, and the
existing consequence preview and Apply button remain the only acceptance path. Missing credentials
were exercised against a scratch database: HTTP 503, no draft and no revision history. No paid call was
submitted. The landing page's absolute “No upload” sentence was corrected to distinguish the local trip
file from these explicitly optional provider/model transmissions.

## Final local closure pass, 2026-08-11

Device emulation removed the old 500px verification limit. The landing page and all nine journey
routes were exercised in Thai at 640, 427 and 320 CSS pixels — the reflow equivalents of 200%,
300% and 400% zoom from a 1280px layout. All 30 cases kept document width within the viewport,
exposed exactly one `h1`, had no unnamed interactive node in Chrome's accessibility tree, and
reported no console or failed-request event. The remaining sub-24px hit areas were inline
attribution/source links, which use the inline-link target-size exception. Mobile disclosures and
the two itinerary actions now have a 44px floor. The itinerary's compass rose was also absolutely
positioned against the page because its map lacked a positioned ancestor; it is now anchored to
the map itself.

The native dialog had one real state bug left. Escape closed the browser's dialog while React's
`open` state stayed true, leaving the card mounted and making the reopen button a no-op. The
`cancel` event now prevents the browser-first close and runs the same state-led close path as the
visible buttons. Three repeated browser runs each closed the card, remembered the dismissal,
returned focus to “How this works”, and reopened immediately with focus inside. A forced attempt
to focus the background was rejected while the modal was open.

Static delivery now receives the same treatment as the large JSON snapshots: compressible files
are gzip-negotiated, hashed assets are immutable for one year, and route shells are revalidated.
The built main script measured **515,343 B identity and 152,748 B gzip**. Under 4x CPU slowdown,
150ms latency and about 1.6 Mbps, local transfer was 240,436 B for landing, 204,849 B for setup,
791,930 B for Places and 313,602 B for itinerary; CLS stayed zero. Places still decoded 3,502,625 B
and produced five 95–139ms long tasks while rendering its real pilot data. Vite still warns about
the 515KB raw entry chunk: moving libraries into a second chunk would silence the threshold without
reducing bytes, so this pass fixes transfer rather than disguising the warning.

Every external HTTP link exposed by the representative nine-route walkthrough was followed on the
day of the check: Wikipedia, Huashan 1914 and the two OpenStreetMap pages all returned HTTP 200.
The stored catalogue was checked without hammering a public service: all **855** source URLs equal
the canonical OpenStreetMap URL for their own provider id, and all **58** distinct place-evidence
URLs are HTTPS with no literal space (41 Commons, 12 English Wikipedia, four Thai Wikipedia and one
Huashan). A representative Commons file redirect returned an image with HTTP 200. The two itinerary
map handoffs use syntactically pinned `geo:` URIs. Open-Meteo, Overpass and OpenRouteService were
reachable, and an explicitly approved synthetic paid smoke made one Google Places request and one
Google Routes request; both were reachable and no trip data was sent. All application/browser work
used the scratch database. The owner database remained unopened by the app at
`6c708328a5d3c8fbd208078af40609f9a0d9453414790fba11336e8b552af92c`.

What remains is evidence this machine cannot manufacture: a native Thai copy review; a full
VoiceOver/Safari journey; NVDA/Firefox on Windows; and field Core Web Vitals from a deployed URL and
real users. Headless Chrome did not expose LCP, so the local profile does not substitute a number.
Those are release-validation boundaries, not unimplemented product fixes.

The owner later asked that those checks be retained for the day this becomes public. They now live
in [`PUBLIC_RELEASE_PLAN.md`](../../PUBLIC_RELEASE_PLAN.md), together with the larger hosted-service
work they imply: authentication and tenant isolation, durable hosted data, privacy/provider controls,
security and recovery, field performance, release operations and an invite-only beta. This ticket
remains the evidence record; the public-release file is the forward plan.

## What followed, 2026-08-11

The same review asked a second question — *can `/split` and `/costs` do what
`Auto-Bill-Splitter` did* — and it is recorded here rather than in a ticket of its
own, because a new ticket file fails `--check` until a paid graph rebuild pays for
its node, and none of what follows is a decision this map had not already taken.

**The donor is readable, and reading it changed three answers.** It is at
`ML/Personal_Project/Tourist/Auto-Bill-Splitter`, archived read-only, not the
Windows path `WF-020` records. Working from its 41-element inventory rather than
its source had produced an inferred gap list, and the source corrected it:
`equalSplit` really does dump the whole rounding remainder on `people[0]`, exactly
as `WF-018` claimed; its manual mode tolerates a 0.015 mismatch and silently moves
the difference onto the first positive share, where an exact-equality rule would
have rejected a hand-typed 33.33 three times against a 100.00 bill; and its
**Daily Spending Flow** chart is keyed on a day field this app already stores as
`plan_day` and has never surfaced.

**The largest finding was not a parity gap at all.** `WF-030` locked two
workbooks and only the plan file was ever built, so the split ledger could only be
exported inside the file that carries the itinerary, every address and the
readiness evidence — the one file that ticket says must not be handed to anyone.
See the money-workbook section of `CLAUDE.md` for the four sheets and for why it
is deliberately not gated on an active plan.

Also built: manual allocation as a fourth split mode, the main-cardholder
selector, per-row notes, the donut and per-person meters (which is where map item
5's question gets its real answer), and per-trip expense categories with the seven
kept as an unremovable floor.

**Two divergences were offered and declined**, and stay declined: a people manager
inside `/split` (the roster lives in setup, and `validate_row` refusing an unknown
traveller id is what stops settlement fracturing on `Mum` versus `mum`) and a JSON
import/export backup (`WF-024` decided no importer is built).

## Related

- [Decide what the journey must explain before it asks](048-decide-what-the-journey-must-explain-before-it-asks.md) —
  the same kind of finding from the only reader the app had. This ticket is what a
  different reader saw.
- [Lock the Phase 2 slice plan and validation scorecard](../artifacts/033-phase-2-slice-plan-and-scorecard.md) —
  the scorecard this measures against.
- [Define the visual parity gate for the Tailwind rebuild](025-define-the-visual-parity-gate-for-the-tailwind-rebuild.md) — whose 1440×900
  blind spot is the reason a live mobile regression survived. The viewport is still one
  fixed size per set, by the same reasoning; there are now two sets.
- [Decide the offline asset policy for the webapp](034-decide-the-offline-asset-policy-for-the-webapp.md) — the favicon is
  drawn rather than fetched for its reason, and does not follow the destination accent: a
  favicon is the app, not the trip.
