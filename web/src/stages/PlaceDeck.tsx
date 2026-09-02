import { useEffect, useRef, useState } from "react";

import type { CandidateChoice, DiscoveryCandidate, PlaceInsight, PlaceSummary, Ranking } from "../api/client";
import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";
import { flyToShortlist } from "../shared/flyToShortlist";
import { distinguishingCons, evaluatedEffort, evaluatedFeasibility } from "../shared/cards";
import { PHOTO_THIN_AT, galleryFor, warmTargets } from "../shared/photos";
import { tagIcon } from "../shared/tagIcons";

/**
 * The swipe deck `WF-005` decided on 2026-07-28 and `WF-036` left to prototype.
 *
 * One card at a time from `main_queue`, which the core already builds to the ratio
 * that ticket specified: four highest-ranked unseen candidates, then one protected
 * exploration card. Verified on the real Taipei catalogue — ranked, ranked, ranked,
 * ranked, protected_exploration, repeating, with all 111 already-decided places
 * absent. So "swipe updates reorder only unseen cards, and rated cards keep their
 * decisions" needs nothing here: the queue arrives that way.
 *
 * **Swipe is not the only way in.** A gesture-only deck locks out keyboard and
 * screen-reader users, so every action has a real button and the arrow keys work.
 * The gesture is an accelerant, never the mechanism — which also lets
 * `renderToStaticMarkup` test the whole thing, since the buttons are the truth.
 *
 * The first gesture did not work, and reported as "swipe is not working". Four
 * causes, all fixed here, none of them the threshold:
 *
 * - **No pointer capture.** A drag that left the element never delivered its
 *   `pointerup`, so the gesture died silently — which is most drags, since a swipe
 *   that commits is a drag that leaves.
 * - **No `touch-action`.** The browser claimed the gesture for scrolling and sent
 *   `pointercancel`, so on a touchscreen or trackpad it could not complete at all.
 * - **No feedback.** The card never moved, so there was nothing to tell an owner
 *   the gesture existed, was being recognised, or had passed the threshold.
 * - **`pointerdown` bound to the whole card**, buttons included, so a press on a
 *   control started a drag and a drag over a control ended in a click.
 */

/** How far a drag must travel to commit, in pixels. Below this the card springs back. */
const COMMIT_DISTANCE = 96;
/** Where the pending action starts being named, as a fraction of the commit distance. */
const HINT_FRACTION = 0.35;
/**
 * How far the pointer must move before a press becomes a drag.
 *
 * Capturing on `pointerdown` broke tapping the photograph to see the next one: a
 * captured pointer retargets its events, so the inner button never received the click.
 * Nothing is captured until the pointer has actually travelled, so a tap stays a tap.
 */
const DRAG_SLOP = 6;
/** How many more cards one press of "show more" reveals. Matches the page the screen
 *  deals in, so the count on the button is the count you get. */
const LANE_STEP = 20;

type Intent = "must_do" | "interested" | "not_for_trip" | "skip" | "maybe" | null;

/** The same normalisation `discovery.py` dedupes on, so the two agree about what
 *  counts as the same name: case folded, punctuation and spacing dropped. */
/** The lines shown while a card arrives. */
const LOADING_LINES = [
  "loading_card",
  "loading_card_2",
  "loading_card_3",
  "loading_card_4",
  "loading_card_5",
  "loading_card_6",
] as const;

/** How long each loading line holds before the next one. */
const LOADING_LINE_MS = 1400;

/** How many cards ahead of the one in front get their lead photograph warmed.
 *
 * Four, because `PlacesPage` already fetches summaries ten ahead, so their image URLs are
 * known long before they are needed, and four is enough runway for fast decisions without
 * making the burst that earns a Wikimedia 429. The card in front still warms its whole
 * gallery; these are one image each. */
const WARM_AHEAD = 4;

/** Idle time before the card nudges, and how long the nudge itself runs. */
const NUDGE_AFTER_MS = 5000;
const NUDGE_MS = 700;
/** How many times one card will offer the hint before letting it go. */
const NUDGE_TIMES = 3;

/**
 * Where the loading line starts for this card.
 *
 * Derived from the place id rather than drawn at random: two cards in a row do not open
 * on the same sentence, and a screenshot of a loading deck is still the same screenshot
 * twice — `Math.random()` here would be the self-drifting-baseline bug that the export
 * timestamp and the paid-usage counter were already fixed for. The lines then advance on
 * a timer, because a wait that is long enough to notice wants something that is visibly
 * still running, which one fixed sentence is not.
 */
function loadingLine(placeId: string, step: number): string {
  let hash = 0;
  for (const character of placeId) hash = (hash * 31 + character.charCodeAt(0)) % 100_000;
  return LOADING_LINES[(hash + step) % LOADING_LINES.length];
}

function nameKey(value: string): string {
  return value.normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
}

interface Drag {
  pointerId: number;
  fromX: number;
  fromY: number;
  x: number;
  y: number;
}

/** Which way a drag is going, once it is going anywhere. Vertical beats sideways only
 *  when it is clearly vertical, so a lazy diagonal still reads as a decision. */
function intentOf(drag: Drag | null): Intent {
  if (!drag) return null;
  const reach = COMMIT_DISTANCE * HINT_FRACTION;
  if (Math.abs(drag.y) > Math.abs(drag.x)) {
    if (drag.y > reach) return "skip";
    // Up is `interested`, at the owner's asking. It used to be `maybe`, paired with
    // `skip` as the two ways of not answering yet — a tidy symmetry that spent the
    // deck's second-strongest gesture on its weakest answer. `maybe` keeps its button.
    if (drag.y < -reach) return "interested";
    return null;
  }
  // Right is the strongest keep, which is what the legend beside it says.
  if (drag.x > reach) return "must_do";
  if (drag.x < -reach) return "not_for_trip";
  return null;
}

function committed(drag: Drag): boolean {
  return Math.abs(drag.x) >= COMMIT_DISTANCE || Math.abs(drag.y) >= COMMIT_DISTANCE;
}

export interface PlaceDeckProps {
  ranking: Ranking;
  /** Which lane the deck deals from. `main_queue` is `WF-005`'s 4:1 ranked-to-exploration
   *  queue and stays the default *shape* of the stage — but on the real Taipei catalogue
   *  20 of its top 20 have no Wikidata id, so the deck opened on twenty cards with no
   *  photograph and no description. The list beside it moved to `city_icons` for exactly
   *  that reason at S4 and the deck did not follow; now it does, and the lane picker
   *  drives both. Every lane still reaches `main_queue` in one select. */
  entries: Ranking["lanes"]["main_queue"];
  /** The normalized catalogue by place id, for OpenStreetMap's own photo tag. */
  candidates: Record<string, DiscoveryCandidate>;
  summaries: Record<string, PlaceSummary>;
  /** Paid, session-only photographs keyed by the card they were bought for. */
  insights?: Record<string, PlaceInsight>;
  choices: CandidateChoice[];
  language: Language;
  /** Resolves a display name. Passed in so `shared/names.ts` stays the one place
   *  naming happens, per the S5 consolidation. */
  nameOf: (placeId: string) => string;
  /** The local-script name to show beside it, or null when it would repeat. 61% of the
   *  Taipei catalogue has no `name:en` at all, so this is often the only readable pair
   *  the app can offer. */
  altNameOf: (placeId: string) => string | null;
  /** Records a decision and advances. `null` reason means none was given. */
  onDecide: (placeId: string, action: string, reason: string | null) => void;
  /** True while the card in front is still arriving, so the panel beside it can wait. */
  onPendingChange?: (pending: boolean) => void;
  /** Buy Google's photographs for a place no free source has one for. */
  onWantPhotos?: (placeId: string) => void;
  /** Prevents a second paid press while the first gallery is still arriving. */
  photosLoading?: boolean;
  /** Why the photographs did not come, when the ask itself failed — answered inside
   *  the photo area rather than in a banner above the deck, where it read as the deck
   *  being broken. Asked **per place**: see `photoWithheld`. */
  photoErrorOf?: (placeId: string) => string | null;
  /** Why the paid offer is withheld for one place, or null when it should be offered.
   *
   *  A function rather than a boolean because the answer is *about a place*. These
   *  arrived as two scalars the parent derived from `cardId` — the id this deck last
   *  reported through `onCardChange` — while the card actually drawn is `queue[0]`.
   *  The two agree in the settled state and need not during a decision, so the
   *  condition was right by the parent's bookkeeping rather than by construction.
   *  Asking about `entry.place_id` cannot be scoped to the wrong card.
   *
   *  The permanence reported as "it is always hidden after I once hid it" was not
   *  here: `provider_no_match` was stored with a 90-day expiry that nothing read, so
   *  the server kept reporting the refusal for ever. Fixed in
   *  `actions._provider_no_match_ids`.
   *
   *  What *is* fixed here is the two controls disagreeing. The deck withdrew on a
   *  failed ask and the detail panel beside it did not, so one card offered the same
   *  purchase in one place and refused it in the other; both now ask this. */
  photoWithheld?: (placeId: string) => string | null;
  /** Decisions made before the choices refetch completes. */
  optimisticDecided?: ReadonlySet<string>;
  /** What that costs, so the price is on the button rather than a screen away. */
  paidPhotoUsd?: number | null;
  /** Fetches the free description and photographs for one place. */
  onWantSummary: (placeId: string) => void;
  /** True while this card's description and photographs are still on their way. The card
   *  used to appear complete-but-empty in that window, with a "load them yourself" button
   *  under it — indistinguishable from a place that genuinely has none. */
  summaryLoading?: boolean;
  /** How many more of this lane are held back by the cap, and how to ask for them. The
   *  deck cannot tell "you have decided everything here" from "you have reached the end
   *  of the page" without being told, and those want opposite things said. */
  laneRemaining?: number;
  onShowMore?: () => void;
  /** Somewhere else to go once a lane really is finished. */
  onPickLane?: (lane: string) => void;
  lanes?: readonly string[];
  lane?: string;
  /** The card now in front, so the detail panel beside the deck follows it instead of
   *  sitting on whichever place a select last pointed at. */
  onCardChange?: (placeId: string) => void;
}

export function PlaceDeck({
  ranking,
  entries,
  candidates,
  summaries,
  insights = {},
  choices,
  language,
  nameOf,
  altNameOf,
  onDecide,
  onPendingChange,
  onWantPhotos,
  photosLoading = false,
  photoErrorOf = () => null,
  photoWithheld = () => null,
  optimisticDecided = new Set(),
  paidPhotoUsd,
  onWantSummary,
  summaryLoading = false,
  laneRemaining = 0,
  onShowMore,
  onPickLane,
  lanes = [],
  lane,
  onCardChange,
}: PlaceDeckProps) {
  const [photo, setPhoto] = useState(0);
  /** Places flicked past this sitting, in the order they were skipped. Lives at
   *  the top because the queue below filters on it. */
  const [skippedIds, setSkippedIds] = useState<string[]>([]);
  // *Every* photograph that has painted, not just the most recent one. Holding a
  // single url meant the pulsing placeholder came back on every tap through the
  // gallery -- including for pictures already decoded and sitting in the browser
  // cache -- so tapping quickly through a card read as the page blinking. A set
  // answers the question actually being asked: has *this* one arrived before.
  const [painted, setPainted] = useState<ReadonlySet<string>>(() => new Set());
  const markLoaded = (url: string) =>
    setPainted((current) => (current.has(url) ? current : new Set(current).add(url)));
  const [drag, setDrag] = useState<Drag | null>(null);
  const [leaving, setLeaving] = useState<Intent>(null);
  // A drag that ends over the photo used to advance the gallery as well as decide.
  const travelled = useRef(0);
  /** The card being decided, so the flight can be cut from its photograph. */
  const cardRef = useRef<HTMLDivElement | null>(null);

  /**
   * A photograph counts as arrived when it can be *painted*, not when its bytes have.
   *
   * `complete` and `onLoad` both mean "the response finished", and the image is decoded
   * afterwards — `decoding="async"` asks for exactly that, off the main thread. So a card
   * could be released while its picture was still a blank box, which is the swipe
   * decision made on nothing and the report that survived three rounds of "the skeleton
   * stops after the first two cards": the skeleton was correct that the bytes were in,
   * and wrong that the owner could see anything.
   *
   * `decode()` resolves when the frame is ready to draw. It rejects on a broken image and
   * on an `src` that changed mid-flight, and both mean "stop waiting for this one" — the
   * card is released either way, because a card held forever is worse than a card
   * released early.
   */
  function markPainted(element: HTMLImageElement, url: string | null) {
    if (!url) return;
    if (typeof element.decode !== "function") {
      markLoaded(url);
      return;
    }
    element
      .decode()
      .catch(() => undefined)
      .finally(() => markLoaded(url));
  }

  const decided = new Set([
    ...choices.map((choice) => choice.place_id),
    ...optimisticDecided,
  ]);
  // And by name, not only by id. Discovery merges two records of one place when the
  // name and the spot match, but it cannot merge what it cannot tell apart — a zoo
  // signs the same exhibit twice, 200m apart — so the same attraction still reaches
  // the deck under two ids. Being asked again about a name you just answered is the
  // complaint whatever the cause, and the name is what the owner recognises.
  const decidedNames = new Set(
    choices
      .map((choice) => nameKey(nameOf(choice.place_id)))
      .filter(Boolean),
  );
  // `main_queue` already excludes decided places, but a decision made in this session
  // has not been refetched yet — and the other lanes do not exclude them at all — so
  // filtering here is what makes any lane dealable. Skips leave the queue the same
  // way, on the session list alone: a skip records nothing server-side, so without
  // this a skipped card sat in the deck for ever — and skipping the *last* card
  // clamped the cursor there, with no way to ever reach the end-of-lane panel where
  // the reconsider lists live.
  const queue = entries.filter(
    (entry) =>
      !decided.has(entry.place_id) &&
      !decidedNames.has(nameKey(nameOf(entry.place_id))) &&
      !skippedIds.includes(entry.place_id),
  );
  // The card in front is the first of those left: decided cards leave on the
  // refetch, skipped ones leave through the session list the moment the skip
  // lands, so there is no cursor to move and none to forget.
  const entry = queue[0];
  const card = entry ? ranking.cards[entry.place_id] : undefined;
  const currentId = entry?.place_id;
  const [shownCard, setShownCard] = useState<string | undefined>(currentId);
  // Synchronous with the prop change: the previous card's gallery index must never
  // make the next card look loaded before React commits the reset below.
  const photoIndex = currentId === shownCard ? photo : 0;

  const about = entry ? summaries[entry.place_id] : undefined;
  // Paid photographs lead once the owner asks for them; free encyclopedia and
  // OpenStreetMap images remain behind them. `enrich_place_card` deliberately returns a
  // session overlay, so invalidating the free-summary query cannot make these appear.
  const paidGallery = entry
    ? (insights[entry.place_id]?.photo_gallery ?? []).map((photo) => photo.uri)
    : [];
  const gallery = [...new Set([
    ...paidGallery,
    ...galleryFor(about, entry ? candidates[entry.place_id] : undefined),
  ])];

  // Wikimedia serves every one of these through a `Special:FilePath` redirect, so the
  // first byte costs two round trips. Warming the next photo and the next card's
  // first photo while this one is being read is the whole fix for "images load very
  // slowly": by the time the card turns over, the bytes are in the browser cache.
  // The lead photograph of the next several cards, not just the next one.
  //
  // One ahead is only enough if every card is read slowly. A card decided in a second
  // arrives at a picture that has had a second to load, over a `Special:FilePath`
  // redirect that costs a round trip before the first byte — which is the whole of "the
  // card takes so long". Warming the run means the picture is usually already decoded by
  // the time its card reaches the front, and the gate below never has anything to wait
  // for. Lead images only: the full gallery is warmed for the card actually in front,
  // and warming six deep for four upcoming cards is the burst Wikimedia answers 429 to.
  const nextUrls = queue
    .slice(1, 1 + WARM_AHEAD)
    .map((item) =>
      insights[item.place_id]?.photo_gallery?.[0]?.uri
        ?? summaries[item.place_id]?.image_url
        ?? null,
    )
    .filter((url): url is string => Boolean(url));
  // Which photo is on screen, and which one has finished arriving. Held as the URL
  // rather than a boolean so that tapping through a gallery shows the placeholder again
  // for each new picture, and a cached one never flashes it at all.
  const currentPhoto = gallery.length ? gallery[photoIndex % gallery.length] : null;
  // The card is *withheld* until its first picture has painted, not merely the picture
  // box. A card that arrives complete-but-imageless and fills in a second later is the
  // one thing the owner cannot un-see: the swipe decision is made on the photograph, so
  // showing the text first invites a decision on half the evidence. Only the first
  // photo gates the card — tapping through the gallery must not blank it again.
  // **A card is shown only when it is finished.** There is no deadline releasing it
  // early: one was tried, at four rotations of the loading line, and the owner reported
  // the result immediately — a card on screen with `Loading` still sitting in its picture
  // frame. That is the swipe decision offered on half the evidence, which is the thing
  // this gate exists to prevent, so releasing early cannot be the answer to a slow card.
  // Making it *not slow* is: see the warming below, which now covers several cards ahead
  // rather than one. A broken image still releases the card, through `onError`.
  const cardPending = summaryLoading
    || (Boolean(currentPhoto) && !painted.has(currentPhoto!) && photoIndex === 0);
  // Report the card in front, so the panel beside the deck tracks it.

  // The gallery index belongs to the card, so it resets with the card.
  //
  // It was reset in `decide()` and the skip path of `act()` only — the two ways *this*
  // deck moves on — and not when the card in front changed for any other reason. Changing lane is the
  // and not when the card in front changed for any other reason. Changing lane is the
  // common one, which is why the owner's repro was "after deciding twenty from City
  // Icons and switching category": tap twice through a gallery, switch lane, and the new
  // card arrives with `photo` still at 2. `cardPending` requires `photo === 0`, so it was
  // false, so **no skeleton and a swipeable card whose picture had not loaded** — and the
  // card also opened on its third photograph rather than its first.
  //
  // Adjusted during render rather than in an effect: this is state derived from a prop
  // that changed, which is the shape React sanctions for it, and an effect would paint
  // one frame of the wrong card's gallery first.
  if (currentId !== shownCard) {
    setShownCard(currentId);
    setPhoto(0);
  }
  useEffect(() => {
    if (currentId) onCardChange?.(currentId);
    // `onCardChange` is a fresh closure each render; the card id is what changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentId]);

  // The detail panel beside the deck describes *this* card, so while the card is still
  // arriving the panel is describing a place the owner cannot see — the same "deciding on
  // half the evidence" problem the card gate exists to prevent, one element over.
  useEffect(() => {
    onPendingChange?.(cardPending);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cardPending]);

  // A nudge after five idle seconds, so the card says it can be thrown.
  //
  // The deck already carries a grip bar, two coloured edges and a legend, and the gesture
  // was still reported as undiscovered — all of those are things to read, and nobody
  // reads a card they are looking at. Movement is the one hint that does not need
  // reading. It waits for the card to have arrived (a placeholder cannot be swiped),
  // restarts on every new card, and stops the moment a drag begins, because a hint that
  // keeps firing while someone is using the thing it is hinting at is an animation
  // fighting the hand.
  const [nudge, setNudge] = useState(false);
  useEffect(() => {
    if (cardPending || drag) return;
    if (typeof document !== "undefined" && document.documentElement.dataset.capture) return;
    // Three times per card, then it stops. A hint that keeps pulsing every five seconds
    // for as long as someone is reading stops being a hint and becomes a fidget — and
    // whoever has not taken it by the third has understood and declined it. The count
    // resets with `currentId`, so each new card gets its own three.
    let fired = 0;
    const timer = window.setInterval(() => {
      setNudge(true);
      // Long enough for the animation to finish before the class comes off, so the next
      // one can retrigger it.
      window.setTimeout(() => setNudge(false), NUDGE_MS);
      fired += 1;
      if (fired >= NUDGE_TIMES) window.clearInterval(timer);
    }, NUDGE_AFTER_MS);
    return () => window.clearInterval(timer);
  }, [cardPending, drag, currentId]);

  // Advance the loading line while a card is arriving, and only then: a timer left
  // running behind a loaded deck is a re-render a second for nothing.
  const [loadingStep, setLoadingStep] = useState(0);
  /** Which reconsider row is open, so its detail can be laid out beside the name. */
  const [openRow, setOpenRow] = useState<string | null>(null);
  useEffect(() => {
    if (!cardPending) return;
    const timer = window.setInterval(
      () => setLoadingStep((current) => current + 1),
      LOADING_LINE_MS,
    );
    return () => window.clearInterval(timer);
  }, [cardPending]);

  // The **whole** gallery of the card in front, plus the next card's lead image.
  //
  // Only one photo ahead was warmed, so a second tap outran the prefetch and a third and
  // fourth each waited on a cold fetch — "tap to advance is loading so long". A gallery
  // is a handful of images the browser will cache anyway, they are free, and the owner
  // has already shown they want them by opening the card. Widening this got cheaper to
  // justify and more necessary at the same time: reading a subject's Commons category
  // means galleries are now six deep where they used to be one or two.
  //
  // Every URL is a `Special:FilePath` redirect, which costs a round trip before the bytes
  // start — a direct `upload.wikimedia.org/thumb/...` URL would save it, and cannot be
  // built: Wikimedia refuses widths outside its own listed set, measured as HTTP 400 for
  // the 640 this app asks for. Warming them early is the way to pay that cost off screen.
  // ...but not while the card is still withheld waiting for its own first photograph.
  // `warmTargets` holds that rule and the measurement behind it; the burst was competing
  // with the one download the gate is blocked on, over the single connection they share.
  const galleryKey = gallery.join("|");
  const aheadKey = nextUrls.join("|");
  useEffect(() => {
    for (const url of warmTargets(cardPending, gallery, nextUrls)) {
      const image = new Image();
      image.decoding = "async";
      image.src = url;
    }
    // `gallery` and `nextUrls` are rebuilt each render; their contents are what matter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [galleryKey, aheadKey, cardPending]);

  if (!entry || !card) {
    const rejectedChoices = choices.filter((c) => c.action === "not_for_trip");
    const shortlistedChoices = choices.filter((c) => c.action === "interested" || c.action === "must_do");
    // A skip that has since been decided is not a skip any more; the choices
    // are the truth, so the session list is read through them.
    const skippedHere = skippedIds.filter((id) => !choices.some((c) => c.place_id === id));
    return (
      <div className="place-deck-exhausted">
        <div className="deck-finished-card">
          <p className="deck-finished-title">✓ {copy("deck_exhausted", language)}</p>
          <p className="setup-hint">
            {copyFormat("deck_kept_and_passed", language, {
              kept: shortlistedChoices.length,
              passed: rejectedChoices.length,
            })}
          </p>
          {/* Two different endings, said differently. Reaching the cap is "there is more
              if you want it"; reaching the end of a lane is "this list is spent, here is
              another". They used to be the same blank wall. */}
          {/* Both, not one or the other. "More of this lane" and "try another lane" are
              different questions and the owner has both at once — offering only the first
              until the lane is exhausted meant the other lanes were effectively invisible,
              since a 431-card lane never runs out. */}
          {laneRemaining > 0 && onShowMore ? (
            <button className="setup-primary" onClick={onShowMore} type="button">
              {copyFormat("lane_more", language, {
                count: Math.min(laneRemaining, LANE_STEP),
              })}
            </button>
          ) : null}
          {onPickLane && lanes.length > 1 ? (
            <div className="deck-lane-suggest">
              <p className="setup-hint">
                {copy(laneRemaining > 0 ? "lane_try_another" : "lane_seen_all", language)}
              </p>
              <div className="lane-tabs">
                {lanes
                  .filter((value) => value !== lane)
                  .map((value) => (
                    <button
                      className="lane-tab"
                      key={value}
                      onClick={() => onPickLane(value)}
                      type="button"
                    >
                      {copy(value, language)}
                    </button>
                  ))}
              </div>
            </div>
          ) : null}
          {skippedHere.length > 0 ? (
            <div className="deck-reconsider">
              <h4 className="money-eyebrow">{copy("deck_skipped", language)}</h4>
              {/* The same rows as the reconsider list, because they are the same
                  question wearing a different past: these were never decided, so
                  "add to list" is the whole action. Deciding one removes it from
                  here on the next render, which is why the list filters against
                  the choices rather than mutating its own. */}
              <ul className="deck-reconsider-list">
                {skippedHere.map((placeId) => (
                  <li className="deck-reconsider-row" key={placeId}>
                    <div className="deck-reconsider-detail">
                      <span className="deck-reconsider-name">{nameOf(placeId)}</span>
                      <button
                        className="deck-reconsider-view"
                        onClick={() => {
                          setOpenRow(placeId);
                          onCardChange?.(placeId);
                        }}
                        title={copy("deck_view_details_hint", language)}
                        type="button"
                      >
                        {copy("deck_view_details", language)}
                      </button>
                    </div>
                    <button
                      className="deck-reconsider-btn"
                      onClick={() => onDecide(placeId, "interested", null)}
                      type="button"
                    >
                      + {copy("deck_add_back", language)}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {rejectedChoices.length > 0 ? (
            <div className="deck-reconsider">
              <h4 className="money-eyebrow">{copy("deck_reconsider", language)}</h4>
              {/* Each row opens. Changing your mind about a place you passed on twenty
                  cards ago means remembering what it was, and the name alone is not
                  enough — the picture and the sentence are what the decision was made
                  on. Everything here is already in hand: no fetch, and a `<details>`
                  so the platform owns the open/close and the keyboard. */}
              <ul className="deck-reconsider-list">
                {rejectedChoices.map((c) => {
                  // No photograph or prose read here: the row shows neither, and the
                  // card beside the deck fetches its own.
                  return (
                    <li
                      className={`deck-reconsider-row${openRow === c.place_id ? " open" : ""}`}
                      key={c.place_id}
                    >
                      {/* The detail is *not* shown here. It was, briefly, and it turned a
                          scannable list of skipped names into a wall of pictures --
                          which is the same problem the `<details>` had, arrived at from
                          the other side. The full card already exists beside the deck,
                          with the score, the breakdown and the gallery; this row's job
                          is to name the place and offer the two things you can do with
                          it, one of which is look properly. */}
                      <div className="deck-reconsider-detail">
                        <span className="deck-reconsider-name">{nameOf(c.place_id)}</span>
                        <button
                          className="deck-reconsider-view"
                          onClick={() => {
                            setOpenRow(c.place_id);
                            onCardChange?.(c.place_id);
                          }}
                          title={copy("deck_view_details_hint", language)}
                          type="button"
                        >
                          {copy("deck_view_details", language)}
                        </button>
                      </div>
                      <button
                        className="deck-reconsider-btn"
                        onClick={() => onDecide(c.place_id, "interested", null)}
                        type="button"
                      >
                        + {copy("deck_add_back", language)}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  const name = nameOf(entry.place_id);
  const altName = altNameOf(entry.place_id);
  const intent = leaving ?? intentOf(drag);

  function decide(action: string, reason: string | null = null) {
    // Every keep flies. Written as "not the rejection" rather than as a list of the
    // keeps, because the list was wrong on its first draft — `must_do` is a keep and is
    // dispatched only from the button row, so naming them one by one silently omitted the
    // strongest one. `not_for_trip` is the single action that does not join the shortlist,
    // and sending it there would say the opposite of what happened.
    if (action !== "not_for_trip") {
      flyToShortlist(
        cardRef.current,
        document.querySelector(".shortlist-handle"),
      );
    }
    onDecide(entry!.place_id, action, reason);
    setPhoto(0);
    // Do not advance the cursor: the decided card leaves the queue on refetch, so
    // the same index is already the next card. Advancing too would skip one.
  }

  /** Commit whatever the gesture, an arrow key or a button asked for. */
  function act(action: Intent) {
    // Nothing lands on a card that has not finished arriving, whatever asked. The
    // buttons are disabled and the drag surface is out of layout while pending, but a
    // keypress, a gesture already in flight when the card changed, or any future caller
    // reaches this function directly — and a decision recorded against a place the owner
    // never saw is the one outcome none of those guards may miss.
    if (cardPending) return;
    if (action === "skip") {
      // A skip records nowhere else — and it leaves the queue through the session
      // list alone, exactly like a decided card leaves through the refetch: no
      // cursor move at all, because the same index is already the next card.
      // Advancing too would deal past one. The record is what makes the skip
      // reachable again at the end of the lane, which is where "wait, what was
      // the one I flicked past?" used to dead-end.
      if (entry) {
        setSkippedIds((ids) => (ids.includes(entry.place_id) ? ids : [...ids, entry.place_id]));
      }
      setPhoto(0);
    } else if (action === "must_do") decide("must_do");
    else if (action === "interested") decide("interested");
    else if (action === "maybe") decide("maybe");
    else if (action === "not_for_trip") decide("not_for_trip", null);
  }

  function endDrag(current: Drag | null) {
    if (!current) return;
    const action = committed(current) ? intentOf(current) : null;
    setDrag(null);
    if (!action) return;
    // Let the card finish leaving before the queue swaps under it, so a commit reads
    // as the card going away rather than as a flicker.
    setLeaving(action);
    setTimeout(() => {
      setLeaving(null);
      act(action);
    }, 140);
  }

  const offsetX = leaving
    ? (leaving === "interested" ? 1 : leaving === "not_for_trip" ? -1 : 0) * 420
    : (drag?.x ?? 0);
  const offsetY = leaving
    ? (leaving === "skip" ? 420 : leaving === "maybe" ? -420 : 0)
    : (drag?.y ?? 0);
  // The transform is omitted entirely when the card is sitting still, rather than being
  // written as an identity. An inline style beats a stylesheet animation, so a permanent
  // `translate(0,0) rotate(0)` would have silently swallowed the idle nudge — the class
  // would go on, the keyframes would be correct, and nothing would move.
  const resting = offsetX === 0 && offsetY === 0;
  const style = {
    ...(resting
      ? {}
      : { transform: `translate(${offsetX}px, ${offsetY}px) rotate(${offsetX / 26}deg)` }),
    transition: drag ? "none" : "transform var(--duration-standard) var(--ease-out)",
  };

  return (
    // derives-from: element 14 .stat-card as .place-deck
    <section
      aria-label={copy("deck_mode", language)}
      className="place-deck"
      onKeyDown={(event) => {
        // The same four directions the drag uses, so one mental model covers both.
        // The arrows are the gestures, so they move together or the two stop agreeing.
        if (event.key === "ArrowRight") act("must_do");
        else if (event.key === "ArrowLeft") act("not_for_trip");
        else if (event.key === "ArrowDown") act("skip");
        else if (event.key === "ArrowUp") act("interested");
        else return;
        event.preventDefault();
      }}
      style={style}
      tabIndex={0}
    >
      {/* The drag surface stops above the action row, so pressing a button never
          starts a gesture and a gesture never ends in a click. */}
      {/* The placeholder sits *outside* the surface it stands in for. It was inside, and
          `visibility: hidden` on the card hid the placeholder with it — so a loading card
          was simply a blank space, which is what "the card is hidden but I want a
          skeleton" was reporting. Overlaid rather than stacked, so the deck keeps one
          card's height and nothing jumps when the photograph lands. */}
      {cardPending ? (
        <div aria-busy="true" className="place-deck-pending">
          {/* A small block that says what it is, rather than a full-height grey copy of
              the card. The card's own height is still held by the element underneath, so
              nothing jumps when the photograph lands — only the placeholder shrank. */}
          <p className="place-deck-pending-text">
            {copy(loadingLine(entry.place_id, loadingStep), language)}
          </p>
          <span aria-hidden="true" className="skeleton skeleton-photo" />
          <span aria-hidden="true" className="skeleton skeleton-line" />
        </div>
      ) : null}
      <div
        className={`place-deck-drag${drag ? " dragging" : ""}${cardPending ? " pending" : ""}${nudge ? " nudge" : ""}`}
        onPointerCancel={() => setDrag(null)}
        ref={cardRef}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          // No capture yet. Capturing here retargets every later event at this element,
          // which is why tapping the photograph to advance the gallery did nothing.
          travelled.current = 0;
          setDrag({ pointerId: event.pointerId, fromX: event.clientX, fromY: event.clientY, x: 0, y: 0 });
        }}
        onPointerMove={(event) => {
          const surface = event.currentTarget;
          setDrag((current) => {
            if (!current || current.pointerId !== event.pointerId) return current;
            const x = event.clientX - current.fromX;
            const y = event.clientY - current.fromY;
            travelled.current = Math.abs(x) + Math.abs(y);
            // Past the slop it is a drag, so capture it — this is what keeps a gesture
            // alive once the pointer leaves the card, which is most gestures that commit.
            if (travelled.current > DRAG_SLOP && !surface.hasPointerCapture(event.pointerId)) {
              surface.setPointerCapture(event.pointerId);
            }
            return { ...current, x, y };
          });
        }}
        onPointerUp={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
          }
          endDrag(drag);
        }}
      >
        <header className="place-deck-head">
          <p className="setup-hint">
            {/* The card in front is always the first of those left — decided and
                skipped cards leave the queue, so the counter counts the deal:
                one past the number already gone, out of where the lane started. */}
            {copy("deck_position", language)
              .replace("{current}", String(entries.length - queue.length + 1))
              .replace("{total}", String(entries.length))}
          </p>
          {/* "76% match", not "71.5/100". The number is the same one -- the formula is
              already out of 100, so this is a relabel and not a rescale -- but a score
              out of a hundred asks the reader to know what a good score is, and nothing
              on the card tells them. Framed as fit it answers the question the card is
              actually for. Rounded, because a tenth of a percent of a heuristic is
              precision the number does not have. */}
          <strong className="place-score">
            {copyFormat("relative_match", language, {
              percent: card.relative_match_percent ?? Math.round(card.total_score),
            })}
          </strong>
        </header>

      {/* What the release will do, named while the card is still in hand. */}
        {intent ? (
          <p className={`place-deck-intent intent-${intent}`} aria-hidden="true">
            {copy(
              intent === "must_do"
                ? "drop_to_must_do"
                : intent === "interested"
                  ? "drop_to_interested"
                  : intent === "not_for_trip"
                    ? "drop_to_reject"
                    : intent === "maybe"
                      ? "drop_to_maybe"
                      : "drop_to_skip",
              language,
            )}
          </p>
        ) : null}

        {gallery.length ? (
          // A tap advances the gallery, which is what the owner asked for. It is a
          // button so that a keyboard reaches it and a screen reader announces it.
          <button
            className="place-deck-photo"
            onClick={() => {
              if (travelled.current > 8) return; // that was a drag, not a tap
              setPhoto((current) => (current + 1) % gallery.length);
            }}
            type="button"
          >
            {/* A pulsing placeholder over the image until it is actually painted.
                Wikimedia serves these through a redirect and re-encodes the thumbnail,
                so on a slow link the card sat with an empty box where the picture goes
                — indistinguishable from a place that has no picture at all. It covers
                rather than replaces, so the image is still fetched eagerly and nothing
                below it moves when the bytes land. */}
            <span className="place-deck-photo-frame">
              {!currentPhoto || painted.has(currentPhoto) ? null : (
                <span aria-hidden="true" className="skeleton skeleton-photo" />
              )}
              <img
                alt={name}
                // Eager and high priority: this image is the card, always above the
                // fold, and `loading="lazy"` was actively delaying the one photo the
                // owner is waiting on.
                decoding="async"
                draggable={false}
                fetchPriority="high"
                loading="eager"
                onError={() => currentPhoto && markLoaded(currentPhoto)}
                onLoad={(event) => markPainted(event.currentTarget, currentPhoto)}
                // A photograph already in the browser cache can finish before React
                // attaches `onLoad`, and that handler then never fires — which would
                // leave the card hidden behind its own placeholder for good. `complete`
                // is the browser's own answer to "has this already arrived".
                ref={(element) => {
                  if (element?.complete && element.naturalWidth > 0) {
                    markPainted(element, currentPhoto);
                  }
                }}
                src={currentPhoto ?? undefined}
              />
            </span>
            <span className="setup-hint">
              {copy("photo_of", language)
                .replace("{current}", String((photoIndex % gallery.length) + 1))
                .replace("{total}", String(gallery.length))}
            </span>
          </button>
        ) : summaryLoading ? (
          // Still arriving. The card used to render its "load them yourself" button in
          // this window — a control for work that is already running — so a card whose
          // photographs were seconds away looked exactly like one that had none.
          <div aria-busy="true" className="place-deck-photo place-deck-photo-empty">
            <span aria-hidden="true" className="skeleton skeleton-photo" />
            <p className="setup-hint">{copy("loading", language)}</p>
          </div>
        ) : entry.place_id in summaries ? (
          // Asked and answered with nothing — a great many of these places have no
          // Wikidata entry at all. Offering the fetch button again would be a control
          // that cannot work, which reads as the app being broken rather than the
          // encyclopedia being empty.
          // A place with no free photograph still gets something to look at, and for a
          // while that was a map. It is not a map any more, for two reasons the owner
          // gave: the detail panel beside the deck already draws one for the selected
          // place, so the card was the second copy; and a map is an interactive surface
          // sitting inside a swipe target. It sets `touch-action: none` and captures
          // pointers so it can be panned and pinched, which is exactly what a card being
          // swiped must not do — pinching the card fought the map underneath it.
          //
          // What replaces it says the one thing still known about the place: what kind of
          // thing it is. The glyph comes from `shared/tagIcons.tsx`, the same table the
          // setup chips read, so a category the app can name is a category this can draw.
          // No words, because the caption under the card already prints the category —
          // and nothing here takes a pointer, so the swipe is the card's alone.
          <div className="place-deck-photo place-deck-photo-empty place-deck-photo-kind">
            {(() => {
              const kind = candidates[entry.place_id]?.category;
              const Glyph = tagIcon(kind ?? "");
              return (
                <Glyph
                  aria-hidden="true"
                  className="place-deck-kind-glyph"
                  size={64}
                  strokeWidth={1.25}
                />
              );
            })()}
            {/* The glyph is decoration and says so; this sentence is the actual answer to
                "why is there no picture", and a reader who cannot see the glyph still
                needs it. A failed photograph ask answers here too — inside the card,
                where the question was asked — and it belongs to this card alone: the
                caller scopes it, so the next card never inherits the last one's
                refusal. */}
            <p className="setup-hint">
              {photoErrorOf(entry.place_id) ?? copy("photo_none_kind", language)}
            </p>
          </div>
        ) : (
          <div className="place-deck-photo place-deck-photo-empty">
            {photoErrorOf(entry.place_id) ? (
              <p className="setup-hint">{photoErrorOf(entry.place_id)}</p>
            ) : (
              <>
                <p className="setup-hint">{copy("photos_load_themselves", language)}</p>
                <button onClick={() => onWantSummary(entry.place_id)} type="button">
                  {copy("load_descriptions", language)}
                </button>
              </>
            )}
          </div>
        )}

        {/* The one path that can actually produce a picture of this place, offered
            where the absence is felt rather than in a panel further down. Investigated
            2026-08-17: for the places that come up blank the free sources genuinely hold
            nothing — Commons returns an 18th-century philosophy book for "Taro Quad
            Bikes" and a ministerial PDF for "Puri Agung Peliatan", and the name filter is
            right to refuse them. The photographs the owner has seen are on Google and
            TripAdvisor, which are licensed sources. So the honest answer is not "none
            exists" but "none is free", with the price of the one that is not.

            **One photograph is also thin.** This used to live inside the branch that
            draws a map where a picture should be, so it appeared only at zero — and a
            card carrying a single Commons shot of a car park is exactly as short of a
            picture as one carrying none, with no way to ask for a better one. The
            threshold is `PHOTO_THIN_AT`, the same "one or none" the detail panel has
            always used for `thinlyPictured`; the two disagreeing was the bug. Outside
            the photo block now, so it sits under the carousel and under the map alike. */}
        {onWantPhotos
          && paidPhotoUsd != null
          && gallery.length <= PHOTO_THIN_AT
          // Bought already, not in Google's index, or just asked and failed — the three
          // reasons for withdrawing the offer, all answered by the caller's one
          // `photoWithheld` so this control and the detail panel's cannot disagree about
          // them. Asked about the card being drawn rather than the one last reported.
          && !photoWithheld(entry.place_id) ? (
          <button
            className="place-deck-buy-photo"
            disabled={photosLoading}
            onClick={() => onWantPhotos(entry.place_id)}
            type="button"
          >
            {copyFormat("photo_buy_one", language, { cost: paidPhotoUsd.toFixed(3) })}
          </button>
        ) : null}

        <h3>
          {name}
          {altName ? <small className="place-alt-name">{altName}</small> : null}
        </h3>
        {entry.role === "protected_exploration" ? (
          <p className="setup-hint">{copy("deck_exploration_note", language)}</p>
        ) : null}

        {/* No description here. The panel beside the deck shows the same paragraph from
            the same summary, so printing it twice filled the card with text that was
            already on screen — and the card is for deciding, not for reading.
            The credit stays: the card still shows the photograph, and these are CC BY-SA.
            Attribution follows the image, not the prose it arrived with. */}
        {gallery.length ? (
          <p className="setup-hint">
            {about?.photos_are_nearby
              ? copy("photo_is_nearby", language)
              : copy("wikipedia_credit", language)}
          </p>
        ) : null}

        {/* A caption, not a table.
            The definition list gave every fact a label and a row, which reads as a
            specification sheet -- and on a card whose job is one decision, five labelled
            rows are five things to read before deciding. What is always true of a place
            now reads as one line under its name: what kind of thing it is, how long it
            wants, and what that time buys. The labels go, because "Visit estimate:
            45-90 min" and "45-90 min" carry the same information and one of them is
            shorter.

            What stays labelled is what is *not* always true. Feasibility and crowd
            signals appear only when they have something to say -- see `shared/cards.ts`
            for why three of the original five rows could not -- and an exception deserves
            a label precisely because it is an exception.

            Deliberately below the photograph rather than over it. Overlaid text is the
            more striking arrangement, but this card has five photo states -- gallery,
            loading, no-photo map, buy-a-photo, no-summary -- and a caption that sits on
            the image in one of them and under it in four is worse than one that is always
            in the same place. */}
        <p className="place-deck-caption">
          {(() => {
            const kind = candidates[entry.place_id]?.category;
            return kind ? (
              <span className="place-deck-kind">{copyFrom("CATEGORY_TEXT", kind, language)}</span>
            ) : null;
          })()}
          <span>
            {card.duration_estimate.minimum_minutes}–{card.duration_estimate.maximum_minutes}{" "}
            {copy("minutes", language)}
          </span>
          {evaluatedEffort(card.effort_state) ? (
            <span>
              {copy("effort_access", language)}{" "}
              {card.dimensions.reward_vs_effort.score}/{card.dimensions.reward_vs_effort.max}
            </span>
          ) : null}
        </p>

        {evaluatedFeasibility(card.feasibility.state) || distinguishingCons(card.cons).length ? (
          <p className="place-deck-advisories">
            {evaluatedFeasibility(card.feasibility.state) ? (
              <span>
                {copy("feasibility", language)}: {copy(card.feasibility.state, language)}
              </span>
            ) : null}
            {distinguishingCons(card.cons).length ? (
              <span>
                {copy("crowd_signal", language)}:{" "}
                {distinguishingCons(card.cons)
                  .map((code) => copyFrom("EXPLANATION_TEXT", code, language))
                  .join(" · ")}
              </span>
            ) : null}
          </p>
        ) : null}
      </div>

      {/* Four directions is more than a sentence can carry, so the legend is a diagram:
          each way you can throw the card, beside what it means. */}
      <ul className="place-deck-legend">
        <li><b aria-hidden="true">←</b> {copy("drop_to_reject", language)}</li>
        <li><b aria-hidden="true">→</b> {copy("drop_to_must_do", language)}</li>
        <li><b aria-hidden="true">↑</b> {copy("drop_to_interested", language)}</li>
        <li><b aria-hidden="true">↓</b> {copy("drop_to_skip", language)}</li>
      </ul>
      <p className="setup-hint">{copy("drag_hint", language)}</p>
      <p className="setup-hint">{copy("tap_photo_hint", language)}</p>
      {/* Colour separates keep from drop from defer. Before this the five actions
          were five identical grey buttons and the destructive one sat between two
          keeps. */}
      {/* Disabled while the card is still arriving, for the reason the card itself is
          withheld: the swipe decision is made on the photograph, so a row of live
          decision buttons above a placeholder invites answering before there is anything
          to answer about — and the answer lands on whichever place the deck settles on.
          Skip is disabled too: it is a decision about *this* card, not a way past the
          wait. Same treatment as "Search again", which is a press that cannot be undone
          cheaply. */}
      <div className="place-choice-actions place-deck-actions">
        <button
          className="choice-must_do"
          disabled={cardPending}
          onClick={() => decide("must_do")}
          type="button"
        >
          {copy("must_do", language)}
        </button>
        <button
          className="choice-interested"
          disabled={cardPending}
          onClick={() => decide("interested")}
          type="button"
        >
          {copy("interested", language)}
        </button>
        <button
          className="choice-maybe"
          disabled={cardPending}
          onClick={() => decide("maybe")}
          type="button"
        >
          {copy("maybe", language)}
        </button>
        <button
          className="choice-not_for_trip"
          disabled={cardPending}
          onClick={() => decide("not_for_trip", null)}
          type="button"
        >
          {copy("not_for_trip", language)}
        </button>
        <button
          className="choice-skip"
          disabled={cardPending}
          onClick={() => act("skip")}
          type="button"
        >
          {copy("deck_skip", language)}
        </button>
      </div>
    </section>
  );
}
