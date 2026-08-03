/* eslint-disable react-refresh/only-export-components */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { createBrowserRouter, Link, Navigate, useNavigate } from "react-router";

import { ApiError, rpc, type Journey, type StageKey, type Trip } from "./api/client";
import { copy } from "./i18n/copy";
import { useLanguage } from "./i18n/LanguageProvider";
import { AppShell } from "./shared/AppShell";
import { StageGate } from "./shared/StageGate";
import { CostsPage } from "./stages/CostsPage";
import { OptimizePage } from "./stages/OptimizePage";
import { SetupPage } from "./stages/SetupPage";
import { SplitPage } from "./stages/SplitPage";
import { StagePage } from "./stages/StagePage";

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

function TripsPage() {
  const { language } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [destination, setDestination] = useState("");
  const trips = useQuery({ queryKey: ["trips"], queryFn: () => rpc<Trip[]>("list_trips") });
  const createTrip = useMutation({
    mutationFn: () => rpc<Trip>("create_trip", { name, destination, language }),
    onSuccess: async (trip) => {
      await queryClient.invalidateQueries({ queryKey: ["trips"] });
      navigate(`/trips/${trip.trip_id}/setup`);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    createTrip.mutate();
  }

  const errorCode = createTrip.error instanceof ApiError ? createTrip.error.code : createTrip.error?.message;
  return (
    <main className="trips-page">
      <section className="stage-card">
        <h1>{copy("saved_trips", language)}</h1>
        {trips.isPending ? <p>{copy("loading", language)}</p> : null}
        {trips.data?.length === 0 ? <p>{copy("empty", language)}</p> : null}
        <div className="trip-list">
          {trips.data?.map((trip) => (
            <Link key={trip.trip_id} to={`/trips/${trip.trip_id}/setup`}>
              <strong>{trip.name}</strong>
              <span>{trip.destination}</span>
            </Link>
          ))}
        </div>
      </section>
      <form className="stage-card trip-form" onSubmit={submit}>
        <h2>{copy("new_trip", language)}</h2>
        <label>
          {copy("name", language)}
          <input onChange={(event) => setName(event.target.value)} value={name} />
        </label>
        <label>
          {copy("destination", language)}
          <input
            onChange={(event) => setDestination(event.target.value)}
            required
            value={destination}
          />
        </label>
        {errorCode ? <p className="field-error">⚠ {errorCode}</p> : null}
        <button disabled={createTrip.isPending} type="submit">
          {copy("create", language)}
        </button>
      </form>
    </main>
  );
}

function gated(stage: string, gate: StageKey) {
  return (
    <StageGate stage={gate}>
      <StagePage stage={stage} />
    </StageGate>
  );
}

export const router = createBrowserRouter([
  { path: "/", element: <Landing /> },
  { path: "/trips", element: <TripsPage /> },
  {
    path: "/trips/:tripId",
    element: <AppShell />,
    children: [
      { path: "setup", element: <SetupPage /> },
      { path: "places", element: gated("places", "places") },
      { path: "evidence", element: gated("evidence", "evidence") },
      {
        path: "optimize",
        element: (
          <StageGate stage="optimize">
            <OptimizePage />
          </StageGate>
        ),
      },
      { path: "itinerary", element: gated("itinerary", "itinerary") },
      { path: "readiness", element: gated("readiness", "setup") },
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
      { path: "revise", element: gated("revise", "itinerary") },
    ],
  },
]);
