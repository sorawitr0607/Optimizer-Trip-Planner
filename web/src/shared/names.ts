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
