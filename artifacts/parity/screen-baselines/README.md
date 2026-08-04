# Approved screen baselines — 36 images

`WF-025` §2b: 4 baselines per route (light/dark × en/th) across the 9 routes,
approved once and then diffed on every change.

**What this gate catches: drift over time.** It does *not* prove parity with
Auto-Bill and must not be described as if it does — Auto-Bill has two screens
and the planner has nine, so a whole-screen comparison between them is
meaningless. Parity with the donor is `check_element_parity.py`'s job.

## Reproducing

```bash
uv run --locked python -m api                                    # serve on 8801
uv run --locked python scripts/capture_screen_baselines.py --trip <id>
uv run --locked python scripts/check_screen_baselines.py         # also check.py stage 8
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
the tolerance. Changing the viewport invalidates all 36.

Chrome needs two macOS workarounds, both in `capture()`: it writes the
screenshot and then never exits, so the return code is not a usable signal and
the file itself is judged; and `--headless=old` returns rc=1 without writing.
