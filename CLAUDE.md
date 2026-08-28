# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Dated build history lives in `docs/JOURNAL.md`. This file is the current state; the journal is
why it got that way. Design decisions are in `.wayfinder/tickets/`.

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
`ensure_web_build()` runs **only at startup**, and only rebuilds when a source is newer
than `web/dist/index.html` — so a server left running never picks anything up, and a tab
left open holds the old JavaScript even after it does. Six rounds of owner testing produced
reports of fixes "not working" that had been verified working minutes earlier, and every
one was this. The sidebar prints `build <timestamp>` for exactly this reason: if it does
not match the build just made, nothing about behaviour is worth discussing yet.

## Rules that bind new work

Each of these was learned by breaking it. The journal entry behind each is in `docs/JOURNAL.md`.

**Data and money**

- `TOURIST_DB_URL` **overrides the path it was handed**, so any shell that exports it redirects
  everything that builds a store — tests included. It is cleared in `tests/__init__.py`,
  `scripts/check.py` and `scripts/check_reference_coverage.py`. **Any new script that builds a store
  for verification must clear it too.** It has written test trips and fabricated ledger rows into the
  owner's hosted database twice. A guard at one entry point is not a guard.
- **Do not bump `SCHEMA_VERSION` against a hosted database.** `PostgresStore._copy_before_bump`
  refuses outright, correctly — the file-copy backup a bump demands has no hosted equivalent until
  the owner decides what it is.
- `supabase/schema.sql` is **generated from `store.SCHEMA`**, never hand-edited. A second schema is a
  second source of truth.
- `supabase/backups/` is the **live structure recovery artifact**, not a second schema
  source. Refresh it with `scripts/backup_supabase_schema.py` after hosted structural
  changes. It deliberately contains no rows, so it does not satisfy the private data
  backup required before a destructive migration.
- Every paid provider call routes through `actions._spend()`. An unpriced operation raises rather than
  being assumed free, and the ledger is append-only by trigger. **`_spend` goes before the request,
  on every path.** `_area_amenity_counts` had it after, so the cap was consulted only once the call
  had gone out — the one operation that could cross a spent cap rather than be refused by it. It is
  priced at US$0.00, which is exactly why nothing was overspent and why it went unnoticed for so long:
  the ordering is the invariant, not the amount, and the next operation copied from it will not be
  free. A US$0.00 operation also cannot be refused *by* the cap, so test the ordering directly.
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
- **Hosted egress is the first release criterion: exhausting it disables the app.**
  `scripts/check.py` therefore runs `tests.test_discovery_egress` before every other gate.
  `paid_usage_status()` must aggregate with `summarize_paid_usage()` in SQL; raw ledger
  reads require an explicit limit of at most 1,000 rows; and a zero-price `_spend()` must
  never read the ledger before recording the call. Do not replace any of those with a
  Python-side total. **A read that wants four floats must not fetch 390 KB.** `get_latest_discovery`
  is `SELECT *` and `candidates_json` is ~390 KB on a real city; four callers wanted only
  `query_boundary` and three of them ran on every `/itinerary` view. Use
  `actions._discovery_boundary()` / `store.get_latest_discovery_report()` for anything that is not the
  candidate list itself; navigation uses `get_latest_discovery_header()`.
  **`list_route_snapshots` is the same shape** — `SELECT *`, and a route
  carries its drawn geometry, so five hundred of them is most of a megabyte. Anything that only needs
  to know *whether* a pair is measured takes `store.list_route_pair_keys()`. Supabase's free tier allows 5.5 GB and this trip passed it. The roughly
  217 KB basemap is immutable until its evidence expiry, so `shared/basemap.ts` also keeps it in
  browser storage until the server-provided `expires_at`; do not replace that with a cache for mutable
  plan or route snapshots without measuring another egress problem first.
- **`TOURIST_DB_URL` is a *template* in `.env`, not a literal — it reads
  `"$POSTGRES_URL_NON_POOLING"`.** Passing that commented line's value through verbatim
  starts a worker that loops on `missing "=" after "$POSTGRES_URL_NON_POOLING"`. The
  variable to read is `POSTGRES_URL_NON_POOLING`, per-command and never exported.
- **A worker started without `TOURIST_DB_URL` drains the *local file* and looks perfectly
  healthy doing it.** The deployed app queues into Postgres, so its jobs sit forever while
  the worker reports nothing wrong — `find places` simply times out at the client's 120 s
  abort. Diagnose it by what the worker is *not* holding: no `psycopg` in
  `lsof -p <pid>`, no TCP connection, and a local `jobs` table with zero rows while the
  hosted one has a backlog. The second line of its output is the direct answer —
  `draining PostgresStore` or `draining SQLiteStore`.
- **The worker's idle poll backs off from 2s to `MAX_IDLE_SLEEP_SECONDS` (10s) and resets on any job.**
  A flat 2s is 43,200 queries a day whether or not anyone is using the app. Keep the ceiling below
  `REAP_EVERY_SECONDS` or abandoned jobs slip a whole reap cycle.
- **The worker's loop outlives one bad poll.** `reap_stale`/`run_one` raise on a transient drop;
  bare, that ended the process with the job still `running` and launchd turned it into a 30-second
  crash-loop. The loop catches, logs, backs off, retries. Recording the failure stays inside
  `run_one` — if `fail` cannot reach the database, the reap is the recovery.

**The core**

- The dependency direction below is one-way and enforced by review. Replacing the whole interface at S6
  cost the core nothing because of it.
- **Every new output reads `build_export_snapshot()`**, never the raw variant — that is what keeps
  times, totals and statuses from diverging between outputs.
- **`/optimize` reads its assumptions out of the frozen `optimizer_input`, never recomputed.** The
  snapshot records its own `capability_gaps`; a second opinion derived beside it could disagree with
  the plan it claims to describe.
- **`optimize_trip`'s `on_variant` is the one hook in the pure core, and it observes only.**
  It imports nothing, takes a count, returns nothing, and is never read back — the three
  variants are ~21s each and the whole call was otherwise a single silent minute on every
  build path but auto-resolve. The property that keeps it honest is asserted, not assumed:
  the same input produces the same `deterministic_signature` whether or not a hook was
  passed. Anything that wants to *influence* the optimizer is not this and does not belong
  here.
- The destination string is **`"City, Country"`** — `AppShell.countrySlug()` takes the last
  comma-separated segment, so a city-only string silently loses the destination accent.
- **A slow operation must be queued.** `DEFERRED` is derived from `HANDLERS`; anything inline over
  ~60s answers `http_504` on the deployment while working perfectly locally.
- **A queued job's client deadline measures *silence*, not duration.** It always meant
  "fire when the worker is down, not when the work is slow", and as a flat ceiling on
  total runtime it did the opposite: a `refresh_routes` sweep stored 462 routes in **843
  seconds**, finished cleanly, and the browser had thrown `job_timeout` at 300. Any rise
  in the reported count resets the clock, and `run_one` writes a `0` on claim so being
  picked up resets it too — five minutes unclaimed still fails, which is the case worth
  reporting. An operation that reports nothing keeps the flat five minutes; every
  operation is bounded server-side anyway. The corollary: **an operation that can outlive
  the deadline must report often enough to prove it is alive.** A sweep speaking only
  between passes was still at risk, since a slow provider can spend five minutes inside
  one pass of sixty — `ROUTE_PROGRESS_EVERY` is why it speaks every ten routes.
- **A paid refusal must be remembered, or it is bought again.** `_spend` is recorded
  *before* the request, so a `ProviderNoMatch` costs US$0.025 and returns nothing — and
  the screen said "asking again will not find more" while the button sat there letting
  you. A `provider_no_match` evidence row now refuses the second ask before spending,
  expiring after `PROVIDER_NO_MATCH_DAYS` so a place Google later indexes becomes askable
  again. The same rule on the other side: the deck's buy button withdraws once a place has
  been enriched, because a purchase that returned one photograph will return one
  photograph again. **Note the shape of `list_place_evidence`** — it returns the stored
  snapshot, not the row, so anything that needs `place_id` back must put it *inside* the
  value, which is why `list_venue_notices` does.
- **One worker runs one job at a time, so a long job is a queue-wide outage.** Measured:
  an 843-second `refresh_routes` sweep left `generate_plan_preview` — *three seconds* of
  work — waiting 482s to be claimed, and discovery waiting 885s, which the client
  correctly reported as `job_timeout` on a build that had not started. **Bound anything
  that can run long.** `ROUTE_SWEEP_SECONDS` stops a sweep starting a new pass after
  sixty seconds, so a job is that plus the pass in flight — about 110s at the provider's
  1.8s-a-route pacing, which is what the design did before the sweep existed and never
  starved anything. A job that stops early must say so (`more_pairs`) and the caller must
  come back; when it does, `onProgress` needs a running base, because each job counts from
  zero and a stage that restarts at every request is worse than no count.
  Do not "fix" a long job by widening the client's patience — that hides the starvation
  from the one place that can see it.
- **A bound checked between passes is not a bound.** `ROUTE_SWEEP_SECONDS` was read only
  where a *new pass* would start, and one pass of `MAX_ROUTE_REQUESTS` at the provider's
  measured ~2.1s a route is about 128 seconds — so the sixty-second budget was already
  spent by the first check, every job was exactly one pass, and the multi-pass sweep it
  was written to bound never ran a second pass in production. It is read inside the
  request loop now. **Read a deadline where the work actually is**, and when a constant
  claims a number, check the measurement still produces it: the docstring said 110s and
  the queue said 128.
- **Bounding a job does not shorten the work — it moves it into the caller's loop.**
  Bounding the sweep turned one 843s job into *nine* 128s jobs, so the queue stopped
  starving and the owner's build went from 843 to **1200 seconds**, spinning the whole
  time because progress resets the client's deadline. Read the queue before believing a
  fix landed: nine consecutive `refresh_routes` rows each reporting `progress 60` is what
  that looks like, and `ran` alone will not show it.
- **Fetch for coverage, not for completeness — that, not the ordering, was the twenty
  minutes.** Route evidence is quadratic (41 places are 1640 ordered pairs) and the plan
  needs almost none of it: a place with no route at all is dropped `ROUTE_UNVERIFIED`,
  while a missing pair between two places that each have one is a leg the optimizer
  routes around. Grouping the Tokyo trip's stored rows by retrieval minute shows ten
  bursts of sixty and **every place reached by burst two** — the other eight bought
  refinement nobody was waiting for. `_refresh_routes_with` reports `places_unserved`
  and `collectRouteEvidence` stops on it rather than on `more_pairs`.
  Secondary, and worth keeping straight because the first guess blamed it for the whole
  thing: the old `served` set was read once from stored routes, so on a first sweep every
  pair looked unserved and the order collapsed to pure nearest-first, leaving one place
  of twenty-three unreached after burst one. Promoting the nearest pair that reaches a
  starved place fixes that — **both directions**, since `optimizer._best_route` matches
  origin-to-destination and does not read a leg backwards. Two bursts become one. Size a
  claim like this against the stored data before writing it down; the first version of
  this bullet said nine.
- **One matrix request replaces sixteen hundred directions requests, and the trade is the
  drawn line.** `OpenRouteServiceMatrixProvider` measures every pair at once — same
  service, same free tier, `openrouteservice:matrix` priced at US$0.00 since before
  anything called it. Measured against the live endpoint at 23 places: **506 pairs in
  1.59s**, against 0.87s for one directions call from the same machine — 7.4 minutes of
  pair-by-pair here, ~17.7 at the deployment's 2.1s. It returns **no geometry**, so its
  routes carry `geometry: []`
  and the map draws them as `exact: false` straight lines, which `ItineraryPage` already
  did for an unrouted leg. `refresh_routes` seeds from it and the directions sweep
  upgrades pairs behind it, nearest first. Two consequences: a matrix row is fresh
  evidence *and* still upgradeable, so **both** cache checks in `_refresh_routes_with`
  exempt it (the pair filter and the one inside the fetch loop — the second is what the
  per-pass cap is measured against), and the seed degrades to zero on any failure rather
  than refusing, because the worst case must be the behaviour that came before.
- **A queued operation is expensive to ask for, so do not loop on one from the browser.**
  Every RPC for slow work is a job: enqueue, poll at 1.5s, wait for the worker to claim
  it, poll again — four to twelve seconds of latency before the work starts.
  `collectRouteEvidence` made up to twelve of those in a row and that, not the optimizer,
  was most of a measured ten-minute build. The loop belongs on the server, where the
  passes are consecutive and free: `refresh_routes(max_passes=...)` is the shape, and it
  changes nothing about the work — `_spend` still runs once per route, so the cap is
  checked exactly as often. `force` stays one pass: it refetches cached pairs, so a loop
  would buy the same sixty routes until the ceiling.
- Job payload allowlist keys must match their handler's signature — `tests/test_jobs.py` checks every
  one. An allowlist that permits keys the handler rejects is worse than none.
- **`enqueue`'s look and insert are one transaction, and on Postgres they hold an advisory
  lock.** They were two `connect()` blocks, which is two transactions with a gap: two
  presses landing inside it both read "nothing queued" and both inserted, defeating the
  de-duplication the method exists for. The lock is transaction-scoped and keyed on
  (trip, kind, payload), so only presses that could actually collide wait. Chosen over a
  partial unique index because that is a schema migration against a hosted database.
- **Postgres text cannot contain a NUL byte, and the Postgres branch of `enqueue` has no
  test coverage — those two facts together broke the deployment.** The lock key was first
  passed as text for `hashtext` to hash, joined on `\x00`; every `enqueue` raised
  `DataError`, which is all four queued operations, and "find places" answered
  `internal error`. `is_postgres` is false on SQLite so the suite could not reach the
  statement, and the probe run against the real database checked the *function overload*
  with a harmless literal rather than the key the code builds — it proved the wrong half.
  `_enqueue_lock_key` hashes with `zlib.crc32` in Python now, so what crosses the wire is
  an integer with no encoding rules to violate, and `tests/test_jobs.py`'s
  `PostgresEnqueueTest` fakes a store named `PostgresStore` to assert the parameters of
  every Postgres-only statement. **When verifying against a live database, exercise the
  value the code actually constructs.**
- **Deleting a trip must clear its jobs, and `store.delete_trip` cannot.** The queue is
  deliberately outside `SCHEMA_VERSION` with no foreign key to `trips`, so the ordered
  table list — and the test that enumerates every table with a foreign key — can never
  reach it. A deleted trip left queued work for a worker to claim and fail on,
  `max_attempts` times each. `actions.delete_trip` calls `JobQueue.discard_trip` first,
  so a failure leaves a trip that still exists rather than jobs pointing at one that does
  not.
- **The worker's health endpoint answers any GET on an unauthenticated `0.0.0.0:$PORT`.**
  It published `worker_id` — `hostname:pid:random`. `worker.initial_state` is now the
  whole of what it may say, and it is a function rather than a literal because it is a
  security boundary worth testing directly. The id is unchanged in the log and in
  `claimed_by`, which the owner reads and the internet does not.
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

**The interface**

- **There are three breakpoints — 600, 860, 1100 — and `shell.css`'s header block is the list.**
  It carried **twelve** distinct width values (500, 560, 600, 720, 768, 860, 861, 900, 992, 1000,
  1040, 1100), mixing min and max, so three different rules disagreed about where a phone stopped.
  **860 is load-bearing**: it is also `PHONE` in `shared/useMediaQuery.ts`, which decides whether the
  sidebar or the tab bar is rendered at all, so changing one without the other draws a navigation the
  stylesheet is not expecting. The old `max-width: 992px` block — which turned the shell into
  `display: block` — is the one whose move actually changes something: with the sidebar no longer
  rendered below 861, it had become a band where a full-width ten-link sidebar stacked above every page.
- **The capture set has a third viewport, `t900-`, because 500 and 1440 left the middle untested.**
  Consolidating those twelve breakpoints was a change no gate could have caught going wrong. The phone
  set also covers **every** stage route now, not the four it began with.
- **The type scale's small end is not to be touched, and the heading end is where the contrast went.**
  241 of 279 uses sit in the 12-15px band while `h1` was 27px — about 1.8x body, which is why screens
  read as one flat grey. `--text-4xl` is 30 (28 on a phone, where 30 wraps "Split actual bills" at
  500px), `5xl` 34, `6xl` 42; `2xs`/`xs`/`sm` are unchanged because a global bump would reflow 241
  dense-UI call sites. `font-size` is not one of the five properties the parity gate compares.
  On a phone `tokens.css` redefines `2xs`/`xs`/`sm` one notch up on `:root`, so the relationships hold
  and nothing that lined up stops lining up.
- **The touch floor covers `a`, not just `a.stage-link` — and the headless capture cannot check it.**
  Headless Chrome on macOS clamps its window to a 500px minimum, so the `m500-` set is not a
  phone. Driven through cmux at a real **390px**, `/itinerary`'s five `.plan-next-action`
  links measured **42px** while every capture said the screen was fine. Bare `a` is safe for
  running prose because `min-height` does not apply to a non-replaced inline element, which
  is why the map's "© OpenStreetMap contributors" credit correctly stays 16px.
  **Measure the phone in a real browser before believing the phone baselines.**
  `cmux browser <surface> viewport 390 844` plus `eval` is the whole harness; it also
  confirmed the 861/860 boundary is exact, that no route overflows horizontally, and that
  everything past the right edge on `/costs` and `/itinerary` is inside a legitimate
  `overflow-x: auto` scroller (`.money-table`, `.day-tabs`) or an SVG map viewBox.
- **An author `display:` on a `<dialog>` beats the user agent's closed-dialog hiding.**
  The UA hides a closed dialog with `dialog:not([open]) { display: none }`, and a class
  selector outranks it — so any dialog class given a `display` needs its own
  `:not([open]) { display: none }` or the closed sheet paints over every phone screen.
  `.tour-backdrop`, `.sidebar.sheet-dialog` and `.day-stop-lightbox` all have it, and
  `tests/test_dialog_display_guard.py` now requires it of the fourth, which will be
  written by someone who has not read this. It was caught once by opening the capture
  diffs before approving, which is not a mechanism.
- **`--virtual-time-budget` is 15000 and both directions of that number were measured.**
  `/places` is the only screen whose content arrives asynchronously. At 5000 the deck is
  still showing "Looking it up on the map…", and a loading placeholder is *stable*, so
  `stable_capture`'s two-identical-shots rule accepts it happily — one run caught the
  placeholder, the next caught the card, and the gate reported 2.9% drift on unchanged
  code. At 30000 it fails the other way: virtual time outruns the real network, a request
  aborts, and a "Failed to fetch" banner pushes the page down 29px for 12% drift, again on
  unchanged code. **Bigger is not safer.** Re-measure before changing it, and remember that
  a stable-looking intermediate state defeats the settle check entirely.
- **A wizard chip holds an icon, a number and a short label, and each of the three was
  measured into place.** `STEP_ICONS` is `aria-hidden` and the button carries an
  `aria-label` of "Step N of 5 · <title>", because `.wizard-step-label` is `display: none`
  below 1100px and that had been taking the name out of the accessible tree entirely. The
  visible label is the **short** `chip_*` form: the full names fit only at 1440px and up,
  and truncated to "Before y…" / "Owner tri…" below it. `.wizard-step-icon` needs
  `flex-shrink: 0` — as a flex item in one of five equal columns it was compressed to
  **2px wide** at 390px, rendered and visible and invisible.
- **The landing lost three sections on 2026-08-23** — "Why Mathematical Planning Beats
  Generic AI", "Interactive Bill Settlement Engine" and "How Optimizer Compares" — at the
  owner's asking. Removing a section is not just deleting JSX: it orphaned three nav
  buttons, two `useState` hooks, a whole bill-split computation, and **51 CSS rules**. The
  surviving grouped selectors still name `.benefit-card` and `.comparison-table`
  alongside live classes; those entries are inert and were left rather than picked apart.
  `splitCurrency` survived as a plain const because the lab's conversion table still reads
  it — check what a removed section *shared* before deleting its state.
- **The closing section is `<ShoreScene />`, not a `SceneEnvironment` variant, and the
  difference is measurable.** A variant is a ridge anchored to the foot of a band; that
  section is 1046px tall, so it got a wash with a strip along the bottom — 346 of 1046px
  at 0.68 opacity, against the world scene's 702 of 702 at 1.0, which is what it was asked
  to match. It is now the same construction as `.world-scenery`: one full-height SVG, the
  shared `w-rough` presses, four `--depth` layers, grain last.
- **That SVG is `preserveAspectRatio="none"` with a 900-tall viewBox, and `slice` is the
  trap.** `SceneEnvironment` already documents it; this hit it again. Sliced into a
  section-tall box the 1200-wide composition scaled **1.69x** and cropped to viewBox
  x 220..979 — the boat was 60% outside the frame. A 900-tall box stretched into a ~1046px
  band distorts about 1.16x, which is invisible.
- **Its composition is laid out around the cards, because they are opaque.** Measured, the
  columns cover viewBox x 90..1110 / y 202..609 and the trust strip x 240..960 / y 636..845.
  Anything worth seeing goes above 200 or below 610, and the waterline sits at 772 rather
  than 646 so there is water to moor a boat on *outside* those rectangles. Re-measure
  before moving an object; twice now something has been drawn correctly and been invisible.
- **`BuildStages` takes a stage list, and every list is the calls its page awaits.**
  `BUILD_STAGES` is `/optimize`'s four; `PLAN_STAGES` is `StayPlanner`'s three —
  `save_setup`, `discover_places`, `generate_plan_preview`. That press is the longest
  wait in the app and showed one rotating line, so a slow discovery and a slow proposal
  looked identical and both looked like a hang. The rule is unchanged and is the whole
  point: **a stage ticks when its call returns, never on a timer**, and `Thinking` stays
  nested inside the final stage where `generate_plan_preview` genuinely has no
  milestones. Adding a stage that no `await` corresponds to is a claim about work that
  is not happening — `stayplanner.test.tsx` pins the count to three.
  `PLACES_STAGES` is the third and the odd one: four of its five are reported by the
  **worker** rather than awaited by the page, because `/places` is one queued job. See
  the rule on `REPORTS_PROGRESS` below — the count still moves only on a call returning,
  which is what let that screen have stages at all instead of timed fiction.
- **`ShoreScene` is `slice`, and `SceneEnvironment` is `none`, and the difference is
  what each one draws.** That comment is right that abstract terrain "is the one thing
  that tolerates" stretching; a lighthouse and a boat do not. Measured, `none` on this
  box distorts **20% at 1280x772, 46% at 1920 wide and 276% on a phone**. `slice` never
  distorts and pays for it by cropping the sky, which is the right way round for a
  background. It also means the section's own gradient and the SVG must agree about
  where the horizon is, since the crop moves it.
- **Do not shrink an object to fit a gap.** The boat was squeezed to 86 units wide to
  survive in the right margin and the jetty flattened into a 56-unit band, both to keep
  them out from behind the cards. A miniature crammed into a hole reads worse than a
  whole object half-covered — it is a *background*, and the cards are translucent. Size
  objects to the scene; let the layout cover what it covers.
- **The two cards are `rgb(from var(--bg-card) r g b / 86%)`, and 86% is a contrast
  budget.** Computed across the range: 8% is invisible, 15% is the last value clearing
  4.5:1, 20% fails. Also note the specificity — `.landing .stage-card` sets an opaque
  background later in the file at the same weight, so the rule needs `.landing` on the
  front or it silently does nothing, which cost two rounds of "the transparency is too
  subtle to see". And `.section-lead` takes `--text-primary` here: with the sky cropped
  it sits on the bay, where secondary ink measured **2.87:1**.
- **`ShoreScene` is eight layers and four motion categories, all on existing machinery.**
  `startWorldMotion` already provides `--scroll-y`, `.motion-ready` and `.in-view`; the
  parallax rates, the staged reveal and the ambient loops are CSS on top of it, so no
  dependency was added and `WF-026` holds. Every animation and every hover transform lives
  inside `prefers-reduced-motion: no-preference` — checked by parsing the stylesheet, not
  by reading it — and capture mode freezes animation, so the baselines are unaffected.
- **The scenery is `pointer-events: none` and only `.s-mark` takes events back.** Three
  landmarks answer to a pointer by transforming *themselves* (lift, rotation, scale
  1.03-1.06), never a box-shadow. Verified by hit-testing real points on each shape rather
  than bounding-box centres — two of three centres land on holes, which reads as a failure
  and is not one. The form's inputs must stay the top element where they sit.
- **The scene carries the reference's four signatures, and it was short of all four.**
  Compared path by path against `.world-scenery`: a bright edge on the distant mass
  (`w-snow` → `s-cliff`, or a silhouette reads as a cut-out), **two** halftone screens on
  the ground rather than one, colour landing in exactly one place (`w-bloom` → the buoys
  and shells), and the **dashed route** — `.s-path` copies `.w-path`'s stroke, dash and
  cap unchanged, because the trail through the mountains and the trail along the shore
  have to be one idea.
- **`--landing-estuary-*` is that section's palette and every value flips by theme.** Seven
  tokens, because the landing's mountain tokens are fixed and a scene built from them is a
  bright noon coast inside a dark page. The section's background gradient and the SVG fills
  read from the same tokens — the sky in the gradient and the sky in the scene cannot be
  two skies. Light is midday; dark is dusk, with the jetty the one lit thing. An earlier
  attempt mixed a fixed sky into `--landing-page` and put the section lead at **1.1:1**;
  it is 6.7:1 and 6.3:1 now.
- **`shared/tagIcons.tsx` is the one place a code becomes a glyph**, for three chip rows:
  trip-style tags (`/setup`), readiness categories (`/readiness`) and expense categories
  (`/split`, `/costs`). Every glyph is `aria-hidden` and every chip keeps its word — the
  icon is a second channel for scanning, never the answer. Two of the three vocabularies
  are **Python tuples**, so `tests/test_icon_tables.py` is what keeps the tables
  exhaustive; a Vitest test cannot read `checklist.CATEGORIES`, and a category added there
  without a glyph would ship wearing the fallback with nothing to say so.
  `religious_sites` is `Bell`, not `Church`: the label is "Temples & shrines", the pilot
  destination is Taipei, and lucide has no torii. **Table cells stay plain** — an icon on
  every row of a dense table is weight, not help.
- **`shared/dates.ts` owns the calendar arithmetic**, in UTC, and `spanDays` counts **both
  ends** because a pace does: the balanced five-day pace recommends the 1st to the 5th. Off
  by one there and `/stay`'s custom range either refuses the app's own recommendation or
  allows a sixth day the optimizer was never asked to fill. It is a module rather than
  locals in `StayPlanner` because a file that exports a component may not also export
  helpers — and because a cap is worth testing directly rather than through a render.
- **`.setup-group` is a named group of controls, and `.setup-hours` was already one.**
  Step 2 asks "When are you travelling?" and also holds the flights either end and where
  you are sleeping; those topics were separated by nothing but proximity. Four
  `<fieldset>`/`<legend>` groups now, reusing the pattern rather than inventing one. The
  three `.setup-fields > …` rules are extended to reach inside a group, since wrapping
  changed what "direct child" means — miss that and every label inside a group loses its
  layout.
- **`--trip-bar` is the top bar's height, and a sticky control must rest below it.**
  `.trip-bar` is `sticky; top: 0; z-index: 30`, so anything else that sticks near the top
  parks *inside* its 45px and behind it — covered, and untappable where they overlap,
  which is what happened to the shortlist handle. The number is **measured**: reasoning it
  out from the padding gave 43 against a real 45, which cleared by two pixels and would
  have misled the next thing to use it. Re-measure at 390px before changing the bar's
  padding or type.
- **A wide table may stop being a table on a phone, and `.timeline-table` is the one that
  does.** The generic rule gives every wide table its own horizontal scroller, and for the
  reconciliation table that is right. Six columns of timetable at 390px was not: the owner
  could not see a whole row. Stacking one means undoing three things the column layout
  supplies — cells are `text-align: right`, each draws its own dashed rule, and `td + td`
  adds a 14px gutter — and avoiding two traps: `align-items: baseline` pads every grid row
  to align baselines across columns, and `.money-table tr.timeline-day-start td` sets
  `padding-top` at a higher specificity than a plain `.timeline-table td { padding: 0 }`.
- **`--tab-bar` is the one place the bottom bar's height is written**: 56px of target plus a
  1px top border. Three rules depend on it — the bar, the sticky setup actions that sit on
  top of it, and the padding that keeps content clear — and as three literals they were
  already 1px out of register.
- **No touch control may render below 16px, and the rule that enforces it is `!important` on purpose.**
  iOS Safari zooms the whole page when a focused input's text is under 16px and never zooms back. Nine
  rules in `shell.css` set a control to 12, 14 or 15px, all class-scoped, and `shell.css` is imported
  after `tokens.css` — so a bare element selector loses twice over. It is a floor, not a style.
- **Prose on the stage screens takes `--measure-body`, the same cap the landing page already had.**
  `.stage-main` and `.stage-card` have no `max-width`, so a paragraph ran the full 1130px of card at
  1440 — about 140 characters against the ~75 that note gives as the limit. `max-width` only ever
  narrows, so it is a no-op inside a narrow grid cell and on a phone. Do not write a measure by hand
  and do not write one in `ch`; the note above `--measure-body` explains what that costs.
- **`.setup-primary` and `.primary-link` go full width and 48px tall on a phone**, which is Fitt's law
  in a one-column layout — the primary action becomes the widest thing in the card. `.setup-actions`
  is additionally sticky above the tab bar, and **only there**: setup is the one linear screen, and a
  permanent action bar on a board or a report claims a primary action it does not have.
- **The phone and the desktop get *different* navigation, and only one of them is ever in the DOM.**
  `AppShell` renders the sidebar above 860px and `<StageTabs>` below it, chosen by `useMediaQuery` —
  not by CSS — because rendering both puts two `aria-current="page"` claims in one document, which is
  the exact defect `navSemantics.test.tsx` exists to catch. On the phone the sidebar *is* the More
  sheet and appears only while it is open, so the tab bar and the stage list are never both present.
  `useMediaQuery` answers `false` without `matchMedia`, so the node test environment renders the
  desktop shell; assert the phone surface through `StageTabs.test.tsx` rather than by stubbing globals.
  Keep `PHONE` in `useMediaQuery.ts` equal to the 860px in `shell.css`.
- **A tab may be current for a route it does not link to, so the tabs use `Link` and not `NavLink`.**
  `NavLink` derives `aria-current` from its own route match and overrides the prop, which silenced the
  Money tab on `/split` — the one case the feature exists for. The four `covers` sets must stay
  disjoint, or more than one tab claims the page.
- **`stay`, `evidence`, `revise` and `split` never report `done`** — only the five gate keys do, as
  `stages.ts` says. Anything deriving "the first unfinished stage" from `state !== "complete"` will
  therefore stick on `stay` forever; `StageTabs.buildTarget` reads `journey.next` instead, which is the
  same answer `/` redirects to.
- **There are two build paths and they must do the same work.** `/optimize`'s
  `autoResolveAndGenerate` collects route evidence before asking for a timetable;
  `StayPlanner`'s "use these dates" did not, so a first build measured no leg, every place
  came back `ROUTE_UNVERIFIED`, and the screen said "the route and travel time are not
  verified" — reported twice, once against a credential-less worker and once against this.
  Diagnose it from the queue's *ordering*: a `generate_plan_preview` row earlier than the
  trip's first `route_snapshots.retrieved_at` means something built a plan before any route
  existed. `PLAN_STAGES` carries `routes` because the call is there; adding one without the
  other is the fiction `BuildStages` exists to refuse.
- **Any rebuild that writes setup must re-run `discover_places` first.** Discovery stores
  the setup hash it ran against, so moving a date stales the found places and the rebuild
  refuses `discovery_stale` before doing any work — which is what "Add a day and rebuild"
  did. It is free: the provider cache is keyed on the destination alone, so the run
  rebuilds from disk with no network call. `StayPlanner` has done this since 2026-08-08;
  `addDayAndRebuild` is the second site and there will be a third.
- **A label is a promise, and "Build the plan" on `/places` went to "Where to stay".** The
  destination is right — the journey is places → stay → build and skipping `/stay` skips a
  required stage — but the button named the stage it *unlocks* rather than the one it
  opens, and arriving at a form where nothing builds was reported as a "dead air screen".
  It reads `stage_stay` now. Reading the source for that report found a *different* real
  blank page (`StayPlanner` returned null on an empty recommendation list) and fixing it
  did not answer the complaint: **when a symptom is described from the outside, reproduce
  it in a browser before deciding which bug it is.**
- **A query derived from the plan must be invalidated wherever the plan is.**
  `comfort_tradeoffs` is computed from the stored variant, and only `acceptAll` refreshed
  it — every build path invalidated `plan_preview` and left the report holding whatever it
  said *before* a plan existed, which is "nothing exceeds". Two things then vanish
  together: `ComfortTradeoffs` filters to zero rules and renders nothing, and
  `overBudget` is empty so the accept control never appears. The screen becomes a refusal
  naming a comfort budget, a panel that has disappeared, and no button — reported by the
  owner as "I don't know what to do next, cause it no button anywhere". `invalidatePlan()`
  invalidates the pair together so a new build path cannot refresh one and forget the
  other. **Grep for `plan_preview` before adding a build path**, and treat a control that
  is missing rather than disabled as a data-staleness question first.
- **A message and the control that resolves it must render on one condition.** The comfort
  note needed `comfortOnly` (from the stored variant) and its button additionally needed
  `overBudget` (from a live query) — two sources that diverge, so the note could appear
  alone. Gate them together, and where there is genuinely nothing to agree to, offer the
  rebuild that clears a variant lagging behind an agreement.
- **Extending a page needs the updater form.** `dealMore` read `setShown(LANE_PAGE)` —
  assigning the value it already held — so "Show 20 more from here" recomputed an
  identical window and the deck did not move. A pager that appears to do nothing is
  almost always an assignment where an increment belongs; the catalogue's own pager in the
  same file has always been `shown => shown + CATALOG_PAGE`.
- **Do not turn an outage into a finding.** A failed paid photo ask has three causes and
  they are three different claims: `place_not_in_provider` means Google has none either,
  `provider_unavailable` means Google was never reached, and anything else is neither. One
  blanket "no photograph could be found" asserts a fact about the place out of a network
  error. `photo_ask_none` / `photo_ask_unavailable` / `photo_ask_failed` keep them apart,
  and the pre-press line stays `photo_none_kind`, which is about *free* sources only.
- **Thin photo coverage is usually the data, not a defect.** Measured 2026-08-28: Zurich
  75% of summaries carry an image, Interlaken 43% — and 14 of Interlaken's 16 imageless
  places **have no Wikidata entry at all**, so there is nothing to fetch. Check
  `cache_version` before suspecting staleness (all were current), and do not loosen
  `providers.photo_depicts_place` to raise the number: that filter is why a photograph of
  a bus stopped being offered as a photograph of a hill.
- **Before adding a control to `/optimize`, grep for `autoResolveAndGenerate.mutate()` and count the
  call sites.** That control has been wrong three times, each time a second button running the same
  mutation under a different label.
- **Grep the landing for `ILP`, `Branch`, `Optimality` and `Solve Time` before believing it describes
  this optimizer.** `optimizer.py` is a greedy baseline plus an insertion search. Invented solver
  claims have been removed twice and returned twice; they read like competence, which is what makes
  them hard to catch.
- **Press buttons; do not drive the API.** A hand-rolled call sequence left every variant
  `unavailable` while the real button worked — `autoResolveAndGenerate` orchestrates four steps as
  one. An audit that drives the API will declare the app broken and be wrong.
- **A screenshot is evidence about what someone sees; a measurement is evidence about what was
  measured.** When they disagree, the screenshot is describing the product.
- **Reproduce a reported symptom before deciding which bug it is.** "A dead air screen when
  I click build the plan" was read from the source as `StayPlanner` returning `null` on an
  empty pace list — a real blank page, found and fixed, and *not the report*. Driving the
  app at 390px answered it in one click: the button said "Build the plan" and opened "Where
  to stay", a populated form where nothing builds. Two real bugs, one reported, and reading
  found the wrong one first. Source reading generates candidates; only the running app says
  which candidate the owner met.
- **A measurement that a mechanism works is not evidence that the behaviour is wanted.**
  The card-wait bound was measured firing correctly on the deployment — three waits, two
  released at the ceiling — and reported as verified. It was: the mechanism worked. The
  owner rejected the behaviour the next morning. Separate the two claims when reporting,
  because only the second is what was asked for.
- **"Verified" means the thing that broke was exercised.** Two claims this month were
  reported as verified and were not: an advisory-lock probe that checked the function
  overload with a stand-in string while the real key carried a NUL byte Postgres refuses,
  and a route-coverage story asserted from the code that the stored rows then contradicted.
  Both were live checks of the wrong half. Name what was exercised and what was not.
- **Never print a placeholder as if it were a finding.** Four of the swipe card's fact rows originally
  could not vary: `ranking.py` fixes `feasibility.state` before the optimizer runs, formerly fixed
  `reward_effort = 10.0` against a weight of 20, seeds every card's `cons` with three pipeline-state
  codes, and cost/reservation had no data path at all. `/places` showed it worst — its
  caution column was `cons.slice(0, 2)`, so every place in the catalogue carried the same two strings.
  A row with one possible value cannot separate this place from the next, and it teaches the eye past
  the rows that can. `reward_vs_effort` now varies from category experience per estimated visit minute,
  is labelled `Value for time`, and declares `effort_state: visit_time_estimated`; walking, transfers,
  cost and fatigue remain optimizer evidence. `shared/cards.ts` holds the guards; `WF-005` asks for
  these rows, so they are kept where they can answer and dropped where they cannot.
- **`Thinking` claims no milestones of its own — everything above it does.**
  `autoResolveAndGenerate` awaits four calls in order, so each one returning is a fact the
  page already holds, and `BuildStages` marks a stage done on that and nothing else. Never
  advance it from a timer: a green check that means "probably by now" is the same defect as
  printing a placeholder as a finding. The long `generate_plan_preview` really has no
  milestones, so `Thinking` stays inside that stage where a rotating line and an elapsed
  counter are the honest thing to show.
- **A queued operation describes its own wait, or nothing can.** `jobs.REPORTS_PROGRESS`
  names the operations `run_one` hands a `progress` sink to; they write a **count** into
  `jobs.progress`, `job_status` carries it, and `rpc`'s `onProgress` gives it to the page.
  A count and not a label, because the browser owns the words in both languages. Zero is
  written before the work starts and that is load-bearing: it is the only thing separating
  "queued, nobody is running this" from "a worker has it". Do not add an ignored `progress`
  argument to an operation that has no milestones — that is a claim it can say where it is.
  Clear the count on `fail` and `reap_stale`; a retry starts over, and 3 of 5 would describe
  work the new attempt has not done. Report a stage when its call **stops running**, not
  when it succeeds — a failed Overpass block has still been passed, and `incomplete_blocks`
  is what names it.
- **A day with no places is explained, not suppressed — and the prep evening is not one.**
  Reported as "2 duplicate day plans, day 7 and day 8". They were not duplicates and the
  plan was not wrong: the owner's Porto trip chose 22 places, **all 22 were scheduled**,
  and the trip ran two days longer than they fill. `include_operational_timeline` still
  emits breakfast, free time, lunch, free time and dinner for such a day, so two
  consecutive days rendered the same rows with no stops between them and read as a copy.
  The rows are right and stay — 10-01 carries the real checkout and airport run — so what
  was missing is `day_has_no_places` saying why the day looks like that. Keyed on the day
  having no `visit` item, and **excluding the prep evening** via the same
  `prepFirst && dayIndex === 0` test the label uses: that block never carries places by
  design, is named rather than numbered, and telling the owner their places fit elsewhere
  would describe it wrongly. Diagnose a "duplicate day" report by counting chosen against
  scheduled before looking at the optimizer.
- **`/itinerary` shows the same photograph the swipe card showed, from the free store
  only.** `DayStops` built its own URL from `osmPhotoUrl(item.photo_reference)` — the
  OpenStreetMap tag alone, the narrowest of the three sources `galleryFor` assembles — so
  a place pictured from Wikidata or Commons had a picture on `/places` and none here.
  `ItineraryPage` reads `list_place_summaries` once per trip (`staleTime: Infinity`) and
  passes a `photoOf` callback, the same shape as `nameOf` and `coordsOf`, so `DayStops`
  stays presentational. **The paid overlay is deliberately unreachable from this screen**:
  `enrich_place_card` is session state in `PlacesPage`, never persisted, so there is
  nothing here to read and nothing to spend.
  Two consequences worth knowing. A stop can only show what the free store already holds,
  and the store only holds what something fetched — a place chosen from the list rather
  than dealt by the deck may have no summary at all, which is also why it had no
  swipe-card picture to mirror. And **a geosearch photograph gets no row thumbnail**: the
  row is always on screen and has no space for a caption, so an undisclosed picture of
  somewhere *near* the stop would be exactly the quiet claim `photos_are_nearby` exists to
  prevent. Those still appear full size inside the expanded detail, with the sentence.
- **Any new remote image needs adding to the capture freeze list in `web/src/main.tsx`.**
  It blanks `.place-deck-photo img`, `.place-about-photo`, `.place-insight img` and now
  `.day-stop-thumb`, `.day-stop-photo img`. Third-party pixels re-encode — a Wikimedia
  thumbnail failed this gate at peak 28 with nothing in the repo changed. The day-stop
  selectors were absent for as long as the only pictures there came from an OpenStreetMap
  tag the fixture trip did not carry; the omission cost nothing until the pictures arrived.
- **`PHOTO_THIN_AT` is "one or none", written once in `shared/photos.ts`.** The detail
  panel's `thinlyPictured` always meant one; the deck offered its buy button only at zero,
  because the control lived inside the branch that draws a map where a photograph should
  be. A single Commons shot of the car park next door is as short of a picture of the
  place as nothing at all. Two literals for one threshold is how they drifted.
- **A swipe card is shown only when its first photograph has painted, and no deadline
  releases it early.** The swipe decision is made on the picture, so a card whose frame
  still says `Loading` is a decision offered on half the evidence. A bound was tried —
  four rotations of the loading line — and measured working on the deployment, and the
  owner rejected it the next morning for doing exactly what it was built to do. **A bound
  is not a fix for slowness; it is a decision about what to show while slow**, and here
  the honest answer is "nothing yet". Answer a slow card by making it not slow: the deck
  warms the whole gallery of the card in front plus the lead image of the next
  `WARM_AHEAD` (4), and `PlacesPage` already has their URLs because it fetches summaries
  ten ahead. Lead images only — six-deep galleries for four upcoming cards is the burst
  Wikimedia answers 429 to. A broken image still releases the card, through `onError`.
- **The deck's buy button has three separate withdrawals, and they sit at different
  layers.** It renders only when `paidPhotoUsd != null` **and** the card is thinly
  pictured **and** the place has no session insight **and** this card's ask has not
  failed. The first is the cap: `paidPhotoUsd` comes from a `paid_check` query, so when
  the month is spent the control is never rendered at all — which means a
  `paid_cap_reached` refusal can never reach the card's own error surface, and the whole
  cap class is handled a layer earlier than the failed-ask handling. The third is a
  purchase already made; the fourth is `photoError`, session-scoped because a busy
  provider is not a finding about the place, unlike the stored `provider_no_match`.
- **A failed paid photo ask is hard to summon, and the rejection rule is where to aim.**
  `providers._best_nearby_match` demands distance ≤1500 m, name similarity ≥0.46 against
  the OSM name *or any of its `names` values*, and a category-to-`primaryType` match; a
  miss raises `ProviderUnavailable`, and an empty result raises `ProviderNoMatch`, which
  `enqueue`-style re-raises after recording the refusal. Both reach the browser as errors.
  Two live attempts on the deployment — an `artwork` with a Japanese-only name and a statue
  whose OSM name is misspelled — **both matched Google anyway**, at US$0.075 each, and this
  database holds **zero** `provider_no_match` rows across every ask ever made. Treat this
  path as test-verified: the money buys a coin-flip, not a confirmation.
- **A touch gesture cannot be verified from here — put its arithmetic in a module.**
  A dispatched `PointerEvent` does not drive this map, and that was checked against the
  deployment on code predating the pinch rather than assumed; cmux says the same, raw
  input injection is `not_supported`. So `shared/pinch.ts` holds the maths and is tested,
  the wheel path is the regression check that `setView` still works, and the gesture
  itself needs a finger on a real phone. Do not claim a gesture is verified because a
  synthetic event returned without error.
- **`document.querySelector(".places-map-svg")` on `/places` finds the *hidden* one.**
  The only map on that screen lives in the shortlist drawer, so while it is closed the
  element is `0x0` — measuring against it sends the viewBox to `-Infinity` and reads as a
  broken map. Open the drawer, or pick the element with a non-zero box.
- **Nothing inside a swipe target may take a pointer.** A place with no free photograph
  used to show a map on its deck card: an interactive surface with `touch-action: none`
  and pointer capture, sitting inside a card whose whole job is to be swiped. Pinching the
  card fought the map under it. It is a `tagIcon` glyph and a sentence now — and it was a
  second copy of the detail panel's map anyway, which is the other half of why it went.
- **A control in the deck acts on the card in the deck, never on `selectedId`.** The deck
  deals from a lane and the list has its own selection; they are usually different places.
  `saveChoice` carries the comment saying so and `onWantSummary` obeys it, but
  `onWantPhotos` was wired as `() => enrich.mutate()` — dropping the `place_id` the deck
  had passed — so **the paid photograph was bought for whichever place the list was on**,
  stored against that one, and the tapped card never changed. Any new `on*` prop on
  `PlaceDeck` takes a `placeId` and the handler uses it.
- **A skeleton is a promise that something is being fetched.** Two placeholder cards sat
  under the discovery stage list from the moment the button was pressed, while the list
  above them said the search had not finished — there is no catalogue to draw a card from
  until `discover_places` returns. Show a skeleton for the request that is actually in
  flight, not for the wait in general.
- **Plan-cost tiers are editable seeds, not forecasts.** `/costs` offers Budget, Value,
  Standard, Premium and Luxury in THB, but selecting one writes nothing; only the explicit
  Save creates or updates estimate rows. Accommodation is per room for two people, the
  other units are per traveller, nights come from setup's travel dates rather than prep
  days, and a zero-count category is omitted. Keep `related_item_id=plan-estimate:<category>`
  as the row identity so changing language or itinerary counts updates one row rather than
  creating another; the localized label is only the backward-compatible fallback.
- **The itinerary dashboard is another view of the active export snapshot, not another
  source of trip state.** It may coordinate day, clock, map pins, timeline, search and
  photo dialog, but readiness remains writable only on `/readiness`, planned money on
  `/costs`, and actual bills on `/split`. A wide screen shows map and timeline together;
  a phone switches between them. Do not duplicate those authoritative boards into it.
- **Give `Thinking` a `startedAt` wherever it can be remounted mid-wait.** It counts from
  its own mount otherwise, and `/places` moves it into the active stage the instant the
  worker first reports — a new position in the tree, so a new mount. The counter reset to
  zero part-way through a 30-90s wait, which is the precise "it looks like it hung" that
  counter was added to answer. It reads off the clock now, initial state included so the
  remount does not flash `0s`.
- **A field added to the setup draft must also be added to
  `StayPlanner.wholeDraftWithDates`.** `save_setup` defaults every field it is not sent,
  so that function rebuilds the whole payload by hand — and a field missing from its list
  is silently reset the moment the owner picks dates from the stay planner. Its own
  docstring says so; `active_start` / `active_end` were nearly the first casualty.
- **The day's planning window is the owner's answer, not a literal.**
  `_optimizer_input` hardcoded `08:00`–`22:00` for every trip on earth, which is the same
  invention `WF-046` refused for opening hours. Setup asks; `setup.DEFAULT_ACTIVE_START` /
  `DEFAULT_ACTIVE_END` hold the old pair for a draft saved before the field existed, which
  is what keeps the 27 regressions byte-identical. Arrival and departure still tighten
  their own day — a flight is a fact, active hours are a preference.
- **`--approve` writes the baselines and leaves `screen-current` alone**, so running
  `check_screen_baselines.py` straight afterwards diffs the approve run against whatever
  capture happened to be sitting there and fails with percentages that look alarming and
  mean nothing. Approve, then capture once more without `--approve`, then check. Measured:
  a stale comparison reported `split` at 15-20% drift on code that had not touched it.
- **Light is the default theme regardless of the device.** `ThemeProvider.initialTheme`
  consults the stamped root, then `localStorage`, then answers `light` — it does *not* read
  `prefers-color-scheme`, and neither stylesheet contains such a block, so
  `[data-theme="dark"]` is the only path to dark. It remains a default and not a lock: the
  toggle still works and is still remembered.
- **A screen-baseline run must reuse one Chrome profile *and* be handed the trip's owner token.**
  Trip ownership is a localStorage token. Reusing one profile stops the images disagreeing with each
  other; it does not make the run an owner, because a throwaway profile mints a *new* token on load and
  `list_trips` filters on it. With only the first half fixed, **52 of the 56 captures were the
  unknown-trip recovery screen** — every stage route, both viewports, both themes, both languages — and
  the gate passed on all of them, because an error page compared against an error page is clean. It sat
  green across three handoffs while covering nothing, and "the screen baselines are approved" was
  reported as an achievement. `--owner` is therefore **required**, `capture_screen_baselines.py` puts it
  on the URL as `baseline_owner`, and `web/src/main.tsx` writes it to `localStorage` inside the same
  capture-mode block that already reads `baseline_theme`. Get it with
  `sqlite3 data/tourist.sqlite3 "select owner_token from trips where id = '<trip>'"`.
  Capture mode suppresses the one-time plan-ready dialog so the itinerary baselines cover the dashboard
  beneath it. **Open changed images before approving them** — that rule already existed and would have
  caught this on any of the three occasions it was not followed. A blank-detector over the capture set
  is two lines of Pillow and is worth more than reading the percentages.
- **The visible build stamp is volatile capture data.** It remains visible in the real
  interface, but `data-volatile="build"` freezes it under `baseline_theme`; otherwise every
  rebuild changes unchanged `t900-` screens by about 0.117% and forces unrelated approvals.
  **`TripNow` carries two wall-clock countdowns and both are `data-volatile="countdown"`** —
  "Departs in N days" and the "Next · 19:00 · in N days" line below it. They drifted the
  itinerary baselines a little every day and forced re-approval on a schedule nobody chose.
  Freezing only the first left them still drifting, which the recaptured image showed and
  the reasoning had not: **open the changed capture before believing a freeze worked.** On
  the departure line the whole phrase is frozen rather than the number, because `copyFormat`
  returns one interpolated string and splitting a sentence in two languages to hold three
  characters costs more than that line's width in the diff; the next-action line freezes
  just the gap, since the tag and clock time beside it are stable.
- **One `check.py` at a time — it takes `.check.lock` and refuses a second.** The stages are
  not independent of the working tree: the baseline stage compares `screen-current`, which is
  shared state on disk, so two interleaved runs produced `approved: 2 · compared: 1` and a
  stage that failed exactly like real drift on unchanged code. The tool that runs these
  commands issues parallel Bash calls in one shell, so this was reachable by accident. It
  refuses rather than queues, because a second run is nearly always a mistake and a silent
  ninety-second wait looks like a hang. Remove the lock by hand after a crash.
- **A test that exercises a gate's failure path must capture its output.** The
  `FAILED: 1 screen(s) drifted` line inside the *unit-test* stage was
  `tests/test_screen_baseline_gate.py` proving the gate fails when it should, and it read as
  a real failure inside a passing suite for long enough to be written into three handoffs as
  a trap. Assert the exit code; let the stage that runs it for real own the prose.
- **The phone capture's viewport is ~745px tall, not the 844 in its filename.** Headless Chrome sizes
  the *window*, and its chrome eats the difference, so a 500x844 image carries about 99px of dead white
  below the page — visible in a dark-theme shot, where the band stays white. A `position: fixed` bottom
  bar therefore lands at y≈745 in the image and is correctly pinned all the same. Do not "fix" it.
- **Before penalising an `avoid` chip in `ranking.py`, check the vocabulary.** None of the five is a
  word the place vocabulary uses (`AVOID_TAGS ∩ candidate tags = ∅`), so a deduction keyed on
  candidate tags is dead code that looks like a feature. They reach the engine as optimizer
  thresholds; `tests/test_avoid_tags_reach_the_planner.py` and `tests/test_ranking.py` pin both halves.
- The web runtime is fixed at **six dependencies** (`WF-026`) — the rule GSAP was refused under.
- Only assets actually used are vendored; the unDraw licence forbids pack redistribution.
- Complete a slice vertically, with its own runnable check, before starting the next.

## Architecture

There is one interface, the React webapp, reached two ways: `localserver/` (stdlib
`ThreadingHTTPServer`) locally, and `api/rpc.py` as a Vercel function when hosted. Both share
`static_response` and both dispatch through the same allowlist. The Streamlit POC that proved the core
works was deleted at slice S6 on 2026-08-04. The design decisions are locked in `.wayfinder/tickets/`
(see below) — the constraints in this section are decisions, not incidental structure.

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
- `travel_planner/destinations.py` (country/city) and `costs.COMMON_CURRENCIES` are picker
  convenience only. Both dropdowns take a typed value, so a destination or currency absent from the
  table stays reachable — the worldwide acceptance check requires it. A city name is the geocoder
  query, so it is never localized; localizing it would let a language switch change which place is
  searched.

### Everything crossing a boundary is a frozen, hashed snapshot

`core.freeze_snapshot()` canonicalizes a mapping (sorted keys, no NaN, UTF-8) into
`FrozenSnapshot(canonical_json, sha256)`. Every domain record wraps its payload in one, and every
`store.py` read re-verifies the hash before returning. Consequences:

- `freeze_snapshot()` rejects secret-bearing keys (`api_key`, `*_api_key`, `access_token`, passport and
  booking document keys — see `FORBIDDEN_SNAPSHOT_KEYS`) anywhere in the tree. Snapshots are the place
  secrets could leak into SQLite and exports; that guard is why they can't.
- Hashes are the staleness mechanism, not timestamps: discovery stores `setup_sha256`, and ranking or
  optimization refuses to run when it no longer matches the confirmed setup.

### Pipeline: setup → discovery → ranking → optimization → activation

Each stage is gated on the previous one having a matching hash (`_current_choice_inputs`).

1. **Setup** — `setup.build_setup_payload()` normalizes owner/member preferences into a draft;
   nothing downstream runs until `confirmed`.
   Setup and the optimizer use different accommodation vocabularies — `unknown`/`not_booked`/`booked`
   versus the `unbooked` that `optimizer._hotel_recommendation()` and the frozen fixtures test for.
   `_optimizer_input` translates at the boundary; before it did, hotel-area recommendations silently
   never fired for any app-created trip.
2. **Discovery** — `providers.OpenStreetMapProvider` (Nominatim + Overpass, free) → `discovery.build_candidate_catalog()`
   A dense city takes about 34 s of Overpass time, so the query declares `[timeout:90]` and the socket
   allows 105 s; the earlier 25 s budget failed every Taipei attempt. The endpoint grants 2 concurrent
   slots and answers 504 immediately once they are spent, so a burst of retries reads as an outage that
   is really self-inflicted — space them.
   **Discovery is two Overpass requests, not one, as of `WF-048`** — indexed `["wikipedia"]` landmarks,
   then the balanced family baseline — and each is **best-effort**, failing only when both come back
   empty. As one script Tokyo returned nothing at all: the unindexed baseline scanning the clamped
   0.60-degree window exceeded `[timeout:90]` at 91 s and 93 s, and **Overpass has no partial result**,
   so it discarded the indexed half that had succeeded. Split, Tokyo yields **3082 items**. Three
   consequences. The baseline gets **`[timeout:60]`, not 90** — a browser constraint, since two requests
   run back to back and `web/src/api/client.ts` aborts an RPC at 120 s (Tokyo measured 85.8 s at 90 s
   each). There is a **3 s pause between the blocks**, because fired immediately the second came back
   `Provider HTTP 504` on the 2-slot budget — losing the baseline to a rate limit rather than a timeout,
   which hurts a *small* city most, where little carries a Wikipedia article. And a catalog missing a
   block is **`stale`, never `verified`**, applied after the cache branches so a partial payload is not
   laundered into `verified` on the next read; `coverage.incomplete_blocks` and `known_gaps` name which
   half is missing.
   **A 504 is not always a spent slot.** `overpass-api.de` balances across backends and an unhealthy one
   answers 504 in *seconds*. Measured 2026-08-08 on Singapore: both blocks 504 at 9.0 s and 9.5 s with
   both slots free, and the identical query returned 200 a minute later — an empty catalog for a fault
   that had already passed. `_attempt_block` therefore retries **once**, and only when the failure was
   **fast** (`FAST_FAILURE_SECONDS = 20`) and an HTTP 5xx. That distinction is the whole safety of it: a
   block that died at 90 s died of its own declared timeout, and asking again would spend another 90 s
   to fail identically. A `remark` is never retried — that is the query engine reporting its own
   timeout, not a gateway. `DISCOVERY_BUDGET_SECONDS = 100` is a deadline shared across both blocks and
   their retries, which is what keeps the pair inside `client.ts`'s 120 s abort however the retries
   fall. Do not raise it without moving that abort first. `out center qt` with a 500-record limit truncates in quadtile
   order, so a big city's catalog can miss its landmarks; see the walkthrough notes in
   `artifacts/validation/2026-07-29-slice5-6-evidence-notes.md`.
   normalizes and dedupes into provider-neutral candidates with an explicit status
   (`verified` / `stale` / `unavailable` / `error`). Raw responses live in the `provider_cache` table
   (7-day TTL, keyed by provider + request fingerprint); an expired entry may back a visibly `stale`
   result but never a `verified` one. Inject a fake via `PlannerActions(path, place_provider=...)` —
   that is how every test avoids the network.
3. **Ranking** — `ranking.build_ranking()` scores cards on the fixed 30/20/20/10/15/5 weights in
   `FORMULA_WEIGHTS`, with protected exploration slots and per-card explanations. Deterministic.
4. **Optimization** — `optimizer.optimize_trip()` takes one complete snapshot and returns three
   variants (`best_balance`, `relaxed`, `more_highlights`), each independently rechecked by
   `optimizer.validate_variant()` — never trust solver construction. Same input + same
   `OPTIMIZER_VERSION` must yield the same proposal, asserted via `deterministic_signature`. With no
   trip dates it returns `mode: "stay_recommendation"` instead of a timetable. At the time limit it
   returns only a labelled valid incumbent, never a partial schedule.
5. **Activation** — `activate_plan_preview()` refuses unless the preview's `input_sha256` still
   matches current choices AND the variant is `status == "ready"` with `validation.valid`. It then
   writes an immutable plan version and deletes the preview.
6. **Readiness** — `checklist.propose_items()` generates a city-independent board from setup, choices,
   and verified facts; `diff_proposal()` previews additions, removals, and deadline moves;
   `apply_checklist_proposal()` writes them, dismissing rather than deleting so nothing silently
   disappears. No provider supplies official entry rules, so a generated item stays
   `verification_needed` with no `source_url` until the owner records one — the board names what to
   verify and against which authority, and never asserts a legal conclusion. Requirement level and
   evidence state move independently, and `validate_item()` refuses a verified `required` item with no
   responsible authority type. Board items are the one mutable record type; readiness warnings are
   explicitly non-blocking (`blocks_itinerary` is always False).

**Transit routing arrived on 2026-08-05 (`WF-038`) and changes what the optimizer can plan.**
`travel_planner/transit.py` holds `TransitGraph`, the walking constants and **one** Dijkstra;
`gtfs.TransitFeed` builds one from a timetable zip and `transit.graph_from_osm()` from an
OpenStreetMap `route=subway` relation. `providers.GtfsTransitProvider` and `providers.OsmMetroProvider`
wrap them, both `mode: "transit"`, both priced at US$0.00 — priced rather than omitted, because an
unpriced operation raises. `actions.refresh_transit_routes` stores transit legs **beside** the walking
ones: the store keys a snapshot by (origin, destination, **mode**) and the optimizer takes the shortest it
holds, so short hops keep their walk. `PlannerActions._default_transit_provider` prefers a GTFS feed at
`TOURIST_GTFS_PATH` when one exists and falls back to OSM, which is weaker and says so — GTFS edges carry
`basis: "timetable"`, OSM edges `basis: "nominal"` with ride time from distance at 33 km/h and wait from
an assumed 6-minute headway. Taipei's own GTFS is **not sourced**: TDX needs a Taiwan mobile number.

Three consequences worth knowing. **A transit route is `status: "estimated"`, never `"verified"`**, and
three sites used to admit only `verified` — `actions._optimizer_input`,
`optimizer._routes_between` and `optimizer._best_inbound_route`. All three now admit `estimated` when
`allow_provisional_assumptions` is set, which only `explore_first` sets; a `ready_to_schedule` trip is
unaffected and `ROUTE_UNVERIFIED` stays fatal for it. The precedent is `_planning_fact`'s own docstring —
"a visible assumption allowed only for an Explore preview". **`walking_minutes` excludes the ride**, which
is the whole point: `maximum_walking_minutes_per_leg` measures it, so a 43-minute ride reached by a
2-minute walk passes a 25-minute cap no walk of that distance could. And **`refresh_routes` sorts pairs
nearest-first**, because the 60-per-run cap bites long before 41 places' 1640 pairs and a missing route
falls back to a pessimistic estimate — sorting by `place_id` spent 340 free calls on pairs the plan never
used and produced phantom 68-minute walks.

**Opening hours are per-day as of 2026-08-06 (`WF-041`).** `opening.common_interval` takes the overlap
across the days a place is **open** rather than refusing the moment one trip date is shut, and returns
`open_dates`; `_optimizer_input` puts those in the fact's `applies_to_dates`; `optimizer._open_on()` is
consulted by `_earliest_visit_start` and `validate_variant`. A fact without `applies_to_dates` applies
everywhere, so frozen fixtures are untouched. Before this a venue closed on one trip day was
unschedulable on **every** day — five of thirteen pilot landmarks were lost that way.

**A flight day's window holds its own logistics as of 2026-08-06 (`WF-042`).** The last day owes a fixed
suffix — `optimizer.DEPARTURE_LOGISTICS`, 45 + 45 + 90 = **180 minutes** of checkout, transfer and airport
— so `_optimizer_input` opens that day at `min("08:00", departure_time − DEPARTURE_LOGISTICS_MINUTES)`.
That constant is exported for exactly this reason and is the **one** source both sites read. Before it, a
morning flight made the departure day infeasible, and because `_greedy_baseline` accepts a placement only
when the **whole trip** builds clean, one unusable day emptied the entire plan — 13 visits to 0, every
landmark blamed on `PLAIN_WALK_THRESHOLD`. Two things follow. `_build_day` now refuses only when
`sequence or items`, so an empty day cannot veto the others. And **do not fix a window problem in the
builder**: moving `current` without moving `usable_windows` scheduled all 13 visits and then failed
`validate_variant` with `OUTSIDE_USABLE_WINDOW`, because the validator judges every item against the
snapshot's window and is meant to. `_skip_reason` is also not a measurement — it returns
`PLAIN_WALK_THRESHOLD` whenever a place was skipped and that threshold merely exists, so read
`_build_schedules`' own `hard_errors` when diagnosing. **No test set `include_operational_timeline`**
before this; it is `True` for every trip `actions.py` builds and absent from all 27 fixtures, so arrival
transfers, check-in, meals and the airport run were exercised only by the live pilot.

**Every variant gets its own time budget as of 2026-08-06 (`WF-043`).** `optimize_trip` used to compute
**one** absolute deadline and hand it to all three variants, so it was consumed in order and whichever ran
last inherited the remainder — measured on the pilot at 20.7s + 10.4s of a 30s budget, leaving
`more_highlights` already past it. It returned in 0.04s having placed **nothing**, was labelled `ready`
and `valid` because an empty schedule violates nothing, and reported
`objective_improved_or_equal_to_greedy: false` beside a `greedy_baseline` holding all 13 visits. The
deadline is now per variant, so worst case is `len(VARIANT_CONFIGS) × time_limit_seconds` and **a full
proposal takes ~52s, not ~31s** — that is the third variant doing its 21s of real work. Separately,
`_greedy_sequences` is split out of `_greedy_baseline` and `_insertion_search` **falls back to it** when
the deadline does fire: greedy sweeps every candidate and has no time limit, so it is a floor the search
can always afford, and returning worse than a schedule already in hand is never right. Two things not to
misread: `deterministic_signature` hashes the **input**, so it cannot detect a load-dependent output; and
an expired budget legitimately yields 0 visits where greedy's only schedule carries a comfort violation,
because `comfort_violations` outranks `experience_value` in the objective tuple — that ordering is
`WF-039`'s question.

**Assumed windows are batched and the cost trade is reported, not taken, as of 2026-08-07 (`WF-047`).**
`google_places:search_text` is **US$0.025 a place** and is the only paid step that scales with trip size —
40 places is US$1.00 against a US$10 cap. There is **no cheaper verified path**: Text Search takes one
query per place and cannot be batched, and the cheaper `places/{id}` Details endpoint needs a Google place
id the catalogue does not hold. So US$0.025 is the floor for evidence.

`OpenAIOpeningWindowProvider.windows()` batches the *assumption* instead — one request for up to
`BATCH_SIZE = 20` places, matched back by an **echoed integer index**, never by name, and charged to the
ledger **once per request**. Batching measured **more** accurate, which was not expected: 8 of 11 exact on
both ends against 6 of 12, and one overshoot of real closing against four.

**Do not add a cost threshold that switches automatically.** Verified and assumed are different kinds, not
different prices: an assumed fact is read only under `allow_provisional_assumptions`, so on a
`ready_to_schedule` trip a cost-triggered switch spends money on a fact the optimizer ignores.
`actions.opening_evidence_options` prices both paths and carries the cheap one's measured error rate
*beside* its price, and reports `assumed_is_usable: false` where the trip would not read it.

**A venue's own page is read for dated closures as of 2026-08-07 (`WF-044`) — and it is never a fact.**
An opening fact is a **weekly pattern**, so nothing stored can say "closed 1 January", and the trip spans
31 December and 1 January. `providers.VenueNoticeProvider` fetches the landing page and quotes any dated
visitor closure; `actions.scan_venue_notices` stores it as `place_evidence` of kind `venue_notice`.
**`_optimizer_input` does not read that kind** — there is no code path from a notice to the optimizer, so
a false one cannot delete a landmark. That is the bar the ticket set and it is met structurally, because
`WF-046` measured a model inventing 2 of 7 closures.

Two guards, both load-bearing. **The quote must appear verbatim on the fetched page** — `quotes_the_page`
forgives only whitespace, never case or punctuation, since a paraphrase is exactly what cannot be checked
against the source. **No page, no answer**: a failed fetch raises rather than letting the model recall.
Measured on the pilot: 8 sites read, 1 notice found (Huashan 1914's typhoon hours change, the genuine
one), 4 skipped for having no website, 1 unreachable — and **Sun Yat-sen reported nothing** although its
page really does contain `休館公告`, because that notice is about its website, not the hall. This reads
the landing page only; the three sites whose hours sit two hops into a government CMS are unchanged.

**An activated plan is checked against today's evidence as of 2026-08-07 (`WF-045`).** Every other gate
guards the **forward** direction — activation refuses on a stale preview, discovery and ranking on a stale
setup hash — so nothing noticed when evidence *improved* underneath a live plan. One paid opening-hours
lookup left a visit at 17:17–19:32 against real hours ending 17:30 while the stored variant still said
`validation.valid: true`, because that flag was computed at build time and never recomputed.
`actions.active_plan_drift` compares the activated version's own stored `optimizer_input` hash against the
current one, and **re-runs `validate_variant` only when it moved** — the hash says *whether*, the validator
says *what*, and gating the second on the first is what keeps this off the churn path. It **reports and
never repairs**: `plan_versions` is append-only and the owner may have printed the itinerary, so
regenerating is an offer on `/itinerary`, not a side effect of reading. `claimed_valid` and `still_valid`
are both returned so they can be seen to disagree.

**A model may supply the assumed opening window as of 2026-08-07 (`WF-046`) — and nothing more.** The app
always guessed when a place had no verified hours: `_optimizer_input` emitted a flat **09:00–21:00** for
every place on earth. So the question was never evidence versus a guess, it was *which* guess, and the
constant is the worse one — the pilot scheduled a visit at 17:17–19:32 against real hours ending 17:30 and
passed validation. Benchmarked against verified ground truth for all 13 places: the model's window ends
after real closing 5 times by **30–60 min**, the constant 6 times by **180–270 min**.

Five rules not to relax. **The status stays `assumed`** whichever guess fills it — only `source` differs
(`model_recalled_window:<model>`), so nothing is upgraded. **A place with verified hours is never asked
about.** **A window spanning 20 hours or more is discarded** (`DEGENERATE_SPAN_MINUTES`): `gpt-5.6-luna`
answered `00:00–23:59` for Huashan 1914, and a non-answer that permits *more* than the constant inverts
the reason for asking — the bar sits above sixteen hours because temples really do open 06:00–22:00. **`closed_weekdays` is not requested at all**: the same benchmark got 7 closure claims of which
**2 were invented** (Huashan 1914, Taipei Zoo), a false closure silently drops a place, and 29 December is
a Tuesday — do not add the field back without re-running the benchmark. And **`_optimizer_input` never
fetches**; it runs on every read, so the window is read from storage or the constant stands. Recall cannot
reach a *holiday* closure at all — that is `WF-044` and needs a fetch.

**A comfort tradeoff can be accepted as of 2026-08-07 (`WF-039`), and the acceptance is a number.**
`comfort_acceptances` (schema **14**) stores the *measured value* the owner agreed to per threshold
code, and `optimizer._accepts` requires `measured <= accepted_value` — so agreeing to a 27-minute
walking leg never blesses the 90-minute one a replan produces, while a tighter plan stays covered.
`optimizer.COMFORT_RULES` is the one table pairing each reason code with its violation code, metric and
threshold key; validator, soft count, `actions.comfort_tradeoffs` and the screen all read it.

Two things not to undo. **Consent must reach `_comfort_violation_count`, not just `validate_variant`** —
`comfort_violations` outranks `experience_value` in the objective tuple, so the search drops a place
rather than exceed a budget and the owner silently loses a stop; clearing only the hard error leaves
that intact. Measured on `jp-shibuya-plain-walk-overload`: 2 of 3 visits without an acceptance, **3 of 3
with one**. And **do not revive `fits_with_tradeoff`** — no call site has ever produced it (only `fits`
and `cannot_currently_fit`), and the three threshold violations carry `subject_id: None` because they
are properties of the whole variant, so routing consent through a per-place record was the wrong shape.
`has_unaccepted_tradeoff` and the `exports.py` tradeoff list stay dead for that reason; deleting them is
its own decision.

**Two names, and two sources, as of 2026-08-07.** `shared/names.ts` is still the one place
naming happens, and it now answers two questions: `placeName()` for the readable name and
`placeAltName()` for the local-script one beside it — `null` where they would be identical, so a card
never prints the same string twice. Both are shown because a traveller needs each: the local name is
what the station sign and a taxi driver use. Two sources feed it via `mergeNames()`, **OpenStreetMap
winning** because `name:en` is the name on the ground, with Wikidata's label filling gaps. That matters
because **61% of the Taipei catalogue (525 of 849) has no `name:en` at all**; 131 of those carry a QID,
and sampling 17 of them recovered a real English name for 13 — 三井物產株式會社舊廈 is "Mitsui & Co.,
Ltd. Old Building", not a translation. `WikidataSummaryProvider` gets labels in the request it was
already making (`props=sitelinks|claims|labels`), so the cost is zero, and a label arrives with the free
description rather than before it. A place with no article still yields a name: `text` can be empty while
`names` is not, and `refresh_place_summaries` stores the whole value, so nothing drops it.

Do not machine-translate the rest. The residual is places like 華江橋下自行車練習場 (a bicycle practice
ground) with no name in any free source, and inventing one is fabrication, not naming.

**The planner recommends where to stay as of 2026-08-06 (`WF-040`).** `travel_planner/areas.py` is a new
pure module and `actions.recommend_areas` the coordinator; `recommend_areas` was the **64th** allowlisted
method. **The unit is a transit station, not a hotel and not a district** — that is how the owner
searches ("it only near ximenting station"), it is the only unit whose travel time the app can measure
exactly, and district names do not generalise (Taipei's OSM addresses carry `中正區` on 278 of 832
candidates, so parsing one would be a Chinese-only regex over a third of the data). Five factors:
travel time 45, metro access 20, food 15, after-dark 10, lodging choice 10. Free — one Overpass request
for the whole shortlist via `OsmAreaAmenitiesProvider`, `openstreetmap:areas` priced at 0.0.
Four things are **never** scored and are returned on every result including an empty one: price, room
type and family capacity, cleanliness, safety. Do not fold any of them into the score — the owner's own
constraint was a family room that existed only on Airbnb, which no free source can see.

Three traps, all found by measuring rather than reasoning. **Group graph stops by name**: `STOP_TAGS`
admits platforms so relations resolve, so 437 Taipei stops are 138 stations (six for 板橋) and without
grouping the shortlist fills with duplicates. **Score travel time as a ratio against the best, not a
rank across the observed range**: the shortlisted stations all average 20-22 minutes, and rank-scaling
turned that into a 45-point gap. **Set count ceilings from data and use a log curve**: a linear scale
saturating at 30 gave every station a flat 15 of 15 when Taipei really returns 150-586. And
`TransitGraph.journey` returns `None` when nothing needs riding, so travel time takes the **better of
riding and walking** — otherwise a station across the road from a place scores as unreachable.

**Which months suit a destination is measured, not recalled, as of 2026-08-08 (`WF-048`).**
`travel_planner/climate.py` is a new pure module and `actions.travel_month_guide` the coordinator, the
**75th** allowlisted method when it landed, and a read. A model asked "when should I go to Seoul" answers instantly and
unverifiably — the failure `WF-046` measured — so this answers from Open-Meteo's archive (five whole
years of recorded daily highs, lows and precipitation, keyless, free) and Nager.Date's published public
holidays. Both are priced at **US$0.00** and recorded anyway, so call counts stay reconcilable.

Four things that are decisions rather than implementation. **Bands are relative to the destination**:
Taipei's coolest month is warmer than Seoul's warmest, so a global comfort threshold would call one city
uniformly bad and answer a question nobody asked — three best, three worst, six fair, per city.
**Every month is returned and stays selectable**, because a recommendation that removes the choice
decides for an owner who may be travelling on dates a school year sets. **A long national holiday is a
`con` and a `pro` at once** — it fills the trains *and* it is the only month the festival happens — and
neither is netted into the other, the same "report, do not decide" shape as `WF-047`'s cost options and
`WF-045`'s drift. Every verdict carries the numbers behind it, and the core emits codes with args while
the view renders them.

**Holidays come from two sources, because one was not enough.** Nager.Date's own coverage page puts
**Asia at 38%** (19 of 50) and says it depends on community contributions, so Taiwan, Thailand, Malaysia,
India and the UAE were all missing — the pilot destination among them. Google's public holiday calendars
are free, keyless, published as iCalendar and cover every one, so `_google_holidays` is the fallback and
`holiday_source` records which answered. **Turkey was never missing**: Nager has it as `Türkiye`, and
matching on the `destinations.py` spelling reported a covered country as uncovered — a wrong answer from
a name, now aliased alongside `Czechia`.

Two things about the Google feed that are load-bearing. **Observances are excluded**: it carries both
kinds and Taiwan's has 213 public holidays against 117 observances, so counting International Women's Day
would invent a crowd out of a day nobody takes off — the filter is on the feed's own `DESCRIPTION`, not
on the name. And **the calendar ids follow no derivable rule** — `en.taiwan`, `en.th`, `en.indian` and
`en.turkish` are all real while `en.tw`, `en.thailand` and `en.india` all 500 — so it is a looked-up
table, and a country in neither source stays honestly uncovered with a `month_crowding_unknown` con.

Verified on both. Seoul: best April, October, May; hardest January, February, July, catching **Seollal**
and **Chuseok**. Taipei: best January, March, November; hardest June, July, August, and February drops to
fair on a **9-day Lunar New Year run** — the single most important travel fact about Taiwan, and the one
that was invisible before.

**Two things a self-review caught that testing had not, 2026-08-08.** `travel_month_guide`'s cache-hit
branch read `held["value"]`, but `store.get_trip_evidence` **spreads the stored value at the top level**
and adds only `retrieved_at` / `expires_at` — so every cache hit raised `KeyError`. It shipped because
every read written while building it passed `force=True`, which skips the branch. Measured after the
fix: 9.08 s cold, **0.017 s warm**. And `photos_are_nearby` was written by `refresh_place_summaries` and
**read by nothing** — the flag existed, the comment claimed the screen used it, and a Commons geosearch
photograph of the next street was shown exactly like a photograph of the place. Both the deck and the
detail panel now print `photo_is_nearby` instead of the Wikipedia credit when the flag is set. The
lesson is the general one: a flag nothing renders is not a disclosure, and a branch no test enters is
not code that works.

**A city-only destination resolves its country as of 2026-08-08.** `destination.split(",")[-1]` gave
`"Taipei"` as a country for every trip made before the country/city picker — and for 49 of the fixtures
— which matched no holiday source and reported a covered country as having none.
`destinations.country_for()` looks the city up, falling back to the last segment so a country outside
the picker still reaches the holiday sources, which cover far more than it does.

**Changing setup does not cost a re-search as of 2026-08-08 (`WF-048`).** Discovery stores the setup
hash it ran against, so adding dates made the found places stale — and a stale trip cannot even record
a choice, the server refuses with 409. The advice was "discover again", which on a dense city is a
minute of Overpass and reads as losing the work. Nothing needs re-searching: `discover_places` keys the
provider cache on the **destination alone**, so with a fresh entry it rebuilds the run from disk with
**no network call** — measured at 0.05 s on a 715-place Seoul catalogue — and `place_id` is a hash of
name, coordinates and category, so every existing choice still points at the same place. `StayPlanner`
does it automatically after writing dates, and the stale-setup warning on `/places` carries a button
that does the same. Never `force_refresh` for this: that goes back to Overpass and undoes the point.

**A summary carries the provider version it was written under as of 2026-08-08 (`WF-048`).**
`cache_version` existed on every provider and `refresh_place_summaries` never consulted it, so a place
cached before Commons geosearch was added kept its empty gallery for the full 60-day TTL — cards stayed
blank after the source that would have filled them landed. The version is stored inside the value and
compared on read, so bumping it (`wikidata-summary-v2`) refetches each place once and no further.

**A trip can be deleted from the webapp as of 2026-08-08 (`WF-048`), and `delete_trip` was broken.**
The method has been on the allowlist since S1 with no control anywhere, so a trip made by mistake
stayed in the switcher for good. Building the control found the method itself unusable: `split_rows`,
`split_settled_markers` (S2) and `comfort_acceptances` (`WF-039`) all arrived after
`store.delete_trip`'s ordered table list was written and none was added, so deleting any trip that had
settled a bill or accepted a comfort tradeoff raised `FOREIGN KEY constraint failed`. Its own comment
predicted exactly this — "a future trip-scoped table fails this transaction safely until added here" —
and nothing was checking it. `test_delete_trip_removes_planning_data_but_keeps_paid_usage` already
enumerated every trip-scoped table and asserted zero rows survived, but the victim had no rows in the
three, so it counted zero of zero and passed. It now populates them, and negative-tested against the
old `store.py` it fails with the real error. **Paid usage is deliberately kept** — the charge really
happened, so it stays on the monthly total. The confirmation is type-the-name, which is the POC's own
design: `delete_trip_confirm` was already in the catalogue, the deletion is irreversible, and a button
you can hit twice by reflex is not a confirmation.

**Category variety reverses the learned bonus as of 2026-08-08 (`WF-048`).**
`ranking._learned_category_weights` only ever argued for *more* of what was already chosen: pick three
temples and temples rose, so the fourth and fifth led every lane and the deck offered "the same thing
over and over". It now saturates at `VARIETY_SATURATION = 3.0` weighted picks — unchanged below that,
which is the signal that discovers a taste — then each further pick costs `VARIETY_PENALTY = 1.5`,
bounded at `VARIETY_FLOOR = -6.0` so a category is pushed down the order but never out of reach. Five
temple picks measure −3.0 against a first museum's +2.0. The same number now argues both ways, so it
carries two explanations: `learned_from_choices` when positive, `category_already_well_covered` when
negative, and the latter is a `con` as well. Ranking already re-ran on every choice; only the direction
was missing. Five tests in `tests/test_ranking.py` pin the curve, including that a `not_for_trip`
neither teaches nor saturates.

**Discovery dedupes on name and place, not on tag, as of 2026-08-08 (`WF-048`).** Requiring an
identical `category` as well let one attraction through twice whenever OpenStreetMap disagreed with
itself about what it is — Singapore's "Jelutong Tower" arrived as `viewpoint` and as `landmark`, so the
owner was asked about it in one lane having already answered in another. An identical normalized name
within 150 m is the strong signal; the category was the weak one and it was doing the deciding.
`PlaceDeck` also filters by name, because discovery cannot merge what it cannot tell apart — a zoo
signs one exhibit twice, 200 m apart.

**Photographs have a third source as of 2026-08-08 (`WF-048`).** Wikidata `P18` and Wikipedia both need
a QID, and 61% of the Taipei catalogue has none — those places were `skipped` outright in
`refresh_place_summaries`, which is why so many cards had no picture. Wikimedia Commons **geosearch**
works from the coordinates every candidate has. It answers "what is photographed at this spot", **not**
"photographs of this place" — 300 m around Taipei 101 returns a sunset and a street in Keelung — so the
radius is small, it is used only where nothing better exists, and it is stored `photos_are_nearby:
true` so the screen can say which it is showing. *(**The radius is 400 m since 2026-08-17**, not the
150 m this paragraph was written against: 150 m is the building rather than the site, and a citadel or
a park is routinely photographed from a corner of its own grounds. That was affordable only because the
name filter had by then become much stronger — see "The photo filter got looser in one direction" below.
The Keelung street is still refused, by the name, not by the radius.)* It returns direct thumbnail URLs rather than
`Special:FilePath` redirects, so these load in one round trip instead of two. `web/src/shared/photos.ts`
is the one place a gallery is assembled, and it also reads OpenStreetMap's own `wikimedia_commons` /
`image` tag, stored as `photo_reference` since discovery was written and never read until now.

**A geosearch photograph must name the place as of 2026-08-09 (`WF-048`), or it is not shown.** Saying
which kind of picture it was turned out not to be enough: the pilot offered a city bus as the picture of
a hill, from `KKMT_470-FY_right_side_at_Yuanshan_Bus_Station`, and a caption does not undo a wrong
photograph on a card whose picture is what the swipe decision is made on. `providers.photo_depicts_place`
filters on the file's own name, which is the only evidence available about its subject and turns out to
be a good one.

**Containment alone fails, and the pilot's own case is why.** The catalogue calls that hill `Yuanshan`,
which `Yuanshan Bus Station` contains — so the name must also account for at least
`PHOTO_NAME_MIN_COVERAGE` of the file name, digits and the `File:`/extension wrapper removed. Measured:
the two bus photographs score **0.20 and 0.31** against **0.46, 0.48 and 0.75** for correct ones, which
is a gap rather than a boundary. Strip the wrapper or the rule inverts — counting `File:` and `.jpg` puts
`Daan Forest Park` at 0.39 of its own photograph.

Three costs, all measured and all accepted. **The whole name must appear, not one of its words**:
`Herbarium 植物園蠟業館` really is the Herbarium of Taipei Botanical Garden and is rejected, because
matching single words instead would accept any `Taipei` street scene for the majority of a catalogue
whose names begin with the city. *(**Softened on 2026-08-17**, and only in one direction: the same words
in **any order** now match, so `Thành cổ Điện Hải` is accepted for `Thành Điện Hải`. **Every** word must
still appear — the any-word rule this paragraph rejects is still rejected, and for the reason it gives.
The Herbarium is still lost. See "The photo filter got looser in one direction" below.)* **A verbose file name loses its place** — a title reciting country,
city and district before naming the park scores 0.14 — though such places generally carry a plainer file
too. And **a name under `PHOTO_NAME_MIN_CHARACTERS` matches nothing**: 圓山 is two characters and a
substring of 圓山站, 圓山公園 and 圓山大飯店, three different places. Verified against the live API on
the pilot: Da-an Forest Park and Jieshou Park keep correct photographs and the correct one now *leads*
where `Dongmen by night` used to, while Yuanshan, Yuanshan Park, Mantoushan, Central Art Park and the
Floriculture Experiment Center show **no photograph rather than a wrong one** — 19 of 22 summaries carry
a picture against 19 before, so the whole cost was one correct photograph and four wrong ones.

`cache_version` is bumped to `wikidata-summary-v3`, which is what makes a stored bus heal itself rather
than sit out the 60-day TTL. The screen's caption changes with it: the picture is no longer "not
necessarily of this place".

**Ranking divides by category breadth as of 2026-08-06 (`WF-037`).** `group_preference_fit` divided the
owner's matched styles by how many they *named*, which a category with more tags wins for free: `peak`
carries four tags and `attraction` two, so a nameless hill scored 27 of 30 against Taipei 101's 12.8 and
Taipei 101 ranked **363rd of 832**. It now divides by `_breadth(candidate_tags)`, capped at four.
`FORMULA_WEIGHTS` is untouched. Do not assume the ranker's ordering is tested by the old suite — it
asserted only that the score was internally consistent, which holds under any weighting, and
`test_a_landmark_is_not_buried_by_a_richer_tag_vocabulary` is the first test of what it recommends.

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

Plans are append-only: `plan_versions` and `discovery_runs` carry SQLite triggers that abort UPDATE
and DELETE. Restoring an old plan creates a *new* version pointing at the old snapshot. `active_plans`
holds exactly one version per trip; `optimization_previews` holds at most one replaceable pending
preview. `SCHEMA_VERSION` (`store.py`) is stamped into `PRAGMA user_version`; a newer DB refuses to open.

### Bilingual by data, not by branching

All user-facing strings live in the eight `en`/`th` tables in `i18n/copy.json`; `travel_planner/copy.py`
reads it for the exports and React imports the same catalogue. The core emits stable codes; the views map code →
language → text. Switching language must never change ranking, scheduling, or the active plan — so
never put display text in the core or a language check in a scoring path. New user-visible string ⇒ add both
`en` and `th`. Tests enforce key parity across all tables except `CATEGORY_TEXT`'s documented derived-English
rule. Unknown stable codes render visibly as `⚠ CODE`; never prettify them into copy-looking prose.

### Tests

Python uses `unittest`; the webapp uses Vitest. No network, no paid API, no Python fixtures framework.
**`AppTest` is gone** — S6 removed the 18 tests that used it, having first moved the 14 portable
behaviours down to actions/core/exports. The suite has grown steadily since (311 at S6); run it for
the current count rather than trusting one written here.
`tests/fixtures/historic_regressions.json` encodes 20 atomic + 7 interaction failures from four real
past trips; `scripts/run_optimizer_regressions.py` replays all of them through the real optimizer.
Behavior changes to the optimizer should be expressed there.


## Deployment

**The app is live on Vercel and shared.** It was local-only until 2026-08-19; anything in this
repository or the journal that still says "local-only and single-owner" predates that and is wrong.

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

**Storage and the queue.** `open_store()` picks the backend: `TOURIST_DB_URL` selects Postgres,
absence of it selects the file. `PostgresStore` (`travel_planner/pgstore.py`) subclasses `SQLiteStore`
and replaces only `connect()`, so no statement is rewritten and the two backends cannot drift.
Discovery is 30–90s and a full proposal ~52s, so `travel_planner/jobs.py` holds the work and
`travel_planner/worker.py` drains it, claiming with `FOR UPDATE SKIP LOCKED`. The queue carries its own
idempotent DDL and sits **outside `SCHEMA_VERSION`** deliberately — it holds no planning truth and can
be rebuilt.

**The worker is a long-lived process and Vercel has no home for it.** A container or small VM is
required somewhere; "Vercel + Supabase" alone does not run this app.

Today it is a process on the owner's laptop, and on 2026-08-23 it was **not running at all** — the
deployment answered `job_timeout` at 300 s on every job for hours, which reads as an application
fault and is not one. `deploy/macos/install.sh` installs a launchd agent that keeps it up across
crash, sleep and reboot; `deploy/macos/worker.sh` is the wrapper it runs and the one place the
start-up rules are enforced rather than remembered. The same script is the control surface —
`status`, `logs`, `restart`, `stop`, `start`, `uninstall`. **Restart it after changing anything
the worker imports**: the process holds the code it started with, which is the `ensure_web_build()`
trap in a second place. `stop` leaves the plist, so launchd loads it again at the next login;
only `uninstall` is permanent. And `kill` is not a stop — `KeepAlive` returns the worker within
seconds, so it is a slow `restart` wearing a misleading name.

**Diagnose the worker by its python child, never by the `uv` wrapper.** `uv run` leaves two
processes and the parent holds nothing, so `lsof -p <uv pid> | grep -c psycopg` is `0` on a
perfectly healthy worker. `deploy/macos/install.sh status` prints both, plus the `draining
PostgresStore` line that is the actual answer.

**The agent needs `/bin/bash` in Full Disk Access, once per machine.** The repo lives under
`~/Documents`, which macOS protects, and a launchd agent gets neither access nor a prompt — the
first install failed with exit 126 and `Operation not permitted` on a script that runs perfectly
from a terminal, because Terminal holds the grant and launchd does not. Two consequences worth
keeping. The grant is attributed to the binary launchd spawns, so the plist names `/bin/bash`
explicitly instead of exec'ing the script through a `#!/usr/bin/env bash` shebang whose image PATH
would choose. And the secret stays out of it either way: a plist in `~/Library/LaunchAgents` is
world-readable, so the URL is read from `.env` at start rather than written into
`EnvironmentVariables` — `worker.sh` reads **`POSTGRES_URL_NON_POOLING`**, per the template rule
above, and passes it to one process without exporting it.

**Sharing.** The token is a random value the browser keeps in `localStorage` — not a credential and not
offered as one; it separates several people's trips, which was the actual problem. Two consequences:
trips are per-browser, so the same person in a second browser sees an empty list, and **the spend cap
is global, so any visitor can spend the owner's keys.**

`PUBLIC_RELEASE_PLAN.md` holds the canonical build order and exit gates for the wider release. Link to
it from tickets rather than copying its checklist; retain run evidence under `artifacts/validation/<run-id>/`.

## Configuration

**The default model is `gpt-5.6-luna` as of 2026-08-07** (`TOURIST_OPENAI_MODEL` still overrides), and it
beat `gpt-4.1-mini` on the `WF-046` benchmark — 6 of 12 exact against 5 of 13, four overshoots against
five, and it declines rather than claiming to know all thirteen. **The three `openai:*` prices were measured against
luna's rate card** (US$0.20/M input, US$1.20/M output at short context; nothing here reaches long
context, and `store: false` means caching never applies). luna is a *reasoning* model, so output is
mostly hidden reasoning and varies: six measured `opening_window` calls ran US$0.000090–US$0.000266, so
it is priced at **US$0.0005** and a 13-place refresh costs US$0.0065. `interpret_revision` and
`explain_revision` are sized from the real payload rather than measured end to end. The revision
surface is now reachable, but no real paid interpretation was submitted during its 2026-08-11
verification, so the UI correctly says **about** US$0.002. **The ledger over-reports OpenAI spend by
~US$0.325** from 30 calls recorded at interim
tenfold prices; `paid_usage` is append-only by design, the error is in the safe direction, and it decays
as new rows use the measured price.

`TOURIST_DB_URL` (unset by default; when set it selects Postgres and **overrides the path**, see the hosted-port section above), `TOURIST_DB_PATH` (default `data/tourist.sqlite3`), `TOURIST_NOMINATIM_URL`, `TOURIST_OVERPASS_URL`,
`TOURIST_USER_AGENT`, `TOURIST_GTFS_PATH` (default
`data/gtfs/transit.zip`; a GTFS zip read locally for transit legs — see `WF-038`). Providers still read keys from `os.environ` and nowhere else — that is what keeps
a key out of every snapshot, export and log. `credentials.load_local_credentials()` (called once at startup by
`localserver` and once by `travel_planner/worker.py`, which is the thing that talks to providers)
copies a flat `secrets.local.json` into the environment first, so the owner need not
export four variables per shell; an already-set variable always wins, and the module never logs or
returns a value. `.env` / `secrets.local.json` are gitignored, `.env.example` / `secrets.example.json`
hold names and placeholders. `scripts/check_provider_access.py` reads the same file directly.
`tests/__init__.py` sets `TOURIST_LOCAL_SECRETS=off`. The original reason — `AppTest` importing `app.py`,
which loaded secrets at module scope — died with the POC, and secrets are now loaded only at an entry
point, never at import. **Do not remove that line anyway**: it costs nothing and the failure it prevents is a bill. Paid usage is capped
at US$10/month by decision (warn at $8). `usage.py` is that ledger: `PRICES_USD` holds the estimated
unit price per `provider:operation`, `actions._spend()` refuses a call that would cross the cap and
records what it cost, and free-tier operations are recorded at zero so call counts stay reconcilable.
Every paid provider call must route through `_spend`; an unpriced operation raises rather than being
assumed free. Ledger rows are append-only by SQLite trigger.
`enrich_place_card` photographs are a **session overlay**, not a `place_summaries` write. Both the
detail panel and swipe deck must read `PlaceInsight` directly; invalidating the free-summary query
cannot reveal paid photographs and leaves the charged card blank. Disable the card's paid control
while that overlay is arriving so one press cannot become two charges.


## Graphify: this repo overrides the parent instructions

The ancestor `Thaksin/CLAUDE.md` tells agents to run `graphify query` for codebase questions and `graphify update .`
after edits. **Do not do either here.** Read source and tests directly; consult
`graphify-out/GRAPH_REPORT.md` only for a broad architecture question.

`graphify-out/GRAPH_REPORT.md` carries a generated "Graph Freshness" line advising `graphify update .`
after code changes. That is graphify 0.9.3 boilerplate, it is regenerated on every rebuild, and it is
wrong for this repo — ignore it.

On 2026-07-29 `graphify update . --no-cluster` corrupted the checked-in graph: it dropped the
`directed` flag and removed the Wayfinder/document nodes. `graphify-out/graph.json` is canonical and
must stay directed. Rebuild only through `python3 scripts/build_project_graph.py` (paid, needs
`OPENAI_API_KEY`; wraps extract → normalize → cluster-only → export and restores the previous graph on
failure), and only when explicitly asked or after a topology-changing milestone. After any graph
change, `--check` must pass before committing. See `AGENTS.md`.

**Rebuilt on 2026-08-27 for `WF-051` and `--check` passes**: **3252 nodes, 7551 directed
edges, 248 communities**, up from 3188/7392. It took **two attempts and US$0.070005**, and
the failure was the documented clustering-variance one: the first run lost **20** valid
extracted endpoint pairs, only one of which (`actions_delete_trip -> jobqueue_discard_trip`)
belonged to the new code — the other nineteen were pre-existing edges from
`recommend_areas` and `travel_month_guide` that nothing in this session touched. **Retry
before diagnosing**: the second run was 91 hit / 0 miss on the warm semantic cache, cost
**nothing**, and passed.

**A failed rebuild *is* recorded now, and the note below saying otherwise is stale.** The
US$0.070005 above is the *failed* run; the successful retry added zero, and `cost.json`'s
cumulative went 0.799241 → 0.869246 on the failure alone. Read the ledger rather than
assuming a failure was free or that a success was paid for.

**Rebuilt on 2026-08-24 for `WF-050` and `--check` passes**: **3091 nodes, 7245
directed edges, 223 communities**. The first extraction cost US$0.064237 and failed after
clustering lost 140 valid endpoint pairs. It also exposed a failure-path bug: `cluster_raw_graph()`
deleted `.graphify_raw.json` in `finally`, before `build()` could preserve the raw graph it promised
to keep for diagnosis. The staged raw graph now survives until validation succeeds, and its test
pins that lifecycle. The warm retry was 88 hits / 2 misses, cost US$0.003505 and passed; this rebuild
therefore cost **US$0.067742** in total. If validation fails again, inspect both
`failed-raw.json` and `failed-clustered.json` before paying for another extraction.

**The report's "Suggested Questions" are prompts, not defects, and three of the four
standing ones are answered by the architecture.** Asked on 2026-08-24 and settled by
comparing each node's reach with inferred edges included against `EXTRACTED` edges only —
twenty lines over `graph.json`, and the check to repeat rather than re-deriving the
argument:

| Node | communities bridged, all edges | on `EXTRACTED` only | inference-only |
|---|---|---|---|
| `PlannerActions` | 64 | **41** | 23 |
| `SQLiteStore` | 20 | **15** | 5 |
| `PlannerRefusal` | 39 | 12 | **27** |

So `PlannerActions` bridging everything is **the design working**, not a smell: it is the
only coordinator, by decision, and it still reaches 41 communities with every inferred
edge removed. `SQLiteStore` is the same story one layer down. Neither is a refactoring
target, and a graph metric is not an argument for splitting them.

**`PlannerRefusal` is the one that is an artifact, and the proof is exact.** Its 27
outgoing inferred edges are *byte-identical* to `PlannerActions`' — same relations, same
targets, nothing unique to it — so the graph claims a two-line exception class `uses`
`CandidateChoice`, `DiscoveryRun` and `PlanVersion`. It does not. Thirty same-file groups
show the same shape: every top-level class in a module inherits one inferred edge set.
**Inference in this graph is attributed at file granularity**, so an `INFERRED` edge means
"something in this file does this", never "this symbol does this". Read them that way and
do not cite one as evidence about a class.

This was left unpruned on purpose. The obvious guard — drop a copied edge when the class
never names the target — removes **468 of 691** inferred edges, and it cannot tell
indirect use from invention: a test that calls `self.actions` really does use
`PlannerActions` without ever writing the word. Deleting true relationships to tidy a
report section is the worse trade, and the endpoint-pair guard exists because guesses
about this graph have been wrong before.

Two counting traps when reading that report. It reports **outgoing** inferred edges only,
so "27 inferred relationships involving `PlannerActions`" is 27 of its 150. And its
community lists are filtered — 105 thin communities are omitted — so "connects Community 0
to 17 others" is not the 64 the graph holds.

**Rebuilt on 2026-08-22 after the itinerary dashboard and `--check` passes**: **2964 nodes, 6970
directed edges, 220 communities**, up from 2389/5732/200 — seven new modules
(`shared/tripClock.ts`, `shared/cards.ts`, `shared/ticks.ts`, `shared/checklistText.ts`,
`stages/DayStops.tsx`, `stages/TripNow.tsx`, `tests/test_discovery_egress.py`) and the rewritten
`/itinerary`. It took **three attempts and US$0.076311**, and both failures are the two documented
kinds rather than anything new:

- The first lost **110** endpoint pairs, all pointing at `travel_planner_actions`, whose file node
  extraction had simply not emitted that run. **The retry produced it**, which is the "extraction is
  not deterministic" case below — retry before diagnosing.
- The second lost exactly **one**: `travel_planner_providers_openmeteoforecastprovider_forecast ->
  web_src_shared_tripclock_at`. A **third name collision**, and the reverse direction of the first two:
  `providers.py` has a local `def at(field)` inside `OpenMeteoForecastProvider.forecast`, and the new
  `shared/tripClock.ts` exported a function called `at`. Renamed to `momentAt`; the third run was
  **free** on a warm cache (89 hit / 0 miss).

**Do not name anything on either side after a short generic the other side also uses.** That is now
`rpc`, `fetch` and `at` — three occurrences, and the rule runs both ways: it was written as "do not
name a Python method after something the TypeScript side calls", but a two-letter TypeScript *export*
collided with a Python local just as easily. Fix it by renaming, never by weakening the endpoint-pair
guard.

**Rebuilt on 2026-08-10 for `WF-049` and `--check` passed**: **2389 nodes, 5732 directed edges,
200 communities**; recorded cumulative cost is US$0.455929 over 41 runs. Adding the ticket file is what
required it — `--check` demands a node per ticket, so stage 4 of `check.py` failed with
`Extraction produced no node for WF-049` until this ran. It cost **US$0.0296** and succeeded on the
first attempt, with no `no node for …` flake.

**A fold guard was wrong, and the rebuild's own output is what showed it.** `normalize_raw_graph`
prints every fold precisely so they can be read, and this run printed eight. Four were genuine file
twins. The other four were **real methods being deleted**: `json` is in `SOURCE_EXTENSIONS`, `_json`
is also an ordinary Python method name, and `PlannerHandler._json` (then `api/__init__.py`, now `localserver/__init__.py`) extracted
as `api_init_plannerhandler_json`, found its own *class* sitting there as a stem, and was folded out
of existence — along with the `_json` on three providers in `travel_planner/providers.py`.

The comment above that code claimed "the stem-must-exist guard is what makes a wrong fold
unreachable". That was true only while every stem was a file. **A class is not a file, and a method is
not a duplicate of its class.** The fold now requires the stem to be a *file node*, recognised rather
than guessed: extraction labels a file with its own name and places it at `L1`, where a class or
method carries an identifier and its real line, and both conditions are required because a one-line
module would satisfy either alone. Re-running with the fix recovered exactly those four nodes and
folded the same four twins, on a **warm semantic cache at 76 hits / 0 misses, so it cost nothing** —
which is the same property that makes a retry after a failed rebuild free.

The earlier build the same day gave **2337 nodes, 5683 directed edges, 177 communities** at
US$0.426294 over 40 runs — +294 nodes and +651 edges over the one before it, which was the map work:
`web/src/shared/tiles.ts`, `tests/test_map_layers.py`, the rebuilt `PlaceMap`, and the forecast,
country-outline and route-shape providers.

**Extraction is not deterministic, and the per-ticket guard will catch that.** The first run failed with
`Extraction produced no node for WF-048` after being billed US$0.0262 — every ticket from 001 to 047
produced a node and 048 produced none. Nothing was wrong with the ticket: **the immediate retry produced
one and the build passed**, for US$0.0059 on a warm cache. So treat a single `Extraction produced no node
for …` as a coin-flip before treating it as a defect: retry first, and only then go looking at the ticket.
The failed run's US$0.0262 was **not** in `cost.json` at the time — the ledger recorded a run only when it
completed. **That is no longer true as of 2026-08-27**: the `WF-051` rebuild's failed first attempt
recorded its own US$0.070005 and the successful retry added nothing, so the ledger now attributes a
warm-cache retry's success to the failure that preceded it. Either way the rule is the same — read
`cost.json` rather than reasoning about which attempt paid.

The earlier `WF-048` rebuild on 2026-08-07 gave 2043 nodes, 5032 edges and 167 communities at
US$0.420408 cumulative; the `WF-047` one before it gave 2026 nodes, 5002 edges and 165 communities.

**A duplicate node twin can be spelled without a separator, and that cost a paid run.** The
`WF-048` rebuild failed after being billed: extraction emitted `travel_planner_destinationspy` and
`web_src_routestsx` beside the real nodes, where `SOURCE_SUFFIX_IDS` listed only `_py` / `_ts`. Same
trap as below, new spelling — so the list is now generated from one extension tuple in **both**
spellings, and `normalize_raw_graph` **prints every fold it makes**, because a silent fold is
indistinguishable from the pair guard being weakened. Two tests in `tests/test_graph_builder.py`
pin it, including the negative case: `wayfinder_tickets` ends in `ts` and does not fold, because the
stem must itself be a node. **A retry after a failed rebuild is free** — the semantic cache stays
warm, so the second run reported 74 hit / 0 miss and US$0.00. Do not treat a failed rebuild as money
that must be spent again.

**A second name collision, and the same fix the first one needed.** A provider method called `fetch`
collided with the browser `fetch()` that `web/src/api/client.ts`'s `rpc` calls: extraction invented an edge
claiming TypeScript calls Python, clustering rightly dropped it, and the endpoint-pair guard demanded a
false edge survive. Renamed to `read_page`. **Do not name a Python method after something the TypeScript
side calls** — `fetch`, `rpc`, `post`. That is now two occurrences, so treat it as a rule rather than a
curiosity. *(Three as of 2026-08-22, and the third ran the other way: a TypeScript export named `at`
against a Python local `def at`. See the rebuild note above — the rule is symmetric.)*

A third ticket-authoring trap, and the fix is in `normalize_raw_graph` rather than in how tickets are
written. Extraction sometimes emits one file **twice** — `tests_test_x` and `tests_test_x_py`,
`web_src_shared_names` and `web_src_shared_names_ts` — when a document cites it by path. `SOURCE_SUFFIX_IDS`
lists the extensions this affects; the `_py` case was fixed first and `_ts` appeared on the very next
rebuild, so treat the suffix list as incomplete rather than exhaustive. Both land in the raw node set, so the endpoint-pair guard treats an edge
to the `_py` twin as real, clustering then correctly collapses the duplicate, and the build fails claiming
data was lost. `WF-039` cited `tests/test_comfort.py` in the identical style and extracted cleanly, so it
is extraction variance, not a citation style to correct. The twin is now folded into the real node before
`expected` is computed — the same normalisation the `wayfinder_tickets_NNN` aliases already perform, and
**not** a relaxation of the guard: the edge survives, pointed at the node that does. The `WF-039` rebuild the same day
gave 1868 nodes, 4589 edges and 150 communities. The `WF-040` rebuild the day before
gave 1818 nodes, 4492 edges and 153 communities for US$0.0121.

Two ticket-authoring gotchas learned paying for that run. **Cite a module by its path** — a bare
`exports.py` extracted as a node id `exports` that does not exist, clustering rightly dropped the edge,
and the endpoint-pair guard then demanded a false edge survive; every other ticket writes
`travel_planner/exports.py`, which resolves. And **a ticket dense in code identifiers may extract no
titled node at all**: `WF-039` produced only `comfort_acceptances Table`, `COMFORT_RULES` and
`comfort_tradeoffs`, so `resolve_ticket_node` could not choose among three candidates and aborted the
build. That was fixed at the root rather than worked around — a ticket's node id is read **only** as an
endpoint of a `blocked_by` edge, so `resolve_ticket_node` now takes `required=` and only refuses over
ambiguity when the id is actually used. An **empty** extraction still always raises, because that is the
per-ticket presence guard `--check` depends on. The `WF-042`/`WF-043` rebuild earlier the same day gave 1756
nodes, 4305 edges and 148 communities for US$0.0125.
Adding a ticket file **breaks stage 4 of `check.py` until this is re-run**, because `--check` demands a
node per ticket; that is the normal reason to pay for a rebuild.

The earlier S6 rebuild on 2026-08-04 gave 1599 nodes, 3185 → 3851 directed edges and 149 communities, with
**zero nodes sourced from the deleted POC** (there were 82), for US$0.028350.

One of those failures was not flaky and is worth knowing: validation refused three times over the same
lost pair, `test_s4_taipei_journey_reaches_activation_and_both_downloads → web/src/api/client.rpc`. The
cause was a **name collision** — that test defined a local `def rpc(...)` helper and `client.ts` exports
`rpc`, so extraction invented an edge claiming a Python test calls a TypeScript function. Clustering was
right to drop it and the guard was demanding a false edge survive. Fixed at the source by renaming the
test-local helper to `post_api`; there is now no `def rpc` in any Python file. **Do not weaken the
endpoint-pair guard to get past a failure like this** — find the collision. `build()` now preserves
`failed-raw.json` and `failed-clustered.json` on failure, because the two files that explain a validation
failure were exactly the two its cleanup deleted. The script reads `OPENAI_API_KEY` from `secrets.local.json` itself.
Three things to know: **ticket nodes are keyed by title, not by ID**, so `WF-0nn` never appears in a node
name; **`--exclude` patterns are gitignore lines**, so anchor them (`/artifacts`, not `artifacts`) or they
match at every depth; and **never run `graphify extract` by hand** — it is incremental against an existing
`graph.json` and will overwrite it with a partial. `AGENTS.md` has the detail.

A node's `source_file` may hold an absolute path from the machine that built the graph. Such a path is
not `is_absolute()` on Windows, so joining it to the repository root produced a drive-relative path
that matched nothing, and `--check` failed with `Extraction produced no node for WF-001` on every
ticket except the one stored relatively. That reads exactly like the corruption above but is not it:
the nodes are present. `build_project_graph.source_path()` resolves a node's source against the
longest trailing segments that exist in this checkout, so the check works from any OS and any root.
Diagnose a `--check` failure by counting the wayfinder-sourced nodes before assuming data loss.


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
constraints. The Streamlit POC was deleted at S6 on 2026-08-04, and with it `fpdf2`, the 9:16
poster, the trip PDF and the whole export-font apparatus — no Unicode TTF, no `resolve_font()`, no
`TOURIST_EXPORT_FONT`. `_labels()` still strips pictographs, because the wording alone carrying the
state is an accessibility rule and not only an export one.

Out of scope for the Python core: FastAPI, Docker, Redis, remote collaboration, hosted notifications.
Runtime dependencies are `xlsxwriter` (slice 5 renders a workbook) and the two `psycopg` lines the
hosted deployment needs — `pyproject.toml` explains why they are there and not only in
`requirements.txt`. `pillow` is a dev dependency; the screen-baseline gate reads PNGs with it.

Slice-by-slice detail, and the counts that went with each slice, are in `docs/JOURNAL.md`.

## The journal

`docs/JOURNAL.md` holds the dated build history that used to live here: owner-testing rounds, the
hosted port, the Vercel deployment, and the slice-by-slice Phase 2 record. It is history, not guidance
— where it contradicts this file, this file wins. Read it for the reasoning behind a specific decision
when the ticket does not carry it; do not read it top-to-bottom before starting work.

When something in this file stops being true, **edit it**. The journal grew to 3,700 lines because
every change was appended as a new dated section while the old claim stayed where it was, and the file
ended up asserting both.
