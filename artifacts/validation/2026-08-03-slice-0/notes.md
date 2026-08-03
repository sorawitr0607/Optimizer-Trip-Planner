# S0 — the scope cut

Authority: `.wayfinder/artifacts/033-phase-2-slice-plan-and-scorecard.md` §0.
The first Phase 2 implementation work, and the first slice deliberately because it *removes* work from every
slice after it.

## What was cut

`exporters.py` **1136 → 692 lines**. Fourteen functions deleted, two outputs remaining: the six-sheet workbook
and the readiness ICS.

The PDF and poster turned out to be **coupled** — `plan_pdf` embedded the poster via
`pdf.image(day_poster_png(...))` — so cutting one without the other was never possible. That is why the plan
treated them as a pair.

## One thing preserved rather than deleted

Tracing found that **`_code()` was used only by `plan_pdf` and `_fallback_line`**, both of which were going —
so a naive cut would have deleted it, and with it the export family's only optimizer-code localisation. The
workbook wrote codes raw.

Losing that would have been a **silent behaviour regression** against a mandatory bilingual requirement: a Thai
owner would have started seeing `nearby_museum` where they previously saw Thai. So `_code()` was kept and
wired into the workbook's four raw-code sites, threading `words` into `_write_timeline` and `_write_choices` —
which follows the file's own existing pattern, since `plan_workbook_xlsx` already computed `words` and already
passed it to `_write_checklist` and `_write_costs`.

**This changed workbook content**, which is worth stating plainly rather than discovering later: the fallback
trigger now reads `Rain` instead of raw `rain`. That is what `plan_pdf` always produced, so the two outputs now
agree rather than disagreeing.

## Three corrections the build made to the plan

1. **230 tests, not 231.** The estimate missed `test_pdf_carries_the_appendix_and_a_cover_summary` in
   `test_checklist.py` — five tests delete, not four.
2. **`pillow` is not actually removed.** `streamlit` depends on it, so only `fpdf2`, `fonttools` and
   `defusedxml` left the environment. `pillow` waits for S6.
3. **S0's stated check named `scripts/check.py`**, which does not exist until S1. The existing commands were
   used instead.

## A pre-existing gap found and deliberately not fixed

The workbook writes **raw status and type values** — `confirmed`, `visit`, `buffer` — rather than the localised
`state_*` labels. A Thai owner sees English in those columns. This is **not** caused by the cut, so it was
recorded rather than fixed: S0 is a deletion slice, and the one extension made here was to prevent a regression
the cut itself would have caused. Fixing a pre-existing gap is different work.

## Gates

| Gate | Result |
|---|---|
| `unittest discover -s tests` | **230 OK** (was 235) |
| `run_optimizer_regressions.py` | PASS — 20 atomic, 7 interaction, 3 variants each |
| `validate_regression_fixtures.py` | PASS — 24 rules |
| `build_project_graph.py --check` | PASS |
| `check_provider_access.py --self-test` | PASS |
