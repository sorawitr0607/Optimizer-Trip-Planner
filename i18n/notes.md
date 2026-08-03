# Copy catalogue notes

`copy.json` is the single source used by Python and TypeScript. The core emits stable codes; copy never
enters ranking, scheduling, or the active plan.

- `TEXT.catalog_table`: the ranked list is also called "Browse all", so the raw provider catalogue needs a
  distinct label.
- `TEXT.provider_verified` through `TEXT.provider_error`: provider availability is evidence status, not plan
  feasibility, so it has its own vocabulary.
- `CATEGORY_TEXT.en`: English is derived from the code. `place_of_worship` is the sole override because its
  preposition must remain lowercase.
- `OPTIMIZER_CODE_TEXT`: the English strings and the new refusal/interpreter strings were machine-drafted on
  2026-08-03 and remain owner-reviewable. Unknown codes render as `⚠ CODE`; they are never prettified.
