import type { DiscoveryCandidate } from "../api/client";

/** One place as a point on the drawn map. */
export interface MapPlace {
  place_id: string;
  label: string;
  name: string;
  latitude: number;
  longitude: number;
  /** An optimizer status, where the caller has one. The itinerary colours its stops by
   *  it — a locked stop and a re-check are not the same pin, and the plan is read by
   *  glancing at which is which. */
  status?: string;
  /** True when this pin represents a timed itinerary stop rather than context such as
   *  the hotel. The itinerary uses it as the same time control as the timeline row. */
  interactive?: boolean;
}

/**
 * Shortlisted places as map points, numbered in the order they were kept.
 *
 * Here rather than beside the component because two screens build the same list and a
 * lint rule rightly keeps component files to components — but the real reason is that
 * the numbering *is* the contract: the map's label and the list's label have to be the
 * same string or neither picture can be read against the other. The shortlist rows
 * read the same numbers through `shortlistNumber`, which is why this lives in a
 * module both can import.
 *
 * A place with no coordinates yields no point. It stays on the shortlist; it simply
 * cannot be drawn, which is a gap rather than a reason to drop it.
 */
export function mapPlaces(
  order: { place_id: string }[],
  catalog: DiscoveryCandidate[],
  nameOf: (candidate: DiscoveryCandidate) => string,
): MapPlace[] {
  return order
    .map((item, index) => {
      const found = catalog.find((value) => value.place_id === item.place_id);
      if (!found || found.latitude === null || found.longitude === null) return null;
      return {
        place_id: item.place_id,
        label: String(index + 1),
        name: nameOf(found),
        latitude: found.latitude,
        longitude: found.longitude,
      };
    })
    .filter((point): point is MapPlace => point !== null);
}

/** The number a shortlisted place wears on the map, for the list rows that name the
 *  same place. One-based over the whole kept order — the same figure the pin draws —
 *  and undefined for a place that cannot be drawn, which is exactly the case where
 *  the list must not pretend a pin exists. */
export function shortlistNumber(
  placeId: string,
  order: { place_id: string }[],
  catalog: DiscoveryCandidate[],
): number | undefined {
  const index = order.findIndex((item) => item.place_id === placeId);
  if (index < 0) return undefined;
  const found = catalog.find((value) => value.place_id === placeId);
  if (!found || found.latitude === null || found.longitude === null) return undefined;
  return index + 1;
}

/**
 * A link that hands the last fifty metres to the phone's own map.
 *
 * This app schedules a day; it does not do turn-by-turn, and should not try — the
 * routing it holds is a duration, not a path. What it can do is stop being a dead end at
 * the moment the owner is standing on a corner looking for a temple.
 *
 * **Coordinates only, and the name is deliberately not sent.** `query` is a *search*,
 * so `Namba Yasaka Shrine 34.66,135.50` is answered by whatever Google's index thinks
 * best matches the words — which is how a stop opened on a different shrine in another
 * ward, and how a name it does not recognise opened on nothing at all. A bare
 * `lat,lng` is not a search at all; it drops a pin exactly where the catalogue says the
 * place is. Labelling that pin would need a Google place id, which this app has never
 * held. The name is already on screen beside the link.
 */
export function mapsLink(latitude: number, longitude: number): string {
  return `https://www.google.com/maps/search/?api=1&query=${latitude.toFixed(6)},${longitude.toFixed(6)}`;
}
