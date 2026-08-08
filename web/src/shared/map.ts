import type { DiscoveryCandidate } from "../api/client";

/** One place as a point on the drawn map. */
export interface MapPlace {
  place_id: string;
  label: string;
  name: string;
  latitude: number;
  longitude: number;
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
