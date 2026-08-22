import { Clock3, Footprints, MapPinned, Sparkles } from "lucide-react";

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
