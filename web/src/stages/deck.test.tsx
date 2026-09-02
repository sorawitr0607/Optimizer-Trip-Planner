import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { DiscoveryCandidate, PlaceInsight, PlaceSummary, Ranking } from "../api/client";
import { warmTargets } from "../shared/photos";
import { PlaceDeck } from "./PlaceDeck";

/**
 * `WF-036` built against `WF-005`.
 *
 * The gesture cannot be exercised by `renderToStaticMarkup`, which is the reason the
 * deck was built with buttons as the mechanism and the swipe as an accelerant. What
 * is asserted here is therefore the whole contract: the 4:1 queue order, the required
 * card content, the exploration card being labelled as such, and every action being
 * reachable without a pointer.
 */

const CARD = {
  place_id: "",
  total_score: 71.5,
  relative_match_percent: 88,
  dimensions: {
    group_preference_fit: { score: 24, max: 30 },
    experience_value: { score: 18, max: 20 },
    reward_vs_effort: { score: 10, max: 20 },
    time_fit: { score: 6, max: 10 },
    route_compatibility: { score: 12, max: 15 },
    evidence_quality: { score: 4, max: 5 },
  },
  deductions: [],
  candidate_tags: ["sightseeing"],
  matched_tags: ["sightseeing"],
  matched_people: ["owner"],
  learned_category_bonus: 0,
  experience_value: 18,
  is_city_icon: true,
  city_icon_basis: ["wikipedia"],
  queue_role: "ranked",
  why_shown: ["group_preference_match"],
  pros: ["preference_match"],
  cons: ["route_not_verified"],
  duration_estimate: { minimum_minutes: 45, maximum_minutes: 90, origin: "planner_category_default" },
  feasibility: { state: "not_evaluated_until_optimizer" },
  ratings: {},
  example_reviews: [],
  effort_state: "unknown",
  route_distance_to_selected_metres: null,
} as unknown as Ranking["cards"][string];

const RANKING = {
  cards: {
    first: { ...CARD },
    explore: { ...CARD, total_score: 52.0, relative_match_percent: 35 },
  },
  lanes: {
    main_queue: [
      { place_id: "first", role: "ranked" },
      { place_id: "explore", role: "protected_exploration" },
    ],
    city_icons: [],
    worth_it_if: [],
    local_alternatives: [],
    browse_all: [],
  },
  coverage: {},
} as unknown as Ranking;

const SUMMARY: Record<string, PlaceSummary> = {
  first: {
    place_id: "first",
    qid: "Q1",
    text: { en: "A landmark tower with an observation deck." },
    image_url: "https://commons.example/one.jpg",
    image_urls: ["https://commons.example/one.jpg", "https://commons.example/two.jpg"],
    licence: "CC BY-SA, Wikipedia and Wikimedia Commons",
    source_urls: { en: "https://en.wikipedia.org/wiki/One" },
  },
};

/** `explore` has no encyclopedia entry but does carry OpenStreetMap's own photo tag,
 *  which is the case the third image source exists for. */
const CANDIDATES = {
  first: { place_id: "first", photo_reference: null },
  explore: { place_id: "explore", photo_reference: "File:Quiet Park.jpg" },
} as unknown as Record<string, DiscoveryCandidate>;

function render(
  summaries: Record<string, PlaceSummary>,
  choices: string[] = [],
  entries = RANKING.lanes.main_queue,
  rejected: string[] = [],
  summaryLoading = false,
  ranking: Ranking = RANKING,
  insights: Record<string, PlaceInsight> = {},
  photoError: string | null = null,
  photosUnavailable = false,
  optimisticDecided: ReadonlySet<string> = new Set(),
  /** Which place the failure and the no-match are about. Defaults to the card these
   *  tests put in front, so the two cases above read exactly as they did. */
  about = "first",
) {
  const photoErrorOf = (placeId: string) =>
    placeId === about ? photoError : null;
  // Mirrors `PlacesPage.photoWithheld`, which is the caller this prop exists for: a
  // stored no-match withdraws the offer, and so does a failed ask.
  const photoWithheld = (placeId: string) =>
    placeId === about && photosUnavailable
      ? "none"
      : photoErrorOf(placeId)
        ? "failed"
        : insights[placeId]
          ? "bought"
          : null;
  return renderToStaticMarkup(
    <PlaceDeck
      candidates={CANDIDATES}
      choices={[
        ...choices.map((place_id) => ({ place_id, action: "must_do", reason: null }) as never),
        ...rejected.map((place_id) => ({ place_id, action: "not_for_trip", reason: null }) as never),
      ]}
      entries={entries}
      insights={insights}
      language="en"
      altNameOf={(placeId) => (placeId === "first" ? "台北101" : null)}
      nameOf={(placeId) => (placeId === "first" ? "Taipei 101" : "A quiet park")}
      onDecide={() => {}}
      onWantPhotos={() => {}}
      onWantSummary={() => {}}
      paidPhotoUsd={0.075}
      photoErrorOf={photoErrorOf}
      photoWithheld={photoWithheld}
      optimisticDecided={optimisticDecided}
      ranking={ranking}
      summaryLoading={summaryLoading}
      summaries={summaries}
    />,
  );
}

describe("PlaceDeck paid photo control", () => {
  /**
   * A failed ask must withdraw the offer, not repeat it.
   *
   * The card said no photograph could be found and kept a button beside it inviting the
   * owner to pay for one again — a control that contradicts the sentence above it, and
   * the owner reported reading both. This is the same shape as the buy button withdrawing
   * once a purchase has *succeeded*: asking again buys the answer already in hand.
   *
   * Scoped to the card, and session-only: a provider that was merely busy is not a
   * finding about the place, so a reload offers the purchase again. That is the line
   * between this and the stored `provider_no_match` refusal, which is a finding.
   */
  /** No free photograph at all, which is the state the paid offer exists for.
   *  `SUMMARY.first` carries two and is correctly never offered a purchase. */
  const BLANK = { first: { ...SUMMARY.first, image_url: null, image_urls: [] } };

  it("offers the purchase on a card with no free photograph", () => {
    const html = render(BLANK, [], RANKING.lanes.main_queue, [], false, RANKING, {});

    expect(html).toContain("Get photographs from Google");
  });

  it("withdraws the purchase once the ask has failed for that card", () => {
    const html = render(
      BLANK, [], RANKING.lanes.main_queue, [], false, RANKING, {},
      "No photograph could be found for this place",
    );

    expect(html).not.toContain("Get photographs from Google");
    // And the reason is on the card, where the question was asked.
    expect(html).toContain("No photograph could be found for this place");
  });

  it("withdraws the purchase after Google's durable no-match answer", () => {
    const html = render(BLANK, [], RANKING.lanes.main_queue, [], false, RANKING, {}, null, true);

    expect(html).not.toContain("Get photographs from Google");
  });

  /**
   * The withdrawal belongs to one place, and the deck must ask about the card it is
   * drawing rather than trust a scalar the parent derived from another id.
   *
   * `photosUnavailable` and `photoError` used to arrive already reduced to booleans
   * against `cardId` — the id this deck last *reported* — so the condition was correct
   * by the parent's bookkeeping rather than by construction. Answering for a different
   * place now leaves the drawn card's offer exactly where it was.
   */
  it("keeps the offer up when the refusal belongs to a different place", () => {
    const html = render(
      BLANK, [], RANKING.lanes.main_queue, [], false, RANKING, {},
      "No photograph could be found for this place", true,
      new Set(), "some-other-place",
    );

    expect(html).toContain("Get photographs from Google");
  });
});

describe("PlaceDeck", () => {
  it("shows the facts WF-005 requires that can actually differ between places", () => {
    const html = render(SUMMARY);
    expect(html).toContain("Taipei 101");
    // Both names, because 61% of the Taipei catalogue has no `name:en` and the local
    // string is what the signage and a taxi driver use.
    expect(html).toContain("台北101");
    // The score reads as fit now, not as an exam mark: same number out of the same 100,
    // rounded, because a tenth of a percent of a heuristic is precision it does not have.
    expect(html).toContain("88% match");
    expect(html).not.toContain("/100");
    // The description is deliberately NOT here. The panel beside the deck renders the
    // same paragraph from the same summary, so the card printed text already on screen
    // — and the card is for deciding, not for reading.
    expect(html).not.toContain("A landmark tower");
    // The always-true facts read as a caption now, not as labelled rows: the duration is
    // there, its label is not, because "Visit estimate: 45-90 min" and "45-90 min" carry
    // the same information and one of them is shorter.
    expect(html).toContain("45–90");
    expect(html).not.toContain("Visit estimate");
    // Held back for the same reason as the other two: `ranking.py` hardcodes
    // `reward_vs_effort` to 10 of 20 and marks `effort_state`
    // `route_and_walking_not_evaluated`, so this row read "10/20" on every card in the
    // catalogue. Found auditing the scoring formula, not by reading the card.
    expect(html).not.toContain("Effort and access");
    // Three of WF-005's rows are not facts about this place, they are constants.
    // `ranking.py` fixes `feasibility.state` before the optimizer runs; no licensed
    // source backs cost/reservation at all; and `cons` is seeded with
    // `route_not_verified`, `ratings_not_enriched` and `best_time_unconfirmed` on every
    // candidate alike. This card's only con is one of those three, so the crowd row has
    // nothing to say and does not appear. Printed anyway they train the eye past the
    // rows that do differ, so their absence is asserted and restoring one is deliberate.
    expect(html).not.toContain("Crowd and tourist-trap signals");
    expect(html).not.toContain("Cost and reservation");
    expect(html).not.toContain("Feasibility");
    expect(html).toContain("CC BY-SA");
    // The second card must not be on screen: this is a deck, not a list.
    expect(html).not.toContain("A quiet park");
  });

  it("advances immediately while a decision is waiting for its refetch", () => {
    const html = render(SUMMARY, [], RANKING.lanes.main_queue, [], false, RANKING, {}, null, false, new Set(["first"]));

    expect(html).toContain("A quiet park");
    expect(html).not.toContain("Taipei 101");
  });

  it("shows value once visit time has been estimated", () => {
    const estimated = {
      ...RANKING,
      cards: {
        ...RANKING.cards,
        first: {
          ...CARD,
          effort_state: "visit_time_estimated",
          dimensions: { ...CARD.dimensions, reward_vs_effort: { score: 16, max: 20 } },
        },
      },
    } as unknown as Ranking;
    const html = render(SUMMARY, [], RANKING.lanes.main_queue, [], false, estimated);

    expect(html).toContain("Value for time");
    expect(html).toContain("16/20");
  });

  it("shows the crowd row once a con is about the place, not about the pipeline", () => {
    // The other half of the same rule: the row is held back for the three seeded
    // constants, and appears the moment a con actually describes this place.
    const flagged = {
      ...RANKING,
      cards: {
        ...RANKING.cards,
        first: { ...CARD, cons: ["route_not_verified", "possible_duplicate"] },
      },
    } as unknown as Ranking;
    const html = render(SUMMARY, [], RANKING.lanes.main_queue, [], false, flagged);

    expect(html).toContain("Crowd and tourist-trap signals");
    expect(html).toContain("Possible duplicate needs owner review");
    // The seeded constant beside it is still filtered out.
    expect(html).not.toContain("are not routed yet");
  });

  it("offers every decision as a real button, not only as a gesture", () => {
    const html = render(SUMMARY);
    for (const label of ["Must do", "Interested", "Maybe", "Not for trip", "Skip for now"]) {
      expect(html).toContain(label);
    }
    // A gesture-only deck would exclude keyboard and screen-reader users.
    expect(html).toContain("Drag the card");
    expect(html).toContain("The buttons do the same thing");
    expect(html).toContain('tabindex="0"');
  });

  it("separates the drag surface from the actions, and names each action", () => {
    // A `pointerdown` bound to the whole card meant pressing a button started a
    // drag and a drag over a button ended in a click. The surface stops above the
    // action row, and `touch-action` lives on it so the browser cannot claim the
    // gesture for scrolling — the reason the swipe did nothing on a touchscreen.
    const html = render(SUMMARY);
    // Not an exact class match: the surface also carries `pending` until the card's
    // first photograph has painted.
    expect(html).toContain('class="place-deck-drag');
    // Colour, not five identical greys, and the class carries the action code so
    // the stylesheet and the handler cannot drift apart.
    for (const action of ["must_do", "interested", "maybe", "not_for_trip", "skip"]) {
      expect(html).toContain(`choice-${action}`);
    }
  });

  it("loads the visible photo eagerly, because it is the card", () => {
    // `loading="lazy"` was delaying the one image the owner is waiting on.
    const html = render(SUMMARY);
    expect(html).toMatch(/<img[^>]*loading="eager"/);
    expect(html).not.toContain('loading="lazy"');
  });

  it("warms nothing while the card is still waiting for its own photograph", () => {
    /**
     * The gate and the warming were competing for one connection. Every URL here is
     * `commons.wikimedia.org`, so the whole gallery plus the lead images of the next four
     * cards are multiplexed alongside the single download that decides whether the card
     * may be shown — ~3 MB of speculative bytes against the ~344 kB one the owner is
     * actually waiting on.
     *
     * Withheld means warm nothing. Shown means warm everything, which is the state the
     * card spends seconds in while it is read, so nothing is lost by waiting.
     */
    const gallery = ["a.jpg", "b.jpg"];
    const ahead = ["next-1.jpg", "next-2.jpg"];

    expect(warmTargets(true, gallery, ahead)).toEqual([]);
    expect(warmTargets(false, gallery, ahead)).toEqual(["a.jpg", "b.jpg", "next-1.jpg", "next-2.jpg"]);
  });

  it("labels the exploration card so a low score is not read as a bad pick", () => {
    // WF-005: one protected exploration card per four ranked ones. Deciding the
    // first card leaves the exploration card in front.
    const html = render(SUMMARY, ["first"]);
    expect(html).toContain("A quiet park");
    expect(html).toContain("widen the search");
    expect(html).toContain("35% match");
  });

  it("shows a placeholder outside the card it stands in for", () => {
    // The skeleton was rendered *inside* `.place-deck-drag`, which is hidden while the
    // first photograph loads — so it was hidden along with the card and a loading card
    // was simply a blank space. It has to be a sibling to be visible at all.
    const html = render(SUMMARY);

    expect(html).toContain("place-deck-pending");
    expect(html).toContain("place-deck-drag");
    // The placeholder opens before the hidden surface does, so it cannot be inside it.
    expect(html.indexOf("place-deck-pending")).toBeLessThan(html.indexOf("place-deck-drag"));
  });

  it("keeps the card gated until its photograph has actually painted", () => {
    /**
     * **No deadline releases a card early.** One was tried — four rotations of the
     * loading line — and the owner reported the result the same day: a card on screen
     * with `Loading` still in its picture frame. That is the swipe decision offered on
     * half the evidence, which is the thing this gate exists to prevent, so a slow card
     * is answered by making it *not slow* (the deck warms `WARM_AHEAD` lead images ahead
     * of the one in front) and never by showing it unfinished.
     *
     * A photograph is unpainted in a static render, so this is the pending state: the
     * placeholder is up and every decision is refused. `act()` guards the same condition
     * for the keyboard and for a gesture already in flight.
     */
    const html = render(SUMMARY);

    expect(html).toContain("place-deck-pending");
    // Not one disabled control among many: every decision on the card is refused.
    const decisions = ["Must do", "Interested", "Maybe", "Not for trip"];
    for (const label of decisions) {
      const at = html.indexOf(`>${label}<`);
      expect(at, `${label} should render`).toBeGreaterThan(-1);
      // The button opens before its label, and carries `disabled` when the card is not
      // ready. Search the tag rather than the whole document.
      const tag = html.lastIndexOf("<button", at);
      expect(html.slice(tag, at), `${label} must be disabled while the card loads`)
        .toContain("disabled");
    }
  });

  it("locks every decision while the selected card summary is loading", () => {
    const html = render({}, [], RANKING.lanes.main_queue, [], true);

    expect(html).toContain('aria-busy="true"');
    expect((html.match(/disabled=""/g) ?? [])).toHaveLength(5);
  });

  it("counts the gallery and makes the photo itself the control", () => {
    const html = render(SUMMARY);
    expect(html).toContain("Photo 1 of 2");
    expect(html).toContain("commons.example/one.jpg");
    // The image sits inside a button so a keyboard can advance it.
    expect(html).toMatch(/<button[^>]*class="place-deck-photo"/);
  });

  it("offers the free fetch when a card has no imagery yet", () => {
    const html = render({});
    expect(html).toContain("Load free descriptions");
    expect(html).toContain("free, no key");
    expect(html).not.toContain("Photo 1 of");
  });

  it("shows OpenStreetMap's own photo when there is no encyclopedia entry", () => {
    // Most of a dense city's catalogue has no Wikidata id, so Wikipedia alone left the
    // card blank. `photo_reference` is already on every candidate and cost nothing.
    const html = render({}, [], [{ place_id: "explore" }]);

    expect(html).toContain("Special:FilePath/Quiet_Park.jpg");
    expect(html).toContain("Photo 1 of 1");
  });

  it("reloads the whole card with the paid session gallery", () => {
    const blank = {
      first: {
        ...SUMMARY.first,
        image_url: null,
        image_urls: [],
      },
    };
    const paid = {
      first: {
        photo_gallery: [
          { uri: "https://places.example/paid-one.jpg" },
          { uri: "https://places.example/paid-two.jpg" },
        ],
      },
    };

    const html = render(blank, [], RANKING.lanes.main_queue, [], false, RANKING, paid);

    expect(html).toContain("places.example/paid-one.jpg");
    expect(html).toContain("Photo 1 of 2");
    expect(html).not.toContain("Get photographs from Google");
  });

  it("names all four directions, up included", () => {
    // Right is `must_do` and up is `interested`, at the owner's asking. Up used to be
    // `maybe` — paired with `skip` as the two ways of not answering yet, a tidy symmetry
    // that spent the deck's second-strongest gesture on its weakest answer. `maybe` keeps
    // its button; the legend and the arrow keys move with the gestures or the three stop
    // agreeing about what a swipe does.
    const html = render(SUMMARY);
    for (const label of ["Must do", "Interested", "Not for trip", "Skip"]) {
      expect(html).toContain(label);
    }
    expect(html).toContain("Tap the photo");
  });

  it("says so when every unseen place has been decided", () => {
    const html = render(SUMMARY, ["first", "explore"]);
    expect(html).toContain("Every unseen place has had a decision");
  });

  it("counts the finished deck and offers every passed place back", () => {
    // Reaching the end used to print one line and nothing else, so a place dropped in
    // the first ten cards was unrecoverable without hunting the detailed list for it.
    const html = render(SUMMARY, ["first"], RANKING.lanes.main_queue, ["explore"]);

    expect(html).toContain("You have shortlisted 1 places and passed on 1.");
    expect(html).toContain("Reconsider skipped places");
    expect(html).toContain("A quiet park");
    expect(html).toContain("Add to list");
  });

  it("names a passed place and offers a way to look at it properly", () => {
    // Three shapes have been tried here. A `<details>` spent a click on finding out
    // whether the click was worth spending. Everything inline turned a scannable list
    // of skipped names into a wall of pictures. So: the name, and a control that says
    // what it opens -- the full card beside the deck, which has the score, the
    // breakdown and the gallery this row could only ever hint at.
    const html = render(SUMMARY, ["explore"], RANKING.lanes.main_queue, ["first"]);

    expect(html).not.toContain("<details");
    expect(html).toContain("View details");
    // The row stays a row: no photograph and no prose inlined into it.
    expect(html).not.toContain("commons.example/one.jpg");
  });

  it("deals from whichever lane it is given, not always from main_queue", () => {
    // The deck hardcoded `main_queue`, whose top 20 have no Wikidata id on the real
    // Taipei catalogue — so it opened on twenty cards with no photograph while the
    // list beside it had already moved to City Icons for that exact reason.
    const html = render(SUMMARY, [], [{ place_id: "explore" }]);

    expect(html).toContain("A quiet park");
    expect(html).not.toContain("Taipei 101");
    // A lane that is not the queue carries no role, so the exploration note stays off.
    expect(html).not.toContain("widen the search");
  });

  it("filters decided places out of any lane, not only the queue", () => {
    // `main_queue` excludes decided places server-side; the other lanes do not, so
    // without the local filter a City Icons deck would re-deal answered cards.
    const html = render(SUMMARY, ["explore"], [{ place_id: "explore" }, { place_id: "first" }]);

    expect(html).toContain("Taipei 101");
    expect(html).not.toContain("A quiet park");
  });
});
