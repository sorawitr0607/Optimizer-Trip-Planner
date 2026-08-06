# The swipe deck: WF-036 built against WF-005

The owner remembered a Tinder-style interface being discussed, and they were right —
it is recorded in **`WF-005`, 2026-07-28**, under "Transparent swipe learning with
protected exploration". `WF-036` was the prototype ticket left open for it, deferred
past the pilot.

## Most of it was already built

`WF-005` specified a queue of "four highest-ranked unseen candidates followed by one
protected exploration candidate", and that rated cards keep their decisions while only
unseen cards reorder. **The core already does this.** Verified on the real 832-candidate
Taipei catalogue:

    ranked, ranked, ranked, ranked, protected_exploration, ranked, ranked, …

and all **111 already-decided places absent from the queue**. So nothing about
ordering or exclusion needed writing — `main_queue` arrives correct, and 86 cards
carry `protected_exploration`. What was missing was only the interface: `/places`
rendered a **selectbox**, which is exactly what `WF-036` called the problem.

## Swipe is the accelerant, not the mechanism

Every action is a real button and the arrow keys work. A gesture-only deck locks out
keyboard and screen-reader users, and that is not a simplification worth making.

It has a second benefit: because the buttons are the truth, `renderToStaticMarkup`
can test the entire contract — the 4:1 order, the required card content, the
exploration label, the gallery counter, the exhausted state. A gesture-only deck
would have been largely untestable in this suite.

The gesture maps right to `interested` and left to `not_for_trip`, matching the order
the buttons sit in, so the direction is learnable from the layout rather than needing
to be taught.

## Multi-image, free

The owner asked for a tappable gallery. `prop=images` on a Wikipedia article gives one
free list — **27 entries for Chiang Kai-shek Memorial Hall** — so a gallery costs one
extra request and **no money**. Capped at six, rasters only: an SVG on a Wikipedia
article is almost always an icon, a locator map or a flag, never a photograph.

The curated `P18` image comes first where there is one, then article photographs. The
photo itself is a `<button>` so a keyboard can advance it.

## WF-005's minimum card content

Rendered as a definition list, one labelled topic per row rather than run into a
sentence: visit estimate, feasibility, effort and access, crowd and tourist-trap
signals, cost and reservation. Plus the score out of 100, the name, the free
description with CC BY-SA attribution, and an explicit note on the exploration card
that it is "shown to widen the search, not because it scored highly" — so a low score
there is not misread as a bad recommendation.

## And the page around it

The deck first landed **620 px down the page**, behind the coverage report — which is
how the screen came to be "not user friendly" in the first place. The coverage report
is how you audit a discovery run, not how you choose a place, so it is now collapsed
behind a one-line summary. The whole deck fits on one screen: position, score, photo,
name, all five topics, and all five actions.

## What this does not do for *this* trip

The deck's first card is an *RC model airplane runway*. That is correct behaviour, not
a bug: `main_queue` excludes decided places, the owner has already chosen their 13
landmarks, and what remains is genuinely the leftovers. The deck will earn its keep on
the next trip, where 832 undecided candidates are exactly what it is for.

## Baseline note

One approval ran against a stale `screen-current` and reported `places-light-th` as
6.294% changed. That was the comparison set being older than the baselines, not
instability — recapturing both gave a clean pass. Worth knowing: `--approve` writes
the baselines only, so the comparison set has to be recaptured before the gate means
anything.
