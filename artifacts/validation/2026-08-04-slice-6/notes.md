# S6 — the parity gate, and the deletion

The last slice of Phase 2. Two levels of visual parity gate, then `views/`,
`app.py` and `ui/` deleted: 2,951 lines and one runtime dependency.

`scripts/check.py` is 11 stages, green in 16 s.

## The gate is two levels because one level would be meaningless

`WF-025` asks for parity with Auto-Bill, and the obvious reading — screenshot
the donor, screenshot the rebuild, diff — cannot work. Auto-Bill has two
screens; the planner has nine. There is no pairing to diff.

So the comparison is per element, and it compares **computed style values**
rather than images: exact, no tolerance, and it keeps working after the donor is
archived. The pairing comes from the `derives-from:` declarations, which
`check_design_tokens.py` validates against the donor catalogue — so a citation
cannot silently point at the wrong element. That validation was not
decoration: **eight of eleven element numbers were wrong** when it was added,
written from memory across S2–S6. One cited an element that does not exist.

The screen baselines are the second level and they claim less: 36 images, drift
over time only. Saying they prove parity with the donor would be false.

## A gate that has never failed is not a gate

Every gate added this slice was negative-tested, and two of them were wrong on
first run in ways that only failing revealed.

**The element gate reported 15 unexplained differences, all artifacts of my own
harness.** Border width and style are positional on a list row — a dashed
separator with `:first-child { border-top: 0 }` captures as `0px` for whichever
row happened to be recorded first — so comparing them measured DOM position,
not parity. And the pairing had been inferred from the nearest `className`,
which picked a filter *container* instead of the chip inside it. Excluding
positional borders and requiring an explicit `as .planner-class` fixed both.

**The screen gate failed four screens on an unchanged app.** That is worse than
no gate, so both causes were fixed rather than absorbed by widening the
tolerance:

- `setup-dark-*`, 49 % of pixels but a peak delta of only 10–25. The same pixel
  read `(79,78,78)` in one shot and `(64,64,64)` in the next — the screenshot
  was landing part-way through `body`'s 300 ms theme fade. Capture mode now
  injects a stylesheet disabling transitions, so there is no intermediate state
  left to photograph.
- `readiness-*-th`, 0.15 % of pixels with a peak of 229, confined to bbox
  `(325,114)–(1280,501)`. The board was still loading. `stable_capture()` now
  requires **two consecutive byte-identical shots**, which is the only check
  that actually tests "has this settled" — the previous file-size settle test
  passes happily on a complete PNG of the wrong moment.

Then the negative test: 14 px of left padding on `.money-row` failed exactly
the eight screens that render it, `costs` and `split` × 4 variants, at
0.265–0.332 % with peaks of 221–229. Nothing else moved.

That test was itself wrong the first time. `padding-left: 14px` placed above the
existing `padding: 9px 0` shorthand is reset by it, so the gate passed and
looked broken. Worth knowing before concluding a gate missed something.

## Two accents failed the contrast floor

`check_design_tokens.py` enforces 3:1 rather than reporting it, and that caught
`united-states` at **1.81:1** and `united-kingdom` at **2.47:1** on dark — both
used for buttons. Dark-scoped overrides fixed them. A gate that reports a
number nobody reads is a gate that does nothing.

## What the deletion actually cost

Nothing in the core, which is the point: the no-UI-imports rule in
`core.py`/`optimizer.py`/`ranking.py`/`setup.py`/`discovery.py` is exactly what
made replacing the entire interface survivable, and `shared.journey()` had
already moved into `PlannerActions.journey()`.

18 tests used `AppTest`. Removing them properly meant removing **7 whole test
classes** (their every test was UI) plus 11 individual methods and 2 module-level
`AppTest` helpers — a method-level pass alone left six files that would not
parse.

Three things a blind deletion would have got wrong:

1. **`test_owner_can_go_from_new_trip_to_every_export` is not a UI test.** Its
   body drives `PlannerActions` directly; only two sections used `AppTest`, and
   those clicks called `generate_plan_preview` and `activate_plan_preview` and
   nothing else. The walk was kept and repointed at those two methods. Artifact
   029 classified it as genuinely-UI; measured against the source, it wasn't.
2. **`test_every_interface_string_exists_in_both_languages` imported `ui.text`**
   — a re-export shim. The bilingual key-parity test is a locked requirement, so
   it was repointed at `travel_planner.copy`, the catalogue both renderers read.
   Its `shared.plain` half asserted two things: that a refusal code has Thai
   prose (kept, directly on the catalogue) and that `$` was escaped for
   Streamlit's markdown (dead with Streamlit). Rendering a code with a `⚠`
   fallback is already asserted on `exporters._code` in `test_exports.py`.
3. **Three surviving tests in `test_checklist.py` imported `ui.text` too**, via
   an `_app_text()` helper. Found by running the suite, not by grep alone.

`pillow` was the other trap. It was only ever installed transitively through
streamlit, and the screen-baseline gate reads PNGs with it — so declaring it in
`[dependency-groups] dev` before the deletion is what stopped the new gate
breaking the moment the POC went. Runtime dependencies are now **one**:
`xlsxwriter`, for the workbook.

## Artifact 029's three genuinely-UI tests

All three were resolved before anything was deleted, none by dropping it:

| Test | Where it lives now |
|---|---|
| `each_paid_enrichment_offers_its_own_card` | `web/src/stages/s4.test.tsx` — "paid cost before its button" |
| `streamlit_entry_point_renders` | `web/src/routes.test.tsx` — nine routes, five gate keys |
| `owner_can_go_from_new_trip_to_every_export` | actions-level body kept; its eight-page render loop is the 36-screen capture |

The entry-point test is the interesting one. It "does not die, it changes
subject", and the subject is the route table: nine stage routes in the decided
order resolving to exactly five gate keys. Neither half is visible from a
screen — a dropped route is a 404 nobody notices until they navigate there, and
a gate key drifting to a sixth value silently changes which stage blocks which.
Both failure modes were injected and both were caught.

The route table is exported as data and `main.tsx` builds the router from it,
because `createBrowserRouter` reads `window.history` at construction and Vitest
runs in the node environment. Adding jsdom to check a nine-row array would have
been the wrong trade.

One test died with no replacement: `money_on_screen_is_not_read_as_maths`.
Streamlit read a pair of `$` as inline LaTeX and silently swallowed the amounts
in `US$0.1300 / US$10.00`. There is nothing left for it to protect against.

## Honest gaps

- **`graphify-out/` still describes `app.py`, `views/` and `ui/`.** `--check`
  passes, so this is not corruption; a rebuild is paid (~US$0.07) and was not
  run.
- **`data/tourist.sqlite3` is still at schema 12** and bumps on first real open.
  That remains the owner's deliberate act.
- **Neither bundled font has a Thai subset.** Thai falls through per glyph to a
  system font, exactly as before, so a Thai screen baseline is only stable on a
  machine with the same system fonts. This is part of why baselines are
  machine-specific by decision.
- **Pre-existing dead code was left alone**: `unicodedata` in `test_exports.py`,
  `ROOT` in `test_interpret.py`, `ROOT` and `patch` in `test_usage.py`. All were
  already unreferenced before this slice; only orphans this change created were
  removed.
- **The screen baselines are 3.1 MB in the repository.** That is the cost of the
  gate existing at all.
