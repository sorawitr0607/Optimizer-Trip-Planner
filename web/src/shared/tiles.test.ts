import { describe, expect, it } from "vitest";

import { tileZoomFor, tilesFor } from "./tiles";

/**
 * The slippy-map numbering every raster tile server shares. Getting a tile's own bounds
 * wrong does not fail loudly — the image simply lands in the wrong place and smears
 * against the pins drawn on it — so the arithmetic is pinned against known values.
 */
describe("map tiles", () => {
  it("gives each tile bounds that contain the ground it covers", () => {
    const [tile] = tilesFor([25.03, 121.56, 25.04, 121.57], 740);
    expect(tile.north).toBeGreaterThan(tile.south);
    expect(tile.east).toBeGreaterThan(tile.west);
    expect(tile.north).toBeGreaterThanOrEqual(25.03);
    expect(tile.west).toBeLessThanOrEqual(121.56);
  });

  it("picks a zoom worth about one image pixel per screen pixel", () => {
    // Asserted as the property rather than a level: the number is a consequence of the
    // window and the width, and writing it down by hand got it wrong by two levels.
    for (const box of [
      [25.03, 121.56, 25.04, 121.57],
      [25.0, 121.4, 25.4, 121.8],
      [24.5, 120.5, 25.5, 122.5],
    ]) {
      const zoom = tileZoomFor(box, 740);
      const tilesAcross = ((box[3] - box[1]) / 360) * 2 ** zoom;
      expect(tilesAcross * 256).toBeGreaterThan(740 / 2);
      expect(tilesAcross * 256).toBeLessThan(740 * 2);
    }
  });

  it("covers the whole window, not just its corner", () => {
    const box = [25.02, 121.5, 25.06, 121.56];
    const tiles = tilesFor(box, 740);
    expect(tiles.length).toBeGreaterThan(1);
    expect(Math.max(...tiles.map((t) => t.north))).toBeGreaterThanOrEqual(box[2]);
    expect(Math.min(...tiles.map((t) => t.south))).toBeLessThanOrEqual(box[0]);
    expect(Math.min(...tiles.map((t) => t.west))).toBeLessThanOrEqual(box[1]);
    expect(Math.max(...tiles.map((t) => t.east))).toBeGreaterThanOrEqual(box[3]);
  });

  it("asks for a deeper zoom for a smaller window", () => {
    const wide = tileZoomFor([25.0, 121.4, 25.4, 121.8], 740);
    const close = tileZoomFor([25.03, 121.56, 25.04, 121.57], 740);
    expect(close).toBeGreaterThan(wide);
    // The standard style is not rendered past 19, and asking anyway returns 404s.
    expect(tileZoomFor([25.0, 121.5, 25.0001, 121.5001], 740)).toBeLessThanOrEqual(19);
  });

  it("refuses a window that would need an unreasonable number of tiles", () => {
    // A guard against the maths going wrong, not against a view anyone asked for: a
    // public tile server should never be asked for hundreds of images at once.
    expect(tilesFor([-85, -180, 85, 180], 740 * 400)).toEqual([]);
  });

  it("returns nothing for a window that is inside out", () => {
    expect(tilesFor([25.04, 121.57, 25.03, 121.56], 740)).toEqual([]);
  });

  it("wraps a tile column that runs past the antimeridian", () => {
    for (const tile of tilesFor([-0.01, 179.99, 0.01, 180.01], 740)) {
      const [, x] = tile.key.split("/").map(Number);
      expect(x).toBeGreaterThanOrEqual(0);
    }
  });
});
