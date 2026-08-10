import { useEffect, useId, useMemo, useRef, useState, type CSSProperties } from "react";

import { rpc, type Basemap, type DiscoveryCandidate, type MapDetail } from "../api/client";
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
 * and no new request.
 *
 * **Zoomed in, it draws the layers a street map is made of** — land use, water, parks,
 * building footprints, the road hierarchy with casings, rail, transit markers, and
 * street names along the streets themselves. All of it from one free Overpass request
 * for the window on screen, all of it vector.
 *
 * `WF-034` forbids a tile map and this does not become one: nothing is fetched per tile,
 * nothing is fetched at view time except that single windowed request, and the numbered
 * list under the map still repeats every pin, so the drawing is never the only carrier.
 */

/** Taller than the itinerary's strip: this draws a whole city, and a square town in a
 *  wide band piles every pin into the middle. */
const FRAME = { width: 420, height: 260 } as const;
/** Far enough in to read a single street, far enough out to see the whole catalogue.
 *  Bounded both ways so the view can always be recovered by dragging. 8x was not enough:
 *  Taipei's catalogue spans about 0.56 degrees, so even at the old ceiling the window was
 *  still 0.07 degrees wide and the detail request was refused as too wide at every
 *  zoom the map could reach. */
const MIN_ZOOM = 1;
const MAX_ZOOM = 24;
/** Ask for the detailed layers once the window on screen is this small, in degrees.
 *  Measured against the *window*, not against the zoom factor: zoom is a ratio of the
 *  catalogue's own span, so the same factor is a different real distance in every city,
 *  and a street-scale view of Taipei is a regional view of somewhere compact. Matches
 *  `OpenStreetMapProvider.detail_max_span`, which refuses anything wider. */
const DETAIL_MAX_SPAN = 0.06;
/** How long the view must hold still before its detail is worth fetching. Long enough
 *  that swiping through the deck costs nothing — a card glanced at and thrown never
 *  asks — and short enough to feel immediate on the one being read. */
const SETTLE_MS = 900;
/** How much ground a focused map opens on, in kilometres across. A neighbourhood: near
 *  enough that streets and footprints are legible and the place can be recognised, wide
 *  enough to see what it sits next to. */
const FOCUS_KM = 1.6;
/**
 * Snapping the window onto a shared grid was tried, so that neighbouring places would
 * ask for one window and the second would be a cache hit. **It made the map worse and
 * was reverted.** `detail_limit` is a budget, and snapping spent it on ground that is
 * not on screen: measured in central Taipei, the snapped 4.4 km tile holds **15253**
 * buildings so the 1200 then returned were 8% of it, against **3546** in the 2.2 km
 * window actually being looked at. A scattered half of a neighbourhood reads as a city;
 * a twelfth of a district reads as a rash. The request rate is held down by `SETTLE_MS`
 * instead, which costs coverage nothing.
 */

/**
 * The road hierarchy, which is most of what makes a drawing read as a *map*.
 *
 * Every road used to be one grey line of one width, so a six-lane trunk road and a
 * service alley behind a shop were the same mark and the eye had nothing to follow.
 * Each class is drawn twice — a wider casing under a narrower fill — which is how a road
 * gets an edge, and how one road crossing another reads as a junction rather than a
 * smudge. Widths are in screen pixels via `vector-effect`, so they stay honest at every
 * zoom rather than fattening with the magnification.
 *
 * Ordered deliberately: the list is drawn in sequence, so a motorway is painted over the
 * alley it flies above rather than under it.
 */
const ROAD_STYLES: Record<string, { casing: number; fill: number; tone: string }> = {
  service: { casing: 2.2, fill: 1.4, tone: "minor" },
  cycleway: { casing: 0, fill: 1.2, tone: "cycle" },
  pedestrian: { casing: 4.4, fill: 3.2, tone: "walk" },
  living_street: { casing: 4.4, fill: 3, tone: "minor" },
  unclassified: { casing: 4.6, fill: 3.2, tone: "minor" },
  residential: { casing: 5, fill: 3.6, tone: "minor" },
  tertiary_link: { casing: 5, fill: 3.6, tone: "minor" },
  tertiary: { casing: 6, fill: 4.4, tone: "minor" },
  secondary_link: { casing: 6, fill: 4.4, tone: "major" },
  secondary: { casing: 7, fill: 5.2, tone: "major" },
  primary_link: { casing: 7, fill: 5.2, tone: "major" },
  primary: { casing: 8.2, fill: 6.2, tone: "major" },
  trunk_link: { casing: 8.2, fill: 6.2, tone: "trunk" },
  trunk: { casing: 9.4, fill: 7.2, tone: "trunk" },
  motorway_link: { casing: 9.4, fill: 7.2, tone: "trunk" },
  motorway: { casing: 10.6, fill: 8.2, tone: "trunk" },
};
const ROAD_ORDER = Object.keys(ROAD_STYLES);

/** Land use and landcover, grouped into the few families worth telling apart on a
 *  street map. Anything unlisted is drawn as plain land, which is what it is. */
const AREA_TONES: Record<string, string> = {
  park: "green", garden: "green", grass: "green", forest: "green", wood: "green",
  scrub: "green", pitch: "sport", playground: "sport", cemetery: "green",
  water: "water", riverbank: "water",
  residential: "built", retail: "retail", commercial: "retail",
  industrial: "industrial", construction: "construction",
};

/**
 * The families a discovered place is coloured by: food warm, shopping blue, culture
 * purple, outdoors green, lodging pink. The catalogue already carries a category for
 * every candidate, so this costs no request and no new data.
 *
 * **These dots are the point of the city view**, and were nearly deleted for looking
 * like noise. They are every attraction the search found, which is exactly the question
 * "where are the things I could add, and which part of town is each in" — the numbered
 * pins only show what has already been chosen, so on their own the map can never help
 * anyone choose. They were unreadable rather than unnecessary: no legend, no name, and
 * nothing happened when you touched one. Now the legend names the families, a dot
 * carries its own name, and tapping one opens that place's card.
 */
const POI_FAMILIES = ["food", "shop", "culture", "outdoors", "stay", "other"] as const;
const POI_TONES: Record<string, string> = {
  restaurant: "food", cafe: "food", fast_food: "food", bar: "food", pub: "food",
  marketplace: "food", food_court: "food",
  department_store: "shop", mall: "shop", supermarket: "shop", shop: "shop",
  museum: "culture", gallery: "culture", theatre: "culture", historic: "culture",
  memorial: "culture", monument: "culture", place_of_worship: "culture",
  temple: "culture", shrine: "culture", castle: "culture", ruins: "culture",
  attraction: "culture", artwork: "culture",
  park: "outdoors", garden: "outdoors", peak: "outdoors", viewpoint: "outdoors",
  nature_reserve: "outdoors", beach: "outdoors", zoo: "outdoors", waterfall: "outdoors",
  hotel: "stay", hostel: "stay", guest_house: "stay",
};

/** A street name is only worth printing if the street is long enough **on screen** to
 *  hold it, and only once however many segments OpenStreetMap splits it into. Expressed
 *  as a share of the visible width rather than in projection units: those are a share of
 *  the whole catalogue's span, where a real street is about two of them and every label
 *  was silently thrown away. */
const LABEL_MIN_SHARE = 0.16;
const LABEL_MAX = 26;

/**
 * Roughly how wide a string will be, in the same units the path is measured in.
 *
 * `textPath` does not wrap and does not shrink: a name longer than the street it runs
 * along is simply cut off wherever the path ends, which rendered as **a single stray
 * glyph** sitting in the middle of a park — the map looked like it had been sprinkled
 * with punctuation. So the label is measured before it is offered, and a street that
 * cannot hold its own name goes unlabelled, which is what a paper map does too.
 *
 * A CJK glyph occupies about a full em and a Latin one a little over half, which is
 * close enough to decide whether a name fits.
 */
function textWidth(text: string, size: number): number {
  let total = 0;
  for (const character of text) {
    total += /[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef]/.test(character) ? size : size * 0.55;
  }
  return total;
}
/** Below this the detailed layers are drawn but not labelled: at a whole-district view
 *  the names collide into a grey mat before any of them can be read. */
const LABEL_FROM_ZOOM = 6;

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
  /** Streets, water and parks for the whole city. Without it this is dots on grey; with
   *  it the city is recognisable and a pin has somewhere to be. */
  basemap?: Basemap | null;
  /** Drawn large and filled; everything else is context. Omit to weight them equally. */
  focusId?: string;
  /** The numbered list under the map. Off in the card, where one name is enough. */
  withKey?: boolean;
  /** Enables the zoomed-in detail fetch. Omit on a map nobody zooms. */
  tripId?: string;
  /** Opens a discovered place's card. Given one, the dots become the way to choose from
   *  the map rather than only to look at it. */
  onPick?: (placeId: string) => void;
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
  onPick,
}: PlaceMapProps) {
  // Zoom and pan, because at city scale several hundred dots and a dozen pins overlap
  // and no amount of styling separates them — the answer to "where is it" is sometimes
  // "closer". Held as a viewBox rather than a CSS transform, so that what is drawn can
  // be counter-scaled deliberately instead of everything magnifying together.
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 });
  const svgRef = useRef<SVGSVGElement | null>(null);
  // The ref carries the grab origin; the boolean is what the class reads, because a ref
  // read during render cannot re-render and React rightly refuses it.
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const [detail, setDetail] = useState<MapDetail | null>(null);
  // Which window has already been asked for, so panning inside it costs nothing.
  const asked = useRef<string>("");
  // Unique per instance, because two maps are on screen at once and a `textPath` points
  // at a path by id — shared ids would make the card's labels follow the pane's streets.
  // `useId` rather than a random ref: it is stable across renders *and* readable during
  // one, which a ref is not.
  const uid = useId().replace(/:/g, "");

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
        category: item.category ?? "",
        name: item.name ?? "",
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
    // *not* to the detail. Detail covers only the window currently on screen, so
    // including it would move the bounds every time a new window loaded and the whole
    // map would jump under the hand that zoomed it. It is projected through the
    // transform instead of helping define it.
    const projection = projectionOf([...vertices, ...city, ...pins], FRAME);
    const at = (latitude: number, longitude: number) =>
      projection ? projection.toXY(latitude, longitude) : { x: 0, y: 0 };
    const path = (ring: [number, number][]) =>
      ring.map(([lat, lon]) => { const p = at(lat, lon); return `${p.x.toFixed(1)},${p.y.toFixed(1)}`; })
        .join(" ");

    const linePoints = projection
      ? vertices.map((vertex) => projection.toXY(vertex.latitude, vertex.longitude))
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

    // The detailed layers, projected once and kept as strings ready to draw.
    const areas = (detail?.areas ?? []).map((area) => ({
      tone: AREA_TONES[area.kind] ?? "built",
      points: path(area.points),
    }));
    const buildings = (detail?.buildings ?? []).map(path);
    const roads = (detail?.roads ?? [])
      .filter((road) => road.class in ROAD_STYLES)
      .map((road) => {
        const points = road.points.map(([lat, lon]) => at(lat, lon));
        let length = 0;
        for (let i = 1; i < points.length; i += 1) {
          length += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
        }
        return {
          cls: road.class,
          name: road.name,
          nameEn: road.name_en,
          oneway: road.oneway,
          reversed: road.reversed,
          length,
          // Left-to-right where possible, so a label is never printed upside down.
          d: (points[0].x <= points[points.length - 1].x ? points : [...points].reverse())
            .map((p, index) => `${index ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
            .join(" "),
          points: points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" "),
        };
      });
    const rails = (detail?.rails ?? []).map((rail) => ({
      cls: rail.class,
      points: path(rail.points),
    }));
    const markers = (detail?.markers ?? []).map((marker) => ({
      kind: marker.kind,
      ...at(marker.point[0], marker.point[1]),
    }));

    return {
      projection,
      unitsPerKm,
      lines,
      linePoints,
      areas,
      buildings,
      roads,
      rails,
      markers,
      cityPoints: city.map((item) => ({ ...item, ...at(item.latitude, item.longitude) })),
      pinPoints: pins.map((pin) => ({ ...pin, ...at(pin.latitude, pin.longitude) })),
      across: Math.round(spanKm(city.length ? city : places)),
    };
  }, [basemap, context, places, detail]);
  const { lines, linePoints, areas, buildings, roads, rails, markers } = geometry;
  const { cityPoints, pinPoints, across } = geometry;
  const focused = pinPoints.find((point) => point.place_id === focusId);

  // The view the map opens on, and the one Reset returns to.
  //
  // Fitting the projection meant every map opened on the whole region — so the card's
  // "where is this one" was a picture of all of Taipei with one pin somewhere in it,
  // which is the complaint this screen kept getting. A map with a focus now opens at
  // street scale **on its subject**; one without fits the pins it was given. As a
  // consequence the card map's window is small enough to be worth the detailed layers,
  // so they arrive without anyone having to know to zoom.
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
  // `geometry` is rebuilt when detail arrives, and reacting to that would snap the map
  // home and undo the very pan that asked for it.
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

  // The detailed layers, only once the map is close enough for them to be legible, and
  // only for the window actually on screen. The inverse of the same projection is what
  // makes "the window actually on screen" expressible as latitude and longitude.
  const inverse = geometry.projection;
  const windowBox = (() => {
    if (!inverse) return null;
    const a = inverse.toLatLon(view.x, view.y);
    const b = inverse.toLatLon(view.x + FRAME.width / view.zoom, view.y + FRAME.height / view.zoom);
    return [
      Math.min(a.latitude, b.latitude), Math.min(a.longitude, b.longitude),
      Math.max(a.latitude, b.latitude), Math.max(a.longitude, b.longitude),
    ].map((value) => Number(value.toFixed(3)));
  })();
  // Wider than this and a footprint is sub-pixel anyway, so the provider refuses and
  // there is nothing to gain by asking.
  const visible =
    windowBox && Math.max(windowBox[2] - windowBox[0], windowBox[3] - windowBox[1]) <= DETAIL_MAX_SPAN
      ? windowBox
      : null;
  const windowKey = visible ? visible.join(",") : "";
  // **Does the detail still cover what is on screen?** It is one window's worth, so
  // zooming out past it left the map blank except for that patch — the city underneath
  // had been switched off the moment the detail arrived and never came back. The
  // city-wide basemap is drawn again as soon as the view reaches past the edge of the
  // detailed window, which is what makes zooming out show the city again.
  const detailCovers = Boolean(
    detail && windowBox
      && windowBox[0] >= detail.bbox[0] && windowBox[1] >= detail.bbox[1]
      && windowBox[2] <= detail.bbox[2] && windowBox[3] <= detail.bbox[3],
  );

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
    // Never during a capture. `refresh_map_detail` *writes* — it stores the window in
    // `provider_cache` — so photographing this screen would change what the next
    // photograph shows, which is the drift the summaries prefetch already caused once.
    // A capture observes the app; it does not operate it.
    if (typeof document !== "undefined" && document.documentElement.dataset.capture) return;
    if (!tripId || !windowKey) return;
    if (asked.current === windowKey) return;
    const timer = window.setTimeout(() => {
      asked.current = windowKey;
      rpc<MapDetail>("refresh_map_detail", { trip_id: tripId, bbox: windowKey.split(",").map(Number) })
        .then((result) => setDetail(result.too_wide ? null : result))
        .catch(() => {
          // A provider that refused simply draws the city view, which was readable
          // before any of this existed. The window is *un*-marked so that coming back
          // to it asks again: Overpass answers 503 under load, and a transient refusal
          // should not leave one patch of the city permanently plain.
          asked.current = "";
          setDetail(null);
        });
    }, SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [tripId, windowKey]);

  // Below every hook, not above: an early return before `useEffect` changes the hook
  // order between renders, which React forbids and the linter catches.
  if (!places.length) return null;

  // One label per name, on its longest segment: OpenStreetMap splits a street wherever
  // anything about it changes, so `中華路一段` arrives as a dozen ways and printing each
  // would stamp the name across the road a dozen times.
  const acrossView = FRAME.width / view.zoom;
  const leastLength = acrossView * LABEL_MIN_SHARE;
  const labelSize = 7 / view.zoom;
  const longestByName = new Map<string, (typeof roads)[number]>();
  if (detailCovers && view.zoom >= LABEL_FROM_ZOOM) {
    for (const road of roads) {
      if (!road.name || road.length < leastLength) continue;
      const held = longestByName.get(road.name);
      if (!held || road.length > held.length) longestByName.set(road.name, road);
    }
  }
  const labelled = [...longestByName.values()]
    // The romanized name where there is one: it is far shorter than the pair, so it
    // fits on streets the pair never would, and the local spelling is still on every
    // pin and in the list under the map.
    .map((road) => ({ ...road, label: road.nameEn || road.name }))
    .filter((road) => road.length >= textWidth(road.label, labelSize) * 1.05)
    .sort((left, right) => right.length - left.length)
    .slice(0, LABEL_MAX);

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
        {/* Paths for the street labels to run along. Defined once, referenced by
            `textPath`, and never painted themselves. */}
        <defs>
          {labelled.map((road, index) => (
            <path d={road.d} id={`${uid}-r${index}`} key={index} />
          ))}
          {/* `markerUnits` defaults to `strokeWidth`, so an arrow is scaled by the
              stroke of the line carrying it. The carrier is invisible and so had the
              default 1 *user* unit — which at 24x drew every arrow about 170 screen
              pixels wide, and a few hundred of them merged into one taupe mass that
              looked like a landmass and hid the whole map under it. Sized in user space
              instead, counter-scaled by the zoom like everything else here. */}
          <marker
            id={`${uid}-flow`}
            markerHeight={7 / view.zoom}
            markerUnits="userSpaceOnUse"
            markerWidth={7 / view.zoom}
            orient="auto"
            refX="2"
            refY="2"
            viewBox="0 0 4 4"
          >
            <path className="places-map-flow" d="M0.6,0.7 L2.6,2 L0.6,3.3" />
          </marker>
        </defs>

        {/* Painted in the order a map is read: ground, then water and green, then what
            is built on it, then what runs over it, then what is written on it. */}
        {detailCovers
          ? areas.map((area, index) => (
              <polygon className={`places-map-area ${area.tone}`} key={`a-${index}`} points={area.points} />
            ))
          : null}
        {detailCovers
          ? buildings.map((points, index) => (
              <polygon className="places-map-building" key={`b-${index}`} points={points} />
            ))
          : null}

        {/* The city-wide basemap steps aside once the real streets are here, rather than
            drawing a second, coarser set of the same roads on top of them. */}
        {detailCovers
          ? null
          : lines.map((line, index) => (
              <polyline
                className={`places-map-${line.layer}`}
                key={`${line.layer}-${index}`}
                points={linePoints
                  .slice(line.from, line.from + line.count)
                  .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
                  .join(" ")}
              />
            ))}

        {/* Casings for every road first, then every fill: done class by class the casing
            of the next road would cut a notch out of the fill of the last. */}
        {(detailCovers ? ROAD_ORDER : []).map((cls) =>
          roads.filter((road) => road.cls === cls && ROAD_STYLES[cls].casing).map((road, index) => (
            <polyline
              className={`places-map-road-casing ${ROAD_STYLES[cls].tone}`}
              key={`c-${cls}-${index}`}
              points={road.points}
              strokeWidth={ROAD_STYLES[cls].casing}
            />
          )),
        )}
        {(detailCovers ? ROAD_ORDER : []).map((cls) =>
          roads.filter((road) => road.cls === cls).map((road, index) => (
            <polyline
              className={`places-map-road ${ROAD_STYLES[cls].tone}`}
              key={`f-${cls}-${index}`}
              points={road.points}
              strokeWidth={ROAD_STYLES[cls].fill}
            />
          )),
        )}

        {/* Rail over road: a metro line passes under the street it follows, but on a map
            it is the line you are trying to find. */}
        {(detailCovers ? rails : []).map((rail, index) => (
          <polyline className={`places-map-rail ${rail.cls}`} key={`t-${index}`} points={rail.points} />
        ))}

        {/* Which way the traffic goes, on the roads big enough to care about. */}
        {detailCovers && view.zoom >= LABEL_FROM_ZOOM
          ? roads
              .filter((road) => road.oneway && road.length >= leastLength && ROAD_STYLES[road.cls].casing >= 5)
              .slice(0, 60)
              .map((road, index) => (
                <polyline
                  className="places-map-flow-line"
                  key={`o-${index}`}
                  markerMid={`url(#${uid}-flow)`}
                  // Thinned to every fourth vertex: `marker-mid` draws one arrow per
                  // intermediate point, and OpenStreetMap records a city street in
                  // dozens of them, so the road came out hatched like a railway.
                  points={(() => {
                    const all = road.points.split(" ");
                    const order = road.reversed ? [...all].reverse() : all;
                    return order.filter((_, at) => at % 4 === 0 || at === order.length - 1).join(" ");
                  })()}
                />
              ))
          : null}

        {/* Transit and service markers from OpenStreetMap: a station exit is the single
            most useful thing on a city map you are navigating on foot. */}
        {(detailCovers ? markers : []).map((marker, index) => (
          <circle
            className={`places-map-marker ${marker.kind}`}
            cx={marker.x}
            cy={marker.y}
            key={`m-${index}`}
            r={(marker.kind === "metro_entrance" ? 3.4 : 2.2) / view.zoom}
          />
        ))}

        {/* Radii and type are divided by the zoom: a viewBox scales its contents, so a
            fixed radius grows with the magnification and at 5x the pins already covered
            the streets they were meant to sit on. */}
        {cityPoints.map((point) => (
          <circle
            className={`places-map-city ${POI_TONES[point.category] ?? "other"}${onPick ? " pickable" : ""}`}
            cx={point.x}
            cy={point.y}
            key={point.place_id}
            onClick={onPick ? () => onPick(point.place_id) : undefined}
            r={(detailCovers ? 2.6 : 2.2) / view.zoom}
          >
            {/* The native tooltip, so a dot can say what it is without a hover card and
                without anything to lay out. */}
            <title>{point.name}</title>
          </circle>
        ))}

        {/* Street names last, over everything, each running along its own street. */}
        {labelled.map((road, index) => (
          <text
            className="places-map-street"
            fontSize={labelSize}
            key={`l-${index}`}
            strokeWidth={2.6 / view.zoom}
          >
            <textPath href={`#${uid}-r${index}`} startOffset="50%" textAnchor="middle">
              {road.label}
            </textPath>
          </text>
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
      {/* Shown on both maps, not only the one with a key: "what is the dot" is asked
          wherever the dots are, and the card's map draws them too. */}
      {cityPoints.length ? (
        <div className="places-map-legend">
          <p>{copy("map_legend", language)}</p>
          <ul>
            {POI_FAMILIES.map((family) => (
              <li key={family}>
                <span aria-hidden="true" className={`places-map-swatch ${family}`} />
                {copy(`map_kind_${family}`, language)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
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
