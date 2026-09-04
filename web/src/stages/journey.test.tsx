import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { PlanPreview, SetupDraft, SetupVocabulary, Trip } from "../api/client";
import type { Language } from "../i18n/copy";
import { LanguageProvider } from "../i18n/LanguageProvider";
import { AppShell } from "../shared/AppShell";
import { ThemeProvider } from "../shared/ThemeProvider";
import { OptimizePage } from "./OptimizePage";
import { SetupPage } from "./SetupPage";
import { TripsPage } from "./TripsPage";

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
              place_id: "taipei_101",
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

function render(
  page: ReactNode,
  language: Language,
  plan: PlanPreview = PREVIEW,
  setup: SetupDraft = SETUP,
  /** Seed `["comfort_tradeoffs", trip, variantId]`. The key is the point of the test
   *  that uses it: the page must ask about the variant it is drawing. */
  comfort?: { variantId: string | null; report: unknown },
): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (comfort) {
    client.setQueryData(["comfort_tradeoffs", TRIP, comfort.variantId], comfort.report);
  }
  client.setQueryData(["trips"], TRIPS);
  client.setQueryData(["setup", TRIP], setup);
  client.setQueryData(["setup_vocabulary"], VOCABULARY);
  client.setQueryData(["candidate_choices", TRIP], [
    { trip_id: TRIP, place_id: "p1", action: "must_do", reason: null },
  ]);
  client.setQueryData(["plan_preview", TRIP], plan);
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <LanguageProvider initial={language}>
          <MemoryRouter initialEntries={[`/trips/${TRIP}/x`]}>
            <Routes>
              <Route element={page} path="/trips/:tripId/x" />
            </Routes>
          </MemoryRouter>
        </LanguageProvider>
      </ThemeProvider>
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
      <ThemeProvider>
        <LanguageProvider initial={language}>
          <MemoryRouter initialEntries={[`/trips/${TRIP}/x`]}>
            <Routes>
              <Route element={page} path="/trips/:tripId/x" />
            </Routes>
          </MemoryRouter>
        </LanguageProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function expectNoMissingCopy(html: string): void {
  expect(html).not.toMatch(/⚠ [a-z][a-z0-9_]{3,}/);
}

describe("TripsPage", () => {
  it("keeps the Thai headline wrap-capable and states the optional network boundary", () => {
    const html = render(<TripsPage />, "th");
    const heading = html.match(/<h1>(.*?)<\/h1>/)?.[1] ?? "";

    // Thai does not separate every word with a space. Wrapping its whole headline in
    // the English word-animation span made it one unbreakable inline block on phones.
    expect(heading).toContain("วางแผนเที่ยวตามข้อจำกัดในโลกจริง");
    expect(heading).not.toContain("hero-word");
    expect(html).toContain("การทำงานเสริมผ่านผู้ให้บริการหรือ AI");
    expect(html).not.toContain("ไม่มีการอัปโหลด");
    expectNoMissingCopy(html);
  });

  it("uses explicit native controls for the trip-creation fields", () => {
    const html = render(<TripsPage />, "en");

    expect(html).toMatch(/<select[^>]*name="country"[^>]*required/);
    expect(html).toContain('aria-describedby="destination-help"');
    expect(html).toContain('autoComplete="country-name"');
    expect(html).toContain('autoComplete="address-level2"');
    expect(html).toContain('type="text" name="city-custom"');
    expect(html).toContain('type="text" name="trip-name"');
    expect(html).toContain("Trip name (optional)");
    expect(html).toContain("Destination is required.");
    expectNoMissingCopy(html);
  });

  it("keeps landing claims durable and exposes interactive selection state", () => {
    const html = render(<TripsPage />, "en");

    expect(html).toContain("Regression-tested planning core");
    expect(html).toContain("Trip data stays in local SQLite");
    expect(html).not.toContain("638 Deterministic Tests Passing");
    expect(html).not.toContain("100% Offline &amp; Private");
    expect(html).not.toContain("mathematical certainty");
    expect(html).not.toContain("100% Hours Verified");
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("Fresh place discovery, map data");
    expectNoMissingCopy(html);
  });
});

describe("SetupPage", () => {
  it("opens a returning owner on the first question, not on the intro", () => {
    // Step 1 explains the wizard, which is worth reading once. This trip already
    // has a saved draft, so the intro would be six steps of ceremony in front of
    // an answer that was given weeks ago.
    const html = render(<SetupPage />, "en");

    expect(html).toContain("Step 2 of 5");
    expect(html).toContain("wizard-steps");
    expect(html).not.toContain("wizard-count");
    expect(html).not.toContain("Setup confirmed. Discovery is now available.");
    // The saved draft is what the form opens on, not an empty one.
    expect(html).toContain("2026-12-29");
    expect(html).toContain("value=\"17:00\"");
    expect((html.match(/type="date"/g) ?? []).length).toBe(2);
    // Four: arrival and departure, plus the two active-hours fields that replaced the
    // 08:00-22:00 literals `_optimizer_input` used to invent for every trip.
    expect((html.match(/type="time"/g) ?? []).length).toBe(4);
    expect((html.match(/type="checkbox"/g) ?? []).length).toBe(3);
    expect(html).toContain('name="accommodation-status"');
    expectNoMissingCopy(html);
  });

  it("explains what the wizard wants before asking anything, on a fresh trip", () => {
    // A first-time owner used to meet a date checkbox with nothing anywhere saying
    // what the form was for or how long it ran.
    const html = renderWithoutSetup(<SetupPage />, "en");

    expect(html).toContain("Step 1 of 5");
    expect(html).toContain("What you will be asked");
    expect(html).toContain("about five minutes");
    expect(html).toContain('aria-label="Setup progress"');
    expect(html).toContain('aria-current="step"');
    expect(html).toContain("<form");
    // Nothing is asked here, so there is no draft to save.
    expect(html).not.toContain("Save draft");
    expectNoMissingCopy(html);
  });

  it("renders the same wizard in Thai", () => {
    const html = render(<SetupPage />, "th");

    expect(html).toContain("ขั้นที่ 2 จาก 5");
    expect(html).toContain("2026-12-29");
    expectNoMissingCopy(html);
  });

  it("opens with only the current step reachable", () => {
    const html = render(<SetupPage />, "en");

    // Step 1 is current; every later step is closed, because later steps
    // depend on earlier answers.
    expect((html.match(/disabled=""/g) ?? []).length).toBeGreaterThanOrEqual(4);
    expect(html).toContain("wizard-step current reached");
  });

  it("puts an invalid date range beside the date fields in plain language", () => {
    const invalid = {
      ...SETUP,
      snapshot: {
        ...SETUP.snapshot,
        data: {
          ...SETUP.snapshot.data,
          trip_basics: {
            ...SETUP.snapshot.data.trip_basics,
            start_date: "2030-05-10",
            end_date: "2030-05-05",
          },
        },
      },
    } satisfies SetupDraft;
    const html = render(<SetupPage />, "en", PREVIEW, invalid);

    expect(html).toContain("End date must be the same as or later than the start date.");
    expect(html).toContain('id="trip-dates-error"');
    expect(html).toContain('aria-invalid="true"');
    expect(html).toContain('aria-describedby="accommodation-help"');
    expect(html).not.toContain("bad_request");
    expectNoMissingCopy(html);
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

    // explore_first + provisional + valid is the one case that activates without a
    // ready variant, and it says so **before** the button rather than inside its
    // label. The button read "Use and export this provisional itinerary" — a sentence
    // on the terminal control of the longest screen in the app — and this assertion
    // was matching that word inside it. The caveat is `provisional_activation_help`,
    // which is where it was always meant to be; the button is now the same short
    // "Use this itinerary" the ready case has always used.
    expect(html).toContain("stays Provisional and must be optimized again");
    expect(html).toContain("Use this itinerary");
    expect(html).not.toContain("optimize-actions\"><button class=\"setup-primary\" disabled");
  });

  it("no longer prints the kept-places table", () => {
    const html = render(<OptimizePage />, "en");

    // Removed at the owner's asking. Every row it carried is said where it is
    // actionable now: a place that fits is on the timeline, a place that does not is in
    // the unfit list with the way out beside it.
    expect(html).not.toContain("reconcile-table");
    expect(html).not.toContain("What happened to each place you kept");
  });

  /** A place no length of trip can hold, which is the endless-button bug. */
  function withReason(reason: string) {
    const plan = structuredClone(PREVIEW);
    plan.proposal.data.variants![0].reconciliation[0] = {
      ...plan.proposal.data.variants![0].reconciliation[0],
      status: "cannot_currently_fit",
      reason,
      consequence: "kept_in_unscheduled_shortlist",
    };
    return plan;
  }

  it("recommends removing a place no length of trip can hold, not adding days", () => {
    // Reported as: press "add 3 days and rebuild once", get another plan still showing
    // the same button. `NO_DAY_LONG_ENOUGH` is the optimizer's answer to "could this fit
    // an *empty* day", so more days provably cannot help and must not be offered.
    const html = render(<OptimizePage />, "en", withReason("NO_DAY_LONG_ENOUGH"));

    expect(html).toContain("cannot fit any single day");
    expect(html).toContain("Remove 1 place(s) and rebuild once");
    expect(html).not.toContain("day(s) and rebuild once");
  });

  it("still offers days when more days would actually help", () => {
    // The other side of the split: `NO_TIME_CAPACITY` now means only what it says, so
    // the offer is honest where it appears.
    const html = render(<OptimizePage />, "en", withReason("NO_TIME_CAPACITY"));

    expect(html).toContain("day(s) and rebuild once");
    expect(html).not.toContain("cannot fit any single day");
  });

  /** Two places that do not fit, neither for want of days. */
  function withTwoUnfit() {
    const plan = structuredClone(PREVIEW);
    const first = plan.proposal.data.variants![0].reconciliation[0];
    const unfit = {
      ...first,
      status: "cannot_currently_fit",
      reason: "CLOSED_AT_AVAILABLE_TIME",
      consequence: "kept_in_unscheduled_shortlist",
    };
    plan.proposal.data.variants![0].reconciliation = [
      unfit,
      {
        ...unfit,
        place_id: "night_market",
        name: "Night Market",
        names: { en: "Night Market", th: "ตลาดกลางคืน" },
      },
    ];
    return plan;
  }

  it("offers checkboxes and one shared rebuild when two places do not fit", () => {
    // Reported as a rebuild per row: dropping three places meant three full
    // builds. More than one unfit row becomes tick-boxes and a single button
    // running the same multi-drop mutation the capacity branch already used.
    const html = render(<OptimizePage />, "en", withTwoUnfit());

    expect(html.match(/type="checkbox"/g) ?? []).toHaveLength(2);
    expect(html).toContain("Drop selected and rebuild (0)");
    expect(html).not.toContain(">Drop and rebuild<");
    expectNoMissingCopy(html);
  });

  it("keeps the single drop button when only one place does not fit", () => {
    const html = render(<OptimizePage />, "en", withReason("CLOSED_AT_AVAILABLE_TIME"));

    expect(html).toContain(">Drop and rebuild<");
    expect(html).not.toContain('type="checkbox"');
    expectNoMissingCopy(html);
  });

  /**
   * The wasted rebuild, and why it happened.
   *
   * `variantId` is null until the owner picks a plan option, and the screen draws
   * `variants[0]` — so the report was asked about `variant_id: null`, which the server
   * answers from the **active plan**. `comfortOnly` (the drawn variant's own violations)
   * said a comfort budget was the only problem while `overBudget` (the report) had
   * nothing to accept, so the screen fell through to a bare "Build them again" that
   * changed nothing except lining the two up. Reported as the first of three presses to
   * get one plan.
   *
   * Seeding under the **drawn variant's** id is the assertion: the accept control only
   * appears if the page asks the question this test answers.
   */
  const COMFORT_REPORT = {
    has_plan: true,
    rules: [
      {
        code: "DAILY_WALKING_BUDGET",
        threshold: 45,
        measured: 61,
        exceeds: true,
        accepted_value: null,
        covered: false,
      },
    ],
  };

  function overBudgetPlan() {
    const plan = structuredClone(PREVIEW) as PlanPreview;
    plan.proposal.data.variants![0].validation = {
      valid: false,
      hard_violations: [{ code: "UNAPPROVED_DAILY_WALKING_BUDGET", subject_id: null }],
    };
    plan.proposal.data.variants![0].status = "unavailable";
    return plan;
  }

  /** Just the comfort refusal's own action row.
   *
   *  Scoped deliberately: "Build them again" also sits at the top of the screen as the
   *  owner's own way to rebuild the options, which is a deliberate affordance and stays.
   *  The one that was waste is the one that appeared *as the way out of this refusal*. */
  function comfortAction(html: string): string {
    const at = html.indexOf('class="optimize-actions comfort-acceptance"');
    expect(at).toBeGreaterThan(-1);
    return html.slice(at, html.indexOf("</div>", at));
  }

  it("offers the acceptance straight away, not a bare rebuild first", () => {
    const html = render(<OptimizePage />, "en", overBudgetPlan(), SETUP, {
      variantId: "best_balance",
      report: COMFORT_REPORT,
    });

    // The measured figure is on the button, which only happens if the page asked the
    // report about the variant it is drawing.
    expect(comfortAction(html)).toContain("61");
    expect(comfortAction(html)).not.toContain("Build them again");
  });

  it("waits rather than offering a rebuild while the report is still arriving", () => {
    // No seed, so the query is pending. A rebuild here is a whole build whose only
    // effect is that the next pass has the figures loaded.
    const html = render(<OptimizePage />, "en", overBudgetPlan());

    expect(comfortAction(html)).toContain("Loading");
    expect(comfortAction(html)).not.toContain("Build them again");
  });

  it("renders optimizer warnings through the code catalogue", () => {
    const html = render(<OptimizePage />, "en");

    expect(html).toContain("optimize-warnings");
    // A stable code must never surface raw to the owner.
    expect(html).not.toContain("OPENING_UNVERIFIED");
  });

  it("offers one route fix inside the places that did not make the plan", () => {
    const blocked = structuredClone(PREVIEW) as PlanPreview;
    blocked.proposal.data.variants![0].reconciliation[0] = {
      ...blocked.proposal.data.variants![0].reconciliation[0],
      status: "cannot_currently_fit",
      reason: "ROUTE_UNVERIFIED",
    };

    const html = render(<OptimizePage />, "en", blocked);

    expect(html).toContain("Places that did not make the plan");
    expect(html).toContain("Accept criteria and rebuild");
    expect(html).not.toContain("Accept a walking estimate and rebuild");
    expect(html.match(/Accept criteria and rebuild/g) ?? []).toHaveLength(1);
  });
});

describe("AppShell", () => {
  it("renders the sidebar and the trip selector, and no phone surface", () => {
    const html = render(<AppShell />, "en");

    expect(html).toContain("Build the trip");
    expect(html).toContain("Use the trip");
    // The trip context sits under the stages, the language control at the foot.
    expect(html).toContain("trip-context");
    expect(html).toContain("Taipei New Year");
    expect(html).toContain("Taipei, Taiwan");
    // This used to assert a `nav-toggle` hamburger holding all ten stages. It is
    // gone: the phone gets `<StageTabs>` in the thumb zone and the sidebar only as
    // the More sheet. `useMediaQuery` answers false without `matchMedia`, which the
    // node test environment does not have, so this render is the desktop one — and
    // asserting the phone surface is *absent* here is what pins that, since the two
    // must never be in one document. `StageTabs.test.tsx` covers the phone side.
    expect(html).not.toContain("stage-tabs");
    expect(html).not.toContain("trip-bar");
    expectNoMissingCopy(html);
  });

  it("renders the sidebar in Thai", () => {
    const html = render(<AppShell />, "th");

    expect(html).toContain("สร้างทริป");
    expect(html).toContain("ใช้งานทริป");
    expectNoMissingCopy(html);
  });
});
