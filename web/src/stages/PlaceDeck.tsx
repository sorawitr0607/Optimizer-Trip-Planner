import { useEffect, useRef, useState } from "react";

import type { CandidateChoice, DiscoveryCandidate, PlaceSummary, Ranking } from "../api/client";
import { copy, copyFrom, type Language } from "../i18n/copy";
import { galleryFor } from "../shared/photos";

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

type Intent = "interested" | "not_for_trip" | "skip" | "maybe" | null;

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
    // Up is `maybe`: a real decision, unlike skip, and the two are opposite gestures
    // because they are the two ways of not answering yet.
    if (drag.y < -reach) return "maybe";
    return null;
  }
  if (drag.x > reach) return "interested";
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
  /** Fetches the free description and photographs for one place. */
  onWantSummary: (placeId: string) => void;
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
  onWantSummary,
}: PlaceDeckProps) {
  const [cursor, setCursor] = useState(0);
  const [photo, setPhoto] = useState(0);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [leaving, setLeaving] = useState<Intent>(null);
  // A drag that ends over the photo used to advance the gallery as well as decide.
  const travelled = useRef(0);

  const decided = new Set(choices.map((choice) => choice.place_id));
  // `main_queue` already excludes decided places, but a decision made in this session
  // has not been refetched yet — and the other lanes do not exclude them at all — so
  // filtering here is what makes any lane dealable.
  const queue = entries.filter((entry) => !decided.has(entry.place_id));
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
  useEffect(() => {
    for (const url of [upcoming, nextUrl]) {
      if (!url) continue;
      const image = new Image();
      image.decoding = "async";
      image.src = url;
    }
  }, [upcoming, nextUrl]);

  if (!entry || !card) {
    return <p className="setup-hint">{copy("deck_exhausted", language)}</p>;
  }

  const name = nameOf(entry.place_id);
  const altName = altNameOf(entry.place_id);
  const intent = leaving ?? intentOf(drag);

  function decide(action: string, reason: string | null = null) {
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
        if (event.key === "ArrowRight") act("interested");
        else if (event.key === "ArrowLeft") act("not_for_trip");
        else if (event.key === "ArrowDown") act("skip");
        else if (event.key === "ArrowUp") act("maybe");
        else return;
        event.preventDefault();
      }}
      style={style}
      tabIndex={0}
    >
      {/* The drag surface stops above the action row, so pressing a button never
          starts a gesture and a gesture never ends in a click. */}
      <div
        className={`place-deck-drag${drag ? " dragging" : ""}`}
        onPointerCancel={() => setDrag(null)}
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
              intent === "interested"
                ? "drop_to_keep"
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
            <img
              alt={name}
              // Eager and high priority: this image is the card, always above the
              // fold, and `loading="lazy"` was actively delaying the one photo the
              // owner is waiting on.
              decoding="async"
              draggable={false}
              fetchPriority="high"
              loading="eager"
              src={gallery[photo % gallery.length]}
            />
            <span className="setup-hint">
              {copy("photo_of", language)
                .replace("{current}", String((photo % gallery.length) + 1))
                .replace("{total}", String(gallery.length))}
            </span>
          </button>
        ) : entry.place_id in summaries ? (
          // Asked and answered with nothing — a great many of these places have no
          // Wikidata entry at all. Offering the fetch button again would be a control
          // that cannot work, which reads as the app being broken rather than the
          // encyclopedia being empty.
          <div className="place-deck-photo place-deck-photo-empty">
            <p className="setup-hint">{copy("no_description_yet", language)}</p>
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

        {about?.text?.[language] || about?.text?.en ? (
          <>
            <p>{about.text[language] ?? about.text.en}</p>
            <p className="setup-hint">{copy("wikipedia_credit", language)}</p>
          </>
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
        <li><b aria-hidden="true">→</b> {copy("drop_to_keep", language)}</li>
        <li><b aria-hidden="true">↑</b> {copy("drop_to_maybe", language)}</li>
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
