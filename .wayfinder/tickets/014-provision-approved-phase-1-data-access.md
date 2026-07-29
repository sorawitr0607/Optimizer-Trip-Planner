---
id: WF-014
title: Provision approved Phase 1 data access
status: closed
labels:
  - "wayfinder:task"
parent: WF-MAP-001
assignee: user-and-root
blocked_by:
  - WF-004
---

# Provision approved Phase 1 data access

## Question

Create and verify the minimum access for one worldwide Phase 1 pipeline: no-key OpenStreetMap/Open-Meteo access, an openrouteservice key for core routing, and an optional Google key for live place quality, maps, and transit. Keep OpenAI text processing and Taipei/TDX enrichment separately optional; a new city must never require another API setup. Restrict keys, set hard quotas and spend controls, store secrets locally, and retain a redacted capability check without authorizing purchases beyond the confirmed ceiling.

## Progress comments

### 2026-07-28 — One-time worldwide access scaffold prepared

- Added one ignored local secret file, [`secrets.local.json`](../../secrets.local.json), with a safe committed template at [`secrets.example.json`](../../secrets.example.json). It contains only worldwide provider keys; there is no city-key registry.
- Added a standard-library-only [redacted capability check](../../Main/check_provider_access.py). Normal mode never calls a paid endpoint; `--live-paid` makes one explicit Google Places request only after a key is configured.
- Python compilation and the offline redaction self-check pass. The checker also repairs this Python installation's missing default CA path by loading the existing macOS system CA bundle without disabling TLS verification.
- Open-Meteo live access is verified. The main public Overpass service was reachable once, then returned two HTTP 504 responses even for a tiny bounded query; this confirms that public OSM access needs graceful retry/cached/manual fallback and cannot be treated as an availability guarantee.
- No openrouteservice, Google Maps, or OpenAI key is currently configured. OpenAI remains optional. The ticket stays open until the required worldwide routing key and the approved Google overlay keys are stored locally, restricted, quota-capped, and verified without exposing them.

### One-time user setup required

1. Sign in to [openrouteservice](https://openrouteservice.org/log-in/), create one Standard-plan key, and put it in `OPENROUTESERVICE_API_KEY` in the ignored local secret file.
2. Create one dedicated Google Maps Platform project with billing enabled, then enable Places API (New), Routes API, and Maps JavaScript API.
3. Create a private server key restricted to Places API (New) and Routes API, then put it in `GOOGLE_MAPS_SERVER_KEY`. Apply an IP restriction only if the computer has a stable public IP; otherwise retain strict API and quota restrictions and never expose this key to the browser.
4. Create a browser key restricted to Maps JavaScript API and local website referrers only, then put it in `GOOGLE_MAPS_BROWSER_KEY`.
5. Set deliberately low API quotas and US$5/US$8/US$10 budget alerts. Budget alerts are notifications, not hard stops; the app's local usage ledger remains the final stop before the US$10 ceiling.
6. Leave `OPENAI_API_KEY` blank for now unless optional tag extraction or translation is deliberately enabled later.

After the keys are saved, run `python3 Main/check_provider_access.py` for the no-cost/redacted status and use `--live-paid` only for the final two-request Google verification.

### 2026-07-28 — Credentials added and live server access verified

- The ignored local file now contains openrouteservice, Google server, Google browser, and OpenAI credentials; their values were never printed.
- The redacted normal check passed for live Open-Meteo, bounded OpenStreetMap Overpass, and openrouteservice routing. It detected both Google keys and the optional OpenAI key.
- The explicitly approved two-request Google check passed for Places API (New) and Routes API. The browser key is configuration-verified only until the map prototype loads it under its referrer restriction; OpenAI remains uncalled because it is not core provisioning.
- The ticket remains open only until the user confirms that API restrictions, deliberately low quotas, and the US$5/US$8/US$10 budget alerts were also applied in Google Cloud. Those controls cannot be inferred from a successful API response.

### 2026-07-28 — Security and cost controls confirmed

The user confirmed that the Google server/browser restrictions, conservative method quotas, quota-usage alerts, and project-scoped US$5/US$8/US$10 budget alerts are configured. Provisioning is complete: the same worldwide credentials can serve every destination, optional city adapters require no user setup, secret values remain only in the ignored local file, and no provider call is allowed inside an optimizer search loop.
