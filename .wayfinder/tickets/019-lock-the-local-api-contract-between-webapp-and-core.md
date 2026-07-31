---
id: WF-019
title: Lock the local API contract between the webapp and the planning core
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee: user-and-root
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

## Resolution comments

### 2026-07-31 — Decided through the API-contract interview

The full contract, every measured count, the 26-code refusal vocabulary with line numbers, and the
status map are in [`019-local-api-contract.md`](../artifacts/019-local-api-contract.md).

- **Transport: stdlib `http.server.ThreadingHTTPServer`, zero new runtime dependencies.** Threads need
  no special work because `store.connect()` already opens and closes a connection per operation. FastAPI
  was rejected on a measured cost: ~110 Pydantic classes duplicating existing dataclasses, whose failure
  mode is silently dropping a field. The escape hatch stays open *because* the style is RPC.
- **Style: RPC per action, `POST /api/<method>`.** Verified that none of the 56 public methods has a
  positional-only parameter, so `fn(actions, **body)` binds in every case and the transport can hold no
  business rule. REST was rejected because 39 methods are verbs, and `PUT /plan/active` would assert an
  idempotency that `activate_plan_preview` explicitly refuses.
- **The exposed surface is a literal allowlist — never introspection — because two methods must never be
  reachable.** `save_plan_version` writes an arbitrary snapshot as an activated immutable version with no
  optimizer validation, bypassing the whole activation gate; `record_paid_call` forges rows in the
  append-only paid ledger. Initial list: the 50 the Streamlit UI needs, minus those two.
- **Refusals become `PlannerRefusal(code, **detail)` raised by the core.** The 46 `raise ValueError` in
  `actions.py` are 45 owner-visible refusals collapsing into **26 stable codes** (one is an internal
  invariant that never escapes). It subclasses `ValueError`, so all 18 existing `except` sites keep
  working. This fixes a live **Phase 1** defect: a Thai owner reads English at every refusal today.
- **One generic `jsonable()` owns the wire shape.** `sha256` is exposed — the UI needs it for the
  stale-setup warning and as the export cache key — and **never accepted**, because the server already
  re-derives every hash itself. One contract test per dataclass is required, not optional.
- **Long operations block, with a persisted started-at marker.** Discovery already persists before
  returning and Streamlit already freezes for 34 s, so blocking is parity. The marker buys refresh-safe
  in-flight state and the duplicate-fire guard with no job registry. No progress percentage ever:
  Overpass emits no signal, and an invented percentage is fabricated evidence.
- **The boundary is guarded by requiring `application/json` plus a `Host` allowlist on `127.0.0.1`.**
  `application/json` is not CORS-safelisted, so cross-origin callers must preflight and get nothing.
  This is a security control with a comment saying so, because `set_paid_cap` and `delete_trip` are
  exposed RPCs — an unguarded local API is a money-loss and history-loss path.
- **Provider and paid status use `{status, code, detail}`, the same shape as a refusal.** `detail` is
  explicitly diagnostic. Keys cannot leak through it: verified they travel in `Authorization` headers,
  never query strings.
- **Dev proxies through Vite; real use is one Python process serving `web/dist` and `/api` on one port**,
  so CORS never exists. The 120 s timeout must be set on both `fetch` and the Vite proxy or discovery
  dies in dev only.

Left open deliberately, in §11 of the artifact: whether the 45-site `PlannerRefusal` migration is its
own ticket, given that it fixes a Phase 1 bilingual defect and so is **not** gated by the Phase 2
decision gate.
