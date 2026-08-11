import type { Journey, StageKey } from "../api/client";

/**
 * The nine stage routes and the five gate keys they resolve to.
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
  evidence: "evidence",
  optimize: "optimize",
  itinerary: "itinerary",
  readiness: "setup",
  costs: "setup",
  split: "setup",
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
  if (journey.next === route) return { state: "next", blockedBy: null };
  // Only the five gate keys report `done`. The other four are always revisitable
  // and claim nothing, which is honest: nothing measures when costs are finished.
  const own = journey.stages.find((stage) => stage.key === route);
  if (own?.done) return { state: "complete", blockedBy: null };
  return { state: "available", blockedBy: null };
}
