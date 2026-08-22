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

/**
 * Whether reward-versus-effort is a measurement on this card.
 *
 * It usually is not. `ranking.py` assigns `reward_effort = 10.0` as a literal and sets
 * `effort_state` to `route_and_walking_not_evaluated`, so this dimension is **20 of the
 * formula's 100 points frozen at exactly half** for every candidate in the catalogue.
 * Ordering is unaffected -- a constant added to every score preserves the order -- but
 * printing "Reward versus effort: 10/20" on a card states a per-place finding that was
 * never computed, and it reads identically on all of them.
 *
 * Found auditing the scoring against setup, which is also how the deck came to be
 * showing three such rows out of five.
 */
const UNMEASURED_EFFORT = new Set([
  // What `ranking.py` actually emits today.
  "route_and_walking_not_evaluated",
  // And the older spelling still in fixtures. Listed rather than assumed away: a state
  // this does not recognise is treated as *not* measured, because printing a placeholder
  // as a finding is the failure being fixed and staying silent is not.
  "unknown",
]);

export function evaluatedEffort(state: string | undefined): boolean {
  return Boolean(state) && !UNMEASURED_EFFORT.has(state as string);
}
