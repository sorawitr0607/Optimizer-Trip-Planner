import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { PlanProposal } from "../api/client";
import { LanguageProvider } from "../i18n/LanguageProvider";
import { daysInMonth, spanDays } from "../shared/dates";
import { StayPlanner } from "./StayPlanner";

/**
 * The way out of a trip with no dates. Without them the optimizer returns a stay
 * recommendation instead of a timetable, and that was a dead end — reported as
 * "without time date I can not go on into itinerary".
 */

const PROPOSAL = {
  mode: "stay_recommendation",
  stay_recommendations: [
    { id: "minimum", days: 3, daily_capacity_minutes: 540 },
    { id: "balanced", days: 5, daily_capacity_minutes: 420 },
    { id: "relaxed", days: 7, daily_capacity_minutes: 330 },
  ],
} satisfies PlanProposal;

function render(today: Date): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["setup", "trip_1"], null);
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <LanguageProvider initial="en">
        <StayPlanner language="en" proposal={PROPOSAL} today={today} tripId="trip_1" />
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

describe("StayPlanner", () => {
  it("offers all three paces with their length and daily capacity", () => {
    const html = render(new Date("2026-08-07T00:00:00"));

    expect(html).toContain("3 days");
    expect(html).toContain("5 days");
    expect(html).toContain("7 days");
    // 420 minutes is 7 hours, and the owner reads hours, not the optimizer's minutes.
    expect(html).toContain("about 7 h of visiting a day");
    // Balanced is preselected: the middle option is the one to argue with.
    expect(html).toMatch(/class="stay-pace active"[^>]*>?[\s\S]{0,80}Balanced/);
  });

  it("derives an end date from the chosen pace, inclusive of the first day", () => {
    // Default month is two ahead of today, so October from an August start, and the
    // balanced five-day pace runs the 1st to the 5th — not the 6th.
    const html = render(new Date("2026-08-07T00:00:00"));

    expect(html).toContain("2026-10-01");
    expect(html).toContain("2026-10-05");
  });

  it("rolls a month that has already passed into next year", () => {
    // Chosen from December, the default month is February — which this year is behind
    // us, so offering it would be offering a date in the past.
    const html = render(new Date("2026-12-20T00:00:00"));

    expect(html).toContain("2027-02-01");
  });

  it("says the dates are provisional and that discovery has to run again", () => {
    // Changing setup changes its hash, so any discovery already run is stale. Saying so
    // beats letting the next stage refuse with a code.
    const html = render(new Date("2026-08-07T00:00:00"));

    expect(html).toContain("provisional dates");
    expect(html).toContain("Use these dates");
  });

  it("offers late-month and Saturday ranges beside the early and mid ones", () => {
    // October 2026 begins on a Thursday, so the first Saturday is the 3rd; the balanced
    // five-day pace ends on the 31st when it is placed to finish the month, so late
    // starts on the 27th.
    const html = render(new Date("2026-08-07T00:00:00"));

    expect(html).toContain("Early month");
    expect(html).toContain("Mid month");
    expect(html).toContain("Late month");
    expect(html).toContain("2026-10-27");
    expect(html).toContain("Starts on a Saturday");
    expect(html).toContain("2026-10-03");
  });

  it("never runs the late-month range past the end of the month", () => {
    // The whole reason late is anchored to the *end*: a fixed 22nd start plus a seven
    // day pace would spill into November and stop being "late October".
    const html = render(new Date("2026-08-07T00:00:00"));
    const late = html.match(/Late month[\s\S]{0,120}?(\d{4}-\d{2}-\d{2})[^\d]+(\d{4}-\d{2}-\d{2})/);

    expect(late).not.toBeNull();
    expect(late![2].slice(0, 7)).toBe("2026-10");
  });

  it("shows how much of the pace a range uses, and offers a custom one", () => {
    const html = render(new Date("2026-08-07T00:00:00"));

    expect(html).toContain("Pick your own");
    // Collapsed until asked for, so the default screen is not four date inputs.
    expect(html).toContain('aria-expanded="false"');
  });
});

/**
 * The arithmetic behind the custom range, tested directly.
 *
 * The cap is "no longer than the pace the owner chose", and the pace is a count of
 * days — so the whole rule rests on counting a start..end pair the same way the pace
 * counts. Off by one here and a 5-day pace either refuses its own recommended range or
 * silently allows six.
 */
describe("date arithmetic", () => {
  it("counts both ends of a range, like the pace does", () => {
    // The balanced pace is 5 days and its own recommended range is the 1st to the 5th.
    expect(spanDays("2026-10-01", "2026-10-05")).toBe(5);
    expect(spanDays("2026-10-01", "2026-10-01")).toBe(1);
  });

  it("counts across a month and a year boundary", () => {
    expect(spanDays("2026-10-30", "2026-11-02")).toBe(4);
    expect(spanDays("2026-12-30", "2027-01-02")).toBe(4);
  });

  it("returns nothing usable when the end is before the start", () => {
    // Drives `endsBeforeStart`, which disables the save rather than sending a
    // backwards range to `save_setup`.
    expect(spanDays("2026-10-05", "2026-10-01")).toBeLessThanOrEqual(0);
  });

  it("knows the length of a month, including February in a leap year", () => {
    expect(daysInMonth(2026, 10)).toBe(31);
    expect(daysInMonth(2026, 2)).toBe(28);
    expect(daysInMonth(2028, 2)).toBe(29);
  });
});
