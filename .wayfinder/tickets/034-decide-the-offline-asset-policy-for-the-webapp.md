---
id: WF-034
title: Decide the offline asset policy for the webapp
status: open
labels:
  - "wayfinder:grilling"
parent: WF-MAP-002
assignee:
blocked_by:
  - WF-020
---

# Decide the offline asset policy for the webapp

## Question

Which fonts, flags, and artwork ship inside the repository, in which formats and weights, and what does the
webapp look like on a plane or in a Taipei hotel with no usable network?

## Context

Graduated from the map's fog by the token contract, which found three separate network dependencies in an
app whose whole premise is local-first.

- The Google Fonts `@import` at `index.css:1` is render-blocking and unreachable offline, so Auto-Bill
  currently degrades to `Segoe UI` for text and **Courier New for every numeral** — the worst possible
  fallback for a money app. It requests Plus Jakarta Sans `300;400;500;600;700;800` (300 never used) and
  JetBrains Mono `400;500;600`, while `.font-mono` is used at weight 700/800 in six places, so every bold
  monospace numeral in the app today is browser-synthesised faux bold. Decide whether that bold becomes real.
- The export font is a **separate asset that cannot be the same file**. `exporters.resolve_font()` needs a
  `.ttf` for Pillow covering Latin + Thai + CJK; the only entry in its candidate list covering all three is
  macOS `Arial Unicode.ttf`, which does not exist on this Windows machine, and Plus Jakarta Sans has neither
  Thai nor CJK. With no font it raises rather than rendering tofu, so the PDF and poster simply fail. So the
  repo needs both webfonts for the browser and a Unicode TTF for Pillow, and `TOURIST_EXPORT_FONT` points at
  the latter.
- `utils.js` fetches country flags from `flagcdn.com` for a ~50-country list — a second remote dependency,
  and a country can have a flag with no accent because three divergent country lists exist (13-entry accent
  table, ~30-entry emoji flags, ~50-entry flag URLs). Emoji flags are the offline-safe alternative, but the
  export path already strips pictographs (`_labels()`) because no Unicode font carries them.
- The poster and Excel palette (`#101820`, `#F2F5F7`, `#8FB8D8`, `#2A3B49`, `#A9BECD`, `#F2C14E`, `#6C8598`,
  `#E8EEF3`) shares nothing with the splitter tokens. A well-meaning "unify the tokens" pass must not
  recolour the exports; decide explicitly whether the two palettes converge or stay separate.
- `assets/hero.png` and `public/icons.svg` are local already; `lucide-react` bundles. Those are fine.
- **Map tiles are the third remote dependency, and the largest.** The element inventory found the numbered map
  to be the only planner element Auto-Bill's visual language cannot reach — it has no spatial primitive and no
  map dependency at all. Whatever draws it fetches tiles, which is exactly what a Taipei hotel with no network
  cannot do. Decide whether tiles are cached ahead of the trip, whether a static rendered map image suffices
  offline, or whether the numbered list is the offline fallback for the map.

Decide at least: self-host or CDN, and if self-hosted where the files live and under what licence record;
which families and weights ship, in `woff2` for the browser and `.ttf` for Pillow; whether bold monospace
becomes a real weight; what replaces `flagcdn.com`; whether the export palette and the UI tokens converge;
and what the app is contractually allowed to do when offline during a trip.
