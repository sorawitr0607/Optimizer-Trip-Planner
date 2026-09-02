# Approved screen baselines — 136 images

`WF-025` §2b: 4 baselines per screen (light/dark × en/th), approved once and
then diffed on every change. The current matrix is:

- **44 desktop** at 1440×900: landing plus all ten stage routes
- **48 phone** at 500×844, prefixed `m500-`: the same screens plus the tour
- **44 middle-width** at 900×900, prefixed `t900-`: landing plus all stage routes

Two things about that set. It is **500×844, not 390**: headless Chrome on macOS
clamps the window and the layout viewport to a 500px minimum, so `--window-size`
values below that all measure 500, and a file named 390 would carry a false
label. Every `max-width: 768px` rule is still exercised; a true 320–390px reflow
check needs device emulation over the DevTools protocol and stays manual. And the
**tour** is reached with `?baseline_tour=open`, which forces on the first-visit
overlay that `data-capture` suppresses everywhere else — otherwise the one modal
in the app has no visual regression cover at all.

The desktop-only gate was not merely incomplete, it was hiding a live bug: below
768px `.plan-stop-maps` auto-flowed into the 10px status-dot column and rendered
"Open in Maps" as a sliver on every stop of every day. Nothing failed, because
nothing was looking.

**What this gate catches: drift over time.** It does *not* prove parity with
Auto-Bill and must not be described as if it does — Auto-Bill has two screens
and the planner has nine, so a whole-screen comparison between them is
meaningless. Parity with the donor is `check_element_parity.py`'s job.

## The fixture trip these were captured from is missing

Recorded 2026-09-02, because it costs a session an hour to rediscover. The approved images
show a trip named **"Taipei 4-Day Food & Night…"** in the sidebar's trip selector, and that
trip is in neither `data/tourist.sqlite3` (which holds only "Baseline set") nor the hosted
Postgres. Capturing against any other trip changes that dropdown on **every** screen, so the
comparison reports drift on ~116 of 136 images that is entirely the trip name — cropping the
diff shows the changed pixels are the selector, not a layout.

So stage 9 cannot currently be re-approved honestly: replacing 136 images captured from a
trip nobody can reproduce would silently change what the gate compares, and this file's own
history is about a gate that compared nothing under a green tick. Until the fixture trip is
restored or deliberately re-based, `check_screen_baselines.py` reporting **DID NOT RUN**
(exit 2) with no `screen-current/` present is the accurate state, not a failure to paper over.

Re-basing is a decision, not a fix: it needs one named trip, kept, with its id and owner
token written down here.

## Reproducing

```bash
uv run --locked python -m localserver                            # serve on 8765
uv run --locked python scripts/capture_screen_baselines.py \
  --base http://127.0.0.1:8765 --trip <id> --owner <owner-token>
uv run --locked python scripts/check_screen_baselines.py         # also check.py stage 9
```

`--approve` writes straight into this directory instead of the comparison set.
Only this directory is committed; `screen-current/` is gitignored because it is
regenerated on every capture run.

## Tolerance

Agreed with the owner on 2026-08-04, and it is **two conditions**:

    fail when  >0.1% of pixels differ  AND  a differing pixel is off by >8/255

Both must hold. Zero tolerance was rejected because it is flaky regardless of
care, and artifact 025 records the consequence — a flaky gate gets switched off.

## Two capture races, found by running the gate against an unchanged app

The first run produced 4 failures with nothing changed. A gate that fails on an
unchanged app is worse than no gate, so both causes were fixed rather than
absorbed by widening the tolerance:

- **`setup-dark-*`, 49% of pixels, peak 10–25.** The screenshot landed part-way
  through `body`'s 300ms background/colour fade: one shot read `(79,78,78)`
  where the next read `(64,64,64)`. Capture mode now injects a stylesheet
  disabling every transition and animation, so there is no intermediate state
  to photograph.
- **`readiness-*-th`, 0.15% of pixels, peak 221–229, confined to bbox
  (325,114)–(1280,501).** The board was still loading. `stable_capture()` now
  accepts a shot only once **two consecutive shots are byte-identical**, which
  is the only check that actually tests "has this settled" — the previous
  file-size settle test passes happily on a complete PNG of the wrong moment.

## Negative test

A gate that has never failed is a gate nobody has tested. Injecting
`padding: 9px 0 9px 14px` on `.money-row` failed exactly the 8 screens that
render it — `costs` and `split` × 4 variants — at 0.265–0.332% of pixels with
peaks of 221–229, and nothing else.

The first attempt at that test was itself a no-op: `padding-left: 14px` placed
*above* the existing `padding: 9px 0` shorthand is reset by it, so the gate
passed and looked broken. Worth knowing before concluding the gate missed
something.

## The baselines are machine-specific by decision

Captured on one machine at a fixed 1440×900 viewport with
`--force-device-scale-factor=1`. Cross-platform font rendering is what makes
image gates flaky, so a capture from another machine is not comparable to these
and re-approving is the correct response to changing machines — not widening
the tolerance. Changing a viewport invalidates every approved image at that width.

Chrome needs two macOS workarounds, both in `capture()`: it writes the
screenshot and then never exits, so the return code is not a usable signal and
the file itself is judged; and `--headless=old` returns rc=1 without writing.

The whole capture set also shares one temporary Chrome profile. Trip ownership is
stored in localStorage, so creating a profile per image let the first image claim
the scratch trip and made the other 55 quietly photograph `Trip not found`.
`CaptureOwnerSessionTest` pins the shared profile. Capture mode also suppresses the
one-time plan-ready dialog; otherwise every itinerary baseline covers the modal
instead of the interactive dashboard it is meant to protect.

## The capture renders live app state, so look before approving

These are screenshots of the running app against the real database, not of
static markup. Whatever the app is honestly showing at capture time is what
gets frozen — including a failure.

Measured 2026-08-07. A capture taken that morning baked a provider-error banner
into `/places`: *"The provider could not return a current catalog."* It was not
a capture bug and not a rendering glitch. The discovery cache had passed its
7-day TTL on 2026-08-06 05:20, the refresh attempted minutes later hit Overpass
`HTTP 504` because its two concurrent slots were spent, and the run fell back to
the expired cache with `status: "stale"`. The app was right to say so; approving
that image would have made "the catalogue is stale" the baseline for `/places`
and hidden the banner's later disappearance.

Re-running discovery cleared it — `verified`, 849 candidates, 51s — and the
`/places` diff dropped back inside tolerance on its own. So:

- **Open the changed images before `--approve`.** A diff that is large and
  unexplained is usually state, not styling.
- **Reject `Trip not found` and full-screen plan-ready dialogs.** They are capture
  state, not acceptable itinerary baselines.
- **Check `get_latest_discovery(...).status` is `verified` first.** A `stale`
  run means the banner is on screen.
- Data changes legitimately move these images. Confirming the accommodation base
  alone moved `/evidence` by 13.9%, and a new plan version moves `/itinerary` by
  0.2% through the version id and snapshot timestamp in its header.

## What the 1440×900 viewport cannot see

Anything below the fold. `/places` grew a stay-area ranking (`WF-040`) under the
swipe deck and `/optimize` grew a comfort-acceptance control (`WF-039`), and
**neither appears in any baseline** — the deck card and the plan summary fill the
viewport above them. The gate is not evidence about those sections in either
direction. Recorded rather than worked around, because changing the viewport
invalidates all 44 desktop images and is `WF-025`'s decision to revisit, not a capture setting.

## The gate now refuses a capture older than the code

Added 2026-08-07 after this failed three times in one day. Capturing is manual, so the
comparison stage compares whatever was last written to `screen-current` — and three times
that was an image taken before the frontend changed, while the stage printed **PASS**
having compared nothing relevant. A green gate that tested nothing is worse than a red
one, because it is trusted.

`check_screen_baselines.py` now lists every `.tsx`, `.ts` or `.css` file under `web/src`
modified after the **oldest** capture, and fails naming them and the command that fixes
it. Oldest rather than newest because the 136 images are written over several minutes; an
edit landing mid-run would otherwise be judged only against the screens photographed after
it.

## Four features this gate cannot see

Everything below the 1440×900 fold, and that is now most of what was built on 2026-08-07:

- `/places` — the stay-area ranking (`WF-040`), under the swipe deck
- `/optimize` — the comfort-acceptance control (`WF-039`), under the plan summary
- `/evidence` — the venue-notice card (`WF-044`), the fifth card down
- `/itinerary` — the drift banner (`WF-045`) renders **only when the plan has drifted**,
  which the pilot's has not, so no baseline will ever contain it

Recorded rather than worked around: widening the viewport invalidates all 44 desktop images and is
`WF-025`'s decision to revisit. But the erosion is worth knowing — a passing screen gate
now says less about this app than it did in August.
