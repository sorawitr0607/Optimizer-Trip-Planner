# Public release improvement plan

Status: **deferred until the owner decides to operate a public service**. The current product is a
strong local, single-owner pilot. It must not be exposed directly to the Internet: its stdlib API,
localhost `Host` allowlist, local SQLite file and local provider credentials were designed for one
trusted machine, not anonymous or multi-user traffic.

This is the canonical plan for turning that pilot into a public product. The audit evidence and
local closure record remain in
[WF-049](.wayfinder/tickets/049-decide-what-the-interface-owes-a-reader-who-is-not-the-owner.md).
Do not copy this checklist into tickets; link here and retain run evidence in
`artifacts/validation/<run-id>/`.

## 1. Choose what “public” means

Make this decision before changing the architecture:

| Release | What it means | Required work |
|---|---|---|
| Source/local download | People run their own private copy | Licence, installation/update path, secret-safe examples, supported-platform statement and user documentation |
| Invite-only hosted beta | A controlled set of accounts use a hosted service | Every section below; **recommended first hosted release** |
| Broad public service | Open registration or anonymous use | Beta gates plus abuse controls, support capacity, public policies and a proven operating history |

The plan below assumes a hosted, account-based service. Keep the planning core, immutable plan
versions and snapshot-only exporters; replace only the local-only operating boundary.

## 2. Build a production trust boundary

- Write a threat model covering accounts, trip data, traveller details, paid-provider actions,
  exports, administrator access and account recovery.
- Put the React build behind HTTPS and a production application server or managed platform. Do not
  bind `PlannerHandler` to a public interface.
- Add authenticated sessions, authorization on every trip-scoped action, tenant isolation and
  owner/admin separation. A guessed trip id must reveal and modify nothing.
- Define a versioned request schema and validate size, type and allowed fields at the public API
  boundary. Preserve the existing literal action allowlist.
- Add CSRF protection where cookies are used, a restrictive CORS policy, security headers, request
  and paid-action rate limits, and idempotency for retried billable operations.
- Keep provider keys server-side. Separate development, staging and production credentials,
  quotas, databases and paid-usage ledgers.
- Choose durable hosted storage with migrations, encrypted backups, point-in-time recovery and
  tested restore/delete procedures. The local SQLite file remains the local edition, not the
  shared production database.
- Verify the applicable controls from the current
  [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/)
  and close every Critical/High finding before inviting users.

Exit gate: an independent security review finds no unresolved Critical/High issue; access-control,
rate-limit, secret-redaction, backup/restore and rollback tests pass in staging.

## 3. Make privacy and provider use explicit

- Inventory every stored and transmitted field, its purpose, retention period and deletion path.
  Treat trip dates, locations, traveller preferences and expense allocations as private data.
- Reconcile the UI disclosures with the real payload sent to OpenStreetMap, routing, weather,
  Google and optional model providers. Record provider retention and regional-processing limits.
- Add account export and deletion, backup-expiry handling, and a way to withdraw optional-provider
  consent without losing deterministic/local planning.
- Publish a privacy notice, terms/support contact and provider attribution appropriate to the
  launch jurisdictions. Obtain legal review rather than inferring jurisdictional compliance from
  code.
- Define per-account and global paid budgets, alerts and emergency disable switches. A public user
  must never inherit the owner pilot's US$10 ledger or credentials.
- Add privacy-safe monitoring: no trip text, keys, full provider payloads or exported itineraries in
  logs, traces or analytics.

Exit gate: the data inventory matches the implementation; export/deletion and provider opt-out are
tested end to end; public disclosures name what leaves the service and why.

## 4. Finish human accessibility and language validation

- Have a native Thai reviewer walk every setup-to-export path and correct clarity, register,
  terminology, dates, currency and failure messages. Reapprove affected visual baselines.
- Test the complete journey with VoiceOver/Safari and NVDA/Firefox, including the guided tour,
  blocked stages, validation failures, tables, maps, exports and plan revisions.
- Repeat keyboard-only, 320px, 200–400% zoom, reduced-motion and high-contrast checks on the deployed
  build. Test status announcements, not only static names and roles.
- Add an automated accessibility check to CI as a regression alarm, while retaining manual
  assistive-technology testing for releases.
- Use [WCAG 2.2 Level AA](https://www.w3.org/TR/WCAG22/) as the public conformance target across
  whole pages and complete processes. Record scope, browser/AT versions, failures and retest evidence.

Exit gate: a native Thai reviewer and the VoiceOver/NVDA testers sign off; every Level A/AA failure
in the public journey is closed or the release is blocked.

## 5. Prove field performance and reliability

- Deploy staging with production compression, caching, image delivery and realistic provider
  latency. Test on a mid-range phone and constrained mobile network.
- Collect consent-appropriate field data. At the 75th percentile, target the current “good” Core Web
  Vitals thresholds: LCP at most 2.5 seconds, INP at most 200 ms and CLS at most 0.1, as defined by
  [web.dev](https://web.dev/articles/defining-core-web-vitals-thresholds).
- Profile Places first. The last local audit transferred about 792 KB after compression but decoded
  about 3.50 MB and produced five 95–139 ms long tasks. If field or staging results miss the gate,
  introduce a new lightweight summary endpoint and fetch full immutable snapshots only when their
  audit detail is opened; do not narrow data while retaining a hash for different bytes.
- Recheck thumbnail sizes, `srcset`, route chunks and below-fold loading from measurements. The raw
  Vite chunk warning alone is not a release failure; user timing and transferred bytes decide.
- Exercise weather, map, routing, place, model and paid-provider outages. The saved trip, exports and
  non-paid planning path must remain usable, with explicit stale/unavailable states.
- Define availability and recovery objectives, health checks, alert ownership and a rollback drill.

Exit gate: field Core Web Vitals are good on the supported public journeys, provider-failure drills
preserve a usable plan, and restore plus rollback complete within the chosen objectives.

## 6. Operate a beta before broad release

- Create reproducible staging and production deployments with reviewed migrations and one-command
  rollback. CI must run `scripts/check.py`, production build, security/dependency checks and the
  public API tests.
- Publish supported browsers/devices, a status/support contact and an incident-response owner.
- Run an invite-only beta first. Track accessibility, privacy, data-loss, provider-cost and
  performance incidents separately from feature requests.
- Do not open registration while a Critical/High security or privacy issue, a blocking accessibility
  defect, failed restore, unexplained paid spend, or a P0/P1 product defect remains.
- After the beta, make an explicit go/no-go decision with retained evidence. “The local tests pass”
  is supporting evidence, not the public-release decision.

## Public release gate

All of the following must be true at the same candidate commit:

- The full 12-stage local gate and production build pass; the graph integrity check passes.
- Staging matches the production architecture and has passed migration, backup, restore and rollback.
- Independent security review and the selected OWASP ASVS controls have no open Critical/High issue.
- Privacy/data inventory, public notices, provider consent, export and deletion match runtime behavior.
- WCAG 2.2 AA, VoiceOver/Safari, NVDA/Firefox and native Thai reviews pass the complete journey.
- Field Core Web Vitals meet the recorded thresholds with enough real data to support the claim.
- Provider outage, rate-limit, paid-budget and abuse tests fail safely.
- The invite-only beta has no unresolved release blocker, and support/incident ownership is active.

Until this gate passes, describe the product as a **local personal-planning pilot**, not a public
hosted service.
