import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { PlanProposal } from "../api/client";
import { LanguageProvider } from "../i18n/LanguageProvider";
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
});
