import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { PlanProposal } from "../api/client";
import { LanguageProvider } from "../i18n/LanguageProvider";
import { copy } from "../i18n/copy";
import { PLAN_STAGES } from "../shared/buildStages";
import { BuildStages } from "./BuildStages";
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

function render(today: Date, proposal: PlanProposal = PROPOSAL): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["setup", "trip_1"], null);
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <LanguageProvider initial="en">
        <StayPlanner language="en" proposal={proposal} today={today} tripId="trip_1" />
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

  it("still offers a date range when the optimizer recommended no pace", () => {
    /**
     * **`/optimize` renders this component for every dateless trip**, and it used to
     * `return null` on an empty recommendation list — so a trip the optimizer could not
     * pace put a *blank page* behind "Build the plan". That is the dead-air screen the
     * owner reported, and returning nothing is never the answer: a screen that cannot
     * recommend must still let the decision be made.
     *
     * Every `chosen`-derived value is guarded, and an `allowedDays` of 0 disables the
     * span cap rather than failing it, so the custom range is a complete answer on its
     * own — the owner types two dates and the plan builds.
     */
    const html = render(new Date("2026-08-07T00:00:00"), {
      mode: "stay_recommendation",
      stay_recommendations: [],
    } satisfies PlanProposal);

    expect(html).not.toBe("");
    // The date inputs are present and usable...
    expect(html).toContain('type="date"');
    // ...the custom range is open, since there is nothing to pick instead...
    expect(html).toContain("stay-window-card active");
    // ...and the pace heading is not left standing over an empty group.
    expect(html).toContain('hidden=""');
    expect(html).not.toContain("⚠");
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

/**
 * The build reports which of its four calls it is on.
 *
 * It used to show one rotating line for a press that writes the dates, rebuilds
 * discovery, collects route evidence and runs a full three-variant proposal — so a slow
 * discovery and a slow proposal looked identical, and both looked like a hang. Same rule
 * as `/optimize`: a stage is ticked when its call returns, never on a timer.
 */
describe("StayPlanner build progress", () => {
  it("names the four calls the press actually makes", () => {
    const html = render(new Date("2026-08-07T00:00:00"));

    // Not visible until the build runs, but the stage vocabulary must resolve —
    // a missing key renders as a visible ⚠ CODE rather than as copy.
    expect(copy("stage_dates", "en")).toBe("Your dates");
    expect(copy("stage_discovery", "en")).toBe("Places for those dates");
    expect(copy("stage_routes", "en")).not.toContain("⚠");
    expect(copy("stage_plan", "en")).toBe("Three plan options");
    expect(html).not.toContain("⚠");
  });

  it("has one stage per awaited call, and no more", () => {
    // Four `await`s in the mutation: save_setup, discover_places,
    // collectRouteEvidence, generate_plan_preview. A fifth stage would be a claim about
    // work that is not happening — which is the defect this whole pattern exists to
    // avoid. It was three, and the missing one was `routes`: this path built a plan
    // without measuring a single leg, so every place came back `ROUTE_UNVERIFIED` and
    // the owner was told "the route and travel time are not verified". The count went up
    // because the *call* went in, which is the only reason it ever may.
    expect(PLAN_STAGES).toHaveLength(4);
    expect(PLAN_STAGES.map((stage) => stage.key)).toEqual([
      "dates", "discovery", "routes", "plan",
    ]);
    for (const stage of PLAN_STAGES) {
      expect(copy(`stage_${stage.key}`, "en")).not.toContain("⚠");
      expect(copy(`stage_${stage.key}_detail`, "en")).not.toContain("⚠");
      expect(copy(`stage_${stage.key}`, "th")).not.toContain("⚠");
      expect(copy(`stage_${stage.key}_detail`, "th")).not.toContain("⚠");
    }
  });
});

describe("the build checklist itself", () => {
  function stages(reached: number): string {
    return renderToStaticMarkup(
      <LanguageProvider initial="en">
        <BuildStages language="en" reached={reached} stages={PLAN_STAGES} />
      </LanguageProvider>,
    );
  }

  it("draws one row per call plus the completion row", () => {
    const html = stages(0);

    expect(html.match(/class="build-stage[ "]/g) ?? []).toHaveLength(PLAN_STAGES.length + 1);
    expect(html).toContain("Your dates");
    expect(html).toContain("Places for those dates");
    expect(html).toContain("Three plan options");
    expect(html).toContain("Your plan is ready");
    expect(html).toContain("Usually 2–10 sec");
    expect(html).toContain("Overall progress · 0%");
    expect(html).toContain("<progress");
  });

  it("marks exactly the calls that have returned", () => {
    // One returned: the first is done, the second is the one in flight.
    const html = stages(1);

    expect(html.match(/build-stage done/g) ?? []).toHaveLength(1);
    expect(html.match(/build-stage active/g) ?? []).toHaveLength(1);
  });

  it("stops claiming work once every call has returned", () => {
    const html = stages(PLAN_STAGES.length);

    expect(html).toContain('aria-busy="false"');
    expect(html.match(/build-stage active/g) ?? []).toHaveLength(0);
    expect(html).toContain("Overall progress · 100%");
  });
});
