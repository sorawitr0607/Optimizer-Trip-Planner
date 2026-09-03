/**
 * Whether a free source records a place as closed, and how to say so.
 *
 * **A signal, not a verdict.** Wikidata knows `NHK Studio Park` closed in 2020 — it was
 * given four and a half hours on a 2026 plan — and knows nothing about `Yoshimoto ∞ Hall`,
 * which closed in March 2025. OpenStreetMap still tags both as attractions. So the app
 * shows what the source says and leaves the decision to the owner, who can answer with
 * `permanently_closed` where no source knows.
 *
 * Nothing here filters or drops a place. That is deliberate and was measured: reading
 * Wikidata's `P576` instead would have removed Edo Castle — whose site is the Imperial
 * Palace East Gardens — along with an open museum and a historic monument.
 */

/** Wikidata dates zero the parts it does not know: `2020-00-00` is "2020, month unknown". */
export function closedYear(summary: { closed_on?: string | null } | undefined): string | null {
  const stamp = (summary?.closed_on ?? "").trim();
  if (!stamp) return null;
  const year = stamp.slice(0, 4);
  return /^\d{4}$/.test(year) ? year : null;
}

/** Whether to show the note at all. Kept beside `closedYear` so the two cannot disagree. */
export function looksClosed(summary: { closed_on?: string | null } | undefined): boolean {
  return closedYear(summary) !== null;
}
