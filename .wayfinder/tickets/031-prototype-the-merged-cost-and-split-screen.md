---
id: WF-031
title: Prototype the merged cost and split screen
status: open
labels:
  - "wayfinder:prototype"
parent: WF-MAP-002
assignee:
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

Produce a throwaway prototype and link it from this ticket. Record what the owner reacted against, not just
what was built.
