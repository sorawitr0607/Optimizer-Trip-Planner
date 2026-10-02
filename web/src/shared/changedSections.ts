/** Sections named by a preview_stale refusal, without assuming its detail shape. */
export function changedSections(detail: unknown): string[] {
  if (typeof detail !== "object" || detail === null) return [];
  const changed = (detail as { changed?: unknown }).changed;
  if (!Array.isArray(changed)) return [];
  return changed.filter((item): item is string => typeof item === "string");
}
