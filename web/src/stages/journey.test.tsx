import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { PlanPreview, SetupDraft, SetupVocabulary, Trip } from "../api/client";
import type { Language } from "../i18n/copy";
import { LanguageProvider } from "../i18n/LanguageProvider";
import { AppShell } from "../shared/AppShell";
import { OptimizePage } from "./OptimizePage";
import { SetupPage } from "./SetupPage";

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

const VOCABULARY = {
  planning_modes: ["explore_first", "ready_to_schedule"],
  accommodation_statuses: ["unknown", "not_booked", "booked"],
  tag_groups: {
    main_style: ["sightseeing", "culture", "nature"],
    also_enjoy: ["local_street_food", "night_view"],
    avoid: ["tourist_traps"],
    comfort: ["balanced_pace", "rest_breaks"],
  },
  countries: [
    { code: "Taiwan", label: { en: "Taiwan", th: "ไต้หวัน" }, cities: ["Taipei", "Hualien"] },
  ],
} satisfies SetupVocabulary;

const SETUP = {
  trip_id: TRIP,
  snapshot: {
    data: {
      trip_basics: {
        start_date: "2026-12-29",
        end_date: "2027-01-03",
        arrival_time: "17:00",
        departure_time: "11:00",
        accommodation_status: "not_booked",
      },
      owner: {
        age: 34,
        main_style: ["sightseeing", "culture"],
        also_enjoy: ["night_view"],
        avoid: ["tourist_traps"],
        comfort: ["balanced_pace"],
        description: "Walking is fine when the route has sights.",
        must_respect: ["No 6am starts"],
        nationality: "TH",
      },
      travellers: [
        {
          traveller_id: "member_1",
          label: "Mum",
          age: 63,
          tags: ["rest_breaks"],
          description: "Slower mornings",
          must_respect: ["No long stairs"],
          nationality: "TH",
        },
      ],
    },
    sha256: "abc",
  },
  confirmed: true,
  updated_at: "now",
} satisfies SetupDraft;

const PREVIEW = {
  trip_id: TRIP,
  optimizer_input: {
    data: { candidates: [{ id: "area_1", name: "Ximen", names: { en: "Ximen" } }] },
    sha256: "in",
  },
  proposal: {
    data: {
      mode: "timetable",
      variants: [
        {
          variant_id: "best_balance",
          status: "provisional",
          metrics: {
            scheduled_visits: 6,
            travel_minutes: 120,
            walking_minutes: 45,
            meal_minutes: 90,
            logistics_minutes: 30,
            preparation_minutes: 20,
            plain_walking_minutes: 15,
            buffer_minutes: 40,
          },
          warnings: ["OPENING_UNVERIFIED"],
          reconciliation: [
            {
              name: "Taipei 101",
              names: { en: "Taipei 101", th: "ตึกไทเป 101" },
              priority: "must_do",
              status: "ready",
              reason: "OPENING_UNVERIFIED",
              consequence: "ACCESS_UNVERIFIED",
            },
          ],
          days: [
            {
              date: "2026-12-30",
              items: [
                {
                  type: "visit",
                  start: "09:00",
                  end: "10:30",
                  duration_minutes: 90,
                  name: "Taipei 101",
                  names: { en: "Taipei 101", th: "ตึกไทเป 101" },
                },
              ],
            },
          ],
          stopped_at_limit: false,
          objective_improved_or_equal_to_greedy: true,
          validation: { valid: true },
          hotel_recommendation: { default_area_id: "area_1", basis: "optimizer_recommendation" },
        },
      ],
    },
    sha256: "out",
  },
  created_at: "now",
} satisfies PlanPreview;

function render(page: ReactNode, language: Language): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["trips"], TRIPS);
  client.setQueryData(["setup", TRIP], SETUP);
  client.setQueryData(["setup_vocabulary"], VOCABULARY);
  client.setQueryData(["candidate_choices", TRIP], [
    { trip_id: TRIP, place_id: "p1", action: "must_do", reason: null },
  ]);
  client.setQueryData(["plan_preview", TRIP], PREVIEW);
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <LanguageProvider initial={language}>
        <MemoryRouter initialEntries={[`/trips/${TRIP}/x`]}>
          <Routes>
            <Route element={page} path="/trips/:tripId/x" />
          </Routes>
        </MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

/** The same tree with no stored setup, which is what a just-created trip has. */
function renderWithoutSetup(page: ReactNode, language: Language): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["trips"], TRIPS);
  client.setQueryData(["setup", TRIP], null);
  client.setQueryData(["setup_vocabulary"], VOCABULARY);
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <LanguageProvider initial={language}>
        <MemoryRouter initialEntries={[`/trips/${TRIP}/x`]}>
          <Routes>
            <Route element={page} path="/trips/:tripId/x" />
          </Routes>
        </MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

function expectNoMissingCopy(html: string): void {
  expect(html).not.toMatch(/⚠ [a-z][a-z0-9_]{3,}/);
}

describe("SetupPage", () => {
  it("opens a returning owner on the first question, not on the intro", () => {
    // Step 1 explains the wizard, which is worth reading once. This trip already
    // has a saved draft, so the intro would be six steps of ceremony in front of
    // an answer that was given weeks ago.
    const html = render(<SetupPage />, "en");

    expect(html).toContain("Step 2 of 6");
    expect(html).toContain("wizard-steps");
    // The saved draft is what the form opens on, not an empty one.
    expect(html).toContain("2026-12-29");
    expect(html).toContain("value=\"17:00\"");
    expectNoMissingCopy(html);
  });

  it("explains what the wizard wants before asking anything, on a fresh trip", () => {
    // A first-time owner used to meet a date checkbox with nothing anywhere saying
    // what the form was for or how long it ran.
    const html = renderWithoutSetup(<SetupPage />, "en");

    expect(html).toContain("Step 1 of 6");
    expect(html).toContain("What you will be asked");
    expect(html).toContain("about five minutes");
    // Nothing is asked here, so there is no draft to save.
    expect(html).not.toContain("Save draft");
    expectNoMissingCopy(html);
  });

  it("renders the same wizard in Thai", () => {
    const html = render(<SetupPage />, "th");

    expect(html).toContain("ขั้นที่ 2 จาก 6");
    expect(html).toContain("2026-12-29");
    expectNoMissingCopy(html);
  });

  it("opens with only the current step reachable", () => {
    const html = render(<SetupPage />, "en");

    // Step 1 is current; every later step is closed, because later steps
    // depend on earlier answers.
    expect((html.match(/disabled=""/g) ?? []).length).toBeGreaterThanOrEqual(5);
    expect(html).toContain("wizard-step current reached");
  });
});

describe("OptimizePage", () => {
  it("renders the variant, its metrics and the timeline in English", () => {
    const html = render(<OptimizePage />, "en");

    expect(html).toContain("optimize-metrics");
    expect(html).toContain("Taipei 101");
    expect(html).toContain("2026-12-30");
    // Three metrics per row, not five.
    expect(html).toContain("optimize-variant");
    expectNoMissingCopy(html);
  });

  it("renders the same screen in Thai", () => {
    const html = render(<OptimizePage />, "th");

    expect(html).toContain("ตึกไทเป 101");
    expectNoMissingCopy(html);
  });

  it("offers provisional activation for an explore-first trip", () => {
    const html = render(<OptimizePage />, "en");

    // explore_first + provisional + valid is the one case that activates
    // without a ready variant, and it says so before the button.
    expect(html).toContain("provisional");
    expect(html).not.toContain("optimize-actions\"><button class=\"setup-primary\" disabled");
  });

  it("renders optimizer warnings through the code catalogue", () => {
    const html = render(<OptimizePage />, "en");

    expect(html).toContain("optimize-warnings");
    // A stable code must never surface raw to the owner.
    expect(html).not.toContain("OPENING_UNVERIFIED");
  });
});

describe("AppShell", () => {
  it("renders the sidebar, the trip selector and the phone toggle", () => {
    const html = render(<AppShell />, "en");

    expect(html).toContain("Build the trip");
    expect(html).toContain("Use the trip");
    // The trip context sits under the stages, the language control at the foot.
    expect(html).toContain("trip-context");
    expect(html).toContain("Taipei New Year");
    expect(html).toContain("Taipei, Taiwan");
    // Designed, not lifted: the donor has no phone precedent for a nav sidebar.
    expect(html).toContain("nav-toggle");
    expect(html).toContain('aria-expanded="false"');
    expectNoMissingCopy(html);
  });

  it("renders the sidebar in Thai", () => {
    const html = render(<AppShell />, "th");

    expect(html).toContain("สร้างทริป");
    expect(html).toContain("ใช้งานทริป");
    expectNoMissingCopy(html);
  });
});
