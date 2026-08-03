---
id: WF-031
title: Prototype the merged cost and split screen
status: closed
labels:
  - "wayfinder:prototype"
parent: WF-MAP-002
assignee: user-and-root
blocked_by:
  - WF-023
  - WF-025
  - WF-028
---

# Prototype the merged cost and split screen

## Question

What does the joined money screen actually look like and feel like — two ledgers, a rate snapshot, payment
states, participants, and a settlement view, in the Auto-Bill visual language, in both languages?

## Context

This is the highest-risk screen in the whole redesign: it is the only place where the merge is visible to the
owner, and it carries more state than any Auto-Bill screen ever had. Build it rough and throwaway; the
question is whether the arrangement is right, not whether the code is.

- Auto-Bill's dashboard already solves part of this and is worth reacting to directly: stat cards, filters by
  traveller, day, and category, the settlement grid, a main-cardholder selector, and a transaction modal with
  three allocation modes.
- What it never had to show: an `estimate` / `committed` / `paid` state per row, a paid row whose THB is locked
  against later rate changes, a timestamped rate snapshot with a source and an optional buffer that the owner
  may edit, a per-currency rate table rather than one flat rate, and rows that no rate can convert at all —
  `costs.totals()` reports `unconvertible_rows` and `missing_rates` because a missing rate must stay a visible
  gap rather than a guess.
- Two ledgers must be legible as two ledgers without making the owner do arithmetic in their head; the
  reconciliation ticket decides the rules, this ticket decides how they read.
- Thai and English both need to fit, and numerals are set in JetBrains Mono while text is Plus Jakarta Sans.
- Phone matters: the owner uses this during the trip, standing up, after paying for something.

Two things the decided split model forces onto this screen specifically:

- **Balances are trip-to-date totals and settling up is never recorded.** So the screen must present a balance
  as a suggestion rather than an outstanding-debt claim — after a traveller actually transfers the money, the
  app will keep showing the same number, and the wording has to survive that without lying to anyone.
- **The cardholder can owe a traveller.** Cash a non-cardholder fronted is netted off, so the direction of a
  balance is not fixed. Auto-Bill only ever renders `{person} owes {cardholder}` (`Dashboard.jsx:1531`) and its
  memo template says the same, so both need a reversed form in both languages.

**2026-07-31 — the premise changed, and this ticket's title is now misleading.**
[Map every stage to its webapp screen and route](028-map-every-stage-to-its-webapp-screen-and-route.md)
decided that costs and split are **two cross-linked screens**, not one merged screen, on the owner's
distinction: costs is the *estimated* cost for the drafted plan, split is the function that splits the bill
for *actual cost that happened*, with values linkable and editable between them. So `/costs` carries the
estimates, the rate snapshot, payment states, `unconvertible_rows` and `missing_rates`; `/split` carries
Auto-Bill's full surface — the 694-line `TransactionModal`, participant chips, settlement grid, cardholder
selector — plus the link action's editable result. Everything below still applies; it applies across two
screens and the link between them rather than one arrangement. The hardest questions are unchanged: making
two ledgers legible as two without mental arithmetic, presenting a balance as a suggestion when settling up
is never recorded, and rendering a reversed owe-direction in both languages.

Produce a throwaway prototype and link it from this ticket. Record what the owner reacted against, not just
what was built.

## Resolution comments

### 2026-08-03 — Prototyped and reviewed

Prototype: [`031-money-screens-prototype.html`](../artifacts/031-money-screens-prototype.html) — one
self-contained file, EN/TH and light/dark toggles, a phone width, and no external requests. Throwaway per the
map, so nothing landed in `web/` and the Phase 2 code freeze holds.

It renders **two** screens, not one, following
[Map every stage to its webapp screen and route](028-map-every-stage-to-its-webapp-screen-and-route.md):
`/costs` carries planned/actual/diff by category plus the estimated per-person figure, `/split` carries the
transaction list, aggregates, settlement and the recovered filter interaction. Tokens are the extracted
contract with deviations **D1, D2, D5, D8** applied, and the five concatenated alphas are named tint tokens.

**Nine decisions were put up for reaction. All nine were confirmed**, so the arrangement stands as built:

1. Two per-person numbers computed differently (headcount vs real participants) sitting on different screens
   with a note joining them — **approved**.
2. The reversed direction ("You pay Dad") coloured as a warning, since the cardholder owing a traveller is the
   surprising case Auto-Bill could never render — **approved, with one addition (below)**.
3. Settled as an owner marker that does not change the balance, cleared when a row involving that traveller
   changes — approved.
4. "Suggestions, not debts" as a standing panel rather than per-row wording — approved.
5. Unclaimed-paid-row warnings on the planned screen, where the double-count risk lives — approved.
6. A missing rate keeping rows in NT$ and out of every THB total rather than guessing — approved.
7. Voided rows staying visible, struck through and dimmed — approved.
8. The claim link as a text action on the planned row, with an accent rail on the linked split row — approved.
9. The accent being destination-driven teal rather than the house red — approved.

**The one thing reacted against: filtering was missing.** That is the right catch, and it was the largest gap
in the prototype rather than a detail — **6 of the 23 classes styled only inline are the filter interaction**
(`.active-filter`, `.dimmed-filter`, `.active-cat`, `.dimmed-cat`, `.active-bar`, `.dimmed-bar`), the biggest
recoverable group in the whole extraction, and this ticket's own Context lists Auto-Bill's traveller / day /
category filters as something "worth reacting to directly." Omitting it left the single most
stylesheet-invisible behaviour untested by the prototype.

Added, using the values recovered in
[`020-auto-bill-token-contract.md` §10e](../artifacts/020-auto-bill-token-contract.md): a `1.5px` border and
tint fill on the selected chip, weight `800` when selected, `0.4` on unselected chips and `0.35` on
non-matching rows. Filters combine across Who and Category, and **dim rather than hide** — which is the
behaviour that keeps a total that moved explainable, and is consistent with voided rows staying visible.

Two fidelity limits are recorded on the page itself so nobody mistakes them for decisions: **Plus Jakarta Sans
and JetBrains Mono are substituted by a system stack**, because the woff2 files are not in the repo yet
(`WF-034`) and the artifact runtime blocks font CDNs — so weights and metrics are approximate; and the day
filter is present as a group but the sample data carries only one day.
