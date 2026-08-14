/* eslint-disable react-refresh/only-export-components */
import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { Navigate } from "react-router";

import { rpc, type Journey, type Trip } from "./api/client";
import { copy } from "./i18n/copy";
import { useLanguage } from "./i18n/LanguageProvider";
import { AppShell } from "./shared/AppShell";
import { Recovery, RouteError } from "./shared/Recovery";
import { StageGate } from "./shared/StageGate";
import { STAGE_GATE, STAGE_ROUTES, type StageRoute } from "./shared/stages";
import { TripsPage } from "./stages/TripsPage";

function Loading() {
  const { language } = useLanguage();
  return <p>{copy("loading", language)}</p>;
}

function Landing() {
  const { language } = useLanguage();
  const landing = useQuery({
    queryKey: ["landing"],
    queryFn: async () => {
      const trips = await rpc<Trip[]>("list_trips");
      const recent = [...trips].sort((left, right) => right.created_at.localeCompare(left.created_at))[0];
      if (!recent) return "/trips";
      const journey = await rpc<Journey>("journey", { trip_id: recent.trip_id });
      return `/trips/${recent.trip_id}/${journey.next}`;
    },
  });
  if (landing.isPending) return <p>{copy("loading", language)}</p>;
  if (landing.isError) return <p>⚠ {landing.error.message}</p>;
  return <Navigate replace to={landing.data} />;
}

/**
 * The nine stage screens, each its own chunk.
 *
 * They used to be nine static imports, so the build was one 636 KB module and
 * every route paid for all nine — the map, the optimizer screen, the split ledger
 * and the workbook views included — before the first one could paint. A stage is
 * a natural split point: the IA is a sequence and nobody is on two of them at
 * once. `TripsPage` stays eager because it is the landing screen, so lazy-loading
 * it would only add a round trip to the one route that has nothing to wait for.
 */
const PAGES: Record<StageRoute, React.LazyExoticComponent<() => React.ReactNode>> = {
  setup: lazy(() => import("./stages/SetupPage").then((m) => ({ default: m.SetupPage }))),
  places: lazy(() => import("./stages/PlacesPage").then((m) => ({ default: m.PlacesPage }))),
  evidence: lazy(() => import("./stages/EvidencePage").then((m) => ({ default: m.EvidencePage }))),
  optimize: lazy(() => import("./stages/OptimizePage").then((m) => ({ default: m.OptimizePage }))),
  itinerary: lazy(() => import("./stages/ItineraryPage").then((m) => ({ default: m.ItineraryPage }))),
  readiness: lazy(() => import("./stages/ReadinessPage").then((m) => ({ default: m.ReadinessPage }))),
  costs: lazy(() => import("./stages/CostsPage").then((m) => ({ default: m.CostsPage }))),
  split: lazy(() => import("./stages/SplitPage").then((m) => ({ default: m.SplitPage }))),
  revise: lazy(() => import("./stages/RevisePage").then((m) => ({ default: m.RevisePage }))),
};

// The table is data; `main.tsx` builds the router from it. That split is what
// lets the entry-point smoke test assert the nine routes and five gate keys
// without a DOM: `createBrowserRouter` reads `window.history` at construction,
// Vitest runs in the node environment, and adding jsdom to check a nine-row
// array would be the wrong trade.
//
// The children are generated from `shared/stages.ts` rather than written out, so
// the gate a route waits on and the state the sidebar reports for it are the same
// fact rather than two literals that agree until one is edited.
/** The catch-all. A component rather than an inline element so it reads the language
 *  the same way every other screen does. */
function Recovery404() {
  const { language } = useLanguage();
  return (
    <Recovery
      body={copy("not_found_body", language)}
      title={copy("not_found_title", language)}
    />
  );
}

export const routes = [
  { path: "/", element: <Landing />, errorElement: <RouteError /> },
  { path: "/trips", element: <TripsPage />, errorElement: <RouteError /> },
  // A mistyped address or a stale bookmark used to reach React Router's own development
  // error page — "Unexpected Application Error!" with no branding and nothing to press.
  { path: "*", element: <Recovery404 /> },
  {
    path: "/trips/:tripId",
    element: <AppShell />,
    errorElement: <RouteError />,
    children: STAGE_ROUTES.map((route) => {
      const Page = PAGES[route];
      const page = (
        <Suspense fallback={<Loading />}>
          <Page />
        </Suspense>
      );
      return {
        path: route,
        errorElement: <RouteError />,
        // Setup is the one ungated route: it is what every gate checks for.
        element: route === "setup" ? page : <StageGate stage={STAGE_GATE[route]}>{page}</StageGate>,
      };
    }),
  },
];
