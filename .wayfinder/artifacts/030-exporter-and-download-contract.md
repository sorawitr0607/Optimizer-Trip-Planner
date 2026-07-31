# Exporter and download contract

Resolves `Decide which exporter survives, Python or JavaScript` (WF-030).

Decided 2026-07-31 through the exporter interview. Measured against the planner at `35686dc` and
`Auto-Bill-Splitter` on disk. Paths are repo-relative to each project.

## The comparison that decided it

| | Python | JavaScript (donor) |
|---|---|---|
| Lines | `exporters.py` 1136 + `exports.py` 527 | `excelExporter.js` 708 |
| Sheets | **6**: Summary, Timeline, Choices & Backups, Checklist, Costs, Sources | **5** + dynamic pivots: Settings, Transactions, Split Detail, Summary, Summary by Day |
| Other outputs | **PDF, 9:16 poster PNG, ICS** | JSON backup |
| Tests | **25** in `tests/test_exports.py` | **0** — the donor has no test runner |
| Purity | snapshot-in, bytes-out, no browser | needs a DOM |

## The four decisions

| # | Question | Decided |
|---|---|---|
| 1 | Which exporter | **Python survives.** `excelExporter.js` is deleted; its five sheets are reference, not reuse |
| 2 | How the browser gets a file | **A dedicated `GET` download endpoint** with `Content-Disposition` |
| 3 | The JSON backup | **Survives as the migration import channel** — and must be exported before archiving |
| 4 | Where the split ledger lands | **Its own workbook**, so it can be shared with travellers without the itinerary |

## 1. Python survives

The decisive argument is `CLAUDE.md`'s standing rule that every new output must read
`build_export_snapshot()` rather than a raw variant — *that* is what stops times, totals and statuses
diverging between the poster, the PDF and the workbook. **One generator is the only arrangement in which
that rule can hold.**

The test asymmetry is the second argument, and the tests are not shallow:

- `test_summary_formulas_point_at_the_real_timeline_columns`
- `test_every_formula_ships_with_a_cached_value` — so a reader that does not recalculate still sees numbers
- `test_workbook_keeps_english_thai_and_local_names_side_by_side`
- `test_status_wording_survives_when_its_icon_cannot_be_drawn`
- `test_totals_that_disagree_with_the_optimizer_are_refused`
- `test_long_names_wrap_inside_the_poster_instead_of_being_clipped`

Twenty-five of those against zero on the donor side, for the artifact the owner physically carries.

Third: **only Python has PDF, poster PNG and ICS.** JavaScript has none of them in this stack; each would
be a new dependency and a full reimplementation. And purity matters more now than it did — `WF-029` has to
replace `AppTest`, and an exporter that is snapshot-in/bytes-out with no browser is the easiest thing in the
codebase to keep tested.

**Accepted costs:**

- The split ledger's sheets must be written in Python. The donor's 708 lines inform the layout and are then
  deleted; they do not port, because they produce the donor's five sheets rather than the planner's.
- `WF-025`'s deviation **D7** applies: the 17 hardcoded hexes in `exporters.py` must be re-pointed at the
  single colour source.
- `exporters.resolve_font()`'s problem stays Python's: a Unicode TTF covering Latin + Thai + CJK, which
  raises rather than rendering tofu. `Decide the offline asset policy for the webapp` owns shipping it.

## 2. Downloads use a `GET` endpoint, and that needs its own written rule

```
GET /api/export/{trip_id}/workbook.xlsx
GET /api/export/{trip_id}/split.xlsx
GET /api/export/{trip_id}/plan.pdf
GET /api/export/{trip_id}/poster-{date}.png
GET /api/export/{trip_id}/checklist.ics
    Content-Disposition: attachment; filename="…"
```

The browser's own download handling gets the parts that matter right: filename, save location, and **phone
behaviour** — which is decisive, because these files are the Taipei artifact and a blob save is historically
the flaky path on a phone. The filename is set server-side, where the plan version, language and date are
already known.

> **This is a deliberate exception to `WF-019`'s single convention, and it weakens one guard.** That contract
> chose RPC-per-action with `POST /api/<method>` and requires `Content-Type: application/json` as a
> **security control** — a `GET` has no body to carry one, so these endpoints rest on the **`Host` allowlist
> alone.**
>
> Accepted, for stated reasons: a download is a **read**, and a cross-origin caller cannot see the response.
> The worst case is an unread file generation, i.e. wasted CPU. The rule to write into `api/`: **bare `GET`
> may reach export downloads and nothing else** — never a mutation, never a paid call, never `set_paid_cap`.

## 3. The JSON backup is the migration channel

Auto-Bill keeps everything in `localStorage` — `alipay_splitter_settings`, `alipay_splitter_transactions`,
`alipay_splitter_theme` — and its backup (`Dashboard.jsx:608`) is a download of exactly that. **A file
survives archiving; `localStorage` does not**, since reading it requires the donor running at its own origin.

`WF-018` already made participants traveller ids rather than free text, so name-to-id resolution is the
one-time import concern it was designed to be. `Decide the migration path for existing trips and splitter
data` owns the mapping; this ticket only fixes that the channel is the backup file.

**Accepted:** the format is undocumented and validated by a `JSON.parse` plus a shape guess with `alert()`
on failure; it is a one-way, one-time channel, so its reader is dead code after migration; and nothing
guarantees the backup captures everything the app holds.

### One dated pre-archive action now covers two tickets

Both of these need `Auto-Bill-Splitter` runnable and both are lost once it is archived:

1. **Export a backup JSON per trip** — this ticket.
2. **Capture the 41 lifted elements in isolation** — `WF-025`'s element-level parity baseline.

(An earlier version of this pattern in `WF-022` — capturing Streamlit reference exports — was voided when
Streamlit stopped being a pilot vehicle. These two stand.)

## 4. Two workbooks, because the money file is shareable

The split ledger gets **its own workbook**. The reason is a purpose the exports never had: **a money file
can be handed to Mum without handing over the whole itinerary.** The split ledger is group data that other
people have a legitimate claim on; the plan is the owner's.

```
{trip}-plan.xlsx    Summary · Timeline · Choices & Backups · Checklist · Costs · Sources
{trip}-money.xlsx   Split rows · Settlement            <- shareable
```

**Both read `build_export_snapshot()`**, so `CLAUDE.md`'s one-snapshot rule holds across two files — one
source, two renderings, no divergence.

A useful property falls out: since the money workbook is meant to leave the owner's hands, it must carry
**nothing private**. `FORBIDDEN_SNAPSHOT_KEYS` already bars passport and booking-document keys from any
snapshot, so the floor is in place; the money workbook additionally carries no itinerary, no addresses and
no readiness evidence.

### The `WF-023` collision, and how it resolves

`WF-023` put planned-versus-actual per category on the cost screen, reading both ledgers. Across two files a
cross-workbook formula is not reliable. So:

> **The Costs sheet in the plan workbook carries `planned`, `actual` and the difference per category as
> plain values, computed by `build_export_snapshot()`.** Not formulas, because there is nothing in the same
> file to point them at.

This is a **deliberate departure from the formula-plus-cached-value pattern** that
`test_every_formula_ships_with_a_cached_value` protects, and the consequence is stated rather than
discovered: **edit a split row in the money workbook and the plan workbook's comparison does not update.**
That is acceptable because an export is a snapshot of a plan version, not a live document — but the sheet
should say so, so nobody trusts a stale figure.

The money workbook keeps live formulas internally, where its own rows are in the same file.

**Accepted costs of two files:** two artifacts to carry and keep in step on a trip; the donor's split output
is really two views (Split Detail, Summary by Day) plus pivots, so "its own workbook" may be two or three
sheets rather than one; and settlement is a third record shape again.

## What this adds

| Where | Addition |
|---|---|
| `api/` | Five `GET` export routes, outside the RPC convention, plus the written rule that bare `GET` reaches downloads and nothing else |
| `exporters.py` | A second workbook builder for the money file; `planned`/`actual`/diff as values on the Costs sheet; D7 re-tokenisation of 17 hexes |
| Deleted | `excelExporter.js` (708 lines), `exceljs`, `file-saver` — never added to `web/`'s dependencies |
| One-time | A backup-JSON reader for migration, dead code once migration is done |

## Explicitly not decided here

- How many sheets the money workbook has, and whether settlement is one of them.
- The exact filename scheme beyond the shape above.
- Whether the poster stays one-day-per-file or gains a whole-trip variant.
- Whether the money workbook is bilingual per file or carries both languages side by side as the plan
  workbook does.

## What this hands downstream

| Ticket | Consequence |
|---|---|
| `Decide the migration path for existing trips and splitter data` | The channel is Auto-Bill's backup JSON, and it **must be exported before the donor is archived**. Only the name-to-traveller-id mapping is left to decide |
| `Decide the offline asset policy for the webapp` | Confirms the Unicode TTF for Pillow is still needed and is Python-side, since Python keeps PDF and poster rendering. `exceljs` and `file-saver` are **not** joining `web/` |
| `Define the visual parity gate for the Tailwind rebuild` | D7's re-tokenisation is confirmed as needed — Python survives, so those 17 hexes are real work, not potentially wasted |
| `Decide the test strategy after Streamlit AppTest dies` | The 25 export tests survive untouched and need no browser, so they are the model for what post-`AppTest` coverage looks like |
| `Lock the Phase 2 slice plan and validation scorecard` | Five outputs across two workbooks, all from one snapshot; the reference workbooks' `ค่าใช้จ่าย` sheet is the validation target for the money file and `ตารางเวลา` for the plan file |
