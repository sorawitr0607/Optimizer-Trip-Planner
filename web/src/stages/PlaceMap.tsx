import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { rpc, type Basemap, type Buildings, type DiscoveryCandidate } from "../api/client";
import { copy, copyFormat, type Language } from "../i18n/copy";
import type { MapPlace } from "../shared/map";
import { projectionOf } from "./ItineraryPage";

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
/** Far enough in to read a single street, far enough out to see the whole catalogue.
 *  Bounded both ways so the view can always be recovered by dragging. 8x was not enough:
 *  Taipei's catalogue spans about 0.56 degrees, so even at the old ceiling the window was
 *  still 0.07 degrees wide and the buildings request was refused as too wide at every
 *  zoom the map could reach. */
const MIN_ZOOM = 1;
const MAX_ZOOM = 24;
/** Ask for buildings once the window on screen is this small, in degrees. Measured
 *  against the *window*, not against the zoom factor: zoom is a ratio of the catalogue's
 *  own span, so the same factor is a different real distance in every city, and a
 *  building-scale view of Taipei is a regional view of somewhere compact. Matches
 *  `OpenStreetMapProvider.buildings_max_span`, which refuses anything wider. */
const BUILDINGS_MAX_SPAN = 0.06;
/** How long the view must hold still before its buildings are worth fetching. Long
 *  enough that swiping through the deck costs nothing — a card glanced at and thrown
 *  never asks — and short enough to feel immediate on the one being read. */
const SETTLE_MS = 900;
/** How much ground a focused map opens on, in kilometres across. A neighbourhood: near
 *  enough that streets and footprints are legible and the place can be recognised, wide
 *  enough to see what it sits next to. */
const FOCUS_KM = 1.6;
/**
 * Snapping the window onto a shared grid was tried, so that neighbouring places would
 * ask for one window and the second would be a cache hit. **It made the map worse and
 * was reverted.** `buildings_limit` is a budget, and snapping spent it on ground that is
 * not on screen: measured in central Taipei, the snapped 4.4 km tile holds **15253**
 * buildings so the 1200 returned were 8% of it, against **3546** in the 2.2 km window
 * actually being looked at. A scattered half of a neighbourhood reads as a city; a
 * twelfth of a district reads as a rash. The request rate is held down by `SETTLE_MS`
 * instead, which costs coverage nothing.
 */

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
  /** Streets, water and parks. Without it this is dots on grey; with it the city is
   *  recognisable and a pin has somewhere to be. */
  basemap?: Basemap | null;
  /** Drawn large and filled; everything else is context. Omit to weight them equally. */
  focusId?: string;
  /** The numbered list under the map. Off in the card, where one name is enough. */
  withKey?: boolean;
  /** Enables the zoomed-in buildings fetch. Omit on a map nobody zooms. */
  tripId?: string;
}

export function PlaceMap({
  places,
  language,
  title,
  context = [],
  basemap = null,
  focusId,
  withKey = true,
  tripId,
}: PlaceMapProps) {
  // Zoom and pan, because at city scale several hundred dots and a dozen pins overlap
  // and no amount of styling separates them — the answer to "where is it" is sometimes
  // "closer". Held as a viewBox rather than a CSS transform so stroke widths and pin
  // radii stay put: zooming a transform would fatten every dot as it magnified.
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 });
  const svgRef = useRef<SVGSVGElement | null>(null);
  // The ref carries the grab origin; the boolean is what the class reads, because a ref
  // read during render cannot re-render and React rightly refuses it.
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const [footprints, setFootprints] = useState<[number, number][][]>([]);
  // Which window has already been asked for, so panning inside it costs nothing.
  const asked = useRef<string>("");

  // One projection over pins *and* city, so both sit in the same frame. Projecting them
  // separately would scale each to its own bounds and put the pins somewhere the city
  // is not. Memoized because dragging and zooming change only the viewBox: without this
  // every pointer move reprojected the whole city and every building corner with it.
  const geometry = useMemo(() => {
    const city = context
      .filter((item) => item.latitude !== null && item.longitude !== null)
      .map((item) => ({
        kind: "city" as const,
        place_id: item.place_id,
        latitude: item.latitude as number,
        longitude: item.longitude as number,
      }));
    const pins = places.map((place) => ({ ...place, kind: "pin" as const }));
    // Basemap vertices go through the *same* projection as the pins, in one pass. A
    // second projection would fit the streets to their own bounds and lay the city
    // somewhere the pins are not — the two have to be scaled by one transform or they
    // describe different places.
    const lines: { layer: string; from: number; count: number }[] = [];
    const vertices: { latitude: number; longitude: number }[] = [];
    for (const layer of ["water", "green", "roads"] as const) {
      for (const line of basemap?.[layer] ?? []) {
        lines.push({ layer, from: vertices.length, count: line.length });
        for (const [latitude, longitude] of line) vertices.push({ latitude, longitude });
      }
    }
    // The projection is fitted to the city, the streets and the pins — and deliberately
    // *not* to the footprints. Footprints cover only the window currently on screen, so
    // including them would move the bounds every time a new window loaded and the whole
    // map would jump under the hand that zoomed it. They are projected through the
    // transform instead of helping define it.
    const projection = projectionOf([...vertices, ...city, ...pins], FRAME);
    const linePoints = projection
      ? vertices.map((vertex) => projection.toXY(vertex.latitude, vertex.longitude))
      : [];
    const buildingRings = projection
      ? footprints.map((ring) =>
          ring
            .map(([latitude, longitude]) => {
              const point = projection.toXY(latitude, longitude);
              return `${point.x.toFixed(1)},${point.y.toFixed(1)}`;
            })
            .join(" "),
        )
      : [];
    // One kilometre, measured through this projection, so a view can be sized in real
    // distance instead of in whatever the catalogue happened to span.
    const anchor = pins[0] ?? city[0];
    let unitsPerKm = 0;
    if (projection && anchor) {
      const here = projection.toXY(anchor.latitude, anchor.longitude);
      const north = projection.toXY(anchor.latitude + 1 / 111, anchor.longitude);
      unitsPerKm = Math.hypot(north.x - here.x, north.y - here.y);
    }
    return {
      projection,
      unitsPerKm,
      lines,
      linePoints,
      buildingRings,
      cityPoints: projection ? city.map((item) => ({ ...item, ...projection.toXY(item.latitude, item.longitude) })) : [],
      pinPoints: projection ? pins.map((pin) => ({ ...pin, ...projection.toXY(pin.latitude, pin.longitude) })) : [],
      across: Math.round(spanKm(city.length ? city : places)),
    };
  }, [basemap, context, places, footprints]);
  const { lines, linePoints, buildingRings, cityPoints, pinPoints, across } = geometry;
  const focused = pinPoints.find((point) => point.place_id === focusId);

  // The view the map opens on, and the one Reset returns to.
  //
  // Fitting the projection meant every map opened on the whole region — so the card's
  // "where is this one" was a picture of all of Taipei with one pin somewhere in it,
  // which is the complaint this screen kept getting. A map with a focus now opens at
  // street scale **on its subject**; one without fits the pins it was given. As a
  // consequence the card map's window is small enough to be worth footprints, so the
  // detail arrives without anyone having to know to zoom.
  const home = useMemo(() => {
    const { projection, unitsPerKm } = geometry;
    if (!projection || !pinPoints.length || !unitsPerKm) return { x: 0, y: 0, zoom: 1 };
    const subject = focusId ? pinPoints.filter((point) => point.place_id === focusId) : [];
    const points = subject.length ? subject : pinPoints;
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    // A single pin has no extent of its own, so it is given a neighbourhood rather than
    // an infinite zoom.
    const least = FOCUS_KM * unitsPerKm;
    const width = Math.max(maxX - minX, least);
    const height = Math.max(maxY - minY, (least * FRAME.height) / FRAME.width);
    const zoom = Math.min(
      MAX_ZOOM,
      Math.max(MIN_ZOOM, Math.min(FRAME.width / (width * 1.3), FRAME.height / (height * 1.3))),
    );
    return {
      zoom,
      x: (minX + maxX) / 2 - FRAME.width / zoom / 2,
      y: (minY + maxY) / 2 - FRAME.height / zoom / 2,
    };
  }, [geometry, focusId, pinPoints]);

  // Adjusted during render rather than in an effect — React's own pattern for resetting
  // state when a prop changes, and it avoids the extra committed frame at the old view
  // that an effect would paint. Compared as a *value*, not by object identity:
  // `geometry` is rebuilt when footprints arrive, and reacting to that would snap the
  // map home and undo the very pan that asked for them.
  const homeKey = `${home.x.toFixed(1)},${home.y.toFixed(1)},${home.zoom.toFixed(3)}`;
  // Starts as `null`, not as the first `homeKey`: seeded with the key, a map whose
  // geometry was already cached on its first render counted as settled and kept the
  // initial view instead of its own. That is exactly what happened to the shortlist
  // map, which sat at the whole-projection zoom while the card map — whose data arrives
  // a beat later — fitted correctly.
  const [settledHome, setSettledHome] = useState<string | null>(null);
  if (settledHome !== homeKey) {
    setSettledHome(homeKey);
    setView(home);
  }

  // Buildings, only once the map is close enough for them to be bigger than a pixel,
  // and only for the window actually on screen. The inverse of the same projection is
  // what makes "the window actually on screen" expressible as latitude and longitude.
  const inverse = geometry.projection;
  const visible = (() => {
    if (!inverse) return null;
    const a = inverse.toLatLon(view.x, view.y);
    const b = inverse.toLatLon(view.x + FRAME.width / view.zoom, view.y + FRAME.height / view.zoom);
    const box = [
      Math.min(a.latitude, b.latitude), Math.min(a.longitude, b.longitude),
      Math.max(a.latitude, b.latitude), Math.max(a.longitude, b.longitude),
    ].map((value) => Number(value.toFixed(3)));
    // Wider than this and footprints are sub-pixel anyway, so the provider refuses and
    // there is nothing to gain by asking.
    return Math.max(box[2] - box[0], box[3] - box[1]) <= BUILDINGS_MAX_SPAN ? box : null;
  })();
  const windowKey = visible ? visible.join(",") : "";

  // Wheel is bound by hand rather than through `onWheel`, because React registers its
  // own wheel listener **passively** — `preventDefault` inside a JSX handler is ignored,
  // so zooming the map scrolled the page out from under it at the same time.
  useEffect(() => {
    const node = svgRef.current;
    if (!node) return;
    function zoomBy(event: WheelEvent) {
      event.preventDefault();
      const box = node!.getBoundingClientRect();
      const factor = event.deltaY < 0 ? 1.2 : 1 / 1.2;
      setView((current) => {
        const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current.zoom * factor));
        if (zoom === current.zoom) return current;
        // Keep the point under the cursor under the cursor.
        const px = (event.clientX - box.left) / box.width;
        const py = (event.clientY - box.top) / box.height;
        return {
          zoom,
          x: current.x + (FRAME.width / current.zoom - FRAME.width / zoom) * px,
          y: current.y + (FRAME.height / current.zoom - FRAME.height / zoom) * py,
        };
      });
    }
    node.addEventListener("wheel", zoomBy, { passive: false });
    return () => node.removeEventListener("wheel", zoomBy);
    // Re-bound when the map appears: it renders nothing until it has places.
  }, [places.length]);

  // Waited out rather than fired per frame. One continuous zoom crosses many distinct
  // windows, and asking for each one measured **five Overpass requests from a single
  // gesture** — against an endpoint that grants two concurrent slots and answers 504
  // once they are spent, so the burst reads as an outage it caused itself. The delay
  // means a gesture costs one request, taken once the hand stops.
  useEffect(() => {
    // Never during a capture. `refresh_buildings` *writes* — it stores the window in
    // `provider_cache` — so photographing this screen would change what the next
    // photograph shows, which is the drift the summaries prefetch already caused once.
    // A capture observes the app; it does not operate it.
    if (typeof document !== "undefined" && document.documentElement.dataset.capture) return;
    if (!tripId || !windowKey) return;
    if (asked.current === windowKey) return;
    const timer = window.setTimeout(() => {
      asked.current = windowKey;
      rpc<Buildings>("refresh_buildings", { trip_id: tripId, bbox: windowKey.split(",").map(Number) })
        .then((result) => setFootprints(result.too_wide ? [] : result.buildings))
        // A window with no footprints, or a provider that refused, simply draws none —
        // the map was already readable without them.
        .catch(() => setFootprints([]));
    }, SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [tripId, windowKey]);

  // Below every hook, not above: an early return before `useEffect` changes the hook
  // order between renders, which React forbids and the linter catches.
  if (!places.length) return null;

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
        ref={svgRef}
        role="img"
        style={{ "--map-zoom": view.zoom } as CSSProperties}
        viewBox={`${view.x} ${view.y} ${FRAME.width / view.zoom} ${FRAME.height / view.zoom}`}
      >
        {/* Footprints first — they are texture, not information — then water, parks
            and roads, in the order a map is read. */}
        {buildingRings.map((points, index) => (
          <polygon className="places-map-building" key={index} points={points} />
        ))}
        {lines.map((line, index) => (
          <polyline
            className={`places-map-${line.layer}`}
            key={`${line.layer}-${index}`}
            points={linePoints
              .slice(line.from, line.from + line.count)
              .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
              .join(" ")}
          />
        ))}
        {/* Radii and type are divided by the zoom: a viewBox scales its contents, so a
            fixed radius grows with the magnification and at 5x the pins already covered
            the streets they were meant to sit on. */}
        {cityPoints.map((point) => (
          <circle
            className="places-map-city"
            cx={point.x}
            cy={point.y}
            key={point.place_id}
            r={1.4 / view.zoom}
          />
        ))}
        {pinPoints.map((point) => {
          const isFocus = point.place_id === focusId;
          return (
            <g
              className={`plan-map-point${isFocus ? " current" : ""}${focusId && !isFocus ? " context" : ""}`}
              key={point.place_id}
            >
              <circle cx={point.x} cy={point.y} r={(isFocus ? 10 : 8) / view.zoom} />
              <text textAnchor="middle" x={point.x} y={point.y + 3 / view.zoom}>
                {point.label}
              </text>
            </g>
          );
        })}
      </svg>
      {/* Outside the svg, so panning does not carry the compass off the edge. */}
      <span aria-hidden="true" className="places-map-rose">N ↑</span>
      {homeKey === `${view.x.toFixed(1)},${view.y.toFixed(1)},${view.zoom.toFixed(3)}` ? null : (
        <button className="places-map-reset" onClick={() => setView(home)} type="button">
          {copy("map_reset", language)}
        </button>
      )}
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
