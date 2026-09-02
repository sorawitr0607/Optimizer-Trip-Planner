# Capturing and approving screen baselines

Rules for `capture_screen_baselines.py` and `check_screen_baselines.py`. Moved out of `CLAUDE.md` on
2026-09-02 because only a capture or approval run reaches them. **These are current guidance**, not
history — the dated story behind each is in `docs/JOURNAL.md`.

Three related rules stay in `CLAUDE.md` because an ordinary `check.py` run hits them without meaning to:
the `NODE_OPTIONS` preload it drops, the `.check.lock` that refuses a second run, and the
`FAILED: 1 screen(s) drifted` line that is a *unit test* proving the gate works.

## The run must reuse one Chrome profile *and* be handed the trip's owner token

Trip ownership is a `localStorage` token. Reusing one profile stops the images disagreeing with each
other; it does not make the run an owner, because a throwaway profile mints a *new* token on load and
`list_trips` filters on it.

With only the first half fixed, **52 of the 56 captures were the unknown-trip recovery screen** — every
stage route, both viewports, both themes, both languages — and **the gate passed on all of them**, because
an error page compared against an error page is clean. It sat green across three handoffs while covering
nothing, and "the screen baselines are approved" was reported as an achievement.

So `--owner` is **required**. `capture_screen_baselines.py` puts it on the URL as `baseline_owner`, and
`web/src/main.tsx` writes it to `localStorage` inside the same capture-mode block that already reads
`baseline_theme`. Get it with:

```bash
sqlite3 data/tourist.sqlite3 "select owner_token from trips where id = '<trip>'"
```

Capture mode also suppresses the one-time plan-ready dialog, so the itinerary baselines cover the
dashboard beneath it.

**Open changed images before approving them.** That rule already existed and would have caught the error
pages on any of the three occasions it was not followed. A blank-detector over the capture set is two
lines of Pillow and is worth more than reading the percentages.

## `--approve` writes the baselines and leaves `screen-current` alone

So running `check_screen_baselines.py` straight afterwards diffs the approve run against whatever capture
happened to be sitting there, and fails with percentages that look alarming and mean nothing. Measured: a
stale comparison reported `split` at 15-20% drift on code that had not touched it.

**Approve, then capture once more without `--approve`, then check.**

## `--virtual-time-budget` is 15000, and both directions of that number were measured

`/places` is the only screen whose content arrives asynchronously.

- At **5000** the deck is still showing "Looking it up on the map…". A loading placeholder is *stable*, so
  `stable_capture`'s two-identical-shots rule accepts it happily — one run caught the placeholder, the next
  caught the card, and the gate reported 2.9% drift on unchanged code.
- At **30000** it fails the other way: virtual time outruns the real network, a request aborts, and a
  "Failed to fetch" banner pushes the page down 29px for 12% drift, again on unchanged code.

**Bigger is not safer.** Re-measure before changing it, and remember that a stable-looking intermediate
state defeats the settle check entirely.

## The viewports

**The capture set has a third viewport, `t900-`**, because 500 and 1440 left the middle untested.
Consolidating the twelve stray breakpoints into three was a change no gate could have caught going wrong.
The phone set also covers **every** stage route now, not the four it began with.

**The phone capture's viewport is ~745px tall, not the 844 in its filename.** Headless Chrome sizes the
*window*, and its chrome eats the difference, so a 500x844 image carries about 99px of dead white below
the page — visible in a dark-theme shot, where the band stays white. A `position: fixed` bottom bar
therefore lands at y≈745 in the image and is correctly pinned all the same. **Do not "fix" it.**

**Headless Chrome clamps its window to a 500px minimum, so the `m500-` set is not a phone.** Driven at a
real 390px, `/itinerary`'s five `.plan-next-action` links measured **42px** while every capture said the
screen was fine. Measure the phone in a real browser before believing these baselines.

## Volatile data must be frozen, or the baselines drift on a schedule nobody chose

Anything wall-clock or build-stamped changes unchanged screens and forces unrelated approvals.

- **The visible build stamp** stays visible in the real interface, but `data-volatile="build"` freezes it
  under `baseline_theme`; otherwise every rebuild changes unchanged `t900-` screens by about 0.117%.
- **`TripNow` carries two wall-clock countdowns and both are `data-volatile="countdown"`** — "Departs in N
  days" and the "Next · 19:00 · in N days" line below it. On the departure line the whole phrase is frozen
  rather than the number, because `copyFormat` returns one interpolated string and splitting a sentence in
  two languages to hold three characters costs more than that line's width in the diff; the next-action
  line freezes just the gap, since the tag and clock time beside it are stable.

Freezing only the first countdown left them still drifting, which the recaptured image showed and the
reasoning had not: **open the changed capture before believing a freeze worked.**

## Any new remote image needs adding to the capture freeze list in `web/src/main.tsx`

It blanks `.place-deck-photo img`, `.place-about-photo`, `.place-insight img`, `.day-stop-thumb` and
`.day-stop-photo img`. Third-party pixels re-encode — a Wikimedia thumbnail failed this gate at peak 28
with nothing in the repo changed. The day-stop selectors were absent for as long as the only pictures
there came from an OpenStreetMap tag the fixture trip did not carry; the omission cost nothing until the
pictures arrived.
