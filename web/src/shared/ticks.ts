import { useState } from "react";

import type { TimedItem } from "./tripClock";

/**
 * Which stops the traveller has been to, per browser.
 *
 * There is no server field for "I have been here": `plan_versions` is append-only and
 * records what was *scheduled*, not what happened, and inventing one would mean a write
 * path, a migration and a schema bump against a hosted database that
 * `PostgresStore._copy_before_bump` rightly refuses. So this is `localStorage`.
 *
 * The cost is that ticks do not follow you to a second browser -- the same trade the
 * trip's own token already makes, and for the same reason.
 */

const TICK_PREFIX = "otp:done:";

function read(tripId: string): Record<string, 1> {
  try {
    return JSON.parse(localStorage.getItem(TICK_PREFIX + tripId) ?? "{}");
  } catch {
    // A private window, cleared site data, or storage blocked outright. An itinerary that
    // will not render because it could not read a tick is worse than no ticks.
    return {};
  }
}

function write(tripId: string, ticks: Record<string, 1>): void {
  try {
    localStorage.setItem(TICK_PREFIX + tripId, JSON.stringify(ticks));
  } catch {
    /* Nothing to do about it, and nothing worth breaking the page over. */
  }
}

export interface Ticks {
  isDone: (key: string) => boolean;
  toggle: (key: string, done: boolean) => void;
}

export function useTicks(tripId: string): Ticks {
  const [ticks, setTicks] = useState<Record<string, 1>>(() => read(tripId));
  return {
    isDone: (key: string) => Boolean(ticks[key]),
    toggle: (key: string, done: boolean) => {
      const next = { ...ticks };
      if (done) next[key] = 1;
      else delete next[key];
      setTicks(next);
      write(tripId, next);
    },
  };
}

/** How many of a set of stops are ticked, for a day's progress line. */
export function doneCount(items: TimedItem[], isDone: (key: string) => boolean): number {
  return items.filter((item) => isDone(item.key)).length;
}
