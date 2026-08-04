# Slice 5 — quick actions, revise, readiness

Built 2026-08-04. Numbers are in `manifest.json`; this file carries the narrative and the decisions taken
while building. Closes the S5 row of `.wayfinder/artifacts/033-phase-2-slice-plan-and-scorecard.md`.

## The three closing checks

| Check | Where it lives |
|---|---|
| Quick actions produce a rebuilt variant with consequences shown | `S5RevisionGateTest` + the live walk |
| A revision applies and restores | `test_a_revision_applies_and_the_old_version_restores` |
| The readiness board generates and applies | `test_the_board_previews_before_it_applies` |

328 Python and 38 web tests, all 8 check stages green. No paid call, no new runtime dependency, and **three
new copy keys** — only the readiness summary counts needed labels.

## The deletion checklist is empty

S5 ports the last four behaviours artifact 029 called portable: the two readiness ones, the revision one,
and `costs_section_renders_and_saves`, whose screen has existed since S2. **All 14 are now asserted below
Streamlit**, so `views/`, `app.py` and `ui/` can be deleted at S6 without coverage dipping. No `AppTest`
original was deleted here — that is S6's job, as `WF-022` set out.

What remains for S6 is the parity gate itself plus artifact 029's three genuinely-UI tests: the paid-card
placement rule, the entry-point smoke test that changes subject to React, and the full journey walk.

## The GenAI surface is absent on purpose

`interpret_revision` is allowlisted and the transport would carry it, but `RevisePage` never calls it.
Artifact 033 defers constrained GenAI revision past the pilot: *"only the React surface defers. The non-AI
quick actions stay in scope — local, free, deterministic."* A test asserts the screen renders no textarea
and no interpret control, so the deferral cannot be undone by accident.

## What the live walk showed

Walked on a copy of `data/tourist.sqlite3`, never the original, which stayed at schema 12.

**Readiness** generated 13 items from the real Taipei trip and grouped them by timing bucket — *do now /
before booking*, *30 days before*, *7 days before* — each carrying its requirement level, progress,
evidence state, deadline, smallest-next-step consequence and responsible authority. Eleven category filter
chips, a progress control and a dismiss control per row, and dismissed items stay restorable. The summary
line reads `Verification needed · Open 13 · Required open 5 · Required, unverified 5 · Overdue 0 · Due soon 0`.

Generated titles interpolate their arguments and read in both languages — `Verify entry requirements for
Taipei, Taiwan` becomes `ตรวจสอบข้อกำหนดการเข้า Taipei, Taiwan จากแหล่งทางการ`. **The destination stays
unlocalized inside the Thai title**, which is the rule: a city name is the geocoder query, so localizing it
would change which place is searched.

**Revise** offered 9 quick actions. Running *reduce walking* rebuilt a variant and showed the whole
consequence set: changed days `2027-01-03, 2027-01-04`, a before/after/change table across all seven
dimensions with signed and coloured deltas, two moved stops with their old and new times, two removed, and
two displaced with reasons. Every one of those **names a place** — `Daxiangshan`, `Dailaokengshan`,
`Ejiaogeshan`, `Yuantanzikengshan` — never a truncated `place_id`, which is the whole point of that rule.

## One defect the walk caught

The board read **"Confirm with: attraction_operator"**. `expected_authority` holds a stable code, and all
six codes have catalogue entries, but the screen rendered the field raw. It now resolves through the
catalogue with a literal fallback, because the field also accepts owner-entered text. Both the before and
after captures are retained.

## A pre-existing gap recorded rather than fixed

The assumptions line reads `⚠ WALKING_MINUTES_PER_LEG_SET_TO_14`. That is **not** a port defect:
`revision.py` builds assumption codes with the value interpolated (`f"{key.upper()}_SET_TO_{tightened}"`),
so no static catalogue entry can ever exist, and the POC renders the identical `⚠ CODE`. The rendering is
the documented fallback — unknown codes surface visibly and are never prettified into copy-looking prose —
but it means that line is permanently machine output. Changing how a locked domain module names its
assumptions is outside S5 and needs its own decision.

## Decisions taken while building

- **`checklist_vocabulary` is the 60th allowlisted read.** The board needs the categories, requirement
  levels, timing buckets, progress and evidence states, none of which React could reach. Like
  `setup_vocabulary`, its orders are explicit lists asserted against the core tuples, so a new member cannot
  be added in `checklist.py` and silently miss the board. `TIMING_BUCKETS` carries meaning in its order.
- **A third `localName` was refused.** `places` and `optimize` already had one each with different
  signatures, and `revise` needed a third. They are now one `placeName` / `placeNameFrom` in
  `web/src/shared/names.ts` and the two duplicates are gone. Divergence in this rule is invisible until a
  screen shows an id, which is exactly the failure it is supposed to prevent.
- **The readiness summary shows five counts, not seven.** `total` and `dismissed` are derivable from the
  board itself and had no labels; adding copy for them would have been labels for numbers nobody reads.
- **No "warnings are non-blocking" notice.** `blocks_itinerary` is always false by decision, but that is a
  system guarantee rather than something to tell the owner on every visit, and the POC does not say it
  either. A test asserts the property instead.
- **`MAX_MEMBERS`-style hardcoding was avoided again.** Every vocabulary the board renders comes from the
  API with a drift guard rather than a TypeScript literal.

## What remains explicit

- **Apply and restore were witnessed at actions level, not in the browser.** Every variant on the real
  Taipei trip is `provisional` because opening evidence is missing, and `apply_revision` refuses unless the
  rebuilt variant is `ready` and valid. So the browser saw the **blocked** path — with its visible reason
  and a disabled Apply, which is the gate working — while apply-then-restore is proven on a historic
  fixture with verified hours. The same evidence limit S4 recorded for fresh-trip route evidence causes
  this; do not weaken the hard constraint to make a screenshot nicer.
- **The graph was not rebuilt.** `--check` passes at 1358 nodes and 3185 directed edges, but it does not
  know about the two new screens or `shared/names.ts`. Paid, and reserved for an explicit ask.
- **`data/tourist.sqlite3` is still at schema 12**, unchanged by this slice.
- **The `Auto-Bill-Splitter` pre-archive debt** — one backup JSON per trip and the 41 isolated element
  captures — is unchanged and still lost once the donor is archived. **S6 deletes the POC, so this is now
  the last slice before that window closes.**
