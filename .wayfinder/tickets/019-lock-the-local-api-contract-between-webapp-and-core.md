---
id: WF-019
title: Lock the local API contract between the webapp and the planning core
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
blocked_by: []
---

# Lock the local API contract between the webapp and the planning core

## Question

What is the exact shape of the thin local HTTP layer between the React webapp and `PlannerActions` — its
framework, its endpoint style, how it carries the snapshot hash gates, how it reports failure, and how it
survives a request that legitimately takes half a minute?

## Context

- `travel_planner/actions.py` (1564 lines) is already the only coordinator: it assembles snapshots, calls
  the core, and persists. It holds no Streamlit state and no presentation formatting, so it is the natural
  API surface. The layer being added is a transport, not a second coordinator — new business rules landing
  in it would break the one-way dependency direction that `CLAUDE.md` documents.
- `pyproject.toml` currently lists `streamlit` as the only runtime dependency, by decision. This ticket
  necessarily changes that; decide the smallest thing that works. `http.server` from the standard library,
  Flask, and FastAPI are all real candidates and the choice has consequences for typed schemas, validation,
  and the test strategy.
- The pipeline is gated stage by stage on matching hashes (`_current_choice_inputs`): discovery stores
  `setup_sha256`; ranking and optimization refuse to run when it no longer matches the confirmed setup;
  `activate_plan_preview()` refuses unless `input_sha256` still matches and the variant is `ready` and
  valid. Those refusals are the safety model and must be expressible over HTTP, not softened by it.
- A dense-city Overpass discovery run takes about 34 seconds; the query declares `[timeout:90]` and the
  socket allows 105 s. The endpoint grants 2 concurrent slots and answers 504 immediately once spent, so
  retries must be spaced. Streamlit hid this behind a rerun; HTTP will not.
- Paid provider calls route through `actions._spend()` against a US$10 monthly cap with a warning at $8
  (`travel_planner/usage.py`). Nothing in the transport may bypass `_spend`, and a browser that can
  trigger paid calls by refreshing is a new failure mode Streamlit did not have.
- Secrets are environment-only. No key may cross to the browser, and `freeze_snapshot()` already refuses
  secret-bearing keys — decide what the API returns for provider status without leaking configuration.

Decide at least: RPC-per-action versus REST resources; request and response schema ownership; the error
taxonomy the frontend can rely on (the free-text revision path already names its causes —
`missing_credentials`, `offline`, `refused`, `invalid_reply`, `rate_limited`, `api_error`); how long
operations report progress or completion; whether the API is single-tenant-by-assumption or checks
anything; and how the dev server proxies to it.
