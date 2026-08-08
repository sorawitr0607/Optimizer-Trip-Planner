import type { DiscoveryCandidate } from "../api/client";
import { copy, copyFormat, type Language } from "../i18n/copy";
import type { MapPlace } from "../shared/map";
import { plotCoordinates } from "./ItineraryPage";

/**
 * Where places are, drawn once and used twice.
 *
 * The card answers "where is *this* one", the shortlist pane "where are they all" — the
 * same question at two scales, so one projection answers both and two pictures of the
 * same coordinates cannot disagree.
 *
 * **The city is drawn from the catalogue, which is why this stopped being a blank box.**
 * Six pins on empty grey told an owner nothing: no coastline, no districts, no sense of
 * which end of town anything was. Every discovered candidate already carries
 * coordinates and is already in memory — several hundred of them — so plotting the lot
 * as faint dots draws the city's actual footprint for free, with no tiles, no network
 * and no new request. Density does the work a basemap would: parks thin out, old
 * quarters clot, the river shows as an absence.
 *
 * `WF-034` forbids a tile map and this does not become one. The numbered list under the
 * map still repeats every pin, so the drawing is never the only carrier.
 */

/** Taller than the itinerary's strip: this draws a whole city, and a square town in a
 *  wide band piles every pin into the middle. */
const FRAME = { width: 420, height: 260 } as const;

/** Bounding span of a set of points, in kilometres, for the scale note. */
function spanKm(points: { latitude: number; longitude: number }[]): number {
  if (points.length < 2) return 0;
  const lats = points.map((p) => p.latitude);
  const lons = points.map((p) => p.longitude);
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
  const north = (Math.max(...lats) - Math.min(...lats)) * 111;
  const east = (Math.max(...lons) - Math.min(...lons)) * 111 * Math.cos((midLat * Math.PI) / 180);
  return Math.max(north, east);
}

export interface PlaceMapProps {
  places: MapPlace[];
  language: Language;
  title: string;
  /** The whole discovered catalogue, drawn faintly so the city has a shape. */
  context?: DiscoveryCandidate[];
  /** Drawn large and filled; everything else is context. Omit to weight them equally. */
  focusId?: string;
  /** The numbered list under the map. Off in the card, where one name is enough. */
  withKey?: boolean;
}

export function PlaceMap({
  places,
  language,
  title,
  context = [],
  focusId,
  withKey = true,
}: PlaceMapProps) {
  if (!places.length) return null;

  // One projection over pins *and* city, so both sit in the same frame. Projecting them
  // separately would scale each to its own bounds and put the pins somewhere the city
  // is not.
  const city = context
    .filter((item) => item.latitude !== null && item.longitude !== null)
    .map((item) => ({
      kind: "city" as const,
      place_id: item.place_id,
      latitude: item.latitude as number,
      longitude: item.longitude as number,
    }));
  const pins = places.map((place) => ({ ...place, kind: "pin" as const }));
  const projected = plotCoordinates([...city, ...pins], FRAME);
  const cityPoints = projected.filter((point) => point.kind === "city");
  const pinPoints = projected.filter((point) => point.kind === "pin");
  const focused = pinPoints.find((point) => point.place_id === focusId);
  const across = Math.round(spanKm(city.length ? city : places));

  return (
    // derives-from: A1 numbered map; no tiles or network, and the list repeats every pin.
    <section className="places-map">
      <h4>{title}</h4>
      <svg aria-label={title} role="img" viewBox={`0 0 ${FRAME.width} ${FRAME.height}`}>
        {cityPoints.map((point) => (
          <circle className="places-map-city" cx={point.x} cy={point.y} key={point.place_id} r="1.4" />
        ))}
        {pinPoints.map((point) => {
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
        {/* North and a scale, so the drawing can be read rather than only looked at. */}
        <g className="places-map-rose">
          <text textAnchor="middle" x="404" y="18">N</text>
          <path d="M404 22 L400 32 L404 29 L408 32 Z" />
        </g>
      </svg>
      <p className="places-map-scale">
        {across > 0 ? copyFormat("map_span", language, { km: across }) : null}
        {focused ? ` · ${focused.label} · ${focused.name}` : null}
      </p>
      {withKey ? (
        <ol className="places-map-key">
          {pinPoints.map((point) => (
            <li className={point.place_id === focusId ? "current" : undefined} key={point.place_id}>
              <b>{point.label}</b> {point.name}
            </li>
          ))}
        </ol>
      ) : null}
      {pinPoints.length < places.length ? (
        <p className="setup-hint">{copy("map_no_coordinates", language)}</p>
      ) : null}
    </section>
  );
}
