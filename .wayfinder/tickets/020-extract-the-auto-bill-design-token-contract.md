---
id: WF-020
title: Extract the Auto-Bill design token contract
status: closed
labels:
  - "wayfinder:research"
parent: WF-MAP-002
assignee: research-agent
blocked_by: []
---

# Extract the Auto-Bill design token contract

## Question

What is the complete, exact token set that defines the Auto-Bill visual language, expressed so a Tailwind
rebuild can reproduce it without inventing a single value?

## Context

This is AFK reading work against local files, resolvable in one session. The source of truth is
`E:\ML_PROJECT\trip_planner\Auto-Bill-Splitter\src\index.css` (2458 lines) plus
`src/utils.js` for the country-accent table and `src/App.jsx:59` for how the accent is injected at runtime.

Already sampled, to be completed rather than re-derived:

- Light theme: `--bg-primary #FCFBF9`, `--bg-secondary #F3F1EC`, `--bg-card #FFFFFF`,
  `--bg-card-border #1A1A1A`, text `#1A1A1A` / `#4D4D4D` / `#737373`, accent `#A30000` with
  `--color-accent-light #F7ECEC` and hover `#800000`, success `#006644`, danger `#D11A2A`,
  warning `#C46200`, each with a `-light` companion.
- Dark theme under `:root.dark`: `#121212` / `#1C1C1C` / `#181818`, border `#3A3A3A`, accent `#E53E3E`.
- Shadows are the signature: `1px/3px/5px` hard offsets at zero blur, `#1A1A1A` in light and `#3A3A3A` in
  dark. `--glass-blur: 0px`. Reproducing these as ordinary soft Tailwind shadows would destroy the look.
- Typography: Plus Jakarta Sans (300–800) for text and JetBrains Mono (400–600) for numerals, pulled from
  a Google Fonts CDN `@import` at line 1 — note that a local-only, sometimes-offline app cannot rely on
  a CDN, and the planner's PDF and poster exports already need a self-hosted Unicode TTF covering Latin,
  Thai, and CJK (`exporters.resolve_font()`).
- The country accent overrides `--color-accent`, `--color-accent-light`, and `--color-accent-hover` at the
  document root per destination, from a 13-country table with per-country hex values.

Produce: the full palette for both themes, the shadow and border scale, the radius scale, the spacing and
type scale actually used, transition durations and easings, the breakpoints (`992px` appears in the
landing grid), the z-index layers, and the accent-override contract — each mapped to the Tailwind theme key
it will occupy. Name every place the CSS hardcodes a colour outside the token set, because those are the
values a rebuild silently loses.

## Resolution comments

### 2026-07-31 — Extracted from the Auto-Bill sources

- The token set is **23 custom properties in light** (`index.css:3`–`31`), **21 redefined in dark**
  (`:33`–`59`), plus **5 local `--hero-panel-*` vars** on `.hero-banner-card` (`:461`–`465`) that
  are rewritten at runtime from the uploaded banner image. `--text-muted #737373` is the only
  colour identical in both themes; `--bg-card-hover` is identical to `--bg-card` in light.
  `src/App.css` is a single comment line — there is no second stylesheet.
- **The shadow scale is the whole identity and Tailwind's default must be replaced, not extended.**
  `1px/3px/5px` at `0px` blur and `0px` spread, coloured exactly `--bg-card-border`
  (`#1A1A1A` light / `#3A3A3A` dark). A fourth **2px rung exists only as literals** (`:328`, `391`,
  `402`, `422`, `428`, `758`) and is the button shadow — it pairs with `translate(-1px, -1px)` on
  hover so the shadow appears to grow, and `.btn-hero-cta:active` returns to `1px`. Emitting
  Tailwind's soft-blurred `shadow-md` anywhere destroys the look. Exact `boxShadow` config is in
  the artifact §2.
- **Two incompatible radius systems coexist.** Cards/buttons/inputs/avatars are `2px` (10 uses);
  charts/badges/settings/modal run `0.375rem`–`1rem` (20 uses), plus `50%` and `9999px` pills.
  `.setup-card` alone is `4px` (`:276`). This reads as an unfinished restyle from rounded to sharp.
  Reproduce both; normalising it silently is a visible change.
- **Counts:** 17 font sizes in CSS + 5 more only in JSX (`0.7rem`, `0.725rem`, `0.8rem`, `0.85rem`);
  5 weights; 8 letter-spacings; 6 line-heights; 8 transition durations across 3 easings
  (`ease`, `ease-out`, one `cubic-bezier(0.16, 1, 0.3, 1)` on the modal only); **16 `@media` blocks
  at 5 distinct max-widths** (1200 / 992 / 768 / 576 / 480 — all desktop-first, so a mobile-first
  Tailwind `screens` map will drift, and `992px` is not Tailwind's `lg` `1024px`);
  **7 z-index values** (0,1,2,3,5,10,999) with nothing between 10 and the modal backdrop;
  **5 keyframes of which 2 (`scale-up`, `pulse-glow`) are never referenced.**
- **Font hosting is broken two ways.** The Google Fonts CDN `@import` at `index.css:1` is
  render-blocking and unreachable offline — and this app is local-first (`localStorage` only), so
  on a plane it falls back to `Segoe UI` + `Courier New`. It requests Plus Jakarta Sans
  `300;400;500;600;700;800` (**300 never used**) and JetBrains Mono `400;500;600` — but `.font-mono`
  is combined with weight **700/800** at six places in `Dashboard.jsx`, so **every bold monospace
  numeral in the app is a browser-synthesised faux bold.** Self-host Jakarta 400–800 and Mono
  400–600 as `woff2` (add Mono 700 only if we decide the bold should be real).
- **The planner's export font is a separate asset and cannot be the same file.**
  `exporters.resolve_font()` needs a **`.ttf`** for Pillow, covering Latin+Thai+CJK; the only
  candidate in `FONT_CANDIDATES` that covers all three is macOS `Arial Unicode.ttf`. Plus Jakarta
  Sans has no Thai and no CJK, so it could never serve. Ship `Noto Sans` + `NotoSansThai-Regular`
  + `Noto Sans TC` (or one CJK TC face + the Thai face) as in-repo `.ttf` and point
  `TOURIST_EXPORT_FONT` at it. The poster/Excel palette (`#101820`, `#F2F5F7`, `#8FB8D8`,
  `#2A3B49`, `#A9BECD`, `#F2C14E`, `#6C8598`, `#E8EEF3`) shares nothing with the splitter tokens —
  a "unify the tokens" pass must not recolour the exports.
- **Accent-override contract:** exactly three properties — `--color-accent`,
  `--color-accent-light`, `--color-accent-hover` — written as **inline styles on
  `document.documentElement`** by `App.jsx:64`–`66`, from a 13-country table
  (`utils.js:1`–`15`, all Tailwind `-600`/`-700` pairs with `rgba(…, 0.12)` tints). Theme is a
  `.dark` class on the same element. **Because inline styles beat `:root.dark`, the dark accent
  triple (`#E53E3E` / `#3B1C1C` / `#FC8181`) is dead code** the moment a trip has a country —
  which is always, post-setup. The `accentLight` values are 12% alpha tuned against a near-white
  page and composite over `#121212` in dark; nobody chose that.
- **The fallback accent is blue, not the house red.** Both documented fallbacks —
  no-country (`utils.js:17`–`28`) and country-not-in-table (`:151`–`160`) — return
  `#2563eb` / `#1d4ed8` / `rgba(37,99,235,0.12)`. They **disagree on currency**: `CNY @ 4.90`
  versus `USD @ 1.0`. `CNY` and the `alipay_splitter_*` localStorage keys are fossils of the
  app's origin. Also three separate country lists exist (13-entry accent table, ~30-entry
  `commonFlags`, ~50-entry `countryCodes` feeding remote `flagcdn.com` images) — a country can have
  a flag and no accent, and `flagcdn.com` is a second network dependency in an offline app.
- **`#8b5cf6` (violet-500) is a fifth semantic colour with no custom property** — 8 uses across
  brand gradient, `highlight-focus` ring, `.stat-icon-wrapper.purple`, insights stripe, chart
  gradient, `.mode-badge.m-man`, and the manual split tab. Add `--color-purple`/`-light` or the
  rebuild ships four semantics where the original has five.
- **Stale blue from a previous accent theme survives in a red-accented app:**
  `rgba(59,130,246,0.15)` chart glow (`:1427`) and `rgba(59,130,246,0.03)` table row hover
  (`:1797`). Reproduce verbatim or fix deliberately — not by accident.
- **The category and participant colour palettes are data, not decoration, and they live in JSX,
  not CSS.** 6 categories + 6 fallbacks (`Dashboard.jsx:399`–`412`) and 7 participant colours
  **duplicated verbatim** in `Dashboard.jsx:416`–`424` and `TransactionModal.jsx:14`–`22`, with a
  third bare copy at `TransactionModal.jsx:593`. The donut, meters, settlement cards, row stripes
  and badges all read from them. Tints are built by string concatenation `${color}NN` at five
  undocumented alphas (`10`/`12`/`15`/`30`/`40`).
- **Off-token literals that a CSS-only port loses entirely.** The landing hero panel is a whole
  second palette, always dark regardless of theme (`#121212`, `#111111`, `#60a5fa`, `#a78bfa`,
  `#9ca3af`, `#f3f4f6`, `#6b7280`, `#e5e5e5`, six `rgba(255,255,255,…)` steps).
  `.btn-hero-cta` uses pure `#000000` shadows (`:612`, `623`, `629`) rather than the border token,
  so in dark mode that one button keeps a black shadow — the comment at `:602` suggests it is
  intentional. `#ffffff` appears 12 times as on-accent text with no token. `#0f172a` is the
  tooltip. Validation-panel borders use `rgba(239,68,68,0.2)` / `rgba(16,185,129,0.2)` instead of
  the danger/success tokens. Non-integer sizes: `4.5px`, `2.5px`, `1.5px`, `0.45rem`.
  **~28 classes are styled only inline** — the entire filter-dimming interaction
  (`opacity 0.4`/`0.35`, `1.5px solid <colour>`, `${color}10`/`12` fills) exists nowhere in the
  stylesheet.
- **AMBIGUITIES left unresolved (7, numbered in the artifact):** (1) dark accent triple is dead;
  (2) `.setup-card` `4px` versus the house `2px`; (3) the two radius systems; (4) Mono 700/800 not
  loaded; (5) the two fallbacks disagree on currency/rate; (6) three divergent country lists;
  (7) `.landing-wizard-side` declared twice (`:156`–`162` dead, `:253`–`261` wins and adds the
  radial accent wash). Plus five inline/CSS contradictions where the inline wins and the CSS is
  dead: `.meter-bar-container` pill radius never renders (JSX forces `6px`/`3px`),
  `.avatar-circle-sm` renders at three different sizes, `.category-badge` borders differ between
  recent list and table, `.filters-grid`'s grid definition **and its `768px` media query are both
  dead** (JSX makes it a flex-wrap row), and the selected-day bar highlight is a no-op because
  `backgroundColor` cannot beat the `background` shorthand's gradient.
- **`--glass-blur: 0px` means there is no glassmorphism.** Both
  `backdrop-filter: blur(var(--glass-blur))` consumers (`:1143` navbar, `:2040` modal) are no-ops,
  and `.glassmorphic-card`'s only declaration is `box-shadow: var(--shadow-lg)`. Keep the hook —
  it is the documented off-switch — but do not assume it does anything.
- Full contract: [`020-auto-bill-token-contract.md`](../artifacts/020-auto-bill-token-contract.md)
