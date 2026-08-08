import { copy, type Language } from "../i18n/copy";
import type { MapPlace } from "../shared/map";
import { plotCoordinates } from "./ItineraryPage";

/**
 * Where places are, drawn once and used twice.
 *
 * The card needs to answer "where is *this* one", and the shortlist needs "where are
 * they all" — the same question at two scales, so the same projection answers both and
 * the two pictures cannot disagree about the same coordinates.
 *
 * A lone pin on an empty box says nothing, so a single place is still drawn against the
 * rest of the shortlist, dimmed. That is what gives it somewhere to be.
 *
 * No tiles and no network, per `WF-034`: the numbered list under the map repeats every
 * pin, so the drawing is never the only carrier.
 */

export interface PlaceMapProps {
  places: MapPlace[];
  language: Language;
  title: string;
  /** Drawn large and filled; everything else is context. Omit to weight them equally. */
  focusId?: string;
  /** The numbered list under the map. Off in the card, where one name is enough. */
  withKey?: boolean;
}

export function PlaceMap({ places, language, title, focusId, withKey = true }: PlaceMapProps) {
  if (!places.length) return null;
  const points = plotCoordinates(places);
  const focused = points.find((point) => point.place_id === focusId);

  return (
    // derives-from: A1 numbered map; no tiles or network, and the list repeats every pin.
    <section className="places-map">
      <h4>{title}</h4>
      <svg aria-label={title} role="img" viewBox="0 0 420 120">
        {points.map((point) => {
          const isFocus = point.place_id === focusId;
          return (
            <g
              className={`plan-map-point${isFocus ? " current" : ""}${focusId && !isFocus ? " context" : ""}`}
              key={point.place_id}
            >
              <circle cx={point.x} cy={point.y} r={isFocus ? 10 : 8} />
              <text textAnchor="middle" x={point.x} y={point.y + 3}>{point.label}</text>
            </g>
          );
        })}
      </svg>
      {focused ? <p className="places-map-focus">{focused.label} · {focused.name}</p> : null}
      {withKey ? (
        <ol className="places-map-key">
          {points.map((point) => (
            <li className={point.place_id === focusId ? "current" : undefined} key={point.place_id}>
              <b>{point.label}</b> {point.name}
            </li>
          ))}
        </ol>
      ) : null}
      {points.length < places.length ? (
        <p className="setup-hint">{copy("map_no_coordinates", language)}</p>
      ) : null}
    </section>
  );
}
