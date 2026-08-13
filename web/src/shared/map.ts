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
}

/**
 * Shortlisted places as map points, numbered in the order they were kept.
 *
 * Here rather than beside the component because two screens build the same list and a
 * lint rule rightly keeps component files to components — but the real reason is that
 * the numbering *is* the contract: the map's label and the list's label have to be the
 * same string or neither picture can be read against the other.
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

/**
 * A link that hands the last fifty metres to the phone's own map.
 *
 * This app schedules a day; it does not do turn-by-turn, and should not try — the
 * routing it holds is a duration, not a path. What it can do is stop being a dead end at
 * the moment the owner is standing on a corner looking for a temple. `geo:` is the
 * platform-neutral scheme: Android opens the user's chosen map, iOS opens Apple Maps,
 * and a desktop browser falls back to whatever is registered, so no vendor is wired in.
 * The name rides along as the query label so the pin says what it is.
 */
export function mapsLink(latitude: number, longitude: number, name: string): string {
  const at = `${latitude.toFixed(6)},${longitude.toFixed(6)}`;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(name ? `${name} ` : "")}${at}`;
}
