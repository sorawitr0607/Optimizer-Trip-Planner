---
id: WF-022
title: Decide the Streamlit freeze and pilot fallback rules
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
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
