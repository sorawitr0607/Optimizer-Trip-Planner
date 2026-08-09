import { useRef, useState } from "react";

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
/** Far enough in to read a single street's worth of dots, far enough out to see the
 *  whole catalogue. Bounded both ways so the view can always be recovered by dragging. */
const MIN_ZOOM = 1;
const MAX_ZOOM = 8;

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
  // Zoom and pan, because at city scale several hundred dots and a dozen pins overlap
  // and no amount of styling separates them — the answer to "where is it" is sometimes
  // "closer". Held as a viewBox rather than a CSS transform so stroke widths and pin
  // radii stay put: zooming a transform would fatten every dot as it magnified.
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 });
  // The ref carries the grab origin; the boolean is what the class reads, because a ref
  // read during render cannot re-render and React rightly refuses it.
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
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
      <svg
        aria-label={title}
        className={`places-map-svg${dragging ? " dragging" : ""}`}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = { x: event.clientX, y: event.clientY, ox: view.x, oy: view.y };
          setDragging(true);
        }}
        onPointerMove={(event) => {
          const held = drag.current;
          if (!held) return;
          const box = event.currentTarget.getBoundingClientRect();
          // Pixels to viewBox units, so a drag moves the map exactly as far as the hand.
          const scale = FRAME.width / view.zoom / box.width;
          setView((current) => ({
            ...current,
            x: held.ox - (event.clientX - held.x) * scale,
            y: held.oy - (event.clientY - held.y) * scale,
          }));
        }}
        onPointerUp={() => { drag.current = null; setDragging(false); }}
        onPointerCancel={() => { drag.current = null; setDragging(false); }}
        onWheel={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          const factor = event.deltaY < 0 ? 1.2 : 1 / 1.2;
          setView((current) => {
            const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current.zoom * factor));
            if (zoom === current.zoom) return current;
            // Keep the point under the cursor under the cursor.
            const px = (event.clientX - box.left) / box.width;
            const py = (event.clientY - box.top) / box.height;
            const beforeW = FRAME.width / current.zoom;
            const beforeH = FRAME.height / current.zoom;
            const afterW = FRAME.width / zoom;
            const afterH = FRAME.height / zoom;
            return {
              zoom,
              x: current.x + (beforeW - afterW) * px,
              y: current.y + (beforeH - afterH) * py,
            };
          });
        }}
        role="img"
        viewBox={`${view.x} ${view.y} ${FRAME.width / view.zoom} ${FRAME.height / view.zoom}`}
      >
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
      </svg>
      {/* Outside the svg, so panning does not carry the compass off the edge. */}
      <span aria-hidden="true" className="places-map-rose">N ↑</span>
      {view.zoom > 1 ? (
        <button className="places-map-reset" onClick={() => setView({ x: 0, y: 0, zoom: 1 })} type="button">
          {copy("map_reset", language)}
        </button>
      ) : null}
      <p className="places-map-scale">
        {across > 0
          ? copyFormat("map_span", language, { km: Math.max(1, Math.round(across / view.zoom)) })
          : null}
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
