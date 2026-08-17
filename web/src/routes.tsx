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
/** Sessions that have already reloaded once, so a genuine failure cannot loop. */
const RELOADED = "chunk-reload-attempted";

/**
 * `lazy`, plus the one recovery a code-split app owes an open tab.
 *
 * A build replaces every chunk's content hash and Vite empties `dist`, so the file the
 * *running* page was told to fetch no longer exists. A tab left open across a rebuild
 * therefore dies on its next navigation with `Failed to fetch dynamically imported
 * module: .../OptimizePage-D8dLZlyq.js` — reported from the owner's own browser — and
 * every screen it had already loaded keeps running the old code, which is worse: it looks
 * like the app, it answers like the app, and it is a build old enough to be missing
 * whatever was just fixed. That reads as "still not fixed" rather than as "stale tab",
 * and it cost several rounds of testing to recognise.
 *
 * A failed import is therefore treated as "this page is out of date" and the page is
 * reloaded, which fetches a fresh `index.html` — the server already sends that
 * `no-cache` — and with it the current chunk names. Once per session, recorded in
 * `sessionStorage`: if the second attempt fails too, the chunk is genuinely missing and
 * the error belongs on screen rather than in a reload loop.
 */
function lazyPage(load: () => Promise<{ default: () => React.ReactNode }>) {
  return lazy(() =>
    load().catch((error: unknown) => {
      if (sessionStorage.getItem(RELOADED)) throw error;
      sessionStorage.setItem(RELOADED, "1");
      window.location.reload();
      // Never resolves: the reload is already under way and rendering an error state
      // behind it would flash a failure the owner is about to leave anyway.
      return new Promise<{ default: () => React.ReactNode }>(() => {});
    }),
  );
}

const PAGES: Record<StageRoute, React.LazyExoticComponent<() => React.ReactNode>> = {
  setup: lazyPage(() => import("./stages/SetupPage").then((m) => ({ default: m.SetupPage }))),
  places: lazyPage(() => import("./stages/PlacesPage").then((m) => ({ default: m.PlacesPage }))),
  stay: lazyPage(() => import("./stages/StayPage").then((m) => ({ default: m.StayPage }))),
  evidence: lazyPage(() => import("./stages/EvidencePage").then((m) => ({ default: m.EvidencePage }))),
  optimize: lazyPage(() => import("./stages/OptimizePage").then((m) => ({ default: m.OptimizePage }))),
  itinerary: lazyPage(() => import("./stages/ItineraryPage").then((m) => ({ default: m.ItineraryPage }))),
  readiness: lazyPage(() => import("./stages/ReadinessPage").then((m) => ({ default: m.ReadinessPage }))),
  costs: lazyPage(() => import("./stages/CostsPage").then((m) => ({ default: m.CostsPage }))),
  split: lazyPage(() => import("./stages/SplitPage").then((m) => ({ default: m.SplitPage }))),
  revise: lazyPage(() => import("./stages/RevisePage").then((m) => ({ default: m.RevisePage }))),
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
