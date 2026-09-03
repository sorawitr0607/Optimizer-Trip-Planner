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
  /** The date Wikidata records this place as closed, or absent when it records none.
   *
   *  A signal, never a filter. Read from `P3999` ("date of official closure") and
   *  item-level `P582` ("end time") — claims the app already fetches for photographs, so
   *  it costs no request. `P576` is deliberately not read: measured over 500 candidate
   *  QIDs it flagged Edo Castle, an open museum and a monument, because historic sites
   *  are visited precisely because the original structure is gone.
   *
   *  Wikidata's own precision, so `2020-00-00` means "2020, month unknown". */
  closed_on?: string | null;
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
    /** The hours the owner wants to be out. `_optimizer_input` used to invent these;
     *  `setup.DEFAULT_ACTIVE_*` still supplies them for a draft saved before the field. */
    active_start?: string | null;
    active_end?: string | null;
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
  related_item_id?: string | null;
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
  category?: string;
  total_score: number;
  /** Percentile inside this trip's current catalogue; unlike `total_score`, this is
   *  suitable for a comparative "fit" label on the swipe card. */
  relative_match_percent?: number;
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
  /** Which effort evidence backs the score. Cards currently know estimated visit time;
   *  walking, transfers, cost and fatigue belong to the optimizer. */
  effort_state?: string;
  /** Metres from the discovery centre; null where the centre is unknown. */
  distance_from_centre_metres?: number | null;
  /** True past FAR_FROM_CENTRE_M — an hour-out place in a local evening. */
  far_from_centre?: boolean;
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

export interface RankedDiscovery {
  discovery: DiscoveryRun | null;
  ranking: Ranking | null;
  provider_no_match: string[];
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
  reason?: string;
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
        duration_bounds?: {
          minimum_minutes?: number;
          ideal_minutes?: number;
          maximum_minutes?: number;
        };
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
  photo_reference?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  /** The ranking card's `total_score` for this place, carried through
   *  `actions._optimizer_input` and the optimizer onto the exported row. Out of 100, so
   *  it renders as the same "% match" the deck shows -- one number, two screens. Absent
   *  or 0 on synthetic rows (meals, logistics, buffers), which is why it is optional. */
  score?: number | null;
}

export interface ExportStop {
  stop_number: number;
  subject_id: string;
  display_name: string;
  latitude: number | null;
  longitude: number | null;
  status: string;
  /** OpenStreetMap's own photo tag, carried here so the itinerary never has to read the
   *  discovery run -- whose `candidates_json` is ~390 KB -- to show a picture. */
  photo_reference?: string | null;
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
  retrieved_at?: string;
  expires_at?: string;
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

/**
 * Who this browser is, for a deployment more than one person uses.
 *
 * A random value kept in `localStorage`, sent on every call, and that is the whole
 * mechanism -- no account, which is the product's promise, and no login to build.
 * It is not a credential and is not offered as one: whoever holds the token holds
 * the trips, exactly as whoever holds a share link holds what it points at. What it
 * fixes is the accidental case, which was the entire problem. Without it
 * `list_trips` returned every visitor's trips and `/` opened inside whichever was
 * newest -- someone else's travellers, ages and accommodation address.
 *
 * `crypto.randomUUID` where it exists; a random string where it does not, because
 * the value only has to be unlikely to collide across ten people.
 */
export const OWNER_KEY = "planner.owner";

/** The one credential that is a credential: proves the right to raise the global
 *  spend cap. Typed by the owner once, kept beside the owner token, sent as
 *  `X-Planner-Admin`; the server compares it against `TOURIST_ADMIN_KEY`. Unlike
 *  the owner token this is offered as a secret — `set_paid_cap` is the single
 *  action whose effect is deployment-wide. */
export const ADMIN_KEY = "planner.admin";

export function setAdminKey(key: string): void {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(ADMIN_KEY, key.trim());
}

function adminToken(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(ADMIN_KEY) ?? "";
}

function ownerToken(): string {
  if (typeof localStorage === "undefined") return "";
  const held = localStorage.getItem(OWNER_KEY);
  if (held) return held;
  const minted = typeof crypto?.randomUUID === "function"
    ? crypto.randomUUID()
    : `own_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
  localStorage.setItem(OWNER_KEY, minted);
  return minted;
}

/** How often to ask whether a queued job has finished. Discovery is 30-90s and a
 *  proposal about 52s, so a poll a second is roughly sixty questions for one
 *  answer; 1.5s keeps it under forty and still feels immediate at the end. */
const JOB_POLL_MS = 1_500;

/** Give up after five minutes of **silence**, not five minutes of work.
 *
 * The intent was always "fire when the worker is down, not when the work is slow",
 * and as a flat ceiling on total runtime it did not do that. `refresh_routes` sweeps
 * up to twelve capped passes in one job now; a measured run stored 462 routes in
 * **843 seconds**, finished perfectly, and the browser had already given up on it at
 * 300 — reporting `job_timeout` for work that succeeded.
 *
 * So the clock is reset every time the job says something new. An operation in
 * `jobs.REPORTS_PROGRESS` reports a rising count, and `run_one` writes a `0` the
 * moment a worker claims the job, so the reset also covers the wait to be picked up:
 * five minutes with nobody claiming it still fails, which is the case worth
 * reporting. An operation that reports nothing keeps the flat five minutes it always
 * had, and every operation is bounded server-side anyway — `MAX_ROUTE_PASSES`,
 * `DISCOVERY_BUDGET_SECONDS`, and one time limit per variant. */
const JOB_TIMEOUT_MS = 300_000;

interface JobEnvelope {
  job_id: string;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  /** How many of the operation's stages have returned, or null when it does not
   *  describe itself and while it is still queued behind a worker. */
  progress: number | null;
  result: unknown;
}

async function post(
  method: string,
  payload: Record<string, unknown>,
  timeoutMs: number,
): Promise<{ status: number; value: unknown }> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`/api/${method}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // Belt and braces for a hosted deployment, where one rewrite points every
        // /api/* at a single function. If a platform ever forwards the rewritten
        // path instead of the requested one, the server reads the method here
        // rather than dispatching every call to the same wrong name.
        "X-Planner-Method": method,
        "X-Planner-Owner": ownerToken(),
        "X-Planner-Admin": adminToken(),
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const body = await response.text();
    // Whether a body arrived, kept apart from what it parsed to: `null` is a real
    // answer here. delete_trip, clear_candidate_choice, delete_cost_item and
    // discard_revision_draft all return it on success, and reading a parsed null
    // as "empty" makes every successful delete throw.
    const hasBody = body.trim().length > 0;
    let value: unknown = null;
    if (hasBody) {
      try {
        value = JSON.parse(body) as unknown;
      } catch {
        value = body;
      }
    }
    if (!response.ok) {
      const error = value && typeof value === "object" ? (value as { code?: string; detail?: unknown }) : null;
      throw new ApiError(
        error?.code ?? `http_${response.status}`,
        error?.detail ?? (typeof value === "string" && value.trim() ? value : response.statusText || "The API returned an empty response"),
      );
    }
    if (!hasBody) {
      throw new ApiError("empty_response", "The API returned an empty response");
    }
    return { status: response.status, value };
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Call one method and return its answer, whether the server does the work or queues it.
 *
 * `onProgress` is how a caller sees inside a queued operation. Every poll below already
 * holds the job row, and the operations in `jobs.REPORTS_PROGRESS` write a count of the
 * stages they have finished into it -- so this hands over a fact the loop was throwing
 * away, on the same rule `BuildStages` draws: a number goes up because a call came back.
 *
 * It fires only against a deployment that queues. The local server runs the same work
 * inline and answers 200, so a caller there is never told anything and must have
 * something honest to show for that -- `Thinking`, in every case so far.
 */
export async function rpc<T>(
  method: string,
  payload: Record<string, unknown> = {},
  onProgress?: (reached: number) => void,
): Promise<T> {
  const first = await post(method, payload, 120_000);

  // 202 means the server queued the work instead of doing it. Three operations
  // are too slow for a serverless function's time limit, so they return a job id
  // and a worker runs them elsewhere. Polling lives here rather than at each call
  // site: every caller wants the answer, not the receipt, and the local server --
  // which runs the same work inline and answers 200 -- never reaches this branch.
  if (first.status !== 202) return first.value as T;

  const { job_id: jobId } = first.value as { job_id: string };
  let deadline = Date.now() + JOB_TIMEOUT_MS;
  let reported: number | null = null;
  for (;;) {
    await new Promise((resume) => setTimeout(resume, JOB_POLL_MS));
    let value: unknown;
    try {
      value = (await post("job_status", { job_id: jobId }, 30_000)).value;
    } catch (error) {
      // "Failed to fetch" while the build was running, reported by the owner.
      //
      // A build is 30-90 seconds and this polls every 1.5, so a single run asks about
      // sixty times. `fetch` rejects with a bare `TypeError: Failed to fetch` for
      // anything below HTTP -- a Vercel cold start closing an idle socket, a DNS
      // blip, a phone changing network -- and one such rejection anywhere in that
      // sequence threw out of the loop and failed the whole build. The work itself was
      // usually finishing perfectly on the worker, exactly as with the 843-second
      // discovery that `JOB_TIMEOUT_MS` above documents.
      //
      // A poll is a pure read of a row a worker owns, so asking again is always safe
      // and costs one more request. Only network-level failures are swallowed: an
      // `ApiError` means the server answered -- 404 unknown_job, 403 not_your_trip --
      // and repeating that would hide a real refusal behind a five-minute wait.
      //
      // Nothing new bounds this. `deadline` is unchanged and still fails a job that
      // has genuinely stopped reporting, which is the case worth surfacing.
      if (error instanceof ApiError) throw error;
      if (Date.now() > deadline) {
        throw new ApiError("job_unreachable", {
          job_id: jobId,
          detail: error instanceof Error ? error.message : String(error),
        });
      }
      continue;
    }
    const job = value as JobEnvelope;
    // Before the exits, so the last count reported still reaches the caller on the
    // poll that also carries the result.
    if (typeof job.progress === "number") {
      if (job.progress !== reported) {
        // News. Whatever else is true, this job is not abandoned, so the clock that
        // exists to catch abandonment starts again.
        reported = job.progress;
        deadline = Date.now() + JOB_TIMEOUT_MS;
      }
      onProgress?.(job.progress);
    }
    if (job.status === "done") return job.result as T;
    if (job.status === "failed") throw new ApiError(job.error ?? "job_failed", { job_id: jobId });
    if (Date.now() > deadline) throw new ApiError("job_timeout", { job_id: jobId });
  }
}
