import { renderToStaticMarkup } from "react-dom/server";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";

import type { Journey } from "../api/client";
import { StageTabs } from "./StageTabs";

/**
 * The phone's navigation. `journey.test.tsx` asserts this surface is *absent* from
 * the desktop shell; this asserts it is right when it is present.
 */

const TRIP = "trip_1";

function journeyWith(overrides: Partial<Journey> = {}): Journey {
  return {
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
    ...overrides,
  };
}

function render(journey: Journey | undefined, stage: string): string {
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: (
          <StageTabs
            journey={journey}
            language="en"
            onMore={() => {}}
            stage={stage}
            tripId={TRIP}
          />
        ),
      },
    ],
    { initialEntries: [`/trips/${TRIP}/${stage}`] },
  );
  return renderToStaticMarkup(<RouterProvider router={router} />);
}

describe("StageTabs", () => {
  it("names exactly one current page", () => {
    const html = render(journeyWith(), "places");

    expect(html.match(/aria-current="page"/g) ?? []).toHaveLength(1);
  });

  it("resumes the build at the first unfinished stage", () => {
    // Setup is done and Places is not, so Build points at Places rather than
    // restarting at Setup.
    expect(render(journeyWith(), "places")).toContain(`/trips/${TRIP}/places`);
    expect(render(journeyWith(), "places")).not.toContain(`/trips/${TRIP}/setup`);
  });

  it("keeps Build pointing at a build stage once everything is finished", () => {
    // `journey.next` falls back to `itinerary` when there is nothing left, and a
    // Build tab that quietly becomes the Itinerary tab is the bug this guards.
    const done = journeyWith({
      stages: [
        { key: "setup", done: true, blocked_by: null },
        { key: "places", done: true, blocked_by: null },
        { key: "evidence", done: true, blocked_by: null },
        { key: "optimize", done: true, blocked_by: null },
        { key: "itinerary", done: true, blocked_by: null },
      ],
      next: "itinerary",
    });

    expect(render(done, "itinerary")).toContain(`/trips/${TRIP}/optimize`);
  });

  it("owns the screens a tab stands in for", () => {
    // Split has no tab of its own; Money is current while it is open. It needs an
    // unblocked itinerary to be reachable at all — Costs and Split both gate on it —
    // so the first shape of this test asked for a state the app cannot be in, and
    // Money was correctly rendered locked with nothing current.
    const usable = journeyWith({
      stages: [
        { key: "setup", done: true, blocked_by: null },
        { key: "places", done: true, blocked_by: null },
        { key: "evidence", done: true, blocked_by: null },
        { key: "optimize", done: true, blocked_by: null },
        { key: "itinerary", done: true, blocked_by: null },
      ],
      next: "itinerary",
    });
    const html = render(usable, "split");

    expect(html.match(/aria-current="page"/g) ?? []).toHaveLength(1);
    expect(html).toContain(`aria-current="page"`);
    expect(html).toContain(`/trips/${TRIP}/costs`);
  });

  it("does not offer a locked stage as a link", () => {
    // Itinerary is blocked by optimize in the fixture.
    const html = render(journeyWith(), "places");

    expect(html).toContain('aria-disabled="true"');
    expect(html).not.toContain('href="#"');
  });

  it("survives a journey that has not loaded yet", () => {
    const html = render(undefined, "setup");

    expect(html).toContain("stage-tabs");
    expect(html).not.toContain("⚠");
  });
});
