import type { ExportDay, ExportPlanItem } from "../api/client";
import { copy, copyFormat, type Language } from "../i18n/copy";

/**
 * The trip as one ordered list of moments, and where "now" falls in it.
 *
 * The itinerary is stored day by day, which is how it is read but not how it is lived:
 * "what am I doing, and what is next" crosses midnight and crosses days. So the days are
 * flattened once into a single sequence with real `Date`s on it, and every question the
 * screen asks -- what is live, what is next, how far off is it -- is answered against
 * that one list.
 *
 * Pure and free of React so it can be tested directly. The `Date` arithmetic is the part
 * worth testing: a plan whose last item ends after midnight is normal, not an edge case.
 */

export interface TimedItem extends ExportPlanItem {
  /** Which day block the item was listed under, which is not always its own date. */
  dayDate: string;
  startAt: Date;
  endAt: Date;
  /** Stable across re-renders and across languages, for tick state and React keys. */
  key: string;
}

/** `YYYY-MM-DD` plus `HH:MM` as a local Date. Local, because a plan is lived locally.
 *
 *  Named `momentAt` rather than `at`: `providers.py` has a local `def at(field)` inside
 *  `OpenMeteoForecastProvider.forecast`, and the graph builder matched the two names and
 *  invented an edge claiming Python calls TypeScript. That is the third occurrence of the
 *  same collision after `rpc` and `fetch`, and CLAUDE.md's rule is to fix it at the
 *  source rather than weaken the endpoint-pair guard. A two-letter module export was
 *  asking for it. */
export function momentAt(date: string, time: string): Date {
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  return new Date(year, month - 1, day, hour, minute);
}

/**
 * Every item of every day, in time order, with an end for each.
 *
 * An item whose `end` is before its `start` has crossed midnight, so a day is
 * added rather than the row being drawn as ending before it began -- the same rollover
 * rule the trip dashboards derive their dates with. An item with no usable end borrows
 * the next item's start, and the last one falls back to its stated duration.
 */
export function flattenDays(days: ExportDay[]): TimedItem[] {
  const items: TimedItem[] = [];
  for (const day of days) {
    for (const item of day.items) {
      items.push({
        ...item,
        dayDate: day.date,
        startAt: momentAt(item.date, item.start),
        endAt: momentAt(item.date, item.start),
        key: `${item.date}|${item.start}|${item.item_id}`,
      });
    }
  }
  items.sort((left, right) => +left.startAt - +right.startAt);
  items.forEach((item, index) => {
    const stated = item.end ? momentAt(item.date, item.end) : null;
    if (stated && +stated >= +item.startAt) {
      item.endAt = stated;
    } else if (stated) {
      // Earlier than its own start means the clock passed midnight inside this item.
      item.endAt = new Date(+stated + 864e5);
    } else {
      const following = items[index + 1];
      item.endAt = following
        ? following.startAt
        : new Date(+item.startAt + Math.max(1, item.duration_minutes) * 6e4);
    }
  });
  return items;
}

/** The item happening at `moment`, if any. A gap between two items is not an item. */
export function liveItem(items: TimedItem[], moment: Date): TimedItem | undefined {
  return items.find((item) => moment >= item.startAt && moment < item.endAt);
}

/** The first item still ahead of `moment`. */
export function nextItem(items: TimedItem[], moment: Date): TimedItem | undefined {
  return items.find((item) => item.startAt > moment);
}

/**
 * The index the clock is "at": the last item to have started, or 0 before the trip.
 *
 * Stepping is by stop rather than by minute, because a trip is thousands of minutes wide
 * and every moment worth landing on is one the plan actually describes.
 */
export function indexAt(items: TimedItem[], moment: Date): number {
  const ahead = items.findIndex((item) => item.startAt > moment);
  if (ahead === -1) return Math.max(0, items.length - 1);
  return Math.max(0, ahead - 1);
}

/** How far through its own span `moment` is, 0..100. Outside the span it clamps. */
export function progressPercent(item: TimedItem, moment: Date): number {
  const span = +item.endAt - +item.startAt;
  if (span <= 0) return 0;
  return Math.min(100, Math.max(0, ((+moment - +item.startAt) / span) * 100));
}

/** The gap to a future moment, as the pieces a copy string needs. */
export function gapParts(milliseconds: number):
  | { unit: "now" }
  | { unit: "minutes"; minutes: number }
  | { unit: "hours"; hours: number; minutes: number }
  | { unit: "days"; days: number } {
  const minutes = Math.round(milliseconds / 6e4);
  if (minutes < 1) return { unit: "now" };
  if (minutes < 60) return { unit: "minutes", minutes };
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return { unit: "hours", hours, minutes: minutes % 60 };
  return { unit: "days", days: Math.round(hours / 24) };
}

/** A gap as words, in the reader's language. The pieces come from `gapParts`. */
export function gapText(milliseconds: number, language: Language): string {
  const parts = gapParts(milliseconds);
  switch (parts.unit) {
    case "now":
      return copy("gap_now", language);
    case "minutes":
      return copyFormat("gap_minutes", language, { n: parts.minutes });
    case "hours":
      return parts.minutes
        ? copyFormat("gap_hours", language, { h: parts.hours, m: parts.minutes })
        : copyFormat("gap_hours_only", language, { h: parts.hours });
    case "days":
      return copyFormat("gap_days", language, { n: parts.days });
  }
}

/** A span as words: minutes under an hour, then hours and minutes. */
export function durationText(from: Date, to: Date, language: Language): string {
  const minutes = Math.max(0, Math.round((+to - +from) / 6e4));
  if (minutes < 60) return `${minutes} ${copy("minutes", language)}`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest
    ? copyFormat("dur_hours", language, { h: hours, m: rest })
    : copyFormat("dur_hours_only", language, { h: hours });
}
