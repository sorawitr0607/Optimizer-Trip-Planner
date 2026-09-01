import {
  CalendarCheck,
  Clock3,
  Footprints,
  Landmark,
  ListChecks,
  MapPinned,
  Save,
  Scale,
  Search,
  Sparkles,
  Wind,
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
  { key: "timezone", icon: Clock3, estimateSeconds: [5, 15] },
  { key: "hours", icon: MapPinned, estimateSeconds: [2, 10] },
  { key: "routes", icon: Footprints, estimateSeconds: [15, 90] },
  { key: "variants", icon: Sparkles, estimateSeconds: [45, 120] },
] as const;

/**
 * The four calls `StayPlanner`'s "use these dates" awaits, in order.
 *
 * Same idea as `BUILD_STAGES` and the same rule: a stage is marked done when its
 * call returns, never on a timer. This path is the longest wait in the app — it
 * writes the dates, rebuilds discovery against the new setup hash, collects route
 * evidence, and then runs a full three-variant proposal — and it was showing only
 * `Thinking`: one rotating line, which cannot say which of
 * them it is on. A wait that reports nothing is the same silence that had
 * `/optimize` reported as broken before `BUILD_STAGES` existed.
 *
 * **`routes` was missing, and so was the call.** This path went dates → discovery →
 * proposal, with nothing measuring a single leg, so every place came back
 * `ROUTE_UNVERIFIED` and the plan said "the route and travel time are not verified" —
 * reported by the owner twice, once against a worker with no credentials and once
 * against this. `/optimize`'s own build has always collected routes first; the two
 * build paths simply did different work under the same promise. The stage is added
 * because the *call* is added: a stage no `await` corresponds to would be the exact
 * fiction `BuildStages` exists to refuse.
 */
export const PLAN_STAGES = [
  { key: "dates", icon: CalendarCheck, estimateSeconds: [2, 10] },
  { key: "discovery", icon: MapPinned, estimateSeconds: [5, 90] },
  { key: "routes", icon: Footprints, estimateSeconds: [15, 90] },
  { key: "plan", icon: Sparkles, estimateSeconds: [45, 120] },
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
  { key: "place_lookup", icon: Search, estimateSeconds: [5, 15] },
  { key: "place_landmarks", icon: Landmark, estimateSeconds: [10, 25] },
  { key: "place_baseline", icon: MapPinned, estimateSeconds: [20, 60] },
  { key: "place_catalogue", icon: ListChecks, estimateSeconds: [3, 10] },
  { key: "place_ranking", icon: Sparkles, estimateSeconds: [2, 10] },
] as const;

/** How many of `PLACES_STAGES` the worker reports; the rest is the page's own wait. */
export const PLACES_WORKER_STAGES = 4;

/**
 * What one `generate_plan_preview` does, in the order it does it.
 *
 * Three variants at roughly 21s each and then a write — the longest single call in
 * the app. `/optimize`'s auto-resolve could always describe its own wait because it
 * drives four calls itself, but the plain build and the paid build are *one* call,
 * so they showed a rotating line for the better part of a minute and had nothing
 * else they could honestly show. Now the optimizer says which variant it has
 * finished, the worker writes the count down, and this is the list that reads it.
 *
 * A trip with no dates gets a stay recommendation instead of variants and so arrives
 * at the last row without passing through the first three, which is what happened.
 */
export const PREVIEW_STAGES = [
  { key: "variant_balanced", icon: Scale, estimateSeconds: [10, 35] },
  { key: "variant_relaxed", icon: Wind, estimateSeconds: [10, 35] },
  { key: "variant_highlights", icon: Sparkles, estimateSeconds: [10, 35] },
  { key: "preview_saved", icon: Save, estimateSeconds: [1, 5] },
] as const;
