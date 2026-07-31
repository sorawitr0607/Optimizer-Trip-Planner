# Streamlit POC retirement and the pilot commitment

Resolves `Decide the Streamlit freeze and pilot fallback rules` (WF-022).

Decided 2026-07-31. **The ticket's original question was voided by an owner reframing on the same date**,
recorded in full below. Every measured claim was verified against the checkout at `3b9cec5`. Paths are
repo-relative.

## The reframing that voided the question

The ticket asks "by what date and criteria is it decided whether the Taipei pilot runs on the webapp or
on the frozen Streamlit app?" **That question has no subject.** The owner's frame, stated 2026-07-31:

> Streamlit was the POC — it proved the planning core works. The objective of every Phase 2 ticket is to
> move all of it into the webapp, merged with the bill splitter and matching Auto-Bill's design. Streamlit
> is not essential now. Slice 6 is built as part of the webapp, not as a separate phase. Validation
> compares against the reference itinerary workbooks, not against Streamlit's output.

Streamlit is therefore **not a pilot vehicle at all**, and everything the fallback framing implied is
void:

| Voided | Because |
|---|---|
| "Frozen at slices 1–5 as the fallback Taipei pilot vehicle" | It is a POC, not a candidate |
| A git tag pinning the fallback | Nothing to pin |
| A documented downgrade path | Nothing to downgrade to |
| "Re-meaning a snapshot payload is a one-way door" | That constraint existed only to keep an old checkout able to open a newer DB |
| Capturing Streamlit reference exports as gate fixtures | The baseline is the reference workbooks |
| "Slice 6 built only in React — never twice" | With the POC deleted at parity there is no lasting duplication, so the rule is simply spent |

This is a **destination-level change**, not a ticket decision: it replaces a line the map listed as locked
and not open to re-litigation inside tickets. It is recorded here because the owner made it explicitly,
not because this ticket claimed the right to.

## The reference workbooks are the spec, not just a baseline

`data/reference-itineraries/` holds four hand-made trip workbooks with matching Thai timetable PDFs:

| City | Sheets |
|---|---|
| fukuoka | **ตารางเวลา** · **ค่าใช้จ่าย** · **♢ To-Do List** · **☺ Things to Bring** |
| japan | ตารางเวลา · Transport · ค่าใช้จ่าย · ♢ To-Do List · ☺ Things to Bring |
| kunming | ตารางเวลา · ค่าใช้จ่าย · ☺ Things to Bring |
| shanghai | ตารางเวลา · Disney · ค่าใช้จ่าย · ♢ To-Do List · ☺ Things to Bring |

**The four recurring sheets are the merged app's entire output surface.** That is the finding worth
carrying forward:

| Reference sheet | Merged app surface |
|---|---|
| ตารางเวลา (timetable) | itinerary, timeline, and the timetable export |
| ค่าใช้จ่าย (expenses) | the cost ledger **and** the split ledger |
| ♢ To-Do List | the readiness board |
| ☺ Things to Bring | packing items on the readiness board |

`ค่าใช้จ่าย` living in the same workbook as `ตารางเวลา` is the original, human-made argument for merging
the splitter into the planner — the owner has been keeping both in one document for four trips already.
The merge is not a new idea being introduced; it is the reference format being honoured.

The workbooks are also **evidence that a hand-made plan is a working alternative**: four completed trips
were planned this way, before any of this software existed.

## The five decisions

| # | Decision |
|---|---|
| 1 | **Streamlit is a POC, not a fallback.** No tag, no downgrade path, no schema constraint |
| 2 | **`views/`, `app.py` and `ui/` stay in the tree, unmaintained, and are deleted when React reaches parity across all 8 stages** |
| 3 | **Slice 6 is built as part of the webapp**, not as a separate phase and not twice |
| 4 | **The webapp is the committed vehicle for the Taipei pilot**, with a dated checkpoint on **1 November 2026** to detect slippage early |
| 5 | **Validation compares generated output against all four reference-workbook sheet types, programmatically** |

### 1–2. Why the POC stays in the tree until parity

Deleting it now would delete the thing being ported *from*. `views/*.py` holds nine stages of real,
resolved interaction decisions, and `ui/text.py` holds **1,293 lines** of `en`/`th` copy that the webapp
must carry over — `Decide the bilingual copy pipeline for the webapp` depends on it existing.

Accepted costs:

- **12 of the 15 test files use `streamlit.testing.v1.AppTest`.** Those tests either keep running against
  an unmaintained UI or get retired early; `Decide the test strategy after Streamlit AppTest dies` owns
  that call, and it now has a clear frame — the coverage is POC coverage, not product coverage.
- "Unmaintained but present" invites someone to repair it out of habit. Nobody should. There is no
  obligation to keep `views/` green.
- Dead code sits in the tree for months. Deletion at parity is the checkable moment that removes it.

### 4. The commitment, and what the checkpoint is for

The pilot runs **29 December 2026 – 4 January 2027**. The webapp is the committed vehicle. The
1 November checkpoint exists because the commitment is genuinely ambitious: **14 planning tickets are
still open and no webapp code exists yet**, and the target is a merged, design-matched, bilingual,
nine-stage application with a split ledger.

The checkpoint's criteria are the three pilot-ready gates:

| Gate | Test |
|---|---|
| **1. Real-trip dry run** | The actual Taipei trip planned end to end in the webapp: setup → discovery → ranking → optimization → activation → export. The real trip, not a fixture. Doubles as genuine trip planning, so the effort is not wasted |
| **2. Reference comparison** | Generated timetable, expenses, to-do and packing output compared against the four reference workbooks (§ below) |
| **3. Tests green** | All 235 Python tests pass. The core is shared, so this is table stakes rather than evidence |

**If the checkpoint says not on track, Taipei is planned by hand in Excel**, exactly as Fukuoka, Japan,
Kunming and Shanghai were. That is the accepted consequence of having no software fallback — not a
failure mode, just the pre-app baseline. It is written down so the November conversation is short.

### 5. The validation baseline

All four sheet types, compared programmatically rather than by eye, so the check is repeatable instead of
being done once and then skipped.

Three real difficulties, named up front:

- **`openpyxl` is not in the project environment.** It is importable from the system Python only, and
  `pyproject.toml` has no dev-dependency group at all today. Reading the workbooks in a repo check means
  creating one — a dev dependency, never a runtime one, so the four-runtime-dependency discipline holds.
- **The workbooks are hand-made and inconsistent.** `kunming` has no To-Do List; `japan` adds
  `Transport`; `shanghai` adds `Disney`. "Compare" therefore needs a tolerant definition: the comparison
  asserts that the generated output *covers the structure the reference uses*, not that sheets match cell
  for cell.
- **Structural comparison of a human spreadsheet against generated output is fiddly work.** It is a real
  task, not a checkbox, and `Lock the Phase 2 slice plan and validation scorecard` should size it.

The four Thai timetable PDFs stay useful for the thing a structural diff cannot see — visual and layout
judgement, which matters because design match is a hard requirement of this phase. They complement the
programmatic check rather than substituting for it.

## The timeline

| Date | Event |
|---|---|
| **2026-07-31** | Reframing recorded. Streamlit becomes a POC awaiting deletion. Fallback apparatus dropped |
| 2026-08 → 2026-10 | Phase 2 proceeds. Schema unconstrained. `views/` unmaintained and allowed to rot |
| **2026-11-01** | **Checkpoint.** Evaluate the three gates. Not on track ⇒ plan Taipei by hand in Excel |
| 2026-11 → 2026-12 | Polish the webapp for the trip |
| **2026-12-29 → 2027-01-04** | The Taipei pilot |
| At parity across all 8 stages | Delete `views/`, `app.py`, `ui/`, and the `AppTest` suite |

## What this hands downstream

| Ticket | What is now settled |
|---|---|
| `Decide the test strategy after Streamlit AppTest dies` | `AppTest` covers a POC, not a product. It may be retired without keeping `views/` green — there is no fallback depending on it |
| `Decide the migration path for existing trips and splitter data` | Schema is fully unconstrained. No downgrade path, no snapshot-payload one-way door |
| `Lock the Phase 2 slice plan and validation scorecard` | The outer deadline is the **1 November** checkpoint, the three gates are its criteria, and the reference-workbook comparison is a sized task with a dev dependency attached |
| `Decide the bilingual copy pipeline for the webapp` | `ui/text.py` survives until the copy port completes; deletion is gated on parity |
| `Prototype the merged cost and split screen` | `ค่าใช้จ่าย` in the reference workbooks is the human-made precedent for the merged money screen — consult it before designing |
| Every prototype ticket | The webapp must be essentially complete before 1 November for gate 1 to be passable |

## Stale claims corrected while measuring this ticket

| Location | Was | Now |
|---|---|---|
| `CLAUDE.md:9` | `202 tests, ~7s` | 235 tests, ~13 s |
| `CLAUDE.md` slice note | "**Not yet built:** all of slice 6" | Slice 6's quick actions (`a7ad537`) and GenAI revision (`a2d59f6`) shipped 2026-07-29 in the POC; only the live pilot is unbuilt |
| `CLAUDE.md`, map | "the 202 tests survive the redesign" | 235 |
| map, `CLAUDE.md` | "Streamlit is frozen … as the fallback Taipei pilot vehicle" | A POC, deleted at parity |
