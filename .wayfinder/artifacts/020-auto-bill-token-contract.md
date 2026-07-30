# Auto-Bill design token contract

Extracted 2026-07-31 from `E:\ML_PROJECT\trip_planner\Auto-Bill-Splitter\` at the state on disk.
Sources, in order of authority:

| File | Lines | Role |
|---|---|---|
| `src/index.css` | 2458 | the whole stylesheet; only `:root` / `:root.dark` blocks are tokens |
| `src/utils.js` | 231 | `COUNTRIES_DB` accent table + `getCountryDetails()` fallback |
| `src/App.jsx` | 140 | runtime accent injection (`:59`–`77`), theme class on `<html>` (`:80`–`90`) |
| `src/components/Dashboard.jsx` | 2183 | category/participant colour arrays, hero-panel runtime vars, inline overrides |
| `src/components/TransactionModal.jsx` | 694 | duplicate participant colour array, inline overrides |
| `src/components/SetupWizard.jsx` | 596 | inline overrides |
| `index.html` | 14 | no styling; `<title>Trip Splitter Pro</title>`, favicon `/favicon.svg` |
| `src/App.css` | 1 | **empty** — one comment line, no rules. Nothing to port. |

Everything below is verbatim. Where the CSS contradicts itself or the JSX, it is flagged
**AMBIGUITY** rather than resolved.

---

## 1. Colour palette — every custom property, both themes

23 properties in light (`:root`, `index.css:3`–`31`), 21 in dark (`:root.dark`, `:root:33`–`59`).
Dark does **not** redefine `--glass-blur`; it inherits `0px`.

| Custom property | Light (`:root`) | Dark (`:root.dark`) | Semantic role |
|---|---|---|---|
| `--bg-primary` | `#FCFBF9` | `#121212` | page / app background (`body`, `.setup-wrapper`, `.dashboard-grid`, `.landing-wizard-side`) |
| `--bg-secondary` | `#F3F1EC` | `#1C1C1C` | recessed surface: sidebar, inputs, table `th`, tags, avatar circles, split-tab track, import dropzone |
| `--bg-card` | `#FFFFFF` | `#181818` | raised surface: `.card`, `.setup-card`, `.modal-card`, `.top-navbar`, `.trip-summary-box`, `.donut-hole`, active split tab |
| `--bg-card-hover` | `#FFFFFF` | `#1F1F1F` | hover surface. **Identical to `--bg-card` in light** — no visible hover delta on white cards; only used by `.recent-row-item:hover` (`:1613`), whose base is `--bg-secondary`, so it does read there |
| `--bg-card-border` | `#1A1A1A` | `#3A3A3A` | **the single border colour for the whole app** and the colour of every hard shadow; also the meter-bar track (`:1034`), scrollbar thumb (`:2430`), empty-donut fill (`Dashboard.jsx:433`) |
| `--text-primary` | `#1A1A1A` | `#F5F5F5` | body copy, headings, values |
| `--text-secondary` | `#4D4D4D` | `#A3A3A3` | labels, sub-copy, inactive tab text, table `th` |
| `--text-muted` | `#737373` | `#737373` | **same in both themes.** Placeholders, section eyebrows, meta, icons, scrollbar-thumb hover |
| `--color-accent` | `#A30000` | `#E53E3E` | brand accent — **overwritten at runtime per country, see §8** |
| `--color-accent-light` | `#F7ECEC` | `#3B1C1C` | accent tint surface (active tab, badges, icon wells) — **overwritten at runtime** |
| `--color-accent-hover` | `#800000` | `#FC8181` | accent hover / gradient end-stop — **overwritten at runtime** |
| `--color-success` | `#006644` | `#38A169` | positive: settled, valid manual split, THB totals, "selected" split mode |
| `--color-success-light` | `#EAF5F0` | `#1C3B24` | success tint surface; also the focus ring colour at `:769` |
| `--color-danger` | `#D11A2A` | `#E53E3E` | destructive: delete, reset trip, invalid split |
| `--color-danger-light` | `#FCECEE` | `#3B1C1C` | danger tint surface **and** danger *border* colour (`.btn-reset-trip` `:1231`, and 4 inline JSX borders) |
| `--color-warning` | `#C46200` | `#DD6B20` | caution: "single payer" split mode, shopping-ish accents |
| `--color-warning-light` | `#FAF3EC` | `#3B2A1C` | warning tint surface |
| `--shadow-sm` | `1px 1px 0px 0px #1A1A1A` | `1px 1px 0px 0px #3A3A3A` | see §2 |
| `--shadow-md` | `3px 3px 0px 0px #1A1A1A` | `3px 3px 0px 0px #3A3A3A` | see §2 |
| `--shadow-lg` | `5px 5px 0px 0px #1A1A1A` | `5px 5px 0px 0px #3A3A3A` | see §2 |
| `--glass-blur` | `0px` | *(inherits `0px`)* | see §2 note |

Non-theme locally-scoped properties, declared on `.hero-banner-card` (`index.css:461`–`465`),
overwritten at runtime from the uploaded banner image (`Dashboard.jsx:162`–`165`, `:335`).
Values are **space-separated RGB triplets**, not hex, because they are consumed through
`rgb()`/`rgba()`:

| Property | Default | Consumed at |
|---|---|---|
| `--hero-panel-dark-rgb` | `18 24 30` | `:526` gradient stop 0% |
| `--hero-panel-mid-rgb` | `28 38 48` | `:527` gradient stop 62% |
| `--hero-panel-edge-rgb` | `42 58 72` | `:528` stop 100%, `:562` right-edge fade |
| `--hero-panel-glow-rgb` | `56 76 92` | `:521`–`522` corner radial glow |
| `--hero-panel-image` | `none` | `:545` blurred wash behind hero text |

**AMBIGUITY 1 — the dark accent triple is dead code.** `App.jsx:64`–`66` writes
`--color-accent` / `--color-accent-light` / `--color-accent-hover` as **inline styles on
`document.documentElement`**. An inline style beats both `:root` and `:root.dark`. A trip always
has a country once setup completes, so `#E53E3E` / `#3B1C1C` / `#FC8181` never render, and neither
does light's `#A30000` / `#F7ECEC` / `#800000`. They are the pre-setup wizard palette only.
A consequence: the country `accentLight` values are `rgba(…, 0.12)` tuned against a near-white
page; in dark mode they composite over `#121212` instead. Nobody chose that.

---

## 2. Shadow scale and border scale

### The shadow scale is the signature. Zero blur, hard offset, border-coloured.

Format is `<x> <y> 0px 0px <colour>` — **the third value (blur) is always `0px`** and the fourth
(spread) is always `0px`. The colour is always exactly `--bg-card-border`.

| Token | Light | Dark | Applied to |
|---|---|---|---|
| `--shadow-sm` | `1px 1px 0px 0px #1A1A1A` | `1px 1px 0px 0px #3A3A3A` | `.trip-summary-box` `:961`, `.stat-card` `:1261`, `.recent-row-item` `:1607`, active split tab `:2146`, `.avatar-preview-card.clickable:hover` `:2208` |
| `--shadow-md` | `3px 3px 0px 0px #1A1A1A` | `3px 3px 0px 0px #3A3A3A` | `.setup-card` `:275`, `.hero-banner-card` `:481`, `.card` `:704`, `.settlement-item` (`Dashboard.jsx:1512`) |
| `--shadow-lg` | `5px 5px 0px 0px #1A1A1A` | `5px 5px 0px 0px #3A3A3A` | `.setup-card.glassmorphic-card` `:282`, `.hero-banner-card:hover` `:493`, `.bar-tooltip-popup` `:1461`, `.modal-card` `:2039` |

An **unnamed 2px rung** exists only as literals — never tokenised. It is the interactive/button
shadow, and it pairs with a `translate(-1px, -1px)` lift so the shadow appears to grow:

| Literal | Line(s) | Use |
|---|---|---|
| `2px 2px 0px 0px var(--bg-card-border)` | `328`, `391`, `402`, `422`, `428`, `758` | active wizard step, `.btn-primary`, `.btn-secondary`, `.btn-outline:hover`, `.btn-success`, focused input |
| `3px 3px 0px 0px var(--bg-card-border)` | `396`, `409`, `433` | `:hover` of primary / secondary / success (same as `--shadow-md` but written literally) |
| `1px 1px 0px 0px var(--bg-card-border)` | `416`, `2224` | `.btn-outline` rest, `.avatar-circle` (same as `--shadow-sm`, written literally) |
| `inset var(--shadow-sm)` | `1523` | `.donut-hole` — resolves to `inset 1px 1px 0px 0px <border>` |

Soft shadows exist, and they are the only soft shadows in the app. Four of them:

| Literal | Line | Element | Note |
|---|---|---|---|
| `0 2px 6px rgba(0, 0, 0, 0.3)` | `658` | banner hover pill | off-token |
| `0 10px 20px -5px var(--color-accent-hover)` | `1061` | `.sidebar-grand-total` | accent-coloured glow |
| `0 12px 24px -5px var(--color-accent-hover)` | `1080` | `.sidebar-grand-total:hover` | accent-coloured glow |
| `0 2px 6px rgba(59, 130, 246, 0.15)` | `1427` | `.bar-pillar-fill` | **blue-500 alpha, stale from an earlier blue accent theme; the accent is now red** |
| `0 4px 10px var(--color-accent-light)` | `1433` | `.bar-pillar-fill` hover | |

Plus two focus rings, which are spread-only (`0 0 0 3px`):
`rgba(139, 92, 246, 0.15)` at `:764` and `var(--color-success-light)` at `:769`.

> ### Tailwind's default shadow scale must be overridden, not extended.
> Tailwind's `shadow-sm` / `shadow` / `shadow-md` / `shadow-lg` are all soft-blurred, multi-layer
> `rgb(0 0 0 / …)` values. Emitting `shadow-md` in a rebuild produces a blurred grey drop shadow
> and **destroys the entire visual identity** — the hard offset against a 1px near-black border is
> what makes this look like the app it is. Replace the whole `boxShadow` scale:
>
> ```js
> // tailwind.config.js — theme.extend.boxShadow
> boxShadow: {
>   none: 'none',
>   sm:   '1px 1px 0px 0px var(--bg-card-border)',
>   DEFAULT: '2px 2px 0px 0px var(--bg-card-border)', // the untokenised button rung
>   md:   '3px 3px 0px 0px var(--bg-card-border)',
>   lg:   '5px 5px 0px 0px var(--bg-card-border)',
>   'inner-sm': 'inset 1px 1px 0px 0px var(--bg-card-border)',
>   // the four soft exceptions, kept explicit so they cannot be reached by accident:
>   'pill':        '0 2px 6px rgba(0, 0, 0, 0.3)',
>   'accent-glow': '0 10px 20px -5px var(--color-accent-hover)',
>   'accent-glow-hover': '0 12px 24px -5px var(--color-accent-hover)',
>   'bar':         '0 2px 6px rgba(59, 130, 246, 0.15)',
>   'bar-hover':   '0 4px 10px var(--color-accent-light)',
> },
> ```
> Route the colour through the CSS variable rather than baking `#1A1A1A`, so `:root.dark` keeps
> flipping shadows to `#3A3A3A` for free. Also set
> `theme.extend.dropShadow` / `ringWidth` nowhere — nothing in the source uses them.

### Border scale

There is **one border colour** (`--bg-card-border`) and six widths. No `--border-*` token exists;
widths are literals.

| Width | Style | Count | Where |
|---|---|---|---|
| `1px` | `solid` | 28 × `border`, 5 × `border-top`, 5 × `border-bottom`, 3 × `border-right` | the default everywhere: cards, inputs, tags, avatars, table rows, navbar, modal header/footer, sidebar edge |
| `1px` | `dashed` | 2 (`:970` `.summary-row-stat`, `:2106` `.modal-split-section`) | separators |
| `1.5px` | `solid` | 1 (`:1396` `.bar-chart-container` bottom) | chart axis. Also `.progress-line-4` `height: 1.5px` (`:336`) as a background, not a border |
| `2px` | `solid` | 5 (`:1983` `.backup-card-header`, `:2149`–`2152` active split-tab underlines) | emphasis underline |
| `2px` | `dashed` | 1 (`:2008` `.import-action-zone`) | dropzone |
| `4px` | `solid` | 1 (`:712` `.card-title` left rule) + JSX `borderLeft: '4px solid …'` at `Dashboard.jsx:865`, `:1510`, `:1578` | category / accent stripe |
| `4.5px` | `solid` | 5 (`:873` `.currency-info-box`, `:1333`–`1336` `.insights-card.border-left-*`) | insight-card left stripe. **Non-integer px — Tailwind needs `borderWidth: { '4.5': '4.5px' }`** |

Focus ring is an `outline`, not a border: `outline: 2.5px solid var(--color-accent)` with
`outline-offset: 2.5px` (`:2443`–`2444`). Also non-integer.

> **`--glass-blur` note.** It is `0px` in both themes, and its only two consumers are
> `backdrop-filter: blur(var(--glass-blur))` on `.top-navbar` (`:1143`) and `.modal-card` (`:2040`).
> Both are therefore **no-ops**. The class name `.glassmorphic-card` (`:281`) is vestigial: its
> only declaration is `box-shadow: var(--shadow-lg)`. There is no glassmorphism in this app.
> Real backdrop blur exists in exactly three unrelated places: `blur(2px)` `:645`,
> `blur(4px)` `:1524` and `:2026`, and a `filter: blur(18px) saturate(1.18) contrast(1.05)` `:548`.
> A rebuild should keep the `--glass-blur` hook (it is the documented off-switch) but must not
> assume it does anything today.

---

## 3. Radius scale, spacing, and the type scale

### Radius — 11 distinct values, two vocabularies mixed

| Value | Count | Where |
|---|---|---|
| `2px` | 10 | **the house radius**: `.card`, `.hero-banner-card`, `.btn`, inputs, `.tag-item`, `.hero-banner-badge`, `.btn-hero-cta`, `.avatar-circle`, `.avatar-circle-sm`, `.progress-step-4 .step-num-4` |
| `4px` | 1 | `.setup-card` (`:276`) — **AMBIGUITY 2: the wizard card is `4px` while every other card is `2px`.** Deliberate or leftover, cannot tell from the source |
| `0.25rem` | 1 | `.bar-pillar-fill` top corners: `0.25rem 0.25rem 0 0` (`:1425`) |
| `0.25rem` | 1 | `.btn-remove-icon` (`:1920`) |
| `0.375rem` | 5 | `.bar-tooltip-popup`, `.action-btn`, `.badge-day`, `.mode-badge`, split `.tab-btn` |
| `0.5rem` | 8 | `.tab-link`, `.btn-reset-trip`, `.stat-icon-wrapper`, `.settings-people-row`, `.backup-icon`, `.split-modes-tabs`, `.avatar-preview-card`, `.manual-validation-panel` |
| `0.625rem` | 2 | `.currency-info-box`, `.recent-row-item` |
| `0.75rem` | 4 | `.feature-icon`, `.trip-summary-box`, `.stat-card`, `.import-action-zone` |
| `1rem` | 3 | `.wizard-step-header .step-icon`, `.sidebar-grand-total`, `.modal-card` |
| `50%` | 6 | circles: `.tag-remove`, `.theme-toggle-btn`, `.donut-chart`, `.donut-hole`, `.legend-dot`, `.modal-close-btn` |
| `9999px` | 6 | pills: `.app-logo-badge`, banner overlay pill, `.meter-bar-container`, `.meter-bar-fill`, `.category-badge`, scrollbar thumb |

**AMBIGUITY 3 — two radius systems coexist.** The card/button/input layer is `2px` (sharp,
brutalist). The chart/badge/settings layer is `0.375rem`–`1rem` (soft, conventional). They sit
next to each other on the same screen. This looks like an incompletely finished restyle from a
rounded design to a sharp one. Reproduce both; do not normalise.

### Spacing — every value that appears

`padding`: `0`, `1px`, `0.1875rem`, `0.22rem`, `0.25rem`, `0.375rem`, `0.5rem`, `0.625rem`,
`0.7rem`, `0.75rem`, `0.875rem`, `1rem`, `1.25rem`, `1.5rem`, `1.75rem`, `2rem`, `2.5rem`, `3rem`,
`4rem`, `6rem`, plus two px pairs `32px 24px` and `36px 40px` (`:684`, `:511`).
Composites in use: `0.1875rem 0.625rem`, `0.22rem 0.75rem`, `0.25rem 0.625rem`,
`0.375rem 0.625rem`, `0.375rem 0.75rem`, `0.5rem 0`, `0.5rem 0.75rem`, `0.5rem 0.875rem`,
`0.5rem 1rem`, `0.625rem 0.875rem`, `0.625rem 1.25rem`, `0.7rem 1.75rem`, `0.875rem 1.25rem`,
`1rem 0`, `1rem 1.25rem`, `1rem 1.5rem`, `1rem 2rem`, `1.25rem 0.875rem`, `1.25rem 1.75rem`,
`1.5rem 3rem`, `2rem 1.5rem`, `4rem 2rem`, `6rem 1.5rem 3rem 1.5rem`, `3rem !important`.

`gap`: `0.25rem`, `0.375rem`, `0.5rem`, `0.75rem`, `0.875rem`, `1rem`, `1.25rem`, `1.5rem`,
`2rem`, `2.5rem`.

`margin`: `0`, `auto` (`margin-top`), `0.125rem`, `0.25rem`, `0.375rem`, `0.5rem`, `0.6rem`,
`0.75rem`, `1rem`, `1.15rem`, `1.25rem`, `1.5rem`, `1.75rem`, `2rem`, `2.5rem`, `3rem`, `4rem`,
`0.625rem` (`margin-right`), plus shorthands `0.375rem 0` and `1.25rem 0`.

Off-grid values a rebuild must add explicitly, because Tailwind's default scale has no equivalent:
`0.1875rem` (=3px), `0.22rem`, `0.6rem`, `0.7rem`, `1.15rem`, `1.85rem`, `4.5px`, `2.5px`,
`1.5px`, `0.45rem`.

Fixed sizes / track widths (all literals, none tokenised):

| Value | Where |
|---|---|
| `320px` | sidebar column `:890`; `.hero-banner-card` first track `minmax(320px, 34%)` `:468` |
| `260px` | `.hero-banner-card` `height`/`min-height`/`max-height` — pinned three ways `:473`–`475` |
| `220px` | mobile hero image height `:694`; `.settings-people-list` `max-height` `:1894` |
| `200px` | `.vertical-chart-view` height `:1384`; `.no-data-chart` height `:1584` |
| `180px` | `.donut-chart-container` `:1500`–`1501`; `.max-width-splits` `:1858` |
| `140px` | `.text-truncate` max-width `:991` |
| `95px` | `.recent-meta` width `:1621` |
| `60px` | `.transactions-table .width-row` `:1801` |
| `32px` / `34px` | `.bar-wrapper-item` min-width `:1407` / `.bar-interactive-pillar` max-width `:1414` |
| `32px` | `.hero-banner-content::after` fade width `:560` |
| `16px 16px` | hero dot-grid `background-size` `:149` |
| `6px` | scrollbar width and height `:2423`–`2424` |
| `520px` / `580px` / `540px` / `840px` | `.setup-card` / `.hero-content` / `.hero-description` / `.modal-card` max-widths |
| `92vh` | `.modal-card` max-height `:2033` |
| `300px` | `.person-meters-list` max-height `:1005` |
| `18px` | `.hero-banner-content::before` `inset: -18px` `:544` |
| minmax tracks | `220px` (stat cards `:1251`, insights `:1322`), `130px` (avatar grid `:2162`), `280px` (settlement grid, `Dashboard.jsx:1495`) |
| grid ratios | `1.1fr 0.9fr` `:116`, `1fr 1.2fr` `:1302`, `2fr 1fr 1fr auto` `:1714`, `1fr 1.5fr auto` `:2270`, `minmax(320px,34%) minmax(0,1fr)` `:468` |

### Type scale

Two families only.

- **Plus Jakarta Sans** — everything. Declared once, on `body` (`:69`):
  `'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`
- **JetBrains Mono** — numerals only, via the single utility `.font-mono` (`:2371`–`2373`):
  `'JetBrains Mono', 'Courier New', Courier, monospace`
- Inputs re-inherit with `font-family: inherit` (`:752`) so form fields stay Jakarta.

Sizes present: `0.65rem`, `0.6875rem`, `0.75rem`, `0.8125rem`, `0.875rem`, `0.9375rem`, `0.95rem`,
`1.05rem`, `1.1rem`, `1.15rem`, `1.25rem`, `1.4rem`, `1.5rem`, `1.75rem`, `1.85rem`, `3rem`, and
one fluid `clamp(1.55rem, 2.2vw, 2rem)`.
Weights present in CSS: `500`, `600`, `700`, `800` (body inherits `400`).
Letter-spacings: `-0.03em`, `-0.025em`, `-0.02em`, `-0.01em`, `0.0125em`, `0.025em`, `0.05em`,
`0.075em`.
Line-heights: `1.15`, `1.2`, `1.25`, `1.45`, `1.5` (body default), `1.6`.

Every distinct pairing, by role:

| Size | Weight | Tracking | Leading | Family | Role / selector (`index.css` line) |
|---|---|---|---|---|---|
| `1rem` (implicit) | 400 | — | `1.5` | Jakarta | `body` `:68`–`72` |
| `3rem` | 800 | `-0.03em` | `1.15` | Jakarta | `.hero-headline` `:186`–`191` |
| `clamp(1.55rem,2.2vw,2rem)` | 800 | `-0.03em` | `1.2` | Jakarta | `.hero-title` `:585`–`591` |
| `1.85rem` | 800 | `-0.025em` | `1.2` (parent) | Jakarta | `.sidebar-grand-total .main-price` `:1097`–`1102` (+ `text-shadow: 0 2px 4px rgba(0,0,0,0.15)`) |
| `1.75rem` | — | — | — | emoji | `.sidebar-brand .brand-logo` `:928`–`930` |
| `1.5rem` | 800 | `-0.025em` | — | Jakarta | `.setup-header .brand` `:103`–`111` (gradient-clipped text) |
| `1.5rem` | — | — | — | emoji | `.feature-icon` `:225` |
| `1.4rem` | 800 | `-0.02em` | — | Jakarta | `.wizard-step-header h2` `:358`–`364` |
| `1.25rem` | 800 | `-0.02em` | `1.2` | Jakarta | `.sidebar-brand h1` `:932`–`937` |
| `1.25rem` | 800 | — | `1.2` | Jakarta | `.stat-value` `:1288`–`1292`; `.modal-header h2` `:2052`–`2055` |
| `1.15rem` | 800 | — | — | Jakarta | `.donut-value` `:1541`–`1545` |
| `1.15rem` | — | — | — | emoji | `.card-header-icon .icon` `:1344`–`1346` |
| `1.1rem` | 700 | — | — | Jakarta | `.feature-details h4` `:232`–`237` |
| `1.1rem` | — | — | `1.6` | Jakarta | `.hero-subtext` `:200`–`204` |
| `1.05rem` | 800 | `-0.01em` | — | Jakarta | `.card-title` `:707`–`715` |
| `1.05rem` | 800 | — | `1.25` | Jakarta | `.insights-prices strong` `:1369`–`1373` |
| `1.05rem` | 700 | — | `1.2` | Jakarta | `.sidebar-grand-total .thb-price` `:1105`–`1110` (+ `text-shadow: 0 1px 2px rgba(0,0,0,0.1)`) |
| `0.95rem` | 800 | — | — | Jakarta | `.btn-hero-cta` `:603`–`607` |
| `0.95rem` | — | — | `1.45` | Jakarta | `.hero-description` `:594`–`599` |
| `0.9375rem` | 800 | — | — | Jakarta | `.avatar-circle` `:2211`–`2225` |
| `0.9375rem` | 800 | — | — | Jakarta | `.recent-cost-actions .txn-amount` `:1672`–`1675` |
| `0.9375rem` | 700 | — | — | Jakarta | `.insights-body h5` `:1356`–`1361` |
| `0.875rem` | 800 | — | — | Jakarta | `.modal-split-section .section-title` `:2110`–`2116` (uppercase) |
| `0.875rem` | 700 | — | `1.25` | Jakarta | `.btn` `:372`–`386`; `.btn-text` `:436`–`443`; `.tab-link` `:1166`–`1180`; `.manual-person-name` `:2288`–`2291` |
| `0.875rem` | 400 | — | — | Jakarta | `.wizard-step-header p`, `.input-field`/`.select-field`/`.textarea-field` `:744`–`754`, `.no-items-text` (italic), `.transactions-table`, `.no-data-chart` (italic), `.recent-details .txn-name`, `.backup-grid p`, `.feature-details p` (`line-height 1.5`) |
| `0.8125rem` | 700 | `0.05em` | — | Jakarta | `.app-logo-badge` `:170`–`184` (uppercase) |
| `0.8125rem` | 700 | — | — | Jakarta | `.tag-item` `:826`–`837`; `.rename-form h4` `:1940`–`1946` (uppercase); `.avatar-name` `:2227`–`2235`; `.manual-input-box .input-prefix` `:2299`–`2305` |
| `0.8125rem` | 600 | — | — | Jakarta | `.meter-info` `:1016`–`1022`; `.legend-item` `:1554`–`1559` |
| `0.8125rem` | 500 | — | — | Jakarta | `.landing-footer-credits` `:245`–`251` |
| `0.8125rem` | 400 | — | — | Jakarta | `.summary-row-stat` `:964`–`972`; `.currency-info-box` `:868`–`876`; `.split-descriptor`; `.manual-validation-panel` |
| `0.75rem` | 800 | `0.075em` | — | Jakarta | `.hero-banner-badge` `:572`–`583`; `.sidebar-title` `:947`–`954`; `.sidebar-grand-total span` `:1083`–`1089` — all uppercase |
| `0.75rem` | 800 | `0.05em` | — | Jakarta | `.form-group label` `:736`–`742`; `.transactions-table th` `:1775`–`1784` — uppercase |
| `0.75rem` | 800 | `0.025em` | — | Jakarta | `.card-header-icon h4` `:1348`–`1354` (uppercase) |
| `0.75rem` | 800 | — | — | Jakarta | `.progress-step-4 .step-num-4` `:304`–`316`; `.avatar-circle-sm` `:2247`–`2259` |
| `0.75rem` | 700 | `0.0125em` | — | Jakarta | `.mode-badge` `:1827`–`1835` |
| `0.75rem` | 700 | — | — | Jakarta | `.input-with-label .field-suffix`; `.hero-banner-image-overlay`; `.btn-reset-trip`; `.stat-label` (uppercase); `.badge-day`; `.split-modes-tabs .tab-btn`; `.btn-sm`/`.btn-adjust` |
| `0.75rem` | 600 | — | — | Jakarta | `.stat-subvalue` `:1294`–`1298`; `.insights-prices span`; `.avatar-cost` |
| `0.75rem` | 400 | — | — | Jakarta | `.txn-desc-cell .cell-notes`; `.form-help-text` |
| `0.6875rem` | 800 | `0.025em` | — | Jakarta | `.category-badge` `:1625`–`1635` (uppercase) |
| `0.6875rem` | 700 | — | — | Jakarta | `.progress-step-4 .step-label-4`; `.bar-item-label`; `.donut-label` (uppercase); `.recent-day` |
| `0.6875rem` | 400 | — | — | Jakarta / Mono | `.meter-thb`; `.recent-details .txn-splits-people`; `.bar-tooltip-popup` (mono via `.font-mono` in JSX) |
| `0.65rem` | 700 | `0.05em` | — | Jakarta | `.sidebar-brand .brand-badge` `:939`–`945` (uppercase) — the smallest text in the app |

Utility weights: `.font-semibold` = 600, `.font-bold` = 700 (`:2374`–`2375`).

**AMBIGUITY 4 — JetBrains Mono is used at weights that are not loaded.** `.font-mono` is
combined with weight 700 or 800 at `Dashboard.jsx:943`, `:1324`, `:1366`, `:1613`, `:1620`, `:1800`
(and via `.recent-cost-actions .txn-amount` `font-weight: 800`), but the `@import` requests
JetBrains Mono at `400;500;600` only. Every bold monospace numeral in this app is a
browser-synthesised faux bold. Either self-host JetBrains Mono 700 (changing the look slightly) or
reproduce the synthetic bold deliberately. Say which; do not leave it accidental.

---

## 4. Font loading

`index.css:1`, one line, the whole font strategy:

```css
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
```

Requested: **Plus Jakarta Sans 300, 400, 500, 600, 700, 800** (6 weights) and
**JetBrains Mono 400, 500, 600** (3 weights). Latin subset only — `css2` without `&subset=`
returns whatever `unicode-range` faces Google decides, and Plus Jakarta Sans ships **no Thai and
no CJK coverage at all**.

Actually used: Jakarta 400 (body default), 500, 600, 700, 800 → **300 is imported and never used,
drop it.** Mono: no weight is ever set on `.font-mono` directly, so it renders at whatever the
cascade gives it — 400 by default, but 600/700/800 in the six places noted above, and 700/800 are
not loaded (AMBIGUITY 4).

### Why the CDN `@import` is unusable here

1. **Offline.** The splitter is a local-first app; all state lives in `localStorage`
   (`App.jsx:11`, `:27`, `:41`). It is expected to work on a plane. A CDN `@import` on a plane
   yields the whole `font-family` fallback chain — `-apple-system` / `Segoe UI` on the sans side
   and `Courier New` on the mono side. `Courier New` at `0.6875rem` in a `9999px` pill badge is a
   different app.
2. **`@import` is render-blocking and serialised.** It sits at the top of the only stylesheet, so
   the CSS parser must fetch it before painting, in addition to whatever it costs.
   Even online, this is the worst possible way to load these fonts.
3. **The same import is invisible to any offline/PWA cache** unless the fetch is proxied.

### Self-host requirement

| Family | Weights to self-host | Format | Why |
|---|---|---|---|
| Plus Jakarta Sans | 400, 500, 600, 700, 800 (skip 300) | `woff2` for the browser | all UI text |
| JetBrains Mono | 400, 500, 600 — **plus 700 if AMBIGUITY 4 is resolved toward real bold** | `woff2` for the browser | all numerals |
| A Latin+Thai+CJK Unicode TTF | one regular face is enough | **`ttf`, not `woff2`** | the planner's `exporters.resolve_font()` |

### The planner's export font is a separate, non-overlapping requirement

`Optimizer-Trip-Planner/travel_planner/exporters.py:130`–`139`. `resolve_font()` returns a `Path`
to a **`.ttf`** which Pillow's `ImageFont.truetype()` loads for the 9:16 poster PNG and the trip
PDF. It checks `TOURIST_EXPORT_FONT` first, then `FONT_CANDIDATES` (`exporters.py:65`–`71`):

```
/Library/Fonts/Arial Unicode.ttf
/System/Library/Fonts/Supplemental/Arial Unicode.ttf
/System/Library/Fonts/Supplemental/Ayuthaya.ttf
/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf
/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
```

With no match it **raises** rather than rendering tofu. Two things follow for the rebuild:

- **Pillow cannot use a `woff2`.** The webfont self-host and the export font are two separate
  assets even if they were the same family. Plus Jakarta Sans could not serve as the export font
  anyway: it has no Thai and no CJK, and the Taipei pilot needs CJK.
- **Recommendation.** Self-host `Noto Sans` + `Noto Sans Thai` + `Noto Sans TC` as `.ttf` for the
  exporter (or a single `Noto Sans CJK TC` which carries Latin + CJK, paired with
  `NotoSansThai-Regular.ttf`), and add the chosen path to `FONT_CANDIDATES` or ship it in-repo and
  point `TOURIST_EXPORT_FONT` at it. That removes the current macOS-only dependency on
  `Arial Unicode.ttf`, which is the only candidate in the list that covers all three scripts.
- The poster palette is its own thing and shares nothing with the splitter tokens —
  `#101820`, `#F2F5F7`, `#8FB8D8`, `#2A3B49`, `#A9BECD`, `#F2C14E`, `#6C8598`, and Excel header
  `#E8EEF3` (`exporters.py:156`–`267`, `:501`). Flagged so a "unify the design tokens" pass does
  not silently recolour the exports.

---

## 5. Transitions and animations

### Durations and easings — 8 distinct durations, 3 easings

| Duration | Easing | Property | Line | Element |
|---|---|---|---|---|
| `0.1s` | `ease` | `transform`, `box-shadow` | `385` | `.btn` — the button lift |
| `0.1s` | `ease` | `transform`, `box-shadow` | `613` | `.btn-hero-cta` |
| `0.15s` | *(default)* | `opacity`, `transform` | `1464` | `.bar-tooltip-popup` |
| `0.2s` | *(default)* | `all` | `1178`, `1209`, `1234`, `1693`, `2139`, `2176` | `.tab-link`, `.theme-toggle-btn`, `.btn-reset-trip`, `.action-btn`, split `.tab-btn`, `.avatar-preview-card` |
| `0.2s` | *(default)* | `transform` | `1608` | `.recent-row-item` |
| `0.25s` | *(default)* | `all` | `1426` | `.bar-pillar-fill` |
| `0.3s` | `ease` | `background-color`, `color` | `73` | `body` — the theme cross-fade |
| `0.3s` | `ease` | `opacity` | `643` | `.hero-banner-image-overlay` |
| `0.3s` | `ease` | `all` | `1062` | `.sidebar-grand-total` |
| `0.4s` | `ease-out` | `width` | `1042` | `.meter-bar-fill` — the meter grow |
| `0.5s` | `ease` | `transform` | `668` | `.hero-trip-img` — the slow Ken-Burns zoom on hover |

Plus, from JSX inline styles, `transition: 'all 0.2s ease'` at `Dashboard.jsx:931`, `:1352`,
`:1423`, `:1475` and `transition: 'all 0.3s ease'` at `Dashboard.jsx:855`.

Easings used: `ease` (CSS default keyword, written explicitly), `ease-out`, and one
`cubic-bezier(0.16, 1, 0.3, 1)` (`:2041` — an "easeOutExpo"-ish overshoot-free decel, only on the
modal entrance).

Hover transforms that pair with the shadow scale, and are part of the signature:

| Transform | Line | Element |
|---|---|---|
| `translate(-1px, -1px)` | `395`, `408`, `421`, `432`, `622` | button hover — lifts up-left so the hard shadow appears to grow |
| `translate(0, 0)` | `628` | `.btn-hero-cta:active` — press returns and shadow shrinks to `1px` |
| `translateX(3px)` | `1612` | `.recent-row-item:hover` — slides right |
| `translateY(-3px)` | `1079` | `.sidebar-grand-total:hover` |
| `translateY(-2px)` | `2207` | `.avatar-preview-card.clickable:hover` |
| `scale(1.05)` | `672` | `.hero-trip-img` on wrapper hover |
| `scaleX(1.1)` | `1432` | `.bar-pillar-fill` on hover |
| `scale(1.08)` | `550` | `.hero-banner-content::before` static wash |
| `rotate(-90deg)` | `1509` | `.donut-chart` — starts the conic gradient at 12 o'clock |

### Keyframes — 5 defined, 3 used

| Name | Line | What it does | Used by |
|---|---|---|---|
| `fade-in` | `2392` | `opacity: 0 → 1` | `.animate-fade-in` = `fade-in 0.25s ease-out` (`:2413`). Applied to every tab view and wizard step: `Dashboard.jsx:1041, 1648, 1849, 2113`, `SetupWizard.jsx:263, 366, 473, 534`, `TransactionModal.jsx:489` |
| `slide-down` | `2397` | `translateY(-8px) + opacity 0 → translateY(0) + 1` | `.animate-slide-down` = `slide-down 0.2s ease-out` (`:2417`). One use: `SetupWizard.jsx:389` |
| `slide-up-fade` | `2402` | `translateY(12px) + opacity 0 → translateY(0) + 1` | `.modal-card` (`:2041`), `0.3s cubic-bezier(0.16, 1, 0.3, 1)` |
| `scale-up` | `2387` | `scale(0.95) + opacity 0 → scale(1) + 1` | **never referenced — dead** |
| `pulse-glow` | `2407` | 3-stop expanding white ring: `0 0 0 0 rgba(255,255,255,0.4)` → `0 0 0 10px rgba(255,255,255,0)` at 70% → `0 0 0 0 rgba(255,255,255,0)` | **never referenced — dead** |

Drop `scale-up` and `pulse-glow`, or port them and note they are unused. Do not invent
`animation-iteration-count` for `pulse-glow` — the source never declares one.

---

## 6. Breakpoints

**16 `@media` blocks, 5 distinct widths, all `max-width` (desktop-first).**

| Width | Blocks | What collapses |
|---|---|---|
| `1200px` | `1310` | `.visuals-grid` `1fr 1.2fr` → `1fr`; `.span-cols-full` `span 2` → `span 1` |
| `992px` | `121`, `263`, `895`, `915`, `1126`, `1878` | **the main layout breakpoint.** `.onboarding-landing-grid` `1.1fr 0.9fr` → `1fr` **and `.landing-hero-side { display: none !important }`** — the entire marketing panel is deleted, not stacked; `.landing-wizard-side` padding → `6rem 1.5rem 3rem 1.5rem` (top padding makes room for the absolutely-positioned header); `.dashboard-grid` `320px 1fr` → `1fr`; `.sidebar` loses `height: 100vh` + `position: sticky` → `auto` / `static`; `.main-content` loses `max-height: 100vh` + `overflow-y: auto` → `none` / `visible`; `.settings-cards-grid` `1fr 1fr` → `1fr` |
| `768px` | `675`, `1146`, `1159`, `1719`, `1972` | `.hero-banner-card` → single column, height unpinned (`auto`/`0`/`none`), `.hero-banner-content` swaps `border-right` for `border-bottom` and padding `36px 40px` → `32px 24px`, `::after` edge fade hidden, image wrapper fixed to `220px`; `.top-navbar` → column, `gap: 1rem`, `align-items: stretch`; `.workspace-tabs` → `overflow-x: auto` + `padding-bottom: 0.25rem`; `.filters-grid` `2fr 1fr 1fr auto` → `1fr`; `.backup-grid` `1fr 1fr` → `1fr` |
| `576px` | `1491`, `2090`, `2448` | `.chart-flex-layout` → column centred (donut above legend); `.modal-form-grid` `repeat(2,1fr)` → `1fr` and `.span-full` `span 2` → `span 1`; `.split-modes-tabs` → `flex-wrap: wrap !important`, `gap: 0.375rem !important`, and each `.tab-btn` → `width: calc(50% - 0.25rem) !important` (2×2 grid) |
| `480px` | `2275` | `.manual-row-item` `1fr 1.5fr auto` → `1fr`, `gap` `1.25rem` → `0.5rem` |

> **Tailwind conversion warning.** Tailwind `screens` are **`min-width`** and mobile-first. These
> five are `max-width` and desktop-first, and `992px` is not a Tailwind default
> (`lg` is `1024px`). A mechanical `sm/md/lg/xl` mapping will move the layout break by 32px and
> shift where the hero panel disappears. Either declare the raw max-widths:
> ```js
> screens: {
>   'max-xl':  { max: '1200px' },
>   'max-lg':  { max: '992px'  },
>   'max-md':  { max: '768px'  },
>   'max-sm':  { max: '576px'  },
>   'max-xs':  { max: '480px'  },
> }
> ```
> …or invert every rule to min-width at `481px / 577px / 769px / 993px / 1201px`. Pick one and be
> consistent; mixing them is how `992`/`1024` drift creeps in.

---

## 7. z-index layers

7 distinct values. There is no scale, no token, and no comment explaining the ordering.

| z | Line | Occupant |
|---|---|---|
| `0` | `552` | `.hero-banner-content::before` — blurred image wash |
| `0` | `564` | `.hero-banner-content::after` — right-edge fade |
| `1` | `569` | `.hero-banner-content > *` — every direct child of the hero text panel, lifted above the two pseudo-elements |
| `2` | `299` | `.progress-step-4` — wizard step dots, above `.progress-line-4` |
| `2` | `508` | `.hero-banner-content` — the text panel, above the image column |
| `3` | `646` | `.hero-banner-image-overlay` — "click to upload" scrim |
| `5` | `167` | `.hero-content` — landing hero copy, above the `::before` dot grid |
| `10` | `100` | `.setup-header` — absolutely-positioned brand + theme toggle over the landing grid |
| `10` | `1142` | `.top-navbar` — sticky |
| `10` | `1219` | `.theme-toggle-btn.float` |
| `10` | `1463` | `.bar-tooltip-popup` |
| `999` | `2022` | `.modal-backdrop` — the only layer above everything |

Note the jump from `10` to `999` with nothing between: the modal is deliberately unreachable by
any other stacking context. `.modal-card` itself declares no `z-index`; it relies on being a child
of the backdrop.

---

## 8. The country-accent override contract

### The mechanism

`App.jsx:59`–`77`, a `useEffect` keyed on `[tripSettings]`:

```js
const root = document.documentElement;
if (tripSettings && tripSettings.country) {
  const details = getCountryDetails(tripSettings.country);
  if (details && details.accent) {
    root.style.setProperty('--color-accent', details.accent);
    root.style.setProperty('--color-accent-light', details.accentLight);
    root.style.setProperty('--color-accent-hover', details.accentHover);
  } else { /* removeProperty ×3 */ }
} else { /* removeProperty ×3 */ }
```

**Exactly three properties** are overwritten: `--color-accent`, `--color-accent-light`,
`--color-accent-hover`. Everything else in the palette is theme-only. They are written as **inline
styles on `<html>`**, which is why they beat `:root.dark` (AMBIGUITY 1).

Theme is a **class** on the same element, `App.jsx:80`–`90`: `dark` and `light` are mutually
exclusive (`classList.add('dark'); classList.remove('light')` and vice-versa), persisted to
`localStorage['alipay_splitter_theme']`, default `'light'`. Only `.dark` has a CSS rule; `.light`
is written but never styled — the light palette is the bare `:root`. The class is *also* put on
`.app-container` (`App.jsx:109`) where nothing consumes it.

Note the shape mismatch: `accentLight` in the table is `rgba(r, g, b, 0.12)`, while the theme
tokens it replaces are opaque hex (`#F7ECEC` / `#3B1C1C`). So the accent tint changes from opaque
to 12%-translucent the moment a country is chosen.

### The full 13-country table

`utils.js:1`–`15`. Keys are matched **case-insensitively against the trimmed country name**
(`utils.js:143`).

| Country | currency | symbol | defaultRate | flag | accent | accentHover | accentLight |
|---|---|---|---|---|---|---|---|
| China | `CNY` | `¥` | `4.90` | 🇨🇳 | `#dc2626` | `#b91c1c` | `rgba(220, 38, 38, 0.12)` |
| Japan | `JPY` | `¥` | `0.23` | 🇯🇵 | `#e11d48` | `#be123c` | `rgba(225, 29, 72, 0.12)` |
| South Korea | `KRW` | `₩` | `0.026` | 🇰🇷 | `#2563eb` | `#1d4ed8` | `rgba(37, 99, 235, 0.12)` |
| Singapore | `SGD` | `S$` | `26.6` | 🇸🇬 | `#7c3aed` | `#6d28d9` | `rgba(124, 58, 237, 0.12)` |
| United States | `USD` | `$` | `35.50` | 🇺🇸 | `#1e3a8a` | `#172554` | `rgba(30, 58, 138, 0.12)` |
| United Kingdom | `GBP` | `£` | `45.50` | 🇬🇧 | `#475569` | `#334155` | `rgba(71, 85, 105, 0.12)` |
| Eurozone | `EUR` | `€` | `38.50` | 🇪🇺 | `#0284c7` | `#0369a1` | `rgba(2, 132, 199, 0.12)` |
| Taiwan | `TWD` | `NT$` | `1.12` | 🇹🇼 | `#0d9488` | `#0f766e` | `rgba(13, 148, 136, 0.12)` |
| Hong Kong | `HKD` | `HK$` | `4.55` | 🇭🇰 | `#059669` | `#047857` | `rgba(5, 150, 105, 0.12)` |
| Vietnam | `VND` | `₫` | `0.00142` | 🇻🇳 | `#ea580c` | `#c2410c` | `rgba(234, 88, 12, 0.12)` |
| Malaysia | `MYR` | `RM` | `7.60` | 🇲🇾 | `#ca8a04` | `#a16207` | `rgba(202, 138, 4, 0.12)` |
| Switzerland | `CHF` | `CHF` | `40.50` | 🇨🇭 | `#be185d` | `#9d174d` | `rgba(190, 24, 93, 0.12)` |
| Australia | `AUD` | `A$` | `23.30` | 🇦🇺 | `#16a34a` | `#15803d` | `rgba(22, 163, 74, 0.12)` |

All 13 accents are Tailwind v3 palette colours at the `-600` step with `-700` hovers
(`red-600/700`, `rose-600/700`, `blue-600/700`, `violet-600/700`, `blue-900/950`,
`slate-600/700`, `sky-600/700`, `teal-600/700`, `emerald-600/700`, `orange-600/700`,
`yellow-600/700`, `pink-700/800`, `green-600/700`). The default theme accent `#A30000` is *not*
from that palette — it is a bespoke deep red. So the token default and every override come from
two different colour systems.

### Documented fallbacks — there are two, and they differ

**Fallback A — no country name at all** (`utils.js:17`–`28`, the `if (!countryName)` guard):

| currency | symbol | defaultRate | flag | accent | accentHover | accentLight |
|---|---|---|---|---|---|---|
| `CNY` | `¥` | `4.90` | ✈️ | `#2563eb` | `#1d4ed8` | `rgba(37, 99, 235, 0.12)` |

**Fallback B — a country name that is not in `COUNTRIES_DB`** (`utils.js:151`–`160`):

| currency | symbol | defaultRate | flag | accent | accentHover | accentLight |
|---|---|---|---|---|---|---|
| `USD` | `$` | `1.0` | `commonFlags[cleaned] \|\| "✈️"` (`utils.js:84`) | `#2563eb` | `#1d4ed8` | `rgba(37, 99, 235, 0.12)` |

Both fall back to the same accent triple (Tailwind `blue-600`/`blue-700`/`blue-600 @ 12%`) — so
**the fallback accent is blue, never the `#A30000` house red.** A rebuild that "defaults to the
brand accent" is wrong; the app defaults to blue.

**AMBIGUITY 5 — the two fallbacks disagree on currency and rate.** No-country gives `CNY` at
`4.90`; unknown-country gives `USD` at `1.0` (i.e. 1 THB per USD, obviously a placeholder, not a
rate). Both are reachable. `CNY @ 4.90` is a fossil of the app's origin — `localStorage` keys are
`alipay_splitter_*` (`App.jsx:11`, `:27`, `:41`) and `index.html:7` still says "Premium trip
expense splitter". This is a data bug, not a token question, but a rebuild will inherit it if
copied blind.

**AMBIGUITY 6 — a second, larger country table shadows the accent table.** `utils.js` also carries
`commonFlags` (~30 entries, `:31`–`~90`) and `countryCodes` (~50 entries, `:~95`–`138`, feeding
`https://flagcdn.com/w40/<code>.png` at `:141`). So a country can have a flag *and a remote flag
image* while having **no accent** — it takes Fallback B's blue. Three tables, three different
country lists. Also: `flagcdn.com` is a second network dependency in a supposedly offline app
(`Dashboard.jsx:203`–`216` renders the remote `<img>`).

---

## 9. Values hardcoded outside the token set

These are the values a rebuild silently loses. All paths relative to
`E:\ML_PROJECT\trip_planner\Auto-Bill-Splitter\`.

### 9a. The landing hero panel is an entirely separate, un-tokenised palette

`.landing-hero-side` and children are **always dark regardless of theme** — it hardcodes what
happens to be the dark theme's `--bg-primary`. Nine literals, none in the token set, all from the
Tailwind slate/gray/blue/violet families:

| Value | File:line | Role |
|---|---|---|
| `#121212` | `src/index.css:132` | hero panel background (== dark `--bg-primary`, written literally) |
| `#ffffff` | `src/index.css:133` | hero text |
| `#1A1A1A` | `src/index.css:140` | hero `border-right` (== light `--bg-card-border`, written literally) |
| `rgba(255, 255, 255, 0.02)` | `src/index.css:148` | 1px dot-grid, `background-size: 16px 16px`, `opacity: 0.8` |
| `rgba(255, 255, 255, 0.05)` / `rgba(255, 255, 255, 0.1)` | `src/index.css:174`, `:175` | `.app-logo-badge` fill / border |
| `#60a5fa` | `src/index.css:182` | `.app-logo-badge` text (blue-400) |
| `#60a5fa` → `#a78bfa` | `src/index.css:195` | `.hero-headline span` gradient (blue-400 → violet-400) |
| `#9ca3af` | `src/index.css:202`, `:241` | `.hero-subtext`, `.feature-details p` (gray-400) |
| `rgba(255, 255, 255, 0.03)` / `rgba(255, 255, 255, 0.08)` | `src/index.css:223`, `:224` | `.feature-icon` fill / border |
| `#f3f4f6` | `src/index.css:235` | `.feature-details h4` (gray-100) |
| `#6b7280` | `src/index.css:247` | `.landing-footer-credits` (gray-500) |
| `rgba(255, 255, 255, 0.06)` | `src/index.css:249` | credits `border-top` |

### 9b. `#8b5cf6` — the missing fifth semantic colour

Violet-500 acts as a full semantic ("purple" / manual-split / activities) with **no custom
property**, 8 occurrences:

| File:line | Use |
|---|---|
| `src/index.css:108` | `.setup-header .brand` gradient end-stop (`linear-gradient(135deg, var(--color-accent), #8b5cf6)`) |
| `src/index.css:763` | `.input-field.highlight-focus:focus` border |
| `src/index.css:764` | that focus ring: `0 0 0 3px rgba(139, 92, 246, 0.15)` |
| `src/index.css:1278` | `.stat-icon-wrapper.purple` — `background rgba(139, 92, 246, 0.15)`, `color #8b5cf6` |
| `src/index.css:1334` | `.insights-card.border-left-purple` — `4.5px solid #8b5cf6` |
| `src/index.css:1424` | `.bar-pillar-fill` gradient: `linear-gradient(to top, var(--color-accent), #8b5cf6)` |
| `src/index.css:1853`–`1854` | `.mode-badge.m-man` — `rgba(139, 92, 246, 0.15)` / `#8b5cf6` |
| `src/index.css:2152` | `.split-modes-tabs .tab-btn.mode-manual.active` — `2px solid #8b5cf6` and `color` |

`#a78bfa` (violet-400) is its hover partner at `src/index.css:195` and `:1431`.
Add `--color-purple` / `--color-purple-light` or the rebuild will have four semantic colours where
the original has five.

### 9c. Stale blue from a previous accent theme

The accent is red now. These are rgba blue-500 and never got updated:

| Value | File:line | Use |
|---|---|---|
| `rgba(59, 130, 246, 0.15)` | `src/index.css:1427` | `.bar-pillar-fill` drop shadow |
| `rgba(59, 130, 246, 0.03)` | `src/index.css:1797` | `.transactions-table tbody tr:hover` background |

A red-accented app with blue hover rows and blue chart glow. Reproduce verbatim or fix
deliberately — do not fix it by accident.

### 9d. Off-token literals, remaining CSS

| Value | File:line | Use |
|---|---|---|
| `#111111` | `src/index.css:482`, `:489`, `:503` | `.hero-banner-card` / `.hero-banner-card.card` / `.hero-banner-image-wrapper` background. Near-black but **not** `#121212` and not `#1A1A1A`; a fourth near-black |
| `#000000` | `src/index.css:612`, `:623`, `:629` | `.btn-hero-cta` shadow at 2px/3px/1px. **Pure black, not `var(--bg-card-border)`** — so in dark mode this one button keeps a black shadow while every other element's goes `#3A3A3A`. The comment at `:602` says "Original CTA button styling: do not change this" — apparently intentional |
| `#ffffff` | `src/index.css:327`, `390`, `407`, `427`, `531`, `575`, `590`, `605`, `636`, `1054`, `1100`, `1239` | on-accent text. 12 occurrences of a literal that should be one `--text-on-accent` token |
| `#e5e5e5` | `src/index.css:595` | `.hero-description` colour |
| `rgba(255, 255, 255, 0.85)` / `rgba(255, 255, 255, 0.95)` | `src/index.css:1087`, `:1108` | grand-total label / THB price |
| `rgba(255, 255, 255, 0.15)` | `src/index.css:1074` | grand-total radial sheen |
| `rgba(255, 255, 255, 0.25)` | `src/index.css:657` | banner overlay pill border |
| `rgba(0, 0, 0, 0.4)` | `src/index.css:635` | banner hover scrim |
| `rgba(0, 0, 0, 0.75)` | `src/index.css:654` | banner overlay pill |
| `rgba(0, 0, 0, 0.6)` | `src/index.css:2021` | `.modal-backdrop` |
| `rgba(0, 0, 0, 0.3)` | `src/index.css:658` | pill shadow |
| `rgba(0, 0, 0, 0.15)` / `rgba(0, 0, 0, 0.1)` | `src/index.css:1102`, `:1109` | the app's only two `text-shadow`s |
| `#0f172a` | `src/index.css:1451`, `:1475` | `.bar-tooltip-popup` background **and** its `::after` arrow. slate-900. The only near-black tooltip; unaffected by theme |
| `rgba(239, 68, 68, 0.2)` | `src/index.css:2328` | `.manual-validation-panel.invalid` border — red-500 alpha, not `--color-danger` |
| `rgba(16, 185, 129, 0.2)` | `src/index.css:2333` | `.manual-validation-panel.valid` border — emerald-500 alpha, not `--color-success` |
| `rgba(255, 255, 255, 0.4)` / `…, 0)` | `src/index.css:2408`–`2410` | `@keyframes pulse-glow` (dead) |
| `2.5px` / `4.5px` / `1.5px` / `0.45rem` | `:2443`–`2444` / `873`,`1333`–`1336` / `336`,`1396`,`933` (JSX) / `1033` | non-integer sizes |

**AMBIGUITY 7 — `.landing-wizard-side` is declared twice.** `src/index.css:156`–`162` and
`:253`–`261`, same selector. The second wins and adds
`background-image: radial-gradient(circle at 80% 20%, var(--color-accent-light), transparent 35%)`;
the first is dead. Two identical `/* RIGHT SIDE WIZARD PANEL */` comments (`:155`, `:253`) confirm
this is a duplicated block, not a deliberate cascade. Port the second.

### 9e. Off-token literals in JSX

**Category colours** — a 6-entry map + 6 fallbacks, all literals, `src/components/Dashboard.jsx:399`–`412`:

| Category | Hex | Tailwind name |
|---|---|---|
| `transport` | `#3b82f6` | blue-500 |
| `food & dining` | `#10b981` | emerald-500 |
| `accommodation` | `#ec4899` | pink-500 |
| `shopping` | `#f59e0b` | amber-500 |
| `activities` | `#8b5cf6` | violet-500 |
| `others` | `#64748b` | slate-500 |
| *fallbacks, cycled by index* | `#f43f5e`, `#a855f7`, `#6366f1`, `#14b8a6`, `#84cc16`, `#eab308` | rose-500, purple-500, indigo-500, teal-500, lime-500, yellow-500 |

**Participant colours** — 7 literals, cycled by index. **Duplicated verbatim in two files**:
`src/components/Dashboard.jsx:416`–`424` and `src/components/TransactionModal.jsx:14`–`22`:
`#10b981`, `#3b82f6`, `#8b5cf6`, `#ea580c`, `#ec4899`, `#06b6d4`, `#eab308`.
A third copy of the fallback exists as a bare default at `TransactionModal.jsx:593`: `'#2563eb'`.

Both palettes are data, not decoration — the donut chart, the per-person meters, the settlement
cards, the category badges and the row stripes all read from them. They must move into the token
set with the rest, and the two copies must become one.

**Alpha-hex suffix convention** — colours are tinted by string concatenation, `${color}NN`, an
8-digit hex. Five different alphas, no naming:

| Suffix | Alpha | File:line | Use |
|---|---|---|---|
| `10` | 6.3% | `Dashboard.jsx:936`, `:2077` | selected person-meter background; category tag background |
| `12` | 7.1% | `Dashboard.jsx:1351` | selected legend-item background |
| `15` | 8.2% | `Dashboard.jsx:1516`, `:1583`, `:1783`, `:2007` | settlement avatar, recent-list badge, table badge, settings avatar |
| `30` | 18.8% | `Dashboard.jsx:1785` | table category-badge border |
| `40` | 25.1% | `Dashboard.jsx:2077` | category tag border |

**Inline sizes that are not in the CSS type scale** — five sizes exist only in JSX:

| Value | File:line |
|---|---|
| `0.7rem` | `Dashboard.jsx:953`, `:1620`, `:1803`, `:1811`, `TransactionModal.jsx:620`, `:630` |
| `0.725rem` | `Dashboard.jsx:1988`, `SetupWizard.jsx:341` |
| `0.8rem` | `TransactionModal.jsx:597` |
| `0.85rem` | `Dashboard.jsx:1454`, `:1467` |
| `1.1rem` (avatar) / `1.15rem` (settlement amount) | `Dashboard.jsx:1526` / `:1536` |

**Inline geometry that contradicts the CSS** — these are the real trap:

| CSS rule | Overridden inline by | Effect |
|---|---|---|
| `.meter-bar-container { height: 0.45rem; border-radius: 9999px }` (`index.css:1032`–`1036`) | `Dashboard.jsx:947`: `{ height: '6px', borderRadius: '3px' }` | the CSS pill radius **never renders**; the meter is a 6px bar with 3px corners |
| `.meter-bar-fill { border-radius: 9999px }` (`index.css:1041`) | `Dashboard.jsx:950`: `borderRadius: '3px'` | same |
| `.avatar-circle-sm { width/height: 1.85rem; font-size: 0.75rem }` (`index.css:2247`–`2259`) | `Dashboard.jsx:1515`–`1527`: `2.5rem`, `1.1rem`, weight 800 · `Dashboard.jsx:2007`: tinted bg · `TransactionModal.jsx:597`: re-states `1.85rem` + `0.8rem` redundantly | one class, three different sizes |
| `.category-badge { border: 1px solid transparent }` (`index.css:1630`) | `Dashboard.jsx:1583` sets bg+colour only; `:1783`–`1785` also sets `borderColor: ${catColor}30` | **recent-list badges have an invisible border, table badges have a tinted one.** Same component, two looks |
| `.bar-pillar-fill { background: linear-gradient(…) }` (`index.css:1424`) | `Dashboard.jsx:1436`: `backgroundColor: isThisDaySelected ? 'var(--color-accent)' : undefined` | `background-color` does not beat `background` shorthand's image — the selected-day bar keeps its gradient and the highlight is a no-op |
| `.filters-grid { display: grid; grid-template-columns: 2fr 1fr 1fr auto }` (`index.css:1712`–`1717`) | `Dashboard.jsx:1083`, `:1650`: `{ display: 'flex', flexWrap: 'wrap', … }` | the grid definition and its `768px` media query are **both dead**; it is a flex-wrap row at every width |

**Classes styled only inline** — no CSS rule exists for `.clickable-filter-item`,
`.active-filter`, `.dimmed-filter`, `.clickable-filter`, `.active-cat`, `.dimmed-cat`,
`.active-bar`, `.dimmed-bar`, `.btn-clear-filter-sm`, `.settlement-card`, `.settlement-grid`,
`.settlement-item`, `.avatar-cost-thb`, `.donut-subvalue`, `.txn-amount-thb`, `.txn-share-badge`,
`.txn-price-insight`, `.flex-column`, `.flex-between`, `.grid-2-columns`, `.main-cardholder-select`,
`.step-badge-indicator`, `.overview-tab-view`, `.transactions-tab-view`, `.settings-tab-view`,
`.backup-tab-view`, `.wizard-step-content`, `.split-workspace`. A rebuild that ports only
`index.css` loses every one of these; the filter-dim interaction
(`opacity 0.4` / `0.35`, `1.5px solid <colour>`, `${color}10`/`12` background) exists **nowhere in
the stylesheet**.

**The `.font-mono` + bold problem** — see AMBIGUITY 4, §3.

---

## 10. Tailwind mapping

`theme.extend`, key by key. Colours route through the CSS variables so `:root.dark` and the
runtime country override keep working untouched — **do not inline the hex values into the config**,
or `App.jsx`'s `setProperty` calls stop having any effect.

```js
// tailwind.config.js
export default {
  darkMode: ['class', ':root.dark'],   // the app puts .dark on <html>, not on <body>
  theme: {
    extend: {
      colors: {
        bg: {
          primary:   'var(--bg-primary)',
          secondary: 'var(--bg-secondary)',
          card:      'var(--bg-card)',
          'card-hover': 'var(--bg-card-hover)',
        },
        border: { DEFAULT: 'var(--bg-card-border)' },  // also the shadow colour
        text: {
          primary:   'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted:     'var(--text-muted)',
        },
        accent:  { DEFAULT: 'var(--color-accent)',  light: 'var(--color-accent-light)',  hover: 'var(--color-accent-hover)' },
        success: { DEFAULT: 'var(--color-success)', light: 'var(--color-success-light)' },
        danger:  { DEFAULT: 'var(--color-danger)',  light: 'var(--color-danger-light)'  },
        warning: { DEFAULT: 'var(--color-warning)', light: 'var(--color-warning-light)' },
        // NEW — currently untokenised, see §9b/§9e. Add or lose them.
        purple:  { DEFAULT: '#8b5cf6', light: 'rgba(139, 92, 246, 0.15)', hover: '#a78bfa' },
        'on-accent': '#ffffff',
        tooltip:  '#0f172a',
        'hero-bg':      '#121212',
        'hero-panel':   '#111111',
        'hero-badge':   '#60a5fa',
        'hero-grad-to': '#a78bfa',
        'hero-h4':      '#f3f4f6',
        'hero-body':    '#9ca3af',
        'hero-credits': '#6b7280',
        'hero-desc':    '#e5e5e5',
        category: {
          transport: '#3b82f6', food: '#10b981', accommodation: '#ec4899',
          shopping: '#f59e0b', activities: '#8b5cf6', others: '#64748b',
        },
        participant: ['#10b981','#3b82f6','#8b5cf6','#ea580c','#ec4899','#06b6d4','#eab308'],
        'category-fallback': ['#f43f5e','#a855f7','#6366f1','#14b8a6','#84cc16','#eab308'],
        'stale-blue': { glow: 'rgba(59,130,246,0.15)', row: 'rgba(59,130,246,0.03)' },
      },

      boxShadow: {   // OVERRIDE, not extend — see §2
        none: 'none',
        sm:  '1px 1px 0px 0px var(--bg-card-border)',
        DEFAULT: '2px 2px 0px 0px var(--bg-card-border)',
        md:  '3px 3px 0px 0px var(--bg-card-border)',
        lg:  '5px 5px 0px 0px var(--bg-card-border)',
        'inner-sm': 'inset 1px 1px 0px 0px var(--bg-card-border)',
        'cta':       '2px 2px 0px 0px #000000',
        'cta-hover': '3px 3px 0px 0px #000000',
        'cta-active':'1px 1px 0px 0px #000000',
        pill: '0 2px 6px rgba(0, 0, 0, 0.3)',
        'accent-glow':       '0 10px 20px -5px var(--color-accent-hover)',
        'accent-glow-hover': '0 12px 24px -5px var(--color-accent-hover)',
        bar:       '0 2px 6px rgba(59, 130, 246, 0.15)',
        'bar-hover':'0 4px 10px var(--color-accent-light)',
        'ring-purple':  '0 0 0 3px rgba(139, 92, 246, 0.15)',
        'ring-success': '0 0 0 3px var(--color-success-light)',
      },

      borderRadius: {
        none: '0',
        DEFAULT: '2px',      // the house radius
        card: '4px',         // .setup-card only — AMBIGUITY 2
        xs:  '0.25rem',
        sm:  '0.375rem',
        md:  '0.5rem',
        lg:  '0.625rem',
        xl:  '0.75rem',
        '2xl': '1rem',
        full: '9999px',
      },

      borderWidth: { DEFAULT: '1px', '1.5': '1.5px', 2: '2px', 4: '4px', '4.5': '4.5px' },
      outlineWidth:  { focus: '2.5px' },
      outlineOffset: { focus: '2.5px' },

      fontFamily: {
        sans: ['"Plus Jakarta Sans"', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"',
               'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Courier New"', 'Courier', 'monospace'],
      },

      fontSize: {
        // [size, { lineHeight?, letterSpacing? }] — pairings from §3
        '2xs':  ['0.65rem',   { letterSpacing: '0.05em' }],
        'xs':   ['0.6875rem', {}],
        'sm':   ['0.75rem',   {}],
        'base': ['0.8125rem', {}],
        'md':   ['0.875rem',  { lineHeight: '1.25' }],
        'lg':   ['0.9375rem', {}],
        'xl':   ['0.95rem',   { lineHeight: '1.45' }],
        '2xl':  ['1.05rem',   { letterSpacing: '-0.01em' }],
        '3xl':  ['1.1rem',    { lineHeight: '1.6' }],
        '4xl':  ['1.15rem',   {}],
        '5xl':  ['1.25rem',   { lineHeight: '1.2', letterSpacing: '-0.02em' }],
        '6xl':  ['1.4rem',    { letterSpacing: '-0.02em' }],
        '7xl':  ['1.5rem',    { letterSpacing: '-0.025em' }],
        '8xl':  ['1.75rem',   {}],
        '9xl':  ['1.85rem',   { lineHeight: '1.2', letterSpacing: '-0.025em' }],
        'display':      ['3rem', { lineHeight: '1.15', letterSpacing: '-0.03em' }],
        'hero-fluid':   ['clamp(1.55rem, 2.2vw, 2rem)', { lineHeight: '1.2', letterSpacing: '-0.03em' }],
        // JSX-only sizes, §9e — add or the components regress
        'jsx-70':  '0.7rem', 'jsx-725': '0.725rem', 'jsx-80': '0.8rem', 'jsx-85': '0.85rem',
      },

      fontWeight: { normal: '400', medium: '500', semibold: '600', bold: '700', extrabold: '800' },
      letterSpacing: {
        tightest: '-0.03em', tighter: '-0.025em', tight: '-0.02em', snug: '-0.01em',
        normal: '0', hair: '0.0125em', wide: '0.025em', wider: '0.05em', widest: '0.075em',
      },
      lineHeight: { tight: '1.15', snug: '1.2', normal: '1.25', relaxed: '1.45', body: '1.5', loose: '1.6' },

      screens: {   // max-width, desktop-first — see §6 warning
        'max-xl': { max: '1200px' },
        'max-lg': { max: '992px'  },
        'max-md': { max: '768px'  },
        'max-sm': { max: '576px'  },
        'max-xs': { max: '480px'  },
      },

      zIndex: { 0: '0', 1: '1', 2: '2', 3: '3', 5: '5', 10: '10', modal: '999' },

      transitionDuration: {
        press: '100ms', tip: '150ms', DEFAULT: '200ms', bar: '250ms',
        theme: '300ms', meter: '400ms', zoom: '500ms',
      },
      transitionTimingFunction: { DEFAULT: 'ease', out: 'ease-out', modal: 'cubic-bezier(0.16, 1, 0.3, 1)' },

      keyframes: {
        'fade-in':      { from: { opacity: '0' }, to: { opacity: '1' } },
        'slide-down':   { from: { transform: 'translateY(-8px)', opacity: '0' }, to: { transform: 'translateY(0)', opacity: '1' } },
        'slide-up-fade':{ from: { transform: 'translateY(12px)', opacity: '0' }, to: { transform: 'translateY(0)', opacity: '1' } },
        // dead in the source, §5 — port only if you intend to use them
        'scale-up':   { from: { transform: 'scale(0.95)', opacity: '0' }, to: { transform: 'scale(1)', opacity: '1' } },
        'pulse-glow': { '0%': { boxShadow: '0 0 0 0 rgba(255,255,255,0.4)' },
                        '70%': { boxShadow: '0 0 0 10px rgba(255,255,255,0)' },
                        '100%': { boxShadow: '0 0 0 0 rgba(255,255,255,0)' } },
      },
      animation: {
        'fade-in':       'fade-in 250ms ease-out',
        'slide-down':    'slide-down 200ms ease-out',
        'slide-up-fade': 'slide-up-fade 300ms cubic-bezier(0.16, 1, 0.3, 1)',
      },

      spacing: {   // only the off-grid values Tailwind lacks; §3
        '0.5px': '0.5px', '1.5px': '1.5px', '2.5px': '2.5px', '4.5px': '4.5px',
        '0.22': '0.22rem', '0.45': '0.45rem', '0.6': '0.6rem', '0.7': '0.7rem',
        '1.15': '1.15rem', '1.85': '1.85rem',
      },
      maxWidth:  { setup: '520px', hero: '580px', 'hero-desc': '540px', modal: '840px',
                   truncate: '140px', splits: '180px', pillar: '34px' },
      maxHeight: { modal: '92vh', meters: '300px', people: '220px' },
      height:    { banner: '260px', chart: '200px', 'banner-mobile': '220px', donut: '180px' },
      width:     { sidebar: '320px', meta: '95px', 'row-narrow': '60px', 'edge-fade': '32px' },
      backdropBlur: { glass: 'var(--glass-blur)', tip: '2px', card: '4px', wash: '18px' },
    },
  },
}
```

Two things that cannot be expressed in `theme.extend` and must be hand-written CSS:

1. **The `:root` / `:root.dark` variable blocks themselves.** Put them in a global stylesheet
   (`@layer base`). Tailwind's config references them; it does not define them.
2. **`--hero-panel-*-rgb`** — set on `.hero-banner-card` and rewritten at runtime from image
   extraction (`Dashboard.jsx:162`–`165`). They are space-separated triplets consumed by
   `rgb()`/`rgba()`, which Tailwind's colour machinery will mangle. Keep the hero banner's
   gradients as plain CSS.

---

## Counts, for the record

- **23** CSS custom properties in light, **21** redefined in dark, **5** local hero-panel vars.
- **3** shadow tokens + **1** untokenised 2px rung + **5** soft one-offs + **2** focus rings.
- **11** distinct border-radius values across **2** incompatible radius systems.
- **17** font sizes in CSS + **5** more only in JSX; **5** weights; **8** letter-spacings; **6** line-heights.
- **9** font weights imported, **1** never used (Jakarta 300), **2** used but not imported (Mono 700/800).
- **11** transition duration/property pairs, **8** distinct durations, **3** easings.
- **5** keyframes, **2** dead.
- **16** `@media` blocks, **5** distinct max-widths.
- **7** z-index values, largest gap `10 → 999`.
- **13** countries × 8 fields, **2** divergent fallbacks, **3** overwritten properties.
- **13** category/participant palette colours in JSX, one array duplicated across 2 files.
- **7** ambiguities left unresolved (numbered above).
