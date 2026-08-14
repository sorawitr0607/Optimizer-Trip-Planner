import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";

import type { Journey } from "../api/client";
import { LanguageProvider } from "../i18n/LanguageProvider";
import { ThemeProvider } from "./ThemeProvider";
import { AppShell } from "./AppShell";

/**
 * Exactly one element may claim to be the current page.
 *
 * An audit on 2026-08-14 found three on a completed route — the brand, the real stage
 * and "New trip slot", because `/trips` matches every `/trips/:id/*` descendant without
 * `end` — and **eight** on a fresh Places route, because a locked stage pointed at `#`,
 * which resolves to whatever page you are on. A screen reader asks one question about
 * where it is and was given contradictory answers, while locked destinations were
 * announced as links to the page already open.
 */

const TRIP = "trip_1";

const JOURNEY: Journey = {
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
};

function render(path: string): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["journey", TRIP], JOURNEY);
  client.setQueryData(
    ["trips"],
    [{ trip_id: TRIP, name: "Trip", destination: "Hong Kong, Hong Kong", planning_mode: "explore_first", language: "en", created_at: "" }],
  );
  const router = createMemoryRouter(
    [{ path: "/trips/:tripId", element: <AppShell />, children: [{ path: "places", element: <p /> }] }],
    { initialEntries: [path] },
  );
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <LanguageProvider initial="en">
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

describe("sidebar navigation semantics", () => {
  it("names exactly one current page", () => {
    const html = render(`/trips/${TRIP}/places`);

    expect(html.match(/aria-current="page"/g) ?? []).toHaveLength(1);
  });

  it("never ticks a stage in Check and adjust", () => {
    // Evidence, readiness and revise are not steps you finish — evidence is checked when
    // something looks wrong, the board is kept rather than completed, and a revision is
    // made whenever the plan needs one. A tick claims a thing is behind you that you may
    // come back to twice more. The *announcement* goes with the mark: dropping the glyph
    // while still saying "Done" would give a screen reader a claim nobody else gets.
    const html = render(`/trips/${TRIP}/places`);
    const check = html.slice(html.indexOf("Check and adjust"));

    expect(check).toContain("Check trip facts");
    expect(check).not.toContain("— Done");
  });

  it("does not offer a locked stage as a link", () => {
    const html = render(`/trips/${TRIP}/places`);

    // Three stages are blocked in the fixture above, and none of them may be an anchor.
    expect(html).toContain('aria-disabled="true"');
    expect(html).not.toContain('href="#"');
  });
});
