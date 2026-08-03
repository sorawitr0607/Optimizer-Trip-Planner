# Phase 2 slice plan and validation scorecard

Resolves `Lock the Phase 2 slice plan and validation scorecard` (WF-033) — the map's destination and its
handoff artifact.

Decided 2026-08-03. Measured against the checkout at `c013228`. Paths are repo-relative.

## 0. A scope cut recorded here by owner decision

**The PDF and the 9:16 poster are dropped.** The workbook and the ICS calendar survive. Recorded in this
ticket at the owner's instruction rather than by amending three closed tickets.

Measured cost of the rendered-document pair:

| Output | Lines | Dependency | Hardcoded hexes | Needs the Unicode font |
|---|---|---|---|---|
| Poster PNG | 211 | `pillow` | **16 of 17** | yes |
| PDF | 138 | `fpdf2` | 0 | yes |
| Workbook | 422 | `xlsxwriter` | 1 | no |
| ICS | 93 | none | 0 | no |

**What the cut deletes:**

- **~350 lines** plus the shared drawing helpers (`fit_lines`, `_ellipsize`, `_draw_block`).
- **2 of 4 runtime dependencies** — `pillow` and `fpdf2`. `pyproject.toml` drops to **`streamlit` +
  `xlsxwriter`**.
- **The entire font apparatus**: the merged Noto TTF, its `fonttools` build recipe, the multi-megabyte
  checked-in binary, the OFL licence record, `resolve_font()`, `FONT_CANDIDATES`, `TOURIST_EXPORT_FONT`. That
  is most of `WF-034`'s §1.
- **Most of deviation D7** — 16 of the 17 hexes live in the poster, so the colour re-tokenisation nearly
  disappears. One workbook hex remains.

**Why this is defensible rather than a retreat.** `WF-013`'s resolution records that **the owner added the four
reference PDFs themselves, exported from the `.xlsx`** — the originals were untouched by code. So in the
established workflow a PDF is already *a rendering of the workbook*, produced by print-to-PDF. Shipping the
workbook and exporting on demand is how the reference trips were actually made.

**What is genuinely lost:** the 9:16 poster, with no substitute; and the PDF as an automatic artifact.
`WF-035`'s no-icons rule loses its hard export justification but keeps its accessibility one.

**Test impact, measured:** 7 tests touch it — 4 PDF-only, 2 poster-only, plus
`test_missing_export_font_is_a_precise_error` which dies with `resolve_font()`. But **three of the PDF-only
tests assert content, not rendering** — `status_wording_survives_when_its_icon_cannot_be_drawn`,
`documents_carry_the_fallback_and_the_hotel_anchor`, `documents_localize_optimizer_codes_like_the_app` — so they
**re-base onto the workbook** rather than being deleted. Net: **235 → 230**, with 3 rewritten.

> **Corrected 2026-08-03 by building S0.** The estimate above said 231; the real figure is **230**, because
> `test_pdf_carries_the_appendix_and_a_cover_summary` in `test_checklist.py` was missed when counting — 5 tests
> delete, not 4. Two further corrections from the build: **`pillow` is not actually removed from the
> environment**, because `streamlit` depends on it, so only `fpdf2`, `fonttools` and `defusedxml` leave and
> `pillow` waits for S6; and preserving code localisation **changed workbook content** — the fallback trigger
> now reads `Rain` rather than raw `rain`, matching what the PDF always produced.

**Tickets this amends**, each of which gets a dated pointer here: `WF-030` (chose Python partly because only it
had PDF and poster — the workbook keeps that conclusion intact), `WF-034` (§1's merged font is void; the
`woff2` browser fonts and D8's real mono 700 stand), `WF-025` (D7 shrinks to one workbook hex).

## 1. The slice order

**Two answers had to be reconciled.** The chosen strategy was *thin walkable path, cheap screens first*; the
chosen split-ledger placement was *early, right after the foundation*. Those conflicted — the strategy put
money at S4. Resolved by moving money to **S2** and shifting the journey screens back one, which keeps
cheap-before-expensive *within* the journey while proving the merge early.

| Slice | Contents | The runnable check that closes it |
|---|---|---|
| **S0** | The scope cut: delete PDF + poster, `pillow`, `fpdf2`, the font apparatus | **Done 2026-08-03.** All existing gates green at **230** tests; `pyproject.toml` shows 2 runtime deps. *(This row originally named `scripts/check.py`, which does not exist until S1 — the existing commands were used instead.)* |
| **S1** | **Foundation.** `api/` transport (dispatch, 51-method allowlist, `jsonable()`, error map, boundary guard, `GET` downloads) · `PlannerActions.journey()` · `tokens.css` · the JSON copy catalogue · `web/` shell with routing and `<StageGate>` · `scripts/check.py` | One contract test per dataclass shape; the three socket-level guard tests; parity test over all 8 copy tables; `uv run python -m api` serves the shell and one real API call round-trips |
| **S2** | **The merge.** `split.py` · the split-ledger table with its pre-bump database copy · `costs.totals()` gaining `planned_thb` / `actual_thb` · `/costs` and `/split` screens | `split.py` unit tests including the rounding remainder and star settlement; a claimed cost row contributes its actual **once**; both screens render in `en` and `th`; the pre-bump copy exists and the migration refuses without it |
| **S3** | **The cheap journey screens.** `setup` (5 steps, one whole draft) · `optimize` · app chrome · the sidebar navigation | The real Taipei trip's setup round-trips whole; a variant activates and refuses on a stale hash; 3 of the 14 ported `AppTest` behaviours pass at actions level |
| **S4** | **The expensive journey screens.** `places` (570 lines, nearly all-new) · `itinerary` (the six row types, the stop list, the coordinate map) | **Gate 1 becomes assessable**: the real Taipei trip walks setup → discovery → ranking → optimize → activate → export in the webapp |
| **S5** | **Slice 6 and the rest.** Non-AI quick actions · `revise` · `readiness` | Quick actions produce a rebuilt variant with consequences shown; a revision applies and restores; the readiness board generates and applies |
| **S6** | **Parity and deletion.** The parity harness green · the remaining ported behaviours · delete `views/`, `app.py`, `ui/` | Element diffs within tolerance for all 41 lifted elements; 36 screen baselines approved; token allowlist clean; deviation register D1–D10 complete; `check.py` green with `AppTest` gone |

**S4 is the slice that first makes the webapp usable end to end**, and it is the slice the 1 November
checkpoint actually measures.

### Accepted costs of this order

- **`places` and `itinerary` are stubs until S4** — and they are the two screens looked at most.
- **The irreversible schema bump lands at S2**, when coverage of the new stack is thinnest. `WF-024`'s
  pre-bump copy that refuses on failure is therefore load-bearing, not a formality.
- **S1 must be a fuller foundation than the word implies** — routing and `<StageGate>` have to ship in it,
  because S2's money screens depend on them.
- **Walkable is not usable.** A thin path can flatter progress; S4's check is deliberately the real trip, not
  a fixture.

## 2. Retained evidence per slice

Following the convention `AGENTS.md` already sets, and Phase 1's precedent of reproducible bundles:

Each slice writes `artifacts/validation/<date>-slice-<n>/` containing a `manifest.json` with the run's
numbers — test counts, timings, token spend where a paid call was made — and a notes file beside it carrying
the narrative. **Numbers in the manifest, prose in the notes, one line linking them from the slice's entry
here.** Appending long evidence prose into a ticket is what starved `WF-012`'s graph extraction twice.

Slices that produce a visual surface (S2, S3, S4, S5) also retain the screen captures their check produced, so
S6's parity baselines have a history rather than appearing from nowhere.

## 3. The hard gates — everything that must pass

**Inherited and still binding:**

| Gate | Command or rule |
|---|---|
| Unit tests | `unittest discover -s tests` — **230** after S0, not the 202 this ticket was charted with |
| Historic regressions | `scripts/run_optimizer_regressions.py` — 27 cases, 20 atomic + 7 interaction |
| Fixture structure | `scripts/validate_regression_fixtures.py` |
| Copy parity | `en`/`th` key-for-key across **all 8 tables**, with `CATEGORY_TEXT` exempted and tested on rendered output |
| Graph integrity | `scripts/build_project_graph.py --check` |
| Redaction | `scripts/check_provider_access.py --self-test` |
| Paid cap | US$10 refuses, US$8 warns, every paid call through `_spend` |
| **No silent behaviour change** | A port that alters ranking, scheduling or the active plan is a **regression**. `deterministic_signature` must not move for the same input and `OPTIMIZER_VERSION` |

**New, from this phase:**

| Gate | Source |
|---|---|
| One `jsonable()` contract test per dataclass shape | `WF-019` — the wire shape is implicit, so this is the only thing catching a renamed field |
| Three socket-level guard tests | `WF-029` — the `Content-Type` check *is* the CORS defence, the `Host` allowlist *is* the DNS-rebinding defence, and bare `GET` must reach downloads and nothing else |
| Element-level parity for 41 lifted elements | `WF-025` — captured from the donor **before it is archived** |
| 36 screen baselines, light/dark × en/th × 9 routes | `WF-025` |
| Token allowlist clean; every new element declares an ancestor | `WF-025` — numbered map canvas exempt |
| Deviation register complete, **D1–D10** | `WF-025` — an unregistered deviation is indistinguishable from drift |
| Reference-workbook comparison, all four sheet types | `WF-022` — structural coverage, not cell equality |
| One green command | `scripts/check.py`, one exit code, stage-by-stage |

**Pilot-ready, judged 1 November 2026** — `WF-022`'s three gates, with gate 2 narrowed by the scope cut:

1. **The real Taipei trip planned end to end in the webapp.** Not a fixture.
2. **Exports verified against the four reference workbooks** — now the workbook and ICS only, since the PDF and
   poster are gone.
3. **All 230 tests green.**

Not on track ⇒ Taipei is planned by hand in Excel, as the four reference trips were.

## 4. Explicitly deferred past the pilot

| Deferred | Why it is safe to defer |
|---|---|
| **Constrained GenAI revision** | Already optional in the locked frame. `interpret.py` exists and is tested; only the React surface defers. Needs credentials and bills per call against the cap. The non-AI quick actions stay in scope — local, free, deterministic |
| **The ranked candidate card grid** | `WF-021` called it the biggest design gap and said the port *unlocks* it rather than ports it, so it is new design. `places` is already the most expensive screen; a functional ranked list serves the pilot. `WF-036` stays open |
| **Voided rows in exports** | Narrower now the PDF is gone: it reduces to whether voided rows appear in the workbook. The app shows them either way, which is where a moved total most needs explaining |
| **Per-person figures feeding upstream** | Affordability in ranking or budget caps in optimization would be a Phase 1 contract change to scoring or scheduling, which the map puts out of scope for a UI port |

## 5. The calendar, stated plainly

**13 weeks** from 2026-08-03 to the 1 November checkpoint. Seven slices, so **under two weeks each**, with
zero webapp code written today. Gate 1 is not assessable until **S4** — the fifth slice.

That is tight, and the plan does not pretend otherwise. Three things make it survivable:

- **S0 removes work from every slice after it.** Doing the scope cut first is worth more than its size suggests.
- **The POC keeps working the whole time.** It is not deleted until S6, so the trip can be planned on Streamlit
  while the webapp is built. The webapp only has to be good enough to be the *pilot vehicle*.
- **The 1 November call is a checkpoint, not a deadline.** `WF-022` already decided what happens if it fails,
  and it is not a disaster — it is a spreadsheet.

**One dated dependency outside the slices:** the 41 element captures and one backup JSON per trip must be taken
from `Auto-Bill-Splitter` **while it is still runnable**. Neither is on a slice's critical path, and both are
lost once it is archived.

## 6. What this leaves on the map

With this ticket closed, `WF-MAP-002` has **no unresolved decisions**, which is the destination it named:

> "Reach a decision-complete, implementation-ready Phase 2 specification … Implementation begins only after
> this map has no unresolved decisions."

**`WF-036` remains open by decision, not by omission** — the ranked candidate card grid is deferred past the
pilot, so it is a prototype ticket outliving the map's decision gate rather than a gap in it.

**So the Phase 2 code freeze lifts when this closes.** `CLAUDE.md`'s rule that no Phase 2 code gets written
until the map is decision-complete has been satisfied, and S0 is the first thing that may be built.
