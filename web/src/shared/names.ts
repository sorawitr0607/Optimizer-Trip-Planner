import type { Language } from "../i18n/copy";

/**
 * One place-naming rule for every screen.
 *
 * A place shows its sourced English name, falling back to the stored name only
 * when no English name is available. Two things depend on getting this right and
 * are stated rules rather than taste: a consequence or a plan row must **name a
 * place, never a truncated `place_id`**, and a **city name is never localized**
 * because it is the geocoder query.
 *
 * It lives here because three screens needed it and had begun to diverge:
 * `places`, `optimize` and `revise` each carried their own copy with a different
 * signature. Divergence in this rule is invisible until a screen shows an id.
 */
export function placeName(
  source: { name?: string; names?: Record<string, string | undefined> | null } | null | undefined,
  _language: Language,
  fallback = "",
): string {
  const names = source?.names ?? undefined;
  return names?.en || source?.name || names?.local || fallback;
}

/**
 * One naming source from the catalogue plus whatever a free lookup has since supplied.
 *
 * OpenStreetMap wins where it has a name, because `name:en` is the name on the ground.
 * Wikidata's label fills the gaps — 61% of the Taipei catalogue has no `name:en` at all,
 * and for the places that carry a QID the label is a real English name rather than a
 * translation: 三井物產株式會社舊廈 is "Mitsui & Co., Ltd. Old Building".
 *
 * The label arrives with the free description, so a place shows its English name once
 * the owner has asked for descriptions and not before. That is the honest sequence —
 * the app cannot know a name it has not looked up.
 */
export function mergeNames(
  source: { name?: string; names?: Record<string, string | undefined> | null } | null | undefined,
  extra: Record<string, string | undefined> | null | undefined,
): { name?: string; names: Record<string, string | undefined> } {
  const found = Object.fromEntries(
    Object.entries(extra ?? {}).filter(([, value]) => Boolean(value)),
  );
  const stored = Object.fromEntries(
    Object.entries(source?.names ?? {}).filter(([, value]) => Boolean(value)),
  );
  return { name: source?.name, names: { ...found, ...stored } };
}

/** The same rule against an untyped frozen snapshot payload. */
export function placeNameFrom(
  data: Record<string, unknown> | null | undefined,
  _language: Language,
  fallback = "",
): string {
  if (!data) return fallback;
  const names = data.names;
  const table =
    names && typeof names === "object" ? (names as Record<string, string | undefined>) : undefined;
  const literal = typeof data.name === "string" ? data.name : undefined;
  return table?.en || literal || table?.local || fallback;
}
