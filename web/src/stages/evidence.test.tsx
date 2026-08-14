import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { Journey, OpeningIntervals, PaidUsageStatus, RouteRecord, Trip } from "../api/client";
import type { Language } from "../i18n/copy";
import { LanguageProvider } from "../i18n/LanguageProvider";
import { EvidencePage } from "./EvidencePage";

const TRIP = "taipei";

const TRIPS = [
  {
    trip_id: TRIP,
    name: "Taipei New Year",
    destination: "Taipei, Taiwan",
    planning_mode: "explore_first",
    language: "en",
    created_at: "2026-07-30",
  },
] satisfies Trip[];

const USAGE = {
  month: "2026-08",
  estimated_usd: 0.229,
  spent_usd: 0.229,
  cap_usd: 10,
  warn_at_usd: 8,
  remaining_usd: 9.771,
  requests: 50,
  state: "ok",
  cap_is_owner_raised: false,
  by_operation: {},
  entries: [],
} satisfies PaidUsageStatus;

const INTERVALS = {
  place_a: { interval: { start: "09:00", end: "18:00" }, reason: "OPENING_CONFIRMED_OFFICIAL" },
  place_b: { interval: null, reason: "OPENING_NOT_FETCHED" },
  place_c: { interval: null, reason: "ACCESS_UNVERIFIED" },
} satisfies OpeningIntervals;

const ROUTES = [
  { origin_id: "place_a", destination_id: "place_b", mode: "walk", status: "verified" },
] satisfies RouteRecord[];

const JOURNEY = {
  stages: [
    { key: "setup", done: true, blocked_by: null },
    { key: "places", done: true, blocked_by: null },
    { key: "evidence", done: false, blocked_by: null },
    { key: "optimize", done: false, blocked_by: null },
    { key: "itinerary", done: false, blocked_by: "optimize" },
  ],
  next: "evidence",
  capability_gaps: ["ACCOMMODATION_BASE_UNCONFIRMED", "OPENING_EVIDENCE_MISSING"],
  has_active_plan: false,
  choice_count: 3,
} satisfies Journey;

function render(language: Language, overrides: Record<string, unknown> = {}): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const seed: Record<string, unknown> = {
    accommodation_base: null,
    timezone_evidence: null,
    opening_intervals: INTERVALS,
    routes: ROUTES,
    journey: JOURNEY,
    candidate_choices: [
      {
        trip_id: TRIP,
        place_id: "place_b",
        action: "must_do",
        reason: null,
        candidate: { data: { name: "Longshan Temple", names: { en: "Longshan Temple", th: "วัดหลงซาน" } }, sha256: "x" },
      },
    ],
    ...overrides,
  };
  client.setQueryData(["trips"], TRIPS);
  client.setQueryData(["paid_usage"], overrides.paid_usage ?? USAGE);
  for (const key of ["accommodation_base", "timezone_evidence", "opening_intervals", "routes", "journey", "candidate_choices"]) {
    client.setQueryData([key, TRIP], seed[key]);
  }
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <LanguageProvider initial={language}>
        <MemoryRouter initialEntries={[`/trips/${TRIP}/x`]}>
          <Routes>
            <Route element={<EvidencePage />} path="/trips/:tripId/x" />
          </Routes>
        </MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

function expectNoMissingCopy(html: string): void {
  expect(html).not.toMatch(/⚠ [a-z][a-z0-9_]{3,}/);
}

describe("EvidencePage", () => {
  it("states each paid cost immediately before its own button", () => {
    const html = render("en");

    // Element 16: one card per paid action, cost then button — never a wall of
    // stacked buttons with the costs somewhere in between.
    const zoneCost = html.indexOf("One paid lookup, about US$0.005");
    const zoneButton = html.indexOf("Look up the time zone", zoneCost);
    expect(zoneCost).toBeGreaterThan(-1);
    expect(zoneButton).toBeGreaterThan(zoneCost);

    const hoursCost = html.indexOf("One paid lookup per selected place");
    expect(hoursCost).toBeGreaterThan(-1);
    expect(html.indexOf("evidence-cost", hoursCost - 200)).toBeLessThan(hoursCost);
    expectNoMissingCopy(html);
  });

  it("states no cost for route fetching, which is free-tier", () => {
    const html = render("en");

    // openrouteservice is priced at 0.0, so a cost line here would be a lie.
    // With a verified route the header reads "Routes stored: 1", so anchor on
    // the button and look back over its own card.
    const button = html.indexOf("Fetch walking routes");
    expect(button).toBeGreaterThan(-1);
    const card = html.slice(html.lastIndexOf('<div class="evidence-card">', button), button);
    expect(card).not.toContain("evidence-cost");
    expect(card).toContain("Routes stored");
  });

  it("shows the spend meter against the cap before any paid card", () => {
    const html = render("en");

    // Two decimal places: this is money, and US$0.2290 of US$10.00 claims a precision
    // an estimate from a price table does not have. The ledger keeps the full value.
    expect(html).toContain("US$0.23");
    expect(html).toContain("US$10.00");
    expect(html).toContain("50");
    expect(html.indexOf("US$0.23")).toBeLessThan(html.indexOf("evidence-cost"));
  });

  it("stops the paid buttons when the cap is reached", () => {
    const html = render("en", { paid_usage: { ...USAGE, state: "stopped", estimated_usd: 10.5 } });

    expect(html).toContain("The monthly paid cap is reached");
    // Both paid buttons refuse; the free route button stays available.
    expect((html.match(/disabled=""/g) ?? []).length).toBeGreaterThanOrEqual(2);
  });

  it("offers the owner a free window only where they can resolve it", () => {
    const html = render("en");

    // OPENING_NOT_FETCHED is owner-fixable; ACCESS_UNVERIFIED is not.
    expect(html).toContain("Longshan Temple");
    expect(html).toContain("evidence-owner-hours");
    expect((html.match(/evidence-owner-hours/g) ?? []).length).toBe(1);
  });

  it("names the capability gaps and offers the provisional path in explore mode", () => {
    const html = render("en");

    expect(html).toContain("Still needed before a validated plan:");
    // Codes render through the catalogue, never raw.
    expect(html).not.toContain("ACCOMMODATION_BASE_UNCONFIRMED");
    expect(html).not.toContain("OPENING_EVIDENCE_MISSING");
    expect(html).toContain("Explore mode can continue now");
    expectNoMissingCopy(html);
  });

  it("goes straight to optimize when nothing is missing", () => {
    const html = render("en", { journey: { ...JOURNEY, capability_gaps: [] } });

    expect(html).not.toContain("Still needed before a validated plan:");
    expect(html).toContain("Build the plan");
  });

  it("renders the whole screen in Thai", () => {
    const html = render("th");

    expect(html).toContain("เขตเวลา");
    expect(html).toContain("วัดหลงซาน");
    expectNoMissingCopy(html);
  });
});
