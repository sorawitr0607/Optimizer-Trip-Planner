import { useEffect, useRef, useState } from "react";

import type { CandidateChoice, DiscoveryCandidate, PlaceSummary, Ranking } from "../api/client";
import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";
import { flyToShortlist } from "../shared/flyToShortlist";
import { galleryFor } from "../shared/photos";
import { PlaceMap } from "./PlaceMap";

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
  choices,
  language,
  nameOf,
  altNameOf,
  onDecide,
  onPendingChange,
  onWantSummary,
  summaryLoading = false,
  laneRemaining = 0,
  onShowMore,
  onPickLane,
  lanes = [],
  lane,
  onCardChange,
}: PlaceDeckProps) {
  const [cursor, setCursor] = useState(0);
  const [photo, setPhoto] = useState(0);
  const [photoLoaded, setPhotoLoaded] = useState<string | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [leaving, setLeaving] = useState<Intent>(null);
  // A drag that ends over the photo used to advance the gallery as well as decide.
  const travelled = useRef(0);
  /** The card being decided, so the flight can be cut from its photograph. */
  const cardRef = useRef<HTMLDivElement | null>(null);

  const decided = new Set(choices.map((choice) => choice.place_id));
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
  // filtering here is what makes any lane dealable.
  const queue = entries.filter(
    (entry) =>
      !decided.has(entry.place_id) && !decidedNames.has(nameKey(nameOf(entry.place_id))),
  );
  const entry = queue[Math.min(cursor, Math.max(0, queue.length - 1))];
  const card = entry ? ranking.cards[entry.place_id] : undefined;

  const about = entry ? summaries[entry.place_id] : undefined;
  // Encyclopedia photographs plus OpenStreetMap's own tag, which costs no extra request
  // and is often the only picture a place without an article has.
  const gallery = galleryFor(about, entry ? candidates[entry.place_id] : undefined);

  // Wikimedia serves every one of these through a `Special:FilePath` redirect, so the
  // first byte costs two round trips. Warming the next photo and the next card's
  // first photo while this one is being read is the whole fix for "images load very
  // slowly": by the time the card turns over, the bytes are in the browser cache.
  const nextEntry = queue[Math.min(cursor + 1, queue.length - 1)];
  const nextUrl = nextEntry ? summaries[nextEntry.place_id]?.image_url : null;
  const upcoming = gallery.length ? gallery[(photo + 1) % gallery.length] : null;
  // Which photo is on screen, and which one has finished arriving. Held as the URL
  // rather than a boolean so that tapping through a gallery shows the placeholder again
  // for each new picture, and a cached one never flashes it at all.
  const currentPhoto = gallery.length ? gallery[photo % gallery.length] : null;
  // The card is *withheld* until its first picture has painted, not merely the picture
  // box. A card that arrives complete-but-imageless and fills in a second later is the
  // one thing the owner cannot un-see: the swipe decision is made on the photograph, so
  // showing the text first invites a decision on half the evidence. Only the first
  // photo gates the card — tapping through the gallery must not blank it again.
  const cardPending = summaryLoading || (Boolean(currentPhoto) && photoLoaded !== currentPhoto && photo === 0);
  // Report the card in front, so the panel beside the deck tracks it.
  const currentId = entry?.place_id;
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

  // Advance the loading line while a card is arriving, and only then: a timer left
  // running behind a loaded deck is a re-render a second for nothing.
  const [loadingStep, setLoadingStep] = useState(0);
  useEffect(() => {
    if (!cardPending) return;
    const timer = window.setInterval(
      () => setLoadingStep((current) => current + 1),
      LOADING_LINE_MS,
    );
    return () => window.clearInterval(timer);
  }, [cardPending]);

  useEffect(() => {
    for (const url of [upcoming, nextUrl]) {
      if (!url) continue;
      const image = new Image();
      image.decoding = "async";
      image.src = url;
    }
  }, [upcoming, nextUrl]);

  if (!entry || !card) {
    const rejectedChoices = choices.filter((c) => c.action === "not_for_trip");
    const shortlistedChoices = choices.filter((c) => c.action === "interested" || c.action === "must_do");
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
                  const about = summaries[c.place_id];
                  const photo = galleryFor(about, candidates[c.place_id])[0] ?? null;
                  const prose = about?.text?.[language] ?? about?.text?.en
                    ?? about?.description?.[language] ?? about?.description?.en ?? "";
                  return (
                    <li className="deck-reconsider-row" key={c.place_id}>
                      <details className="deck-reconsider-detail">
                        <summary className="deck-reconsider-name">{nameOf(c.place_id)}</summary>
                        <div className="deck-reconsider-about">
                          {photo ? (
                            <img alt={nameOf(c.place_id)} decoding="async" loading="lazy" src={photo} />
                          ) : null}
                          <p>{prose || copy("no_description_yet", language)}</p>
                        </div>
                      </details>
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

  function advance(step: number) {
    setPhoto(0);
    setCursor((current) => Math.min(Math.max(0, current + step), queue.length - 1));
  }

  /** Commit whatever the gesture, an arrow key or a button asked for. */
  function act(action: Intent) {
    if (action === "skip") advance(1);
    else if (action === "must_do") decide("must_do");
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
  const style = {
    transform: `translate(${offsetX}px, ${offsetY}px) rotate(${offsetX / 26}deg)`,
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
        className={`place-deck-drag${drag ? " dragging" : ""}${cardPending ? " pending" : ""}`}
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
            {copy("deck_position", language)
              .replace("{current}", String(Math.min(cursor + 1, queue.length)))
              .replace("{total}", String(queue.length))}
          </p>
          <strong className="place-score">
            {card.total_score.toFixed(1)}
            <small>/100</small>
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
              {photoLoaded === currentPhoto ? null : (
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
                onError={() => setPhotoLoaded(currentPhoto)}
                onLoad={() => setPhotoLoaded(currentPhoto)}
                // A photograph already in the browser cache can finish before React
                // attaches `onLoad`, and that handler then never fires — which would
                // leave the card hidden behind its own placeholder for good. `complete`
                // is the browser's own answer to "has this already arrived".
                ref={(element) => {
                  if (element?.complete && element.naturalWidth > 0) {
                    setPhotoLoaded(currentPhoto);
                  }
                }}
                src={currentPhoto ?? undefined}
              />
            </span>
            <span className="setup-hint">
              {copy("photo_of", language)
                .replace("{current}", String((photo % gallery.length) + 1))
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
          // A place with no free photograph anywhere still gets something to look at:
          // where it is. Measured on the owner's Sapporo catalogue, six places had a QID,
          // no image property, no OpenStreetMap tag and nothing that passed the Commons
          // name filter — two of them stone monuments whose names are two characters,
          // which the name filter refuses by design. There is no picture to find for
          // those, and inventing one is fabrication, so this shows the map instead and
          // says that is what it is. A swipe decision made on a location is a worse
          // decision than one made on a photograph, and a much better one than a
          // decision made on a grey box.
          <div className="place-deck-photo place-deck-photo-empty">
            {(() => {
              // No coordinates is the one case with nothing to draw either. Discovery
              // refuses a candidate without them, so this is defence rather than a
              // branch the catalogue reaches.
              const spot = candidates[entry.place_id];
              if (spot?.latitude == null || spot.longitude == null) {
                return <p className="setup-hint">{copy("no_description_yet", language)}</p>;
              }
              return (
                <PlaceMap
                  focusId={entry.place_id}
                  headingLevel={4}
                  language={language}
                  places={[
                    {
                      place_id: entry.place_id,
                      name,
                      label: name,
                      latitude: spot.latitude,
                      longitude: spot.longitude,
                    },
                  ]}
                  title={copy("photo_none_map", language)}
                  withKey={false}
                />
              );
            })()}
          </div>
        ) : (
          <div className="place-deck-photo place-deck-photo-empty">
            <p className="setup-hint">{copy("descriptions_are_free", language)}</p>
            <p className="setup-hint">{copy("photos_load_themselves", language)}</p>
            <button onClick={() => onWantSummary(entry.place_id)} type="button">
              {copy("load_descriptions", language)}
            </button>
          </div>
        )}

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

        {/* `WF-005`'s minimum card content, one labelled topic per line so each is
            readable on its own rather than run together in a sentence. */}
        <dl className="place-deck-topics">
          <dt>{copy("duration", language)}</dt>
          <dd>
            {card.duration_estimate.minimum_minutes}–{card.duration_estimate.maximum_minutes}{" "}
            {copy("minutes", language)}
          </dd>
          <dt>{copy("feasibility", language)}</dt>
          <dd>{copy(card.feasibility.state, language)}</dd>
          <dt>{copy("effort_access", language)}</dt>
          <dd>
            {copyFrom("DIMENSION_TEXT", "reward_vs_effort", language)}:{" "}
            {card.dimensions.reward_vs_effort.score}/{card.dimensions.reward_vs_effort.max}
          </dd>
          <dt>{copy("crowd_signal", language)}</dt>
          <dd>
            {card.cons.length
              ? card.cons.map((code) => copyFrom("EXPLANATION_TEXT", code, language)).join(" · ")
              : copy("none", language)}
          </dd>
          <dt>{copy("cost_reservation", language)}</dt>
          <dd>{copy("no_licensed_rating", language)}</dd>
        </dl>
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
      <div className="place-choice-actions place-deck-actions">
        <button className="choice-must_do" onClick={() => decide("must_do")} type="button">
          {copy("must_do", language)}
        </button>
        <button className="choice-interested" onClick={() => decide("interested")} type="button">
          {copy("interested", language)}
        </button>
        <button className="choice-maybe" onClick={() => decide("maybe")} type="button">
          {copy("maybe", language)}
        </button>
        <button
          className="choice-not_for_trip"
          onClick={() => decide("not_for_trip", null)}
          type="button"
        >
          {copy("not_for_trip", language)}
        </button>
        <button className="choice-skip" onClick={() => advance(1)} type="button">
          {copy("deck_skip", language)}
        </button>
      </div>
    </section>
  );
}
