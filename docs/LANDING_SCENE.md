# The landing page and its scenery

Rules for the marketing landing page and the SVG scenes on it. Moved out of `CLAUDE.md` on 2026-09-02
because only work on that page reaches them. **These are current guidance**, not history — the dated
story behind each is in `docs/JOURNAL.md` ("Three landing sections removed, and the estuary").

`CLAUDE.md`'s general interface rules still apply here: the three breakpoints, the 16px touch floor, the
`--measure-body` prose cap, and the design-token gate (`scripts/check_design_tokens.py`).

## Removing a section is not just deleting JSX

**The landing lost three sections on 2026-08-23** — "Why Mathematical Planning Beats Generic AI",
"Interactive Bill Settlement Engine" and "How Optimizer Compares" — at the owner's asking. Removing them
orphaned three nav buttons, two `useState` hooks, a whole bill-split computation, and **51 CSS rules**.
The surviving grouped selectors still name `.benefit-card` and `.comparison-table` alongside live
classes; those entries are inert and were left rather than picked apart. `splitCurrency` survived as a
plain const because the lab's conversion table still reads it — **check what a removed section *shared*
before deleting its state.**

## The closing section is `<ShoreScene />`, not a `SceneEnvironment` variant

A variant is a ridge anchored to the foot of a band; that section is 1046px tall, so as a variant it got
a wash with a strip along the bottom — 346 of 1046px at 0.68 opacity, against the world scene's 702 of
702 at 1.0, which is what it was asked to match. It is now the same construction as `.world-scenery`: one
full-height SVG, the shared `w-rough` presses, four `--depth` layers, grain last.

**`ShoreScene` is eight layers and four motion categories, all on existing machinery.**
`startWorldMotion` already provides `--scroll-y`, `.motion-ready` and `.in-view`; the parallax rates, the
staged reveal and the ambient loops are CSS on top of it, so no dependency was added and `WF-026` holds.
Every animation and every hover transform lives inside `prefers-reduced-motion: no-preference` — checked
by parsing the stylesheet, not by reading it — and capture mode freezes animation, so the baselines are
unaffected.

## `preserveAspectRatio`: `slice` for `ShoreScene`, `none` for `SceneEnvironment`

The difference is what each one draws. Abstract terrain is the one thing that tolerates stretching; a
lighthouse and a boat do not. Measured, `none` on this box distorts **20% at 1280x772, 46% at 1920 wide
and 276% on a phone**. `slice` never distorts and pays for it by cropping the sky, which is the right way
round for a background — but it means the section's own gradient and the SVG must agree about where the
horizon is, since the crop moves it.

**The inverse trap is just as real.** An earlier attempt used a 900-tall viewBox with
`preserveAspectRatio="none"`; sliced into a section-tall box the 1200-wide composition scaled **1.69x**
and cropped to viewBox x 220..979, putting the boat 60% outside the frame. A 900-tall box stretched into
a ~1046px band distorts about 1.16x, which is invisible. Know which one you are using and why.

## The composition is laid out around the cards, because they are opaque

Measured, the columns cover viewBox x 90..1110 / y 202..609 and the trust strip x 240..960 / y 636..845.
Anything worth seeing goes above 200 or below 610, and the waterline sits at 772 rather than 646 so there
is water to moor a boat on *outside* those rectangles. **Re-measure before moving an object**; twice now
something has been drawn correctly and been invisible.

**Do not shrink an object to fit a gap.** The boat was squeezed to 86 units wide to survive in the right
margin and the jetty flattened into a 56-unit band, both to keep them out from behind the cards. A
miniature crammed into a hole reads worse than a whole object half-covered — it is a *background*, and
the cards are translucent. Size objects to the scene; let the layout cover what it covers.

## The two cards are `rgb(from var(--bg-card) r g b / 86%)`, and 86% is a contrast budget

Computed across the range: 8% is invisible, 15% is the last value clearing 4.5:1, 20% fails. Note the
specificity — `.landing .stage-card` sets an opaque background later in the file at the same weight, so
the rule needs `.landing` on the front or it silently does nothing, which cost two rounds of "the
transparency is too subtle to see". And `.section-lead` takes `--text-primary` here: with the sky cropped
it sits on the bay, where secondary ink measured **2.87:1**.

## The scenery is `pointer-events: none` and only `.s-mark` takes events back

Three landmarks answer to a pointer by transforming *themselves* (lift, rotation, scale 1.03-1.06), never
a box-shadow. Verify by hit-testing real points on each shape rather than bounding-box centres — two of
three centres land on holes, which reads as a failure and is not one. The form's inputs must stay the top
element where they sit.

## The scene carries the reference's four signatures

It was short of all four. Compared path by path against `.world-scenery`:

- a bright edge on the distant mass (`w-snow` → `s-cliff`), or a silhouette reads as a cut-out;
- **two** halftone screens on the ground rather than one;
- colour landing in exactly one place (`w-bloom` → the buoys and shells);
- the **dashed route** — `.s-path` copies `.w-path`'s stroke, dash and cap unchanged, because the trail
  through the mountains and the trail along the shore have to be one idea.

## `--landing-estuary-*` is that section's palette and every value flips by theme

Seven tokens, because the landing's mountain tokens are fixed and a scene built from them is a bright noon
coast inside a dark page. The section's background gradient and the SVG fills read from the same tokens —
the sky in the gradient and the sky in the scene cannot be two skies. Light is midday; dark is dusk, with
the jetty the one lit thing. An earlier attempt mixed a fixed sky into `--landing-page` and put the
section lead at **1.1:1**; it is 6.7:1 and 6.3:1 now.

## Claims about the optimizer

**Grep the landing for `ILP`, `Branch`, `Optimality` and `Solve Time` before believing it describes this
optimizer.** `optimizer.py` is a greedy baseline plus an insertion search. Invented solver claims have
been removed twice and returned twice; they read like competence, which is what makes them hard to catch.
