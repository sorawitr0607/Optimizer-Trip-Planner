/**
 * Which places the owner has already lengthened the trip for, per trip.
 *
 * **"Add N days and rebuild once" must not be offered twice for the same place.** The
 * optimizer can prove some places will never fit — `NO_DAY_LONG_ENOUGH`, which is its
 * answer to "could this fit an *empty* day" — and those are recommended for removal
 * straight away. But `NO_TIME_CAPACITY` is a genuine "a longer trip would hold this",
 * and it can still be wrong in practice: the added days go on the end, and a place whose
 * opening hours, routes or locks conspire against it can come back unplaced anyway. The
 * owner then sees the same button they just pressed. Reported as "after you try to add
 * the day but it still have some place that still can't fit".
 *
 * So the offer is made **once per place**. A place that is still short of capacity after
 * days were added for it is one adding days did not help, whatever the optimizer can
 * prove, and the honest next step is to drop it.
 *
 * No invalidation, deliberately. The set is only ever consulted for places that are
 * *still* unplaced, so an entry for a place that now fits is never read — and a place
 * that fits does not appear in `needsDays` at all. Clearing it on a date change would
 * mean guessing which change was meant to help which place.
 *
 * `localStorage`, guarded, on `shared/basemap.ts`'s pattern: bare rather than
 * `window.`-qualified because the suite runs under `environment: "node"`, and every
 * access wrapped because a locked-down profile must not cost the screen. A profile that
 * refuses storage simply gets offered the day once more, which is the old behaviour.
 */

const TRIED_KEY = "tourist.days_added_for";

export function placesDaysWereAddedFor(tripId: string): ReadonlySet<string> {
  if (!tripId || typeof localStorage === "undefined") return new Set();
  try {
    const held = JSON.parse(localStorage.getItem(`${TRIED_KEY}.${tripId}`) ?? "[]");
    return new Set(Array.isArray(held) ? held.filter((id) => typeof id === "string") : []);
  } catch {
    return new Set();
  }
}

export function rememberDaysAddedFor(tripId: string, placeIds: readonly string[]): void {
  if (!tripId || typeof localStorage === "undefined") return;
  try {
    const merged = new Set([...placesDaysWereAddedFor(tripId), ...placeIds]);
    localStorage.setItem(`${TRIED_KEY}.${tripId}`, JSON.stringify([...merged].sort()));
  } catch {
    /* A profile that refuses storage gets offered the day once more. */
  }
}
