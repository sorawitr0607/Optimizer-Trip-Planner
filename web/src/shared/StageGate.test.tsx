import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";

import type { Journey } from "../api/client";
import { LanguageProvider } from "../i18n/LanguageProvider";
import { StageGate } from "./StageGate";

function Location() {
  return <span data-location={useLocation().pathname} />;
}

describe("StageGate", () => {
  it("explains a blocked route in place without redirecting", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData<Journey>(["journey", "trip-1"], {
      stages: [
        { key: "setup", done: true, blocked_by: null },
        { key: "places", done: false, blocked_by: null },
        { key: "evidence", done: false, blocked_by: "places" },
        { key: "optimize", done: false, blocked_by: "places" },
        { key: "itinerary", done: false, blocked_by: "optimize" },
      ],
      next: "places",
      capability_gaps: [],
      has_active_plan: false,
      choice_count: 0,
    });

    const html = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <LanguageProvider>
          <MemoryRouter initialEntries={["/trips/trip-1/optimize"]}>
            <Location />
            <Routes>
              <Route
                path="/trips/:tripId/optimize"
                element={
                  <StageGate stage="optimize">
                    <p>hidden optimizer</p>
                  </StageGate>
                }
              />
            </Routes>
          </MemoryRouter>
        </LanguageProvider>
      </QueryClientProvider>,
    );

    expect(html).toContain('data-location="/trips/trip-1/optimize"');
    expect(html).toContain("Finish this first:");
    expect(html).toContain("/trips/trip-1/places");
    expect(html).not.toContain("hidden optimizer");
  });
});
