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
  label?: string;
  age?: number | null;
  tags?: string[];
  description?: string;
  must_respect?: string[];
  nationality?: string | null;
}

export interface SetupPayload {
  planning_mode?: string;
  trip_basics?: {
    start_date?: string | null;
    end_date?: string | null;
    arrival_time?: string | null;
    departure_time?: string | null;
    accommodation_status?: string;
  };
  owner?: {
    age?: number | null;
    main_style?: string[];
    also_enjoy?: string[];
    avoid?: string[];
    comfort?: string[];
    description?: string;
    must_respect?: string[];
    nationality?: string | null;
  };
  travellers?: SetupMember[];
  group_preference_weights?: Record<string, number>;
}

export interface SetupDraft {
  trip_id: string;
  snapshot: { data: SetupPayload; sha256: string };
  confirmed: boolean;
  updated_at: string;
}

export interface SetupVocabulary {
  planning_modes: string[];
  accommodation_statuses: string[];
  tag_groups: {
    main_style: string[];
    also_enjoy: string[];
    avoid: string[];
    comfort: string[];
  };
  countries: { code: string; label: { en: string; th: string }; cities: string[] }[];
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

export interface CandidateChoice {
  trip_id: string;
  place_id: string;
  discovery_run_id?: string;
  action: string;
  reason: string | null;
  candidate?: Frozen<Record<string, unknown>>;
  updated_at?: string;
}

export interface Frozen<T> {
  data: T;
  sha256: string;
}

export type Names = Record<string, string | undefined>;

export interface DiscoveryCandidate {
  place_id: string;
  name: string;
  names?: Names;
  latitude: number | null;
  longitude: number | null;
  category: string;
  address?: string | null;
  website?: string | null;
  photo_reference?: string | null;
  provider_aliases: { provider: string; provider_place_id: string; source_url?: string | null }[];
  operational_evidence: {
    opening_hours: { value?: unknown; state: string };
    best_time?: { value?: unknown; state: string };
    access?: { value?: unknown; state: string };
  };
}

export interface DiscoveryReport {
  canonical_candidates: number;
  duplicates_merged: number;
  geographic_cells_with_candidates: number;
  attribution?: string | null;
  license?: string | null;
  license_url?: string | null;
  [key: string]: unknown;
}

export interface DiscoveryRun {
  run_id: string;
  trip_id: string;
  setup_sha256: string;
  provider: string;
  status: string;
  candidates: Frozen<{ candidates: DiscoveryCandidate[] }>;
  report: Frozen<DiscoveryReport>;
  created_at: string;
}

export interface RankingCard {
  place_id: string;
  total_score: number;
  dimensions: Record<string, { score: number; max: number }>;
  deductions: { code: string; points: number }[];
  candidate_tags: string[];
  matched_tags: string[];
  matched_people: string[];
  experience_value: number;
  is_city_icon: boolean;
  why_shown: string[];
  pros: string[];
  cons: string[];
  duration_estimate: { minimum_minutes: number; maximum_minutes: number; origin: string };
  feasibility: { state: string; reason: string };
  choice_action: string | null;
}

export interface RankingLaneEntry {
  place_id: string;
  role?: string;
  alternative_to?: string;
}

export interface Ranking {
  cards: Record<string, RankingCard>;
  lanes: {
    main_queue: RankingLaneEntry[];
    city_icons: string[];
    worth_it_if: string[];
    local_alternatives: RankingLaneEntry[];
    browse_all: string[];
  };
  coverage: Record<string, number>;
}

export interface PaidCallCheck {
  allowed: boolean;
  estimate_usd: number;
  projected_usd: number;
  cap_usd: number;
  reason: string | null;
}

export interface PlaceInsight {
  rating?: number | null;
  user_rating_count?: number;
  google_maps_uri?: string | null;
  photo_uri?: string | null;
  photo_gallery?: { uri: string; authors?: { name?: string; uri?: string }[] }[];
  review_summary?: {
    text?: string | null;
    disclosure?: string | null;
    reviews_uri?: string | null;
    flag_uri?: string | null;
  };
  reviews?: {
    text: string;
    rating?: number | null;
    published?: string | null;
    author?: string | null;
    author_uri?: string | null;
  }[];
}

export interface PlanItem {
  type: string;
  start: string;
  end: string;
  duration_minutes: number;
  name?: string;
  names?: Names;
}

export interface PlanDay {
  date: string;
  items: PlanItem[];
}

export interface Reconciliation {
  name: string;
  names?: Names;
  priority: string;
  status: string;
  reason: string;
  consequence: string;
}

export interface PlanVariant {
  variant_id: string;
  status: string;
  metrics: Record<string, number>;
  warnings: string[];
  reconciliation: Reconciliation[];
  days: PlanDay[];
  stopped_at_limit: boolean;
  objective_improved_or_equal_to_greedy: boolean;
  validation: { valid: boolean };
  hotel_recommendation?: { default_area_id: string; basis: string } | null;
}

export interface PlanProposal {
  mode: string;
  variants?: PlanVariant[];
  stay_recommendations?: { id: string; days: number; daily_capacity_minutes: number }[];
}

export interface PlanPreview {
  trip_id: string;
  optimizer_input: {
    data: { candidates?: { id?: string; name?: string; names?: Names }[] };
    sha256: string;
  };
  proposal: { data: PlanProposal; sha256: string };
  created_at: string;
}

export type PlanItemType = "visit" | "travel" | "meal" | "preparation" | "logistics" | "buffer";

export interface ExportPlanItem {
  order: number;
  item_id: string;
  type: PlanItemType;
  subject_id: string;
  date: string;
  start: string;
  end: string;
  duration_minutes: number;
  status: string;
  stop_number?: number;
  display_name?: string;
  names?: Names;
  local_name?: string | null;
  kind?: string | null;
  priority?: string | null;
  address?: string | null;
  opening_verified?: boolean;
  origin_name?: string;
  destination_name?: string;
  mode?: string | null;
  walking_minutes?: number;
  distance_m?: number | null;
  transfers?: number | null;
  boarding_buffer_minutes?: number;
  sightseeing_walk?: boolean;
  notes?: string;
  from_name?: string | null;
  to_name?: string | null;
  reason?: string | null;
}

export interface ExportStop {
  stop_number: number;
  subject_id: string;
  display_name: string;
  latitude: number | null;
  longitude: number | null;
  status: string;
}

export interface ExportFallback {
  primary_id: string;
  fallback_id: string;
  trigger: string;
  date: string | null;
  half_day: "morning" | "afternoon" | null;
  primary_name: string;
  replacement_name: string;
  replacement_start: string | null;
  displaced_reason?: string | null;
  displaced_consequence?: string | null;
}

export interface ExportDay {
  date: string;
  start: string;
  end: string;
  items: ExportPlanItem[];
  stops: ExportStop[];
  fallbacks: ExportFallback[];
  totals: Record<string, number>;
  highest_risk: { status: string; item_id: string; subject_id: string } | null;
}

export interface ExportSnapshot {
  stamp: {
    plan_version_id: string;
    is_active_plan: boolean;
    variant_id: string;
    variant_status: string;
    language: string;
    base_currency: string;
    exported_at: string;
    capability_gaps: string[];
  };
  readiness: { state: string; variant_status: string; capability_gaps: string[] };
  days: ExportDay[];
  unscheduled: {
    place_id: string;
    display_name: string;
    priority: string;
    reason: string;
    consequence: string;
  }[];
  checklist: { items: unknown[] };
  accommodation: {
    status: string;
    anchor: {
      subject_id: string;
      display_name: string;
      latitude: number | null;
      longitude: number | null;
    } | null;
  };
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
