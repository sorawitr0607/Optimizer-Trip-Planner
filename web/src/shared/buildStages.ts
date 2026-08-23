import {
  CalendarCheck,
  Clock3,
  Footprints,
  Landmark,
  ListChecks,
  MapPinned,
  Search,
  Sparkles,
} from "lucide-react";

/**
 * The four calls `autoResolveAndGenerate` awaits, in the order it awaits them.
 *
 * Data rather than a component, so `OptimizePage` can read the count without importing a
 * component file — the lint rule that forbids mixed exports is the same one
 * `shared/cards.ts` exists for.
 *
 * This is the honest list. `Thinking` says in its own comment that "the server reports no
 * milestones, so this claims none", which was true of the server and never of the client:
 * the page drives these four itself, so each one returning is a fact it already holds.
 */
export const BUILD_STAGES = [
  { key: "timezone", icon: Clock3 },
  { key: "hours", icon: MapPinned },
  { key: "routes", icon: Footprints },
  { key: "variants", icon: Sparkles },
] as const;

/**
 * The three calls `StayPlanner`'s "use these dates" awaits, in order.
 *
 * Same idea as `BUILD_STAGES` and the same rule: a stage is marked done when its
 * call returns, never on a timer. This path is the longest wait in the app — it
 * writes the dates, rebuilds discovery against the new setup hash, and then runs
 * a full three-variant proposal at roughly 52s — and it was showing only
 * `Thinking`: one rotating line and an elapsed counter, which cannot say which of
 * the three it is on. A wait that reports nothing is the same silence that had
 * `/optimize` reported as broken before `BUILD_STAGES` existed.
 */
export const PLAN_STAGES = [
  { key: "dates", icon: CalendarCheck },
  { key: "discovery", icon: MapPinned },
  { key: "plan", icon: Sparkles },
] as const;

/**
 * What `/places` waits through, in the order it happens.
 *
 * The first four are the worker's, not the page's. Discovery is one queued job, so
 * unlike the two lists above this screen cannot see its own milestones -- it holds a
 * job id and a poll. The job row now carries a count of stages that have returned and
 * `rpc`'s `onProgress` hands it over, which is what made an honest list possible here:
 * the alternative was timed stages, and inventing those is the exact thing
 * `BuildStages` was built to refuse.
 *
 * The fifth is the page's own. `discover_places` returning is not the end of the wait
 * -- the ranking and the first card follow it, and `busy` on this screen has always
 * covered both -- so a list that stopped at four would hand back a finished checklist
 * and keep spinning.
 *
 * Nothing arrives on the local server, which runs discovery inline and answers the
 * request. There the page shows `Thinking`, as it always has.
 */
export const PLACES_STAGES = [
  { key: "place_lookup", icon: Search },
  { key: "place_landmarks", icon: Landmark },
  { key: "place_baseline", icon: MapPinned },
  { key: "place_catalogue", icon: ListChecks },
  { key: "place_ranking", icon: Sparkles },
] as const;

/** How many of `PLACES_STAGES` the worker reports; the rest is the page's own wait. */
export const PLACES_WORKER_STAGES = 4;
