import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { CostItem, CostTotals, SetupDraft, SplitRow, SplitSummary } from "../api/client";
import type { Language } from "../i18n/copy";
import { LanguageProvider } from "../i18n/LanguageProvider";
import { CostsPage } from "./CostsPage";
import { SplitPage } from "./SplitPage";

const TRIP = "taipei";

const SETUP = {
  trip_id: TRIP,
  snapshot: {
    data: {
      travellers: [
        { traveller_id: "member_1", label: "Mum" },
        { traveller_id: "member_2", label: "Dad" },
      ],
    },
    sha256: "abc",
  },
  confirmed: true,
  updated_at: "now",
} satisfies SetupDraft;

const TOTALS = {
  base_currency: "THB",
  estimated_thb: 1800,
  paid_thb: 11450,
  total_thb: 13250,
  by_category: { accommodation: 11450, activity: 1800 },
  rows: 3,
  unconvertible_rows: 3,
  missing_rates: ["TWD"],
  planned_thb: 37700,
  actual_thb: 29690,
  by_category_comparison: {
    accommodation: {
      planned_thb: 12000,
      actual_thb: 11450,
      difference_thb: -550,
      planned: true,
      actual: true,
    },
    activity: {
      planned_thb: 8400,
      actual_thb: 9120,
      difference_thb: 720,
      planned: true,
      actual: true,
    },
    fees: {
      planned_thb: 1800,
      actual_thb: 0,
      difference_thb: -1800,
      planned: true,
      actual: false,
    },
    food: { planned_thb: 0, actual_thb: 6880, difference_thb: 6880, planned: false, actual: true },
  },
  claimed_cost_ids: ["cost_hotel"],
  unclaimed_paid_rows: 2,
  categories_without_plan: ["food"],
  planned_per_person_thb: 12566.67,
} satisfies CostTotals;

const COST_ITEMS = [
  {
    cost_id: "cost_hotel",
    label: "Hotel · 5 nights",
    category: "accommodation",
    original_amount: 12000,
    original_currency: "THB",
    payment_state: "paid",
    actual_thb: 11450,
    converted_thb: 12000,
    reported_thb: 11450,
    rate_missing: false,
  },
  {
    cost_id: "cost_ticket",
    label: "Taipei 101 observatory",
    category: "activity",
    original_amount: 1800,
    original_currency: "THB",
    payment_state: "estimate",
    actual_thb: null,
    converted_thb: 1800,
    reported_thb: 1800,
    rate_missing: false,
  },
] satisfies CostItem[];

const SUMMARY = {
  base_currency: "THB",
  cardholder: "owner",
  actual_thb: 29690,
  by_category: { accommodation: 11450, food: 6880, transport: 2240 },
  rows: 8,
  voided_rows: 1,
  balances: [
    { traveller_id: "owner", shares_thb: 9180, paid_out_thb: 20290, net_thb: -11110 },
    { traveller_id: "member_1", shares_thb: 6240, paid_out_thb: 1000, net_thb: 5240 },
    { traveller_id: "member_2", shares_thb: 6120, paid_out_thb: 8400, net_thb: -2280 },
  ],
  settlement: [
    {
      traveller_id: "member_1",
      shares_thb: 6240,
      paid_out_thb: 1000,
      net_thb: 5240,
      amount_thb: 5240,
      direction: "traveller_pays_cardholder",
      settled: true,
    },
    {
      traveller_id: "member_2",
      shares_thb: 6120,
      paid_out_thb: 8400,
      net_thb: -2280,
      amount_thb: 2280,
      direction: "cardholder_pays_traveller",
      settled: false,
    },
  ],
  unconvertible_rows: 0,
  missing_rates: [],
} satisfies SplitSummary;

const SPLIT_ROWS = [
  {
    split_id: "split_1",
    label: "Hotel · night 1",
    mode: "equal_all",
    paid_by: "owner",
    participants: ["owner", "member_1", "member_2"],
    tag: "accommodation",
    category: "accommodation",
    original_amount: 2045,
    original_currency: "TWD",
    actual_thb: null,
    converted_thb: 2290,
    reported_thb: 2290,
    rate_missing: false,
    cost_id: "cost_hotel",
    plan_day: null,
    place_id: null,
    voided: false,
  },
  {
    split_id: "split_2",
    label: "Longshan Temple donation",
    mode: "equal_all",
    paid_by: "owner",
    participants: ["owner"],
    tag: "fees",
    category: "fees",
    original_amount: 224,
    original_currency: "THB",
    actual_thb: null,
    converted_thb: 224,
    reported_thb: 224,
    rate_missing: false,
    cost_id: null,
    plan_day: null,
    place_id: null,
    voided: true,
  },
] satisfies SplitRow[];

function render(page: ReactNode, language: Language): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["cost_totals", TRIP], TOTALS);
  client.setQueryData(["cost_items", TRIP], COST_ITEMS);
  client.setQueryData(["setup", TRIP], SETUP);
  client.setQueryData(["split_summary", TRIP], SUMMARY);
  client.setQueryData(["split_rows", TRIP], SPLIT_ROWS);
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

// A copy() miss renders as `⚠ <code>`, so this catches any key that exists in
// one language and not the other.
function expectNoMissingCopy(html: string): void {
  expect(html).not.toMatch(/⚠ [a-z][a-z0-9_]{3,}/);
}

describe("CostsPage", () => {
  it("offers a way to record an estimate, which it previously only asked for", () => {
    // The screen had zero mutations: it said "add estimates to see the plan against
    // actual spend" and gave no means, while save_cost_item was allowlisted and
    // unreachable. So the comparison could only ever compare nothing.
    const html = render(<CostsPage />, "en");
    expect(html).toContain("Record an estimate");
    expect(html).toContain("What is it for");
    expect(html).toContain("Amount");
    expect(html).toMatch(/inputMode="decimal" min="0"[^>]*step="0.01" type="number"/);
    expect(html).toContain('type="submit"');
    expect(html).toContain("Edit");
    expectNoMissingCopy(html);
  });

  it("renders the planned-versus-actual comparison in English", () => {
    const html = render(<CostsPage />, "en");

    expect(html).toContain("Planned cost");
    expect(html).toContain("Planned per person");
    expect(html).toContain("12,566.67");
    expect(html).toContain("37,700");
    expect(html).toContain("29,690");
    expectNoMissingCopy(html);
  });

  it("renders the same screen in Thai", () => {
    const html = render(<CostsPage />, "th");

    expect(html).toContain("ค่าใช้จ่ายที่วางแผน");
    expect(html).toContain("ต่อคน (ประมาณ)");
    expect(html).toContain("แยกตามหมวด");
    // Numbers keep one shape in both languages.
    expect(html).toContain("37,700");
    expectNoMissingCopy(html);
  });

  it("distinguishes a category with no plan from one that spent nothing", () => {
    const html = render(<CostsPage />, "en");

    // fees planned 1,800 with no actual, food spent 6,880 with no plan:
    // neither renders as a misleading zero, and neither difference is coloured
    // as over or under, because there is nothing to compare against.
    expect(html).toContain("Spending with no plan in:");
    expect(html).toMatch(/1,800<\/td><td class="money-num">—/);
    expect(html).toMatch(/—<\/td><td class="money-num">6,880/);
    expect(html).not.toMatch(/money-(over|under)">—/);
  });

  it("warns about unclaimed paid rows and a missing rate without blocking", () => {
    const html = render(<CostsPage />, "en");

    // Counted wording is label-first so it reads correctly at 1 as well as 2,
    // without a plural rule Thai would never use.
    expect(html).toContain("Unclaimed paid cost rows: 2");
    expect(html).toContain("TWD");
    expect(html).toContain("claimed by the split ledger");
    // A claimed row's own actual is superseded, and the screen says so.
    expect(html).toContain("Its actual comes from the split rows that claim it");
  });
});

describe("SplitPage", () => {
  it("renders the settlement in English with the reversed direction", () => {
    const html = render(<SplitPage />, "en");

    expect(html).toContain("Group spend");
    expect(html).toContain("These are suggestions, not debts.");
    expect(html).toContain("Mum pays you");
    // The cardholder owing a traveller is the surprising case, so it is marked.
    expect(html).toContain("You pay Dad");
    expect(html).toContain("money-reversed");
    expect(html).toContain("so the cardholder owes them");
    expect(html).toContain("2,280");
    expectNoMissingCopy(html);
  });

  it("renders the same screen in Thai", () => {
    const html = render(<SplitPage />, "th");

    expect(html).toContain("ค่าใช้จ่ายกลุ่ม");
    expect(html).toContain("นี่คือข้อเสนอแนะ ไม่ใช่ยอดหนี้");
    expect(html).toContain("จ่ายคืนคุณ");
    expect(html).toContain("คุณจ่ายคืน");
    expectNoMissingCopy(html);
  });

  it("keeps a voided row visible and struck through", () => {
    const html = render(<SplitPage />, "en");

    expect(html).toContain("Longshan Temple donation");
    expect(html).toContain("money-row voided");
    expect(html).toContain("removed · kept visible so the total can be explained");
    expect(html).toContain("Restore");
  });

  it("rails a row that claims a planned cost row", () => {
    const html = render(<SplitPage />, "en");

    expect(html).toContain("linked");
    expect(html).toContain("linked to a planned row");
  });

  it("shows a settled marker without changing the balance it describes", () => {
    const html = render(<SplitPage />, "en");

    // Mum is marked settled and her 5,240 still reads, because payments
    // between people are never recorded.
    expect(html).toContain("money-settled");
    expect(html).toContain("Settled");
    expect(html).toContain("5,240");
  });

  it("names the two per-person numbers as different sums", () => {
    const html = render(<SplitPage />, "en");

    expect(html).toContain("12,566.67");
    expect(html).toContain("9,180");
    expect(html).toContain("They are different sums.");
  });
});
