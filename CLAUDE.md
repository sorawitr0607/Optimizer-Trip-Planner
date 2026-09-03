# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**This file is the current state.** Dated build history is in `docs/JOURNAL.md`, design decisions in
`.wayfinder/tickets/`, graph and validation mechanics in `AGENTS.md`. Two topics are disclosed rather
than inlined because only some work reaches them:

- Working on the **marketing landing page** or its scenery SVGs — `docs/LANDING_SCENE.md`.
- **Capturing or approving screen baselines** — `docs/SCREEN_BASELINES.md`.

## Commands

```bash
npm --prefix web install                                             # first web run only
uv run --locked python -m localserver                                # local shell on 127.0.0.1:8765
uv run --locked python scripts/check.py                              # every free Python + web gate
uv run --locked python -m unittest discover -s tests -p 'test_*.py'  # whole suite, ~16s
uv run --locked python -m unittest tests.test_optimizer.OptimizerCoreTest.test_safe_route_and_weather_fallback_are_selected  # one test
python3 scripts/validate_regression_fixtures.py                      # fixture catalog structure
uv run --locked python scripts/run_optimizer_regressions.py          # 27 historic cases through the real optimizer
uv run --locked python -m compileall -q api localserver travel_planner scripts tests
python3 scripts/build_project_graph.py --check                       # graph integrity (free)
python3 scripts/check_provider_access.py --self-test                 # redaction check, no network
uv run --locked python scripts/check_design_tokens.py                # token gate: 13 accent triples, no literals, ancestors, 4.5:1 contrast
uv run --locked python scripts/check_reference_coverage.py           # structural coverage of the four reference workbooks
```

All commands run from the repo root: `tests/` imports both `travel_planner` and `scripts` as top-level
packages via cwd on `sys.path`. Python has no linter or formatter; `web/` uses ESLint and deliberately has
no formatter.

`scripts/check_provider_access.py --live-paid` makes billable Google requests. Don't run it unasked.

Counts that used to be written here — test count, refusal codes, allowlist size — are asserted by the
tests instead. They drifted every time they were also prose. Read the assertion, not a number in a doc.

**To run what you just changed: restart the server, then hard-reload the browser.**
`ensure_web_build()` runs **only at startup**, and only rebuilds when a source is newer than
`web/dist/index.html` — so a server left running never picks anything up, and a tab left open holds the
old JavaScript even after it does. Six rounds of owner testing produced reports of fixes "not working"
that had been verified working minutes earlier, and every one was this. The sidebar prints
`build <timestamp>` for exactly this reason: if it does not match the build just made, nothing about
behaviour is worth discussing yet. **The worker holds the code it started with too** — restart it after
changing anything it imports.

## Rules that bind new work

Each of these was learned by breaking it. The journal entry behind each is in `docs/JOURNAL.md`.

**Data, money and access**

- `TOURIST_DB_URL` **overrides the path it was handed**, so any shell that exports it redirects
  everything that builds a store — tests included. It is cleared in `tests/__init__.py`,
  `scripts/check.py` and `scripts/check_reference_coverage.py`. **Any new script that builds a store
  for verification must clear it too.** It has written test trips and fabricated ledger rows into the
  owner's hosted database twice. A guard at one entry point is not a guard.
- **`TOURIST_DB_URL` is a *template* in `.env`, not a literal — it reads
  `"$POSTGRES_URL_NON_POOLING"`.** Passing that commented line's value through verbatim starts a worker
  that loops on `missing "=" after "$POSTGRES_URL_NON_POOLING"`. The variable to read is
  `POSTGRES_URL_NON_POOLING`, per-command and never exported.
- **Do not bump `SCHEMA_VERSION` against a hosted database.** `PostgresStore._copy_before_bump`
  refuses outright, correctly — the file-copy backup a bump demands has no hosted equivalent until
  the owner decides what it is.
- `supabase/schema.sql` is **generated from `store.SCHEMA`**, never hand-edited. A second schema is a
  second source of truth. `supabase/backups/` is the **live structure recovery artifact**, not a second
  schema source; refresh it with `scripts/backup_supabase_schema.py` after hosted structural changes. It
  deliberately contains no rows, so it does not satisfy the private data backup a destructive migration
  requires.
- **Every paid provider call routes through `actions._spend()`, and `_spend` goes before the request on
  every path.** An unpriced operation raises rather than being assumed free; the ledger is append-only
  by trigger. `_area_amenity_counts` had it after, so the cap was consulted only once the call had gone
  out — the one operation that could cross a spent cap rather than be refused by it. It is priced at
  US$0.00, which is exactly why nothing was overspent and why it went unnoticed: **the ordering is the
  invariant, not the amount**, and the next operation copied from it will not be free. A US$0.00
  operation also cannot be refused *by* the cap, so test the ordering directly.
- **A client-supplied bound is a server-side clamp.** `generate_plan_preview`'s `time_limit_seconds`
  is spent once per variant, so an unbounded value held the single worker for as long as the caller
  liked — past `STALE_AFTER_SECONDS`, where the still-running job is handed to a second worker.
  `bounded_preview_seconds` is the bound; a cap is worth testing directly.
- `costs.py` converts owner-recorded expenses into THB against an owner-editable, timestamped rate
  snapshot. **A paid charge locks its actual THB** so a later rate cannot rewrite it, and a missing
  rate stays a visible gap rather than a guess.
- **Anything that calls a provider must load credentials, and log how many it loaded.** The worker did
  not, so every route job raised "not configured" and the failure only surfaced as an empty plan three
  minutes later.
- **Hosted egress is the first release criterion: exhausting it disables the app.** Supabase's free tier
  allows 5.5 GB and this trip passed it, so `scripts/check.py` runs `tests.test_discovery_egress` before
  every other gate. `paid_usage_status()` must aggregate with `summarize_paid_usage()` in SQL; raw ledger
  reads require an explicit limit of at most 1,000 rows; and a zero-price `_spend()` must never read the
  ledger before recording the call. Do not replace any of those with a Python-side total.

  **A field nothing reads still costs on every read.** Candidate-level `evidence` had eleven fields and
  no reader in the planner: `_evidence_score` — the function named for it — scores
  `operational_evidence`, `names`, `website`, `provider_aliases` and `signals` and never touches it, and
  it is not in the browser's `DiscoveryCandidate` type. Eight of the eleven were constants or duplicates
  besides: four were one value on every candidate, `license` follows from `provider`, `confidence` from
  `status`, and `provider_place_id`/`source_url` sit in `provider_aliases` beside it. On a
  3,073-candidate catalogue that was **43% of the blob**. Trimmed to `provider`, `status` and
  `retrieved_at`, the mean stored catalogue went **807 KB to 598 KB**; `tests.test_setup_discovery` pins
  the key *set*, not a size, so a field cannot come back without a reader.

  **Measure the wire, not the disk.** `pg_total_relation_size / n_live_tup` reports *compressed TOAST*
  and understated the catalogue about fivefold. Quote `octet_length`, because that is what crosses the
  wire: `candidates_json` is **630 KB median, 3.23 MB largest** across 19 live runs, and
  `jobs.result_json` averages **479 KB and reaches 3.76 MB**.

  **A read that wants four floats must not fetch 390 KB.** `get_latest_discovery` is `SELECT *`, and
  four callers wanted only `query_boundary` — three of them on every `/itinerary` view. Use
  `actions._discovery_boundary()` / `store.get_latest_discovery_report()` for anything that is not the
  candidate list itself; navigation uses `get_latest_discovery_header()`. Where a screen genuinely needs
  the catalogue twice, pass the loaded `DiscoveryRun` through — `/places` starts with
  `get_ranked_discovery()`, and `_optimizer_input()` reuses its discovery while ranking.
  `opening_evidence_options()` is deliberately narrower still: confirmed setup, selected choice snapshots
  and opening evidence are enough to price the two build paths, where `_optimizer_input()` would reload
  and rescore the whole catalogue before the choice box can appear.
  **The catalogue is read once per run, not once per caller.** `PlannerActions.get_latest_discovery`
  memoises the `DiscoveryRun` on the run id and validates it with the 111-byte header on every call.
  That is sound *only* because `discovery_runs` is append-only — enforced by the
  `discovery_runs_no_update` and `discovery_runs_no_delete` triggers — so a run id names bytes that
  cannot change and the invalidation is the id, never a clock. It is not licence to cache anything
  mutable. Without it, `_current_choice_inputs` runs on **every swipe** and a twenty-card session paid
  for the same immutable blob about forty times — 129 MB to record twenty verdicts. Route internal reads
  through `self.get_latest_discovery`, never `self.store.get_latest_discovery`.

  **Navigation reads two columns, not every chosen place.** `journey()` runs on every page load and
  wants only which actions exist; `store.list_candidate_actions()` is that read. The `SELECT *` it
  replaced carries `candidate_json` at **1.1 KB a row on the wire** and ran 8,110 times in two weeks.
  `list_candidate_choices()` stays for the callers that genuinely need the place — ranking, the
  optimizer input, the checklist — and `journey()` still uses it in the one branch reading
  `operational_evidence`.

  **`list_route_snapshots` is the same shape** — `SELECT *`, and a route carries its drawn geometry, so
  five hundred of them is most of a megabyte. Anything that only needs to know *whether* a pair is
  measured takes `store.list_route_pair_keys()`.

  **A job poll must not select `result_json` before it returns one.** `JobQueue.status()` is the poll's
  read and `JobQueue.get()` stays the worker's. The column is NULL until `complete` writes it, so the
  saving on an ordinary build is small; it matters for polls that meet a *finished* job they were not
  waiting for — a reload mid-build, a second tab, a retried poll — where `SELECT *` moves up to 3.76 MB
  to answer a status string.

  The roughly 217 KB basemap is immutable until its evidence expiry, so `shared/basemap.ts` keeps it in
  browser storage until the server-provided `expires_at`. Do not replace that with a cache for mutable
  plan or route snapshots without measuring another egress problem first.
- **A worker started without `TOURIST_DB_URL` drains the *local file* and looks perfectly healthy doing
  it.** The deployed app queues into Postgres, so its jobs sit forever while the worker reports nothing
  wrong — `find places` simply times out at the client's 120 s abort. Diagnose it by what the worker is
  *not* holding: no `psycopg` in `lsof -p <pid>`, no TCP connection, and a local `jobs` table with zero
  rows while the hosted one has a backlog. The second line of its output is the direct answer —
  `draining PostgresStore` or `draining SQLiteStore`.
- **The worker's idle poll backs off from 2s to `MAX_IDLE_SLEEP_SECONDS` (10s) and resets on any job.**
  A flat 2s is 43,200 queries a day whether or not anyone is using the app. Keep the ceiling below
  `REAP_EVERY_SECONDS` or abandoned jobs slip a whole reap cycle.
- **The worker's loop outlives one bad poll.** `reap_stale`/`run_one` raise on a transient drop;
  bare, that ended the process with the job still `running` and launchd turned it into a 30-second
  crash-loop. The loop catches, logs, backs off, retries. Recording the failure stays inside
  `run_one` — if `fail` cannot reach the database, the reap is the recovery.
- **The worker's health endpoint answers any GET on an unauthenticated `0.0.0.0:$PORT`.** It published
  `worker_id` — `hostname:pid:random`. `worker.initial_state` is now the whole of what it may say, and
  it is a function rather than a literal because it is a security boundary worth testing directly. The
  id is unchanged in the log and in `claimed_by`, which the owner reads and the internet does not.
- Provider retries are **three attempts, four seconds apart, and only for 429 and 5xx**. A 400 or 404
  is the endpoint saying "not this"; repeating it spends the budget to be refused identically.
- Trip ownership is checked in **`dispatch` for everything trip-scoped**, and in `api/rpc.py`'s
  `handle()` for the two paths that bypass it — `job_status` and the deferred enqueues. A check
  written 108 times will be missing from the 109th; the 109th and 110th were a full plan result
  answering any job id, and discovery enqueued against a stranger's trip.
- Anything whose effect is deployment-wide answers to **`OWNER_ONLY_ACTIONS` and the admin key**:
  `set_paid_cap` is the only member. `dispatch` compares `X-Planner-Admin` against
  `TOURIST_ADMIN_KEY`; `api/rpc.py` refuses outright when the variable is unset — hosted is
  fail-closed, a local single-user run without the variable stays open. The browser keeps the key
  beside the owner token and prompts once. Unlike the owner token, this one is offered as a secret.

**The core**

- The dependency direction under "Architecture" is one-way and enforced by review. Replacing the whole
  interface at S6 cost the core nothing because of it.
- **Every new output reads `build_export_snapshot()`**, never the raw variant — that is what keeps
  times, totals and statuses from diverging between outputs.
- **`/optimize` reads its assumptions out of the frozen `optimizer_input`, never recomputed.** The
  snapshot records its own `capability_gaps`; a second opinion derived beside it could disagree with
  the plan it claims to describe.
- **`optimize_trip`'s `on_variant` is the one hook in the pure core, and it observes only.** It imports
  nothing, takes a count, returns nothing, and is never read back — the three variants are ~21s each and
  the call was otherwise a silent minute on every build path but auto-resolve. The property that keeps it
  honest is asserted, not assumed: the same input produces the same `deterministic_signature` whether or
  not a hook was passed. Anything that wants to *influence* the optimizer does not belong here.
- The destination string is **`"City, Country"`** — `AppShell.countrySlug()` takes the last
  comma-separated segment, so a city-only string silently loses the destination accent.
- **A slow operation must be queued.** `DEFERRED` is derived from `HANDLERS`; anything inline over
  ~60s answers `http_504` on the deployment while working perfectly locally.
- **A poll must survive one network failure; the build must not die of it.** A build is 30-90s against a
  1.5s poll, so one run asks about sixty times, and `fetch` rejects with a bare
  `TypeError: Failed to fetch` for anything below HTTP — a cold start closing an idle socket, DNS, a
  phone changing network. One such rejection used to throw straight out of `rpc`'s poll loop and fail a
  build the worker was finishing perfectly. A poll is a pure read of a row the worker owns, so it
  retries. **Only network-level failures**: an `ApiError` means the server answered — 404 `unknown_job`,
  403 `not_your_trip` — and retrying would bury a real refusal under a five-minute wait. The existing
  `deadline` still bounds it, as `job_unreachable`.
- **A queued job's client deadline measures *silence*, not duration.** As a flat ceiling on total runtime
  it did the opposite of its purpose: a `refresh_routes` sweep stored 462 routes in **843 seconds**,
  finished cleanly, and the browser had thrown `job_timeout` at 300. Any rise in the reported count
  resets the clock, and `run_one` writes a `0` on claim so being picked up resets it too — five minutes
  unclaimed still fails, which is the case worth reporting. An operation that reports nothing keeps the
  flat five minutes; every operation is bounded server-side anyway. The corollary: **an operation that
  can outlive the deadline must report often enough to prove it is alive** — a slow provider can spend
  five minutes inside one pass of sixty, which is why `ROUTE_PROGRESS_EVERY` speaks every ten routes.
- **A paid refusal must be remembered, or it is bought again.** `_spend` is recorded *before* the
  request, so a `ProviderNoMatch` costs US$0.025 and returns nothing — and the screen said "asking again
  will not find more" while the button sat there letting you. A `provider_no_match` evidence row refuses
  the second ask before spending, expiring after `PROVIDER_NO_MATCH_DAYS` so a place Google later indexes
  becomes askable again. Only `place_not_in_provider` sets it; a provider outage does not. The same rule
  on the other side: the deck's buy button withdraws once a place has been enriched, because a purchase
  that returned one photograph will return one photograph again. `get_ranked_discovery()` piggy-backs the
  durable no-match ids onto the catalogue response so the deck and detail buttons agree after reload with
  no extra catalogue read.

  Two shapes to know. **`list_place_evidence` returns the stored snapshot, not the row**, so anything
  needing `place_id` back must put it *inside* the value — which is why `list_venue_notices` does. And
  **it returns expired rows**, doing no freshness filtering on purpose, since venue notices and assumed
  windows judge their own. That made `PROVIDER_NO_MATCH_DAYS` decorative — written and never read, both
  photo controls withdrawn for good, reported as "it is always hidden after I once hid it".
  `actions._provider_no_match_ids()` is now the one read both callers use and it compares `expires_at`.
  A third caller of a *gating* evidence kind must filter the expiry itself; the shared read will not.
- **Two controls that buy the same call must withhold on the same condition.**
  `PlacesPage.photoWithheld(placeId)` is that condition — bought / not in Google's index / just asked and
  failed — and both the deck's "Get photographs from Google" and the detail panel's "Load live details"
  consult it. They had drifted, so one card offered the purchase in one place and refused it in the
  other. Affordability is deliberately **not** in there: whether the cap allows a purchase is a fact
  about the trip, and the two surfaces are right to present it differently — the deck has no button, the
  panel keeps a disabled one under the price so the reason is on screen. `PlaceDeck` takes
  `photoWithheld` and `photoErrorOf` as **functions of a place id**, not booleans, so a card cannot be
  told about a different card: the scalars they replaced were derived from `cardId`, the id the deck last
  *reported*, while the card drawn is `queue[0]`.
- **One worker runs one job at a time, so a long job is a queue-wide outage.** Measured: an 843-second
  `refresh_routes` sweep left `generate_plan_preview` — *three seconds* of work — waiting 482s to be
  claimed, and discovery waiting 885s, which the client correctly reported as `job_timeout` on a build
  that had not started. **Bound anything that can run long.** `ROUTE_SWEEP_SECONDS` stops a sweep
  starting a new pass after sixty seconds. A job that stops early must say so (`more_pairs`) and the
  caller must come back; when it does, `onProgress` needs a running base, because each job counts from
  zero and a stage that restarts at every request is worse than no count. Do not "fix" a long job by
  widening the client's patience — that hides the starvation from the one place that can see it.
- **A bound checked between passes is not a bound.** `ROUTE_SWEEP_SECONDS` was read only where a *new
  pass* would start, and one pass of `MAX_ROUTE_REQUESTS` at ~2.1s a route is about 128 seconds — so the
  sixty-second budget was already spent by the first check, every job was exactly one pass, and the
  multi-pass sweep it was written to bound never ran a second pass in production. It is read inside the
  request loop now. **Read a deadline where the work actually is**, and when a constant claims a number,
  check the measurement still produces it: the docstring said 110s and the queue said 128.
- **Bounding a job does not shorten the work — it moves it into the caller's loop.** Bounding the sweep
  turned one 843s job into *nine* 128s jobs, so the queue stopped starving and the owner's build went
  from 843 to **1200 seconds**, spinning the whole time because progress resets the client's deadline.
  Read the queue before believing a fix landed: nine consecutive `refresh_routes` rows each reporting
  `progress 60` is what that looks like, and `ran` alone will not show it.
- **Fetch for coverage, not for completeness.** Route evidence is quadratic (41 places are 1640 ordered
  pairs) and the plan needs almost none of it: a place with no route at all is dropped
  `ROUTE_UNVERIFIED`, while a missing pair between two places that each have one is a leg the optimizer
  routes around. Grouping the Tokyo trip's stored rows by retrieval minute shows ten bursts of sixty and
  **every place reached by burst two** — the other eight bought refinement nobody was waiting for.
  `_refresh_routes_with` reports `places_unserved` and `collectRouteEvidence` stops on that rather than
  on `more_pairs`. Secondary: the old `served` set was read once from stored routes, so on a first sweep
  every pair looked unserved and the order collapsed to pure nearest-first. Promoting the nearest pair
  that reaches a starved place fixes it — **both directions**, since `optimizer._best_route` matches
  origin-to-destination and does not read a leg backwards. Two bursts become one.
- **One matrix request replaces sixteen hundred directions requests, and the trade is the drawn line.**
  `OpenRouteServiceMatrixProvider` measures every pair at once — same service, same free tier,
  `openrouteservice:matrix` priced at US$0.00. Measured live at 23 places: **506 pairs in 1.59s**,
  against 0.87s for one directions call — 7.4 minutes of pair-by-pair here, ~17.7 at the deployment's
  2.1s. It returns **no geometry**, so its routes carry `geometry: []` and the map draws them as
  `exact: false` straight lines, which `ItineraryPage` already did for an unrouted leg. `refresh_routes`
  seeds from it and the directions sweep upgrades pairs behind it, nearest first. Two consequences: a
  matrix row is fresh evidence *and* still upgradeable, so **both** cache checks in
  `_refresh_routes_with` exempt it (the pair filter, and the one inside the fetch loop that the per-pass
  cap is measured against); and the seed degrades to zero on any failure rather than refusing, because
  the worst case must be the behaviour that came before.
- **`MAX_ROUTE_REQUESTS` prices outbound requests, so a provider that makes none per pair is exempt.**
  `refresh_transit_routes` runs through the same `_refresh_routes_with` and inherited the sixty-pair cap,
  and `collectRouteEvidence` calls it **once** — sixty of a 22-place trip's 462 ordered pairs is 13%, so
  seven pairs in eight held only a walking route and the optimizer took "the shortest route it holds".
  That is the whole of the owner's Tokyo plan walking 8.5, 9.5, 15.7 and **17.6 km** between sights:
  nothing fabricated and nothing unverified, the metro leg simply did not exist to be compared against.
  `OsmMetroProvider.build_graph` memoises after one Overpass call and `GtfsTransitProvider` reads a local
  file, so both set `answers_pairs_locally` and sweep every pair. The **deadline** is what bounds such a
  job — `refresh_transit_routes` had none, survivable only while the count cap bounded it by accident.
- **A `route=subway` relation lists its own platform nodes, so without grouping the metro graph has no
  interchanges at all.** Two lines meeting at one station arrive as two unrelated ids with no edge
  between them, so `journey` — which already charges `TRANSFER_PENALTY_MINUTES` and counts the change —
  was never *offered* a transfer. Measured on live Overpass for Tokyo: 1489 stops, 2194 edges, **every**
  successful journey reporting `transfers=0`, and Hama-rikyu to Shibuya, 5.6 km across the middle of the
  city, answering `None`. `_station_of` groups on normalised name within `STATION_GROUP_METRES`: **496
  stations**, 6 of 7 sample pairs served. **Merge the nodes; do not add transfer edges** — a transfer
  edge must spend its walk as `ride_minutes`, which `walking_minutes` cannot see, and `walking_minutes`
  is what the comfort cap measures, so a leg would pass a walking budget by hiding the walk. Grouping
  stays conservative: an interchange whose halves carry *different* names stays unmerged, losing a
  connection rather than inventing one.
- **A fast Overpass 5xx is retried, and the metro query is the third site of that fault.**
  `_attempt_block` has retried discovery since `WF-048` and `_drawing_elements` the basemap since
  2026-08-10; `OsmMetroProvider._metro_payload` was written after reproducing it — two consecutive 504s
  on the Tokyo network, then 200 on the identical query. It costs more here than at either of the others:
  a thin catalogue or a plain map is a degraded answer, but the transit graph is **one** request, so
  losing it sends every pair back to walking. Only a *fast* failure is retried; one that died at the
  query's own 90s timeout would spend another 90s to fail identically. **Widening the query to reach JR
  and private rail is not a free win** — `route=train` pulls every node of routes spanning the country
  through `>;`, and both attempts answered 504. Kawagoe correctly returns no transit for that reason,
  which is the app being honest rather than broken.
- **A queued operation is expensive to ask for, so do not loop on one from the browser.** Every RPC for
  slow work is a job: enqueue, poll at 1.5s, wait for the worker to claim it, poll again — four to twelve
  seconds of latency before the work starts. `collectRouteEvidence` made up to twelve of those in a row
  and that, not the optimizer, was most of a measured ten-minute build. The loop belongs on the server,
  where the passes are consecutive and free: `refresh_routes(max_passes=...)` is the shape, and it
  changes nothing about the work — `_spend` still runs once per route. `force` stays one pass: it
  refetches cached pairs, so a loop would buy the same sixty routes until the ceiling.
- Job payload allowlist keys must match their handler's signature — `tests/test_jobs.py` checks every
  one. An allowlist that permits keys the handler rejects is worse than none.
- **`enqueue`'s look and insert are one transaction, and on Postgres they hold an advisory lock.** They
  were two `connect()` blocks, which is two transactions with a gap: two presses landing inside it both
  read "nothing queued" and both inserted, defeating the de-duplication the method exists for. The lock
  is transaction-scoped and keyed on (trip, kind, payload), so only presses that could actually collide
  wait. Chosen over a partial unique index because that is a schema migration against a hosted database.
- **Postgres text cannot contain a NUL byte, and the Postgres branch of `enqueue` has no test coverage —
  those two facts together broke the deployment.** The lock key was first passed as text for `hashtext`
  to hash, joined on a NUL; every `enqueue` raised `DataError`, which is all four queued operations, and
  "find places" answered `internal error`. `is_postgres` is false on SQLite so the suite could not reach
  the statement, and the probe run against the real database checked the *function overload* with a
  harmless literal rather than the key the code builds — it proved the wrong half. `_enqueue_lock_key`
  hashes with `zlib.crc32` in Python now, so what crosses the wire is an integer with no encoding rules
  to violate, and `tests/test_jobs.py`'s `PostgresEnqueueTest` fakes a store named `PostgresStore` to
  assert the parameters of every Postgres-only statement. **When verifying against a live database,
  exercise the value the code actually constructs.**
- **Deleting a trip must clear its jobs, and `store.delete_trip` cannot.** The queue is deliberately
  outside `SCHEMA_VERSION` with no foreign key to `trips`, so the ordered table list — and the test that
  enumerates every table with a foreign key — can never reach it. A deleted trip left queued work for a
  worker to claim and fail on, `max_attempts` times each. `actions.delete_trip` calls
  `JobQueue.discard_trip` first, so a failure leaves a trip that still exists rather than jobs pointing
  at one that does not.

**The interface — layout, type and navigation**

- **There are three breakpoints — 600, 860, 1100 — and `shell.css`'s header block is the list.** It
  carried **twelve** distinct width values, mixing min and max, so three different rules disagreed about
  where a phone stopped. **860 is load-bearing**: it is also `PHONE` in `shared/useMediaQuery.ts`, which
  decides whether the sidebar or the tab bar is rendered at all, so changing one without the other draws
  a navigation the stylesheet is not expecting.
- **The type scale's small end is not to be touched, and the heading end is where the contrast went.**
  241 of 279 uses sit in the 12-15px band while `h1` was 27px — about 1.8x body, which is why screens
  read as one flat grey. `--text-4xl` is 30 (28 on a phone, where 30 wraps "Split actual bills" at
  500px), `5xl` 34, `6xl` 42; `2xs`/`xs`/`sm` are unchanged because a global bump would reflow 241
  dense-UI call sites. On a phone `tokens.css` redefines `2xs`/`xs`/`sm` one notch up on `:root`, so the
  relationships hold and nothing that lined up stops lining up. `font-size` is not one of the five
  properties the parity gate compares.
- **No touch control may render below 16px, and the rule that enforces it is `!important` on purpose.**
  iOS Safari zooms the whole page when a focused input's text is under 16px and never zooms back. Nine
  rules in `shell.css` set a control to 12, 14 or 15px, all class-scoped, and `shell.css` is imported
  after `tokens.css` — so a bare element selector loses twice over. It is a floor, not a style.
- **The touch floor covers `a`, not just `a.stage-link`.** Driven at a real **390px**, `/itinerary`'s
  five `.plan-next-action` links measured **42px** while every headless capture said the screen was fine
  (see `docs/SCREEN_BASELINES.md` for why the capture cannot check this). Bare `a` is safe for running
  prose because `min-height` does not apply to a non-replaced inline element, which is why the map's
  "© OpenStreetMap contributors" credit correctly stays 16px.
- **An author `display:` on a `<dialog>` beats the user agent's closed-dialog hiding.** The UA hides a
  closed dialog with `dialog:not([open]) { display: none }`, and a class selector outranks it — so any
  dialog class given a `display` needs its own `:not([open]) { display: none }` or the closed sheet
  paints over every phone screen. `.tour-backdrop`, `.sidebar.sheet-dialog` and `.day-stop-lightbox` all
  have it, and `tests/test_dialog_display_guard.py` requires it of the fourth, which will be written by
  someone who has not read this.
- **A wizard chip holds an icon, a number and a short label, and each of the three was measured into
  place.** `STEP_ICONS` is `aria-hidden` and the button carries an `aria-label` of "Step N of 5 ·
  <title>", because `.wizard-step-label` is `display: none` below 1100px and that had been taking the
  name out of the accessible tree entirely. The visible label is the **short** `chip_*` form: the full
  names fit only at 1440px and up. `.wizard-step-icon` needs `flex-shrink: 0` — as a flex item in one of
  five equal columns it was compressed to **2px wide** at 390px, rendered and visible and invisible.
- **`--trip-bar` is the top bar's height, and a sticky control must rest below it.** `.trip-bar` is
  `sticky; top: 0; z-index: 30`, so anything else that sticks near the top parks *inside* its 45px and
  behind it — covered, and untappable where they overlap, which is what happened to the shortlist
  handle. The number is **measured**: reasoning it out from the padding gave 43 against a real 45.
  Re-measure at 390px before changing the bar's padding or type.
- **`--tab-bar` is the one place the bottom bar's height is written**: 56px of target plus a 1px top
  border. Three rules depend on it — the bar, the sticky setup actions that sit on top of it, and the
  padding that keeps content clear — and as three literals they were already 1px out of register.
- **A wide table may stop being a table on a phone, and `.timeline-table` is the one that does.** The
  generic rule gives every wide table its own horizontal scroller, and for the reconciliation table that
  is right. Six columns of timetable at 390px was not: the owner could not see a whole row. Stacking one
  means undoing three things the column layout supplies — cells are `text-align: right`, each draws its
  own dashed rule, and `td + td` adds a 14px gutter — and avoiding two traps: `align-items: baseline`
  pads every grid row to align baselines across columns, and `.money-table tr.timeline-day-start td`
  sets `padding-top` at a higher specificity than a plain `.timeline-table td { padding: 0 }`.
- **Prose on the stage screens takes `--measure-body`**, the same cap the landing page already had.
  `.stage-main` and `.stage-card` have no `max-width`, so a paragraph ran the full 1130px of card at
  1440 — about 140 characters against the ~75 that note gives as the limit. `max-width` only ever
  narrows, so it is a no-op inside a narrow grid cell and on a phone. Do not write a measure by hand and
  do not write one in `ch`; the note above `--measure-body` explains what that costs.
- **`.setup-primary` and `.primary-link` go full width and 48px tall on a phone**, which is Fitt's law in
  a one-column layout — the primary action becomes the widest thing in the card. `.setup-actions` is
  additionally sticky above the tab bar, and **only there**: setup is the one linear screen, and a
  permanent action bar on a board or a report claims a primary action it does not have.
- **`.setup-group` is a named group of controls, and `.setup-hours` was already one.** Step 2 asks "When
  are you travelling?" and also holds the flights either end and where you are sleeping; those topics
  were separated by nothing but proximity. Four `<fieldset>`/`<legend>` groups now, reusing the pattern
  rather than inventing one. The three `.setup-fields > …` rules are extended to reach inside a group,
  since wrapping changed what "direct child" means — miss that and every label inside a group loses its
  layout.
- **The phone and the desktop get *different* navigation, and only one of them is ever in the DOM.**
  `AppShell` renders the sidebar above 860px and `<StageTabs>` below it, chosen by `useMediaQuery` — not
  by CSS — because rendering both puts two `aria-current="page"` claims in one document, which is the
  exact defect `navSemantics.test.tsx` exists to catch. On the phone the sidebar *is* the More sheet and
  appears only while it is open, so the tab bar and the stage list are never both present.
  `useMediaQuery` answers `false` without `matchMedia`, so the node test environment renders the desktop
  shell; assert the phone surface through `StageTabs.test.tsx` rather than by stubbing globals. Keep
  `PHONE` in `useMediaQuery.ts` equal to the 860px in `shell.css`.
- **A tab may be current for a route it does not link to, so the tabs use `Link` and not `NavLink`.**
  `NavLink` derives `aria-current` from its own route match and overrides the prop, which silenced the
  Money tab on `/split` — the one case the feature exists for. The four `covers` sets must stay
  disjoint, or more than one tab claims the page.
- **`stay`, `evidence`, `revise` and `split` never report `done`** — only the five gate keys do, as
  `stages.ts` says. Anything deriving "the first unfinished stage" from `state !== "complete"` will
  therefore stick on `stay` forever; `StageTabs.buildTarget` reads `journey.next` instead, which is the
  same answer `/` redirects to.
- **Light is the default theme regardless of the device.** `ThemeProvider.initialTheme` consults the
  stamped root, then `localStorage`, then answers `light` — it does *not* read `prefers-color-scheme`,
  and neither stylesheet contains such a block, so `[data-theme="dark"]` is the only path to dark. It
  remains a default and not a lock: the toggle still works and is still remembered.
- **`shared/tagIcons.tsx` is the one place a code becomes a glyph**, for three chip rows: trip-style tags
  (`/setup`), readiness categories (`/readiness`) and expense categories (`/split`, `/costs`). Every
  glyph is `aria-hidden` and every chip keeps its word — the icon is a second channel for scanning, never
  the answer. Two of the three vocabularies are **Python tuples**, so `tests/test_icon_tables.py` is what
  keeps the tables exhaustive; a Vitest test cannot read `checklist.CATEGORIES`, and a category added
  there without a glyph would ship wearing the fallback with nothing to say so. `religious_sites` is
  `Bell`, not `Church`: the label is "Temples & shrines", the pilot destination is Taipei, and lucide has
  no torii. **Table cells stay plain** — an icon on every row of a dense table is weight, not help.
- **`shared/dates.ts` owns the calendar arithmetic**, in UTC, and `spanDays` counts **both ends** because
  a pace does: the balanced five-day pace recommends the 1st to the 5th. Off by one there and `/stay`'s
  custom range either refuses the app's own recommendation or allows a sixth day the optimizer was never
  asked to fill. It is a module rather than locals in `StayPlanner` because a file that exports a
  component may not also export helpers — and because a cap is worth testing directly.
- The web runtime is fixed at **six dependencies** (`WF-026`) — the rule GSAP was refused under.
- Only assets actually used are vendored; the unDraw licence forbids pack redistribution.
- Complete a slice vertically, with its own runnable check, before starting the next.

**The build and the plan screens**

- **There are two build paths and they must do the same work.** `/optimize`'s `autoResolveAndGenerate`
  collects route evidence before asking for a timetable; `StayPlanner`'s "use these dates" did not, so a
  first build measured no leg, every place came back `ROUTE_UNVERIFIED`, and the screen said "the route
  and travel time are not verified". Diagnose it from the queue's *ordering*: a `generate_plan_preview`
  row earlier than the trip's first `route_snapshots.retrieved_at` means something built a plan before
  any route existed. `PLAN_STAGES` carries `routes` because the call is there; adding one without the
  other is the fiction `BuildStages` exists to refuse.
- **Before adding a control to `/optimize`, grep for `autoResolveAndGenerate.mutate()` and count the
  call sites.** That control has been wrong three times, each time a second button running the same
  mutation under a different label.
- **`BuildStages` takes a stage list, and every list is the calls its page awaits.** `BUILD_STAGES` is
  `/optimize`'s four; `PLAN_STAGES` is `StayPlanner`'s three — `save_setup`, `discover_places`,
  `generate_plan_preview`, pinned to three by `stayplanner.test.tsx`. The rule is the whole point: **a
  stage ticks when its call returns, never on a timer.** Adding a stage that no `await` corresponds to is
  a claim about work that is not happening. `PLACES_STAGES` is the odd one — four of its five are
  reported by the **worker** rather than awaited by the page, because `/places` is one queued job, and
  the count still moves only on a call returning. `AREA_STAGES` is the fourth: `recommend_areas` is a
  queued job that reported nothing, so `/stay` showed one rotating line through tens of seconds of
  Dijkstra over every station and then an Overpass request. Its walking fallback, for a destination with
  no metro graph, reports 1 and then 3 — it genuinely skips the shortlist, and marking it would be the
  invented milestone `REPORTS_PROGRESS` refuses.
- **`Thinking` claims no milestones of its own — everything above it does.** The long
  `generate_plan_preview` really has no milestones, so `Thinking` stays inside that stage with a rotating
  line. Never advance a stage from a timer: a green check meaning "probably by now" is the same defect as
  printing a placeholder as a finding. `BuildStages` owns the realistic per-step range and the native
  `<progress>` value below the Ready row.
- **Give `Thinking` a `startedAt` wherever it can be remounted mid-wait.** It counts from its own mount
  otherwise, and `/places` moves it into the active stage the instant the worker first reports — a new
  position in the tree, so a new mount. The counter reset to zero part-way through a 30-90s wait, which
  is the precise "it looks like it hung" that counter was added to answer. It reads off the clock now,
  initial state included so the remount does not flash `0s`.
- **The time estimate lives on the progress bar, as a clock, and is the one thing a timer may drive.**
  `remainingSeconds` sums the **ceilings** of the stages still pending and `Countdown` counts that down
  beside the percentage. The ceiling and the "up to" wording are deliberate: a counter that reaches zero
  while the build carries on is a promise broken on screen, so the ordinary build finishes with time
  left, and past the ceiling it says it is taking longer rather than sitting at 0:00. No stage and no
  percentage moves on time; only the clock does. `Countdown` is mounted with `key={budget}` so a stage
  returning remounts it on the new number — resetting that state from inside an effect is what
  `react-hooks/set-state-in-effect` forbids, and the lint rule will stop you.
- **A queued operation describes its own wait, or nothing can.** `jobs.REPORTS_PROGRESS` names the
  operations `run_one` hands a `progress` sink to; they write a **count** into `jobs.progress`,
  `job_status` carries it, and `rpc`'s `onProgress` gives it to the page. A count and not a label,
  because the browser owns the words in both languages. Zero is written before the work starts and that
  is load-bearing: it is the only thing separating "queued, nobody is running this" from "a worker has
  it". Do not add an ignored `progress` argument to an operation that has no milestones — that is a claim
  it can say where it is. Clear the count on `fail` and `reap_stale`; a retry starts over, and 3 of 5
  would describe work the new attempt has not done. Report a stage when its call **stops running**, not
  when it succeeds — a failed Overpass block has still been passed, and `incomplete_blocks` names it.
- **A skeleton is a promise that something is being fetched.** Two placeholder cards sat under the
  discovery stage list from the moment the button was pressed, while the list above them said the search
  had not finished — there is no catalogue to draw a card from until `discover_places` returns. Show a
  skeleton for the request that is actually in flight, not for the wait in general.
- **"No remaining capacity" is a claim that a longer trip would help, so only make it when that is
  true.** `_skip_reason` answered `NO_TIME_CAPACITY` for anything unplaced that was not in `skipped`, and
  `_insertion_search` only offers the skip branch to candidates below `must_do` — so a must-do place that
  could not be placed **for any reason at all** was reported as the trip being short of time, and
  `/optimize` offered "add N days and rebuild once". Measured on a place whose own visit exceeds a
  09:00–21:00 window: the same refusal and the same button at 3, 4, 6, 9 and 14 days.
  `_fits_an_empty_day` is the fix, and it asks *"would another day help?"* honestly — a new day is at
  best another empty day, so if no empty day can hold the place, no added day ever will. It probes
  `_build_schedules` with the one candidate rather than enumerating the ways a place can be unplaceable,
  because that list is a second implementation of `_build_day` that would drift from the first. The
  distinct reason is `NO_DAY_LONG_ENOUGH`, and the screen recommends **removing** the place on it. Keep
  both sides tested: `NO_TIME_CAPACITY` must still appear where days genuinely help, or the offer
  disappears from the case it exists for.
- **An offer that did not work is not offered twice.** Even a true `NO_TIME_CAPACITY` can fail in
  practice — the added days go on the end, and hours, routes or locks can leave the place unplaced
  anyway — so `shared/dayExtension` records, per trip, which places days were already added for, and
  `planDecisions` moves a place that is *still* short of capacity into the drop recommendation. That
  memory is the only thing that knows better than the optimizer here: the draft cannot know what was
  tried. The two wordings are deliberately different — `unfit_impossible` states what is proved, and
  `unfit_days_did_not_help` states only what happened.
- **Every decision a draft is waiting for is applied in one pass, then built once.** Batching the
  comfort figures alone was too narrow: the other conditions each kept their own control and their own
  rebuild, so the owner walked the refusals in series — reported as "it went through like build them
  again → accept the criteria → add the day → add the day". Every one of them is derivable from the first
  draft. `shared/planDecisions.ts` is the single derivation —
  `{unfit, selectedComfort, needsRoutes, needsDays, extraDays, outstanding}` — and
  `OptimizePage.resolveAllAndRebuild` applies `outstanding` in order before calling
  `autoResolveAndGenerate` once. It was previously derived in three places at three depths of the tree,
  which is how a button and the sentence beside it come to disagree. Order matters: the two acceptances
  are per-trip writes, so the **date write goes last** — it moves the setup hash, and discovery stores
  the hash it ran against, so the catalogue must be re-keyed with `force_refresh: false` before anything
  will build.
- **Any rebuild that writes setup must re-run `discover_places` first.** Discovery stores the setup hash
  it ran against, so moving a date stales the found places and the rebuild refuses `discovery_stale`
  before doing any work — which is what "Add a day and rebuild" did. It is free: the provider cache is
  keyed on the destination alone, so the run rebuilds from disk with no network call. `StayPlanner` has
  done this since 2026-08-08; `resolveAllAndRebuild` is the second site and there will be a third.
- **Removing a place needs the solve, not the evidence preamble.** `cutUnfitAndRebuild` called
  `autoResolveAndGenerate`, which re-runs the timezone lookup, the assumed terminal, the default opening
  windows and `collectRouteEvidence` — and that last loops queued route passes until coverage, which on a
  real trip is minutes. Dropping a place cannot invalidate any of it: the timezone and terminal belong to
  the destination, the windows to the dates, and a route snapshot to a *pair*, so every remaining pair is
  measured exactly as it was. Both drop paths go straight to `generate_plan_preview`. The date-changing
  path still needs the preamble, because a new date is a new window and moving the setup hash re-keys
  discovery.
- **Anything a preview's digest depends on must be settled *before* the freeze, not by a client.**
  `activate_plan_preview` re-derives `_optimizer_input` and refuses `preview_stale` when the digest
  moved, which is right — but `resolve_default_terminal` was called only by the browser, from three
  separate `/optimize` mutations, one of them swallowing its failure with `.catch(() => null)`. So a
  build could freeze `trip.terminal: None`, a later visit could resolve the airport, and activation then
  refused with `changed=['trip']` for a change the owner never made. `generate_plan_preview` resolves it
  itself now, so the freeze and the resolve are one operation. Do not "fix" a future instance of this by
  adding the field to `_VOLATILE_KEYS`: the terminal puts real arrival and departure rows on the plan, so
  a genuine change to it *must* still invalidate a preview. Note the shape too — `_optimizer_input`
  **omits** `terminal` rather than writing `None`, so absent is what both sides see and the digest stays
  consistent. The tests that could not catch this are worth knowing: `test_preview_staleness`'s originals
  are unit tests of `_plan_digest` on synthetic dicts, and the one end-to-end activation test patches
  `_optimizer_input` to return the same snapshot twice; its `ProvisionalActivationTest` builds and
  activates for real.
- **A query derived from the plan must be invalidated wherever the plan is.** `comfort_tradeoffs` is
  computed from the stored variant, and only `acceptAll` refreshed it — every build path invalidated
  `plan_preview` and left the report holding whatever it said *before* a plan existed, which is "nothing
  exceeds". Two things then vanish together: `ComfortTradeoffs` filters to zero rules and renders
  nothing, and `overBudget` is empty so the accept control never appears. The screen becomes a refusal
  naming a comfort budget, a panel that has disappeared, and no button — reported as "I don't know what
  to do next, cause it no button anywhere". `invalidatePlan()` invalidates the pair together so a new
  build path cannot refresh one and forget the other. **Grep for `plan_preview` before adding a build
  path**, and treat a control that is missing rather than disabled as a data-staleness question first.
- **A message and the control that resolves it must render on one condition.** The comfort note needed
  `comfortOnly` (from the stored variant) and its button additionally needed `overBudget` (from a live
  query) — two sources that diverge, so the note could appear alone. Gate them together, and where there
  is genuinely nothing to agree to, offer the rebuild that clears a variant lagging behind an agreement.
- **The comfort report must be asked about the variant on screen.** `variantId` is null until the owner
  picks a plan option and the screen falls back to `variants[0]`, so `comfort_tradeoffs` was asked with
  `variant_id: null` — which the server answers from the **active plan**. `comfortOnly` (the drawn
  variant's own `UNAPPROVED_` violations) then said a comfort budget was the only problem while
  `overBudget` (the report) had nothing to accept, and the screen fell
  through to a bare "Build them again" whose only effect was that the second pass happened to line the
  two up. `shownVariantId` is the fix and **both** the page and `ComfortTradeoffs` take it: they
  previously shared a query key only by both omitting the variant, so they agreed by being wrong
  together. While the report is loading the screen waits; it does not offer a rebuild.
- **Comfort consent belongs to the preview being judged, not an older active plan.**
  `comfort_tradeoffs(trip_id, variant_id)` prefers the matching preview variant and falls back to the
  active plan only when there is no preview. Existing consent is covered only while its accepted
  measurement still reaches the rebuilt variant. When several rules exceed their caps, the screen renders
  checked boxes and submits the selected rules before one rebuild; making the owner rebuild once per rule
  recreates the original bug.
- **The draft timeline is one collapsible group per day, and the mobile grid is keyed on column
  position.** It was a flat table of every item on every day; grouping is what a reader scans by, so
  `/optimize` draws a `<details>` per day whose summary carries the date, the number of places and the
  hours the day runs — collapsed, so that line has to be worth reading on its own. `<details>` rather
  than state: the platform owns the toggle, the keyboard and the open/closed semantics. **The date column
  is gone**, because the summary carries it, and the phone rules under `@media (max-width: 860px)`
  address cells by `nth-child` — so every one of them shifted down by one. A stale mapping there does not
  fail a test; it quietly puts the times where the chip belongs. Check a rendered phone view after
  changing that table's columns. "What happened to each place you kept" was removed in the same pass: a
  place that fits is on the timeline and a place that does not is in `optimize-unfit` with the way out
  beside it, so the table was the third place the same facts appeared and the only one with nothing to
  press. `reason` and `consequence` stay on the wire — `/itinerary` still lists the unscheduled ones.
- **A day with no places is explained, not suppressed — and the prep evening is not one.** Reported as
  "2 duplicate day plans, day 7 and day 8". They were not duplicates and the plan was not wrong: the
  owner's Porto trip chose 22 places, **all 22 were scheduled**, and the trip ran two days longer than
  they fill. `include_operational_timeline` still emits breakfast, free time, lunch, free time and dinner
  for such a day, so two consecutive days rendered the same rows with no stops between them and read as a
  copy. The rows are right and stay, so what was missing is `day_has_no_places` saying why the day looks
  like that. Keyed on the day having no `visit` item, and **excluding the prep evening** via the same
  `prepFirst && dayIndex === 0` test the label uses: that block never carries places by design, is named
  rather than numbered, and telling the owner their places fit elsewhere would describe it wrongly.
  Diagnose a "duplicate day" report by counting chosen against scheduled before looking at the optimizer.
- **A label is a promise, and "Build the plan" on `/places` went to "Where to stay".** The destination is
  right — the journey is places → stay → build and skipping `/stay` skips a required stage — but the
  button named the stage it *unlocks* rather than the one it opens, and arriving at a form where nothing
  builds was reported as a "dead air screen". It reads `stage_stay` now.
- **Extending a page needs the updater form.** `dealMore` read `setShown(LANE_PAGE)` — assigning the
  value it already held — so "Show 20 more from here" recomputed an identical window and the deck did not
  move. A pager that appears to do nothing is almost always an assignment where an increment belongs; the
  catalogue's own pager in the same file has always been `shown => shown + CATALOG_PAGE`.
- **The itinerary dashboard is another view of the active export snapshot, not another source of trip
  state.** It may coordinate day, clock, map pins, timeline, search and photo dialog, but readiness
  remains writable only on `/readiness`, planned money on `/costs`, and actual bills on `/split`. A wide
  screen shows map and timeline together; a phone switches between them. Do not duplicate those
  authoritative boards into it.
- **Plan-cost tiers are editable seeds, not forecasts.** `/costs` offers Budget, Value, Standard, Premium
  and Luxury in THB, but selecting one writes nothing; only the explicit Save creates or updates estimate
  rows. Accommodation is per room for two people, the other units are per traveller, nights come from
  setup's travel dates rather than prep days, and a zero-count category is omitted. Keep
  `related_item_id=plan-estimate:<category>` as the row identity so changing language or itinerary counts
  updates one row rather than creating another; the localized label is only the backward-compatible
  fallback.
- **A field added to the setup draft must also be added to `StayPlanner.wholeDraftWithDates`.**
  `save_setup` defaults every field it is not sent, so that function rebuilds the whole payload by hand —
  and a field missing from its list is silently reset the moment the owner picks dates from the stay
  planner. Its own docstring says so; `active_start` / `active_end` were nearly the first casualty.
- **The day's planning window is the owner's answer, not a literal.** `_optimizer_input` hardcoded
  `08:00`–`22:00` for every trip on earth, which is the same invention `WF-046` refused for opening
  hours. Setup asks; `setup.DEFAULT_ACTIVE_START` / `DEFAULT_ACTIVE_END` hold the old pair for a draft
  saved before the field existed, which is what keeps the 27 regressions byte-identical. Arrival and
  departure still tighten their own day — a flight is a fact, active hours are a preference.
- **Before penalising an `avoid` chip in `ranking.py`, check the vocabulary.** None of the five is a word
  the place vocabulary uses (`AVOID_TAGS ∩ candidate tags = ∅`), so a deduction keyed on candidate tags
  is dead code that looks like a feature. They reach the engine as optimizer thresholds;
  `tests/test_avoid_tags_reach_the_planner.py` and `tests/test_ranking.py` pin both halves.

**Places, photographs and the deck**

- **Never print a placeholder as if it were a finding.** Four of the swipe card's fact rows originally
  could not vary: `ranking.py` fixes `feasibility.state` before the optimizer runs, formerly fixed
  `reward_effort = 10.0` against a weight of 20, seeds every card's `cons` with three pipeline-state
  codes, and cost/reservation had no data path at all. `/places` showed it worst — its caution column was
  `cons.slice(0, 2)`, so every place in the catalogue carried the same two strings. A row with one
  possible value cannot separate this place from the next, and it teaches the eye past the rows that can.
  `reward_vs_effort` now varies from category experience per estimated visit minute, is labelled `Value
  for time`, and declares `effort_state: visit_time_estimated`; walking, transfers, cost and fatigue
  remain optimizer evidence. `shared/cards.ts` holds the guards; `WF-005` asks for these rows, so they
  are kept where they can answer and dropped where they cannot.
- **A control in the deck acts on the card in the deck, never on `selectedId`.** The deck deals from a
  lane and the list has its own selection; they are usually different places. `saveChoice` carries the
  comment saying so and `onWantSummary` obeys it, but `onWantPhotos` was wired as
  `() => enrich.mutate()` — dropping the `place_id` the deck had passed — so **the paid photograph was
  bought for whichever place the list was on**, stored against that one, and the tapped card never
  changed. Any new `on*` prop on `PlaceDeck` takes a `placeId` and the handler uses it.
- **Nothing inside a swipe target may take a pointer.** A place with no free photograph used to show a
  map on its deck card: an interactive surface with `touch-action: none` and pointer capture, sitting
  inside a card whose whole job is to be swiped. Pinching the card fought the map under it. It is a
  `tagIcon` glyph and a sentence now — and it was a second copy of the detail panel's map anyway.
- **`PHOTO_THIN_AT` is "one or none", written once in `shared/photos.ts`.** The detail panel's
  `thinlyPictured` always meant one; the deck offered its buy button only at zero, because the control
  lived inside the branch that draws a map where a photograph should be. A single Commons shot of the car
  park next door is as short of a picture of the place as nothing at all. Two literals for one threshold
  is how they drifted.
- **A swipe card is shown only when its first photograph has painted, and no deadline releases it
  early.** The swipe decision is made on the picture, so a card whose frame still says `Loading` is a
  decision offered on half the evidence. A bound was tried — four rotations of the loading line — and
  measured working on the deployment, and the owner rejected it the next morning for doing exactly what
  it was built to do. **A bound is not a fix for slowness; it is a decision about what to show while
  slow**, and here the honest answer is "nothing yet". Answer a slow card by making it not slow: the deck
  warms the whole gallery of the card in front plus the lead image of the next `WARM_AHEAD` (4), and
  `PlacesPage` already has their URLs because it fetches summaries ten ahead. Lead images only —
  six-deep galleries for four upcoming cards is the burst Wikimedia answers 429 to. A broken image still
  releases the card, through `onError`.
- **The warming must not race the photograph the card is gated on.** Both go to `commons.wikimedia.org`,
  so the whole gallery plus `WARM_AHEAD` lead images are multiplexed down **one** HTTP/2 connection
  alongside the single download that decides whether the card may be shown — a lead photograph is
  ~344 kB, so that is ~3 MB of speculative bytes against the one the owner is waiting on.
  `shared/photos.ts`'s `warmTargets` returns nothing while `cardPending`, and everything once the card is
  up. Nothing is given up: a card is read for seconds, far longer than the warm run needs.
  `fetchPriority="high"` is a hint about ordering, not a promise about bandwidth — not *starting* the
  speculative work is the part this app owns. It is a pure function in `shared/` because `PlaceDeck` may
  not export a non-component (`react-refresh/only-export-components`) and the node test environment runs
  no effects, so the rule is testable only if it lives outside the component.
- **`index.html` preconnects to both Wikimedia origins, and the redirect is why.** A photo URL is
  `commons.wikimedia.org/wiki/Special:FilePath/...`, which 302s to `upload.wikimedia.org` — two origins,
  each wanting DNS, TCP and TLS before a byte arrives. Measured cold: 234 ms to finish the commons
  handshake and **1.1 s to first byte** across the chain. The redirect cannot be skipped: a direct
  `upload.wikimedia.org/thumb/` URL answers only for widths Wikimedia has already materialised and
  **400s** for the rest — and note that `?width=640` is served as the **960px** bucket at ~344 kB, so the
  width this app asks for is not the width it gets.
- **`/itinerary` shows the same photograph the swipe card showed, from the free store only.** `DayStops`
  built its own URL from `osmPhotoUrl(item.photo_reference)` — the OpenStreetMap tag alone, the narrowest
  of the three sources `galleryFor` assembles — so a place pictured from Wikidata or Commons had a
  picture on `/places` and none here. `ItineraryPage` reads `list_place_summaries` once per trip
  (`staleTime: Infinity`) and passes a `photoOf` callback, the same shape as `nameOf` and `coordsOf`, so
  `DayStops` stays presentational. **The paid overlay is deliberately unreachable from this screen**:
  `enrich_place_card` is session state in `PlacesPage`, never persisted, so there is nothing here to read
  and nothing to spend. Two consequences: a stop can only show what the free store already holds, and the
  store only holds what something fetched — a place chosen from the list rather than dealt by the deck may
  have no summary at all. And **a geosearch photograph gets no row thumbnail**: the row is always on
  screen and has no space for a caption, so an undisclosed picture of somewhere *near* the stop would be
  exactly the quiet claim `photos_are_nearby` exists to prevent. Those still appear full size inside the
  expanded detail, with the sentence.
- **The deck's buy button has three separate withdrawals, and they sit at different layers.** It renders
  only when `paidPhotoUsd != null` **and** the card is thinly pictured **and** the place has no session
  insight **and** this card's ask has not failed. The first is the cap: `paidPhotoUsd` comes from a
  `paid_check` query, so when the month is spent the control is never rendered at all — which means a
  `paid_cap_reached` refusal can never reach the card's own error surface, and the whole cap class is
  handled a layer earlier than the failed-ask handling. The third is a purchase already made; the fourth
  is `photoError`, session-scoped because a busy provider is not a finding about the place, unlike the
  stored `provider_no_match`.
- **Do not turn an outage into a finding.** A failed paid photo ask has three causes and they are three
  different claims: `place_not_in_provider` means Google has none either, `provider_unavailable` means
  Google was never reached, and anything else is neither. One blanket "no photograph could be found"
  asserts a fact about the place out of a network error. `photo_ask_none` / `photo_ask_unavailable` /
  `photo_ask_failed` keep them apart, and the pre-press line stays `photo_none_kind`, which is about
  *free* sources only.
- **A failed paid photo ask is hard to summon, and the rejection rule is where to aim.**
  `providers._best_nearby_match` demands distance ≤1500 m, name similarity ≥0.46 against the OSM name *or
  any of its `names` values*, and a category-to-`primaryType` match; a miss raises `ProviderUnavailable`,
  and an empty result raises `ProviderNoMatch`, which re-raises after recording the refusal. Both reach
  the browser as errors. Two live attempts on the deployment — an `artwork` with a Japanese-only name and
  a statue whose OSM name is misspelled — **both matched Google anyway**, at US$0.075 each, and this
  database holds **zero** `provider_no_match` rows across every ask ever made. Treat this path as
  test-verified: the money buys a coin-flip, not a confirmation.
- **Thin photo coverage is usually the data, not a defect.** Measured 2026-08-28: Zurich 75% of summaries
  carry an image, Interlaken 43% — and 14 of Interlaken's 16 imageless places **have no Wikidata entry at
  all**, so there is nothing to fetch. Check `cache_version` before suspecting staleness, and do not
  loosen `providers.photo_depicts_place` to raise the number: that filter is why a photograph of a bus
  stopped being offered as a photograph of a hill.
- **A preset's `name` becomes the trip's name, so it carries no day count.** It used to — "Tokyo 6-Day
  City & Culture" — and `applyPreset` writes it straight into the form, where `exporters.py` reads it back
  as the workbook's title. Nothing recomputes it when the owner picks their real dates, so a trip running
  25 Nov to 2 Dec printed **"Tokyo 6-Day"** over a workbook describing eight days. The count is a
  suggestion about the preset, not a fact about the trip, so it stays in the card's `days` badge and
  `tagKey` heading, neither of which is saved. A name asserting a duration the trip does not have is the
  same defect as printing a placeholder as a finding.
- **A touch gesture cannot be verified from here — put its arithmetic in a module.** A dispatched
  `PointerEvent` does not drive this map, checked against the deployment rather than assumed; raw input
  injection is `not_supported`. So `shared/pinch.ts` holds the maths and is tested, the wheel path is the
  regression check that `setView` still works, and the gesture itself needs a finger on a real phone. Do
  not claim a gesture is verified because a synthetic event returned without error.
- **`document.querySelector(".places-map-svg")` on `/places` finds the *hidden* one.** The only map on
  that screen lives in the shortlist drawer, so while it is closed the element is `0x0` — measuring
  against it sends the viewBox to `-Infinity` and reads as a broken map. Open the drawer, or pick the
  element with a non-zero box.

**What counts as evidence**

- **Press buttons; do not drive the API.** A hand-rolled call sequence left every variant `unavailable`
  while the real button worked — `autoResolveAndGenerate` orchestrates four steps as one. An audit that
  drives the API will declare the app broken and be wrong.
- **Reproduce a reported symptom before deciding which bug it is.** "A dead air screen when I click build
  the plan" was read from the source as `StayPlanner` returning `null` on an empty pace list — a real
  blank page, found and fixed, and *not the report*. Driving the app at 390px answered it in one click:
  the button said "Build the plan" and opened a populated form where nothing builds. Two real bugs, one
  reported, and reading found the wrong one first. Source reading generates candidates; only the running
  app says which candidate the owner met.
- **A screenshot is evidence about what someone sees; a measurement is evidence about what was
  measured.** When they disagree, the screenshot is describing the product.
- **Measure the phone in a real browser before believing the phone baselines.** Headless Chrome clamps
  its window to a 500px minimum, so the capture set's phone viewport is not a phone.
  `cmux browser <surface> viewport 390 844` plus `eval` is the whole harness. A real 390px run
  also confirmed the 861/860 boundary is exact, that no route overflows horizontally, and that everything
  past the right edge on `/costs` and `/itinerary` is inside a legitimate `overflow-x: auto` scroller
  (`.money-table`, `.day-tabs`) or an SVG map viewBox.
- **"Verified" means the thing that broke was exercised.** Two claims in one month were reported as
  verified and were not: an advisory-lock probe that checked the function overload with a stand-in string
  while the real key carried a NUL byte Postgres refuses, and a route-coverage story asserted from the
  code that the stored rows then contradicted. Both were live checks of the wrong half. Name what was
  exercised and what was not.
- **A measurement that a mechanism works is not evidence that the behaviour is wanted.** The card-wait
  bound was measured firing correctly on the deployment — three waits, two released at the ceiling — and
  reported as verified. It was: the mechanism worked. The owner rejected the behaviour the next morning.
  Separate the two claims when reporting, because only the second is what was asked for.
- **Grep the landing for `ILP`, `Branch`, `Optimality` and `Solve Time` before believing it describes
  this optimizer.** `optimizer.py` is a greedy baseline plus an insertion search. Invented solver claims
  have been removed twice and returned twice; they read like competence, which is what makes them hard to
  catch.

**Gates and checks**

- **A stage that fails before it runs is an environment question, not a code one.** `check.py` drops a
  `NODE_OPTIONS` preload whose file has been deleted: agent tooling injects
  `--require=<temp>/restore-node-options.cjs`, macOS empties its temp directory after a few days, and
  from then on every `node` and `npm` invocation aborts with `Cannot find module` **before running
  anything** — which the gate reports as `FAILED: Web typecheck` on a tree where nothing is wrong. Only
  *unresolvable* `--require`/`-r` entries are removed, only from this process; `--max-old-space-size` in
  the same variable is real and is kept.
- **One `check.py` at a time — it takes `.check.lock` and refuses a second.** The stages are not
  independent of the working tree: the baseline stage compares `screen-current`, which is shared state on
  disk, so two interleaved runs produced `approved: 2 · compared: 1` and a stage that failed exactly like
  real drift on unchanged code. The tool that runs these commands issues parallel Bash calls in one
  shell, so this was reachable by accident. It refuses rather than queues, because a second run is nearly
  always a mistake and a silent ninety-second wait looks like a hang. Remove the lock by hand after a
  crash.
- **A test that exercises a gate's failure path must capture its output.** The
  `FAILED: 1 screen(s) drifted` line inside the *unit-test* stage was
  `tests/test_screen_baseline_gate.py` proving the gate fails when it should, and it read as a real
  failure inside a passing suite for long enough to be written into three handoffs as a trap. Assert the
  exit code; let the stage that runs it for real own the prose.

## Architecture

There is one interface, the React webapp, reached two ways: `localserver/` (stdlib
`ThreadingHTTPServer`) locally, and `api/rpc.py` as a Vercel function when hosted. Both share
`static_response` and both dispatch through the same allowlist. The design decisions are locked in
`.wayfinder/tickets/` — the constraints in this section are decisions, not incidental structure.

### Dependency direction is one-way and enforced by review, not by tooling

```
web/ (React)  →  localserver/ | api/rpc.py  →  travel_planner/actions.py
                 (local HTTP)  (Vercel fn)
                                                             │
                                                             ├─ core / optimizer / ranking / setup / discovery
                                                             └─ store.py (SQLite) · providers.py (HTTP)
```

- `core.py`, `optimizer.py`, `ranking.py`, `setup.py`, `discovery.py` are the planning core: pure,
  language-neutral, no UI / SQLite / HTTP / LLM imports. Check the module docstrings — they each state
  this. Adding such an import is the single easiest way to break the design, and honouring it is why
  replacing the whole interface at S6 cost the core nothing.
- `PlannerActions` (`actions.py`) is the only coordinator: it assembles snapshots, calls the core,
  and persists results. It holds no session state and no presentation formatting.
- `PlannerActions.journey()` decides which stages are done and which is next. The webapp renders the
  blocked explanation **in place** through `<StageGate>` rather than redirecting; only `/` redirects, to
  `journey["next"]`, so a returning owner lands on the stage needing attention.
- `travel_planner/destinations.py` (country/city) and `costs.COMMON_CURRENCIES` are picker convenience
  only. Both dropdowns take a typed value, so a destination or currency absent from the table stays
  reachable — the worldwide acceptance check requires it. A city name is the geocoder query, so it is
  never localized; localizing it would let a language switch change which place is searched.
  `destinations.country_for()` resolves a city-only destination's country, falling back to the last
  comma-separated segment — `destination.split(",")[-1]` gave `"Taipei"` as a country for every trip made
  before the picker, which matched no holiday source.

### Everything crossing a boundary is a frozen, hashed snapshot

`core.freeze_snapshot()` canonicalizes a mapping (sorted keys, no NaN, UTF-8) into
`FrozenSnapshot(canonical_json, sha256)`. Every domain record wraps its payload in one, and every
`store.py` read re-verifies the hash before returning. Consequences:

- `freeze_snapshot()` rejects secret-bearing keys (`api_key`, `*_api_key`, `access_token`, passport and
  booking document keys — see `FORBIDDEN_SNAPSHOT_KEYS`) anywhere in the tree. Snapshots are the place
  secrets could leak into SQLite and exports; that guard is why they can't.
- Hashes are the staleness mechanism, not timestamps: discovery stores `setup_sha256`, and ranking or
  optimization refuses to run when it no longer matches the confirmed setup.

Plans are append-only: `plan_versions` and `discovery_runs` carry SQLite triggers that abort UPDATE and
DELETE. Restoring an old plan creates a *new* version pointing at the old snapshot. `active_plans` holds
exactly one version per trip; `optimization_previews` holds at most one replaceable pending preview.
`SCHEMA_VERSION` (`store.py`) is stamped into `PRAGMA user_version`; a newer DB refuses to open.

### Pipeline: setup → discovery → ranking → optimization → activation

Each stage is gated on the previous one having a matching hash (`_current_choice_inputs`).

1. **Setup** — `setup.build_setup_payload()` normalizes owner/member preferences into a draft; nothing
   downstream runs until `confirmed`. Setup and the optimizer use different accommodation vocabularies —
   `unknown`/`not_booked`/`booked` versus the `unbooked` that `optimizer._hotel_recommendation()` and the
   frozen fixtures test for. `_optimizer_input` translates at the boundary; before it did, hotel-area
   recommendations silently never fired for any app-created trip.

2. **Discovery** — `providers.OpenStreetMapProvider` (Nominatim + Overpass, free) →
   `discovery.build_candidate_catalog()`, which normalizes and dedupes into provider-neutral candidates
   with an explicit status (`verified` / `stale` / `unavailable` / `error`). Raw responses live in the
   `provider_cache` table (7-day TTL, keyed by provider + request fingerprint); an expired entry may back
   a visibly `stale` result but never a `verified` one. Inject a fake via
   `PlannerActions(path, place_provider=...)` — that is how every test avoids the network.

   **Discovery is two Overpass requests, not one** — indexed `["wikipedia"]` landmarks, then the balanced
   family baseline — and each is **best-effort**, failing only when both come back empty. As one script
   Tokyo returned nothing at all: the unindexed baseline exceeded `[timeout:90]` at 91 s and 93 s, and
   **Overpass has no partial result**, so it discarded the indexed half that had succeeded. Split, Tokyo
   yields **3082 items**. Three consequences. The baseline gets **`[timeout:60]`, not 90** — a browser
   constraint, since two requests run back to back and `web/src/api/client.ts` aborts an RPC at 120 s.
   There is a **3 s pause between the blocks**, because fired immediately the second came back
   `Provider HTTP 504` on the 2-slot budget — losing the baseline to a rate limit rather than a timeout,
   which hurts a *small* city most. And a catalog missing a block is **`stale`, never `verified`**,
   applied after the cache branches so a partial payload is not laundered into `verified` on the next
   read; `coverage.incomplete_blocks` and `known_gaps` name which half is missing.

   A dense city takes about 34 s of Overpass time, so the query declares `[timeout:90]` and the socket
   allows 105 s; the earlier 25 s budget failed every Taipei attempt. The endpoint grants 2 concurrent
   slots and answers 504 immediately once they are spent, so a burst of retries reads as an outage that
   is really self-inflicted — space them.

   **A 504 is not always a spent slot.** `overpass-api.de` balances across backends and an unhealthy one
   answers 504 in *seconds*: measured on Singapore, both blocks 504 at 9.0 s and 9.5 s with both slots
   free, and the identical query returned 200 a minute later — an empty catalog for a fault that had
   already passed. `_attempt_block` therefore retries **once**, and only when the failure was **fast**
   (`FAST_FAILURE_SECONDS = 20`) and an HTTP 5xx. That distinction is the whole safety of it: a block that
   died at 90 s died of its own declared timeout, and asking again would spend another 90 s to fail
   identically. A `remark` is never retried — that is the query engine reporting its own timeout, not a
   gateway. `DISCOVERY_BUDGET_SECONDS = 100` is a deadline shared across both blocks and their retries,
   which keeps the pair inside `client.ts`'s 120 s abort however the retries fall. Do not raise it without
   moving that abort first. `out center qt` with a 500-record limit truncates in quadtile order, so a big
   city's catalog can miss its landmarks; see the walkthrough notes in
   `artifacts/validation/2026-07-29-slice5-6-evidence-notes.md`.

   **Dedupe on name and place, not on tag.** Requiring an identical `category` as well let one attraction
   through twice whenever OpenStreetMap disagreed with itself about what it is — Singapore's "Jelutong
   Tower" arrived as `viewpoint` and as `landmark`, so the owner was asked about it in one lane having
   already answered in another. An identical normalized name within 150 m is the strong signal; the
   category was the weak one and it was doing the deciding. `PlaceDeck` also filters by name, because
   discovery cannot merge what it cannot tell apart — a zoo signs one exhibit twice, 200 m apart.

   **Changing setup does not cost a re-search.** Adding dates makes the found places stale, and a stale
   trip cannot even record a choice — the server refuses with 409. Nothing needs re-searching:
   `discover_places` keys the provider cache on the **destination alone**, so with a fresh entry it
   rebuilds the run from disk with **no network call** (0.05 s on a 715-place Seoul catalogue), and
   `place_id` is a hash of name, coordinates and category, so every existing choice still points at the
   same place. `StayPlanner` does it automatically after writing dates, and the stale-setup warning on
   `/places` carries a button that does the same. Never `force_refresh` for this: that goes back to
   Overpass and undoes the point.

3. **Ranking** — `ranking.build_ranking()` scores cards on the fixed 30/20/20/10/15/5 weights in
   `FORMULA_WEIGHTS`, with protected exploration slots and per-card explanations. `total_score` remains
   the raw optimizer input; `relative_match_percent` is a catalogue-relative display rank with ties
   sharing a value. Queue spreading uses the exact category when available, falling back to the broad
   family only for legacy cards, so museum/historic alternatives do not form a streak. Deterministic.

   **Divide `group_preference_fit` by category breadth, not by how many styles the owner named**
   (`WF-037`). A
   category with more tags won for free: `peak` carries four tags and `attraction` two, so a nameless hill
   scored 27 of 30 against Taipei 101's 12.8 and Taipei 101 ranked **363rd of 832**. It divides by
   `_breadth(candidate_tags)`, capped at four; `FORMULA_WEIGHTS` is untouched. Do not assume the ranker's
   ordering is tested by the old suite — it asserted only that the score was internally consistent, which
   holds under any weighting, and
   `test_a_landmark_is_not_buried_by_a_richer_tag_vocabulary` is the first test of what it recommends.

   **Category variety reverses the learned bonus.** `ranking._learned_category_weights` only ever argued
   for *more* of what was already chosen: pick three temples and temples rose, so the fourth and fifth led
   every lane and the deck offered "the same thing over and over". It saturates at
   `VARIETY_SATURATION = 3.0` weighted picks — unchanged below that, which is the signal that discovers a
   taste — then each further pick costs `VARIETY_PENALTY = 1.5`, bounded at `VARIETY_FLOOR = -6.0` so a
   category is pushed down the order but never out of reach. Five temple picks measure −3.0 against a
   first museum's +2.0. The same number argues both ways, so it carries two explanations:
   `learned_from_choices` when positive, `category_already_well_covered` when negative, and the latter is
   a `con` as well. Five tests in `tests/test_ranking.py` pin the curve, including that a `not_for_trip`
   neither teaches nor saturates.

4. **Optimization** — `optimizer.optimize_trip()` takes one complete snapshot and returns three variants
   (`best_balance`, `relaxed`, `more_highlights`), each independently rechecked by
   `optimizer.validate_variant()` — never trust solver construction. Same input + same
   `OPTIMIZER_VERSION` must yield the same proposal, asserted via `deterministic_signature`. With no trip
   dates it returns `mode: "stay_recommendation"` instead of a timetable. At the time limit it returns
   only a labelled valid incumbent, never a partial schedule.

5. **Activation** — `activate_plan_preview()` refuses unless the preview's `input_sha256` still matches
   current choices, re-runs `validate_variant()` against the frozen input, and accepts only a ready (or
   explicitly allowed provisional) valid result. It never trusts a stored preview-time
   `validation.valid` flag as write authority. It then writes an immutable plan version and deletes the
   preview; the browser navigates immediately and invalidates queries in the background.

6. **Readiness** — `checklist.propose_items()` generates a city-independent board from setup, choices,
   and verified facts; `diff_proposal()` previews additions, removals, and deadline moves;
   `apply_checklist_proposal()` writes them, dismissing rather than deleting so nothing silently
   disappears. No provider supplies official entry rules, so a generated item stays
   `verification_needed` with no `source_url` until the owner records one — the board names what to
   verify and against which authority, and never asserts a legal conclusion. Requirement level and
   evidence state move independently, and `validate_item()` refuses a verified `required` item with no
   responsible authority type. Board items are the one mutable record type; readiness warnings are
   explicitly non-blocking (`blocks_itinerary` is always False).

7. **Revision** — `revision.py` holds the whole typed operation set. An operation is a *constraint
   change* on the optimizer input, never a schedule instruction, so nothing in it can write an opening
   time, route, fare or closure; the deterministic optimizer rebuilds the plan and `consequences()`
   reports the before/after. `propose_revision` keeps exactly one pending draft and leaves the active
   plan untouched; `apply_revision` refuses unless the rebuilt variant is `ready` and valid, and
   refuses again if the active plan moved behind the preview. Applying writes a new immutable version
   plus an append-only history row; restore creates another version and deletes nothing.

8. **Free-text revision** — `interpret.py` builds the strict structured-output schema *from*
   `revision.OPERATIONS`, so the model can only choose a supported operation and may name only a
   `place_id` it was actually sent. It cannot return an opening time, route, fare or closure because no
   operation carries such a field. `build_payload` sends the plan slice and the request and nothing
   else; `_assert_clean` refuses a payload carrying travellers, documents or credentials. One call per
   request, `store: false`, one retry at most on a transient failure, and every failure names its cause
   (`missing_credentials`, `offline`, `refused`, `invalid_reply`, `rate_limited`, `api_error`) while
   leaving the plan and history untouched. Where the model omits a magnitude the app supplies a
   documented default and shows it as a visible assumption; where the value is the point of the request
   it asks one clarification instead. GenAI is off by default and everything else works without it.

### Whether a place still exists

**The signal is shown, never obeyed.** `WikidataSummaryProvider.CLOSURE_PROPERTIES` is
`("P3999", "P582")` — "date of official closure" and item-level "end time" — read from
claims the `wbgetentities` call already fetches for photographs, so a closure check costs
no request, no key and no second provider. `NHK Studio Park` carries `P582 = 2020` and was
given four and a half hours on a 2026 plan.

**What is absent is the load-bearing part, and both absences were measured over 500
candidate QIDs from a real catalogue.** `P576` (dissolved, abolished, demolished) flagged
four places and three were places anyone would go: `Edo Castle` — whose site is the
Imperial Palace East Gardens — an open museum, and a party headquarters whose QID is the
*party* rather than the building. Historic sites are visited *because* the original
structure is gone. `P5817` "state of use" is worse: its common value is `Q55654238`, which
is literally "in use", and `Tokyo Skytree` carries it, so a presence check would have
dropped the most visited place in the city. `tests.test_closure_signal` asserts both
absences, because the temptation to add them is the hazard.

Because the source is wrong in both directions, **nothing filters on it**. The card states
the record with its caveat, `/itinerary` warns on a scheduled stop — which is the moment
the reported failure was found, by reading the finished plan — and the owner's own answer
is `permanently_closed`, an ordinary rejection reason rather than a new kind of state: a
closed place needs exactly what `not_for_trip` already does.

Coverage is honest and partial: **66% of candidates carry a QID at all**, and
`Yoshimoto ∞ Hall` has one with no closure property, because Wikidata does not record its
March 2025 closure and OpenStreetMap still tags it as a theatre. That case is why the
manual answer exists.

`cache_version` was bumped to `wikidata-summary-v13` so stored summaries are refetched
once; without it a place would keep a silent card for the 60-day TTL.

### What may enter the catalogue, and how far a walk counts

**A bed is not a stop.** `tourism=hotel` reached the catalogue and the optimizer gave it an
82-minute sightseeing slot. Two causes, both fixed. `_category` returned `tags["tourism"]`
unconditionally and *first*, so a place matched for being `historic` was labelled with
whatever `tourism` value it also carried — it now accepts only a value in
`TOURISM_FAMILIES`, the same set `FAMILY_SELECTORS` is built from, so the label names the
tag that actually put the place there. And `_item` drops an element whose only
classification is lodging, keyed on the **tags** rather than on `_category`'s answer,
because a pure hotel now falls through to `landmark` and a label check would miss it. A
palace converted into a hotel keeps `historic` and stays: it is in the catalogue for the
palace.

**`MAX_USABLE_WALK_MINUTES = 60` is a hard ceiling, and `walking_minutes_per_leg` is not.**
That one is a comfort threshold: it caps at 25, `_best_route` treats it as a sort
preference rather than a filter, and the owner may agree to exceed it — which the "make
this plan work" flow encourages. So an accepted tradeoff could bless a walk of any length.
Measured on the live database: **656 stored walking legs, the longest 274 minutes, 41% over
an hour**, and one reached an itinerary as "walk 19,951 metres, 240 minutes". The ceiling is
derived rather than chosen — `plain_walking_minutes_per_day` is at most 60 on the most
permissive pace, so a single leg longer than the most generous *whole-day* budget cannot be
one a plan should use. Filtered in `_routes_between`, the one function every route reader
goes through, so a leg excluded from planning is not still counted as making a pair
reachable. `_accepted_route_estimates` stops fabricating one past the ceiling too: leaving
the pair unrouted means the place is `ROUTE_UNVERIFIED` and recommended for removal, which
is true where a four-hour walk is not. The 27 fixtures peak at 42 minutes and are untouched.

### Transit routing (`WF-038`)

`travel_planner/transit.py` holds `TransitGraph`, the walking constants and **one** Dijkstra;
`gtfs.TransitFeed` builds one from a timetable zip and `transit.graph_from_osm()` from an OpenStreetMap
`route=subway` relation. `providers.GtfsTransitProvider` and `providers.OsmMetroProvider` wrap them, both
`mode: "transit"`, both priced at US$0.00 — priced rather than omitted, because an unpriced operation
raises. `actions.refresh_transit_routes` stores transit legs **beside** the walking ones: the store keys a
snapshot by (origin, destination, **mode**) and the optimizer takes the shortest it holds, so short hops
keep their walk. `PlannerActions._default_transit_provider` prefers a GTFS feed at `TOURIST_GTFS_PATH`
when one exists and falls back to OSM, which is weaker and says so — GTFS edges carry
`basis: "timetable"`, OSM edges `basis: "nominal"` with ride time from distance at 33 km/h and wait from
an assumed 6-minute headway. Taipei's own GTFS is **not sourced**: TDX needs a Taiwan mobile number.

**A transit route is `status: "estimated"`, never `"verified"`, and `optimizer.usable_route_statuses` is
the single source of that rule** (`optimizer._usable_route_statuses` is its snapshot-shaped form). Every
reader goes through one or the other: `actions._optimizer_input`, `optimizer._routes_between`,
`optimizer._best_inbound_route`, `validate_variant` and `_has_incident_usable_route`. **If you add a
third reader, call the shared function.** `_optimizer_input` once held its own inline copy, so widening
`estimated` taught the optimizer and not the layer deciding which stored routes reach the snapshot — a
`ready_to_schedule` trip held **2 transit legs, 0 reaching the snapshot**, and every test that proved the
widening fed the optimizer a snapshot directly, bypassing the layer that was dropping them.

**`estimated` is admitted on every trip, not only an Explore preview.** The earlier rule grouped it with
`accepted_estimate` and withheld both from a `ready_to_schedule` trip, reasoning that a scheduled plan
must not rest on a guess. That is right about `accepted_estimate` and wrong about a timetable, and the
consequence was that **every scheduled plan discarded every metro leg it had already fetched and stored**
and laid the city out on foot and by car — reported as "why is the walking not considering the metro line
too", which is exactly what it was doing. `estimated` is emitted by precisely two things,
`GtfsTransitProvider` and `OsmMetroProvider`, so admitting it is a narrow rule and not a relaxation.
Measured on a cross-city pair holding both: `walk 55` before, `transit 15` after.

`accepted_estimate` stays Explore-only — a crow-flies line inflated by `ACCEPTED_ROUTE_DETOUR` is
*fabricated*, not merely unrouted. Nothing about a missing route softened: `_missing_route_edges` and
`ROUTE_UNVERIFIED` are untouched, so admitting a real journey never became inventing one.

**`walking_minutes` excludes the ride**, which is the whole point: `maximum_walking_minutes_per_leg`
measures it, so a 43-minute ride reached by a 2-minute walk passes a 25-minute cap no walk of that
distance could. And **`refresh_routes` sorts pairs nearest-first**, because the 60-per-run cap bites long
before 41 places' 1640 pairs and a missing route falls back to a pessimistic estimate — sorting by
`place_id` spent 340 free calls on pairs the plan never used and produced phantom 68-minute walks.

### Opening hours and the day's window

**Opening hours are per-day (`WF-041`).** `opening.common_interval` takes the overlap across the days a
place is **open** rather than refusing the moment one trip date is shut, and returns `open_dates`;
`_optimizer_input` puts those in the fact's `applies_to_dates`; `optimizer._open_on()` is consulted by
`_earliest_visit_start` and `validate_variant`. A fact without `applies_to_dates` applies everywhere, so
frozen fixtures are untouched. Before this a venue closed on one trip day was unschedulable on **every**
day — five of thirteen pilot landmarks were lost that way.

**A flight day's window holds its own logistics (`WF-042`).** The last day owes a fixed suffix —
`optimizer.DEPARTURE_LOGISTICS`, 45 + 45 + 90 = **180 minutes** of checkout, transfer and airport — so
`_optimizer_input` opens that day at `min("08:00", departure_time − DEPARTURE_LOGISTICS_MINUTES)`. That
constant is exported for exactly this reason and is the **one** source both sites read. Before it, a
morning flight made the departure day infeasible, and because `_greedy_baseline` accepts a placement only
when the **whole trip** builds clean, one unusable day emptied the entire plan — 13 visits to 0, every
landmark blamed on `PLAIN_WALK_THRESHOLD`. Three things follow. `_build_day` now refuses only when
`sequence or items`, so an empty day cannot veto the others. **Do not fix a window problem in the
builder** — moving `current` without moving `usable_windows` scheduled all 13 visits and then failed
`validate_variant` with `OUTSIDE_USABLE_WINDOW`, because the validator judges every item against the
snapshot's window and is meant to. And `_skip_reason` is not a measurement: it returns
`PLAIN_WALK_THRESHOLD` whenever a place was skipped and that threshold merely exists, so read
`_build_schedules`' own `hard_errors` when diagnosing.

**`include_operational_timeline` is `True` for every trip `actions.py` builds and absent from all 27
fixtures**, so arrival transfers, check-in, meals and the airport run are exercised only by a live trip.

**An omitted terminal becomes a visible airport assumption, not a booked fact.**
`resolve_default_terminal()` asks the existing free OpenStreetMap geocoder for an airport near the
destination, rejects a result more than 200 km from the discovered centre, and caches a successful answer
for 365 days. The value stays `status: "assumed"`; arrival and departure rows carry its coordinates, and
`/itinerary` draws one `A` pin with `Recheck`. The airport is excluded from the drawn visit route because
no verified airport-to-hotel leg was collected. No plausible lookup means no terminal, not an invented pin.

**A model may supply the assumed opening window (`WF-046`) — and nothing more.** The app always guessed
when a place had no verified hours: `_optimizer_input` emitted a flat **09:00–21:00** for every place on
earth. So the question was never evidence versus a guess, it was *which* guess, and the constant is the
worse one. Benchmarked against verified ground truth for all 13 places: the model's window ends after real
closing 5 times by **30–60 min**, the constant 6 times by **180–270 min**.

Five rules not to relax. **The status stays `assumed`** whichever guess fills it — only `source` differs
(`model_recalled_window:<model>`), so nothing is upgraded. **A place with verified hours is never asked
about.** **A window spanning 20 hours or more is discarded** (`DEGENERATE_SPAN_MINUTES`): the model
answered `00:00–23:59` for one venue, and a non-answer permitting *more* than the constant inverts the
reason for asking — the bar sits above sixteen hours because temples really do open 06:00–22:00.
**`closed_weekdays` is not requested at all**: the same benchmark got 7 closure claims of which **2 were
invented**, and a false closure silently drops a place — do not add the field back without re-running the
benchmark. And **`_optimizer_input` never fetches**; it runs on every read, so the window is read from
storage or the constant stands. Recall cannot reach a *holiday* closure at all — that is `WF-044`.

**Assumed windows are batched and the cost trade is reported, not taken (`WF-047`).**
`google_places:search_text` is **US$0.025 a place** and is the only paid step that scales with trip size —
40 places is US$1.00 against a US$10 cap. There is **no cheaper verified path**: Text Search takes one
query per place and cannot be batched, and the cheaper `places/{id}` Details endpoint needs a Google place
id the catalogue does not hold. So US$0.025 is the floor for evidence.
`OpenAIOpeningWindowProvider.windows()` batches the *assumption* instead — one request for up to
`BATCH_SIZE = 20` places, matched back by an **echoed integer index**, never by name, and charged to the
ledger **once per request**. Batching measured **more** accurate, which was not expected: 8 of 11 exact on
both ends against 6 of 12.

**Do not add a cost threshold that switches automatically.** Verified and assumed are different kinds, not
different prices: an assumed fact is read only under `allow_provisional_assumptions`, so on a
`ready_to_schedule` trip a cost-triggered switch spends money on a fact the optimizer ignores.
`actions.opening_evidence_options` prices both paths and carries the cheap one's measured error rate
*beside* its price, and reports `assumed_is_usable: false` where the trip would not read it.

**A venue's own page is read for dated closures (`WF-044`) — and it is never a fact.** An opening fact is
a **weekly pattern**, so nothing stored can say "closed 1 January". `providers.VenueNoticeProvider`
fetches the landing page and quotes any dated visitor closure; `actions.scan_venue_notices` stores it as
`place_evidence` of kind `venue_notice`. **`_optimizer_input` does not read that kind** — there is no code
path from a notice to the optimizer, so a false one cannot delete a landmark. That is the bar the ticket
set and it is met structurally, because `WF-046` measured a model inventing 2 of 7 closures. Two guards,
both load-bearing: **the quote must appear verbatim on the fetched page** (`quotes_the_page` forgives only
whitespace, never case or punctuation, since a paraphrase is exactly what cannot be checked against the
source), and **no page, no answer** — a failed fetch raises rather than letting the model recall. This
reads the landing page only; sites whose hours sit two hops into a government CMS are unchanged.

**An activated plan is checked against today's evidence (`WF-045`).** Every other gate guards the
**forward** direction — activation refuses on a stale preview, discovery and ranking on a stale setup
hash — so nothing noticed when evidence *improved* underneath a live plan. One paid opening-hours lookup
left a visit at 17:17–19:32 against real hours ending 17:30 while the stored variant still said
`validation.valid: true`, because that flag was computed at build time and never recomputed.
`actions.active_plan_drift` compares the activated version's own stored `optimizer_input` hash against the
current one, and **re-runs `validate_variant` only when it moved** — the hash says *whether*, the
validator says *what*, and gating the second on the first is what keeps this off the churn path. It
**reports and never repairs**: `plan_versions` is append-only and the owner may have printed the
itinerary, so regenerating is an offer on `/itinerary`, not a side effect of reading. `claimed_valid` and
`still_valid` are both returned so they can be seen to disagree.

### The optimizer's budget and objective

**Every variant gets its own time budget (`WF-043`).** `optimize_trip` used to compute **one** absolute
deadline and hand it to all three variants, so it was consumed in order and whichever ran last inherited
the remainder — measured at 20.7s + 10.4s of a 30s budget, leaving `more_highlights` already past it. It
returned in 0.04s having placed **nothing**, was labelled `ready` and `valid` because an empty schedule
violates nothing, and reported `objective_improved_or_equal_to_greedy: false` beside a `greedy_baseline`
holding all 13 visits. The deadline is now per variant, so worst case is
`len(VARIANT_CONFIGS) × time_limit_seconds` and **a full proposal takes ~52s, not ~31s** — that is the
third variant doing its 21s of real work.

`_greedy_sequences` is split out of `_greedy_baseline` and `_insertion_search` **falls back to it** when
the deadline fires: greedy sweeps every candidate and has no time limit, so it is a floor the search can
always afford, and returning worse than a schedule already in hand is never right. Two things not to
misread: `deterministic_signature` hashes the **input**, so it cannot detect a load-dependent output; and
an expired budget legitimately yields 0 visits where greedy's only schedule carries a comfort violation,
because `comfort_violations` outranks `experience_value` in the objective tuple.

**The objective spreads places across the days, weighed against the travel it costs.**
`_search_objective` is `(hard_errors, missing_route_edges, must_missing, soft, -experience,
travel_minutes + EMPTY_DAY_MINUTES * empty_days, -lower, len(skipped), ids)`. The sixth term is travel and
spread **together**, and that is a correction to how it first shipped. Nothing had preferred using a day
and `travel_minutes` actively preferred not to, since
every day a plan opens costs another base-to-place-and-back journey, so the cheapest arrangement was to
pile everything onto as few days as possible. Measured on twelve ordinary places over seven ordinary days
with nothing in the way, all three variants scheduled all twelve and still left most of the trip blank:
`[0,0,0,0,0,6,6]`, `[0,0,0,0,4,4,4]`, `[0,0,0,0,0,3,9]` — reported as "the output trip is so weird, it has
a lot of days that have only free times". **No rule was broken by any of those and the reconciliation was
empty**, which is why nothing in the suite could have caught it.

**It first shipped as the sum of the squares of each day's visit count, placed before `travel_minutes`,
and that was wrong.** A lexicographic term wins by any margin, so any spread improvement outranked any
travel saving. Measured on three tight neighbourhoods 75 minutes apart, nine places over four days:
travel went from **120 to 260 minutes** and two of the four days crossed the city — reported as "bad
clustering, crosses Tokyo unnecessarily" and "zigzag".

An empty day is worth avoiding but not at any price, which no ordering of separate terms can express, so
the two share one term at `EMPTY_DAY_MINUTES = 60`. The metric is the **count of empty days**, not
squares: the report was days with *nothing* on them, and squares answered a question nobody asked while
forcing `[2,2,2,3]` over `[0,3,3,3]` even when the latter keeps each day in one neighbourhood. The weight
was measured, not chosen — below about 20 the empty day never earns its detour, and from 20 up the outcome
stops changing at all (identical at 20, 30, 40, 60, 90, 180), so 60 sits well inside the flat region.
After the fix: travel 195, one mixed day, no empty days.

Two failed attempts are worth not repeating. Counting empty days while still placing the term *before*
travel helped but not enough. And applying the penalty only when choosing between **finished** plans did
nothing at all: a beam ranked purely on travel never keeps a spread state, so there is nothing spread left
at the end to prefer — the term has to be inside the search.

What still outranks it is the design: `-experience` above, so a smoother trip can never cost a chosen
place, and `soft` above, so it cannot buy spread by breaking a comfort threshold. A one-day trip has one
arrangement and the term is constant for it, which is why none of the 27 historic single-day regressions
move. `_greedy_sequences` was separately plain first-fit over the dates in order — filling day
one to its ceiling before day two was offered anything — and now takes the emptiest day first, ties broken
on date, so the fallback the search lands on under a real catalogue does not reintroduce the crammed
shape. This is also what removed the repeated "add a day" loop: extending the trip used not to help,
because the optimizer still crammed the front and left the new day empty.

**A comfort tradeoff can be accepted (`WF-039`), and the acceptance is a number.** `comfort_acceptances`
(schema **14**) stores the *measured value* the owner agreed to per threshold code, and
`optimizer._accepts` requires `measured <= accepted_value` — so agreeing to a 27-minute walking leg never
blesses the 90-minute one a replan produces, while a tighter plan stays covered. `optimizer.COMFORT_RULES`
is the one table pairing each reason code with its violation code, metric and threshold key; validator,
soft count, `actions.comfort_tradeoffs` and the screen all read it.

Two things not to undo. **Consent must reach `_comfort_violation_count`, not just `validate_variant`** —
`comfort_violations` outranks `experience_value` in the objective tuple, so the search drops a place
rather than exceed a budget and the owner silently loses a stop; clearing only the hard error leaves that
intact. Measured on `jp-shibuya-plain-walk-overload`: 2 of 3 visits without an acceptance, **3 of 3 with
one**. And **do not revive `fits_with_tradeoff`** — no call site has ever produced it (only `fits` and
`cannot_currently_fit`), and the three threshold violations carry `subject_id: None` because they are
properties of the whole variant, so routing consent through a per-place record was the wrong shape.
`has_unaccepted_tradeoff` and the `exports.py` tradeoff list stay dead for that reason; deleting them is
its own decision.

### Names and photographs

**Two names, and two sources.** `shared/names.ts` is the one place naming happens, and it answers two
questions: `placeName()` for the readable name and `placeAltName()` for the local-script one beside it —
`null` where they would be identical, so a card never prints the same string twice. Both are shown because
a traveller needs each: the local name is what the station sign and a taxi driver use. Two sources feed it
via `mergeNames()`, **OpenStreetMap winning** because `name:en` is the name on the ground, with Wikidata's
label filling gaps. That matters because **61% of the Taipei catalogue (525 of 849) has no `name:en` at
all**; 131 of those carry a QID, and sampling 17 recovered a real English name for 13 —
三井物產株式會社舊廈 is "Mitsui & Co., Ltd. Old Building", not a translation. `WikidataSummaryProvider`
gets labels in the request it was already making (`props=sitelinks|claims|labels`), so the cost is zero. A
place with no article still yields a name: `text` can be empty while `names` is not, and
`refresh_place_summaries` stores the whole value, so nothing drops it. **Do not machine-translate the
rest** — the residual is places like 華江橋下自行車練習場 (a bicycle practice ground) with no name in any
free source, and inventing one is fabrication, not naming.

**Photographs have three sources**, assembled in one place, `web/src/shared/photos.ts`: Wikidata `P18` and
Wikipedia (both needing a QID, which 61% of the catalogue lacks), Wikimedia Commons **geosearch** from the
coordinates every candidate has, and OpenStreetMap's own `wikimedia_commons` / `image` tag stored as
`photo_reference`. Geosearch answers "what is photographed at this spot", **not** "photographs of this
place", so it is used only where nothing better exists and is stored `photos_are_nearby: true` so the
screen can say which it is showing. The radius is **400 m**: 150 m is the building rather than the site,
and a citadel or a park is routinely photographed from a corner of its own grounds. Geosearch returns
direct thumbnail URLs rather than `Special:FilePath` redirects, so these load in one round trip.

**A geosearch photograph must name the place, or it is not shown.** Saying which *kind* of picture it was
turned out not to be enough: the pilot offered a city bus as the picture of a hill, from
`KKMT_470-FY_right_side_at_Yuanshan_Bus_Station`, and a caption does not undo a wrong photograph on a card
whose picture is what the swipe decision is made on. `providers.photo_depicts_place` filters on the file's
own name, the only evidence available about its subject. Four parts to the rule:

- **Containment alone fails.** The catalogue calls that hill `Yuanshan`, which `Yuanshan Bus Station`
  contains — so the name must also account for at least `PHOTO_NAME_MIN_COVERAGE` of the file name, digits
  and the `File:`/extension wrapper removed. The two bus photographs score **0.20 and 0.31** against
  **0.46, 0.48 and 0.75** for correct ones, which is a gap rather than a boundary. Strip the wrapper or
  the rule inverts — counting `File:` and `.jpg` puts `Daan Forest Park` at 0.39 of its own photograph.
- **Every word of the name must appear, in any order.** Any-order is why `Thành cổ Điện Hải` is accepted
  for `Thành Điện Hải`. Matching *one* word instead would accept any `Taipei` street scene for the
  majority of a catalogue whose names begin with the city, so that is still refused — at the cost of
  `Herbarium 植物園蠟業館`, which really is the Herbarium of Taipei Botanical Garden and is rejected.
- **A verbose file name loses its place** — a title reciting country, city and district before naming the
  park scores 0.14, though such places generally carry a plainer file too.
- **A name under `PHOTO_NAME_MIN_CHARACTERS` matches nothing**: 圓山 is two characters and a substring of
  圓山站, 圓山公園 and 圓山大飯店, three different places.

Verified against the live API: Da-an Forest Park and Jieshou Park keep correct photographs and the correct
one now *leads*, while Yuanshan, Yuanshan Park, Mantoushan, Central Art Park and the Floriculture
Experiment Center show **no photograph rather than a wrong one** — 19 of 22 summaries carry a picture
against 19 before, so the whole cost was one correct photograph and four wrong ones.

**A summary carries the provider version it was written under.** `cache_version` existed on every provider
and `refresh_place_summaries` never consulted it, so a place cached before Commons geosearch was added kept
its empty gallery for the full 60-day TTL — cards stayed blank after the source that would have filled them
landed. The version is stored inside the value and compared on read, so bumping it (now
`wikidata-summary-v3`) refetches each place once and no further; that is what makes a stored bus heal
itself rather than sit out the TTL.

**A flag nothing renders is not a disclosure.** `photos_are_nearby` was written by
`refresh_place_summaries` and read by nothing — the flag existed, a comment claimed the screen used it,
and a Commons geosearch photograph of the next street was shown exactly like a photograph of the place.
Both the deck and the detail panel print `photo_is_nearby` instead of the Wikipedia credit when it is set.

### Where to stay (`WF-040`)

`travel_planner/areas.py` is a pure module and `actions.recommend_areas` the coordinator. **The unit is a
transit station, not a hotel and not a district** — that is how the owner searches ("it only near
ximenting station"), it is the only unit whose travel time the app can measure exactly, and district names
do not generalise (Taipei's OSM addresses carry `中正區` on 278 of 832 candidates, so parsing one would be
a Chinese-only regex over a third of the data). Five factors: travel time 45, metro access 20, food 15,
after-dark 10, lodging choice 10. Free — one Overpass request for the whole shortlist via
`OsmAreaAmenitiesProvider`, `openstreetmap:areas` priced at 0.0.

Four things are **never** scored and are returned on every result including an empty one: price, room type
and family capacity, cleanliness, safety. Do not fold any of them into the score — the owner's own
constraint was a family room that existed only on Airbnb, which no free source can see.

Three traps, all found by measuring rather than reasoning. **Group graph stops by name**: `STOP_TAGS`
admits platforms so relations resolve, so 437 Taipei stops are 138 stations (six for 板橋) and without
grouping the shortlist fills with duplicates. **Score travel time as a ratio against the best, not a rank
across the observed range**: the shortlisted stations all average 20-22 minutes, and rank-scaling turned
that into a 45-point gap. **Set count ceilings from data and use a log curve**: a linear scale saturating
at 30 gave every station a flat 15 of 15 when Taipei really returns 150-586. And `TransitGraph.journey`
returns `None` when nothing needs riding, so travel time takes the **better of riding and walking** —
otherwise a station across the road from a place scores as unreachable.

### Which months suit a destination (`WF-048`)

`travel_planner/climate.py` is a pure module and `actions.travel_month_guide` the coordinator, and a read.
A model asked "when should I go to Seoul" answers instantly and unverifiably — the failure `WF-046`
measured — so this answers from Open-Meteo's archive (five whole years of recorded daily highs, lows and
precipitation, keyless, free) and published public holidays. Both are priced at **US$0.00** and recorded
anyway, so call counts stay reconcilable.

Four things that are decisions rather than implementation. **Bands are relative to the destination**:
Taipei's coolest month is warmer than Seoul's warmest, so a global comfort threshold would call one city
uniformly bad and answer a question nobody asked — three best, three worst, six fair, per city. **Every
month is returned and stays selectable**, because a recommendation that removes the choice decides for an
owner who may be travelling on dates a school year sets. **A long national holiday is a `con` and a `pro`
at once** — it fills the trains *and* it is the only month the festival happens — and neither is netted
into the other, the same "report, do not decide" shape as `WF-047`'s cost options and `WF-045`'s drift.
Every verdict carries the numbers behind it, and the core emits codes with args while the view renders
them.

**Holidays come from two sources, because one was not enough.** Nager.Date's own coverage page puts **Asia
at 38%** (19 of 50) and depends on community contributions, so Taiwan, Thailand, Malaysia, India and the
UAE were all missing — the pilot destination among them. Google's public holiday calendars are free,
keyless, published as iCalendar and cover every one, so `_google_holidays` is the fallback and
`holiday_source` records which answered. **Turkey was never missing**: Nager has it as `Türkiye`, and
matching on the `destinations.py` spelling reported a covered country as uncovered — now aliased alongside
`Czechia`.

Two things about the Google feed that are load-bearing. **Observances are excluded**: it carries both
kinds and Taiwan's has 213 public holidays against 117 observances, so counting International Women's Day
would invent a crowd out of a day nobody takes off — the filter is on the feed's own `DESCRIPTION`, not on
the name. And **the calendar ids follow no derivable rule** — `en.taiwan`, `en.th`, `en.indian` and
`en.turkish` are all real while `en.tw`, `en.thailand` and `en.india` all 500 — so it is a looked-up
table, and a country in neither source stays honestly uncovered with a `month_crowding_unknown` con.

Verified on both. Seoul: best April, October, May; hardest January, February, July, catching **Seollal**
and **Chuseok**. Taipei: best January, March, November; hardest June, July, August, and February drops to
fair on a **9-day Lunar New Year run** — the single most important travel fact about Taiwan, and the one
that was invisible before.

**Read a cached value the way the store returns it.** `travel_month_guide`'s cache-hit branch read
`held["value"]`, but `store.get_trip_evidence` **spreads the stored value at the top level** and adds only
`retrieved_at` / `expires_at` — so every cache hit raised `KeyError`. It shipped because every read written
while building it passed `force=True`, which skips the branch. Measured after the fix: 9.08 s cold,
**0.017 s warm**. A branch no test enters is not code that works.

### Deleting a trip

`delete_trip` sat on the allowlist since S1 with no control anywhere, and building one found the method
unusable: `split_rows`, `split_settled_markers` and `comfort_acceptances` all arrived after
`store.delete_trip`'s ordered table list was written and none was added, so deleting any trip that had
settled a bill or accepted a comfort tradeoff raised `FOREIGN KEY constraint failed`. Its own comment
predicted exactly this — "a future trip-scoped table fails this transaction safely until added here" —
and nothing was checking it.
`test_delete_trip_removes_planning_data_but_keeps_paid_usage` already enumerated every trip-scoped table
and asserted zero rows survived, but the victim had no rows in the three, so it counted zero of zero and
passed; it now populates them. **Paid usage is deliberately kept** — the charge really happened, so it
stays on the monthly total. The confirmation is type-the-name (`delete_trip_confirm`): the deletion is
irreversible, and a button you can hit twice by reflex is not a confirmation.

### Bilingual by data, not by branching

All user-facing strings live in the eight `en`/`th` tables in `i18n/copy.json`; `travel_planner/copy.py`
reads it for the exports and React imports the same catalogue. The core emits stable codes; the views map
code → language → text. Switching language must never change ranking, scheduling, or the active plan — so
never put display text in the core or a language check in a scoring path. New user-visible string ⇒ add
both `en` and `th`. Tests enforce key parity across all tables except `CATEGORY_TEXT`'s documented
derived-English rule. Unknown stable codes render visibly as `⚠ CODE`; never prettify them into
copy-looking prose.

### Tests

Python uses `unittest`; the webapp uses Vitest. No network, no paid API, no Python fixtures framework.
Run the suite for the current test count rather than trusting one written in a doc.
`tests/fixtures/historic_regressions.json` encodes 20 atomic + 7 interaction failures from four real past
trips; `scripts/run_optimizer_regressions.py` replays all of them through the real optimizer. Behavior
changes to the optimizer should be expressed there.

## Deployment

**The app is live on Vercel and shared.** It was local-only until 2026-08-19; anything in this repository
or the journal that still says "local-only and single-owner" predates that and is wrong.

- `api/rpc.py` is the serverless entry, and it serves **everything** — Vercel's Python runtime routes
  every request to the declared entrypoint, so `/`, the stylesheet and the API all arrive there.
  File-based functions under `/api` are not offered to this project. `static_response` in
  `localserver/__init__.py` is shared with the local server rather than written twice, which carries
  the traversal guard and the extensionless-routes rule across.
- `vercel.json` pins `regions: ["sin1"]` beside Supabase in `ap-southeast-1`. This was worth more than
  every optimisation before it: the function ran in `iad1` and `build_export_snapshot` took 10.9s.
  **When a hosted read feels slow, check `x-vercel-id` before profiling anything.** Region is a
  performance decision, not a default.
- `buildCommand` does the web install; the Python runtime installs its own dependencies. Do not use
  `installCommand` — it replaces the whole install phase, which is how `psycopg` went missing from
  three builds.
- `pgstore.normalise_url` strips `pgbouncer=true` and other foreign parameters from the provider's
  `POSTGRES_URL`; libpq refuses the URI otherwise. It passes `sslmode` through untouched.
- A misconfigured deployment answers 503 `not_configured` naming the variable. An unexpected failure
  carries the exception **class** and never its message — a driver puts the host, user and sometimes
  the password in there, and this endpoint is public.

**Storage and the queue.** `open_store()` picks the backend: `TOURIST_DB_URL` selects Postgres, absence of
it selects the file. `PostgresStore` (`travel_planner/pgstore.py`) subclasses `SQLiteStore` and replaces
only `connect()`, so no statement is rewritten and the two backends cannot drift. Discovery is 30–90s and
a full proposal ~52s, so `travel_planner/jobs.py` holds the work and `travel_planner/worker.py` drains it,
claiming with `FOR UPDATE SKIP LOCKED`. The queue carries its own idempotent DDL and sits **outside
`SCHEMA_VERSION`** deliberately — it holds no planning truth and can be rebuilt.

**The worker is a long-lived process and Vercel has no home for it.** A container or small VM is required
somewhere; "Vercel + Supabase" alone does not run this app. Today it is a process on the owner's laptop,
and on 2026-08-23 it was **not running at all** — the deployment answered `job_timeout` at 300 s on every
job for hours, which reads as an application fault and is not one.

`deploy/macos/install.sh` installs a launchd agent that keeps it up across crash, sleep and reboot;
`deploy/macos/worker.sh` is the wrapper it runs and the one place the start-up rules are enforced rather
than remembered. The same script is the control surface — `status`, `logs`, `restart`, `stop`, `start`,
`uninstall`. `stop` leaves the plist, so launchd loads it again at the next login; only `uninstall` is
permanent. And `kill` is not a stop — `KeepAlive` returns the worker within seconds, so it is a slow
`restart` wearing a misleading name.

**Diagnose the worker by its python child, never by the `uv` wrapper.** `uv run` leaves two processes and
the parent holds nothing, so `lsof -p <uv pid> | grep -c psycopg` is `0` on a perfectly healthy worker.
`deploy/macos/install.sh status` prints both, plus the `draining PostgresStore` line that is the actual
answer.

**The agent needs `/bin/bash` in Full Disk Access, once per machine.** The repo lives under `~/Documents`,
which macOS protects, and a launchd agent gets neither access nor a prompt — the first install failed with
exit 126 and `Operation not permitted` on a script that runs perfectly from a terminal, because Terminal
holds the grant and launchd does not. Two consequences. The grant is attributed to the binary launchd
spawns, so the plist names `/bin/bash` explicitly instead of exec'ing the script through a
`#!/usr/bin/env bash` shebang whose image PATH would choose. And the secret stays out of it either way: a
plist in `~/Library/LaunchAgents` is world-readable, so the URL is read from `.env` at start rather than
written into `EnvironmentVariables` — `worker.sh` reads **`POSTGRES_URL_NON_POOLING`** and passes it to one
process without exporting it.

**Sharing.** The token is a random value the browser keeps in `localStorage` — not a credential and not
offered as one; it separates several people's trips, which was the actual problem. Two consequences:
trips are per-browser, so the same person in a second browser sees an empty list, and **the spend cap
is global, so any visitor can spend the owner's keys.**

`PUBLIC_RELEASE_PLAN.md` holds the canonical build order and exit gates for the wider release. Link to
it from tickets rather than copying its checklist; retain run evidence under `artifacts/validation/<run-id>/`.

## Configuration

**The hosted database can be named by more than one variable, and `store.HOSTED_URL_VARIABLES`
is the list.** `TOURIST_DB_URL` is first because it is the deliberate one — the worker's
command line and `deploy/` set it. `STORAGE_2_POSTGRES_URL` is Vercel's, written **and
rotated** by the Neon integration, which is the reason it is there: a hand-copied URL breaks
silently on the next credential change. The prefix is Vercel's own numbering, so the name is
specific rather than a `*_POSTGRES_URL` glob — a glob would also match a `STORAGE_1_` left
behind by the previous provider, and reaching the wrong database is worse than finding none.

`hosted_database_url()` is the one resolver, used by `open_store` and by `api/rpc.py`'s
guard, so a deployment cannot report itself misconfigured while working. And
`forget_hosted_database()` is the guard used by `tests/__init__.py`, `scripts/check.py` and
`scripts/check_reference_coverage.py` — **clear the list, never one name by hand.** Popping
`TOURIST_DB_URL` alone is how a suite comes to be redirected at production by an exported
variable, and that has happened twice: 96 test trips written into the live database during
the port, and a "Coverage probe" trip on the run that found the same hole in the gate.
`tests.test_store_selection` asserts the guard clears everything the resolver reads.

Paid usage is capped at **US$10/month** by decision (warn at $8). `usage.py` is that ledger: `PRICES_USD`
holds the estimated unit price per `provider:operation`, and `actions._spend()` refuses a call that would
cross the cap and records what it cost — see the `_spend` rule above, which is the ordering that makes the
cap real. Free-tier operations are recorded at zero so call counts stay reconcilable.

**The default model is `gpt-5.6-luna`** (`TOURIST_OPENAI_MODEL` overrides), which beat `gpt-4.1-mini` on
the `WF-046` benchmark — 6 of 12 exact against 5 of 13, four overshoots against five, and it declines
rather than claiming to know all thirteen. **The three `openai:*` prices were measured against luna's rate
card** (US$0.20/M input, US$1.20/M output at short context; nothing here reaches long context, and
`store: false` means caching never applies). luna is a *reasoning* model, so output is mostly hidden
reasoning and varies: six measured `opening_window` calls ran US$0.000090–US$0.000266, so it is priced at
**US$0.0005** and a 13-place refresh costs US$0.0065. `interpret_revision` and `explain_revision` are
sized from the real payload rather than measured end to end, so the UI correctly says **about** US$0.002.
**The ledger over-reports OpenAI spend by ~US$0.325** from 30 calls recorded at interim tenfold prices;
`paid_usage` is append-only by design, the error is in the safe direction, and it decays as new rows use
the measured price.

Environment: `TOURIST_DB_URL` (unset by default; when set it selects Postgres and **overrides the path** —
see the rules above), `TOURIST_DB_PATH` (default `data/tourist.sqlite3`), `TOURIST_NOMINATIM_URL`,
`TOURIST_OVERPASS_URL`, `TOURIST_USER_AGENT`, `TOURIST_GTFS_PATH` (default `data/gtfs/transit.zip`).

**Providers read keys from `os.environ` and nowhere else** — that is what keeps a key out of every
snapshot, export and log. `credentials.load_local_credentials()` copies a flat `secrets.local.json` into
the environment first, so the owner need not export four variables per shell; an already-set variable
always wins, and the module never logs or returns a value. It is called once at startup by `localserver`
and once by `travel_planner/worker.py`, which is the thing that talks to providers — **secrets are loaded
only at an entry point, never at import.** `.env` / `secrets.local.json` are gitignored, `.env.example` /
`secrets.example.json` hold names and placeholders. `scripts/check_provider_access.py` reads the same file
directly. `tests/__init__.py` sets `TOURIST_LOCAL_SECRETS=off`; the original reason died with the POC, but
**do not remove that line** — it costs nothing and the failure it prevents is a bill.

`enrich_place_card` photographs are a **session overlay**, not a `place_summaries` write. Both the detail
panel and swipe deck must read `PlaceInsight` directly; invalidating the free-summary query cannot reveal
paid photographs and leaves the charged card blank. Disable the card's paid control while that overlay is
arriving so one press cannot become two charges.

## Graphify: this repo overrides the parent instructions

The ancestor `Thaksin/CLAUDE.md` tells agents to run `graphify query` for codebase questions and
`graphify update .` after edits. **Do not do either here.** Read source and tests directly; consult
`graphify-out/GRAPH_REPORT.md` only for a broad architecture question. That report carries a generated
"Graph Freshness" line advising `graphify update .` — it is graphify boilerplate, regenerated on every
rebuild, and wrong for this repo. Ignore it.

`graphify-out/graph.json` is canonical and **must stay directed**: `graphify update . --no-cluster` once
corrupted it, dropping the `directed` flag and removing the Wayfinder/document nodes. **Rebuild only
through `python3 scripts/build_project_graph.py`** (paid, needs `OPENAI_API_KEY` which it reads from
`secrets.local.json` itself; wraps extract → normalize → cluster-only → export and restores the previous
graph on failure), and only when explicitly asked or after a topology-changing milestone. After any graph
change, `--check` must pass before committing. **Never run `graphify extract` by hand** — it is
incremental against an existing `graph.json` and will overwrite it with a partial. `AGENTS.md` has the
operational detail; rebuild history and per-run costs are in `docs/JOURNAL.md`.

**Adding a ticket file breaks stage 4 of `check.py` until a rebuild**, because `--check` demands a node
per ticket. That is the normal reason to pay for one.

**Retry before diagnosing.** Two failure modes are documented and both look like data loss:

- **Extraction is not deterministic.** `Extraction produced no node for WF-0nn` has fired on a ticket that
  was perfectly fine, and the immediate retry produced the node. Treat a single occurrence as a coin-flip.
- **Clustering variance** drops valid extracted endpoint pairs, sometimes over a hundred of them, most
  belonging to code the session never touched.

A retry is usually **free**, because the semantic cache stays warm — repeat runs report 70-90 hits and 0-2
misses. **Read `cost.json` rather than reasoning about which attempt paid**: a failed run records its own
cost, and the warm retry that succeeds may add nothing. If validation fails twice, inspect both
`failed-raw.json` and `failed-clustered.json` — `build()` preserves them for exactly this — before paying
for another extraction.

**Do not weaken the endpoint-pair guard to get past a failure; find the collision.** Three times a
validation refusal traced to a **name collision** where extraction invented an edge claiming Python calls
TypeScript or the reverse: a test-local `def rpc` against `client.ts`'s exported `rpc`, a provider method
`fetch` against the browser's `fetch` (renamed `read_page`), and a TypeScript export `at` against a Python
local `def at` (renamed `momentAt`). **Do not name anything on either side after a short generic the other
side also uses.** The rule is symmetric — a two-letter TypeScript export collided with a Python local just
as easily as the other way round — and the fix is always renaming.

**Ticket-authoring rules**, each learned paying for a run. **Ticket nodes are keyed by title, not by ID**,
so `WF-0nn` never appears in a node name. **Cite a module by its path** — a bare `exports.py` extracted as
a node id that does not exist, clustering rightly dropped the edge, and the guard then demanded a false
edge survive. A ticket dense in code identifiers may extract no titled node at all, which is why
`resolve_ticket_node` takes `required=` and refuses over ambiguity only when the id is actually used as a
`blocked_by` endpoint; an **empty** extraction still always raises, because that is the per-ticket presence
guard `--check` depends on. And **`--exclude` patterns are gitignore lines**, so anchor them (`/artifacts`,
not `artifacts`) or they match at every depth.

**`normalize_raw_graph` folds duplicate node twins, and it prints every fold it makes** — a silent fold
is indistinguishable from the pair guard being weakened, and `tests/test_graph_builder.py` pins the
behaviour including the negative cases. Two traps sit here. Extraction sometimes emits one
file twice, with **and without** a separator (`travel_planner_destinations_py` and
`travel_planner_destinationspy`), so `SOURCE_SUFFIX_IDS` is generated from one extension tuple in both
spellings; treat the list as incomplete rather than exhaustive. And **the fold requires the stem to be a
*file* node**: `json` is in `SOURCE_EXTENSIONS` and `_json` is also an ordinary Python method name, so
`PlannerHandler._json` found its own *class* sitting there as a stem and was folded out of existence, along
with three providers' `_json`. A class is not a file, and a method is not a duplicate of its class.

**`INFERRED` edges are attributed at file granularity**, so one means "something in this file does this",
never "this symbol does this" — thirty same-file groups show every top-level class in a module inheriting
one inferred edge set, which is how the two-line `PlannerRefusal` comes to `use` `CandidateChoice`,
`DiscoveryRun` and `PlanVersion`. Its 27 outgoing inferred edges are *byte-identical* to
`PlannerActions`', with nothing unique to it, which is the proof rather than a suspicion. Read
them that way and never cite one as evidence about a class. This is left unpruned on purpose: the obvious
guard removes 468 of 691 inferred edges and cannot tell indirect use from invention, since a test calling
`self.actions` really does use `PlannerActions` without ever writing the word.

Two counting traps when reading the report, and one conclusion. It reports **outgoing** inferred edges
only, and its community lists are filtered (105 thin communities omitted), so neither number is the graph's
own. The conclusion: `PlannerActions` bridging everything is **the design working**, not a smell — it is
the only coordinator, by decision, and it still reaches 41 communities with every inferred edge removed.
`SQLiteStore` is the same story one layer down. Neither is a refactoring target, and a graph metric is not
an argument for splitting them.

**A node's `source_file` may hold an absolute path from the machine that built the graph**, which is not
`is_absolute()` on Windows — joining it to the repository root produced a drive-relative path that matched
nothing and failed `--check` with `Extraction produced no node for WF-001` on every ticket except the one
stored relatively. `build_project_graph.source_path()` resolves a node's source against the longest
trailing segments that exist in this checkout. Diagnose a `--check` failure by counting the
wayfinder-sourced nodes before assuming data loss.

## Wayfinder: decisions live in tickets

There are **two maps**, and tickets are numbered continuously across both in `.wayfinder/tickets/`; a
ticket's `parent:` field says which map it belongs to.

- `.wayfinder/map.md` (`WF-MAP-001`, **closed**) indexes the 17 closed Phase 1 decision tickets.
- `.wayfinder/map-002-splitter-merge-and-webapp.md` (`WF-MAP-002`) is Phase 2: merging
  `Auto-Bill-Splitter` in as a group split ledger and replacing Streamlit with a React webapp.
  Decision-complete since 2026-08-03 — 49 tickets, 49 closed.

Before changing scoring weights, optimizer rules, schema, or provider policy, **read the relevant
ticket — the "why" is there, not in the code.** Reference tickets by linked title, never bare ID.

All six slices are built and evidenced. `api/` owns the RPC boundary, `localserver/` the local HTTP
server and downloads, `web/` the routes and in-place `StageGate`, and `scripts/check.py` is the one
free green command. `exports.py` builds the one shared export snapshot and `exporters.py` writes the
Excel workbook and readiness ICS — both snapshot-in, bytes-out; `checklist.py` generates the
readiness board. `/evidence` belongs to no slice row: it was built between S5 and S6 because none
owned it, and a *newly created* trip needs it, since route and opening evidence are hard optimizer
constraints. The Streamlit POC that proved the core works was deleted at S6 on 2026-08-04, and with it
`fpdf2`, the 9:16 poster, the trip PDF and the whole export-font apparatus — no Unicode TTF, no
`resolve_font()`, no `TOURIST_EXPORT_FONT`. `_labels()` still strips pictographs, because the wording
alone carrying the state is an accessibility rule and not only an export one.

Out of scope for the Python core: FastAPI, Docker, Redis, remote collaboration, hosted notifications.
Runtime dependencies are `xlsxwriter` (slice 5 renders a workbook) and the two `psycopg` lines the
hosted deployment needs — `pyproject.toml` explains why they are there and not only in
`requirements.txt`. `pillow` is a dev dependency; the screen-baseline gate reads PNGs with it.

Slice-by-slice detail, and the counts that went with each slice, are in `docs/JOURNAL.md`.

## The journal

`docs/JOURNAL.md` holds the dated build history: owner-testing rounds, the hosted port, the Vercel
deployment, the graph rebuilds and the slice-by-slice Phase 2 record. It is history, not guidance — where
it contradicts this file, this file wins. Read it for the reasoning behind a specific decision when the
ticket does not carry it; do not read it top-to-bottom before starting work.

**When something in this file stops being true, edit it.** The journal grew to thousands of lines because
every change was appended as a new dated section while the old claim stayed where it was, and the file
ended up asserting both. This file has been pruned that way twice; keep it that way — a rule, its
decisive measurement, and nothing of the story around it.
