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
import { CoordinateMap, ItineraryPage, plotCoordinates } from "./ItineraryPage";
import { PlacesPage } from "./PlacesPage";

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
    expect(html).toContain("78.4");
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

describe("ItineraryPage", () => {
  it("renders all six row types, the half-day fallback, and both available exports", () => {
    // `?view=timeline` because the map is what opens by default now. The tab is in the
    // URL precisely so this stays assertable rather than becoming unreachable state.
    const html = render(<ItineraryPage />, "en", undefined, "?view=timeline");
    for (const rowType of ["preparation", "travel", "visit", "buffer", "meal", "logistics"]) {
      expect(html).toContain(`plan-row ${rowType}`);
    }
    expect(html).toContain("Fallback for this half-day");
    expect(html.indexOf("Fallback for this half-day")).toBeGreaterThan(html.indexOf("Longshan Temple"));
    expect(html).toContain(`/api/export/${TRIP}/workbook.xlsx`);
    expect(html).toContain(`/api/export/${TRIP}/checklist.ics`);
    expectNoMissingCopy(html);
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
        stops={SNAPSHOT.data.days[0].stops}
      />,
      "en",
    );
    expect(html).toContain("plan-map-route");
    expect(html).toContain("Ximen hotel area");
    expect(html).toContain("Longshan Temple · 🔒 Locked");
    expect(html).toContain("25.03654, 121.49992");
    expectNoMissingCopy(html);
  });
});
