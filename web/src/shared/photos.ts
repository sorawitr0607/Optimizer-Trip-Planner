import type { DiscoveryCandidate, PlaceSummary } from "../api/client";

/**
 * Where a place's photographs come from, in one place.
 *
 * Wikidata and Wikipedia were the only sources, so a place with no encyclopedia entry
 * showed an empty card — common, because most of a dense city's catalogue has neither.
 * OpenStreetMap's own `wikimedia_commons` / `image` tags are a third source that costs
 * nothing extra: `discovery.py` already stores the tag as `photo_reference` on every
 * candidate, and nothing had ever read it.
 */

/** Commons serves any file by name, so no thumbnail URL has to be constructed. */
const COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/";

/**
 * One OpenStreetMap photo tag as an image URL, or null.
 *
 * The tag is not a URL and is not consistently spelled. `wikimedia_commons` holds
 * `File:Foo.jpg` and sometimes `Category:Foo` — a category is a page of many files, not
 * an image, so it is dropped rather than guessed at. `image` sometimes holds a direct
 * http URL, which is used as-is, and sometimes a bare filename.
 */
/**
 * At or below this many photographs, a card counts as thin and the paid lookup is
 * worth offering.
 *
 * **One, not zero.** A single Commons geosearch shot of the car park next door is as
 * short of a picture of the place as no shot at all, and the owner asked for the offer
 * on both. It lives here because two screens decide the same thing — the deck's buy
 * button and the detail panel's `thinlyPictured` — and they were separate literals that
 * had already drifted: the panel said one, the deck said none.
 */
export const PHOTO_THIN_AT = 1;

export function osmPhotoUrl(reference: string | null | undefined): string | null {
  const value = (reference ?? "").trim();
  if (!value) return null;
  if (/^https?:\/\//i.test(value)) return value;
  if (/^category:/i.test(value)) return null;
  const file = value.replace(/^file:/i, "").trim();
  if (!file) return null;
  return `${COMMONS}${encodeURIComponent(file.replace(/\s+/g, "_"))}?width=640`;
}

/**
 * Every photograph known for one place, best first and without duplicates.
 *
 * Wikidata's curated P18 leads where there is one, then article photographs, then
 * OpenStreetMap's tag. Appended rather than substituted: it is one more picture to tap
 * through, and on a place with no article it is the only one.
 */
export function galleryFor(
  summary: PlaceSummary | undefined,
  candidate: Pick<DiscoveryCandidate, "photo_reference"> | undefined,
): string[] {
  const fromEncyclopedia = summary?.image_urls?.length
    ? summary.image_urls
    : summary?.image_url
      ? [summary.image_url]
      : [];
  const fromOsm = osmPhotoUrl(candidate?.photo_reference);
  return [...new Set([...fromEncyclopedia, ...(fromOsm ? [fromOsm] : [])])];
}
