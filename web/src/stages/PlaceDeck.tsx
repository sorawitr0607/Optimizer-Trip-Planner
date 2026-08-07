import { useState } from "react";

import type { CandidateChoice, PlaceSummary, Ranking } from "../api/client";
import { copy, copyFrom, type Language } from "../i18n/copy";

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
 */

/** How far a horizontal drag must travel to count, in pixels. Below this it is a tap. */
const SWIPE_THRESHOLD = 64;

export interface PlaceDeckProps {
  ranking: Ranking;
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
  const [dragFrom, setDragFrom] = useState<number | null>(null);

  const decided = new Set(choices.map((choice) => choice.place_id));
  // The queue already excludes decided places, but a decision made in this session
  // has not been refetched yet, so filter again rather than show a stale card.
  const queue = ranking.lanes.main_queue.filter((entry) => !decided.has(entry.place_id));
  const entry = queue[Math.min(cursor, Math.max(0, queue.length - 1))];
  const card = entry ? ranking.cards[entry.place_id] : undefined;

  if (!entry || !card) {
    return <p className="setup-hint">{copy("deck_exhausted", language)}</p>;
  }

  const about = summaries[entry.place_id];
  const gallery = about?.image_urls?.length
    ? about.image_urls
    : about?.image_url
      ? [about.image_url]
      : [];
  const name = nameOf(entry.place_id);
  const altName = altNameOf(entry.place_id);

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

  return (
    // derives-from: element 14 .stat-card as .place-deck
    <section
      aria-label={copy("deck_mode", language)}
      className="place-deck"
      onKeyDown={(event) => {
        if (event.key === "ArrowRight") advance(1);
        if (event.key === "ArrowLeft") advance(-1);
      }}
      onPointerDown={(event) => setDragFrom(event.clientX)}
      onPointerUp={(event) => {
        if (dragFrom === null) return;
        const travelled = event.clientX - dragFrom;
        setDragFrom(null);
        if (Math.abs(travelled) < SWIPE_THRESHOLD) return;
        // Right means keep, left means not for this trip — the same directions the
        // buttons below are ordered in, so the gesture is learnable from the layout.
        if (travelled > 0) decide("interested");
        else decide("not_for_trip", null);
      }}
      tabIndex={0}
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

      {gallery.length ? (
        // A tap advances the gallery, which is what the owner asked for. It is a
        // button so that a keyboard reaches it and a screen reader announces it.
        <button
          className="place-deck-photo"
          onClick={() => setPhoto((current) => (current + 1) % gallery.length)}
          type="button"
        >
          <img alt={name} loading="lazy" src={gallery[photo % gallery.length]} />
          <span className="setup-hint">
            {copy("photo_of", language)
              .replace("{current}", String((photo % gallery.length) + 1))
              .replace("{total}", String(gallery.length))}
          </span>
        </button>
      ) : (
        <div className="place-deck-photo place-deck-photo-empty">
          <p className="setup-hint">{copy("descriptions_are_free", language)}</p>
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
        <dd>{copyFrom("DIMENSION_TEXT", "reward_vs_effort", language)}: {card.dimensions.reward_vs_effort.score}/{card.dimensions.reward_vs_effort.max}</dd>
        <dt>{copy("crowd_signal", language)}</dt>
        <dd>
          {card.cons.length
            ? card.cons.map((code) => copyFrom("EXPLANATION_TEXT", code, language)).join(" · ")
            : copy("none", language)}
        </dd>
        <dt>{copy("cost_reservation", language)}</dt>
        <dd>{copy("no_licensed_rating", language)}</dd>
      </dl>

      <p className="setup-hint">{copy("swipe_hint", language)}</p>
      <div className="place-choice-actions">
        <button onClick={() => decide("must_do")} type="button">
          {copy("must_do", language)}
        </button>
        <button onClick={() => decide("interested")} type="button">
          {copy("interested", language)}
        </button>
        <button onClick={() => decide("maybe")} type="button">
          {copy("maybe", language)}
        </button>
        <button onClick={() => decide("not_for_trip", null)} type="button">
          {copy("not_for_trip", language)}
        </button>
        <button onClick={() => advance(1)} type="button">
          {copy("deck_skip", language)}
        </button>
      </div>
    </section>
  );
}
