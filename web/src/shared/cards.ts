/**
 * What on a ranked card is about the place, and what is about the pipeline.
 *
 * `ranking.py` fills two fields before it has looked at the place at all, and both were
 * being rendered as though they described it:
 *
 * - `feasibility.state` is fixed at `not_evaluated` / `not_evaluated_until_optimizer`,
 *   because ranking runs before the optimizer and cannot know.
 * - `cons` is seeded with `route_not_verified`, `ratings_not_enriched` and
 *   `best_time_unconfirmed` on every candidate alike.
 *
 * Printed on every card these say only "not looked at yet", identically everywhere, and
 * a row with one possible value cannot separate this place from the next -- it teaches
 * the eye to skip the rows that can. `/places` showed it most plainly: its caution
 * column was `cons.slice(0, 2)`, and since the constants come first, every place in the
 * catalogue carried the same two strings.
 *
 * Shared rather than duplicated because the deck and the list render the same fields,
 * and the two disagreeing about one place is a bug this app has had before.
 */

/** The cons `ranking.py` puts on every card, which therefore distinguish nothing. */
const UNIVERSAL_CONS = new Set([
  "route_not_verified",
  "ratings_not_enriched",
  "best_time_unconfirmed",
]);

/** Only the cons that say something about this place rather than about the pipeline. */
export function distinguishingCons(cons: string[]): string[] {
  return cons.filter((code) => !UNIVERSAL_CONS.has(code));
}

/** Whether a card's feasibility state is an answer rather than a placeholder. */
export function evaluatedFeasibility(state: string): boolean {
  return !state.startsWith("not_evaluated");
}

export function evaluatedEffort(state: string | undefined): boolean {
  // Unknown states stay hidden: presenting a placeholder as measured was the original bug.
  return state === "visit_time_estimated" || state === "routed";
}
