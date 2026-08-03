# Slice 2 — the merge

Built 2026-08-03. Numbers are in `manifest.json`; this file carries the narrative and the
decisions taken while building. Closes the S2 row of
`.wayfinder/artifacts/033-phase-2-slice-plan-and-scorecard.md`.

## The four closing checks

| Check | Where it lives |
|---|---|
| `split.py` unit tests including the rounding remainder and star settlement | `tests/test_split.py` — 21 tests |
| A claimed cost row contributes its actual **once** | `tests/test_costs.py::ReconciliationTest` — 9 tests |
| Both screens render in `en` and `th` | `web/src/stages/money.test.tsx` — 10 tests |
| The pre-bump copy exists, and migration refuses without it | `tests/test_setup_discovery.py::SchemaMigrationTest` — 4 tests |

All eight `scripts/check.py` stages pass in 14.9 s. **No paid call was made**, and no runtime
dependency was added on either side.

## The claim rule, proved rather than asserted

The sharp test is `test_a_claimed_cost_row_contributes_its_actual_exactly_once`: a paid cost row
locked at 1,150 THB, claimed by two split rows totalling 1,000. The answer must be one of those
numbers and never their sum. It is 1,000 — the split side wins, and the cost row's own actual goes
inert.

Three neighbouring tests pin the rest of the rule: an unclaimed paid row supplies its own 1,150;
voiding the claim hands the cost row back so exactly one side still answers; and `planned_thb`
reports 1,200 (the estimate) while `estimated_thb` reports 0, which is what forced the new key
rather than a redefinition of the old one.

**The live walkthrough reproduces it against a real server.** Six cost rows and seven split rows
produce `planned 37,700 / actual 18,976.80`, where the actual is 17,176.80 of split rows plus the
1,800 of the one unclaimed paid row. The hotel cost row's own 11,450 appears nowhere in that total.

## One implementation of the claim rule, not two

`split.py` originally carried a `claimed_cost_ids()` helper and `costs.totals()` needed the same
derivation. Two implementations of "which cost rows does a live split row claim" is exactly the
vocabulary drift `WF-018` warns about — setup and the optimizer held different accommodation
vocabularies and hotel-area recommendations silently never fired until `_optimizer_input`
translated at the boundary.

So the helper was deleted. `costs.totals()` derives claimed-ness and **returns**
`claimed_cost_ids`, which is what the `/costs` screen reads to mark a row's actual as superseded.
One implementation, one caller, nothing to keep in sync.

The dependency direction settled as `split.py → costs.py`: split rows need `BASE_CURRENCY`,
`CATEGORIES` and the currency validator. The reverse would be a cycle, which is why the tag →
category map lives in `split.py` and `apply_rates()` stamps a resolved `category` onto each row
before `costs.totals()` ever sees it.

## Rounding: the remainder spreads rather than landing on one person

`WF-018` requires one documented rounding rule and says which participant absorbs the remainder.
The donor's `equalSplit()` dumped the whole remainder on the first person, which over-charges them
by up to `count - 1` satang. Since the ticket says `equalSplit()` is **ported rather than reused**,
this implementation spreads it one satang at a time over the first `remainder` participants in the
row's own order, capping anyone's error at one satang.

100.00 three ways is `33.34 / 33.33 / 33.33`. The strong invariant is integer, not float:
`test_satang_always_sum_to_the_row_exactly` checks 7 amounts × 8 participant counts and asserts the
satang sum equals `round(amount * 100)` exactly. Money stays 2-decimal floats at the boundary as
`WF-018` decided, with the division done in satang and a `ponytail:` comment naming integer minor
units as the upgrade path.

**This is a deviation from the donor's arithmetic and is recorded here as one.** It is not
visually gated — `WF-025`'s parity gate is element-level and screen-level, not arithmetic.

## The schema bump, and the gate that keeps it honest

`store.py` had no migration ladder: `_initialize()` runs `executescript(SCHEMA)` of
`CREATE TABLE IF NOT EXISTS` statements and then stamps `user_version` unconditionally. So the
bump is three things — two tables added to `SCHEMA`, `SCHEMA_VERSION` 12 → 13, and the copy.

The copy is gated on `0 < on_disk_version < SCHEMA_VERSION`, and that gate is load-bearing in a way
worth writing down:

- **Version 0** is a database the call is creating. There is nothing to preserve, and without the
  gate every one of the suite's ~250 temporary databases would leave a junk copy beside it.
- **An equal version is not a bump.** Reopening a current database must not churn copies.

`test_a_new_database_and_a_current_one_are_never_copied` holds both halves.

Failure behaviour: `shutil.copy2` inside a `try`, any `OSError` re-raised as a `RuntimeError` that
names the source, the target and the cause. Because the raise happens before `executescript`, the
refusal leaves `user_version` at 12 and `split_rows` absent — asserted directly rather than
inferred.

**The pilot database was deliberately not bumped.** `data/tourist.sqlite3` still holds the Taipei
trip at schema 12. The walkthrough ran against a scratch copy under the session directory. Bumping
the only real trip in the file is one-way with no downgrade path, so it is the owner's call to make
deliberately, not a side effect of taking a screenshot.

## The settled marker stores a balance, not a payment

Artifact 023 decided the marker and the rule that any change to a marked traveller's balance
clears it. The mechanism chosen is this repo's own idiom — **hashes are the staleness mechanism, not
timestamps** — applied to money: `split_settled_markers` stores the net that was settled, and
`settled` is derived by comparing it to the current net.

That means no write-time cascade across every split-row mutation, nothing to keep in sync, and it
cannot drift. Clearing is silent and reversible exactly as decided.

**Observed live**, which is the best evidence for it: Mum's balance read 5,541.61 with a ✓ Settled
marker. Recording a new 900 THB bill shared by the owner and Mum moved her balance to 5,991.61 and
the marker silently stopped applying. Dad's balance was untouched by that bill and his state did
not move.

One accepted edge: if a balance changes and then changes back to the marked amount, the marker
reappears. The amount the owner called settled is the amount showing, so this is defensible rather
than merely tolerated.

## Decisions taken while building

- **The owner is the cardholder.** `WF-018` says settlement stars through "the trip's main
  cardholder" and Auto-Bill made it selectable, but nothing in setup stores one and every line of
  artifact 031's wording is "you". `PlannerActions.CARDHOLDER = "owner"` with a `ponytail:` comment
  naming the upgrade. Adding a stored setting would have been a third mutable record for a case the
  pilot does not have.
- **No `delete_split_row`, anywhere.** Removing a row voids it, so there is no delete to write or to
  expose on the allowlist. `test_the_split_ledger_is_reachable_but_deletion_is_not` asserts the
  absence, which makes the decision structural rather than a convention.
- **One arithmetic path for all three split modes.** `equal_all` and `selected` differ only in how
  the participant list was chosen; `single_payer` is that same equal split across a list of one.
  Mode is validated for consistency and otherwise carries intent for the screen.
- **Count wording is label-first.** "Unclaimed paid cost rows: 1" and "Rows: 7 · Voided: 1" rather
  than "1 paid cost rows". `WF-027` rules out an i18n library and Thai does not inflect for number,
  so an English-only plural rule would be machinery for one language. The first live capture caught
  this — it read "1 paid cost rows" — along with a zero difference wrongly coloured as under-budget.
- **`LanguageProvider` gained an optional `initial` prop.** There was no way to render the Thai
  screen in a test; the closing check requires exactly that. Default unchanged, no caller touched.

## Deliberately not built, and when to add it

- **The inline "record as actually spent →" action on `/costs`** (artifact 031's question 8). The
  same claim is made by choosing a planned row in the split form's *Claims a planned row* selector,
  and `/costs` links across. Add it if the flow proves undiscoverable in use.
- **A tag → category assignment surface.** The seven categories are seeded as identity and anything
  else falls to `other`. The ledger starts empty by decision, so no owner-invented tag exists yet to
  assign. Add it when one does.
- **A hide-voided control** (artifact 031's question 7, which says "later"). Voided rows accumulate
  on a long trip; the Taipei trip is six days.
- **The money workbook** (`{trip}-money.xlsx` from artifact 030). Not in S2's row or its closing
  check; it belongs with the export work.

## Two things about state outside this slice

- **The accent is house red, not Taiwan teal.** `tokens.css` carries the country → accent mapping
  (D6) but nothing sets `data-country` on the root yet. That is app chrome, which artifact 033 puts
  in **S3**, so red is correct for S2 rather than a defect. Artifact 031's teal prototype will match
  once S3 sets the attribute.
- **The project graph was not rebuilt.** `--check` passes at 1358 nodes and 3185 directed edges, so
  the gate is green, but the graph does not yet know about `split.py` or the two screens. A rebuild
  is paid (~US$0.07 at S1's rate) and `CLAUDE.md` reserves it for an explicit ask or a
  topology-changing milestone. Left for the owner to trigger.

## Still owed before `Auto-Bill-Splitter` is archived

Unchanged by this slice and still unmet: one backup JSON per trip, and the 41 isolated element
captures for `WF-025`'s parity baseline. Both need the donor runnable and both are lost once it is
archived. Neither blocks S3.
