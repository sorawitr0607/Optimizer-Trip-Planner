---
id: WF-026
title: Choose the webapp stack and project layout
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
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
