# Rebuilding /places and /evidence around real content

The owner's three complaints were that `/places` looked ugly and unhelpful, that its
summary was "too broad and identical", and that its "why" section told them nothing
useful for a decision. All three were correct, and the third was measurable.

## The "why" complaint, in numbers

`why_shown`'s top two codes — `group_preference_match` and
`member_preferences_considered` — appear on **793 of 832** cards. `pros`'
`open_export_source` appears on **all 832**. So the section explained the *matcher*,
never the place. And the card's summary line was a **template** built from those same
codes, which is exactly why every card read alike.

No amount of layout work fixes that. It needed content the app did not have.

## The content was free, and one hop away

Discovery already stored a **`wikidata` id for 373 of 832** candidates. One Wikidata
call gives sitelinks for every language plus a `P18` image claim; one Wikipedia
summary call per language gives the prose. **US$0.00, no API key.**

Going straight to Wikipedia does not work: OSM's tags for Taipei are **333 `zh`
against 12 `en`**, so the article you reach is Chinese. Wikidata is the bridge, and it
carried a Thai sitelink too.

On the real trip: 12 of 13 landmarks stored, 12 with an image, 11 with English prose,
**3 with Thai** — Thai Wikipedia simply has fewer articles, and that gap is shown
rather than filled.

### Why not the AI API the owner asked about

An LLM would be cheaper than Google (`openai:interpret_revision` US$0.002 against
`google_places:card_details` US$0.04) and **worse than free**. Wikipedia's prose is
human-written, in both languages, and carries a citation. Paying to generate something
unsourced and weaker is the wrong trade. An LLM earns its place only for gap-filling —
condensing, or translating where `thwiki` is missing — which is generation from a
cited source rather than recall. Using one to produce opening hours would be inventing
facts, and Places keeps that job.

## What changed on screen

- The card leads with **a photograph and real prose** under "About this place", with
  CC BY-SA attribution and a link to the article. The templated sentence survives only
  as the fallback when nothing was found.
- "Why shown" is retitled **"Why it matched your preferences"** — honest about being
  about the matcher, and left collapsed.
- `/places` now **opens on City Icons rather than the main queue.** Measured: the main
  queue's top 20 holds **4 of 20** with a Wikidata id and led with an *RC model
  airplane runway*; City Icons' top 20 holds **20 of 20**. The queue is one select
  away.
- Summaries fetch **on demand for the card in front of you**, because the screen
  browses 832 candidates and only 13 were selected. A button, not an effect: an effect
  would fire a network call every time the select moved.
- `/evidence` groups gaps by **what closes them** — answer in setup, fetch evidence,
  needs your confirmation. They arrived as one flat ⚠ list, so "type an address" and
  "press a button" looked like the same kind of problem.

## The finding: the baseline gate does not cover what I changed

Twelve of the 36 baselines moved. **Not one of them was `places` or `evidence`.**

The moved twelve were `setup`, `split` and `revise` in all four variants — and those
moved because the **trip data** changed today: travellers went from zero to two,
headcount to three, plan versions to eight. Legitimate content change, re-approved.

The two screens actually redesigned did not move, because **at 1440×900 the changes
are below the fold.** A single-viewport screenshot witnesses the top ~900 px of a page
that scrolls far past it. So "36 screen baselines pass" is a weaker claim than it
sounds for any long screen, and the visual work here is covered by the Vitest
assertions rather than by the image gate.

That is worth knowing before trusting the gate on a future redesign. It is not a
reason to distrust it for what it does cover — drift in the top of each screen — but
it is not whole-page coverage and should not be described as such.

## Four things that went wrong on the way

- **`_selected_places` did not carry `signals`**, so every place was skipped for want
  of a Wikidata id while the report said `fetched: 0` with no failure — a silent no-op
  that reads as success. There is now a test for exactly that.
- **`list_place_evidence` returns the stored value** and does not add `place_id` back,
  so it has to live inside the value. The opening-hours evidence already did this;
  mine did not until it raised.
- **Wikimedia rate-limits bursts.** Eight of thirteen places returned HTTP 429 until
  requests were spaced and retried.
- **`str.replace` has no count by default**, so the `PlaceSummary` type was inserted
  into `client.ts` twice. Caught by `tsc`, not by me.

And one test that measured the fixture instead of the change: the first version keyed
its seeded summary on `harajuku` while the rendered card was `taipei-101`, so it
proved the fallback path worked and nothing else.
