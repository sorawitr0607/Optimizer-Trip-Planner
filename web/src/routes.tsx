/* eslint-disable react-refresh/only-export-components */
import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router";

import { rpc, type Journey, type Trip } from "./api/client";
import { copy } from "./i18n/copy";
import { useLanguage } from "./i18n/LanguageProvider";
import { AppShell } from "./shared/AppShell";
import { StageGate } from "./shared/StageGate";
import { CostsPage } from "./stages/CostsPage";
import { EvidencePage } from "./stages/EvidencePage";
import { ItineraryPage } from "./stages/ItineraryPage";
import { OptimizePage } from "./stages/OptimizePage";
import { ReadinessPage } from "./stages/ReadinessPage";
import { RevisePage } from "./stages/RevisePage";
import { PlacesPage } from "./stages/PlacesPage";
import { SetupPage } from "./stages/SetupPage";
import { SplitPage } from "./stages/SplitPage";
import { TripsPage } from "./stages/TripsPage";

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

// The table is data; `main.tsx` builds the router from it. That split is what
// lets the entry-point smoke test assert the nine routes and five gate keys
// without a DOM: `createBrowserRouter` reads `window.history` at construction,
// Vitest runs in the node environment, and adding jsdom to check a nine-row
// array would be the wrong trade.
export const routes = [
  { path: "/", element: <Landing /> },
  { path: "/trips", element: <TripsPage /> },
  {
    path: "/trips/:tripId",
    element: <AppShell />,
    children: [
      { path: "setup", element: <SetupPage /> },
      {
        path: "places",
        element: (
          <StageGate stage="places">
            <PlacesPage />
          </StageGate>
        ),
      },
      {
        path: "evidence",
        element: (
          <StageGate stage="evidence">
            <EvidencePage />
          </StageGate>
        ),
      },
      {
        path: "optimize",
        element: (
          <StageGate stage="optimize">
            <OptimizePage />
          </StageGate>
        ),
      },
      {
        path: "itinerary",
        element: (
          <StageGate stage="itinerary">
            <ItineraryPage />
          </StageGate>
        ),
      },
      {
        path: "readiness",
        element: (
          <StageGate stage="setup">
            <ReadinessPage />
          </StageGate>
        ),
      },
      {
        path: "costs",
        element: (
          <StageGate stage="setup">
            <CostsPage />
          </StageGate>
        ),
      },
      {
        path: "split",
        element: (
          <StageGate stage="setup">
            <SplitPage />
          </StageGate>
        ),
      },
      {
        path: "revise",
        element: (
          <StageGate stage="itinerary">
            <RevisePage />
          </StageGate>
        ),
      },
    ],
  },
];
