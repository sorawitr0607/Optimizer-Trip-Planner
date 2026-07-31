# Webapp stack and project layout

Resolves `Choose the webapp stack and project layout` (WF-026).

Decided 2026-07-31 through the stack interview. Every count was measured against the checkout at
`c5f9b2b`. Paths are repo-relative.

## Counts up front

| Measure | Value |
|---|---|
| Stage views in the POC (`views/*.py`) | 8, plus app-level chrome |
| Gated stages `journey()` reports | 5 (setup, places, evidence, optimize, itinerary) |
| Lines of gating logic moving from `ui/` into the core | **74** (`ui/shared.py:160–233`) |
| Allowlisted API methods after this ticket | **51** (50 from WF-019, plus `journey`) |
| `save_setup` keyword arguments, all sent every time | **18** |
| `ui/text.py` copy awaiting port | 1,293 lines |
| Auto-Bill elements to lift | 41, plus 18 planner elements with no counterpart |
| New Python runtime dependencies | **0** — still `fpdf2`, `pillow`, `streamlit`, `xlsxwriter` |
| Web runtime dependencies | 6 |
| Web dev dependencies | 10 |

## The nine decisions

| # | Question | Decided |
|---|---|---|
| 1 | Journey/gating spine | **New `PlannerActions.journey()`** — the 51st allowlisted method |
| 2 | Language | **TypeScript** |
| 3 | Server state | **TanStack Query**, with `retry: false` as the default |
| 4 | Routing | **react-router** |
| 5 | Setup form | **One draft object, always sent whole** |
| 6 | Tree layout | **By stage, with `shared/`** |
| 7 | Build and launch | **`web/dist` not committed**; one wrapper command that rebuilds when stale |
| 8 | Lint and format | **ESLint with react-hooks; no formatter.** `tsc` covers types |
| 9 | Tailwind | **v4, CSS-first `@theme`** |

Three further points were settled without needing an interview, and are recorded so they are not
re-opened: **npm** is the package manager (the donor ships `package-lock.json`), **Node is pinned with
`.nvmrc`** mirroring `.python-version`'s precedent (local is v24.14.1), and **`api/` and `web/` sit beside
`travel_planner/`** as the destination interview already locked.

## 1. The journey spine must move into the core, or the rules die with `ui/`

`shared.journey()` (`ui/shared.py:160–233`) is 74 lines of **business logic living in the UI layer**.
Retiring Streamlit made this urgent rather than merely untidy: `ui/` is now POC code scheduled for
deletion at parity, and the gating rules are inside it. Move them down or lose them — there is no third
outcome.

What that helper currently does, all of which belongs in `actions.py`:

- Makes 4 separate `PlannerActions` calls (`get_setup`, `get_latest_discovery`,
  `list_candidate_choices`, `get_active_plan`).
- **Reaches into `planner._optimizer_input(trip_id)` — a private method** (`:185`) — from outside the
  class, to derive `capability_gaps`.
- **Invents a gap code the core never emits**, `OPENING_EVIDENCE_MISSING` (`:198`).
- Re-implements the rated-place filter that `rank_candidates` also enforces (`actions.py:461`).
- Owns all five gated stages' `done` / `blocked_by` rules and picks the landing stage.

`actions.py` is documented as the only coordinator, so this was always a violation of the one-way
dependency rule — the port merely forces the issue. Moving it also lets `_optimizer_input` stay private
and turns `OPENING_EVIDENCE_MISSING` into a real core gap code emitted in one place.

**React cannot recompute this instead.** `capability_gaps` requires the private `_optimizer_input`, so
the alternative would mean exposing it — the `save_plan_version`-class mistake `WF-019` explicitly barred.

`shared.require()`'s "one clear next step" rendering is presentation and correctly stays in the view.
`journey()` becomes one RPC replacing 4 round trips plus a private call, and is the frontend's spine:
route guards and the landing redirect both read it.

## 2. TypeScript

`WF-019` gave up the generated client, so response types are hand-written either way and only its
contract test checks them against Python. TypeScript is chosen because this frontend is far larger than
the donor — 8 stage views against Auto-Bill's 2 screens, 51 endpoints, 18 dataclass-shaped responses,
plus a split ledger — and because hand-written types are the only drift check that exists on the JS side.

**Stated honestly: `tsc` does not validate against Python.** A renamed core field still compiles; only
the `WF-019` contract test catches it. The risk of false confidence is accepted, and the mitigation is
that contract test, not the type system.

Cost: lifted JSX needs annotating as it lands, and a type-build step arrives in a repo that deliberately
runs no linter or formatter on its Python.

## 3. TanStack Query — and its default retry is a money bug

Invalidation is the real problem: any mutation can change the journey state, and hand-rolled
invalidation across 8 stages is exactly where a stale-gate bug hides. Mutation pending/error state also
gives the 34-second discovery its elapsed-time UI for free, and a non-2xx `{code, detail}` from `WF-019`
maps cleanly onto a typed per-query error.

> **`retry: false` is the default, opt-in per call. This is a safety configuration, not a preference.**
> TanStack's default is 3 retries. Retrying a 34 s Overpass call burns both of its 2 concurrent slots and
> reads as an outage that is really self-inflicted. Retrying a paid call **double-spends against the
> US$10 cap**.

Accepted costs: one dependency, a second cache layer over SQLite reads that already answer in under a
millisecond, and a `staleTime`/refetch model designed for shared remote data when this is one owner, one
tab, one authoritative local database. Revalidate-on-focus must be off for the same reason retries are.

## 4. react-router

8 stage routes plus chrome is a trivial route table, and "the landing page is the stage that needs
attention" is one redirect off the `journey()` response. Back and forward behave correctly, including the
popstate cases hand-rolled history code reliably gets wrong, and per-stage URLs are preserved rather than
lost — the POC has them today, and a port that removes them is a regression.

Cost: one dependency for what is conceptually a switch over 8 values, and a data/loader surface far
bigger than this needs. **Nothing in `web/` may use react-router's loaders or actions** — that would
duplicate the server-state layer decided in §3.

## 5. The setup form, and the erase-on-partial hazard

`save_setup` (`actions.py:122`) takes **18 keyword arguments and no partial form**, and every one defaults
to empty (`()`, `None`, `""`). `build_setup_payload()` then normalizes the whole thing.

> **A partial payload silently erases every field it omits.** The POC avoids this via
> `views/setup.py:157 _saved_values()`, which reloads the complete stored draft before each step's save.

So: **one draft object in React state, always sent whole.** This is a correctness requirement, not a
style choice, and it belongs written down because the failure is silent data loss rather than an error.

Every documented Streamlit workaround **disappears and must not be ported**:

| POC workaround | Why it existed | In React |
|---|---|---|
| Autosave via `on_click` callbacks | Streamlit drops widget state when a widget stops rendering | Gone — state persists |
| Per-language widget keys (`country__en`) | The browser cached a closed selectbox's rendered text | Gone — no such cache |
| Each step seeds widgets from the saved draft | Same widget-state loss | Gone — the draft *is* the state |
| No `st.form` at all | The city list depends on the chosen country, and a form defers values until submit | Gone — derived options are just a render |
| `shared.plain()` | Streamlit reads `$…$` as inline LaTeX and swallowed `US$0.13 / US$10.00` | Gone — not a React behaviour |

Carrying any of these across would be dead complexity. Validation is hand-written: dates, times, ages,
and up to 8 travellers.

A merge-on-save API change was considered and rejected as scope creep — this session already adds
`journey()` to the core, and merge semantics would introduce a new ambiguity (how does a caller *clear* a
field once omission means "keep"?) where none exists today.

## 6. Layout

```
travel_planner/          unchanged — the pure core, actions.py, store.py
api/                     the stdlib RPC transport (WF-019)
web/
  src/
    stages/              setup, places, evidence, optimize, itinerary, revise, costs, readiness
    shared/              the ~41 lifted Auto-Bill elements + the 18 with no counterpart
    api/                 the 51-method client and its response types
    i18n/                the ui/text.py port (mechanism is WF-027's)
    routes.tsx
  index.html
  package.json
```

By stage, because the app *is* a journey of 8 stages and `views/` is already one file per stage — the
port becomes a 1:1 mapping, and each stage is reviewable and deletable as a unit while stages land one
at a time. `shared/` versus `stages/` makes "is this element reusable?" an explicit decision instead of
an accident.

Accepted cost: near-identical components may be duplicated across stages before someone promotes them
to `shared/`. That is the trade against the donor's failure mode — a 2,183-line `Dashboard.jsx`.

## 7. Build and launch

`.gitignore` gains `node_modules/` and `web/dist/`; it currently has neither.

Real use stays one command, matching today's single `streamlit run`. The wrapper rebuilds when `dist` is
stale, then serves `dist` and `/api` on one port — which is what makes the `WF-019` boundary guard
trivially satisfiable, since there is one origin and CORS never exists.

Accepted costs, all real:

- The Python entry point now knows about the frontend toolchain, because it shells out to npm.
- The app is not runnable from a bare clone: `npm install` comes first.
- **"Rebuild when stale" needs a real staleness rule** — mtime comparison against `web/src` is the
  obvious one, and it is the piece to get right, because the failure it prevents is `WF-019`'s named
  hazard of a stale `dist` silently serving an old UI.

Dev remains two processes: the Vite dev server proxying `/api`, with the **120 s proxy timeout** `WF-019`
requires or the 34 s discovery dies in dev only.

## 8. Lint and format

ESLint with `eslint-plugin-react-hooks` and `eslint-plugin-react-refresh`, matching the donor's config so
lifted code lints clean on arrival. `tsc` covers types. **No formatter.**

The distinction that justifies the asymmetry with Python: `react-hooks/exhaustive-deps` is a
**correctness** tool. Stale closures and conditionally-called hooks are real bugs that TypeScript cannot
see, and with TanStack Query in the stack, effect-dependency mistakes are precisely the class you will
hit. A formatter, by contrast, addresses style — and this repo has deliberately never had one.

Accepted: style drifts, and it will be visible where lifted JSX meets new code.

## 9. Tailwind v4, configured in CSS

```css
@import "tailwindcss";
@theme {
  --shadow-*: initial;                              /* CLEAR the soft defaults */
  --shadow-sm: 1px 1px 0 0 var(--bg-card-border);
  --radius: 2px;                                    /* the house radius */
}
@custom-variant lg-down (@media (max-width: 992px));
```

**Auto-Bill's tokens are already CSS custom properties** — 23 in light, 21 redefined in dark — and v4
configures with exactly those. So the port is a copy of the source of truth rather than a transcription
through JavaScript. `WF-020`'s drafted values already read `var(--bg-card-border)` throughout, which
means the JS layer was pure indirection over CSS variables.

`--shadow-*: initial` is an unambiguous **clear**, which is what the token contract's hardest requirement
needs. This matters because of a defect in that contract worth fixing before anyone follows it:

> `WF-020` warns that "Tailwind's default shadow scale must be **overridden, not extended**" and that
> getting it wrong "**destroys the entire visual identity**". But its own code comment three lines later
> reads `// tailwind.config.js — theme.extend.boxShadow`, and in v3 `theme.extend` **merges** with
> Tailwind's soft defaults. The drafted config's later `boxShadow` block does carry an `// OVERRIDE, not
> extend` note, so the intent was right and only the pointer was wrong — but a reader following the
> warning block verbatim would produce exactly the outcome it forbids. v4's `initial` sentinel removes
> the ambiguity entirely.

`@custom-variant` also handles the 5 **desktop-first max-width** breakpoints, which fight Tailwind's
mobile-first defaults in either version — `992px` in particular, where the entire marketing panel is
`display: none` rather than stacked.

**Consequence, accepted:** `WF-020`'s drafted JS config becomes reference material rather than code. Real
work already done is not reused verbatim. v4's CSS-first model is also less familiar and has fewer worked
examples for the awkward parts.

## The dependency tally

**Web runtime (6):** `react`, `react-dom`, `react-router`, `@tanstack/react-query`, `lucide-react`,
`tailwindcss`.

`lucide-react` follows from lifting 41 donor elements rather than from an independent choice; if the lift
turns out not to need it, it drops.

**Web dev (10):** `vite`, `@vitejs/plugin-react`, `@tailwindcss/vite`, `typescript`, `@types/react`,
`@types/react-dom`, `eslint`, `@eslint/js`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`.

**Python: unchanged.** Four runtime dependencies — `fpdf2`, `pillow`, `streamlit`, `xlsxwriter`. The API
transport adds none, by `WF-019`'s decision. `openpyxl` arrives as a **dev** dependency from `WF-022`'s
reference-workbook validation, not from this ticket.

## Explicitly not decided here

- **Which exporter survives** — `Decide which exporter survives, Python or JavaScript` owns it. The donor
  ships `exceljs` and `file-saver`; if the Python exporters win, neither is added.
- **The token values and the parity gate** — `Define the visual parity gate for the Tailwind rebuild`.
- **The stage → route mapping** — `Map every stage to its webapp screen and route`. This ticket fixes only
  that routing exists and that `journey()` drives the landing redirect.
- **The i18n mechanism** — `Decide the bilingual copy pipeline for the webapp`. This ticket fixes only
  that `web/src/i18n/` is where it lives.
- **The staleness rule's exact form** for the rebuild wrapper.
- **Whether `journey()` returns the gap codes verbatim** or a richer shape — its signature is settled, its
  payload is not.

## What this hands downstream

| Ticket | What is now settled |
|---|---|
| `Decide the bilingual copy pipeline for the webapp` | Copy lives in `web/src/i18n/`; TypeScript is available for key typing; `ui/text.py`'s 1,293 lines survive until the port completes |
| `Map every stage to its webapp screen and route` | react-router with a route per stage under `web/src/stages/`, and `journey()` drives the landing redirect and route guards |
| `Decide the test strategy after Streamlit AppTest dies` | TypeScript, Vite and ESLint are in place; no test runner is chosen yet — the donor has none |
| `Decide which exporter survives, Python or JavaScript` | If JS wins, `exceljs` and `file-saver` join the 6 runtime deps; if Python wins, nothing is added |
| `Define the visual parity gate for the Tailwind rebuild` | Tailwind **v4** with CSS-first `@theme`, so the gate compares against custom properties rather than a JS config — and `--shadow-*: initial` is the mechanism enforcing the shadow override |
| `Prototype the merged cost and split screen` and the other prototypes | Stack, tree and state model are fixed, so prototypes can be built rather than designed in the abstract |
