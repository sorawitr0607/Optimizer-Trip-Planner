# Element inventory matrix — Auto-Bill supply against planner-stage demand

Resolves `Inventory the Auto-Bill elements each planner stage needs` (WF-021).

Read-only inventory of two codebases taken on 2026-07-31. Nothing in either project was modified.

Paths are absolute in the anchors below only where they leave one project; inside a project they are
repo-relative. `AB/` = `E:\ML_PROJECT\trip_planner\Auto-Bill-Splitter\`,
`TP/` = `E:\ML_PROJECT\trip_planner\Optimizer-Trip-Planner\`.

## Counts up front

| Measure | Count |
|---|---|
| Auto-Bill catalogue entries | 45 |
| — of which renderable UI elements | 41 |
| — utility/animation layer | 1 (entry 42) |
| — empty-state family, 4 unshared variants, no common element | 1 (entry 43) |
| — explicit absence recorded as an entry | 1 (entry 44, feedback) |
| — cross-cutting theming contract, not an element | 1 (entry 45) |
| Auto-Bill CSS class selector blocks in `AB/src/index.css` | 2458 lines, ~330 selector blocks |
| Auto-Bill JSX classes with **no** CSS rule (inline-styled only) | 18 confirmed, incl. the whole settlement grid |
| Inline `style={{…}}` sites | 87 Dashboard / 16 TransactionModal / 10 SetupWizard = 113 |
| Planner stages (8 views + app-level chrome) | 9 |
| Planner shared row renderers in `TP/ui/shared.py` | 3 (`_render_plan_item`, `_render_checklist_item`, `_render_fallback`) |
| Planner elements with **no** Auto-Bill counterpart | 18 (§4) |
| Auto-Bill elements the planner has no use for | 6 dead + 6 deferred-to-WF-018 (§5) |
| Load-bearing behaviours identified | 23 — 14 product, 9 Streamlit artifacts (§6) |
| Planner inline-feedback calls (`st.success/error/warning/info`) | 59 |
| Auto-Bill inline-feedback elements | 0 (33 `alert()`, 5 `window.confirm()`) |

**Two corrections to the ticket's premise, both worth recording before anyone ports:**

1. The ticket and `AB/README.md:9` both say the hero banner is built on a *strict `aspect-ratio: 3 / 1`*.
   There is no `aspect-ratio` declaration anywhere in `AB/src/index.css` or in any `.jsx`. The real rule
   is `AB/src/index.css:460-484`: a **fixed `height/min-height/max-height: 260px`** with
   `grid-template-columns: minmax(320px, 34%) minmax(0, 1fr)`, and the image cropped inside
   `.hero-banner-image-wrapper`. Port the locked 260px height, not a ratio. The README sentence is the
   only place 3/1 exists.
2. "The class names are the element catalogue" holds for about 90% of the file but **fails exactly on the
   newest elements**. `settlement-grid`, `settlement-item`, `settlement-card`, `main-cardholder-select`,
   `txn-share-badge`, `txn-amount-thb`, `flex-between`, `btn-clear-filter-sm`, `hero-stats-info`,
   `clickable-filter`, `grid-2-columns`, `overview-tab-view`, `recent-txns-card`, `split-workspace`,
   `selectables`, `avatar-cost-thb`, `wizard-step-content`, `step-badge-indicator` each have **zero CSS
   rules** — they are class names attached to fully inline-styled markup. A token extraction that reads
   only `index.css` (WF-020) will silently miss the settlement grid, the settlement item's 4px participant
   border, and the main-cardholder selector's entire appearance.

---

## 1. Auto-Bill element catalogue

Format: **name** — `class names` (`file:line`) — states/variants — behaviour.

### App shell and chrome

1. **App shell / theme container** — `.app-container` (`AB/src/index.css:78`), applied at
   `AB/src/App.jsx:106`. Variants: `light` / `dark` via `:root.dark` (`index.css:32-59`).
   Theme class is stamped on `<html>` and persisted to `localStorage` (`App.jsx:77-88`).
2. **Theme toggle** — `.theme-toggle-btn` (`index.css:1198`), `.theme-toggle-btn.float` (`1217`).
   Two placements: in the dashboard navbar (`Dashboard.jsx:1016`) and floating in the pre-setup header
   (`App.jsx:111`). Sun/Moon icon swap, `title` flips with the state.
3. **Setup header / brand bar** — `.setup-header`, `.setup-header .brand` (`index.css:91,103`),
   `App.jsx:108-118`. Exists only before a trip is created.
4. **Split landing grid** — `.onboarding-landing-grid` (`index.css:114-120`), `1.1fr 0.9fr`, full
   `100vh`/`100vw`. Below 992px it collapses to `1fr` **and hides the hero side outright**
   (`display: none !important`, `index.css:121-129`). `SetupWizard.jsx:175`.
5. **Dark hero panel** — `.landing-hero-side` (`index.css:131`) fixed `#121212` outside the token set,
   dotted radial `::before` (`143`), `.hero-content` (`164`), `.app-logo-badge` (`170`),
   `.hero-headline` + gradient `span` (`186,194`), `.hero-subtext` (`200`),
   `.feature-bullets-list` / `.feature-bullet-item` / `.feature-icon` / `.feature-details`
   (`207-244`), `.landing-footer-credits` (`245`). `SetupWizard.jsx:177-220`. Static content.
6. **Wizard shell** — `.landing-wizard-side` (`index.css:156`, redeclared `253`), `.setup-card` (`270`),
   `.setup-card.glassmorphic-card` (`281`). `SetupWizard.jsx:223-224`. Note: "glassmorphic" only bumps
   the shadow to `--shadow-lg`; `--glass-blur` is `0px` (`index.css:30`), so the two `backdrop-filter`
   uses (`1143`, `2040`) are no-ops. There is no glass in the glassmorphism.
7. **Step indicator** — `.wizard-progress-4` (`index.css:286`), `.progress-step-4` (`293`),
   `.step-num-4` (`304`), `.step-label-4` (`318`), `.progress-line-4` (`335`); active states at
   `324,331`. `SetupWizard.jsx:239-259`. States: active / inactive. Behaviour: clicking a step only
   navigates **backwards** (`step >= n ? setStep(n) : null`). The step count is baked into the class
   names.
8. **Step header** — `.wizard-step-header`, `.wizard-step-header .step-icon`, `h2`, `p`
   (`index.css:342-370`). Per-step icon colour via `text-blue|green|purple|amber`
   (`SetupWizard.jsx:265,368,475,536`).
9. **Wizard action row** — `.wizard-actions` (`index.css:878`). Right-aligned, top border, `1rem` gap.
10. **Button family** — `.btn` (`index.css:372`) + `.btn-primary` (`388`), `.btn-secondary` (`399`),
    `.btn-outline` (`412`), `.btn-success` (`425`), `.btn-text` (`436`), size `.btn-sm` (`450`), width
    `.w-full` (`455`). 5 colour variants + 1 size + 1 width. **There is no `:disabled` or `[disabled]`
    rule anywhere in `index.css`** — the 5 JSX `disabled` usages
    (`SetupWizard.jsx` ×4, `TransactionModal.jsx:684`) fall back to browser default styling.
11. **Icon action button** — `.action-btn` (`index.css:1682`), `.action-btn.text-red:hover` (`1701`);
    `.btn-remove-icon` (`1915`) is a near-duplicate with a different size and hover.
    *Unsure whether these are one element with two sizes or two elements* — they differ only in
    dimensions and hover colour, and neither is expressed in terms of the other.

### Data display

12. **Hero CTA banner** — `.hero-banner-card` (`index.css:460`), `.hero-banner-card.card` override
    (`486`), `.hero-banner-image-wrapper` (`496`), `.hero-banner-content` (`506`) with two gradient
    pseudo-layers (`541`, `555`), `.hero-banner-badge` (`572`), `.hero-title` (`585`),
    `.hero-description` (`594`), `.btn-hero-cta` (`603`), `.hero-banner-image-overlay` (`632`),
    `.hero-trip-img` (`661`), mobile stack at 768px (`675`). `Dashboard.jsx:1044-1080`.
    States: **zero-transactions copy vs logged-totals copy** (`Dashboard.jsx:1050-1058`).
    Behaviour: clicking the image opens a file picker; on image load,
    `applyHeroGradientFromImage` (`Dashboard.jsx:73-171`) samples an 84×84 canvas, weights pixels by
    saturation and brightness, derives a dominant colour, clamps its luminance
    (`keepPanelReadable`, max 72, `Dashboard.jsx:62-71`) and writes four `--hero-panel-*-rgb`
    custom properties. 140 lines of colour extraction for one banner.
13. **Generic card** — `.card` (`index.css:699`), `.card-title` (`707`), `.card-header-row` (`717`).
    The base container for everything below.
14. **Stat card** — `.stat-cards-grid` `auto-fit minmax(220px, 1fr)` (`index.css:1249`), `.stat-card`
    (`1256`), `.stat-icon-wrapper` (`1267`) with 4 colour variants `blue|green|purple|amber`
    (`1276-1279`), `.stat-label` (`1281`), `.stat-value` (`1288`), `.stat-subvalue` (`1294`).
    `Dashboard.jsx:1157-1224`, four instances. Behaviour: **the label itself changes with the active
    traveller filter** (`1163,1180,1213`), and every value carries a secondary THB line.
15. **Insight card** — `.insights-panel-cards` (`index.css:1320`), `.insights-card` (`1326`) with four
    left-border colour variants (`1333-1336`), `.card-header-icon` + `.icon` (`1338-1352`),
    `.insights-body h5` (`1356`), `.insights-prices` (`1363-1381`). `Dashboard.jsx:1228-1296`, four
    instances. Distinct from the stat card: emoji header, a primary/secondary money pair, and an
    explicit `'None'` / `'No data'` string per card rather than a shared empty state.
16. **Filter bar** — `.filtering-card` (`index.css:1707`), `.filters-grid` (`1712`, single-column below
    768px), `.search-box` / `.search-icon` / `.search-input` (`1725-1741`), `.filter-group` /
    `.filter-icon` (`1742-1758`). Rendered **twice with duplicated markup**:
    `Dashboard.jsx:1082-1155` (overview) and `Dashboard.jsx:1648-1723` (ledger). Four controls: text
    search + day + category + traveller. A `Clear Filters` button appears only when at least one filter
    is off-default (`1138-1152`). Behaviour: `getFilteredTransactions(excludeFilter)`
    (`Dashboard.jsx:258-271`) deliberately excludes the traveller filter from the per-person totals so
    the sidebar meters stay comparable while a traveller is selected.
17. **Sidebar shell** — `.sidebar` (`index.css:902`), static below 992px (`915`), `.sidebar-brand` /
    `.brand-logo` / `.brand-badge` (`922-946`), `.sidebar-title` (`947`). `Dashboard.jsx:853-862`.
18. **Metadata summary box** — `.trip-summary-box` (`index.css:956`), `.summary-row-stat` with `.label`
    and `.value` (`964-986`), `.text-truncate` (`987`). `Dashboard.jsx:865-889`, five label/value rows
    (name, destination + flag, start date, duration, FX). The only read-only key/value panel.
19. **Person meter row** — `.person-meters-list` (`index.css:1000`), `.person-meter-item` (`1010`),
    `.meter-info` / `.person-name` / `.person-cost` (`1016-1031`), `.meter-bar-container` (`1032`),
    `.meter-bar-fill` (`1039`), `.meter-thb` (`1045`). `Dashboard.jsx:915-958`.
    States: default, selected, dimmed — **the last two exist only as inline `opacity`/`border`
    overrides**; the JSX names `active-filter` and `dimmed-filter` have no CSS rules.
    Behaviour: the whole row is a filter toggle; the bar fill is a percentage of the grand total; the
    per-person colour comes from an 8-entry palette (`Dashboard.jsx:416-429`).
20. **Grand total panel** — `.sidebar-grand-total` (`index.css:1051`) with a `::before` gradient sheen
    (`1067`) and hover (`1078`), `.main-price` (`1097`), `.thb-price` (`1105`).
    `Dashboard.jsx:961-973`. The label flips between the trip total and one traveller's share.
21. **Sidebar quick actions** — `.sidebar-quick-actions` (`index.css:1112`), `Dashboard.jsx:975-979`.
    One full-width outline button (Export Excel).
22. **Workspace tabs** — `.top-navbar` (`index.css:1133`), `.workspace-tabs` (`1154`), `.tab-link`
    (`1166`) + `.tab-link.active` (`1187`), `.tab-viewport` (`1243`). `Dashboard.jsx:985-1011`.
    Four tabs; the expenses tab carries a live count in its label (`996`).
23. **Danger action** — `.btn-reset-trip` (`index.css:1222`). `Dashboard.jsx:1024-1034`, guarded by
    `window.confirm`.
24. **Donut chart** — `.donut-chart-container` (`index.css:1498`), `.donut-chart` conic-gradient
    (`1505`), `.donut-hole` (`1512`), `.donut-center-content` / `.donut-label` / `.donut-value`
    (`1527-1546`), legend `.chart-legend` / `.legend-item` / `.legend-dot` / `.legend-label` /
    `.legend-value` (`1547-1578`), `.chart-flex-layout` (`1484`, stacks below 576px), empty state
    `.no-data-chart` (`1579`). Gradient string built in JS (`Dashboard.jsx:431-448`).
    `Dashboard.jsx:1301-1379`. Legend items are click-to-filter.
25. **Vertical bar chart** — `.vertical-chart-view` (`index.css:1382`), `.bar-chart-container` (`1390`),
    `.bar-wrapper-item` (`1402`), `.bar-interactive-pillar` (`1412`), `.bar-pillar-fill` (`1422`) with
    a hover lift (`1430`), `.bar-item-label` (`1436`), `.bar-tooltip-popup` + `::after` arrow shown on
    pillar hover (`1446-1482`). `Dashboard.jsx:1381-1447`.
26. **Transaction list row** — `.recent-list` (`index.css:1592`), `.recent-row-item` (`1598`) with hover
    (`1611`) and an inline 4px category-colour left border, `.recent-meta` (`1616`),
    `.category-badge` (`1625`), `.recent-day` (`1637`), `.recent-details` / `.txn-name` /
    `.txn-splits-people` (`1643-1665`), `.recent-cost-actions` / `.txn-amount` (`1666-1676`),
    `.action-btns` (`1677`). `Dashboard.jsx:1578-1636`. Behaviour: the category badge and the day chip
    are both click-to-filter toggles; a `Share:` line appears **only** when a traveller filter is on
    (`1620-1623`).
27. **Transaction table** — `.table-card` (`index.css:1759`), `.overflow-x` (`1764`),
    `.transactions-table` with th/td/hover (`1768-1799`), `.width-row` (`1800`), `.badge-day` (`1804`),
    `.txn-desc-cell` / `.cell-notes` (`1815-1825`), `.max-width-splits` (`1857`), empty row
    `.no-items-td` (`1864`). `Dashboard.jsx:1728-1843`, 9 columns.
    *Unsure whether 26 and 27 are one element or two* — they render the same record with different
    markup and share only `.category-badge`. Counted as two.
28. **Split-mode badge** — `.mode-badge` (`index.css:1827`) with `.m-all` / `.m-sel` / `.m-sgl` /
    `.m-man` (`1837-1856`), each its own colour. `Dashboard.jsx:1817-1823`. **The emoji and the word
    are inline string literals in the JSX**, not data.
29. **Settlement grid + settlement item** — `.settlement-card`, `.settlement-grid`, `.settlement-item`:
    **no CSS rules at all**, styled entirely inline at `Dashboard.jsx:1450`, `1493`, `1503-1512`.
    `auto-fit minmax(280px, 1fr)`; each item has a 4px participant-colour left border, an
    `.avatar-circle-sm`, an "X owes Y" line, primary + THB amounts, and a Copy Memo button.
    Empty state: solo traveller, inline italic text (`Dashboard.jsx:1489-1492`).
30. **Main-cardholder selector** — `.main-cardholder-select highlight-focus`
    (`Dashboard.jsx:1477`); appearance is **entirely inline** (`1466-1476`). The only real CSS is
    `.input-field.highlight-focus:focus` (`index.css:762`). Behaviour: changing it recomputes every
    settlement row live and writes back through `onUpdateSettings`.
31. **Copy-memo action** — `.btn btn-outline btn-sm` plus inline sizing
    (`Dashboard.jsx:1543-1551`). Builds a sentence, `navigator.clipboard.writeText`, then a native
    `alert`. No toast.
32. **Settings form / people manager** — `.settings-cards-grid` (`index.css:1872`), `.settings-form`
    (`1884`), `.settings-people-list` / `.settings-people-row` / `.person-info` (`1889-1914`),
    `.btn-remove-icon` (`1915`), `.settings-divider` (`1929`), `.inline-add-form` (`1935`),
    `.rename-form h4` (`1940`), `.form-help-text` (`1948`), `.categories-settings-container` (`1959`).
    `Dashboard.jsx:1849-2110`.

### Input

33. **Form field family** — `.form-group` + `label` (`index.css:729-743`),
    `.input-field, .select-field, .textarea-field` (`744`) with focus ring (`756`) and two highlight
    variants `.highlight-focus` (`762`) / `.highlight-amount-focus` (`767`), `.form-row-two` (`797`),
    `.form-row-three` (`791`), `.input-action-row` (`803`).
34. **Amount + currency field** — three markup shapes for one idea:
    `.input-with-label` + `.field-suffix` (`index.css:772-790`, suffix form — the FX rate's "THB",
    `SetupWizard.jsx:429-441`); `.manual-input-box` + `.input-prefix` + `.manual-input`
    (`index.css:2293-2310`, prefix form — currency symbol before the amount,
    `TransactionModal.jsx:602-611`); and `.input-field.highlight-amount-focus`
    (`index.css:767`, the bill total, `TransactionModal.jsx:422`).
    *Unsure whether this is one element with three variants or three elements* — no shared class binds
    them. Counted as one.
35. **Tag chips** — `.tags-container` (`index.css:814`) + `.no-padding` (`822`), `.tag-item` (`826`) +
    `.tag-item.category-tag` (`839`), `.tag-remove` (`845`) + hover (`857`), empty state
    `.no-items-text` (`862`). People and categories in the wizard
    (`SetupWizard.jsx:493-510`, `554+`) and categories in settings (`Dashboard.jsx:2073-2090`).
36. **Info callout** — `.currency-info-box` (`index.css:868`). Accent 4.5px left border, secondary
    background, small secondary text. The only static in-page explanation element.
    `SetupWizard.jsx:445-450`.
37. **Import / export cards** — `.backup-grid` (`index.css:1966`, single column below 768px),
    `.backup-card-header` (`1978`), `.backup-icon` + `.text-blue` / `.text-green` (`1987-1996`),
    `.backup-grid p` (`1997`), `.import-action-zone` (`2003`). `Dashboard.jsx:2113-2153`.
    Shape: icon + title + one paragraph of prose + one button. A hidden `<input type=file>` behind a
    visible button (`2136-2147`). Excel export lives separately in the sidebar (entry 21).
38. **Modal shell** — `.modal-backdrop` (`index.css:2015`), `.modal-card` (`2030`, max-width 840px,
    max-height 92vh), `.modal-header` + `h2` (`2044-2056`), `.modal-close-btn` (`2057`),
    `.modal-body` (`2073`), `.modal-form-grid` (`2079`) + `.span-full` (`2086`), single column below
    576px (`2090`), `.modal-footer` (`2362`). `TransactionModal.jsx:321-330, 678-690`.
    States: title flips add/edit (`322-324`); the save button disables when a manual split does not
    balance (`684-686`).
39. **Allocation-mode picker** — `.modal-split-section` + `.section-title` (`index.css:2105-2117`),
    `.split-modes-tabs` (`2118`), `.split-modes-tabs .tab-btn` (`2129`) + `.active` (`2143`) + four
    per-mode active colours (`2149-2152`), `.split-descriptor` (`2154`), responsive override at
    `2447-2456`. `TransactionModal.jsx:445-487`. Four modes; each carries its own accent when active.
40. **Participant chooser (avatar card grid)** — `.avatar-preview-grid` (`index.css:2160`),
    `.avatar-preview-card` (`2166`) with `.clickable` (`2179`), `.inactive` (`2201`), hover (`2206`),
    and **three per-mode active skins** that each also restyle `.avatar-circle` and `.avatar-cost`
    (`2183-2199`, `2243-2245`), `.avatar-circle` (`2211`), `.avatar-name` (`2227`), `.avatar-cost`
    (`2237`). `TransactionModal.jsx:496-583`. Three of the four split modes render it; the fourth uses
    entry 41. Each card shows the person's initial, name, their share, and the THB equivalent.
41. **Manual allocation rows + validation panel** — `.manual-inputs-list` (`index.css:2261`),
    `.manual-row-item` (`2268`, wraps below 480px), `.manual-person-info` / `.manual-person-name`
    (`2282-2292`), `.manual-input-box` / `.input-prefix` / `.manual-input` (`2293-2310`),
    `.btn-adjust` (`2311`), `.manual-validation-panel` (`2317`) with `.invalid` (`2326`) / `.valid`
    (`2331`), `.validation-row` (`2336`), `.validation-divider` (`2346`),
    `.validation-row.status-line` (`2351`). `TransactionModal.jsx:587-670`.
    Behaviour: live sum vs bill total with a `0.015` tolerance, and the save button gates on it.
    **This is the only in-page success/error surface in the entire app.**
42. **Avatar chip (small)** — `.avatar-circle-sm` (`index.css:2247`). Reused in settlement items,
    settings people rows, and manual split rows — always with inline size overrides, never at its CSS
    size.

### Cross-cutting

43. **Animation and utility layer** — `@keyframes scale-up / fade-in / slide-down / slide-up-fade /
    pulse-glow` (`index.css:2387-2412`), `.animate-fade-in` (`2413`), `.animate-slide-down` (`2417`);
    helpers `.font-mono` (`2371`) through `.flex-center.gap-2` (`2384`); scrollbar styling (`2421`);
    `:focus-visible` rings, labelled "Principle 5" (`2437-2446`).
44. **Empty states — four, with no shared element** — `.no-items-text` italic muted line
    (`index.css:862`), `.no-data-chart` 200px centred italic (`1579`), `.no-items-td` 3rem table cell
    (`1864`), and fully-inline solo-traveller text (`Dashboard.jsx:1489`). Each was written where it
    was needed.
45. **Feedback: absent.** No toast, no inline banner, no field-level error text. **33 `window.alert()`
    and 5 `window.confirm()`** stand in for it: `Dashboard.jsx:567,597,627,630,633,711,716,732,740,757,
    786,792,796,810,823,827,830,1026,1549,1975`, `SetupWizard.jsx:103,121,136,142,147,152,352`,
    `TransactionModal.jsx:260,265,269,274,281`. Entry 41 is the only exception.
46. **Country accent contract** (not an element) — `AB/src/App.jsx:56-75` writes
    `--color-accent`, `--color-accent-light`, `--color-accent-hover` on `document.documentElement` from
    a 13-country table (`AB/src/utils.js:1-15`). Unknown countries degrade to a flagcdn URL plus `✈️`
    (`utils.js:17-161`). Flags rendered by `renderFlag` (`Dashboard.jsx:197-221`).

---

## 2. Planner stage demand

### App-level chrome — `TP/app.py`

| Element rendered | Anchor |
|---|---|
| Trip selector, sidebar selectbox keyed `selected_trip_id`, label never repeats the destination | `app.py:38-57` |
| Empty-state info when no trip exists | `app.py:59` |
| Journey progress rail — 5 stages, marks `✅` / `⏳` / `○` | `app.py:66-69` |
| Capability-gap counter | `app.py:70-73` |
| Readiness summary line (state + open task count) | `app.py:74-80` |
| Paid-usage line, `US$x.xxxx / US$10.00`, through `shared.plain()` | `app.py:81-87` |
| Language radio, 2 options, horizontal, at the sidebar foot | `app.py:90-96` |
| Navigation — 8 stages in two labelled sections, default computed from `journey["next"]` | `app.py:100-123` |

### `TP/views/setup.py` (511 lines) — the five editable steps

| Element rendered | Anchor |
|---|---|
| New-trip expander, auto-expanded when no trip exists | `setup.py:44` |
| Country selectbox — `accept_new_options`, `index=None`, translated label | `setup.py:52-60` |
| City selectbox — **options depend on the chosen country**, `accept_new_options`, `index=None` | `setup.py:62-69` |
| Destination preview caption (the literal geocoder query) | `setup.py:73-78` |
| Trip name text_input, planning-mode selectbox, create button | `setup.py:80-87` |
| Status + mode metrics (2 columns) | `setup.py:110-112` |
| Overdue / due-soon deadline banners, above the stepper | `setup.py:123-128` |
| `st.progress(step / 5)` + "step N of 5" caption + step title | `setup.py:284-286` |
| Step 1: 3 checkboxes, 2 date_inputs, 2 time_inputs (each disabled by its checkbox), accommodation selectbox | `setup.py:289-341` |
| Step 2: age number_input, **4 tag multiselects**, description text_area | `setup.py:344-370` |
| Step 3: member_count number_input, then per-member expander × N with name/age/tags/notes/must-respect | `setup.py:376-418` |
| Step 4: single must-respect text_area | `setup.py:421-425` |
| Step 5: state text line, 2 metrics, **4 summary rows each with its own Edit button that jumps back** | `setup.py:430-477` |
| Nav row: Back / Save draft / Save & continue \| Confirm, all `on_click` callbacks | `setup.py:480-511` |

### `TP/views/places.py` (400 lines) — discovery + ranking

| Element rendered | Anchor |
|---|---|
| Discover / Refresh button pair + spinner | `places.py:30-45` |
| Stale-setup warning (hash mismatch), provider-gap warning | `places.py:50-53` |
| Provider status as a **text line, not a metric** | `places.py:54-60` |
| Coverage: 3 metrics — candidates / duplicates merged / geographic cells | `places.py:61-64` |
| Raw provider catalog table in a collapsed expander, 5 columns incl. source URL | `places.py:69-85` |
| Attribution + license link | `places.py:88-91` |
| Raw report `st.json` behind a disclosure | `places.py:92-93` |
| Lane selectbox with per-lane counts (5 lanes) | `places.py:136-141` |
| Card selectbox, `name · score/100` | `places.py:147-155` |
| **Candidate detail panel**: title, local name, category, photo or explicit unavailable caption | `places.py:160-167` |
| Role badges as `st.info` — exploration slot / city icon / alternative-to | `places.py:168-178` |
| Score + duration-band metrics | `places.py:180-186` |
| Feasibility text line ("Not evaluated yet") + planner-estimate caveat | `places.py:187-189` |
| Matched tags line | `places.py:191-197` |
| Why / Pros / Cons — 3 columns of code-derived lists, **collapsed by default** | `places.py:198-213` |
| Dimension breakdown table (points vs max) + deductions with negative points | `places.py:215-236` |
| Evidence two-column block: opening state, route effort, source rating, source link | `places.py:238-245` |
| Current-choice caption; 3 action buttons; rejection expander with reason selectbox; clear-choice | `places.py:247-304` |
| Browse-all table (6 columns) | `places.py:306-328` |
| Group-weights table + formula/learned weights `st.json` | `places.py:330-355` |
| All-choices table | `places.py:357-372` |
| Reconciliation table | `places.py:376-396` |

### `TP/views/evidence.py` (130 lines) — provenance and paid usage

| Element rendered | Anchor |
|---|---|
| Timezone evidence card — verified state + retrieval date, or missing + cost + fetch button | `evidence.py:26-48` |
| Paid-usage caption (spend / cap / request count) + stopped-error / warning banner | `evidence.py:52-63` |
| Opening-hours card — usable count, grouped unusable reasons, cost, fetch button | `evidence.py:68-93` |
| Routes card — verified count, or missing + fetch button; result names skipped/failed | `evidence.py:95-119` |
| Raise-cap expander — number_input + save | `evidence.py:121-129` |

Three `st.container(border=True)` cards, each: **state → what it costs → the one button that spends
money** (`evidence.py:65-67`).

### `TP/views/optimize.py` (156 lines) — three variants

| Element rendered | Anchor |
|---|---|
| Flash banner from session state | `optimize.py:19-21` |
| Generate button (disabled with no choices) + info + spinner | `optimize.py:28-44` |
| Stay-recommendation table (no-dates mode) | `optimize.py:49-62` |
| **Variant selectbox — 3 options, one shown at a time** | `optimize.py:65-71` |
| Variant heading with status | `optimize.py:72` |
| 5 metrics laid out **3 + 2**, not 5 across | `optimize.py:73-85` |
| Greedy-check success banner; stopped-at-limit warning | `optimize.py:86-92` |
| Warnings expander, `expanded=True` | `optimize.py:94-97` |
| Reconciliation table (5 columns) | `optimize.py:99-118` |
| Timeline table (6 columns) | `optimize.py:120-136` |
| Activate button, disabled unless `status == "ready"`, with a caption saying why | `optimize.py:138-155` |

### `TP/views/itinerary.py` (197 lines) — the active plan

| Element rendered | Anchor |
|---|---|
| Variant + readiness header line; plan stamp caption (version id, export time, currency, language) | `itinerary.py:29-37` |
| Superseded-plan warning | `itinerary.py:38-39` |
| Capability-gaps expander | `itinerary.py:40-43` |
| Day selectbox | `itinerary.py:45-49` |
| Day totals line + walking breakdown caption | `itinerary.py:52-63` |
| Highest-risk warning | `itinerary.py:64-68` |
| Timeline \| Map tabs | `itinerary.py:70` |
| Timeline: morning/afternoon grouping, plan-item rows, fallback rows | `itinerary.py:71-87` |
| **Numbered map**: `st.map` with per-stop colour + radius by status, gold hotel anchor | `itinerary.py:88-118` |
| Stop text list carrying the same distinctions as the marker colours | `itinerary.py:119-126` |
| **4 download buttons in one row** — poster PNG / PDF / XLSX / ICS, the last replaced by a caption when the checklist is empty | `itinerary.py:128-173` |
| Unscheduled-choices table, **auto-expanded when the day schedules nothing** | `itinerary.py:175-196` |

### `TP/views/readiness.py` (144 lines) — the board

| Element rendered | Anchor |
|---|---|
| Proposal preview expander: `➕` additions / `➖` removals / `📅` deadline moves + apply button | `readiness.py:33-61` |
| Category multiselect filter | `readiness.py:67-72` |
| Timing-bucket section headings | `readiness.py:79-85` |
| Board item rows via `shared._render_checklist_item` | `readiness.py:85` |
| Add-task expander: title, category, timing, level, consequence + button | `readiness.py:87-126` |
| Dismissed-history expander with per-item restore | `readiness.py:128-143` |

### `TP/views/costs.py` (178 lines) — owner-recorded costs

| Element rendered | Anchor |
|---|---|
| Rate-snapshot expander, **auto-expanded when absent**: as-of/source/buffer caption, rate table, currency selectbox, value, date, source, buffer, save | `costs.py:29-83` |
| Totals line — total / estimated / paid THB | `costs.py:88-92` |
| Missing-rates warning | `costs.py:93-94` |
| Per-cost bordered container: `label · amount CUR → THB`, marks caption (state, category, locked, rate-missing), remove button | `costs.py:95-111` |
| Add-cost expander: label, amount, **currency selectbox whose `format_func` appends "rate missing"**, category, state, and an actual-THB field that exists only when the state is `paid` | `costs.py:113-177` |

### `TP/views/revise.py` (220 lines) — quick actions, GenAI, history

| Element rendered | Anchor |
|---|---|
| Quick-action selectbox — operation label + resolved place name | `revise.py:37-54` |
| Run-action button | `revise.py:56-66` |
| Pending-draft bordered panel: operation heading, assumptions caption | `revise.py:68-80` |
| Deterministic reasons: variant + status caption, metrics table, unscheduled list | `revise.py:81-101` |
| **Consequences**: changed-days caption, before/after/delta table, **8 labelled change lists** (moved, added, removed, shortened, lengthened, displaced, new warnings, cleared warnings), blocked warning | `revise.py:102-137` |
| Apply / Cancel button pair, apply disabled unless `can_apply` | `revise.py:138-159` |
| AI toggle checkbox, disabled note, cost + disclosure captions | `revise.py:161-168` |
| Free-text text_area + interpret button; unsupported warning + clarification info | `revise.py:169-197` |
| Revision-history expander (timestamp · operation · `from` → `to` short ids) | `revise.py:199-207` |
| **Version list expander with a restore button per version** | `revise.py:208-220` |

### `TP/ui/shared.py` — the planner's existing de facto components

| Component | Anchor | What it is |
|---|---|---|
| `_render_plan_item` | `shared.py:451-498` | The timeline row. **Three variants**: `visit` (clock, stop number, name, state, duration, local name, disclosure with choice/address/opening-unverified), `travel` (clock, origin→destination, mode, walking minutes, disclosure with sightseeing-vs-transfer/distance/transfers/boarding buffer), `buffer` (caption only). |
| `_render_checklist_item` | `shared.py:334-427` | The board row. Bordered container; title; `level · progress · evidence` line; due date; consequence; progress selectbox; a not-applicable note field that appears conditionally; save button; an evidence disclosure (expected authority, verified URL + last-checked, source-URL input, authority selectbox, record button); dismiss button. |
| `_render_fallback` | `shared.py:430-448` | The half-day fallback row: trigger, `primary → replacement`, replacement start, day-reoptimized flag, displaced consequence. |
| `translated_selectbox` / `translated_multiselect` | `shared.py:110-140` | Language-safe pickers: per-language widget key, language-free stored choice, typed-in options preserved across a switch, translated placeholder. |
| `plain` | `shared.py:57-66` | Escapes `$` so Streamlit does not read money as LaTeX. |
| `journey` / `require` | `shared.py:158-236` | Stage state and the unreachable-stage explanation. |
| `chosen` / `_seed` / `_remember` | `shared.py:81-107` | Reads a translated widget by its language-free name. |
| `_photo_url` | `shared.py:268-277` | Wikimedia `File:` reference → Commons redirect URL. |
| `_plan_documents` / `_day_poster` | `shared.py:317-331` | Export bytes, cached by snapshot sha + language. |

---

## 3. The matrix

Legend: `reuse` — the Auto-Bill element works as-is. `adapt` — the same element, needing new states or
fields. `absent` — no Auto-Bill counterpart exists. `—` — this stage has no use for this element.
`defer` — the element exists and the planner will want it, but only once
`Define the split ledger model and where its math lives` (WF-018) lands.

Split into three tables for readability; it is one matrix.

### 3a. Chrome and layout

| Stage | shell+theme (1) | theme toggle (2) | sidebar (17) | tabs (22) | landing grid (4) | wizard shell (6) | step indicator (7) | hero banner (12) | card (13) | modal shell (38) | buttons (10) | icon btn (11) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| app chrome | reuse | reuse | adapt | adapt | — | — | — | — | reuse | — | adapt | — |
| setup | — | — | — | — | reuse | adapt | adapt | adapt | reuse | reuse | adapt | reuse |
| places | — | — | — | — | — | — | — | — | reuse | reuse | adapt | reuse |
| evidence | — | — | — | — | — | — | — | — | reuse | — | adapt | — |
| optimize | — | — | — | — | — | — | — | — | reuse | — | adapt | — |
| itinerary | — | — | — | reuse | — | — | — | adapt | reuse | — | reuse | — |
| readiness | — | — | — | — | — | — | — | — | reuse | reuse | adapt | reuse |
| costs | — | — | — | — | — | — | — | — | reuse | reuse | reuse | reuse |
| revise | — | — | — | — | — | — | — | — | reuse | reuse | adapt | reuse |

`buttons` is `adapt` almost everywhere for one reason: **`index.css` has no `:disabled` rule**, and the
planner disables a primary action with an explanatory caption in five places (`optimize.py:144`,
`revise.py:142`, `places.py:38`, `setup.py` conditional nav, `optimize.py:32`).

### 3b. Data display

| Stage | stat card (14) | insight card (15) | person meter (19) | metadata box (18) | grand total (20) | list row (26) | table (27) | mode badge (28) | settlement (29) | donut (24) | bar chart (25) | empty states (44) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| app chrome | — | — | **adapt** (spend meter) | adapt | — | — | — | — | — | — | — | reuse |
| setup | reuse | — | — | reuse | — | reuse (review rows) | — | adapt | — | — | — | reuse |
| places | reuse | adapt | — | — | — | absent (candidate card) | reuse | adapt | — | — | absent (score bars) | reuse |
| evidence | reuse | adapt | — | — | — | — | — | adapt | — | — | — | reuse |
| optimize | reuse | — | — | — | — | — | reuse | adapt | — | — | — | reuse |
| itinerary | reuse | adapt | — | reuse (plan stamp) | — | absent (timeline row) | reuse | adapt | — | — | — | reuse |
| readiness | reuse | adapt | — | — | — | absent (board item) | — | adapt | — | — | — | reuse |
| costs | reuse | — | adapt | — | reuse | reuse | reuse | adapt | defer | — | — | reuse |
| revise | reuse | adapt | — | — | — | absent (version row) | reuse | adapt | — | — | — | reuse |

`mode badge` is `adapt` in eight stages for one reason: the planner has **eight** distinct pill
vocabularies (choice action, plan-item status, provider status, evidence state, progress state,
requirement level, payment state, variant status) and every one is a translated code, whereas
`.mode-badge` hardcodes its four emoji+word pairs in the JSX (`Dashboard.jsx:1818-1822`).

### 3c. Input and action

| Stage | filter bar (16) | form fields (33) | amount+currency (34) | tag chips (35) | mode picker (39) | participant chooser (40) | manual+validation (41) | cardholder select (30) | import/export (37) | info callout (36) | copy memo (31) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| app chrome | — | reuse | — | — | absent (language) | — | — | — | — | reuse | — |
| setup | — | reuse | — | reuse | adapt | — | — | — | — | reuse | — |
| places | adapt | reuse | — | reuse | adapt (lanes) | — | — | — | — | reuse | — |
| evidence | — | reuse | — | — | — | — | adapt | — | — | reuse | — |
| optimize | — | — | — | — | adapt (variants) | — | adapt | — | — | reuse | — |
| itinerary | adapt (day pick) | — | — | — | reuse (timeline\|map) | — | — | — | adapt | reuse | — |
| readiness | adapt | reuse | — | reuse | — | — | adapt | — | reuse (ICS) | reuse | — |
| costs | — | reuse | reuse | — | adapt | defer | defer | defer | — | reuse | — |
| revise | — | reuse | — | — | adapt | — | adapt | — | — | reuse | — |

`manual+validation (41)` recurs as `adapt` because it is the only Auto-Bill element that shows a
before/after/difference with a valid/invalid skin — which is structurally what the planner needs for the
revision consequence table (`revise.py:110-122`), the greedy check (`optimize.py:86-92`), the coverage
gap (`places.py:54-64`), and the evidence state (`evidence.py:60-63`).

---

## 4. The absent list

This is the section that matters. 18 entries. For each: (a) what it must show, (b) whether the
Auto-Bill visual language extends or a new element must be designed inside the same rules, (c) the
nearest Auto-Bill element to build from.

### A1. Numbered map

(a) One marker per stop with its ordinal, coloured by status (`locked` `#B4532A` vs flexible `#2A6FB4`)
and sized by it (radius 90 vs 60), a distinct gold hotel anchor (`#E0A32E`, radius 120), a
no-coordinates empty state, and — non-negotiable — **a text list beneath carrying exactly the same
distinctions** (`itinerary.py:88-126`).
(b) **The language does not extend. A new element must be designed.** Auto-Bill contains no spatial
element and no map dependency; nothing in `index.css` positions anything geographically.
(c) Nearest: the donut chart's **legend** (`index.css:1547-1578`, `.legend-item` / `.legend-dot` /
`.legend-label` / `.legend-value`) is structurally the numbered stop list — a coloured dot, a label,
a value, click-to-act. Build the map canvas as a `.card` with the signature 1px `#1A1A1A` border and
`--shadow-md`, pins in the accent/success/warning token colours rather than the three raw hexes the
Streamlit version hardcodes, and reuse the legend verbatim for the stop list.
**Note the three hardcoded hexes** (`itinerary.py:94,104` and `#E0A32E`) sit outside the token set —
WF-020 should absorb them.

### A2. Day timeline with activities and legs

(a) Three row types (`shared.py:451-498`): a **visit** row with clock range, stop ordinal, display name,
status, duration, local name, and a disclosure carrying choice level / address / opening-unverified; a
**travel** row with clock range, `origin → destination`, mode, duration, walking minutes, and a
disclosure carrying sightseeing-walk-vs-plain-transfer, distance in metres, transfer count, boarding
buffer; a **buffer** row that is a caption only. Grouped into morning and afternoon
(`itinerary.py:74-87`), with fallback rows interleaved by half-day.
(b) **Extends, as an `adapt` of `.recent-row-item` (26)** — that element already has a colour left
border, a meta chip cluster, a details block, and a right-hand numeric column. What it needs added: a
time gutter, a vertical connector rail between rows, three row variants instead of one, and a nested
disclosure (which no Auto-Bill row has).
(c) Nearest: `.recent-row-item` (`index.css:1598`) for the row, `.mode-badge` (`1827`) for the travel
mode, `.badge-day` (`1804`) for the clock chip, `.category-badge` (`1625`) for the status pill.

### A3. Fallback row

(a) `words['fallback']` label, the trigger code, `primary → replacement`, the replacement start time, a
day-reoptimized flag, and the displaced consequence (`shared.py:430-448`).
(b) Extends. *Unsure whether this is its own element or a fourth variant of A2* — it renders inside the
timeline flow, at the same width, in a bordered container, but it describes a contingency rather than a
scheduled thing. I lean variant; recording the ambiguity rather than deciding.
(c) Nearest: `.insights-card.border-left-amber` (`index.css:1336`) — a warning-coloured left border is
already the language's way of saying "this is a caveat about the thing above".

### A4. Ranked candidate cards with per-card explanations

(a) A photo or an explicit `photo_unavailable` state with an attribution caption; display name plus the
local name when they differ; category; a score out of 100 to one decimal; a duration band
(`min–max minutes`); role badges (protected exploration slot / city icon / local alternative to *X*);
matched tags; **three parallel code-derived lists** (why shown / pros / cons); a dimension table with
points and a per-dimension maximum; deductions as negative points with a reason code; three evidence
lines each with an explicit not-yet value (opening state, route effort, source rating); a source link;
and four decision actions of which exactly one (`not_for_trip`) carries a reason selector.
(`places.py:147-304`.)
(b) **Extends only partly; a new element is required.** `.avatar-preview-card` (40) supplies the
selectable-card skins (`active` / `inactive` / hover, three per-mode active colours), and
`.insights-card` (15) supplies the header-icon + body + price-pair frame. Neither carries media, a
score, or nested explanation, and no Auto-Bill card is more than ~120px tall.
(c) Nearest, composed: `.insights-card` for the frame and its left-border state colour;
`.avatar-preview-card` for selected/unselected; `.stat-value` + `.stat-subvalue` for the score/duration
pair; `.mode-badge` for the role badges; `.hero-banner-image-wrapper` + `.hero-trip-img` (12) for the
media region — but stripped of its upload affordance.
**Load-bearing note:** the Streamlit version is a **selectbox plus one detail panel**
(`places.py:147-155`), not a card grid — Streamlit cannot lay out comparable cards. **Do not port the
selectbox.** The card grid is the thing the port exists to make possible, and `.stat-cards-grid`'s
`auto-fit minmax(220px, 1fr)` is the layout already in the file.

### A5. Three-variant optimizer comparison

(a) `best_balance`, `relaxed`, `more_highlights` **side by side**, each with its status, five metrics
(scheduled visits, travel minutes, walking minutes, plain walking minutes, buffer minutes), a
greedy-check pass indicator, a stopped-at-limit flag, a warning list, a reconciliation table, and a
timeline; activation permitted only for a variant that is `ready` and validated
(`optimize.py:63-155`).
(b) **No comparison element of any kind exists in Auto-Bill.** But the language extends cleanly: three
`.stat-card` columns inside one `.card`, selected by `.split-modes-tabs`, stays entirely inside the
rules. So: a new `variant-compare` element, composed from existing parts, not a new visual idea.
(c) Nearest: `.split-modes-tabs` (39) for the three-way pick — it already carries a distinct accent per
option, which maps onto three variants; `.stat-card` (14) for each metric cell; `.manual-validation-panel`
(41) for the greedy-check pass/fail framing.
**Load-bearing note:** the Streamlit version shows **one variant at a time** because a selectbox is all
it has (`optimize.py:65-71`), and the 5 metrics are split 3+2 because a fifth of a centred page clips
the labels (`optimize.py:73-74`). Both are Streamlit artifacts. Showing three at once is the point.

### A6. Evidence / provenance panel

(a) Per evidence kind: the state (`verified` / missing / `stale` / `unavailable` / `error`), the
retrieval timestamp, the authority or source URL, **the estimated cost of fetching it**, and one button
that spends money — plus the license/attribution line and the raw provider report behind a disclosure
(`evidence.py:26-119`, `places.py:88-93`, `places.py:238-245`).
(b) **Nothing in Auto-Bill answers "where did this fact come from, when, and what did it cost".**
A new element is needed — but its shape already exists.
(c) Nearest, and closer than expected: **`.backup-card-header` + `.backup-grid p` + one button**
(`index.css:1966-2012`, `Dashboard.jsx:2117-2127`) is exactly *icon + title + one paragraph of prose +
one action*, which is exactly the evidence card's shape. Add a state pill (`.mode-badge`), a
`.font-mono` timestamp line, and put the spend button in the **warning or danger** colour so a paid
action can never look like a free one — `evidence.py:65-67` records that as a decision.

### A7. Readiness board with deadlines and verification states

(a) Timing buckets as sections; per item: a requirement level, a progress state, an **independent**
evidence state, a due date, a consequence, an editable progress control, a not-applicable reason field
that appears conditionally, an evidence sub-panel (expected authority, source URL, authority type, last
checked), a dismiss action; a dismissed-history list with restore; a **proposal preview** of additions /
removals / deadline moves before anything is applied; and overdue / due-soon banners that also render
on the setup stage (`readiness.py`, `shared.py:334-427`, `setup.py:123-128`).
(b) **Extends, but the two-axis state is genuinely new.** Auto-Bill has no deadline, no date chip, and
nothing whose state has two independent dimensions. A `board-item` element must be designed — two pills
that do not imply each other, a date chip, a nested disclosure.
(c) Nearest: `.recent-row-item` (26) for the row shape; `.mode-badge` (28) for the two pills — it
already supports four mutually-exclusive colour skins, so two independent pill sets is a natural
extension; `.badge-day` (`index.css:1804`) for the due-date chip; `.manual-validation-panel` (41) for
the verified/needs-verification framing; `.settings-people-row` (32) for the row-with-inline-control-
and-remove-icon pattern.

### A8. Version history with restore

(a) An append-only revision list — timestamp, operation, `from` → `to` short version ids in monospace;
a separate plan-version list with each version's cause and a restore action; and the invariant that
restoring **creates a new version and deletes nothing** (`revise.py:199-220`).
(b) **Extends.** No list-with-per-row-action exists, but `.settings-people-row` is one row with one
action button, and `.font-mono` (`index.css:2371`) already handles the short ids.
(c) Nearest: `.settings-people-row` (32) or a `.recent-list` row (26) stripped to two columns.
Auto-Bill's nearest *conceptual* neighbour is the backup grid (37) — but export/import is not history:
it has no list, no per-entry action, and no immutable chain.

### A9. Five-step setup with a country-dependent city list

(a) Five steps, not four; a country picker that refreshes the city picker **on change**; both pickers
accepting a typed value so any worldwide destination stays reachable; neither pre-selected; a live
preview of the exact geocoder query; a review step whose four summary rows each jump back to their own
step; a per-step **Save draft** distinct from **Save & continue**; and deadline banners above the
stepper (`setup.py:44-107`, `284-511`).
(b) **Shell: `adapt`. Two parts are `absent`.** The wizard shell (6), step indicator (7), step header
(8) and action row (9) all transfer — but `.wizard-progress-4` / `.progress-step-4` / `.step-num-4` /
`.step-label-4` **encode the step count in the class name**, so five steps means renaming the whole
family (or generalising it, which is the right call). Genuinely absent: (i) the **dependent city
picker** — Auto-Bill has no city concept at all, and its country control is a plain `<select>` over 13
entries with a **separate `isCustomCountry` boolean and a second text input**
(`SetupWizard.jsx:79-96, 373-400`) rather than one combobox that accepts a typed value; (ii) the
**review-with-jump-back rows** (`setup.py:464-474`), for which the wizard has no counterpart —
its step indicator navigates backwards but carries no summary.
(c) Nearest: `.progress-step-4` family for the stepper (rename to be count-agnostic);
`.summary-row-stat` (18) for the review rows plus a `.btn-text` Edit control per row;
`.form-row-two` for the country/city pair; `.currency-info-box` (36) for the destination preview.

### A10. Coverage-gap reporting

(a) The provider status as a **word**, not a number; candidate / duplicates-merged / geographic-cell
counts; grouped unusable-hours reasons (`evidence.py:75-81`); capability gaps as a translated code list
with a count in the sidebar (`app.py:70-73`, `itinerary.py:40-43`); and a stale-setup warning driven by
a **hash mismatch**, not a timestamp (`places.py:50-51`).
(b) **Split.** The three counts are `reuse` on `.stat-card` (14) as-is. The status-as-a-word and the
grouped reason lists are `absent` — a small `gap-list` element is needed: a titled list of translated
codes with a count badge.
(c) Nearest: `.insights-card.border-left-amber` (`index.css:1336`) for the framed gap list;
`.currency-info-box` (36) for the single-line variant; `.mode-badge` for the status word.

### A11. Usage / spend meter against the US$10 cap

(a) Spend to date at four decimals, the cap at two, a request count, three states (`ok` / `warning` at
$8 / `stopped` at the cap), and an owner-editable cap (`app.py:81-87`, `evidence.py:52-63, 121-129`).
(b) **`adapt`, not `absent` — and this is the strongest single reuse in the whole inventory.**
`.person-meter-item` (19) is already a labelled bar with a percentage fill, a primary amount, and a
secondary currency line — structurally identical to a spend-against-cap meter. Changes needed: colour
the fill by state (success → `--color-warning` at 80% → `--color-danger` at 100%) rather than by
participant index; put the cap where the person's name goes; put the request count where `.meter-thb`
goes. Note the selected/dimmed states are inline-only (`Dashboard.jsx:927-936`) and must be lifted into
real classes when ported.
(c) Nearest: `.person-meter-item` + `.meter-bar-container` + `.meter-bar-fill` + `.meter-thb`
(`index.css:1010-1050`).
**Worth flagging explicitly:** nobody would have looked for this. In Auto-Bill the element means "who
owes what"; in the planner it means "how much have we spent on paid APIs". Same element, unrelated
domains.

### A12. Journey progress rail and stage gating

(a) Five gate stages with done / next / not-started marks; which stage blocks which; and a one-line
"do X first" panel when a stage is unreachable, rendered **instead of** the stage
(`app.py:66-69`, `shared.py:158-236`).
(b) **`adapt` of the step indicator (7), plus one new small element.** `.progress-step-4` has active
and inactive, and navigates backwards only — but a wizard is a linear sequence, whereas `journey()` is
a dependency graph with a **blocked** state that the indicator has no expression for. It also lives in
the sidebar permanently rather than at the top of one screen.
(c) Nearest: `.progress-step-4` family (7) rotated vertical, with a third `blocked` state;
`.currency-info-box` (36) for the `require()` panel.

### A13. Before/after consequence panel

(a) Changed dates; a metric before / after / delta table; and **eight** labelled change lists — moved
(with from-date/time → to-date/time), added, removed, shortened, lengthened, displaced (with a reason
code), new warnings, cleared warnings; plus a blocked warning when `can_apply` is false
(`revise.py:102-137`).
(b) **`adapt` of `.manual-validation-panel` (41).** That element is the same idea at a tenth of the
scale: three rows (sum / total / difference), a divider, a status line, and a valid/invalid skin. Scale
it to a diff panel.
(c) Nearest: `.manual-validation-panel` + `.validation-row` + `.validation-divider` +
`.validation-row.status-line` (`index.css:2317-2358`) for the frame; `.transactions-table` (27) for the
before/after/delta grid.

### A14. Feedback banner, toast, and confirm dialog

(a) The planner emits **59** `st.success` / `st.error` / `st.warning` / `st.info` calls across the eight
views and `shared.py` (`costs 5, evidence 7, itinerary 6, optimize 7, places 12, readiness 3, revise 9,
setup 6, shared 4`). Several are structural, not incidental: `require()`'s blocked panel
(`shared.py:227,233`), the flash-after-write pattern in every stage
(`optimize.py:19-21`, `places.py:100-101`, `readiness.py:21-22`, `costs.py:25-26`, `revise.py:21-22`,
`setup.py:139-142`), and the three-level paid-usage state (`evidence.py:60-63`).
(b) **Absent in the direction nobody expects: the port needs a feedback element that Auto-Bill never
had.** Auto-Bill has zero inline feedback elements — 33 `window.alert()` and 5 `window.confirm()`
(catalogue entry 45). A banner element with four levels and a confirm dialog must be designed.
(c) Nearest: `.manual-validation-panel`'s `.valid` / `.invalid` skins (41) already establish how a
success and an error look in this language; `.currency-info-box` (36) establishes the accent-left-border
callout structure; `.modal-card` (38) covers the confirm dialog. The four levels map onto the existing
`--color-success` / `--color-danger` / `--color-warning` / `--color-accent` token pairs, each of which
already has a `-light` companion.

### A15. Data table with translated headers

(a) 13 `st.dataframe` calls whose **column headers come from the language dict**, one of which puts a
URL in a cell (`places.py:82`) and one of which puts a `✓` / `—` presence mark in a cell
(`places.py:387-389`).
(b) **`reuse`.** `.transactions-table` (27) covers it, including the `.overflow-x` wrapper and the
`.no-items-td` empty row.
(c) Nearest: `.transactions-table`. The only change is that headers become data.

### A16. Download button set

(a) Four downloads in **one row** — poster PNG, PDF, XLSX, ICS — with the ICS replaced by an
explanatory caption when the checklist is empty (`itinerary.py:128-173`). The comment at
`itinerary.py:136-137` records the reason: four stacked full-width bars pushed the day's content off
screen.
(b) **`adapt`** of the import/export cards (37): Auto-Bill's export is one full-width card per action
with a paragraph of prose, which is the layout the planner explicitly rejected.
(c) Nearest: `.btn.btn-outline.w-full` inside a 4-up grid, or the `.sidebar-quick-actions` (21)
treatment scaled horizontally.

### A17. Remote photo with an explicit unavailable state

(a) A Wikimedia Commons photo resolved from a `File:` reference (`shared.py:268-277`) with a source
caption, or an explicit `photo_unavailable` caption when there is none (`places.py:164-167`).
(b) **`adapt`.** `.hero-trip-img` + `.hero-banner-image-wrapper` + `.hero-banner-image-overlay` (12) is
the only image element in Auto-Bill, and it is an **upload** affordance — its hover overlay says
"Change Photo". Strip the upload, add an attribution caption and a placeholder state.
(c) Nearest: entry 12's image wrapper.

### A18. Bilingual language control and the code→text layer

(a) A two-option control at the sidebar foot, read **before** its widget is created so the widget can
render last (`app.py:29`, `90-96`); and the rule that switching language changes wording only — never
ranking, scheduling, or the active plan.
(b) **`absent`.** Auto-Bill is English-only, has no language control, and has no code→text layer at
all.
(c) Nearest: `.split-modes-tabs` (39) as a two-way segmented control.
**The consequence is the largest single mechanical change in the port, and it is not a new element:**
every element that displays a code-derived label must take its text from a dict. In Auto-Bill those
labels are inline string literals — `.mode-badge`'s four emoji+word pairs (`Dashboard.jsx:1818-1822`),
the split descriptors (`TransactionModal.jsx:493,516,552,588`), every `.stat-label`
(`Dashboard.jsx:1163,1180,1213`), every `.insights-card` title (`1233,1248,1263,1278`), all 33 alert
strings, and all nine table headers (`Dashboard.jsx:1731-1740`). Roughly 120 hardcoded English strings
across the three components.

---

## 5. Bidirectional gaps — Auto-Bill elements the planner has no use for

**Do not port (dead weight):**

1. **Banner image upload + canvas colour extraction** — `Dashboard.jsx:33-171` (`resetHeroGradient`,
   `mixColor`, `getSaturation`, `getLuminance`, `keepPanelReadable`, `applyHeroGradientFromImage`) plus
   `SetupWizard.jsx:45-77` (client-side JPEG re-compression to 800px). ~200 lines whose entire purpose
   is deriving a panel gradient from a user-uploaded photo. The planner's hero content is a **computed
   day summary**, not a photo. Elegant, and irrelevant.
2. **Reset-trip button** (`.btn-reset-trip`, `index.css:1222`, `Dashboard.jsx:1024-1034`). The planner
   never destroys a trip: `plan_versions` and `discovery_runs` carry SQLite triggers that abort UPDATE
   and DELETE, and the checklist **dismisses rather than deletes** so nothing silently disappears.
   Porting a wipe-everything button would contradict a locked decision.
3. **localStorage persistence** (`App.jsx:9-54`, `43-54`). The planner has SQLite with a sha256
   re-verified on every read. This would be a downgrade.
4. **`alert()` / `confirm()`** (45). Replace with A14 rather than porting.
5. **`.setup-card.glassmorphic-card`** (`index.css:281`) and both `backdrop-filter: blur(var(--glass-blur))`
   uses (`1143`, `2040`). `--glass-blur` is `0px`; all three are no-ops. Dead on arrival.
6. **The duplicated filter bar.** The overview and ledger tabs render the same four-control bar with
   duplicated markup (`Dashboard.jsx:1082-1155` and `1648-1723`). Port one.

**Do not port *yet* — deferred to `Define the split ledger model and where its math lives` (WF-018):**

7. **Settlement grid + settlement item** (29) and **copy-memo** (31). `TP/views/costs.py` records what
   the owner paid, per trip, with **no participants** — there is nothing to settle. These are the whole
   point of the merge; deferred, not dead.
8. **Main-cardholder selector** (30). Same dependency.
9. **Allocation-mode picker** (39), **participant chooser** (40), **manual rows + validation panel**
   (41). All four split modes are ledger-side. Note the planner already has the data source: up to 8
   travellers with ids, labels, ages and tags (`setup.py:376-418`), so the participant chooser has
   somewhere to read from the day WF-018 lands.
10. **Person meter** (19) in its *original* meaning. Its port target is A11 (the spend meter); its
    original per-person-share meaning also waits on WF-018.

**Port at most one of the pair:**

11. **Transaction list row (26) vs transaction table (27).** Two markup shapes for one record. The
    planner needs one table (A15) and one timeline row (A2). Porting both duplicates the maintenance
    that Auto-Bill already pays.

**Probably not, pending a design decision:**

12. **Donut chart (24) and vertical bar chart (25).** Nothing in the planner charts a distribution.
    The nearest candidates are the cost totals (`costs.py:88-92`, three numbers — a stat-card row) and
    the ranking dimension breakdown (`places.py:215-227`, already a table with an explicit per-dimension
    maximum, which a bar chart would express better). Port the bar chart **only** if a design decision
    says the score breakdown becomes a chart; otherwise both are dead weight, and the bar chart's hover
    tooltip (`index.css:1446-1482`) is the most intricate interaction in the file.

**Partial:**

13. **Trip metadata summary box (18).** Four of its five rows map onto the planner's trip context (name,
    destination, dates, duration). The **FX conversion row** belongs to the ledger.
14. **Country accent override (46).** Free for the planner — every trip already has a destination. But
    the table has 13 entries and the planner's worldwide-acceptance requirement means ~190 countries
    fall through; `utils.js:17-161` already degrades gracefully to a flagcdn URL plus `✈️`, so keep the
    fallback path, not just the table.

---

## 6. Load-bearing behaviour to preserve

23 behaviours. **P** = real product behaviour that must survive the port. **S** = Streamlit artifact
that dies with it (sometimes with a rule worth carrying forward).

| # | Behaviour | Anchor | Verdict |
|---|---|---|---|
| 1 | `journey()` decides the landing stage — a returning owner opens on the stage needing attention, not the setup form | `app.py:100`, `shared.py:158-216` | **P** — becomes the default route |
| 2 | `require()` renders one clear next step and returns False, so a view explains itself instead of erroring | `shared.py:219-236` | **P** — becomes a route guard rendering a panel |
| 3 | Setup is five editable steps, not one form; every Save & continue autosaves; nothing typed is lost by navigating | `setup.py:1-20, 241-273` | **P** (behaviour, locked by WF-007). The *stated reasons* — Streamlit drops widget state, `st.form` defers values, `st.rerun()` mid-script leaves two steps in one run — are **S** |
| 4 | The city list depends on the chosen country and refreshes immediately | `setup.py:9-11, 62-69` | **P** |
| 5 | Both destination pickers accept a typed value, so any worldwide destination stays reachable; a city name is **never localized** because it is the geocoder query | `setup.py:59,68`, `shared.py:99-107` | **P**, and a correctness requirement — localizing would change which place is searched |
| 6 | Neither country nor city is pre-selected (`index=None`): "a silently defaulted country would become somebody's trip" | `setup.py:47-49, 55, 65` | **P** |
| 7 | `plain()` escapes `$` so Streamlit does not read `US$0.13 / US$10.00` as inline LaTeX | `shared.py:57-66` | **S** — dies with the port. Re-verify money rendering once in HTML; the hazard is different, not absent |
| 8 | Per-language widget keys with a language-free stored choice (`translated_selectbox` / `translated_multiselect`) | `shared.py:110-140` | **S** — the browser-cache workaround dies. **The rule survives**: a label's language must never change the stored value, and a typed-in option must survive a language switch (`_seed`, `shared.py:99-107`). Free in React; still needs a test |
| 9 | `chosen()` reads the live widget first, then the last remembered choice | `shared.py:81-91` | **S** — dies |
| 10 | A word-valued state is a text line, never a metric | `setup.py:428-433`, `places.py:55-60, 187-188`, `optimize.py:73-74` | **S** reason (metric clipping: "Confirmed f…", "unavaila…", "Not evaluate…") but **P** rule: a state that is a word gets a pill, a state that is a number gets a tile. The codebase learned this three separate times — encode it once in the element set |
| 11 | Three metrics per row, not five | `optimize.py:73-74` | **S** — `.stat-cards-grid`'s `auto-fit` handles it |
| 12 | Card explanations are collapsed by default so the decision buttons stay above the fold and cards remain comparable | `places.py:198-199` | **P** — a disclosure rule, not a layout accident |
| 13 | The unscheduled-choices panel **auto-expands when the day schedules nothing** — "a collapsed panel would leave the owner on a dead-end screen" | `itinerary.py:176-181` | **P** |
| 14 | The rejection reason lives inside the not-for-trip disclosure, not above all four buttons | `places.py:270-272` | **P** |
| 15 | Map marker colours are duplicated as text labels — "Text labels carry the same distinctions as the marker colours" | `itinerary.py:119-126` | **P**, and an accessibility requirement. A prettier map must not drop the list |
| 16 | Every paid action states its cost immediately before the button that spends money, one card per action | `evidence.py:65-67, 82, 36` | **P** — "stacked full-width buttons with the costs in between read as a single wall in which nothing said what it would charge for" |
| 17 | The actual-THB field renders **only** for a `paid` cost; unrated currency codes are flagged inside the picker's `format_func` while the cost is being entered, not as a warning after saving | `costs.py:118-128, 146-159` | **P** |
| 18 | The trip label never prints the destination twice | `app.py:38-48` | **P** |
| 19 | A primary action is disabled with a caption explaining why, never silently | `optimize.py:138-145`, `revise.py:135-142`, `places.py:34-38` | **P** — and it needs a `.btn` disabled token, which `index.css` does not have |
| 20 | Deadline warnings render above the setup stepper — "a deadline matters regardless of which setup step is open" | `setup.py:121-128` | **P**, and cross-stage: the readiness board bleeds into setup |
| 21 | A place shows its localized name and its local name when they differ; a consequence names a place, never a truncated `place_id` | `places.py:159-162`, `shared.py:263-265`, `revise.py:27-35` | **P** |
| 22 | The raw provider report stays reachable behind a disclosure, and the license/attribution renders as a link | `places.py:88-93` | **P**, and a licence obligation |
| 23 | Export bytes are cached **by snapshot sha256 + language** | `shared.py:317-331` | **P** (cache by content hash) wrapped in **S** (`@st.cache_data`) |

Also **S**, and dying quietly: the `*_flash_key` session-state round-trip that every stage uses because
a Streamlit callback cannot draw (`setup.py:138-142` and seven siblings); session-state keys suffixed
with `trip.trip_id`; `st.navigation`'s two-section Build/Use grouping (the *grouping* is a product
choice worth keeping, the mechanism is not); and `AppTest.switch_page` as the test entry point, which
is WF-029's problem.

---

## 7. Where the port is nearly free, and where it is nearly all new

| Stage | Auto-Bill covers | Verdict |
|---|---|---|
| `costs.py` | form fields, amount+currency, table, stat card, modal, grand total | **Nearly free.** Every element exists; only the "rate missing" affordance and the conditional paid field need work |
| `optimize.py` | stat cards, tables, tabs, buttons | **Mostly free** once A5 is built from `.split-modes-tabs` + `.stat-card` — but A5 is where the port *adds* capability Streamlit could not express |
| `setup.py` | wizard shell, step indicator, form fields, tag chips, landing grid | **Mostly free**, but the two absent parts (dependent city picker, review-with-jump-back) are the parts that carry the locked WF-007 decision |
| `readiness.py` | rows, pills, modal, expanders | **Half new** — A7's two-axis state has no counterpart |
| `evidence.py` | backup-card shape, buttons | **Half new** — A6 has the right shape and no semantics |
| `revise.py` | validation panel, tables | **Half new** — A13 scales an existing element; A8 is new |
| `places.py` | card frames, grids, badges, tables | **Mostly new.** A4 is the single largest design gap in the inventory |
| `itinerary.py` | list rows, tabs, hero banner, download buttons | **Mostly new.** A1 (map) has no counterpart at all; A2 adapts one |
| app chrome | shell, theme toggle, sidebar, tabs, person meter | **Nearly free** — including the surprise: the spend meter is `.person-meter-item` |

**The two biggest gaps, ranked:**

1. **The numbered map (A1)** — the only planner element for which Auto-Bill supplies *nothing*: no
   spatial primitive, no dependency, no analogous visual. Everything else in this document is either a
   reuse, an adapt, or a new element composed from existing parts.
2. **The ranked candidate card (A4)** — Auto-Bill supplies parts (a selectable card skin, a framed
   insight card, a media wrapper, badges) but no card anywhere in the file is more than ~120px tall or
   carries nested explanation. This is the element the port must design, and it is also the element the
   port *unlocks*: Streamlit could only ever render it as a selectbox plus one panel.

**The most surprising finding:** the US$10 spend meter, which reads like a bespoke planner concern, is a
straight adapt of `.person-meter-item` — an element built to show who owes whom. And the reverse
surprise: **inline feedback**, which reads like the most basic thing any UI has, is entirely absent from
Auto-Bill and must be designed from scratch to replace 59 Streamlit banner calls.
