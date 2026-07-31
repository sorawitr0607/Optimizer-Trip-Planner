---
id: WF-022
title: Decide the Streamlit freeze and pilot fallback rules
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
blocked_by: []
---

# Decide the Streamlit freeze and pilot fallback rules

## Question

What does "Streamlit is frozen" mean in practice, and by what date and criteria is it decided whether the
Taipei pilot runs on the webapp or on the frozen Streamlit app?

## Context

- Today is 2026-07-31. The pilot runs 29 December 2026 to 4 January 2027. Roughly five months.
- Slices 1–5 are built and evidenced; slice 6 (non-AI quick actions, then optional constrained GenAI
  revision, then the live pilot) is not built, and by this map's locked frame it will be built only in
  React. So the frozen Streamlit app can run the pilot **without** slice 6 — decide whether that is
  acceptable and what the owner loses on the trip if it happens.
- The webapp will change `pyproject.toml`, add an API layer, and potentially change the schema (see the
  migration ticket). A frozen UI that shares a moving core and a moving database is only frozen in the
  sense that nobody edits `views/`. Decide whether `views/` and `app.py` must keep passing their tests
  through Phase 2, or whether they are allowed to rot and the fallback is a git tag instead.
- The Streamlit UI tests are real coverage today: `streamlit.testing.v1.AppTest` paths with
  `TOURIST_DB_PATH` patched to a temp dir, and the documented gotchas about `switch_page`, per-language
  widget keys, and `shared.plain()` and Streamlit's `$`-as-LaTeX. Whether these keep running is entangled
  with the test-strategy ticket but the freeze decision comes first.

Decide at least: whether the fallback is a live maintained app or a tagged commit plus a restore
procedure; whether schema changes must stay backward-compatible with the frozen UI; the date of the
go / no-go call and who makes it; and the concrete gates the webapp must pass to be declared pilot-ready
rather than merely finished.

## Resolution comments

### 2026-07-31 — Question voided by an owner reframing; resolved under the new frame

Full reasoning, the timeline, the gates and the accepted consequence are in
[`022-streamlit-poc-retirement-and-pilot-commitment.md`](../artifacts/022-streamlit-poc-retirement-and-pilot-commitment.md).

**This ticket's question had no subject.** It asks whether the pilot runs on the webapp or on the frozen
Streamlit app. The owner's frame, stated this date: Streamlit was the **POC** that proved the planning
core works; the objective of every Phase 2 ticket is to move all of it into the webapp, merged with the
splitter and matching Auto-Bill's design; Streamlit is not essential; slice 6 is built as part of the
webapp; and validation compares against the **reference itinerary workbooks**, not Streamlit's output.

That is a destination-level change — it replaces a line the map listed as locked — and it is recorded
because the owner made it explicitly, not because this ticket claimed the right to.

- **Streamlit is a POC, not a fallback.** No tag, no downgrade path, no schema constraint. Everything the
  fallback framing implied is void, including the snapshot-payload one-way door that existed only so an
  old checkout could open a newer database.
- **`views/`, `app.py` and `ui/` stay in the tree, unmaintained, and are deleted when the webapp reaches
  parity across all 8 stages.** Deleting now would delete what is being ported *from*: nine stages of
  resolved interaction decisions plus `ui/text.py`'s 1,293 lines of `en`/`th` copy. There is no
  obligation to keep `views/` green.
- **Slice 6 is built as part of the webapp**, not as a separate phase. This dissolves rather than accepts
  the "never twice" problem: the Streamlit quick actions (`a7ad537`) and GenAI revision (`a2d59f6`) that
  shipped 2026-07-29 are POC code awaiting deletion, so no lasting duplication exists.
- **The webapp is the committed vehicle for the pilot** (29 December 2026 – 4 January 2027), with a
  **1 November 2026** checkpoint to catch slippage early. The commitment is ambitious on purpose: 14
  planning tickets are open and no webapp code exists yet. **If the checkpoint says not on track, Taipei
  is planned by hand in Excel** as the four reference trips were — the accepted consequence of having no
  software fallback, written down so the November conversation is short.
- **Pilot-ready means three gates:** the real Taipei trip planned end to end in the webapp; its output
  compared against the four reference workbooks; all 235 tests green. Gate 1 implies the webapp is
  essentially complete *before* 1 November, not on it.
- **Validation compares all four reference-workbook sheet types, programmatically.** The recurring sheets
  are `ตารางเวลา`, `ค่าใช้จ่าย`, `♢ To-Do List` and `☺ Things to Bring` — which is the merged app's entire
  output surface, so this validates the merge itself and not just the itinerary. `ค่าใช้จ่าย` sharing a
  workbook with `ตารางเวลา` is the owner's own four-trip precedent for merging the splitter in. Three
  difficulties are named in the artifact: `openpyxl` is not in the project environment and there is no
  dev-dependency group yet; the workbooks are inconsistent, so comparison must assert structural coverage
  rather than cell equality; and the comparison is real work that the slice-plan ticket must size.

Also corrects stale doc claims this ticket had to measure: 235 tests in ~13 s, not 202 in ~7 s
(`CLAUDE.md:9`, `:267`, map `:27`), and the "not yet built: all of slice 6" note in `CLAUDE.md`.
