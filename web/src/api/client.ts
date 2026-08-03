export interface Trip {
  trip_id: string;
  name: string;
  destination: string;
  planning_mode: "explore_first" | "ready_to_schedule";
  language: "en" | "th";
  created_at: string;
}

export type StageKey = "setup" | "places" | "evidence" | "optimize" | "itinerary";

export interface JourneyStage {
  key: StageKey;
  done: boolean;
  blocked_by: StageKey | null;
}

export interface Journey {
  stages: JourneyStage[];
  next: StageKey;
  capability_gaps: string[];
  has_active_plan: boolean;
  choice_count: number;
}

export interface SetupMember {
  traveller_id: string;
  label: string;
}

export interface SetupDraft {
  trip_id: string;
  snapshot: { data: { travellers?: SetupMember[] }; sha256: string };
  confirmed: boolean;
  updated_at: string;
}

export interface CostItem {
  cost_id: string;
  label: string;
  category: string;
  original_amount: number;
  original_currency: string;
  payment_state: "estimate" | "committed" | "paid";
  actual_thb: number | null;
  converted_thb: number | null;
  reported_thb: number | null;
  rate_missing: boolean;
}

export interface CategoryComparison {
  planned_thb: number;
  actual_thb: number;
  difference_thb: number;
  planned: boolean;
  actual: boolean;
}

export interface CostTotals {
  base_currency: string;
  estimated_thb: number;
  paid_thb: number;
  total_thb: number;
  by_category: Record<string, number>;
  rows: number;
  unconvertible_rows: number;
  missing_rates: string[];
  planned_thb: number;
  actual_thb: number;
  by_category_comparison: Record<string, CategoryComparison>;
  claimed_cost_ids: string[];
  unclaimed_paid_rows: number;
  categories_without_plan: string[];
  planned_per_person_thb: number | null;
}

export type SplitMode = "equal_all" | "selected" | "single_payer";

export interface SplitRow {
  split_id: string;
  label: string;
  mode: SplitMode;
  paid_by: string;
  participants: string[];
  tag: string;
  category: string;
  original_amount: number;
  original_currency: string;
  actual_thb: number | null;
  converted_thb: number | null;
  reported_thb: number | null;
  rate_missing: boolean;
  cost_id: string | null;
  plan_day: string | null;
  place_id: string | null;
  voided: boolean;
}

export interface Balance {
  traveller_id: string;
  shares_thb: number;
  paid_out_thb: number;
  net_thb: number;
}

export interface Settlement extends Balance {
  amount_thb: number;
  direction: "traveller_pays_cardholder" | "cardholder_pays_traveller";
  settled: boolean;
}

export interface SplitSummary {
  base_currency: string;
  cardholder: string;
  actual_thb: number;
  by_category: Record<string, number>;
  rows: number;
  voided_rows: number;
  balances: Balance[];
  settlement: Settlement[];
  unconvertible_rows: number;
  missing_rates: string[];
}

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly detail: unknown,
  ) {
    super(code);
  }
}

export async function rpc<T>(method: string, payload: Record<string, unknown> = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);
  try {
    const response = await fetch(`/api/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const value = (await response.json()) as T | { code?: string; detail?: unknown };
    if (!response.ok) {
      const error = value as { code?: string; detail?: unknown };
      throw new ApiError(error.code ?? "internal_error", error.detail);
    }
    return value as T;
  } finally {
    clearTimeout(timeout);
  }
}
