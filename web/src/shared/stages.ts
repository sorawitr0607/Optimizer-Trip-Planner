import type { Journey, StageKey } from "../api/client";

/**
 * The ten stage routes and the five gate keys they resolve to.
 *
 * This table used to exist twice: once as the literal `stage=` on each
 * `<StageGate>` in `routes.tsx`, and nowhere else — so the sidebar could not say
 * whether a stage was reachable without guessing, and it rendered nine equally
 * available links. A UX audit on 2026-08-10 found the consequence: an owner
 * learns a stage is blocked only by clicking it, and cannot see what is finished,
 * what is next, or what is waiting on something else.
 *
 * Putting the mapping here rather than deriving a second one in the shell is the
 * whole point. The nav and the gate now answer from the same predicate, so the
 * sidebar cannot promise a screen the gate then refuses — which is the failure
 * mode a second copy of this table would reintroduce on its first edit.
 */
export const STAGE_ROUTES = [
  "setup",
  "places",
  // Its own route at the owner's asking, 2026-08-14. It was a section under the deck on
  // `/places` and a card on `/evidence`, so the two halves of one question were never on
  // screen together. Ten routes now, not the nine artifact 028 decided.
  "stay",
  "evidence",
  "optimize",
  "itinerary",
  "readiness",
  "costs",
  "split",
  "revise",
] as const;

export type StageRoute = (typeof STAGE_ROUTES)[number];

/**
 * Artifact 028: nine routes, five gate keys. Several USE-section screens share
 * the `setup` gate because they need a confirmed setup and nothing more — and
 * `setup` itself is the one ungated route, since it is what every gate checks
 * for. It is listed anyway so the nav can report its own state.
 */
export const STAGE_GATE: Record<StageRoute, StageKey> = {
  setup: "setup",
  places: "places",
  // Locked until the owner presses "Build the plan" on `/places`, at their asking on
  // 2026-08-17: the workflow is places → stay → build the plan, and ranking neighbourhoods
  // against a shortlist that is still being swiped ranks them against the wrong shortlist.
  //
  // It borrows the `optimize` key rather than `places` because that key carries exactly
  // this predicate — `blocked_by: None if chosen else "places"`, where `chosen` means kept
  // *and* confirmed — while the `places` key is unblocked the moment setup is. Both
  // therefore unlock at the same moment, which is what makes the sidebar order the real
  // order. It deliberately does not wait on evidence: choosing a neighbourhood is what you
  // do *before* buying opening hours for the places in it.
  stay: "optimize",
  evidence: "evidence",
  optimize: "optimize",
  itinerary: "itinerary",
  // Both describe a plan: a readiness board is generated from one and the cost screen
  // counts what one commits you to. Gated on `setup` they were reachable — and empty —
  // before there was anything to be ready for or to pay for.
  readiness: "itinerary",
  costs: "itinerary",
  // Gated on an activated plan at the owner's request, 2026-08-14.
  //
  // **This reverses a recorded decision.** `WF-030`'s note in CLAUDE.md says `/split`
  // deliberately needs only a confirmed setup, because "bills get paid before an
  // itinerary is built" and a money file that refused until activation would be
  // unavailable for exactly the stretch of a trip when people are paying for things.
  // That reasoning still stands; the owner asked for the lock anyway. Reverting is this
  // one word back to `setup`.
  split: "itinerary",
  revise: "itinerary",
};

export type StageState = "complete" | "next" | "available" | "locked";

export interface StageStatus {
  state: StageState;
  /** The stage that has to happen first. Only set when `state` is `locked`. */
  blockedBy: StageKey | null;
}

/**
 * What the sidebar should say about one route.
 *
 * `locked` is read from the *gate's* stage rather than the route's own, because
 * that is exactly what `<StageGate>` tests — so a link marked locked is precisely
 * a link that will render the blocked explanation, and no other. `readiness`,
 * `costs` and `split` gate on `setup`, which never carries a `blocked_by`, so
 * they are never locked; that is the app's real behaviour and the nav now shows
 * it rather than implying a lock that is not there.
 */
export function stageStatus(journey: Journey | undefined, route: StageRoute): StageStatus {
  if (!journey) return { state: "available", blockedBy: null };
  const gate = journey.stages.find((stage) => stage.key === STAGE_GATE[route]);
  if (gate?.blocked_by) return { state: "locked", blockedBy: gate.blocked_by };
  // Only the five gate keys report `done`. The other four are always revisitable
  // and claim nothing, which is honest: nothing measures when costs are finished.
  const own = journey.stages.find((stage) => stage.key === route);
  // Done beats next. With every stage finished, `journey.next` falls back to
  // `itinerary` so that `/` still has somewhere to send a returning owner — but the
  // sidebar was reading that fallback as a *instruction* and kept a NEXT badge on a
  // screen with nothing left to do, which was reported as not knowing what to do next.
  if (own?.done) return { state: "complete", blockedBy: null };
  if (journey.next === route) return { state: "next", blockedBy: null };
  return { state: "available", blockedBy: null };
}
