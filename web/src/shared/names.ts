import type { Language } from "../i18n/copy";

/**
 * One place-naming rule for every screen.
 *
 * A place shows its localized name, falling back to English, then to the local
 * name, then to the stored literal. Two things depend on getting this right and
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
  language: Language,
  fallback = "",
): string {
  const names = source?.names ?? undefined;
  return names?.[language] ?? names?.en ?? names?.local ?? source?.name ?? fallback;
}

/**
 * The other name, when showing it helps and repeating one does not.
 *
 * A traveller in Taipei needs both: the local name is what the station sign, the taxi
 * driver and the ticket machine use, and the English one is what they can read. So a
 * place shows `placeName()` as its heading and this beside it — `西門` next to `Ximen`,
 * and nothing at all where the two would be the same string.
 *
 * Returns `null` rather than an empty string so a caller cannot render a stray
 * separator around nothing.
 */
export function placeAltName(
  source: { name?: string; names?: Record<string, string | undefined> | null } | null | undefined,
  language: Language,
): string | null {
  const names = source?.names ?? undefined;
  const primary = placeName(source, language);
  // The local name is the useful counterpart in every direction: reading Thai or
  // English, it is the string that matches what is written on the building.
  const alternate = names?.local ?? undefined;
  if (!alternate || !primary || alternate === primary) return null;
  return alternate;
}

/** The same rule against an untyped frozen snapshot payload. */
export function placeNameFrom(
  data: Record<string, unknown> | null | undefined,
  language: Language,
  fallback = "",
): string {
  if (!data) return fallback;
  const names = data.names;
  const table =
    names && typeof names === "object" ? (names as Record<string, string | undefined>) : undefined;
  const literal = typeof data.name === "string" ? data.name : undefined;
  return table?.[language] ?? table?.en ?? table?.local ?? literal ?? fallback;
}
