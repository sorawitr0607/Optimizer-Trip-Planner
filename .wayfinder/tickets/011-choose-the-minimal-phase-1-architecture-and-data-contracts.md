---
id: WF-011
title: Choose the minimal Phase 1 architecture and data contracts
status: closed
labels:
  - "wayfinder:grilling"
parent: WF-MAP-001
assignee: user-and-root
blocked_by:
  - WF-004
  - WF-006
  - WF-007
  - WF-009
  - WF-016
---

# Choose the minimal Phase 1 architecture and data contracts

## Question

What smallest Python, Streamlit, SQLite, cache, secret, multilingual-content, optimizer, and export boundaries satisfy the proven Phase 1 behaviours while keeping reusable logic independent of the future hosted interface?

## Confirmed decisions

### 2026-07-29 — One local modular application

- Build Phase 1 as one local Python application with a Streamlit interface, application actions, a reusable planning core, SQLite persistence, provider adapters, and exporters.
- Keep Streamlit out of the planning core so a future hosted API or PWA can reuse the same setup, evidence, optimization, validation, revision, and export behaviour.
- Do not add FastAPI, React, Docker, Redis, background workers, or microservices to the POC.

### 2026-07-29 — Reproducible local runtime

- Target Python 3.12 and declare the application in one `pyproject.toml` with a committed `uv.lock`.
- Launch Phase 1 through one local Streamlit entry point with `uv run streamlit run app.py`.
- Do not require Docker or Conda for the personal POC.

### 2026-07-29 — Strict inward dependency direction

- Keep the dependency flow `Streamlit UI -> application actions -> planning core`.
- The planning core owns language-neutral trip models, preference evaluation, ranking, optimization, and deterministic validation.
- SQLite, provider HTTP clients, OpenAI, caching, PDF, Excel, poster, and map implementations remain outer adapters; the core never imports them.
- Application actions coordinate the core and adapters without embedding Streamlit session state or presentation formatting.

### 2026-07-29 — SQLite is the sole source of truth

- Keep authoritative structured state in SQLite: trip setup, members and preferences, candidates and selections, evidence and route snapshots, plan and revision versions, readiness checklist state, and paid-API usage.
- Treat raw provider responses as expiring, replaceable cache records rather than permanent truth.
- Generate the poster, map, PDF, and active-plan Excel from the active stored plan version. Exports never become a second editable state or get imported back as planning truth.

### 2026-07-29 — Immutable applied plan versions

- Every generated or accepted itinerary is an immutable plan version; a trip points to exactly one active version.
- Re-optimization, an accepted structured edit, or an accepted GenAI-assisted revision creates a new version linked to its parent and cause.
- Keep only one replaceable pending preview. Restoring an older plan creates a new active version based on that snapshot rather than mutating or deleting history.
- Stamp every poster, map, PDF, and Excel export with its plan-version ID so an old export can be identified accurately.

### 2026-07-29 — Versioned evidence and route inputs

- Each plan version references the exact normalized evidence and route snapshots used by its optimizer and validity checks.
- Each operational fact records the stable subject, fact type and value, provider and source, retrieval time, applicable local date or interval and timezone, confidence, conflict status, and optional raw-cache reference.
- Each route snapshot records its endpoints, mode, duration, distance, walking, transfers, provider, calculation time, and applicable departure context.
- Refreshing a fact or route creates a new snapshot; it never rewrites the inputs behind an older plan. Missing, stale, or conflicting inputs remain explicit and follow the established activation gates.

### 2026-07-29 — Provider-neutral normalized results

- Every worldwide-core or local-enrichment adapter converts provider payloads into stable domain records for places, operational facts, routes, review summaries, and weather.
- Give each result one explicit status: `verified`, `unavailable`, `stale`, `conflicting`, or `error`, together with its provenance, retrieval time, confidence, cache reference, and paid/free usage metadata where applicable.
- The planning core never receives Google, Overpass, Open-Meteo, Taiwan-specific, or other raw provider schemas, and never treats a missing value as a trustworthy default.
- Adding or replacing a city or provider changes adapters and configuration, not optimizer or validation rules.

### 2026-07-29 — Stable place identity and conservative deduplication

- Give each real place an internal `place_id`; provider-specific IDs are aliases, never the worldwide identity used by the planning core.
- Merge records automatically only when normalized name, coordinates or address, and category produce a high-confidence match.
- Keep ambiguous matches separate and visible for owner confirmation instead of silently merging different places.
- Preserve local-script and multilingual names, every provider alias, and every source link on the canonical place record.

### 2026-07-29 — Language-neutral facts and localized display text

- Store each structured fact, place identity, score, route, and schedule value once; keep user-facing names, descriptions, and instructions separately by language code.
- Switching between Thai and English changes only interface and export text, not candidate ranking, optimization, timing, or the active plan version.
- Fall back from the selected language to English and then the original local script. Retain the local-script place name and address wherever they help on-the-ground navigation.
- Preserve source text. Mark machine-generated translations with their origin and never let them overwrite provider or owner-authored text.

### 2026-07-29 — One SQLite read-through API cache

- Keep provider JSON and its cache metadata in SQLite, keyed by provider plus a deterministic fingerprint of the complete request, including language and other result-changing parameters.
- Apply expiry by data type and provider retention rules. A manual refresh bypasses the cached response and creates new normalized snapshots where needed.
- An expired response may support a visibly `stale` result but can never be presented to the optimizer or owner as `verified`.
- Store photo references rather than binary image blobs, and add no Redis or separate cache service for Phase 1.

### 2026-07-29 — Environment-only provider secrets

- Read API keys only from process environment variables. Allow a local gitignored `.env` for convenience and commit only an `.env.example` containing variable names and safe placeholders.
- At startup, show each provider as `configured` or `unavailable` without displaying any part of its secret value.
- Never persist or copy secrets into SQLite, cached payloads, logs, prompts, plan versions, generated exports, or error messages.
- Resolve credentials and redact provider errors at the outer adapter boundary; the planning core receives provider availability and normalized results, never credentials.

### 2026-07-29 — Pure snapshot-in, proposal-out optimizer

- Give the optimizer one complete input snapshot containing trip setup, owner and member preferences, candidates, owner selections, normalized evidence and routes, locks, weights, and thresholds.
- Return a proposal containing scheduled visits, travel legs, meals, rest and contingency buffers, objective-score breakdown, warnings, and every unscheduled item with its reason and consequence.
- The same input and optimizer/configuration version must produce the same proposal through stable tie-breaking.
- The optimizer never calls providers, SQLite, Streamlit, exporters, or GenAI and never persists its own result; application actions assemble the snapshot, validate the proposal, and store the preview or accepted version.

### 2026-07-29 — One immutable snapshot for every export

- An application action builds one immutable export snapshot from the exact active plan version, selected language, THB and destination-currency context, evidence refresh state, and display-ready facts.
- The daily poster, map, PDF, and active-plan Excel exporters all consume that same snapshot so their times, routes, warnings, costs, and status labels cannot diverge.
- Exporters never call providers, query or mutate SQLite, invoke the optimizer, or invent a missing value. A missing required field produces a precise export error.
- Exporting changes no planning state; each artifact remains stamped with its plan version and export context as already defined.

## Resolution summary

Phase 1 is one reproducible local Streamlit application with reusable language-neutral planning logic, SQLite truth and caching, provider-neutral evidence, immutable plan versions, environment-only secrets, a deterministic optimizer, and snapshot-only exporters. Taipei-specific providers remain outer enrichment adapters, so another city does not require changing the core rules.

All blockers are closed and every boundary named in the question is decided. Regression-fixture creation belongs to WF-010; the validation scorecard, runtime proof, and implementation handoff belong to WF-012.
