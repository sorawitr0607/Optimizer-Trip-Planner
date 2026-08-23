/**
 * Calendar arithmetic, in UTC and formatted from UTC parts.
 *
 * Its own module rather than locals in `StayPlanner`, for two reasons. The lint
 * rule is the visible one — a file that exports a component may not also export
 * helpers — but the real one is that this is where the custom date range's cap is
 * decided, and a cap is worth testing directly rather than through a render.
 *
 * UTC throughout: a local-time `Date` shifts the day across a timezone boundary,
 * and every date this app handles is a calendar day rather than an instant.
 */

/**
 * How many days a `start`..`end` pair covers, counting **both** ends.
 *
 * Inclusive because a pace is inclusive: the balanced five-day pace recommends
 * the 1st to the 5th, not the 6th. Get this off by one and the custom range
 * either refuses the app's own recommendation or quietly allows a sixth day the
 * optimizer was never asked to fill.
 *
 * Zero or less when `end` precedes `start`, which the caller reads as invalid
 * rather than as a very short trip.
 */
export function spanDays(start: string, end: string): number {
  const from = Date.parse(`${start}T00:00:00Z`);
  const to = Date.parse(`${end}T00:00:00Z`);
  if (Number.isNaN(from) || Number.isNaN(to)) return 0;
  return Math.round((to - from) / 86_400_000) + 1;
}

/** Days in a month, from day 0 of the next one. `month` is 1-based. */
export function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/** `iso` moved by `days`, as another ISO date. */
export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
