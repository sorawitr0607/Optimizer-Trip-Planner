import { describe, expect, it } from "vitest";

import { projectionOf } from "./ItineraryPage";

/**
 * A projection is fitted to the points it is given, and one point has no extent to fit.
 * The fallback was a scale of **1**, which makes the unit a radian — so a kilometre
 * measured 0.00019 units against 139 for the same map with a second pin on it, a factor
 * of 730,000. Every consumer reasons in real distance (`FOCUS_KM`, `MIN_VIEW_KM`, the
 * detail-fetch gate, the scale note, the tile zoom), so all of them were reading a
 * number with no geographic meaning.
 *
 * That is exactly two screens: the first swipe card, whose shortlist is still empty, and
 * an itinerary day with a single stop.
 */

const FRAME = { width: 420, height: 260 };
const NARA = { latitude: 34.685, longitude: 135.833 };

function unitsPerKm(points: { latitude: number; longitude: number }[]): number {
  const projection = projectionOf(points, FRAME)!;
  const here = projection.toXY(NARA.latitude, NARA.longitude);
  const north = projection.toXY(NARA.latitude + 1 / 111, NARA.longitude);
  return Math.hypot(north.x - here.x, north.y - here.y);
}

describe("projectionOf", () => {
  it("gives a lone point a scale in real distance, not a scale of one", () => {
    const alone = unitsPerKm([NARA]);
    const pair = unitsPerKm([NARA, { latitude: 34.7, longitude: 135.85 }]);

    // Same order of magnitude as a real two-point fit, rather than 1/730000 of it.
    expect(alone).toBeGreaterThan(pair / 20);
    expect(alone).toBeLessThan(pair * 20);
    // And it is the documented span: the usable frame (420 less 14 of padding each
    // side) covers DEGENERATE_SPAN_KM = 2 km, so 392 / 2 = 196 units to the kilometre.
    expect(alone).toBeCloseTo(196, 0);
  });

  it("still fits the points wherever there is an extent to fit", () => {
    // The ordinary path must not move — the 36 screen baselines depend on it.
    const projection = projectionOf([NARA, { latitude: 34.7, longitude: 135.85 }], FRAME)!;
    const a = projection.toXY(NARA.latitude, NARA.longitude);
    const b = projection.toXY(34.7, 135.85);

    expect(Math.max(a.x, b.x)).toBeLessThanOrEqual(FRAME.width);
    expect(Math.max(a.y, b.y)).toBeLessThanOrEqual(FRAME.height);
    expect(Math.min(a.x, b.x)).toBeGreaterThanOrEqual(0);
    expect(Math.min(a.y, b.y)).toBeGreaterThanOrEqual(0);
  });

  it("round-trips a lone point through both directions", () => {
    const projection = projectionOf([NARA], FRAME)!;
    const { x, y } = projection.toXY(NARA.latitude, NARA.longitude);
    const back = projection.toLatLon(x, y);

    expect(back.latitude).toBeCloseTo(NARA.latitude, 6);
    expect(back.longitude).toBeCloseTo(NARA.longitude, 6);
  });
});
