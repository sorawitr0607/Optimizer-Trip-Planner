/**
 * Whether the owner has been asked which list to start with, for one discovery run.
 *
 * **Once per discovery run, not once per trip.** The trigger asked for is "after finish
 * load", and a fresh search really is a fresh set of lanes with fresh counts — so
 * `run_id` is the key. Re-searching offers the choice again; reloading, navigating away
 * and coming back, or deciding a card does not.
 *
 * Storage rules are `PlacesTour`'s, for the same two reasons. Guarded, because
 * `localStorage` throws in a locked-down profile and a panel is not worth a blank
 * screen — a profile that refuses storage simply gets asked again. And suppressed under
 * `data-capture`, because a fresh Chrome profile is always a first visit, so without the
 * seam every `/places` screen baseline would photograph this panel instead of the deck
 * it is watching.
 *
 * Its own module rather than living beside the component: the lint rule that forbids
 * mixed exports from a component file is the same one `shared/buildStages.ts` and
 * `shared/cards.ts` exist for.
 */

const CHOSEN_KEY = "tourist.lane_chosen";

/* Bare `localStorage`, not `window.localStorage`, and guarded with `typeof`. That is
   `shared/basemap.ts`'s pattern and it is the one that works here: `vite.config.ts` runs
   the suite under `environment: "node"`, where there is no `window` at all — so the
   `window.` form throws on every call, is swallowed by the catch, and reads as "already
   answered" in a test that never touches storage. Correct in a browser either way, but
   only this form is testable. */
export function laneAlreadyChosen(runId: string): boolean {
  const root = typeof document === "undefined" ? null : document.documentElement;
  if (root?.dataset.capture) return true;
  if (typeof localStorage === "undefined") return true;
  try {
    return localStorage.getItem(`${CHOSEN_KEY}.${runId}`) === "1";
  } catch {
    return true;
  }
}

export function rememberLaneChoice(runId: string): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(`${CHOSEN_KEY}.${runId}`, "1");
  } catch {
    /* A profile that refuses storage simply gets asked again. */
  }
}
