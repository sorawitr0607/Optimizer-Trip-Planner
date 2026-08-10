/**
 * OpenStreetMap's own map tiles, which is what makes the map look like
 * `openstreetmap.org` rather than like a drawing of it.
 *
 * `WF-034` decided against tiles, and the reason it gave was the app's premise: a plane
 * and a Taipei hotel with no usable network. That reason still holds, so this does not
 * replace the vector map — it sits **on top of it** and disappears the moment a tile
 * fails to load, which is exactly what happens offline. The plan still works on the
 * plane; it just looks better when it doesn't have to.
 *
 * Volume is what makes this acceptable use of a public service. A view is at most a few
 * dozen 256px images, the browser caches them, and nothing is ever fetched in bulk or
 * ahead of time. Attribution is shown beside every map that draws them, which the ODbL
 * requires of the geometry as well — so it should have been there all along.
 */

/** The OSMF standard style: the one `openstreetmap.org` itself serves. */
const TILE_URL = "https://tile.openstreetmap.org";
const TILE_PX = 256;
/** The deepest the standard style is rendered. Past it, tiles 404. */
const MAX_TILE_ZOOM = 19;
/** A whole view is a handful of tiles; more than this means a bug in the maths rather
 *  than a view anyone asked for, and it is not worth asking a public server for. */
const MAX_TILES = 48;

export interface Tile {
  key: string;
  url: string;
  /** The tile's own bounds, so the caller can place it with its own projection. */
  north: number;
  west: number;
  south: number;
  east: number;
}

/** Slippy-map tile numbering: the scheme every raster tile server shares. */
function tileX(longitude: number, n: number): number {
  return ((longitude + 180) / 360) * n;
}

function tileY(latitude: number, n: number): number {
  const radians = (latitude * Math.PI) / 180;
  return ((1 - Math.log(Math.tan(radians) + 1 / Math.cos(radians)) / Math.PI) / 2) * n;
}

function longitudeOf(x: number, n: number): number {
  return (x / n) * 360 - 180;
}

function latitudeOf(y: number, n: number): number {
  const value = Math.PI * (1 - (2 * y) / n);
  return (Math.atan(Math.sinh(value)) * 180) / Math.PI;
}

/**
 * The zoom whose tiles are closest to one image pixel per screen pixel.
 *
 * Chosen from the window rather than from the map's own zoom factor, for the reason
 * everything else here is: a zoom factor is a ratio of whatever the catalogue spans, and
 * a tile server's levels are absolute.
 */
export function tileZoomFor(box: number[], pixelWidth: number): number {
  const lonSpan = Math.max(box[3] - box[1], 1e-6);
  const wanted = Math.log2(((pixelWidth / TILE_PX) * 360) / lonSpan);
  return Math.max(0, Math.min(MAX_TILE_ZOOM, Math.round(wanted)));
}

/** Every tile covering `box`, at the zoom that best matches the space it is drawn in. */
export function tilesFor(box: number[], pixelWidth: number): Tile[] {
  const [south, west, north, east] = box;
  if (!(north > south && east > west)) return [];
  const zoom = tileZoomFor(box, pixelWidth);
  const n = 2 ** zoom;
  const fromX = Math.floor(tileX(west, n));
  const toX = Math.floor(tileX(east, n));
  // Tile rows run north to south, so the northern edge is the *lower* index.
  const fromY = Math.floor(tileY(north, n));
  const toY = Math.floor(tileY(south, n));
  if ((toX - fromX + 1) * (toY - fromY + 1) > MAX_TILES) return [];

  const tiles: Tile[] = [];
  for (let x = fromX; x <= toX; x += 1) {
    for (let y = fromY; y <= toY; y += 1) {
      // Wrapped so a view crossing the antimeridian still asks for a real tile rather
      // than a negative one, which every tile server answers with a 404.
      const wrapped = ((x % n) + n) % n;
      if (y < 0 || y >= n) continue;
      tiles.push({
        key: `${zoom}/${wrapped}/${y}`,
        url: `${TILE_URL}/${zoom}/${wrapped}/${y}.png`,
        north: latitudeOf(y, n),
        west: longitudeOf(x, n),
        south: latitudeOf(y + 1, n),
        east: longitudeOf(x + 1, n),
      });
    }
  }
  return tiles;
}
