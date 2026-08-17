import type { Language } from "../i18n/copy";

export interface Trip {
  trip_id: string;
  name: string;
  destination: string;
  planning_mode: "explore_first" | "ready_to_schedule";
  language: "en" | "th";
  created_at: string;
}

export type StageKey = "setup" | "places" | "evidence" | "optimize" | "itinerary";

/** A free Wikidata/Wikipedia summary for one place. `text` may be empty: a place
 *  with no encyclopedia entry gets a visible gap, never an invented sentence. */
export interface PlaceSummary {
  place_id: string;
  qid: string;
  /** Wikidata's label per language — the entity's *name*, which is what a place with no
   *  OpenStreetMap `name:en` is missing. Present even when the place has no Wikipedia
   *  article, so `text` can be empty while this is not. */
  names?: Partial<Record<Language, string>>;
  text: Partial<Record<Language, string>>;
  /** Wikidata's one-line description, which most places have and few have an article
   *  for — 27 of the owner's 64 stored summaries were a photograph with no words. Kept
   *  apart from `text` because it is CC0 rather than CC BY-SA, so the credit differs. */
  description?: Partial<Record<Language, string>>;
  image_url: string | null;
  /** The curated image first, then article photographs. Free, capped at six. */
  image_urls?: string[];
  /** True when the gallery came from Commons geosearch — photographs taken *near* the
   *  coordinates rather than of the place. The screen must say so: a picture of the
   *  next street shown as the place is the kind of quiet claim this app does not make. */
  photos_are_nearby?: boolean;
  licence: string;
  source_urls: Partial<Record<Language, string>>;
}

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

/** One candidate place to stay. `WF-040`. The unit is a transit station, because that
 *  is how accommodation is searched in a metro city and the only unit the app can
 *  measure travel time for exactly. */
export interface StayArea {
  area_id: string;
  name: string;
  names: Record<string, string>;
  latitude: number | null;
  longitude: number | null;
  total_score: number;
  factors: Record<string, { score: number; max: number }>;
  median_travel_minutes: number;
  total_travel_minutes: number;
  reachable_place_count: number;
  counts: { food_count: number; after_dark_count: number; lodging_count: number };
  notes: string[];
}

export interface StayAreaReport {
  areas: StayArea[];
  /** Price, room type, cleanliness and safety. Always present, never scored. */
  not_evaluated: string[];
  reason: string | null;
  place_count: number;
  /** False when Overpass would not answer, so only the two locally-measured factors
   *  contributed. The screen says which half it is showing. */
  amenities_counted: boolean;
  considered_area_count: number;
}

/** One comfort budget, what the plan measures against it, and what was agreed. `WF-039`.
 *  `accepted_value` is the measurement consented to, not a boolean, so `covered` is false
 *  once a replan pushes past what the owner actually saw. */
export interface ComfortRuleState {
  code: string;
  threshold: number | null;
  measured: number | null;
  exceeds: boolean;
  accepted_value: number | null;
  covered: boolean;
}

export interface ComfortTradeoffReport {
  rules: ComfortRuleState[];
  has_plan: boolean;
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
  /** `optimizer._reconciliation` has always written this; the type simply never named
   *  it, so nothing on screen could act on a row — only describe it. */
  place_id: string;
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
  validation: {
    valid: boolean;
    /** Why not, when not. A code starting `UNAPPROVED_` is a comfort budget the owner
     *  can agree to rather than a fault in the plan — the distinction the optimize
     *  screen needs to tell "drop a place" from "accept the figure". */
    hard_violations?: { code: string; subject_id: string | null }[];
    scheduled_visit_count?: number;
    selected_reconciled_count?: number;
    continuous_timeline?: boolean;
  };
  hotel_recommendation?: { default_area_id: string; basis: string } | null;
}

export interface PlanProposal {
  mode: string;
  variants?: PlanVariant[];
  stay_recommendations?: { id: string; days: number; daily_capacity_minutes: number }[];
}

export interface PlanPreview {
  trip_id: string;
  /** The frozen snapshot the proposal was built from. `facts`, `routes` and
   *  `capability_gaps` are read by `/optimize` to say what the draft had to assume —
   *  the snapshot records its own gaps, so the screen reports them rather than
   *  re-deriving a second opinion that could disagree with the plan. */
  optimizer_input: {
    data: {
      candidates?: {
        id?: string;
        name?: string;
        names?: Names;
        /** `selected_place_centroid` when no address was booked. */
        planning_basis?: string;
      }[];
      facts?: { subject_id: string; fact_type: string; status: string; source?: string }[];
      routes?: { status?: string }[];
      capability_gaps?: string[];
    };
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

/** `WF-048`. When to go, from Open-Meteo's recorded weather and published holidays.
 *  Every month is returned and stays selectable: this reports, it does not choose. */
export interface MonthGuideEntry {
  month: number;
  band: "best" | "fair" | "avoid";
  score: number;
  mean_high_c: number;
  mean_low_c: number | null;
  wet_day_percent: number;
  holiday_days: number;
  holiday_names: string[];
  /** Code plus the numbers behind it. The core emits codes; the view renders them. */
  /** The quietest run of `window_days` inside this month, when a length was asked for.
   *  Null where the trip is longer than the month, which is not a window at all. */
  best_window?: {
    start: string;
    end: string;
    holiday_days: number;
    weekend_days: number;
    reasons: { code: string; args: Record<string, string | number> }[];
  } | null;
  pros: { code: string; args: Record<string, string | number> }[];
  cons: { code: string; args: Record<string, string | number> }[];
  advice: { code: string; args: Record<string, string | number> }[];
}

export interface MonthGuide {
  months: MonthGuideEntry[];
  observed_from: string;
  observed_to: string;
  country: string;
  holiday_year: number;
  /** Null where the holiday source does not cover the country — Taiwan and Thailand
   *  both included — so the screen says crowding is unknown rather than implying quiet. */
  holiday_source: string | null;
  window_days?: number;
  sources: string[];
}

/** `WF-047`. Both ways to fill missing opening hours, priced, with the cheap one's
 *  measured error rate beside its price — and whether this trip would read it at all. */
export interface OpeningEvidenceOptions {
  places: number;
  with_verified_hours: number;
  needing_hours: number;
  already_assumed: number;
  verified: { calls: number; estimate_usd: number };
  assumed: {
    calls: number;
    estimate_usd: number;
    measured?: { of: number; exact_both_ends: number; worst_overshoot_minutes: number };
  };
  assumed_is_usable: boolean;
}

/** `WF-048`. Drawn street/water/park geometry for the window discovery searched, as
 *  rounded [lat, lon] polylines. No tiles: fetched once, stored, drawn locally. */
export interface Basemap {
  roads: [number, number][][];
  water: [number, number][][];
  green: [number, number][][];
  attribution: string;
  license: string;
}

/** `WF-048`. One zoomed-in window's map, in the layers a street map is read in.
 *  Everything empty with `too_wide` when the caller asked for more ground than any of
 *  it could be drawn on. */
/** `WF-048`. The destination country's own boundary, simplified server-side, so the map
 *  can be zoomed out until a place is seen in its country rather than only its city. */
export interface CountryOutline {
  country: string;
  rings: [number, number][][];
}

/** `WF-048`. The real weather for the trip's own dates, where they are near enough to
 *  know. `covered` is false beyond the forecast horizon, which is the true answer. */
export interface TripForecast {
  days: {
    date: string;
    high_c: number | null;
    low_c: number | null;
    rain_chance: number | null;
    rain_mm: number | null;
  }[];
  covered: boolean;
  trip_start: string | null;
  trip_end: string | null;
  horizon_end: string | null;
}

/** `WF-048`. The walking paths held for a trip — the picture of a route, as opposed to
 *  `list_routes`, which is the optimizer's view of one: a duration and a distance. */
export interface RouteShapes {
  shapes: {
    origin_id: string;
    destination_id: string;
    mode: string;
    points: [number, number][];
  }[];
}

export interface MapDetail {
  bbox: number[];
  /** Building footprints, as closed rings of `[latitude, longitude]`. */
  buildings: [number, number][][];
  /** The road network, carrying the `highway` class that gives it its hierarchy and
   *  both spellings of its name for the label that runs along it. */
  roads: {
    class: string;
    name: string;
    name_en: string;
    oneway: boolean;
    reversed: boolean;
    points: [number, number][];
  }[];
  /** Land use and landcover: parks, water, retail, residential, and the rest. */
  areas: { kind: string; points: [number, number][] }[];
  /** Metro, rail and tram alignments. */
  rails: { class: string; name: string; points: [number, number][] }[];
  /** Station entrances, bus stops and charging points. */
  markers: { kind: string; point: [number, number]; name: string }[];
  too_wide: boolean;
}

export interface ChecklistVocabulary {
  categories: string[];
  requirement_levels: string[];
  timing_buckets: string[];
  progress_states: string[];
  evidence_states: string[];
  authority_types: string[];
  closed_states: string[];
}

/** A board item. `title`/`consequence` are stored literals; the codes localize them. */
export interface ChecklistItem {
  item_id: string;
  title: string;
  title_args?: Record<string, string | number> | null;
  template_id?: string | null;
  consequence?: string | null;
  consequence_code?: string | null;
  category: string;
  timing: string;
  requirement_level: string;
  progress: string;
  evidence_state: string;
  due_date?: string | null;
  note?: string | null;
  source_url?: string | null;
  expected_authority?: string | null;
  authority_type?: string | null;
  last_checked_at?: string | null;
  origin?: string | null;
  generated_key?: string | null;
  dismissed: boolean;
  updated_at?: string;
}

export interface ChecklistProposal {
  proposed: ChecklistItem[];
  additions: ChecklistItem[];
  removals: ChecklistItem[];
  deadline_changes: {
    title: string;
    from: { due_date?: string | null };
    to: { due_date?: string | null };
  }[];
  unchanged: number;
}

export interface ChecklistReadiness {
  state: string;
  /** Always false by decision: readiness warnings never gate the itinerary. */
  blocks_itinerary: boolean;
  counts: Record<string, number>;
  due_soon: unknown[];
  overdue: unknown[];
}

export interface QuickAction {
  operation: string;
  arguments: Record<string, string | number>;
}

export interface MetricDelta {
  before: number;
  after: number;
  delta: number;
}

export interface RevisionConsequences {
  changed_dates: string[];
  metrics: Record<string, MetricDelta>;
  moved: { place_id: string; from: { date: string; start: string }; to: { date: string; start: string } }[];
  added: string[];
  removed: string[];
  shortened: { place_id: string; from_minutes: number; to_minutes: number }[];
  lengthened: { place_id: string; from_minutes: number; to_minutes: number }[];
  displaced: { place_id: string; reason: string }[];
  warnings: { new: string[]; cleared: string[] };
  can_apply: boolean;
}

export interface RevisionDraft {
  operation: string;
  arguments?: Record<string, string | number>;
  assumptions?: string[];
  explanation?: {
    variant_id: string;
    status: string;
    metrics: Record<string, number>;
    unscheduled: { place_id: string; reason: string }[];
  } | null;
  consequences?: RevisionConsequences | null;
  can_apply?: boolean;
}

export interface RevisionInterpretationResult {
  supported: boolean;
  operation: string | null;
  clarification: string | null;
  unsupported_reason: string | null;
  model?: string | null;
  draft: RevisionDraft | null;
}

export interface RevisionRecord {
  created_at: string;
  operation: string;
  from_version_id: string;
  to_version_id: string;
}

export interface PlanVersionRecord {
  version_id: string;
  trip_id: string;
  cause: string;
  created_at: string;
}

/** `WF-045`. Whether the evidence under the activated plan has moved, and whether that
 *  broke anything. `claimed_valid` is what the plan said when it was built and
 *  `still_valid` is what today's evidence says — they are reported together so they can
 *  be seen to disagree. */
export interface PlanDrift {
  version_id: string;
  moved: boolean;
  claimed_valid: boolean;
  still_valid: boolean;
  violations: { code: string; subject_id: string | null }[];
  stored_input_sha256: string;
  current_input_sha256: string;
}

/** `WF-044`. A dated closure notice quoted from a venue's own page. Advisory only: it is
 *  stored under a kind the optimizer does not read, so it can never remove a place from a
 *  plan. `quote` is verified to appear verbatim on the fetched page. */
export interface VenueNotice {
  place_id: string;
  name: string;
  quote: string;
  summary: string | null;
  source_url: string;
  model?: string | null;
}

export interface AccommodationBase {
  name: string;
  address?: string | null;
  latitude: number;
  longitude: number;
  /** True when the base sits further than `ACCOMMODATION_BASE_TOO_FAR_KM` from every
   *  chosen place, which is a geocoding accident rather than a stay. */
  implausible?: boolean;
  /** False when `_optimizer_input` discarded it, so no screen calls it the plan's base. */
  used_by_planner?: boolean;
}

export interface TimezoneEvidence {
  status: string;
  timezone: string;
  timezone_name?: string;
  retrieved_at?: string;
  expires_at?: string;
}

export interface PaidUsageStatus {
  month: string;
  estimated_usd: number;
  spent_usd: number;
  cap_usd: number;
  warn_at_usd: number;
  remaining_usd: number;
  requests: number;
  state: string;
  cap_is_owner_raised: boolean;
  by_operation: Record<string, unknown>;
  entries: unknown[];
}

/** place_id -> the usable window, or the stable reason there is none. */
export type OpeningIntervals = Record<
  string,
  { interval: { start: string; end: string } | null; reason: string; retrieved_at?: string | null }
>;

export interface RouteRecord {
  origin_id: string;
  destination_id: string;
  mode: string;
  status: string;
  duration_minutes?: number;
  walking_minutes?: number;
  distance_m?: number;
  transfers?: number;
  provider?: string;
  retrieved_at?: string;
  expires_at?: string;
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
