---
id: WF-MAP-002
title: Merge the bill splitter and rebuild the planner as a webapp
status: open
labels:
  - "wayfinder:map"
tracker: local-markdown
---

# Merge the bill splitter and rebuild the planner as a webapp

## Destination

Reach a decision-complete, implementation-ready Phase 2 specification for two joined changes: absorbing
`Auto-Bill-Splitter` into this repository as a group split ledger linked to the existing cost ledger, and
replacing the Streamlit UI with a local React webapp whose visual design is anchored to Auto-Bill's.
Implementation begins only after this map has no unresolved decisions. Prototypes produced while
resolving tickets are throwaway artifacts, not the build.

> **Reached 2026-08-03. This map is decision-complete and the Phase 2 code freeze has lifted.**
> [Lock the Phase 2 slice plan and validation scorecard](tickets/033-lock-the-phase-2-slice-plan-and-validation-scorecard.md)
> is the handoff artifact — read it first. **It stays `status: open` deliberately**, by owner decision, because
> [Prototype the ranked candidate card grid](tickets/036-prototype-the-ranked-candidate-card-grid.md) is
> **deferred past the pilot** and will be built later. An open map here means outstanding *prototype* work, not
> outstanding decisions: 18 of 19 tickets are closed and nothing on the frontier is a decision.
> **All seven slices are complete as of 2026-08-04.** S6 landed the two-level visual parity gate and
> deleted `views/`, `app.py` and `ui/`; the reference-workbook coverage gate followed, which was the last
> unbuilt gate in the scorecard. `scripts/check.py` is 12 stages. Closed-slice evidence is in
> `artifacts/validation/<date>-slice-<n>/` and `artifacts/validation/2026-08-04-reference-coverage/`.
>
> **What remains is not construction, it is the pilot.** `WF-022`'s gate 1 — the real Taipei trip planned
> end to end in the webapp, not a fixture — is the open item, judged 1 November 2026. `data/tourist.sqlite3`
> was bumped 12 → 13 on 2026-08-04 with `data/tourist-pre-v13-2026-08-04.sqlite3` kept as the only way
> back, deliberately **before** the 29 December – 4 January freeze, which is the trip's own dates.

## Notes

- Domain: local, owner-led trip planning plus group expense splitting, one repository, Python planning
  core behind a thin local API, React frontend.
- Locked by the destination interview (2026-07-31), not open for re-litigation inside tickets:
  - The Python planning core, `actions.py`, and `store.py` remain the domain layer. A thin local HTTP layer
    exposes `PlannerActions`. React replaces the `views/`, `app.py`, and `ui/` presentation surface. The
    deterministic optimizer, hash gates, append-only history, and the current Python suite survive the redesign.
  - **Two linked ledgers.** Planner cost rows stay the budget/estimate truth; the split ledger records
    actual group spend keyed to the trip. Their claim-once reconciliation contract is decided and lands in S2.
  - Everything lands in `Optimizer-Trip-Planner` (`api/` + `web/` beside `travel_planner/`).
    `Auto-Bill-Splitter` becomes a read-only donor — lift its tokens, elements, and split math — then
    it is archived.
  - The design tokens are **rebuilt** in Tailwind / CSS modules rather than lifted verbatim, so visual
    parity with Auto-Bill is a hard, gated requirement: same palette, same hard offset shadows, same
    fonts, same elements. Drift is a defect, not a style choice.
  - Bilingual `en`/`th` is mandatory. The shared JSON catalogue serves both Python and the webapp, the core
    keeps emitting stable codes, and the key-parity test keeps running. Auto-Bill-derived elements gain Thai
    strings they never had.
  - Local-only, single owner: `localhost` API plus local frontend, SQLite on disk, no accounts, no auth.
  - **Streamlit is the POC that proved the core works — not a product and not a pilot fallback.** It stays
    in the tree unmaintained while the webapp is built, and `views/`, `app.py` and `ui/` are deleted once
    the webapp reaches parity across all 8 stages. Slice 6 is built as part of the webapp, so the earlier
    "never twice" concern is spent rather than traded away. **The webapp is the committed vehicle for the
    pilot**, with a 1 November 2026 checkpoint; if it is not on track, Taipei is planned by hand in Excel
    as the four reference trips were. Superseded the original freeze-and-fallback framing by owner
    decision on 2026-07-31 — see [Decide the Streamlit freeze and pilot fallback
    rules](tickets/022-decide-the-streamlit-freeze-and-pilot-fallback-rules.md).
- The Phase 1 "why" lives in [`map.md`](map.md) and its 17 closed tickets. Read the relevant ticket
  before contradicting a scoring weight, optimizer rule, schema choice, or provider policy. This map
  may re-decide the UI; it may not silently re-decide Phase 1's planning contracts.
- Consult Wayfinder, Grilling, and Domain-modeling for decision work; Prototype for the screen tickets.
- Refer to tickets by linked title, never by a bare ID.

## Decisions so far

<!-- Closed-ticket index. The detailed decision belongs in its ticket. -->

- [Extract the Auto-Bill design token contract](tickets/020-extract-the-auto-bill-design-token-contract.md) —
  **Reopened 2026-07-31, completed 2026-08-03.** The parity gate made this contract the *target* the rebuild
  is measured against, and re-measuring found the blind spot larger than stated: **39** JSX classes with no CSS
  rule across **114** inline style sites. §10 of the artifact now extracts that layer, and the split is the
  finding — **23 styled only inline, 16 carrying no styling at all**, so a third of the "missing" classes were
  never visual. **No hardcoded colour appears in any inline site**, which puts the off-token colour problem
  entirely in the stylesheet (41 literals, 75 uses). The five undocumented alphas are confirmed as
  `10 12 15 30 40`, nine inline font sizes form an unacknowledged type scale, and six inline radii collapse to
  one under the `2px` unification. It also corrected two of my own earlier claims: Auto-Bill has **no tab
  element**, and `/split`'s allocation-mode views are **bare containers** whose layout must be designed rather
  than recovered. Output shape is custom properties in `tokens.css`, not the drafted v3 JS config.
  The visual language is captured in [`020-auto-bill-token-contract.md`](artifacts/020-auto-bill-token-contract.md):
  23 light / 21 dark custom properties, a zero-blur hard-offset shadow scale that must **replace** Tailwind's
  soft default rather than extend it, 5 desktop-first max-width breakpoints, a 13-country inline accent
  override, and — in §10 — the inline-only layer. Its seven ambiguities are **all ruled on**, not open: two
  dissolve into the `2px` radius unification, four became deviations D1/D3/D5/D6, and faux bold became D8.
- [Inventory the Auto-Bill elements each planner stage needs](tickets/021-inventory-the-auto-bill-elements-each-stage-needs.md) —
  Auto-Bill supplies 41 reusable elements; 18 planner elements have no counterpart but only the numbered map
  falls outside what the visual language can reach. The biggest design gap is the ranked candidate card, which
  the port *unlocks* rather than ports; the biggest surprise is that Auto-Bill has no inline feedback element
  at all against the planner's 59 status calls, while the US$10 spend meter is a free adapt of the per-person
  meter. 14 of 23 load-bearing behaviours are product decisions that must survive, 9 are Streamlit artifacts
  that die — 3 of those leaving a rule behind. Full matrix and the six-item dead-weight list are in
  [`021-element-inventory-matrix.md`](artifacts/021-element-inventory-matrix.md).
- [Define the split ledger model and where its math lives](tickets/018-define-the-split-ledger-model-and-where-its-math-lives.md) —
  A split row records who paid (defaulting to the cardholder), the split mode plus traveller-id participants
  with shares recomputed on read, an amount in its original currency with an optional permanent `actual_thb`
  lock, an owner-defined tag, and optional day and place links. All math lives in a new pure
  `travel_planner/split.py`; settlement is a star through the cardholder with fronted cash netted off, which is
  exact. Rows are editable and void rather than delete — so the ledger needs **no** append-only discipline.
  Settling up is not recorded, so balances stay trip-to-date totals.
- [Lock the local API contract between the webapp and the planning core](tickets/019-lock-the-local-api-contract-between-webapp-and-core.md) —
  A stdlib `ThreadingHTTPServer` with **zero new runtime dependencies**, dispatching `POST /api/<method>` RPC
  straight onto `PlannerActions`; verified that none of its 56 methods has a positional-only parameter, so the
  transport can hold no business rule of its own. *(56 was the class's public method count when charted, now
  63 with 59 allowlisted. Re-checked after S4: still no positional-only parameter on any allowlisted method,
  so the finding stands.)* Full contract, measured counts and status map in
  [`019-local-api-contract.md`](artifacts/019-local-api-contract.md). Three findings outrank the framework
  choice: the exposed surface must be a **literal allowlist**, because `save_plan_version` would write an
  arbitrary snapshot as an activated immutable version with no optimizer validation and `record_paid_call`
  would forge append-only ledger rows — introspection would have exposed both. The 46 `raise ValueError` in
  `actions.py` collapse into **26 stable codes** behind `PlannerRefusal`, which fixes a live *Phase 1*
  bilingual defect: a Thai owner reads English at every refusal today. And the boundary is guarded by
  requiring `application/json` plus a `Host` allowlist, which is a real security control rather than
  hygiene, since `set_paid_cap` and `delete_trip` are exposed RPCs. Hashes are **exposed and never
  accepted**; long operations block behind a persisted in-flight marker and never invent a progress
  percentage, because Overpass emits no signal to report.
- [Decide the Streamlit freeze and pilot fallback rules](tickets/022-decide-the-streamlit-freeze-and-pilot-fallback-rules.md) —
  **The ticket's question was voided by an owner reframing**: Streamlit is the POC that proved the core
  works, not a pilot vehicle, so there is no tag, no downgrade path and no schema constraint. It stays
  unmaintained in the tree — `views/` need not stay green — and is deleted at 8-stage parity. Slice 6 is
  built as part of the webapp. The webapp is the **committed** pilot vehicle with a **1 November 2026**
  checkpoint; not on track means Taipei is planned by hand in Excel, as the four reference trips were.
  The finding that outlives the ticket: the reference workbooks' four recurring sheets — `ตารางเวลา`,
  `ค่าใช้จ่าย`, `♢ To-Do List`, `☺ Things to Bring` — **are the merged app's entire output surface**, so
  they validate the merge itself rather than only the itinerary, and `ค่าใช้จ่าย` sharing a workbook with
  `ตารางเวลา` is the owner's own four-trip precedent for merging the splitter in. Validation is
  programmatic against all four sheet types; details and the accepted consequence in
  [`022-streamlit-poc-retirement-and-pilot-commitment.md`](artifacts/022-streamlit-poc-retirement-and-pilot-commitment.md).
- [Choose the webapp stack and project layout](tickets/026-choose-the-webapp-stack-and-project-layout.md) —
  TypeScript, react-router, TanStack Query, **Tailwind v4 configured in CSS**, npm with Node pinned;
  `web/src/` organised **by stage** beside `shared/`, `api/` and `i18n/`; ESLint with `react-hooks` and no
  formatter; `web/dist` uncommitted behind one wrapper command that rebuilds when stale and serves on a
  single port. Six web runtime dependencies, ten dev, and **Python stays at four**. Full tally in
  [`026-webapp-stack-and-layout.md`](artifacts/026-webapp-stack-and-layout.md). Three findings outrank the
  library picks. **The journey spine must move into the core**: `shared.journey()` is 74 lines of business
  logic in a layer now scheduled for deletion, and it reaches into the private `_optimizer_input`, invents
  a gap code the core never emits, and duplicates a filter `rank_candidates` already enforces — so it
  becomes the 51st allowlisted method, and React genuinely *cannot* recompute it instead. **`retry: false`
  is a safety setting, not a preference** — the library default would burn both Overpass slots and
  double-spend paid calls against the US$10 cap. And **`save_setup` erases what a partial payload omits**,
  so the whole-draft rule is a correctness requirement; the five Streamlit rerun workarounds it inspired
  must not be ported. Tailwind v4 was chosen because the tokens already *are* CSS custom properties, which
  also retires an extend-versus-override defect in the token contract.
- [Map every Streamlit stage to its webapp screen and route](tickets/028-map-every-stage-to-its-webapp-screen-and-route.md) —
  **9 stage routes under `/trips/:tripId/`, resolving to 5 gate keys, in 2 sections**, with the eight ported
  slugs unchanged from `st.navigation`. Full table in
  [`028-webapp-information-architecture.md`](artifacts/028-webapp-information-architecture.md). The trip id
  lives in the **path**, because all 51 methods take `trip_id` and TanStack keys must include it — ambient
  state would make ~51 query keys each *remember* it, and one omission serves another trip's cached data.
  **One `<StageGate>` wrapper and exactly one redirect**, because this is where a router would have quietly
  broken Phase 1: `require()` does not redirect, it explains in place; only `/` redirects, to
  `journey["next"]`. Setup stays **one route with five steps in state**, which forces two adaptations the
  inventory pins down — the step indicator hardcodes **four** steps in its class names, and clicking a step
  navigates backwards only. **Costs and split are two cross-linked screens**, on the owner's distinction
  between estimates for a drafted plan and actual bills that happened; the split screen therefore gets
  Auto-Bill's whole surface, and removing a row still voids rather than deletes, so `WF-018` holds while the
  button still says remove. Navigation **adapts the existing sidebar shell** rather than inventing one —
  its one real gap is that `.sidebar` goes static at 992px, so a phone drawer must be designed. Auto-Bill's
  own wizard-then-dashboard shape was rejected: it destroys the journey model. **This changes
  [Prototype the merged cost and split screen](tickets/031-prototype-the-merged-cost-and-split-screen.md)'s
  premise** — there is no merged screen, and a dated note records it.
- [Define the visual parity gate for the Tailwind rebuild](tickets/025-define-the-visual-parity-gate-for-the-tailwind-rebuild.md) —
  The target is the **token contract, completed first**; checking is screenshot comparison at two levels;
  new elements pass on **token conformance plus a declared ancestor**; and Auto-Bill's own defects are
  **fixed and recorded in a deviation register (D1–D7)**, without which every intentional fix would read as
  a parity failure. Full definition, failure conditions and ordered prerequisites in
  [`025-visual-parity-gate.md`](artifacts/025-visual-parity-gate.md). Three findings reshape the work.
  **The inline-only count reconciles to 39, not 18 or 28** — across 114 inline style sites — so the
  contract's blind spot is larger than either earlier ticket assumed. *(Refined 2026-08-03 by the completed
  extraction: of the 39, **23 are styled inline and 16 carry no styling at all** — so on `/split` the
  settlement group is inline-only and recoverable, while the allocation-mode views are bare containers whose
  layout must be designed.)* **Whole-screen diffs against the donor are impossible** — 2 donor screens against 9 routes —
  so element-level parity captures must be taken **before `Auto-Bill-Splitter` is archived**, while
  screen-level baselines (4 per route: light/dark × en/th, with the 13 accents asserted as tokens rather
  than imaged) only catch drift. And **`exporters.py` hardcodes 8 hexes across 17 occurrences in a cool
  blue-grey palette matching nothing in Auto-Bill**, so the poster, PDF and workbook — already a
  pilot-ready gate — look like a different product; colour therefore gets one machine-readable source both
  renderers read, on `WF-018`'s precedent. Radius unifies on `2px`, finishing what the contract reads as an
  unfinished sharp restyle.
- [Decide cost-and-split reconciliation rules](tickets/023-decide-cost-and-split-reconciliation-rules.md) —
  **A split row may claim a cost row via one optional `cost_id`, and the claimed row defers its actual.**
  Nothing is added to the cost row and `payment_state` is untouched, because claimed-ness is derived — so
  `planned` is every cost row and `actual` is non-voided split rows **plus unclaimed paid cost rows**, which
  makes double counting structurally impossible rather than merely discouraged. Arithmetic and model
  additions in [`023-cost-and-split-reconciliation.md`](artifacts/023-cost-and-split-reconciliation.md).
  Three findings shape it. **`costs.totals()`' `estimated_thb` sums non-paid rows only**, so a row later
  marked paid drops out of it — correct for "still to pay", wrong as the plan figure, so `planned_thb` and
  `actual_thb` are **added** while no existing key is redefined. **The category mapping is nearly free**: the
  two vocabularies differ by two plurals and `fees`, so the seven become the default tag vocabulary and most
  trips need no mapping. And **`group_preference_weights` is a trap** — `setup.py` already computes
  per-traveller weights, but they are a *taste* weight feeding only `ranking.py`, and using them for money
  would charge the owner half the trip; estimated per-person is `planned_thb / headcount`, actual comes from
  `split.py`'s shares. Split rows inherit the cost snapshot with the buffer skipped, gaps warn without ever
  blocking export, and a per-traveller **settled marker** closes this map's fog item without reversing
  WF-018 — cleared automatically whenever that traveller's balance changes.
- [Decide which exporter survives, Python or JavaScript](tickets/030-decide-which-exporter-survives.md) —
  **Python survives; `excelExporter.js` is deleted and `exceljs`/`file-saver` never join `web/`.** Decided on
  `CLAUDE.md`'s one-snapshot rule (one generator is the only way it can hold), on **25 tests against 0**, and
  on the fact that only Python has PDF, poster and ICS at all. Contract in
  [`030-exporter-and-download-contract.md`](artifacts/030-exporter-and-download-contract.md). Downloads use
  dedicated `GET` routes with `Content-Disposition`, because phone download behaviour decides it and these
  files are the Taipei artifact — **a deliberate exception to the RPC convention that weakens one guard**,
  since a `GET` carries no `Content-Type` and so rests on the `Host` allowlist alone, with the written rule
  that bare `GET` reaches downloads and nothing else. Auto-Bill's **backup JSON is the migration channel**,
  because a file survives archiving where `localStorage` does not — so one dated pre-archive action now covers
  this and WF-025's 41 element captures. **The split ledger gets its own workbook**, for a purpose the exports
  never had: a money file can be handed to a traveller without handing over the itinerary. That collided with
  WF-023, resolved explicitly: planned-versus-actual lands in the plan workbook's Costs sheet as **values, not
  formulas**, since there is nothing in the same file to point at — so an export is a snapshot of a plan
  version, not a live document, and the sheet must say so.
- [Decide the bilingual copy pipeline for the webapp](tickets/027-decide-the-bilingual-copy-pipeline-for-the-webapp.md) —
  **One JSON catalogue that both renderers read**, forced by a fact rather than chosen: `WF-030` kept the
  Python exporters and `_export_labels()` is `TEXT[lang] | OPTIMIZER_CODE_TEXT[lang]`, so moving copy to the
  frontend would duplicate Python's need rather than remove it. No i18n library — **TypeScript importing JSON
  `as const` checks keys at compile time**, which beats runtime lookup and is free. Details in
  [`027-bilingual-copy-pipeline.md`](artifacts/027-bilingual-copy-pipeline.md). **A live defect surfaced while
  measuring**: `ui/text.py` has eight bilingual tables, the parity rule covers exactly **one**, and **24
  optimizer codes have Thai and no English** — invisible because every consumer prettifies the code, so an
  English owner reads `Access unverified` and cannot tell it from real copy. **The fallback is the camouflage**,
  so the test grows to all eight tables and the fallback becomes visibly machine output (`⚠ ACCESS_UNVERIFIED`).
  Those 24 strings, plus WF-019's 26 refusal codes and the 6 `interpret.py` causes, are mandatory before it
  goes green. `CATEGORY_TEXT` is the **one documented exemption** — its English is derived and correct for 24 of
  25, so it gets one override for `place_of_worship` and a stronger test on rendered output. Thai for the ~120
  ported strings is machine-drafted and reviewed with provenance flagged, except the copy-memo template which
  is owner-written because it is pasted into a real chat about real money. Emoji decorate only; **country flags
  are the hard case**, since a flag-only cell becomes an empty cell in the PDF.
- [Decide the test strategy after Streamlit AppTest dies](tickets/029-decide-the-test-strategy-after-apptest-dies.md) —
  **`AppTest` exposure is 7%, not 80%.** The "12 of 15 files" figure is true per file and misleading: measured
  per test, **18 of 235** depend on it, so 217 survive untouched. Classified by the lowest layer that can
  assert the same thing, **14 are portable** to actions/core/exports, **3 are genuinely UI**, and **1 simply
  dies** — the `$`-as-LaTeX workaround. **Most were never UI tests**; they assert product logic through a UI
  because that was the only surface available, and three are portable only because WF-028 made `journey()` a
  real method. Survey and classification in
  [`029-test-strategy-after-apptest.md`](artifacts/029-test-strategy-after-apptest.md). The 14 are ported
  **before** anything is deleted so coverage never dips. API contract tests are `unittest` at two levels —
  dispatch directly, plus a real server on **port 0**, because the `Content-Type` and `Host` guards and the
  bare-`GET` rule are **security controls** unreachable without a socket, and a guard nobody tests is a guard
  someone relaxes. **Vitest** for frontend units (one dev dep, ships with Vite), while **the journey walk comes
  free** from WF-025's parity harness, which already navigates all 9 routes in both themes and languages. One
  green command, `scripts/check.py`, one exit code, reporting stage by stage and skipping frontend steps while
  `web/` does not exist.
- [Decide the migration path for existing trips and splitter data](tickets/024-decide-the-migration-path-for-existing-data.md) —
  **A read-only census reframed it: there is one trip, and it is the pilot.** `data/tourist.sqlite3` holds
  `user_version` 12 and exactly **one** trip — `Taipei, Taiwan`, created 2026-07-30 — with 3 plan versions and
  50 paid-usage rows. So this migrates the pilot trip itself, five months before the pilot. Census and rules in
  [`024-migration-path.md`](artifacts/024-migration-path.md). **No importer is built**: Auto-Bill holds one
  trip's data at a time and there is nothing to merge it into, so the owner exports a backup JSON before
  archiving and it is kept as a **record**, while Taipei's split ledger starts empty. That **deletes three
  problems this map called mandatory** — name→traveller mapping, a `paid_by` the source never recorded, and
  rate provenance at import. A row arriving with known THB and no rate keeps it as a **locked `actual_thb`**,
  because fabricating an `as_of` would put a made-up date in a field that means something else. **Every schema
  bump copies the database first and refuses to proceed if the copy fails** — this bump differs in kind from
  the twelve before it, since WF-022 removed the downgrade path, so a pre-bump copy is the only way back. The
  ticket's downgrade question is **void** (there is no frozen app to return to), and its mid-trip question is
  answered by a rule: **no schema change between 29 December 2026 and 4 January 2027.**
- [Prototype the merged cost and split screen](tickets/031-prototype-the-merged-cost-and-split-screen.md) —
  Built as **two** screens per WF-028, not one:
  [`031-money-screens-prototype.html`](artifacts/031-money-screens-prototype.html), throwaway, EN/TH,
  light/dark, phone width, no external requests. Tokens are the extracted contract with D1/D2/D5/D8 applied and
  the five concatenated alphas replaced by named tints. **Nine decisions were put up for reaction and all nine
  confirmed**, so the arrangement stands: two per-person numbers computed differently and kept visibly
  distinct; the reversed "you pay Dad" direction as a warning; settled as a marker that does not move the
  balance; suggestions-not-debts as a standing panel; unclaimed-paid warnings on the planned screen; missing
  rates excluded rather than guessed; voided rows visible; the claim link as a text action; and the accent as
  destination-driven teal rather than house red. **The one gap reacted against was filtering** — which was the
  right catch and the largest miss available, since **6 of the 23 inline-only classes are the filter
  interaction**, the biggest stylesheet-invisible group in the extraction. Added with its recovered values,
  dimming rather than hiding so a moved total stays explainable.
- [Prototype the itinerary day screen in the new design](tickets/032-prototype-the-itinerary-day-screen-in-the-new-design.md) —
  [`032-day-screen-prototype.html`](artifacts/032-day-screen-prototype.html), throwaway, EN/TH, light/dark,
  phone, plus no-dates and China toggles. **The row model is six types, not three** — `meal`/`preparation`/
  `logistics` share one renderer. Eight calls were put up and **six drew changes**: the type rail went 4px → 10px
  with a colour wash and a type label, because 4px could not be told apart at a glance; **the timeline had four
  gaps and is now continuous 07:30–22:00**, with the implied travel legs and buffers drawn and an unscheduled
  evening shown rather than omitted; text enlarged throughout; the header became **`3/1`**, which deviates from
  the donor's *code* toward its *README* and is registered as **D10**; variants became real buttons. **A map was
  wanted and built as a coordinate plot with no tiles** — true relative geometry, so stops 1 and 2 read as 70 m
  apart while Taipei 101 is 6.5 km east — and it was accepted, so `WF-034` is **not** reopened: the plot needs no
  network, no licence, and Pillow can draw it so screen and export still agree. **Outbound map links** were added
  on top, extending the app's existing TripAdvisor/Wikimedia redirect pattern; two traps are recorded for the
  build — **Amap takes longitude first, and expects GCJ-02 while ours are WGS-84**, so unconverted the pin lands
  100–500 m off, and only mainland China switches provider.
- [Design the feedback, confirm, and disabled elements Auto-Bill never had](tickets/035-design-the-feedback-confirm-and-disabled-elements.md) —
  [`035-feedback-element-family.html`](artifacts/035-feedback-element-family.html): four banner levels named
  **Saved / Cannot / Check / Note**, disabled at 45% with **no shadow and a mandatory reason line**, a
  requires-network state that is deliberately *not* disabled, an inline field error, the blocked-stage panel, a
  real confirm that **names the consequence**, and the deliberately ugly `⚠ CODE` fallback. **All seven calls
  confirmed.** Two counts were measured lower than charted: **68** status calls not 59, and **10** disabled
  actions not 5; the donor has **27** `alert()` not 33, and zero `:disabled` rules. §8 encodes the rule the
  codebase learned three times — a word gets a pill, a number gets a tile. Toasts were rejected because most of
  these messages are *conditions*, not events.
- [Lock the Phase 2 slice plan and validation scorecard](tickets/033-lock-the-phase-2-slice-plan-and-validation-scorecard.md) —
  **The destination. The map is decision-complete and the Phase 2 code freeze lifts.** Plan and scorecard in
  [`033-phase-2-slice-plan-and-scorecard.md`](artifacts/033-phase-2-slice-plan-and-scorecard.md).
  **A scope cut is recorded here by owner decision: the PDF and the 9:16 poster are dropped** — measured, the
  rendered pair costs ~350 lines, **2 of 4 runtime dependencies**, **the entire font apparatus**, and **16 of
  the 17 hexes** behind D7, taking `pyproject.toml` down to `streamlit` + `xlsxwriter` and tests to **231**.
  Defensible because `WF-013` records that the owner made the four reference PDFs themselves by exporting the
  `.xlsx`, so a PDF is already a rendering of the workbook. Order: **S0 scope cut → S1 foundation → S2 the
  merge → S3 cheap journey screens → S4 the expensive two → S5 slice 6 → S6 parity and deletion**, each closing
  with its own runnable check. **Two answers conflicted and the resolution is recorded**: thin-walkable-path
  put money at S4 while the split ledger was wanted early, so money moved to **S2** and the journey screens
  shifted back one. **S4 is where the webapp first works end to end**, and it is what 1 November measures.
  Deferred past the pilot: GenAI revision, the ranked candidate card grid, voided rows in exports, and
  per-person figures feeding upstream.
- [Decide the offline asset policy for the webapp](tickets/034-decide-the-offline-asset-policy-for-the-webapp.md) —
  **The largest item in the ticket turned out not to exist.** Map tiles were called the biggest remote
  dependency, but the exports contain **no map at all** — just numbered stops with coordinates as text — and the
  only tile use is `st.map`, which dies with Streamlit. So tiles would be a *new* dependency, and the webapp
  ships **none**: the numbered stop list is the map, which is what the exports already do, so screen and export
  agree by construction. Recorded as a real product loss, not just a dependency saved. Details in
  [`034-offline-asset-policy.md`](artifacts/034-offline-asset-policy.md). Fonts **self-host as `woff2`** and a
  **merged Noto TTF ships for exports** — measured, exports work today *only* because this Mac has proprietary
  `Arial Unicode.ttf`, while `resolve_font()` raises rather than rendering tofu, so on any other machine the PDF
  and poster fail outright; merging is required because no single Noto file covers both Thai and CJK and Pillow
  cannot fall back. **Bold monospace becomes real**, resolving WF-020's AMBIGUITY 4. `flagcdn.com` becomes a
  **local sprite**, and the which-countries problem dissolves against our own data: `destinations.COUNTRIES` is
  a picker convenience and `nationality` is free text, so no sprite can be complete — flag absent shows the name
  alone, making it an enhancement layer rather than a curation statement. **The offline contract is that
  everything local works** — the optimizer and `revision.py` are pure, so re-optimizing offline already works —
  **and network-requiring actions say so before they are pressed**, mirroring the existing rule that paid
  actions state their cost first. And `tokens.css` is the single colour source **in CSS, not JSON**, because
  WF-025 chose Tailwind v4 precisely for its native custom-property model. Adds **D8** and **D9** to the parity
  register.

## Not yet specified

<!-- In-scope fog: suspected questions not yet sharp enough to ticket. Graduates as the frontier advances. -->

- Whether the 45-site `PlannerRefusal` migration is its own ticket. The 26-code vocabulary is locked by
  the API contract, but the migration fixes a *Phase 1* bilingual defect and is therefore **not** gated by
  this map's decision gate. Sharp enough to ticket as soon as the owner wants it sequenced.
- Whether voided split rows appear in the PDF and Excel exports, or only in the app where the owner can see
  why a total moved.
- How slice 6's free-text GenAI revision presents itself in the new design, and whether its typed-intent
  preview survives as a modal, a diff panel, or something else.
- Whether per-person cost data should feed anything **upstream** — affordability in ranking, budget caps in
  optimization. Narrowed by the reconciliation ticket, which settled the downstream half: estimated
  per-person is `planned_thb / headcount` on the cost overview, actual per-person comes from `split.py`'s
  resolved shares, and neither touches `group_preference_weights`. Whether either figure should influence
  scoring or scheduling is still open, and would be a Phase 1 contract change rather than a UI decision.
- Whether the donut and vertical bar charts have any planner use at all. The element inventory found no
  distribution the planner charts today; the only candidate is the ranking dimension breakdown, which is
  already a table with an explicit per-dimension maximum.
- Archival mechanics for the `Auto-Bill-Splitter` repository, and how lifted code is attributed once its
  origin repo is read-only.

## Out of scope

- Hosted deployment, accounts, per-traveller login, remote member voting, notifications. These stay a
  later phase; the destination is explicitly local and owner-led.
- Rewriting the planning core, optimizer, or ranking in JavaScript or TypeScript.
- Building any slice 6 feature in Streamlit.
- Changing optimizer, ranking, or scoring behaviour as part of the redesign. A UI port that alters
  planning output is a regression, not an improvement.
- Purchasing flights, accommodation, tickets, or subscriptions on the user's behalf.
