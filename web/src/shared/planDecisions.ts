import type { ComfortRuleState, PlanVariant, Reconciliation } from "../api/client";

/**
 * What a draft plan is still waiting for, derived once.
 *
 * The reported journey through `/optimize` was "build them again -> accept the criteria
 * -> add the day -> add the day". Each of those conditions had its own control, each
 * control wrote its own change and then rebuilt, and the *next* condition only appeared
 * once the last rebuild had finished. Four builds to answer four questions that were all
 * already answerable from the first draft.
 *
 * They were also derived in three different places at three different depths of the
 * component, which is how a button and the sentence beside it come to disagree about the
 * same plan. So this is the one derivation, and `OptimizePage` applies the whole list in
 * a single pass before building once.
 *
 * Pure on purpose: it reads the draft the server already returned and asks the owner
 * nothing new.
 */

/** One usable day, in minutes — the same figure the optimize screen has always used. */
const USABLE_DAY_MINUTES = 420;

/** What a place costs beyond its own visit: getting there, and turning around after. */
const TURNAROUND_MINUTES = 30;

/** A place's visit length when the snapshot does not state one. */
const ASSUMED_VISIT_MINUTES = 90;

export type PlanDecision = "comfort" | "routes" | "days";

export interface OptimizerCandidate {
  id?: string;
  duration_bounds?: { ideal_minutes?: number };
}

export interface PlanDecisions {
  /** Every chosen place the draft could not place. */
  unfit: Reconciliation[];
  /** Places no length of trip will hold, so the only way forward is to drop them.
   *
   *  Split out from `needsDays` because offering "add days" for these was an endless
   *  loop: the owner pressed it, the rebuild produced the same refusal with the same
   *  button, and nothing about the trip had changed that could help.
   *
   *  Two ways in. The optimizer *proves* one — `NO_DAY_LONG_ENOUGH`, its answer to
   *  "could this fit an empty day", which no added day can change. And experience
   *  supplies the other: a place still short of capacity **after days were already
   *  added for it** is one that adding days did not help, whatever can be proved. The
   *  second is why `alreadyTried` is a parameter rather than something derivable from
   *  the draft — the draft cannot know what was tried. */
  impossible: Reconciliation[];
  /** The comfort figures the owner has not agreed to and has not unticked. Returned
   *  rather than recomputed by the caller: `outstanding` already depends on it, and two
   *  filters over the same rules are how the button and the list come to disagree. */
  selectedComfort: ComfortRuleState[];
  /** At least one place has a leg nothing would measure. */
  needsRoutes: boolean;
  /** The places that fit nothing wrong — there are simply more of them than days. */
  needsDays: Reconciliation[];
  /** How much longer the trip has to be to hold them. At least one day when any are. */
  extraDays: number;
  /** The decisions to apply, in the order they must be applied. Empty means the draft
   *  needs nothing and the owner's next move is to confirm it. */
  outstanding: PlanDecision[];
}

export function planDecisions(
  variant: PlanVariant | undefined,
  comfortRules: ComfortRuleState[],
  excludedComfort: ReadonlySet<string>,
  candidates: OptimizerCandidate[] | undefined,
  /** Places the owner has already lengthened the trip for. See `shared/dayExtension`. */
  alreadyTried: ReadonlySet<string> = new Set(),
): PlanDecisions {
  const unfit = (variant?.reconciliation ?? []).filter(
    (item) => item.status === "cannot_currently_fit",
  );
  const needsRoutes = unfit.some((item) => item.reason === "ROUTE_UNVERIFIED");
  const shortOfTime = unfit.filter((item) => item.reason === "NO_TIME_CAPACITY");
  // Offered once per place: still short of capacity after days were added for it is a
  // place adding days did not help.
  const needsDays = shortOfTime.filter((item) => !alreadyTried.has(item.place_id));
  const impossible = [
    ...unfit.filter((item) => item.reason === "NO_DAY_LONG_ENOUGH"),
    ...shortOfTime.filter((item) => alreadyTried.has(item.place_id)),
  ];
  const extraMinutes = needsDays.reduce((sum, item) => {
    const candidate = candidates?.find((entry) => entry.id === item.place_id);
    return (
      sum +
      (candidate?.duration_bounds?.ideal_minutes ?? ASSUMED_VISIT_MINUTES) +
      TURNAROUND_MINUTES
    );
  }, 0);
  // A place that does not fit needs a day even when its visit rounds to nothing, so the
  // floor is one whenever there is anything to place at all — and zero when there is not,
  // because "add 1 day" beside a plan that fits is a control with nothing to do.
  const extraDays = needsDays.length
    ? Math.max(1, Math.ceil(extraMinutes / USABLE_DAY_MINUTES))
    : 0;
  // The measured figures the owner has not yet agreed to, minus any they have unticked.
  // `covered` is the server saying an existing acceptance already reaches this value.
  const selectedComfort = comfortRules.filter(
    (rule) =>
      rule.exceeds &&
      rule.measured !== null &&
      !rule.covered &&
      !excludedComfort.has(rule.code),
  );
  return {
    unfit,
    impossible,
    selectedComfort,
    needsRoutes,
    needsDays,
    extraDays,
    outstanding: [
      ...(selectedComfort.length ? (["comfort"] as const) : []),
      ...(needsRoutes ? (["routes"] as const) : []),
      ...(needsDays.length ? (["days"] as const) : []),
    ],
  };
}
