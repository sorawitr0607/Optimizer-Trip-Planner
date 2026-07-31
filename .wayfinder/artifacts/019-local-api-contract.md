# Local API contract — the thin HTTP layer between React and `PlannerActions`

Resolves `Lock the local API contract between the webapp and the planning core` (WF-019).

Decided 2026-07-31 through the API-contract interview. Every count below was measured against the
checkout at `1f83fa7`, not estimated. Paths are repo-relative.

## Counts up front

| Measure | Count |
|---|---|
| `PlannerActions` public methods | 56 |
| — with positional-only params (would break `**kwargs` dispatch) | **0** |
| — `get_`/`list_` reads vs other verbs | 17 / 39 |
| — returning a dataclass rather than dict/list/scalar | 18 |
| — called by the Streamlit UI today | 52 |
| — **that must never be exposed** (internal write paths) | **2** |
| `raise ValueError` in `actions.py` | 46 |
| — reaching a caller as an owner-visible refusal | 45 |
| — internal invariant, caught before it escapes (`actions.py:209`) | 1 |
| Distinct refusal codes those 45 raises collapse into | **26** |
| `except ValueError` sites in `views/` + `ui/shared.py` | 18 |
| New runtime dependencies introduced by this contract | **0** |
| Threading primitives in the repo before this contract | 0 |

## 1. The eight decisions

| # | Decision | Chosen |
|---|---|---|
| 1 | Framework | stdlib `http.server.ThreadingHTTPServer` |
| 2 | Endpoint style | RPC per action — `POST /api/<method>` |
| 3 | Error taxonomy | `PlannerRefusal(code, **detail)` raised by the core |
| 4 | Long operations | Block the request + a persisted in-flight marker |
| 5 | Wire shape | One generic `jsonable()` in the transport |
| 6 | Boundary guard | Require `application/json`, validate `Host`, bind `127.0.0.1` |
| 7 | Provider/paid status | `{status, code, detail}` — same shape as a refusal |
| 8 | Serving | Vite proxy in dev; Python serves `web/dist` on one port for real use |

### 1.1 Framework — stdlib, zero new dependencies

`pyproject.toml` stays at four runtime dependencies. The usual objection to the stdlib server —
threads and SQLite — does not apply here: `store.connect()` (`store.py:314`) opens and closes a
connection per operation, so there is no shared connection and no `check_same_thread` problem. The
transport is ~100–150 lines that must carry their own tests, because a transport bug returns a wrong
answer rather than crashing.

Accepted costs: no request validation (a misspelled field arrives as a Python `TypeError`), no
OpenAPI so React's types are hand-written, no hot reload. The stdlib docs' "not for production" note
is accepted because `127.0.0.1` for one owner is exactly the documented use.

**The escape hatch is real and depends on decision 2.** Moving to FastAPI later is cheap while the
style is RPC — the dispatch dict becomes a router loop — and expensive once REST URLs have been
hand-designed. FastAPI was rejected now for one measured reason: 56 endpoints × request + response
would be ~110 Pydantic classes duplicating dataclasses that already exist, when the actual truth is
`freeze_snapshot`'s SHA-256, and the failure mode of a stale response model is *silently dropping a
field*.

### 1.2 Endpoint style — RPC per action

`POST /api/<method>`, body = that method's keyword arguments, verified to bind for all 56 because
none has a positional-only parameter. The transport provably holds no business rule, which is this
ticket's hard constraint — there is nowhere in a dispatch dict for one to hide.

REST was rejected because 39 of the methods are verbs with no resource shape, and the verb-to-URL
mapping is where business meaning leaks in: `PUT /plan/active` asserts idempotent overwrite, but
`activate_plan_preview` *refuses* on hash mismatch (`actions.py:400`), so the URL would claim
something the core does not do. Hybrid was rejected because its only real win is cacheable GETs, and
one owner on localhost against SQLite has nothing worth caching. Read-only `GET` aliases stay cheap
to add later if address-bar debugging is wanted.

Accepted costs: everything is POST, no HTTP caching, status codes meaningful only on errors, and a
convention nobody arriving from REST will expect.

## 2. The exposed surface is an allowlist, and two methods are barred from it

**The dispatch table is an explicit literal tuple of method names. Never `dir()`, never
`inspect.getmembers`.** This is a security rule, not a style preference, because introspection would
expose both of the following:

| Method | Why it must never be reachable from a browser |
|---|---|
| `save_plan_version` (`actions.py:708`) | Takes an **arbitrary** `snapshot` mapping and writes it as an immutable plan version, `activate=True` by default, with no optimizer validation. Exposing it bypasses `activate_plan_preview`'s hash gate and its `status == "ready"` / `validation.valid` check entirely — a complete bypass of the activation safety model. Legitimate callers: activation and revision, internally. |
| `record_paid_call` (`actions.py:1399`) | Writes the trigger-protected append-only paid ledger with a caller-supplied `operation` and `count`. Exposing it lets the browser forge or spam ledger rows in a table designed to be unfalsifiable. `_spend` (`actions.py:1419`) is the only legitimate caller. |

The initial allowlist is the **52 methods the Streamlit UI proves are needed**, minus those two,
leaving **50**. `get_trip` and `list_discovery_runs` are safe reads that join the list when React
asks for them. Adding a method to the allowlist is a deliberate one-line act, which is the point.

## 3. Response and error envelope

- **Success: no envelope.** A 2xx body *is* the method's return value, passed through `jsonable()`.
  It may be an object, an array, a number, or `null` (for the methods returning `None`).
- **Failure: always the same shape** — `{"code": "<stable_code>", "detail": {...}}` with a non-2xx
  status. One rule, stated once: a 2xx body is the return value, a non-2xx body is the error shape.

### 3.1 `jsonable()` — the whole wire contract

```python
def jsonable(value):
    if isinstance(value, FrozenSnapshot):
        return {"data": value.as_dict(), "sha256": value.sha256}
    if is_dataclass(value):
        return {f.name: jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value
```

Three properties matter, in order:

1. **`sha256` is exposed and never accepted.** The UI genuinely needs it — the stale-setup warning
   compares hashes (`views/places.py:57`) and it is the `@st.cache_data` key for exports
   (`ui/shared.py:334`, `:347`). But enforcement stays server-side, where `activate_plan_preview`
   recomputes `freeze_snapshot(self._optimizer_input(trip_id))` itself (`actions.py:400`). **No
   endpoint ever takes a hash as an argument.** The client is told the hash; it is never trusted
   with it.
2. **`canonical_json` is dropped deliberately.** The browser cannot re-verify a hash and has no
   reason to. Written down as intent so a later reader does not "fix" it.
3. **`FrozenSnapshot` nests as `{"data": …, "sha256": …}` rather than flattening**, so a payload
   carrying its own `sha256` key cannot collide with the snapshot's.

Accepted cost: the wire shape is implicit, so a core field rename silently renames a JSON key with
no error at the boundary. **Mitigation is required, not optional** — one contract test that snapshots
the serialized JSON for each of the 18 dataclass-returning methods.

## 4. Refusal codes — the 45 raises collapse into 26

`PlannerRefusal(ValueError)` lives in the core and carries a stable `code` plus structured `detail`.
It **subclasses `ValueError`**, so all 18 existing `except ValueError` sites keep working untouched
and the migration is additive.

```python
class PlannerRefusal(ValueError):
    def __init__(self, code: str, **detail):
        self.code, self.detail = code, detail
        super().__init__(code)
```

This fixes a live Phase 1 defect, not just a Phase 2 need: 46 refusals carry English prose that 18
view sites render with `str(error)`, so **a Thai owner reads English at every refusal today**, against
a mandatory-bilingual requirement the repo otherwise honours through `OPTIMIZER_CODE_TEXT`,
`REJECTION_TEXT` and friends.

### 4.1 Unknown reference — 5 codes, 18 raises → **404**

| Code | Raises | Lines |
|---|---|---|
| `unknown_trip` | 13 | 144, 174, 303, 334, 717, 746, 925, 1107, 1160, 1233, 1443, 1460, 1810 |
| `unknown_candidate` | 2 | 288, 340 |
| `unknown_plan_variant` | 1 | 409 |
| `unknown_plan_version` | 1 | 730 |
| `unknown_checklist_item` | 1 | 886 |

### 4.2 Stage gate not satisfied — 9 codes, 14 raises → **409**

| Code | Raises | Lines | Today's prose |
|---|---|---|---|
| `setup_not_confirmed` | 2 | 176, 440 | Confirm the trip setup before discovery / ranking |
| `setup_missing` | 2 | 748, 927 | Save the trip setup before … |
| `discovery_missing` | 2 | 442, 1224 | Discover candidates before ranking / time zone |
| `discovery_stale` | 1 | 444 | Discovery belongs to an older setup |
| `discovery_empty` | 1 | 447 | Current discovery has no candidates to rank |
| `preview_missing` | 1 | 399 | Generate a plan preview before activation |
| `preview_stale` | 1 | 402 | Plan preview is stale |
| `variant_not_ready` | 1 | 419 | Only a fully validated Ready variant can become active |
| `no_active_plan` | 3 | 1557, 1650, 1816 | Activate a plan before revising / exporting |

### 4.3 Owner input incomplete or invalid — 6 codes, 7 raises → **422**

| Code | Raises | Lines |
|---|---|---|
| `no_places_chosen` | 2 | 461, 930 |
| `place_not_chosen` | 1 | 1064 |
| `insufficient_geocoded_places` | 1 | 1236 |
| `invalid_time_window` | 1 | 1067 |
| `accommodation_query_missing` | 1 | 1110 |
| `invalid_paid_cap` | 1 | 1383 |

`no_places_chosen` covers two different thresholds (a rated place for ranking, any chosen place for
opening hours); the requirement goes in `detail`, not in a second code. `insufficient_geocoded_places`
stays separate because "two, with coordinates" is a genuinely different condition.

### 4.4 Revision state — 5 codes, 5 raises → **409**

| Code | Line |
|---|---|
| `revision_already_pending` | 1562 |
| `no_pending_revision` | 1732 |
| `revision_not_applicable` | 1734 |
| `revision_base_moved` | 1739 |
| `revision_no_variant` | 1607 |

### 4.5 Feasibility — 1 code, 1 raise → **409**

`no_planning_time` (line 480) — derived from dates and setup, so it is a state conflict rather than
bad input.

### 4.6 Excluded

`actions.py:209` (`Provider result must be an object`) is an internal invariant caught by the
`except Exception` at `actions.py:214`, where it becomes discovery status `error`. It never reaches a
caller and gets no code.

## 5. Full HTTP status map

| Condition | Status | Body |
|---|---|---|
| Success | 200 | `jsonable(result)` |
| Unknown reference (§4.1) | 404 | `{code, detail}` |
| Stage gate / revision state / feasibility (§4.2, §4.4, §4.5) | 409 | `{code, detail}` |
| Owner input (§4.3) | 422 | `{code, detail}` |
| Method not in the allowlist | 404 | `{"code": "unknown_action"}` |
| `TypeError` from unbound kwargs | 400 | `{"code": "bad_request", detail}` |
| `ProviderUnavailable` | 503 | `{"code": "provider_unavailable", detail}` |
| `ProviderBudgetExceeded` | 402 | `{"code": "paid_cap_reached", detail}` |
| `RevisionInterpretationUnavailable` | 503 | the cause `interpret.py` already names, verbatim |
| Content-Type not `application/json` | 415 | `{"code": "unsupported_media_type"}` |
| `Host` not allowlisted | 421 | `{"code": "bad_host"}` |
| Anything unexpected | 500 | `{"code": "internal_error"}`, detail in the log only |

`RevisionInterpretationUnavailable` reuses the six cause names `interpret.py` already emits —
`missing_credentials`, `offline`, `refused`, `invalid_reply`, `rate_limited`, `api_error` — as API
codes unchanged. No second vocabulary for the same failures.

## 6. The boundary guard, and why a content-type check is a security control

```python
# SECURITY CONTROL, not a courtesy. Do not relax to accept other content types.
# application/json is not a CORS-safelisted content type, so a cross-origin fetch
# using it must preflight; we answer no CORS headers, so the real POST is never sent.
# A form POST needs no preflight but can only send text/plain or urlencoded — both bounce here.
if self.headers.get("Content-Type") != "application/json":
    return self._json(415, {"code": "unsupported_media_type"})
# Blocks DNS rebinding, where an attacker's hostname resolves to 127.0.0.1.
if self.headers.get("Host") not in ALLOWED_HOSTS:
    return self._json(421, {"code": "bad_host"})
```

Roughly eight lines, no token to generate, ship, or rotate. This is not defence in depth for its own
sake: `set_paid_cap` and `delete_trip` are exposed RPCs, so an unguarded local API is a **money-loss
and history-loss path** reachable by any page the owner happens to have open — and the US$10 cap is a
decision in this repo with an append-only ledger behind it, while `trip_deletions` exists precisely
so a deliberate deletion can remove otherwise-immutable history.

Two things are explicitly accepted:

- **The comment is part of the control.** Without it, someone relaxes the content-type check as a
  kindness and silently removes the defence.
- **It does nothing against another local process** (`curl`, another app). Accepted: that is the same
  trust level the SQLite file already has.

A minted startup token was rejected because it would have to reach the frontend through two
mechanisms — an env var at Vite dev time and a file read at run time — putting a new secret on disk
in a repo whose rule is that keys live in the environment and nowhere else.

## 7. Long operations — block, and persist the in-flight marker

A dense-city Overpass discovery run takes about 34 s. Two facts decided this:

1. `discover_places` **persists its `DiscoveryRun` before returning** (`actions.py:257`), so a
   mid-flight refresh loses the spinner, never the data.
2. Today's Streamlit equivalent is a blocking `st.spinner` (`views/places.py:48`) and Streamlit runs
   one script per session, so the page is already fully frozen for 34 s. **Blocking HTTP is parity,
   not a regression.**

The contract:

- `POST /api/discover_places` blocks and returns the completed run.
- The store records a **started-at marker** when a long run begins. That single field buys both
  refresh-safe in-flight state *and* the duplicate-fire guard, through the store where all other
  state already lives — no job registry, no thread lifecycle, no second endpoint, no client state
  machine. The transport stays stateless.
- The guard matters concretely: Overpass grants **2 concurrent slots** and answers 504 immediately
  once they are spent, so a refresh-then-click burst reads as an outage that is really
  self-inflicted.
- **No progress percentage, ever.** Overpass emits no progress signal and answers once, at the end.
  The frontend shows elapsed time. An invented percentage would be fabricated evidence, which this
  product treats as a defect. SSE was rejected for exactly this reason: there is nothing truthful to
  stream unless discovery is split into per-category queries, which would change discovery output and
  is out of scope.

Two implementation obligations follow, and both are written here so they are not rediscovered as
bugs:

- **A stale marker needs an age-based expiry rule** — a crashed server leaves one behind.
- **The marker costs a `SCHEMA_VERSION` bump**, and a newer DB refuses to open on older code
  (`store.py`).

## 8. Serving and timeouts

| Mode | Shape |
|---|---|
| Dev | Vite dev server + `server.proxy` for `/api` → `http://127.0.0.1:<port>`, two processes |
| Real use | One Python process serves `web/dist` **and** `/api` on one port — one origin, so CORS never exists |

Static serving is stdlib too (`SimpleHTTPRequestHandler`), so this adds no dependency, and real use
stays a single command like today's single `streamlit run`.

**The 120 s timeout must be set in both places** — the browser `fetch` and the Vite proxy. Vite's
default proxy timeout will kill a 34 s discovery, and it will fail *in dev only*, which is the most
confusing possible shape for that bug.

Separate origins with CORS headers was rejected because it requires adding the very header whose
absence does the security work in §6, converting a defence into a config value that someone widens
to `*` in a hurry.

Accepted cost of the single-port mode: a stale `web/dist` silently serves an old UI. It needs a build
stamp or a freshness check — a new failure mode Streamlit did not have.

## 9. Provider and paid status — `{status, code, detail}`

One shape for "something went wrong", shared by refusals and provider status, so there is no second
convention to learn:

```json
{"status": "unavailable",
 "code": "provider_unavailable",
 "detail": "HTTPError: HTTP Error 504: Gateway Timeout"}
```

- The vocabulary already exists: discovery has four statuses (`verified` / `stale` / `unavailable` /
  `error`) and the three exception types are `ProviderUnavailable`, `ProviderBudgetExceeded`,
  `RevisionInterpretationUnavailable`.
- `code` drives translated UI copy; `detail` is **explicitly diagnostic**, so untranslated English
  inside it is intentional rather than a bilingual hole.
- This satisfies the product intent that missing provider evidence must be *explained* rather than
  presented as a mysterious mismatch, without inventing a redaction layer that does not exist. There
  is no shared redaction helper in the repo — `usage.py:162` documents "detail never carries a key"
  as a convention only.
- **Keys cannot leak this way, verified:** they travel in `Authorization` headers
  (`providers.py:358`, `:969`), never in query strings, so an exception string cannot carry one.
  What `detail` *can* reveal is which providers are configured — acceptable only because §6 gates who
  can ask.
- The standing rule: `detail` stays `ExceptionType: truncated text`, which is what it already is
  (`actions.py:215`). It is never a request dump.
- `paid_usage_status` is returned in full — spend, cap, per-operation counts, `cap_is_owner_raised`.
  It is the owner's own money on the owner's own machine. `set_paid_cap` stays exposed because the
  owner needs it, and is protected by §6 rather than by hiding it.

## 10. What this hands downstream

| Ticket | What is now settled for it |
|---|---|
| `Choose the webapp stack and project layout` | `api/` is stdlib Python with a dispatch table; `web/` is Vite + React; one port in real use, proxy in dev |
| `Decide the test strategy after Streamlit AppTest dies` | No new test dependency needed: call dispatch directly, or bind port 0 and use `urllib`. Two obligations: the §3.1 contract test, and coverage of the transport's own error mapping |
| `Decide which exporter survives, Python or JavaScript` | `build_export_snapshot` is an ordinary allowlisted RPC returning bytes-producing input; the `sha256` the exporters cache on is already exposed |
| `Decide the offline asset policy for the webapp` | Real use is one Python process serving `web/dist`, so asset delivery is local-file, not CDN |
| `Decide the bilingual copy pipeline for the webapp` | 26 refusal codes plus the six `interpret.py` causes are the new code→text keys the pipeline must carry in both `en` and `th` |

## 11. Explicitly not decided here

- **Whether the `PlannerRefusal` migration is its own ticket.** The 26-code vocabulary is locked, but
  the migration of 45 raise sites fixes a *Phase 1* bilingual defect and is therefore not gated by
  the Phase 2 decision gate. Sequencing it is a live choice, not an oversight.
- The stale-`web/dist` freshness mechanism (a build stamp, a check, or a dev-mode banner).
- The in-flight marker's exact expiry threshold.
- Which non-discovery methods also deserve the in-flight marker — `refresh_routes`,
  `refresh_opening_hours` and `enrich_place_card` are candidates but were not measured.
- Whether `get_trip` and `list_discovery_runs` join the allowlist; React has not asked yet.
