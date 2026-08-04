# The reference workbook coverage gate

The last unbuilt gate in `WF-033`'s scorecard, and also its pilot-ready gate 2.
Everything else in that table was green; this one had never been written —
`openpyxl` was absent, nothing read `data/reference-itineraries/`, and no
evidence bundle covered it.

`scripts/check.py` is now **12 stages**, green in 17.7 s.

## Why this gate is worth more than its size

The four workbooks are four real trips — Fukuoka, Japan, Kunming, Shanghai —
planned by hand in Excel before any of this existed. Their recurring sheets are
the merged app's **entire output surface**, so comparing against them is what
validates the merge itself. And it is the only gate that measures against real
trips rather than fixtures.

`WF-022` is explicit that validation never compares against Streamlit's output,
which is now moot in the best way: Streamlit is gone, and this gate reads the
workbooks directly.

## The inconsistency is measured, not assumed

Coverage is structural, not cell equality, because the workbooks are hand-made
and disagree with each other:

| Sheet | Present in |
|---|---|
| `ตารางเวลา` | 4 of 4 |
| `ค่าใช้จ่าย` | 4 of 4 |
| `☺ Things to Bring` | 4 of 4 |
| `♢ To-Do List` | **3 of 4** — Kunming has none |

Column counts vary too: `ตารางเวลา` runs 8 to 18 columns, `ค่าใช้จ่าย` 5 to 9.
Shanghai's money sheet carries per-row `คนหาร` and `จ่ายแล้ว`; Kunming's carries
a pivot table instead. Japan has a `Transport` sheet and Shanghai a `Disney`
sheet — one-offs, so neither is a recurring type and the gate names them as out
of scope rather than silently ignoring them.

Any gate asserting cell equality against this set would be asserting that four
inconsistent spreadsheets agree. They don't.

## The Thai labels are citations, so they get validated

The gate cites ten recurring elements by a marker string that must appear in the
reference sheet — `หัวข้อ` for a cost line, `ค่าใช้จ่ายต่อคน` for per person, and
so on. Each marker is checked against the files **before** anything about the app
is compared. A mis-transcribed label fails on the *reference* side with "fix the
gate, not the app", rather than quietly passing having compared nothing.

That rule is here because of the element-parity gate: requiring a
`derives-from:` declaration was worthless until it *validated* the declaration,
and eight of eleven citations turned out to be wrong.

Negative-tested with `ค่าใช้จ่ายทั้งหมด` — a plausible Thai phrase for "total
cost" that appears in none of the four workbooks. The gate named it.

## One real finding, one false one

**Real: the Costs sheet had no per-person figure.** All four references put
`ค่าใช้จ่ายต่อคน` beside the total. Tracing it: `costs.totals()` already returned
`planned_per_person_thb`, `actions.cost_totals()` already passed the roster size
as headcount, and `build_export_snapshot` already carried the value into the
snapshot — measured at 4,800 THB on a 9,600 THB trip for two. Only the writer
omitted the row. So the fix is one line in `_write_costs`, and per artifact 023
the figure is `planned_thb / headcount` and never
`group_preference_weights`, which expresses taste and would charge the owner
half the trip.

**False: `checklist_ics` emitted no VEVENT.** The first run reported this as a
gap. It wasn't. The gate's own probe saved a setup with no trip dates, so no
readiness item got a `due_date`, and `checklist_ics` correctly emits events only
for dated items. The probe was wrong, not the app. Fixed by passing the
fixture's `local_dates`.

Worth recording because the two findings looked identical in the output, and
"fixing" the second would have meant changing correct code to satisfy a broken
probe.

## Why the gate and a unit test both exist

The gate asserts the **label** is present. It cannot see whether the number under
it is right. Injecting `total_thb` under the heading `Per person THB` — right
label, wrong figure — **passes the coverage gate**.

So `test_costs_sheet_carries_the_per_person_figure_the_references_all_have`
asserts the value: three travellers, 9,000 THB, per person 3,000 and not 4,500.
It fails on that injection. Neither check subsumes the other.

## Scope

This gate answers "does the app carry a counterpart for each recurring element",
which is what `WF-022` asked for. It does not judge wording, layout, or whether
the app's figures are *correct for a given trip* — the export tests and the
optimizer regressions do that. Pilot-ready gate 1, the real Taipei trip planned
end to end in the webapp, remains the thing this cannot substitute for.
