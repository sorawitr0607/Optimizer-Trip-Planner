import { describe, expect, it } from "vitest";

import type { ComfortRuleState, PlanVariant, Reconciliation } from "../api/client";
import { planDecisions } from "./planDecisions";

function unfitPlace(place_id: string, reason: string): Reconciliation {
  return {
    place_id,
    name: place_id,
    priority: "interested",
    status: "cannot_currently_fit",
    reason,
    consequence: "kept_in_unscheduled_shortlist",
  };
}

function variantWith(reconciliation: Reconciliation[]): PlanVariant {
  return {
    variant_id: "best_balance",
    status: "unavailable",
    metrics: {},
    warnings: [],
    reconciliation,
    days: [],
    stopped_at_limit: false,
    objective_improved_or_equal_to_greedy: true,
    validation: { valid: false },
  };
}

function rule(overrides: Partial<ComfortRuleState> = {}): ComfortRuleState {
  return {
    code: "LONG_TRANSFER_WALK",
    threshold: 45,
    measured: 61,
    exceeds: true,
    accepted_value: null,
    covered: false,
    ...overrides,
  };
}

describe("planDecisions", () => {
  it("finds nothing outstanding for a draft that fits", () => {
    const decisions = planDecisions(variantWith([]), [], new Set(), []);

    expect(decisions.outstanding).toEqual([]);
    expect(decisions.extraDays).toBe(0);
  });

  /**
   * The reported journey, in one answer.
   *
   * "It went through like build them again -> accept the criteria -> add the day -> add
   * the day." Every one of those conditions is visible in the first draft, so the list
   * has to come back whole rather than one item per rebuild.
   */
  it("reports every outstanding decision at once, in the order they must be applied", () => {
    const decisions = planDecisions(
      variantWith([
        unfitPlace("north", "NO_TIME_CAPACITY"),
        unfitPlace("bridge", "ROUTE_UNVERIFIED"),
      ]),
      [rule()],
      new Set(),
      [],
    );

    expect(decisions.outstanding).toEqual(["comfort", "routes", "days"]);
  });

  it("costs a day per place that will not fit, rounded up", () => {
    // Two places at 90 + 30 each is 240 minutes against a 420-minute day: one day.
    const one = planDecisions(
      variantWith([
        unfitPlace("a", "NO_TIME_CAPACITY"),
        unfitPlace("b", "NO_TIME_CAPACITY"),
      ]),
      [], new Set(), [],
    );
    expect(one.extraDays).toBe(1);

    // Four of them is 480, which does not fit in one day however it is arranged.
    const two = planDecisions(
      variantWith(["a", "b", "c", "d"].map((id) => unfitPlace(id, "NO_TIME_CAPACITY"))),
      [], new Set(), [],
    );
    expect(two.extraDays).toBe(2);
  });

  it("uses each place's own visit length when the snapshot states one", () => {
    const decisions = planDecisions(
      variantWith([unfitPlace("all_day", "NO_TIME_CAPACITY")]),
      [], new Set(),
      [{ id: "all_day", duration_bounds: { ideal_minutes: 400 } }],
    );

    // 400 + 30 turnaround is over one 420-minute day.
    expect(decisions.extraDays).toBe(2);
  });

  it("leaves out a comfort figure the owner has unticked", () => {
    const decisions = planDecisions(
      variantWith([]),
      [rule({ code: "LONG_TRANSFER_WALK" }), rule({ code: "DAILY_WALKING_BUDGET" })],
      new Set(["DAILY_WALKING_BUDGET"]),
      [],
    );

    expect(decisions.selectedComfort.map((item) => item.code)).toEqual([
      "LONG_TRANSFER_WALK",
    ]);
    expect(decisions.outstanding).toEqual(["comfort"]);
  });

  it("leaves out a figure an existing acceptance already covers", () => {
    // `covered` is the server saying consent already reaches this measurement, so asking
    // again would be asking the owner to agree to something they have agreed to.
    const decisions = planDecisions(
      variantWith([]), [rule({ covered: true })], new Set(), [],
    );

    expect(decisions.outstanding).toEqual([]);
  });

  it("ignores a rule with no measurement behind it", () => {
    // A threshold that exists is not a threshold that was exceeded — the distinction
    // `_skip_reason` was corrected for on the server side.
    const decisions = planDecisions(
      variantWith([]), [rule({ measured: null })], new Set(), [],
    );

    expect(decisions.outstanding).toEqual([]);
  });

  it("does not read a place that was scheduled as one that did not fit", () => {
    const scheduled: Reconciliation = {
      place_id: "fits",
      name: "fits",
      priority: "must_do",
      status: "fits",
      reason: "SCHEDULED",
      consequence: "scheduled_once",
    };
    const decisions = planDecisions(variantWith([scheduled]), [], new Set(), []);

    expect(decisions.unfit).toEqual([]);
    expect(decisions.outstanding).toEqual([]);
  });

  it("recommends dropping a place no day could hold, and never offers it a day", () => {
    // `NO_DAY_LONG_ENOUGH` is the optimizer's answer to "could this fit an *empty*
    // day", so no added day can change it and the offer would be an endless loop.
    const decisions = planDecisions(
      variantWith([unfitPlace("giant", "NO_DAY_LONG_ENOUGH")]),
      [], new Set(), [],
    );

    expect(decisions.impossible.map((item) => item.place_id)).toEqual(["giant"]);
    expect(decisions.needsDays).toEqual([]);
    expect(decisions.extraDays).toBe(0);
    expect(decisions.outstanding).toEqual([]);
  });

  it("offers a day for a capacity refusal the first time", () => {
    const decisions = planDecisions(
      variantWith([unfitPlace("museum", "NO_TIME_CAPACITY")]),
      [], new Set(), [], new Set(),
    );

    expect(decisions.needsDays.map((item) => item.place_id)).toEqual(["museum"]);
    expect(decisions.impossible).toEqual([]);
    expect(decisions.outstanding).toEqual(["days"]);
  });

  it("stops offering a day once one was added and the place still did not fit", () => {
    // Reported as "after you try to add the day but it still have some place that still
    // can't fit". The optimizer cannot prove this one — it really is short of capacity —
    // so the fact that the owner already tried is the only thing that knows better.
    const decisions = planDecisions(
      variantWith([unfitPlace("museum", "NO_TIME_CAPACITY")]),
      [], new Set(), [], new Set(["museum"]),
    );

    expect(decisions.needsDays).toEqual([]);
    expect(decisions.impossible.map((item) => item.place_id)).toEqual(["museum"]);
    expect(decisions.extraDays).toBe(0);
    expect(decisions.outstanding).toEqual([]);
  });

  it("keeps offering a day for a place that has not had one", () => {
    // The memory is per place, not per trip: one place having been tried must not
    // withdraw the offer from another that has not.
    const decisions = planDecisions(
      variantWith([
        unfitPlace("tried", "NO_TIME_CAPACITY"),
        unfitPlace("fresh", "NO_TIME_CAPACITY"),
      ]),
      [], new Set(), [], new Set(["tried"]),
    );

    expect(decisions.needsDays.map((item) => item.place_id)).toEqual(["fresh"]);
    expect(decisions.impossible.map((item) => item.place_id)).toEqual(["tried"]);
    // And the day it asks for is sized for the one place still being offered one.
    expect(decisions.extraDays).toBe(1);
    expect(decisions.outstanding).toEqual(["days"]);
  });

  it("answers for a draft that does not exist yet", () => {
    expect(planDecisions(undefined, [], new Set(), undefined).outstanding).toEqual([]);
  });
});
