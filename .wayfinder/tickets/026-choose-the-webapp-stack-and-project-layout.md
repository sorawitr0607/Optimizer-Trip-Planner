---
id: WF-026
title: Choose the webapp stack and project layout
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
blocked_by:
  - WF-019
  - WF-020
  - WF-021
---

# Choose the webapp stack and project layout

## Question

What is the frontend stack, the directory layout inside this repository, and the state and data-fetching
model — and what single command does the owner run to start the whole thing?

## Context

- Auto-Bill sets the baseline worth matching where there is no reason to differ: React 19, Vite 8, plain
  JavaScript with no TypeScript, `lucide-react` for icons, `exceljs` plus `file-saver` for export, ESLint
  with the react-hooks and react-refresh plugins, and no router, no state library, and no test runner at all.
  It is a two-screen app with no backend; the planner is eight stages with a gated pipeline and a real API,
  so some of those absences will not survive.
- The repository is Python-first: `uv` with a lockfile, `pyproject.toml`, `.python-version`. Adding `web/`
  means a second toolchain and a second lockfile in one repo, and `CLAUDE.md` currently documents a single
  test command for the whole project.
- The pipeline's gating is server-side truth, not client state: `shared.journey()` decides which stages are
  done and which is next, and `shared.require(stage, trip)` renders one clear next step instead of erroring.
  Whatever replaces those two helpers is the spine of the frontend, and it must read the same server-derived
  state rather than duplicating the rules in the browser.
- Streamlit's model was rerun-the-script; React's is not. The documented Streamlit workarounds — autosave
  via `on_click` callbacks because widget state is dropped when a widget stops rendering, per-language widget
  keys because the browser caches a closed selectbox's rendered text — describe problems that disappear, and
  a stack decision that pretends they still exist will carry dead complexity in.
- Tailwind is already chosen for tokens by the destination interview; the version and configuration style
  are not.

Decide at least: TypeScript or plain JavaScript; router choice or hand-rolled routing; server-state approach
for a local API; form handling for the five-step setup; where shared elements live in the tree; whether
`web/` builds are committed; the lint and format setup; and the launch story — one command or two processes.

## Resolution comments

### 2026-07-31 — Decided through the stack interview

Full contract, counts, dependency tally and what is deliberately left open are in
[`026-webapp-stack-and-layout.md`](../artifacts/026-webapp-stack-and-layout.md).

- **TypeScript**, **react-router**, **TanStack Query**, **Tailwind v4 configured in CSS**, **npm**, Node
  pinned by `.nvmrc`. `web/src/` is organised **by stage** with `shared/`, `api/` and `i18n/` beside it.
  ESLint with `react-hooks`, `tsc` for types, **no formatter**. Six web runtime dependencies, ten dev.
  **Python stays at four runtime dependencies.**
- **The journey spine must move into the core, and retiring Streamlit is what forces it.**
  `shared.journey()` is 74 lines of business logic in `ui/shared.py:160–233` — a layer now scheduled for
  deletion. It reaches into the **private** `_optimizer_input` (`:185`), invents the gap code
  `OPENING_EVIDENCE_MISSING` that the core never emits (`:198`), and re-implements the rated-place filter
  `rank_candidates` already enforces (`actions.py:461`). It becomes `PlannerActions.journey()`, the **51st**
  allowlisted method, replacing 4 round trips plus a private call. React cannot recompute it instead:
  `capability_gaps` needs that private method, and exposing it is the `save_plan_version`-class mistake
  `WF-019` barred. `shared.require()`'s rendering is presentation and stays in the view.
- **`retry: false` is TanStack's default here, as a safety configuration rather than a preference.** The
  library default of 3 retries would burn both of Overpass's 2 concurrent slots on a 34 s call and
  **double-spend paid calls against the US$10 cap**. Revalidate-on-focus is off for the same reason.
- **The setup form is one draft object, always sent whole — a correctness rule, not a style choice.**
  `save_setup` takes 18 arguments with no partial form and every field defaults to empty, so **a partial
  payload silently erases what it omits**. Five documented Streamlit workarounds (autosave callbacks,
  per-language widget keys, per-step widget seeding, the `st.form` avoidance, `shared.plain()`) exist only
  because of Streamlit's rerun model and **must not be ported** — carrying them over would be dead
  complexity.
- **`web/dist` is not committed**; `.gitignore` gains `node_modules/` and `web/dist/`. One wrapper command
  rebuilds when stale then serves `dist` and `/api` on one port, so CORS never exists in real use. The
  staleness rule is the piece to get right — it prevents `WF-019`'s named hazard of a stale build silently
  serving an old UI. Dev keeps two processes and needs the 120 s Vite proxy timeout.
- **Tailwind v4 because the tokens are already CSS custom properties** (23 light, 21 dark), so the port is
  a copy rather than a transcription, and `--shadow-*: initial` is an unambiguous clear. This also retires
  a defect in the token contract: `WF-020`'s warning says the shadow scale must be *overridden, not
  extended*, yet its code comment points at `theme.extend.boxShadow`, which in v3 **merges** with
  Tailwind's soft defaults — the exact outcome the warning says destroys the visual identity. The intent
  was right and only the pointer was wrong, but v4 removes the ambiguity. Consequence accepted:
  `WF-020`'s drafted JS config becomes reference material, not code.

Deliberately left open: which exporter survives (`WF-030`), the token values and parity gate (`WF-025`),
the stage→route mapping (`WF-028`), the i18n mechanism (`WF-027`), a frontend test runner (`WF-029`), and
the staleness rule's exact form.
