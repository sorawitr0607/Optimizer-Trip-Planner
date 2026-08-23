import { CalendarCheck, Clock3, Footprints, MapPinned, Sparkles } from "lucide-react";

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
