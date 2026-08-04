import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type {
  ChecklistItem,
  ChecklistProposal,
  ChecklistReadiness,
  ChecklistVocabulary,
  PlanVersionRecord,
  QuickAction,
  RevisionDraft,
} from "../api/client";
import type { Language } from "../i18n/copy";
import { LanguageProvider } from "../i18n/LanguageProvider";
import { ReadinessPage } from "./ReadinessPage";
import { RevisePage } from "./RevisePage";

const TRIP = "taipei";

const VOCABULARY = {
  categories: ["entry_requirements", "money", "packing"],
  requirement_levels: ["required", "recommended", "optional"],
  timing_buckets: ["do_now", "30_days_before", "7_days_before", "24_hours_before", "departure_arrival_day"],
  progress_states: ["to_do", "waiting", "done", "not_applicable"],
  evidence_states: ["verified", "verification_needed"],
  authority_types: ["government", "embassy"],
  closed_states: ["done", "not_applicable"],
} satisfies ChecklistVocabulary;

function item(overrides: Partial<ChecklistItem> = {}): ChecklistItem {
  return {
    item_id: "item_1",
    title: "Check passport validity",
    category: "entry_requirements",
    timing: "do_now",
    requirement_level: "required",
    progress: "to_do",
    evidence_state: "verification_needed",
    due_date: "2026-12-01",
    consequence: "Boarding can be refused",
    dismissed: false,
    ...overrides,
  };
}

const ITEMS = [
  item(),
  item({
    item_id: "item_2",
    title: "Buy a travel eSIM",
    category: "money",
    timing: "7_days_before",
    requirement_level: "recommended",
    progress: "done",
    evidence_state: "verified",
    due_date: null,
    consequence: null,
    source_url: "https://example.gov/entry",
    expected_authority: "Bureau of Consular Affairs",
    authority_type: "government",
  }),
  item({ item_id: "item_3", title: "Old task", dismissed: true, timing: "do_now" }),
] satisfies ChecklistItem[];

const PROPOSAL = {
  proposed: ITEMS,
  additions: [item({ item_id: "new_1", title: "Register arrival card", timing: "24_hours_before" })],
  removals: [item({ item_id: "gone_1", title: "Outdated visa step" })],
  deadline_changes: [
    { title: "Check passport validity", from: { due_date: "2026-11-01" }, to: { due_date: "2026-12-01" } },
  ],
  unchanged: 2,
} satisfies ChecklistProposal;

const READINESS = {
  state: "verification_needed",
  blocks_itinerary: false,
  counts: { total: 3, open: 2, required_open: 1, unverified_required: 1, overdue: 0, due_soon: 1, dismissed: 1 },
  due_soon: [],
  overdue: [],
} satisfies ChecklistReadiness;

const QUICK_ACTIONS = [
  { operation: "fully_reoptimize", arguments: {} },
  { operation: "reduce_walking", arguments: { factor: 0.8 } },
] satisfies QuickAction[];

const DRAFT = {
  operation: "reduce_walking",
  assumptions: ["OPENING_UNVERIFIED"],
  explanation: {
    variant_id: "best_balance",
    status: "ready",
    metrics: { scheduled_visits: 4 },
    unscheduled: [{ place_id: "node_1", reason: "EFFORT_OR_TIME_CONFLICT" }],
  },
  consequences: {
    changed_dates: ["2027-01-03"],
    metrics: {
      walking_minutes: { before: 90, after: 55, delta: -35 },
      scheduled_visits: { before: 4, after: 3, delta: -1 },
    },
    moved: [
      { place_id: "node_1", from: { date: "2027-01-03", start: "09:00" }, to: { date: "2027-01-04", start: "10:00" } },
    ],
    added: [],
    removed: ["node_2"],
    shortened: [{ place_id: "node_1", from_minutes: 90, to_minutes: 60 }],
    lengthened: [],
    displaced: [{ place_id: "node_2", reason: "EFFORT_OR_TIME_CONFLICT" }],
    warnings: { new: ["ACCESS_UNVERIFIED"], cleared: ["OPENING_UNVERIFIED"] },
    can_apply: true,
  },
  can_apply: true,
} satisfies RevisionDraft;

const VERSIONS = [
  { version_id: "plan_aaaaaaaaaaaa", trip_id: TRIP, cause: "optimizer:best_balance", created_at: "now" },
  { version_id: "plan_bbbbbbbbbbbb", trip_id: TRIP, cause: "revision:reduce_walking", created_at: "now" },
] satisfies PlanVersionRecord[];

function render(page: ReactNode, language: Language, overrides: Record<string, unknown> = {}): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const seed: Record<string, unknown> = {
    checklist_vocabulary: VOCABULARY,
    [`checklist_proposal:${TRIP}`]: PROPOSAL,
    [`checklist_items:${TRIP}`]: ITEMS,
    [`checklist_readiness:${TRIP}`]: READINESS,
    [`quick_actions:${TRIP}`]: QUICK_ACTIONS,
    [`revision_draft:${TRIP}`]: DRAFT,
    [`revisions:${TRIP}`]: [
      { created_at: "2026-08-04T10:00:00", operation: "reduce_walking", from_version_id: "plan_aaaaaaaaaaaa", to_version_id: "plan_bbbbbbbbbbbb" },
    ],
    [`plan_versions:${TRIP}`]: VERSIONS,
    [`candidate_choices:${TRIP}`]: [
      { trip_id: TRIP, place_id: "node_1", action: "must_do", reason: null, candidate: { data: { name: "Shibuya Sky", names: { en: "Shibuya Sky", th: "ชิบูยะ สกาย" } }, sha256: "x" } },
      { trip_id: TRIP, place_id: "node_2", action: "interested", reason: null, candidate: { data: { name: "Meiji Shrine", names: { en: "Meiji Shrine", th: "ศาลเจ้าเมจิ" } }, sha256: "y" } },
    ],
    ...overrides,
  };
  client.setQueryData(["checklist_vocabulary"], seed.checklist_vocabulary);
  for (const key of ["checklist_proposal", "checklist_items", "checklist_readiness", "quick_actions", "revision_draft", "revisions", "plan_versions", "candidate_choices"]) {
    client.setQueryData([key, TRIP], seed[`${key}:${TRIP}`]);
  }
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

describe("ReadinessPage", () => {
  it("previews additions, removals and deadline moves before applying", () => {
    const html = render(<ReadinessPage />, "en");

    // Nothing is applied silently, and the panel opens when there is something.
    expect(html).toContain("readiness-preview");
    expect(html).toContain("open=\"\"");
    expect(html).toContain("Register arrival card");
    expect(html).toContain("Outdated visa step");
    expect(html).toContain("2026-11-01");
    expect(html).toContain("2026-12-01");
    expectNoMissingCopy(html);
  });

  it("renders the board in Thai", () => {
    const html = render(<ReadinessPage />, "th");

    expect(html).toContain("จำเป็น");
    expect(html).toContain("Register arrival card");
    expectNoMissingCopy(html);
  });

  it("groups items by timing bucket and shows level, progress and evidence", () => {
    const html = render(<ReadinessPage />, "en");

    expect(html).toContain("Check passport validity");
    expect(html).toContain("Buy a travel eSIM");
    expect(html).toContain("Required");
    expect(html).toContain("Boarding can be refused");
    // A source and its responsible authority render when present.
    expect(html).toContain("https://example.gov/entry");
    expect(html).toContain("Bureau of Consular Affairs");
    // A code authority renders through the catalogue, not as snake_case.
    const coded = render(<ReadinessPage />, "en", {
      [`checklist_items:${TRIP}`]: [item({ expected_authority: "attraction_operator" })],
    });
    expect(coded).not.toContain("attraction_operator");
    expect(coded).toContain("Attraction operator");
  });

  it("keeps a dismissed item restorable rather than gone", () => {
    const html = render(<ReadinessPage />, "en");

    expect(html).toContain("readiness-dismissed");
    expect(html).toContain("Old task");
    expectNoMissingCopy(html);
  });

  it("says the board is unavailable when there is no setup", () => {
    const html = render(<ReadinessPage />, "en", {
      [`checklist_items:${TRIP}`]: [],
      [`checklist_proposal:${TRIP}`]: { proposed: [], additions: [], removals: [], deadline_changes: [], unchanged: 0 },
    });

    expect(html).toContain("Save the trip setup first");
    expectNoMissingCopy(html);
  });

  it("shows only the counts that carry a label", () => {
    const html = render(<ReadinessPage />, "en");

    expect(html).toContain("Open 2");
    // `total` and `dismissed` have no label and are derivable from the board.
    expect(html).not.toMatch(/⚠ total/);
    expect(html).not.toMatch(/⚠ dismissed/);
  });
});

describe("RevisePage", () => {
  it("shows the rebuilt variant's consequences with named places", () => {
    const html = render(<RevisePage />, "en");

    expect(html).toContain("revise-draft");
    // Consequences name places, never a truncated place_id.
    expect(html).toContain("Shibuya Sky");
    expect(html).toContain("Meiji Shrine");
    expect(html).not.toContain("node_1");
    expect(html).not.toContain("node_2");
    // Before / after / delta, with the sign shown.
    expect(html).toContain("-35");
    expect(html).toContain("2027-01-03");
    expectNoMissingCopy(html);
  });

  it("renders the same panel in Thai", () => {
    const html = render(<RevisePage />, "th");

    expect(html).toContain("ชิบูยะ สกาย");
    expect(html).toContain("ศาลเจ้าเมจิ");
    expectNoMissingCopy(html);
  });

  it("renders warnings and assumptions through the code catalogue", () => {
    const html = render(<RevisePage />, "en");

    // A stable code must never surface raw.
    expect(html).not.toContain("OPENING_UNVERIFIED");
    expect(html).not.toContain("ACCESS_UNVERIFIED");
    expect(html).not.toContain("EFFORT_OR_TIME_CONFLICT");
  });

  it("offers history and version restore without deleting anything", () => {
    const html = render(<RevisePage />, "en");

    expect(html).toContain("revise-history");
    expect(html).toContain("revise-versions");
    expect(html).toContain("optimizer:best_balance");
    expect(html).toContain("revision:reduce_walking");
  });

  it("blocks apply and says why when the rebuild cannot be applied", () => {
    const blocked = {
      ...DRAFT,
      can_apply: false,
      consequences: { ...DRAFT.consequences, can_apply: false },
    };
    const html = render(<RevisePage />, "en", { [`revision_draft:${TRIP}`]: blocked });

    expect(html).toContain("money-note-warn");
    expect(html).toMatch(/apply[^<]*<\/button>|disabled=""/);
    expectNoMissingCopy(html);
  });

  it("never offers the deferred free-text GenAI surface", () => {
    const html = render(<RevisePage />, "en");

    // Artifact 033 defers constrained GenAI revision past the pilot.
    expect(html).not.toContain("textarea");
    expect(html).not.toContain("interpret");
  });
});
