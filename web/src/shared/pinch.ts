/**
 * The arithmetic behind pinch-to-zoom, kept out of the component that uses it.
 *
 * A module rather than three exports on `PlaceMap.tsx` for the reason `shared/cards.ts`
 * exists: a file that exports a component may not also export helpers, and the lint rule
 * that says so is not negotiable.
 *
 * It is separate for a second reason too. The gesture itself cannot be tested here —
 * driving it needs real touches, and a dispatched `PointerEvent` does not move the map
 * even on the code that predates the pinch, which was checked against the deployment
 * rather than assumed. So the part that can be pinned is pinned, and the wiring left in
 * the component is small enough to read.
 */

export interface Finger {
  x: number;
  y: number;
}

/** Distance between the first two fingers, in client pixels. */
export function spreadOf(points: Map<number, Finger>): number {
  const [a, b] = [...points.values()];
  if (!a || !b) return 0;
  return Math.hypot(a.x - b.x, a.y - b.y);
}

/** The point halfway between them, which is what a pinch should hold still. */
export function centreOf(points: Map<number, Finger>): Finger {
  const [a, b] = [...points.values()];
  if (!a || !b) return { x: 0, y: 0 };
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

/**
 * The zoom a pinch has reached, measured from where the fingers started.
 *
 * Relative to the start of the gesture rather than to the previous move, so a pinch
 * that goes out and comes back lands where it began instead of drifting. A spread of
 * zero returns the starting zoom untouched: dividing by it would send the viewBox to
 * Infinity, which is what a zero-width map produced while this was being tested.
 */
export function pinchedZoom(
  start: { spread: number; zoom: number },
  spread: number,
  minZoom: number,
  maxZoom: number,
): number {
  if (!spread || !start.spread) return start.zoom;
  return Math.min(maxZoom, Math.max(minZoom, start.zoom * (spread / start.spread)));
}
