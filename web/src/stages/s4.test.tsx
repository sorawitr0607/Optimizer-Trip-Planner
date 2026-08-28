import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type {
  CandidateChoice,
  DiscoveryRun,
  ExportSnapshot,
  Frozen,
  PaidCallCheck,
  Ranking,
  SetupDraft,
} from "../api/client";
import type { Language } from "../i18n/copy";
import { LanguageProvider } from "../i18n/LanguageProvider";
import { copy } from "../i18n/copy";
import { Thinking } from "../shared/Thinking";
import { PLACES_STAGES, PLACES_WORKER_STAGES, PREVIEW_STAGES } from "../shared/buildStages";
import { flattenDays } from "../shared/tripClock";
import { BuildStages } from "./BuildStages";
import { CoordinateMap, ItineraryPage, plotCoordinates } from "./ItineraryPage";
import { centreOf, pinchedZoom, spreadOf } from "../shared/pinch";
import { BuildProgress } from "./OptimizePage";
import { PlacesPage } from "./PlacesPage";
import { TripNow } from "./TripNow";

const TRIP = "taipei";
const SETUP = {
  trip_id: TRIP,
  snapshot: { data: { planning_mode: "explore_first" }, sha256: "setup-1" },
  confirmed: true,
  updated_at: "now",
} satisfies SetupDraft;
const DISCOVERY = {
  run_id: "run-1",
  trip_id: TRIP,
  setup_sha256: "setup-1",
  provider: "openstreetmap",
  status: "verified",
  candidates: {
    sha256: "candidates",
    data: {
      candidates: [{
        place_id: "taipei-101",
        name: "Taipei 101",
        names: { en: "Taipei 101", th: "ตึกไทเป 101", local: "台北101" },
        latitude: 25.03376,
        longitude: 121.5645,
        category: "museum",
        address: "No. 7, Xinyi Road",
        provider_aliases: [{ provider: "openstreetmap", provider_place_id: "node/1", source_url: "https://www.openstreetmap.org/node/1" }],
        operational_evidence: {
          opening_hours: { state: "regular_schedule_only" },
          best_time: { state: "unconfirmed" },
          access: { state: "unconfirmed" },
        },
      }],
    },
  },
  report: {
    sha256: "report",
    data: {
      canonical_candidates: 1,
      duplicates_merged: 0,
      geographic_cells_with_candidates: 1,
      attribution: "OpenStreetMap contributors",
      license: "ODbL",
      license_url: "https://www.openstreetmap.org/copyright",
    },
  },
  created_at: "now",
} satisfies DiscoveryRun;
const RANKING = {
  cards: {
    "taipei-101": {
      place_id: "taipei-101",
      total_score: 78.4,
      dimensions: {
        group_preference_fit: { score: 24, max: 30 },
        experience_value: { score: 18, max: 20 },
      },
      deductions: [],
      candidate_tags: ["sightseeing", "culture"],
      matched_tags: ["sightseeing"],
      matched_people: ["owner"],
      experience_value: 18,
      is_city_icon: true,
      why_shown: ["group_preference_match"],
      pros: ["preference_match"],
      cons: ["route_not_verified", "opening_unconfirmed"],
      duration_estimate: { minimum_minutes: 90, maximum_minutes: 180, origin: "planner_category_default" },
      feasibility: { state: "not_evaluated", reason: "optimizer_not_run" },
      choice_action: "interested",
    },
  },
  lanes: {
    main_queue: [{ place_id: "taipei-101", role: "ranked" }],
    city_icons: ["taipei-101"],
    worth_it_if: ["taipei-101"],
    local_alternatives: [],
    browse_all: ["taipei-101"],
  },
  coverage: { retrieved_candidates: 1 },
} satisfies Ranking;
const CHOICES = [{ trip_id: TRIP, place_id: "taipei-101", action: "interested", reason: null }] satisfies CandidateChoice[];
const PAID = { allowed: true, estimate_usd: 0.0035, projected_usd: 0.0035, cap_usd: 10, reason: null } satisfies PaidCallCheck;

const ITEMS: ExportSnapshot["days"][number]["items"] = [
  { order: 1, item_id: "d#01", type: "preparation", subject_id: "prep", date: "2030-01-01", start: "08:00", end: "08:30", duration_minutes: 30, status: "recheck", display_name: "Pack the day bag", notes: "Check rain gear" },
  { order: 2, item_id: "d#02", type: "travel", subject_id: "route", date: "2030-01-01", start: "08:30", end: "09:00", duration_minutes: 30, status: "confirmed", origin_name: "Hotel", destination_name: "Longshan Temple", mode: "walk", walking_minutes: 20, distance_m: 1400, transfers: 0, boarding_buffer_minutes: 0, sightseeing_walk: true },
  { order: 3, item_id: "d#03", type: "visit", subject_id: "longshan", date: "2030-01-01", start: "09:00", end: "10:00", duration_minutes: 60, status: "locked", stop_number: 1, display_name: "Longshan Temple", local_name: "艋舺龍山寺", priority: "must_do", address: "Wanhua", opening_verified: true },
  { order: 4, item_id: "d#04", type: "buffer", subject_id: "meal_window", date: "2030-01-01", start: "10:00", end: "12:00", duration_minutes: 120, status: "confirmed", reason: "meal_window" },
  { order: 5, item_id: "d#05", type: "meal", subject_id: "lunch", date: "2030-01-01", start: "12:00", end: "13:00", duration_minutes: 60, status: "recheck", display_name: "Lunch near Ximen", notes: "Confirm the queue" },
  { order: 6, item_id: "d#06", type: "logistics", subject_id: "checkin", date: "2030-01-01", start: "13:00", end: "13:30", duration_minutes: 30, status: "recheck", display_name: "Hotel check-in", notes: "Confirm the booked room" },
];
const SNAPSHOT = {
  sha256: "export",
  data: {
    stamp: {
      plan_version_id: "plan_1234567890abcdef",
      is_active_plan: true,
      variant_id: "best_balance",
      variant_status: "provisional",
      language: "en",
      base_currency: "THB",
      exported_at: "2030-01-01T00:00:00+00:00",
      capability_gaps: ["OPENING_EVIDENCE_MISSING"],
    },
    readiness: { state: "action_needed", variant_status: "provisional", capability_gaps: ["OPENING_EVIDENCE_MISSING"] },
    days: [{
      date: "2030-01-01",
      start: "08:00",
      end: "13:30",
      items: ITEMS,
      stops: [{ stop_number: 1, subject_id: "longshan", display_name: "Longshan Temple", latitude: 25.03654, longitude: 121.49992, status: "locked" }],
      fallbacks: [{ primary_id: "outdoor", fallback_id: "museum", trigger: "rain", date: "2030-01-01", half_day: "morning", primary_name: "Elephant Mountain", replacement_name: "National Palace Museum", replacement_start: "10:00", displaced_consequence: "RAIN_FALLBACK_ACTIVATED" }],
      totals: { scheduled_visits: 1, visit_minutes: 60, travel_minutes: 30, walking_minutes: 20, rewarding_walking_minutes: 20, plain_walking_minutes: 0, buffer_minutes: 120, meal_minutes: 60, preparation_minutes: 30, logistics_minutes: 30 },
      highest_risk: { status: "recheck", item_id: "d#01", subject_id: "prep" },
    }],
    unscheduled: [{ place_id: "taipei-101", display_name: "Taipei 101", priority: "interested", reason: "NO_TIME_CAPACITY", consequence: "EFFORT_OR_TIME_CONFLICT" }],
    checklist: { items: [{ title: "Check passport" }] },
    accommodation: { status: "not_booked", anchor: { subject_id: "hotel", display_name: "Ximen hotel area", latitude: 25.042, longitude: 121.508 } },
  },
} satisfies Frozen<ExportSnapshot>;

/** `view` is the places screen's list/deck toggle, which lives in the URL so a reload
 *  keeps it. The list card is what these assertions are about, and in deck mode it is
 *  correctly absent -- it used to render in both, showing a place the deck had already
 *  moved past. */
function render(
  page: ReactNode,
  language: Language,
  seed?: (client: QueryClient) => void,
  search = "?view=list",
): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["setup", TRIP], SETUP);
  client.setQueryData(["discovery", TRIP], DISCOVERY);
  client.setQueryData(["candidate_choices", TRIP], CHOICES);
  client.setQueryData(["ranking", TRIP], RANKING);
  // Free Wikidata summary: the card must lead with real prose and a photo, not with
  // the templated sentence built from the same codes for every place.
  client.setQueryData(["place_summaries", TRIP], {
    "taipei-101": {
      place_id: "taipei-101",
      qid: "Q83263",
      text: { en: "A supertall skyscraper and the tallest building in Taiwan." },
      image_url: "https://commons.example/taipei-101.jpg?width=640",
      licence: "CC BY-SA, Wikipedia and Wikimedia Commons",
      source_urls: { en: "https://en.wikipedia.org/wiki/Taipei_101" },
    },
  });
  client.setQueryData(["paid_check", "google_places:card_details"], PAID);
  client.setQueryData(["paid_check", "google_places:photo", 5], PAID);
  client.setQueryData(["export_snapshot", TRIP, language], {
    ...SNAPSHOT,
    data: { ...SNAPSHOT.data, stamp: { ...SNAPSHOT.data.stamp, language } },
  });
  seed?.(client);
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <LanguageProvider initial={language}>
        <MemoryRouter initialEntries={[`/trips/${TRIP}/x${search}`]}>
          <Routes><Route element={page} path="/trips/:tripId/x" /></Routes>
        </MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

function expectNoMissingCopy(html: string): void {
  expect(html).not.toMatch(/⚠ [a-z][a-z0-9_]{3,}/);
}

describe("PlacesPage", () => {
  it("renders discovery, ranking, choices, and paid cost before its button", () => {
    const html = render(<PlacesPage />, "en");
    // The 2026-08-10 terminology pass renamed both of these: "Broad attraction
    // discovery" and "Personalized place cards" were the engineering-console
    // wording a UX audit flagged. Pinned rather than loosened — a screen that
    // silently loses its title should still fail here.
    expect(html).toContain("Choose where to go");
    expect(html).toContain("Places picked for your trip");
    expect(html).toContain("Taipei 101");
    expect(html).toContain("Museum");
    expect(html).toContain("78% match");
    expect(html).toContain("Current choice: Interested");
    expect(html).toContain("US$0.007");
    expect(html.indexOf("US$0.007")).toBeLessThan(html.indexOf("Load live gallery"));
    expectNoMissingCopy(html);
  });

  it("puts the detail panel beside the deck, without a second set of decisions", () => {
    // The panel used to be a whole other mode reached from a button at the top, so
    // reading about the card in front of you meant leaving the deck. It sits beside it
    // now and follows it -- but the deck owns deciding, and two sets of choice buttons
    // under one card is exactly the duplication reported before.
    const html = render(<PlacesPage />, "en", undefined, "");

    expect(html).toContain("places-workspace");
    expect(html).toContain("place-card-head");
    // Present in the markup, hidden in deck mode: the deck's own buttons are the ones
    // to press, and `hidden` keeps it out of the accessibility tree too.
    expect(html).toMatch(/class="place-choice-actions"[^>]*hidden/);
    // The lane picker is shared by both views and must survive.
    expect(html).toContain("lane-tabs");
  });

  it("hides empty place lanes and falls back to the first lane with cards", () => {
    const html = render(<PlacesPage />, "en", (client) => {
      client.setQueryData(["ranking", TRIP], {
        ...RANKING,
        lanes: { ...RANKING.lanes, city_icons: [] },
      });
    });

    expect(html).not.toMatch(/<button[^>]*>City Icons/);
    expect(html).toMatch(/aria-pressed="true" class="lane-tab active"[^>]*>For your trip/);
    expect(html).toContain("Taipei 101");
  });

  it("leads a card with the free description and photo, not the templated line", () => {
    const html = render(<PlacesPage />, "en");
    expect(html).toContain("About this place");
    expect(html).toContain("tallest building in Taiwan");
    expect(html).toContain("commons.example/taipei-101.jpg");
    expect(html).toContain("CC BY-SA");
    expect(html).toContain("Read on Wikipedia");
    // The description must precede the score breakdown, and the mechanism codes are
    // retitled so nobody reads them as a description of the place.
    expect(html.indexOf("About this place")).toBeLessThan(html.indexOf("Why it matched your preferences"));
    expectNoMissingCopy(html);
  });

  it("offers the free fetch when a card has not been looked up yet", () => {
    // An absent key means not fetched. Distinct from a fetched place that has no
    // entry, because one is worth a button and the other is not.
    const html = render(<PlacesPage />, "en", (client) => {
      client.setQueryData(["place_summaries", TRIP], {});
    });
    expect(html).toContain("Load free descriptions");
    expect(html).toContain("no charge and no key");
    // The templated sentence survives as the fallback meanwhile.
    expect(html).toContain("is worth considering for");
    expectNoMissingCopy(html);
  });

  it("says so when a looked-up place genuinely has no entry", () => {
    // 459 of the 832 real Taipei candidates carry no Wikidata id at all, so this is
    // the common case, not an edge one.
    const html = render(<PlacesPage />, "en", (client) => {
      client.setQueryData(["place_summaries", TRIP], {
        "taipei-101": {
          place_id: "taipei-101", qid: "", text: {}, image_url: null,
          licence: "CC BY-SA, Wikipedia and Wikimedia Commons", source_urls: {},
        },
      });
    });
    expect(html).toContain("No encyclopedia entry found");
    expect(html).not.toContain("Load free descriptions");
    expectNoMissingCopy(html);
  });

  it("renders the same ranked identity in Thai without changing the place id", () => {
    const html = render(<PlacesPage />, "th");
    expect(html).toContain("ตึกไทเป 101");
    expect(html).toContain("พิพิธภัณฑ์");
    expect(html).toContain("taipei-101");
    expectNoMissingCopy(html);
  });
});

describe("the /places stage list", () => {
  function stages(reached: number): string {
    return renderToStaticMarkup(
      <LanguageProvider initial="en">
        <BuildStages language="en" reached={reached} stages={PLACES_STAGES} />
      </LanguageProvider>,
    );
  }

  it("has one stage per reported milestone and copy for every one of them", () => {
    // Four from the worker -- geocode, landmarks, baseline, catalogue -- and the
    // page's own fifth, the ranking and first card that `busy` has always covered.
    // A sixth would be a claim about work nobody does.
    expect(PLACES_STAGES).toHaveLength(PLACES_WORKER_STAGES + 1);
    for (const stage of PLACES_STAGES) {
      for (const language of ["en", "th"] as const) {
        expect(copy(`stage_${stage.key}`, language)).not.toContain("⚠");
        expect(copy(`stage_${stage.key}_detail`, language)).not.toContain("⚠");
      }
    }
  });

  it("marks exactly the stages the worker has reported", () => {
    // Two returned: the geocode and the landmark block. The baseline -- the slow
    // half, and the reason this screen needed a stage list at all -- is in flight.
    const html = stages(2);

    expect(html.match(/build-stage done/g) ?? []).toHaveLength(2);
    expect(html.match(/build-stage active/g) ?? []).toHaveLength(1);
    expect(html).toContain("Everything else");
  });

  it("is still busy when the worker is done, because the ranking is not", () => {
    const html = stages(PLACES_WORKER_STAGES);

    expect(html).toContain('aria-busy="true"');
    expect(html.match(/build-stage active/g) ?? []).toHaveLength(1);
    expect(html).toContain("Your shortlist");
  });
});

describe("the draft build's stage list", () => {
  it("shows the dot-and-line steps immediately, before worker progress arrives", () => {
    const html = renderToStaticMarkup(
      <LanguageProvider initial="en">
        <BuildProgress language="en" />
      </LanguageProvider>,
    );

    expect(html.match(/build-stage done/g) ?? []).toHaveLength(0);
    expect(html.match(/build-stage active/g) ?? []).toHaveLength(1);
    expect(html).toContain("Balanced plan");
  });

  it("has one stage per variant plus the write, with copy for every one", () => {
    // Three variants and then the stored draft. A fourth variant row would be a
    // claim about work the optimizer does not do.
    expect(PREVIEW_STAGES).toHaveLength(4);
    for (const stage of PREVIEW_STAGES) {
      for (const language of ["en", "th"] as const) {
        expect(copy(`stage_${stage.key}`, language)).not.toContain("⚠");
        expect(copy(`stage_${stage.key}_detail`, language)).not.toContain("⚠");
      }
    }
  });

  it("marks the variants that have come back", () => {
    const html = renderToStaticMarkup(
      <LanguageProvider initial="en">
        <BuildStages language="en" reached={2} stages={PREVIEW_STAGES} />
      </LanguageProvider>,
    );

    expect(html.match(/build-stage done/g) ?? []).toHaveLength(2);
    expect(html).toContain("More highlights");
  });
});

describe("pinch to zoom", () => {
  // The map had wheel zoom and nothing else, so on a phone — where there is no wheel,
  // and `touch-action: none` also suppresses the browser's own gesture — it could not
  // be zoomed at all. The gesture cannot be driven from a test: a dispatched
  // `PointerEvent` does not move this map even on the code that predates the pinch,
  // checked against the deployment. The arithmetic is what is pinned here.
  const two = (a: number, b: number) =>
    new Map([[1, { x: a, y: 0 }], [2, { x: b, y: 0 }]]);

  it("measures the spread and the point to hold still", () => {
    expect(spreadOf(two(100, 220))).toBe(120);
    expect(centreOf(two(100, 220))).toEqual({ x: 160, y: 0 });
    // One finger is not a pinch.
    expect(spreadOf(new Map([[1, { x: 5, y: 5 }]]))).toBe(0);
  });

  it("scales from where the fingers started, not from the last move", () => {
    const start = { spread: 60, zoom: 4 };
    // Out to triple the spread, then back to where it began.
    expect(pinchedZoom(start, 180, 1, 24)).toBeCloseTo(12);
    expect(pinchedZoom(start, 30, 1, 24)).toBeCloseTo(2);
    expect(pinchedZoom(start, 60, 1, 24)).toBeCloseTo(4);
  });

  it("respects the zoom floor and ceiling the wheel uses", () => {
    expect(pinchedZoom({ spread: 10, zoom: 20 }, 1000, 1, 24)).toBe(24);
    expect(pinchedZoom({ spread: 1000, zoom: 2 }, 10, 1, 24)).toBe(1);
  });

  it("does nothing when a finger has not moved apart at all", () => {
    // A zero spread would divide by zero and send the viewBox to Infinity.
    expect(pinchedZoom({ spread: 0, zoom: 6 }, 120, 1, 24)).toBe(6);
    expect(pinchedZoom({ spread: 120, zoom: 6 }, 0, 1, 24)).toBe(6);
  });
});

describe("the elapsed counter on a wait", () => {
  it("counts from when the work began, not from when it was last re-rendered", () => {
    // `/places` moves this element into the active stage the moment the worker
    // reports, which is a new mount. Counting from mount would restart the number
    // at zero part-way through a 30-90s wait -- "it looks like it hung", which is
    // the exact report the counter was added to answer.
    const html = renderToStaticMarkup(
      <LanguageProvider initial="en">
        <Thinking language="en" lines={["think_searching"]} startedAt={Date.now() - 42_000} />
      </LanguageProvider>,
    );

    expect(html).toContain("42s");
  });

  it("counts from mount when nothing tells it otherwise", () => {
    const html = renderToStaticMarkup(
      <LanguageProvider initial="en">
        <Thinking language="en" lines={["think_searching"]} />
      </LanguageProvider>,
    );

    expect(html).toContain("0s");
  });
});

describe("ItineraryPage", () => {
  it("says why a day carries no places instead of looking like a copy", () => {
    /**
     * Reported as "2 duplicate day plans, day 7 and day 8". They were not duplicates and
     * the plan was not wrong: the owner's Porto trip chose 22 places, all 22 were
     * scheduled, and the trip ran two days longer than they fill. The operational
     * timeline is still emitted for such a day — breakfast, free time, lunch, free time,
     * dinner — so two consecutive days rendered the same rows with no stops between them.
     *
     * The rows are right. The sentence saying why the day looks like that was missing.
     */
    // A second day carrying only a meal and a buffer, which is what the operational
    // timeline emits once every chosen place is already scheduled elsewhere.
    const freeDay = {
      date: "2030-01-02",
      start: "08:00",
      end: "13:30",
      items: [
        { order: 1, item_id: "e#01", type: "meal", subject_id: "breakfast", date: "2030-01-02", start: "08:00", end: "08:45", duration_minutes: 45, status: "confirmed", display_name: "Breakfast near the base or first stop" },
        { order: 2, item_id: "e#02", type: "buffer", subject_id: "free", date: "2030-01-02", start: "08:45", end: "17:30", duration_minutes: 525, status: "confirmed", reason: "free_time_or_rest" },
      ],
      stops: [],
      fallbacks: [],
      totals: { scheduled_visits: 0, visit_minutes: 0, travel_minutes: 0, walking_minutes: 0, rewarding_walking_minutes: 0, plain_walking_minutes: 0, buffer_minutes: 525, meal_minutes: 45, preparation_minutes: 0, logistics_minutes: 0 },
      highest_risk: null,
    };
    const seedTwoDays = (client: QueryClient) => {
      client.setQueryData(["export_snapshot", TRIP, "en"], {
        ...SNAPSHOT,
        data: { ...SNAPSHOT.data, days: [...SNAPSHOT.data.days, freeDay] },
      });
    };

    const html = render(<ItineraryPage />, "en", seedTwoDays, "?view=timeline&date=2030-01-02");
    expect(html).toContain("No places are scheduled on this day");
    // The rows themselves are right and stay: this is a sentence, not a suppression.
    expect(html).toContain("Breakfast near the base or first stop");

    // And the day that does have places says nothing of the kind.
    const busy = render(<ItineraryPage />, "en", seedTwoDays, "?view=timeline&date=2030-01-01");
    expect(busy).toContain("Longshan Temple");
    expect(busy).not.toContain("No places are scheduled on this day");

    // Nor does the prep evening, which never carries places by design and is already
    // named rather than numbered — "The evening before you go" explains itself, and
    // telling the owner their places fit in the other days would describe it wrongly.
    const prepOnly = {
      ...freeDay,
      date: "2029-12-31",
      items: [
        { order: 1, item_id: "p#01", type: "preparation", subject_id: "pack", date: "2029-12-31", start: "19:00", end: "19:30", duration_minutes: 30, status: "recheck", display_name: "Pack the day bag" },
      ],
    };
    const withPrepEvening = render(<ItineraryPage />, "en", (client: QueryClient) => {
      client.setQueryData(["export_snapshot", TRIP, "en"], {
        ...SNAPSHOT,
        data: { ...SNAPSHOT.data, days: [prepOnly, ...SNAPSHOT.data.days] },
      });
    }, "?view=timeline&date=2029-12-31");
    expect(withPrepEvening).toContain("The evening before you go");
    expect(withPrepEvening).not.toContain("No places are scheduled on this day");
  });

  it("shows a stop the same photograph its swipe card showed", () => {
    /**
     * `DayStops` built its own URL from `osmPhotoUrl(item.photo_reference)` — the
     * OpenStreetMap tag alone, one of the three sources `shared/photos.ts` assembles and
     * the narrowest of them. A place pictured from Wikidata or a Commons geosearch had a
     * photograph on `/places` and none here, which is what the owner asked to close.
     *
     * The paid overlay is deliberately unreachable from this screen: `enrich_place_card`
     * is session-only state held in `PlacesPage` and never persisted, so there is nothing
     * here to read and nothing to spend. This is the free store.
     */
    const html = render(<ItineraryPage />, "en", (client) => {
      client.setQueryData(["place_summaries", TRIP], {
        longshan: {
          place_id: "longshan",
          qid: "Q706976",
          image_url: "https://commons.example/longshan.jpg",
          image_urls: ["https://commons.example/longshan.jpg"],
          licence: "CC BY-SA",
          source_urls: {},
        },
      });
    }, "?view=timeline");

    expect(html).toContain("day-stop-thumb");
    expect(html).toContain("commons.example/longshan.jpg");
  });

  it("says a photograph found by location is not of the place", () => {
    // `photos_are_nearby` is the geosearch disclosure. It was stored and rendered
    // nowhere once already, and a flag nothing prints is not a disclosure — so every
    // surface that shows one of these has to carry the sentence.
    const html = render(<ItineraryPage />, "en", (client) => {
      client.setQueryData(["place_summaries", TRIP], {
        longshan: {
          place_id: "longshan",
          qid: null,
          image_url: "https://commons.example/somewhere-near.jpg",
          image_urls: ["https://commons.example/somewhere-near.jpg"],
          photos_are_nearby: true,
          licence: "CC BY-SA",
          source_urls: {},
        },
      });
    }, "?view=timeline");

    // No thumbnail on the row: it is always on screen, a row has no space for a
    // caption, and an undisclosed picture of somewhere *near* the stop is the quiet
    // claim this app does not make. The picture is still offered inside the expanded
    // detail, where the disclosure sits beside it.
    expect(html).not.toContain("day-stop-thumb");
    // And a confident photograph in the same position does get one, so this is the
    // disclosure rule at work and not simply a missing feature.
    const confident = render(<ItineraryPage />, "en", (client) => {
      client.setQueryData(["place_summaries", TRIP], {
        longshan: {
          place_id: "longshan", qid: "Q706976",
          image_url: "https://commons.example/longshan.jpg",
          image_urls: ["https://commons.example/longshan.jpg"],
          licence: "CC BY-SA", source_urls: {},
        },
      });
    }, "?view=timeline");
    expect(confident).toContain("day-stop-thumb");
  });

  it("renders all six row types, the half-day fallback, and both available exports", () => {
    // `?view=timeline` because the map is what opens by default now. The tab is in the
    // URL precisely so this stays assertable rather than becoming unreachable state.
    const html = render(<ItineraryPage />, "en", undefined, "?view=timeline");
    for (const rowType of ["preparation", "travel", "visit", "buffer", "meal", "logistics"]) {
      // The dashboard renders a `day-stop` list item whose badge carries the type,
      // where the audit table rendered `plan-row <type>` on an article. Every one of the
      // six kinds still appears on its own row, which is what this test is about.
      expect(html).toContain(`plan-row-kind ${rowType}`);
    }
    expect(html).toContain("Fallback for this half-day");
    expect(html.indexOf("Fallback for this half-day")).toBeGreaterThan(html.indexOf("Longshan Temple"));
    expect(html).toContain('<dialog class="day-stop-lightbox"');
    // No summary seeded and the fixture's stops carry no OpenStreetMap tag, so there is
    // no photograph to show — the state the timeline was permanently stuck in.
    expect(html).not.toContain("day-stop-thumb");
    expect(html).toContain(`/api/export?trip=${TRIP}&amp;kind=workbook.xlsx`);
    expect(html).toContain(`/api/export?trip=${TRIP}&amp;kind=checklist.ics`);
    const mapHtml = render(<ItineraryPage />, "en", undefined, "?view=map");
    expect(mapHtml).toContain('href="https://www.google.com/maps/search/?api=1&amp;query=');
    expect((mapHtml.match(/https:\/\/www\.google\.com\/maps\/search\/\?api=1&amp;query=/g) ?? []).length).toBe(2);
    // Coordinates and nothing else. A name in the query makes it a text search, which
    // Google answers with whatever matches the words — a different temple, or none.
    for (const query of mapHtml.matchAll(/api=1&amp;query=([^"]*)"/g)) {
      expect(query[1]).toMatch(/^-?\d+\.\d+,-?\d+\.\d+$/);
    }
    expectNoMissingCopy(html);
  });

  it("keeps the chosen day in the URL and renders the dashboard's two wide-screen panels", () => {
    const second = {
      ...SNAPSHOT.data.days[0],
      date: "2030-01-02",
      items: SNAPSHOT.data.days[0].items.map((item) => ({
        ...item,
        date: "2030-01-02",
        item_id: item.item_id.replace("d#", "d2#"),
      })),
    };
    const html = render(
      <ItineraryPage />,
      "en",
      (client) => client.setQueryData(["export_snapshot", TRIP, "en"], {
        ...SNAPSHOT,
        data: { ...SNAPSHOT.data, days: [...SNAPSHOT.data.days, second] },
      }),
      "?view=timeline&date=2030-01-02",
    );

    expect(html).toContain("2030-01-02");
    expect(html).toMatch(/aria-pressed="true" class="day-tab"[^>]*><span[^>]*>Day 2 of 2/);
    expect(html).toContain('class="itinerary-panels"');
    expect(html.match(/class="itinerary-panel /g) ?? []).toHaveLength(2);
  });

  it("offers an exact Maps handoff from the pinned current stop", () => {
    const item = flattenDays(SNAPSHOT.data.days)[2];
    const html = renderToStaticMarkup(
      <LanguageProvider initial="en">
        <TripNow
          currentDayDate={item.dayDate}
          dayLabelOf={() => "Day 1 of 1"}
          items={flattenDays(SNAPSHOT.data.days)}
          language="en"
          mapHrefOf={() => "https://www.google.com/maps/search/?api=1&query=25.000000,121.000000"}
          nameOf={(entry) => entry.display_name ?? entry.type}
          onPin={() => undefined}
          onSelectDay={() => undefined}
          pinned={item.startAt}
        />
      </LanguageProvider>,
    );

    expect(html).toContain("Open in Maps");
    expect(html).toContain("25.000000,121.000000");
  });

  it("carries the D10 day header with its four judged numbers", () => {
    const html = render(<ItineraryPage />, "en");

    // Deviation D10: a two-column header, ratio enforced in CSS by the token
    // gate. The four numbers a day is actually judged on live here; the full
    // breakdown moves behind a disclosure rather than being dropped.
    expect(html).toContain("dayhead");
    expect(html).toContain("dayhead-left");
    expect(html).toContain("dayhead-right");
    expect((html.match(/dayhead-stat"/g) ?? []).length).toBe(4);
    expect(html).toContain("Day 1 of");
    expect(html).toContain("plan-day-detail");
    // The old prose summary is gone, not duplicated alongside it.
    expect(html).not.toContain("plan-day-summary");
  });

  it("renders the operational rows and warnings in Thai", () => {
    const html = render(<ItineraryPage />, "th", undefined, "?view=timeline");
    // "Active plan" became "Your itinerary" in the terminology pass.
    expect(html).toContain("ตารางเดินทางของคุณ");
    expect(html).toContain("จุดที่ 1");
    expect(html).toContain("รอช่วงมื้ออาหาร");
    expect(html).toContain("แผนสำรองของช่วงนี้");
    expectNoMissingCopy(html);
  });
});

describe("CoordinateMap", () => {
  it("plots true relative geometry and duplicates status in the stop list", () => {
    const points = plotCoordinates([
      { id: "a", label: "1", latitude: 25, longitude: 121, status: "confirmed" },
      { id: "b", label: "2", latitude: 25.001, longitude: 121.001, status: "locked" },
    ]);
    const dx = Math.abs(points[1].x - points[0].x);
    const dy = Math.abs(points[1].y - points[0].y);
    expect(dx / dy).toBeCloseTo(Math.cos((25.0005 * Math.PI) / 180), 3);

    const html = render(
      <CoordinateMap
        accommodationStatus={SNAPSHOT.data.accommodation.status}
        anchor={SNAPSHOT.data.accommodation.anchor}
        language="en"
        onSelectStop={() => undefined}
        stops={SNAPSHOT.data.days[0].stops}
      />,
      "en",
    );
    expect(html).toContain("plan-map-route");
    expect(html).toContain("Ximen hotel area");
    expect(html).toContain("Longshan Temple · 🔒 Locked");
    expect(html).toContain("25.03654, 121.49992");
    expect(html.match(/role="button"/g) ?? []).toHaveLength(1);
    expect(html).toContain("Show Longshan Temple in the trip");
    expectNoMissingCopy(html);
  });
});
