import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { isValidElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { LanguageProvider } from "./i18n/LanguageProvider";
import { routes } from "./routes";
import { StageGate } from "./shared/StageGate";

/**
 * The React entry-point smoke test.
 *
 * `tests/test_foundation.py::test_streamlit_entry_point_renders` does not die
 * with the POC — it changes subject, which is the reclassification artifact 029
 * names. What it asserted was "the app wires up", and that is now this table.
 *
 * Artifact 028 decided 9 stage routes resolving to 5 gate keys; it is **10 routes to
 * 5 keys** since `stay` landed. Both halves
 * are load-bearing and neither is visible from a screen: a dropped route is a
 * 404 nobody notices until they navigate there, and a gate key drifting to a
 * sixth value silently changes which stage blocks which.
 */

// The decided IA, in the decided order: BUILD then USE.
const STAGE_ROUTES = [
  "setup",
  "places",
  // Ten, not the nine artifact 028 decided. "Where to stay" became its own route at the
  // owner's asking on 2026-08-14: the area ranking was a section under the deck on
  // `/places` and the accommodation base was one card among five on `/evidence`, so the
  // two halves of one decision were never on screen together and neither said that the
  // planner was meanwhile working from the centre of the chosen places.
  "stay",
  "evidence",
  "optimize",
  "itinerary",
  "readiness",
  "costs",
  "split",
  "revise",
];

// Five, not nine. Several USE-section screens share the `setup` gate because
// they need a confirmed setup and nothing more.
const GATE_KEYS = new Set(["setup", "places", "evidence", "optimize", "itinerary"]);

const shell = routes.find((route) => route.path === "/trips/:tripId");
const children = shell?.children ?? [];

describe("entry point", () => {
  it("mounts the landing redirect and the trip list above the shell", () => {
    // `*` is the branded catch-all: a mistyped address used to reach React
    // Router's own "Unexpected Application Error!" development page.
    expect(routes.map((route) => route.path)).toEqual(["/", "/trips", "*", "/trips/:tripId"]);
    for (const route of routes) expect(isValidElement(route.element)).toBe(true);
  });

  it("reuses the shell query cache while resolving a returning owner's route", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
    });
    client.setQueryData(["trips"], [{
      trip_id: "trip-1",
      name: "Trip",
      destination: "Taipei, Taiwan",
      planning_mode: "explore_first",
      language: "en",
      created_at: "2026-08-31",
    }]);
    client.setQueryData(["journey", "trip-1"], { next: "itinerary", stages: [] });
    const landing = routes.find((route) => route.path === "/")?.element;

    const html = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <LanguageProvider initial="en">
          <MemoryRouter>{landing}</MemoryRouter>
        </LanguageProvider>
      </QueryClientProvider>,
    );

    expect(html).not.toContain('aria-busy="true"');
  });

  it("resolves every stage route in the decided order under one shell", () => {
    expect(children.map((child) => child.path)).toEqual(STAGE_ROUTES);
    for (const child of children) expect(isValidElement(child.element)).toBe(true);
  });

  it("gates every route except setup, and only on the five decided keys", () => {
    const gated = new Map<string, string>();
    for (const child of children) {
      const element = child.element;
      if (!isValidElement(element) || element.type !== StageGate) continue;
      gated.set(child.path!, (element.props as { stage: string }).stage);
    }

    // Setup is the one ungated route: it is what every gate checks for.
    expect([...gated.keys()]).toEqual(STAGE_ROUTES.filter((path) => path !== "setup"));
    for (const [path, stage] of gated) {
      expect(GATE_KEYS.has(stage), `${path} gates on unknown stage ${stage}`).toBe(true);
    }
    // Four distinct gates, not five. `setup` was a gate that never blocked anything —
    // the journey's setup stage carries no `blocked_by` — so `readiness`, `costs` and
    // `split` gating on it meant "reachable and empty" before a plan existed. They gate
    // on `itinerary` now, which leaves `setup` used by no route. What matters is that
    // every gate is one of the five decided keys, asserted above.
    expect(new Set(gated.values()).size).toBeGreaterThanOrEqual(4);
  });
});
