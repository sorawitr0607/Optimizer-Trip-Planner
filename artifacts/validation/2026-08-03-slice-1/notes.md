# S1 — API and web foundation

Authority: `.wayfinder/artifacts/033-phase-2-slice-plan-and-scorecard.md` §1.

## Outcome

S1 is complete. The stdlib localhost API, server-owned journey gates, shared copy and token sources, React
route shell, in-place `StageGate`, and one green command all run together. No ranking, optimizer, active-plan,
schema, paid-cap, or exporter snapshot rule changed.

## What landed

- `api/`: literal 51-method RPC allowlist, generic `jsonable()`, 26-code refusal/status map, exact JSON and
  Host guards, workbook/ICS downloads, static SPA serving, and mtime rebuild-on-launch.
- `PlannerActions.journey()`: the five server-owned journey gates; Streamlit now calls the same method through
  a compatibility shim.
- `i18n/copy.json`: one eight-table catalogue for Python and TypeScript. Legacy copy compares byte-for-byte;
  the 24 missing English optimizer strings and the refusal/interpreter vocabularies are bilingual. Unknown
  codes stay visibly ugly as `⚠ CODE`.
- `tokens.css`: light/dark design truth, hard shadows, radius/type/motion/category/participant/country tokens,
  Tailwind v4 theme values, and the workbook's remaining header colour.
- `web/`: the locked React/TypeScript/TanStack/react-router/Tailwind shell, all nine routes, only `/`
  redirecting, an actual trip picker/create path, and generic stage stubs for later slices.
- `scripts/check.py`: eight sequential free gates with stage names, timings, stop-on-first-failure, and one
  exit code.

## Closing evidence

| Gate | Result |
|---|---|
| `uv run --locked python scripts/check.py` | **PASS**, 8 stages in 13.9 s |
| Python unit suite | **248 OK** in 9.974 s |
| Historic regressions | **PASS**, 20 atomic + 7 interaction, 3 variants each |
| Fixture catalogue | **PASS**, 24 rules |
| Provider redaction | **PASS**, self-test only |
| Web typecheck / ESLint / Vitest | **PASS / PASS / 2 tests PASS** |
| Production Vite build | **PASS**, 1896 modules |
| `uv run --locked python -m api --port 0` | deep SPA route **200**, real API POST **200** |
| Directed graph | **PASS**, 1358 nodes / 3185 edges / 137 communities |

The live launch used `TOURIST_LOCAL_SECRETS=off` and a temporary SQLite path, so it could not call a provider
or bill. The temporary database was removed and the server stopped after the round-trip.

## Graph rebuild incident

The first two protected rebuilds extracted successfully and then restored the old graph because Graphify's
cluster overwrite guard retained the larger raw graph after semantic IDs were canonicalized. The wrapper now
stages raw extraction separately and keeps the existing endpoint-loss validator. Its focused regression test
and the final full rebuild pass. All three attempts cost US$0.067015 combined; the recorded cumulative graph
cost is US$0.228995.

## Deliberately not in S1

The nine stage bodies are stubs by the slice plan. S2 owns the irreversible schema bump and money screens;
S3–S5 own the remaining stage surfaces. Self-hosted browser fonts and the local flag sprite remain binding
offline-asset work, but are not S1 closure items; add them before the visual parity gate, not as foundation
scaffolding. This bundle is published with the S1 implementation; Git history is the publication record.
