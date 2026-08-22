import { describe, expect, it } from "vitest";

import type { ExportDay } from "../api/client";
import { flattenDays, gapParts, indexAt, liveItem, nextItem, progressPercent } from "./tripClock";

/** Two days, the second of which runs past midnight. */
const DAYS = [
  {
    date: "2026-10-10",
    start: "09:00",
    end: "12:00",
    items: [
      { order: 1, item_id: "a", type: "visit", subject_id: "s1", date: "2026-10-10",
        start: "09:00", end: "10:30", duration_minutes: 90, status: "ready" },
      // No end stated: it borrows the next item's start.
      { order: 2, item_id: "b", type: "travel", subject_id: "s2", date: "2026-10-10",
        start: "10:30", end: "", duration_minutes: 30, status: "ready" },
      { order: 3, item_id: "c", type: "visit", subject_id: "s3", date: "2026-10-10",
        start: "11:00", end: "12:00", duration_minutes: 60, status: "ready" },
    ],
    stops: [], fallbacks: [], totals: {}, highest_risk: null,
  },
  {
    date: "2026-10-11",
    start: "23:00",
    end: "00:30",
    items: [
      // Ends before it starts, which means the clock passed midnight inside it.
      { order: 1, item_id: "d", type: "visit", subject_id: "s4", date: "2026-10-11",
        start: "23:00", end: "00:30", duration_minutes: 90, status: "ready" },
    ],
    stops: [], fallbacks: [], totals: {}, highest_risk: null,
  },
] as unknown as ExportDay[];

describe("flattenDays", () => {
  it("orders every day's items into one sequence", () => {
    expect(flattenDays(DAYS).map((item) => item.item_id)).toEqual(["a", "b", "c", "d"]);
  });

  it("borrows the next start for an item that states no end", () => {
    const borrowed = flattenDays(DAYS).find((item) => item.item_id === "b")!;
    expect(borrowed.endAt.getHours()).toBe(11);
    expect(borrowed.endAt.getMinutes()).toBe(0);
  });

  it("carries an item that ends after midnight into the next day", () => {
    const overnight = flattenDays(DAYS).find((item) => item.item_id === "d")!;
    // 00:30 on the 12th, not 00:30 on the 11th -- which would end 22.5 hours before
    // it began and render as a negative span.
    expect(overnight.endAt.getDate()).toBe(12);
    expect(+overnight.endAt).toBeGreaterThan(+overnight.startAt);
  });

  it("keeps the day it was listed under, which is not always its own date", () => {
    const items = flattenDays(DAYS);
    expect(items.map((item) => item.dayDate)).toEqual([
      "2026-10-10", "2026-10-10", "2026-10-10", "2026-10-11",
    ]);
  });
});

describe("where the clock is", () => {
  const items = flattenDays(DAYS);

  it("finds the item in progress and the one after it", () => {
    const moment = new Date(2026, 9, 10, 9, 45);
    expect(liveItem(items, moment)?.item_id).toBe("a");
    expect(nextItem(items, moment)?.item_id).toBe("b");
  });

  it("reports no live item inside a gap but still names what is next", () => {
    // Nothing spans 12:00-23:00, so this is a gap rather than an item.
    const moment = new Date(2026, 9, 10, 18, 0);
    expect(liveItem(items, moment)).toBeUndefined();
    expect(nextItem(items, moment)?.item_id).toBe("d");
  });

  it("indexes to the last item that has started", () => {
    expect(indexAt(items, new Date(2026, 9, 10, 8, 0))).toBe(0);
    expect(indexAt(items, new Date(2026, 9, 10, 10, 45))).toBe(1);
    expect(indexAt(items, new Date(2026, 9, 20, 0, 0))).toBe(3);
  });

  it("measures progress through the live item and clamps outside it", () => {
    const first = items[0];
    expect(progressPercent(first, new Date(2026, 9, 10, 9, 45))).toBe(50);
    expect(progressPercent(first, new Date(2026, 9, 10, 8, 0))).toBe(0);
    expect(progressPercent(first, new Date(2026, 9, 10, 23, 0))).toBe(100);
  });
});

describe("gapParts", () => {
  it("splits a gap into the pieces a copy string needs", () => {
    // Under half a minute rounds to zero and reads as "now"; 30s rounds up to 1.
    expect(gapParts(20_000)).toEqual({ unit: "now" });
    expect(gapParts(30_000)).toEqual({ unit: "minutes", minutes: 1 });
    expect(gapParts(20 * 6e4)).toEqual({ unit: "minutes", minutes: 20 });
    expect(gapParts(150 * 6e4)).toEqual({ unit: "hours", hours: 2, minutes: 30 });
    expect(gapParts(120 * 6e4)).toEqual({ unit: "hours", hours: 2, minutes: 0 });
    expect(gapParts(3 * 24 * 60 * 6e4)).toEqual({ unit: "days", days: 3 });
  });
});
