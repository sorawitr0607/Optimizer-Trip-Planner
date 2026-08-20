import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { Thinking } from "../shared/Thinking";
import { ComfortTradeoffs } from "./ComfortTradeoffs";
import { StayPlanner } from "./StayPlanner";

import {
  ApiError,
  rpc,
  type CandidateChoice,
  type OpeningEvidenceOptions,
  type PlanPreview,
  type PlanProposal,
  type PlanVariant,
  type PlanVersionRecord,
  type Trip,
  type ComfortTradeoffReport,
} from "../api/client";
import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { placeName } from "../shared/names";
import { collectRouteEvidence } from "../shared/routeEvidence";

// Three per row, not five: at a fifth of a centred page these labels clipped.
const METRICS = [
  "scheduled_visits",
  "travel_minutes",
  "walking_minutes",
  "meal_minutes",
  "logistics_minutes",
  "preparation_minutes",
  "plain_walking_minutes",
  "buffer_minutes",
] as const;

const CONSIDERED = new Set(["must_do", "interested", "maybe"]);

/**
 * What the draft had to stand in for, read out of the snapshot it was built from.
 *
 * The reported gap was "can't see the plan without strict input" — the planner does
 * not in fact refuse on thin evidence, it fills the hole and carries on, and nothing
 * on the screen said which holes it filled. Every line below is read from the frozen
 * `optimizer_input`, so it describes *this* draft and cannot drift from it. The
 * snapshot's own `capability_gaps` are appended rather than re-derived, for the same
 * reason: two opinions about the same evidence is how a screen starts lying.
 */
function assumptionsOf(preview: PlanPreview | null, proposal: PlanProposal | null): string[] {
  if (!preview) return [];
  const input = preview.optimizer_input.data;
  const lines: string[] = [];
  if (proposal?.mode === "stay_recommendation") lines.push("assumption_no_dates");
  const assumedHours = (input.facts ?? []).filter(
    (fact) => fact.fact_type === "opening_interval" && fact.status === "assumed",
  ).length;
  if (assumedHours) lines.push(`assumption_hours:${assumedHours}`);
  if ((input.routes ?? []).some((route) => route.status === "estimated")) {
    lines.push("assumption_routes");
  }
  if (
    (input.candidates ?? []).some(
      (candidate) => candidate.planning_basis === "selected_place_centroid",
    )
  ) {
    lines.push("assumption_accommodation");
  }
  return lines;
}

/** The stages the free build actually goes through, in order. */
const BUILD_LINES = [
  "think_windows", "think_routes", "think_packing",
  "think_variants", "think_checking", "think_almost",
] as const;

/**
 * The wait, shown beside whichever control started it.
 *
 * Four buttons on this screen start the same ~210s job -- assume the missing hours
 * and build -- and three of them showed only the word "Loading" on their own label.
 * The real progress panel existed, but it renders near the top of the page, and two
 * of those buttons sit a few hundred lines of markup below it: the feedback appeared
 * somewhere the owner was not looking, having pressed something at the bottom of a
 * long screen. A label that reads "Loading" without moving for three and a half
 * minutes is the same picture as a page that has hung.
 *
 * 210 seconds, not 52. The 52 is the optimizer alone; the free path collects route
 * evidence first, which on a fresh 15-place trip took the whole thing to 210.
 */
function BuildProgress({ language }: { language: Language }) {
  return (
    <div className="optimize-working" aria-busy="true">
      <Thinking expectSeconds={210} language={language} lines={BUILD_LINES} />
      <p className="setup-hint">{copy("optimizing_note", language)}</p>
    </div>
  );
}

export function OptimizePage() {
  const { tripId = "" } = useParams();
  const { language } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [variantId, setVariantId] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  // Free is the default, and stays the default: this app's rule is that a control which
  // spends money says so before it is pressed, never that it is pressed by accident.
  const [hoursChoice, setHoursChoice] = useState<"assume" | "verified">("assume");
  // Once a draft exists the build controls are done asking. Leaving "Before you build"
  // and "Build three plan options" above a finished proposal put the question and its
  // answer on screen together, so the screen read as still waiting for a press that had
  // already happened — and re-pressing throws away the draft below it. They come back on
  // a deliberate "Build them again", which is the only moment they mean anything.
  const [rebuilding, setRebuilding] = useState(false);

  const trips = useQuery({ queryKey: ["trips"], queryFn: () => rpc<Trip[]>("list_trips") });
  const choices = useQuery({
    queryKey: ["candidate_choices", tripId],
    queryFn: () => rpc<CandidateChoice[]>("list_candidate_choices", { trip_id: tripId }),
  });
  const preview = useQuery({
    queryKey: ["plan_preview", tripId],
    queryFn: () => rpc<PlanPreview | null>("get_plan_preview", { trip_id: tripId }),
  });
  // Activation deletes the preview by design, so with a plan already active this
  // screen rendered a title, a sentence and a button and nothing else — it read as
  // broken rather than as finished.
  const active = useQuery({
    queryKey: ["active_plan", tripId],
    queryFn: () => rpc<PlanVersionRecord | null>("get_active_plan", { trip_id: tripId }),
  });

  // The evidence decision, brought to the moment it matters.
  //
  // It lived only on `/evidence`, so building a plan meant leaving this screen, reading
  // a wall of controls, deciding, and coming back — reported as "back and forth". The
  // only question that screen asks about opening hours is answerable here, in a
  // sentence, beside the button it affects; `/evidence` keeps the detail for anyone who
  // wants it and stops being a required stop.
  const evidence = useQuery({
    queryKey: ["opening_options", tripId],
    queryFn: () => rpc<OpeningEvidenceOptions>("opening_evidence_options", { trip_id: tripId }),
  });
  // Same key the tradeoff panel uses, so TanStack serves both from one response and the
  // two cannot disagree about which budget is exceeded.
  const tradeoffs = useQuery({
    queryKey: ["comfort_tradeoffs", tripId],
    queryFn: () => rpc<ComfortTradeoffReport>("comfort_tradeoffs", { trip_id: tripId }),
  });
  const acceptRoutes = useMutation({
    mutationFn: async () => {
      await rpc("accept_route_estimates", { trip_id: tripId });
      // Rebuilt straight away: the estimates only reach the plan through a new
      // `_optimizer_input`, so accepting without rebuilding would look like nothing.
      return rpc<PlanPreview>("generate_plan_preview", { trip_id: tripId });
    },
    onSuccess: async () => {
      setRefusal(null);
      await queryClient.invalidateQueries({ queryKey: ["plan_preview", tripId] });
    },
    onError: (error) => setRefusal(error instanceof ApiError ? error.code : String(error)),
  });

  const acceptAll = useMutation({
    mutationFn: async (rules: ComfortTradeoffReport["rules"]) => {
      for (const rule of rules) {
        await rpc("accept_comfort_tradeoff", {
          trip_id: tripId,
          code: rule.code,
          value: rule.measured,
        });
      }
      // The plan is judged at build time, so agreeing to a figure changes nothing until
      // it is rebuilt. Without this the button would appear to do nothing at all.
      return rpc<PlanPreview>("generate_plan_preview", { trip_id: tripId });
    },
    onSuccess: async () => {
      setRefusal(null);
      await Promise.all(
        ["comfort_tradeoffs", "plan_preview", "journey"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key, tripId] }),
        ),
      );
    },
    onError: (error) => setRefusal(error instanceof ApiError ? error.code : String(error)),
  });
  // The paid path is buy-then-build, not buy-and-stop. Buying the hours and leaving the
  // owner to press again was the "back and forth" report: the purchase is only ever made
  // *in order to* build, so the two are one press.
  const buyThenGenerate = useMutation({
    mutationFn: async () => {
      if (buildingRef.current) return null;
      buildingRef.current = true;
      await rpc<unknown>("refresh_opening_hours", { trip_id: tripId });
      await queryClient.invalidateQueries({ queryKey: ["opening_options", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["paid_usage"] });
      return rpc<PlanPreview>("generate_plan_preview", { trip_id: tripId });
    },
    onSuccess: async () => {
      setRefusal(null);
      await queryClient.invalidateQueries({ queryKey: ["plan_preview", tripId] });
    },
    onError: (error) => setRefusal(error instanceof ApiError ? error.code : String(error)),
    onSettled: () => {
      buildingRef.current = false;
    },
  });

  const generate = useMutation({
    mutationFn: () => rpc<PlanPreview>("generate_plan_preview", { trip_id: tripId }),
    onSuccess: async () => {
      setRefusal(null);
      await queryClient.invalidateQueries({ queryKey: ["plan_preview", tripId] });
    },
    onError: (error) =>
      setRefusal(error instanceof ApiError ? error.code : String(error)),
  });

  // `isPending` flips on the *next* render, so two clicks inside one frame both pass the
  // disabled check and start two 52-second optimizes — which is what "loading is stuck"
  // looked like: the second run's result replacing the first's, twice as slowly. A ref
  // is set synchronously, so the second click has nothing to do.
  const buildingRef = useRef(false);
  const autoResolveAndGenerate = useMutation({
    mutationFn: async () => {
      if (buildingRef.current) return null;
      buildingRef.current = true;
      // No invented hotel. This used to call `confirm_accommodation_base("")`, which
      // geocodes `"{destination} Station"` — and for "New York, United States" that
      // returned a station in upstate New York State, 286 km from Manhattan and from all
      // eleven chosen places. The optimizer already has an honest answer for an
      // unconfirmed stay: a provisional base at the centre of the places themselves,
      // which is near them by construction and says on screen that it is a hypothesis.
      //
      // Free, all of it. This used to call `refresh_opening_hours` and
      // `refresh_timezone` — **US$0.025 a place** and US$0.005 — from a button whose
      // label promised only to resolve details, with no price anywhere near it. On the
      // owner's five-place Fukuoka trip one press spent US$0.13 without saying so,
      // which breaks this repo's rule that a paid action states its estimate
      // immediately before its button. The very next line already assumes the hours, so
      // buying them here bought nothing this button needed.
      //
      // The paid lookup is not removed from the app — it stays on `/evidence` and in
      // the verdict panel above, priced, where choosing it is the point.
      // Free now: the zone comes from Open-Meteo rather than the paid Google lookup,
      // so there is no reason to leave the trip permanently unverified.
      try {
        await rpc("refresh_timezone", { trip_id: tripId });
      } catch (err) {
        void err;
      }
      await rpc("confirm_default_opening_windows", { trip_id: tripId, start: "09:00", end: "18:00" });
      // Until every pair is measured, not once: one call covers sixty new pairs and
      // eleven places need 110, so a single pass left the rest fatally unverified.
      await collectRouteEvidence(tripId);
      return rpc<PlanPreview>("generate_plan_preview", { trip_id: tripId });
    },
    onSuccess: async () => {
      setRefusal(null);
      await queryClient.invalidateQueries({ queryKey: ["plan_preview", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["opening_options", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["journey", tripId] });
    },
    onError: (error) => setRefusal(error instanceof ApiError ? error.code : String(error)),
  });

  // Drop one place and rebuild without it. `save_candidate_choice` with `not_for_trip`
  // is the same write the deck makes, so this is the owner changing their mind rather
  // than a new kind of state — and the plan is regenerated immediately, because a
  // reconciliation table describing a plan that no longer exists is worse than none.
  const dropAndRebuild = useMutation({
    mutationFn: async (placeId: string) => {
      await rpc("save_candidate_choice", {
        trip_id: tripId,
        place_id: placeId,
        action: "not_for_trip",
        reason: null,
      });
      return rpc<PlanPreview>("generate_plan_preview", { trip_id: tripId });
    },
    onSuccess: async () => {
      setRefusal(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["plan_preview", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["candidate_choices", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["journey", tripId] }),
      ]);
    },
    onError: (error) => setRefusal(error instanceof ApiError ? error.code : String(error)),
    onSettled: () => {
      buildingRef.current = false;
    },
  });

  const building =
    generate.isPending || autoResolveAndGenerate.isPending || buyThenGenerate.isPending;

  const activate = useMutation({
    mutationFn: (variant: string) =>
      rpc<unknown>("activate_plan_preview", { trip_id: tripId, variant_id: variant }),
    onSuccess: async () => {
      setRefusal(null);
      await queryClient.invalidateQueries({ queryKey: ["journey", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["plan_preview", tripId] });
      navigate(`/trips/${tripId}/itinerary`);
    },
    // A stale input hash or an unready variant refuses with a stable code. It
    // has to be shown: activation is the one action that writes an immutable
    // plan version, so a silent failure would read as success.
    onError: (error) =>
      setRefusal(error instanceof ApiError ? error.code : String(error)),
  });

  if (choices.isPending || preview.isPending) return <p>{copy("loading", language)}</p>;
  if (choices.isError) return <p className="field-error">⚠ {choices.error.message}</p>;
  if (preview.isError) return <p className="field-error">⚠ {preview.error.message}</p>;

  const trip = trips.data?.find((item) => item.trip_id === tripId);
  const considered = choices.data.filter((choice) => CONSIDERED.has(choice.action));
  const proposal = preview.data?.proposal.data ?? null;
  const optimizerInput = preview.data?.optimizer_input.data ?? null;
  const variants = proposal?.variants ?? [];
  const variant: PlanVariant | undefined =
    variants.find((item) => item.variant_id === variantId) ?? variants[0];
  const routeBlocked = variants.some((item) =>
    (item.reconciliation ?? []).some(
      (entry) => entry.status === "cannot_currently_fit" && entry.reason === "ROUTE_UNVERIFIED",
    ),
  );

  const provisionalAllowed = Boolean(
    trip?.planning_mode === "explore_first" &&
      variant?.status === "provisional" &&
      variant?.validation?.valid,
  );
  const activationAllowed = variant?.status === "ready" || provisionalAllowed;
  // Hard violations that are *only* an unapproved comfort budget. `COMFORT_RULES` pairs
  // each reason with an `UNAPPROVED_` violation code, so the prefix is the server's own
  // marker for "the owner can agree to this", not a guess made here.
  const comfortOnly = (variant?.validation?.hard_violations ?? []).filter((item) =>
    String(item.code).startsWith("UNAPPROVED_"),
  );
  // The measured figures behind those violations, from the one table the validator, the
  // soft count and the tradeoff screen already share.
  const overBudget = (tradeoffs.data?.rules ?? []).filter(
    (rule) => rule.exceeds && rule.measured !== null && rule.accepted_value === null,
  );

  const area = optimizerInput?.candidates?.find(
    (candidate) => candidate.id === variant?.hotel_recommendation?.default_area_id,
  );
  const assumptions = assumptionsOf(preview.data ?? null, proposal);
  const showBuildControls = !proposal || rebuilding;
  const gaps = optimizerInput?.capability_gaps ?? [];
  // One label, two dead ends — the refusal card and an unusable variant's warnings.
  // It says "free" because it now is, and says what it assumes, because a button that
  // fills a gap has to name the value it filled it with.
  const autoResolveLabel = copy("auto_resolve_free", language);

  return (
    <section className="stage-card optimize-screen">
      <header className="money-head">
        <h1>{copy("optimizer_title", language)}</h1>
        <p>{copy("optimizer_help", language)}</p>
      </header>

      {refusal ? (
        <div className="optimizer-refusal-card">
          <p className="field-error" aria-live="polite">
            ⚠ {copyFrom("OPTIMIZER_CODE_TEXT", refusal, language)}
          </p>
          <button
            type="button"
            className="setup-primary auto-resolve-retry-btn"
            disabled={autoResolveAndGenerate.isPending}
            onClick={() => autoResolveAndGenerate.mutate()}
          >
            {autoResolveAndGenerate.isPending ? copy("loading", language) : autoResolveLabel}
          </button>
          <small className="setup-hint">{copy("auto_resolve_note", language)}</small>
          {autoResolveAndGenerate.isPending ? <BuildProgress language={language} /> : null}
        </div>
      ) : null}

      {/* Gone while the optimize runs. The panel asks a question whose answer has already
          been taken and acted on, and leaving it up during the ~52s wait invites changing
          an answer that is no longer being read — the radio would move while the run it
          was meant to configure was already past it. */}
      {evidence.data && considered.length && !building && showBuildControls ? (
        <section className={`evidence-verdict${evidence.data.needing_hours ? "" : " settled"}`}>
          <h2>{copy("before_you_build", language)}</h2>
          <p className="evidence-verdict-answer">
            {evidence.data.needing_hours
              ? copyFormat("before_hours_gap", language, {
                  needing: evidence.data.needing_hours,
                  places: evidence.data.places,
                })
              : copy("before_all_covered", language)}
          </p>
          {/* Two buttons here were two *actions*, and they are not: they are one action
              and a choice about how to pay for it. Presented as buttons the owner had to
              read both labels to work out that either one builds the plan — so the choice
              is a radio group and "Build three plan options" below is the only press.
              "More evidence controls" is gone for the same reason: a third link beside a
              decision is a third thing to weigh. */}
          {evidence.data.needing_hours ? (
            <fieldset className="evidence-choice">
              <legend>{copy("before_hours_choice", language)}</legend>
              <label>
                <input
                  checked={hoursChoice === "assume"}
                  name="hours-choice"
                  onChange={() => setHoursChoice("assume")}
                  type="radio"
                  value="assume"
                />
                <span>{copy("auto_resolve_free", language)}</span>
              </label>
              <label>
                <input
                  checked={hoursChoice === "verified"}
                  name="hours-choice"
                  onChange={() => setHoursChoice("verified")}
                  type="radio"
                  value="verified"
                />
                <span>
                  {copyFormat("before_buy_hours", language, {
                    cost: evidence.data.verified.estimate_usd.toFixed(3),
                  })}
                </span>
              </label>
            </fieldset>
          ) : null}
        </section>
      ) : null}

      {/* The one action on this screen, always present. It used to be hidden whenever the
          opening-hours question was open, because the two buttons up there built the plan
          instead — which meant the screen's named action disappeared exactly when the
          owner was looking for it. The radio above now decides *how* it builds; this
          decides *that* it builds. */}
      {/* The rebuild offer, where the build controls used to be. */}
      {!showBuildControls && !building ? (
        <div className="optimize-actions">
          <button onClick={() => setRebuilding(true)} type="button">
            {copy("build_again", language)}
          </button>
        </div>
      ) : null}
      <div className="optimize-actions" hidden={!showBuildControls || building}>
        <button
          className="setup-primary"
          disabled={considered.length === 0 || building}
          onClick={() => {
            if (!evidence.data?.needing_hours) return generate.mutate();
            if (hoursChoice === "verified") return buyThenGenerate.mutate();
            return autoResolveAndGenerate.mutate();
          }}
          type="button"
        >
          {building
            ? copy(buyThenGenerate.isPending ? "before_buying" : "optimizing", language)
            : copy("generate_plan", language)}
        </button>
      </div>
      {/* A disabled primary action always says why. */}
      {considered.length === 0 ? (
        <p className="setup-hint">{copy("choose_before_plan", language)}</p>
      ) : null}
      {/* This screen showed a disabled button and nothing else for the ~52s a full
          optimize takes, and was reported as "I still can't build a plan" — the work
          was succeeding every time and the screen never said so. */}
      {generate.isPending || autoResolveAndGenerate.isPending ? (
        <div aria-busy="true">
          <BuildProgress language={language} />
          <div className="skeleton-card">
            <span className="skeleton skeleton-line wide" />
            <span className="skeleton skeleton-line" />
            <span className="skeleton skeleton-photo short" />
            <span className="skeleton skeleton-line" />
          </div>
        </div>
      ) : null}

      {!proposal ? (
        <>
          {active.data ? (
            <>
              <p className="money-note">
                <span>{copy("active_plan_exists", language)}</span>
              </p>
              <Link className="primary-link" to={`/trips/${tripId}/itinerary`}>
                {copy("open_itinerary", language)}
              </Link>
            </>
          ) : null}
          <p className="setup-hint">{copy("no_preview_yet", language)}</p>
          {considered.length > 0 ? (
            <p className="setup-hint">{copy("no_preview_help", language)}</p>
          ) : null}
        </>
      ) : null}

      {/* Hidden while a rebuild runs, at the owner's asking: the previous attempt's
          variants, unfit list and reasons all stay on screen otherwise, and reading
          them during a wait of minutes invites acting on an answer that is being
          replaced. `hidden` rather than unmounting, so a failed rebuild leaves the
          plan that did work exactly as it was. */}
      {proposal ? (
        <div hidden={building}>
          <p className="money-note money-note-plain">
            <span>{copy("plan_draft_note", language)}</span>
          </p>
          {/* Folded behind its own summary, at the owner's asking. It is a list of
              caveats sitting between the draft and the variants the owner came to read,
              and it is the same list every time until something changes — so it is
              available in one press rather than occupying the page. `<details>` rather
              than a hand-rolled toggle: the disclosure triangle, the keyboard behaviour
              and the announced expanded state all come from the platform.
              derives-from: element 36 .currency-info-box as .plan-assumptions */}
          <details className="plan-assumptions">
            <summary>
              <span aria-hidden="true">⚠</span> {copy("assumptions_title", language)}
              {assumptions.length + gaps.length
                ? ` · ${assumptions.length + gaps.length}`
                : ""}
            </summary>
            <p className="setup-hint">{copy("assumptions_help", language)}</p>
            {assumptions.length || gaps.length ? (
              <ul>
                {assumptions.map((line) => {
                  const [code, count] = line.split(":");
                  return (
                    <li key={line}>
                      {count ? copyFormat(code, language, { count }) : copy(code, language)}
                    </li>
                  );
                })}
                {gaps.map((code) => (
                  <li key={code}>{copyFrom("OPTIMIZER_CODE_TEXT", code, language)}</li>
                ))}
              </ul>
            ) : (
              <p className="setup-hint">{copy("assumption_none", language)}</p>
            )}
            <Link className="primary-link" to={`/trips/${tripId}/evidence`}>
              {copy("open_evidence", language)}
            </Link>
          </details>
        </div>
      ) : null}

      {/* All variants share one route snapshot, so its acceptance sits at draft level
          instead of being buried inside whichever variant happens to be selected. */}
      {routeBlocked ? (
        <div className="optimizer-resolve">
          <p className="field-error">
            ⚠ {copyFrom("OPTIMIZER_CODE_TEXT", "ROUTE_UNVERIFIED", language)}
          </p>
          <button
            className="setup-primary"
            disabled={acceptRoutes.isPending}
            onClick={() => acceptRoutes.mutate()}
            type="button"
          >
            {acceptRoutes.isPending
              ? copy("loading", language)
              : copy("accept_route_estimates", language)}
          </button>
        </div>
      ) : null}

      {/* A trip with no dates used to end here, at a table of how many days its places
          want and no way to act on it. The recommendation is now the input to choosing
          dates, which is the one thing that unlocks a timetable. */}
      {proposal?.mode === "stay_recommendation" ? (
        <StayPlanner language={language} proposal={proposal} tripId={tripId} />
      ) : null}

      {/* `WF-039`. Above the variant picker, because an overage is the reason a variant
          is unactivatable and the owner needs the choice before, not after, the button
          that refuses. Renders nothing when no budget is exceeded or agreed. */}
      <ComfortTradeoffs language={language} tripId={tripId} />

      {variant ? (
        <>
          <label className="optimize-variant">
            {copy("variant", language)}
            <select
              onChange={(event) => {
                setVariantId(event.target.value);
                setRefusal(null);
              }}
              value={variant.variant_id}
            >
              {variants.map((item) => (
                <option key={item.variant_id} value={item.variant_id}>
                  {copy(item.variant_id, language)} · {copy(item.status, language)}
                </option>
              ))}
            </select>
          </label>

          {variant.hotel_recommendation ? (
            <div className="optimize-base">
              <strong>
                {copy(
                  variant.hotel_recommendation.basis === "booked_accommodation"
                    ? "booked_base"
                    : "provisional_base",
                  language,
                )}
              </strong>
              <span>{placeName(area, language, "—")}</span>
              <span className="setup-hint">
                {copy(
                  variant.hotel_recommendation.basis === "booked_accommodation"
                    ? "booked_base_help"
                    : "provisional_base_help",
                  language,
                )}
              </span>
              {variant.hotel_recommendation.basis === "booked_accommodation" ? null : (
                <span className="setup-hint">{copy("provisional_base_basis", language)}</span>
              )}
            </div>
          ) : null}

          {/* derives-from: element 14 .stat-card as .money-tile, three per
              row rather than five. */}
          <div className="optimize-metrics">
            {METRICS.map((metric) => (
              <div className="money-tile" key={metric}>
                <span className="money-tile-label">{copy(metric, language)}</span>
                <strong className="money-tile-value">{variant.metrics[metric] ?? 0}</strong>
              </div>
            ))}
          </div>

          {variant.metrics.scheduled_visits && variant.objective_improved_or_equal_to_greedy ? (
            <p className="setup-flash">{copy("greedy_check", language)}</p>
          ) : null}
          {variant.stopped_at_limit ? (
            <p className="money-note money-note-warn">
              <b aria-hidden="true">⚠</b>
              <span>{copy("optimizer_limit", language)}</span>
            </p>
          ) : null}

          {variant.warnings.length > 0 ? (
            <details className="optimize-warnings" open>
              <summary>{copy("optimizer_warning", language)}</summary>
              <ul>
                {variant.warnings.map((code) => (
                  <li key={code}>{copyFrom("OPTIMIZER_CODE_TEXT", code, language)}</li>
                ))}
              </ul>
              {/* The way out, beside the list of what is wrong. This lived only on the
                  refusal card, which is a different failure: a refusal is the request
                  being rejected, while these warnings come back *with* a variant that
                  simply cannot be activated. So a plan that built and could not be used
                  named six blockers and offered nothing to press — reported as being
                  stuck here having already supplied everything. */}
            </details>
          ) : null}

          {/* Outside the warnings box, not inside it. A control that resolves the list
              is not one of the list's items, and buried in a `<details>` it read as part
              of the problem rather than the way out. */}
          {/* Why this plan cannot be used, when the answer is "a comfort budget", and it
              very often is. Measured on the owner's Singapore trip: all 14 places
              scheduled, timeline continuous, and the single hard violation was
              `UNAPPROVED_PLAIN_WALK_THRESHOLD` at 40 minutes against a 35-minute
              preference. A finished plan was being withheld over five minutes of walking,
              the screen said only "cannot activate", and the one control on offer was
              "drop a place" — so the owner dropped places to fix a problem no place was
              causing. The tradeoff panel that resolves it was already on the screen,
              above; nothing connected the two. */}
          {!activationAllowed && comfortOnly.length ? (
            <p className="money-note money-note-warn">
              <b aria-hidden="true">⚠</b>
              <span>
                {copyFormat("blocked_by_comfort_only", language, {
                  visits: String(variant.validation.scheduled_visit_count ?? 0),
                })}
              </span>
            </p>
          ) : null}
          {/* The accept, here. It was only in the tradeoff panel further up the page and
              was reported as not being there at all — a control that resolves a refusal
              belongs beside the refusal. It agrees to the **measured** value, never the
              rule in general: `_accepts` requires `measured <= accepted_value`, so a
              later replan that walks further is refused again rather than blessed. */}
          {!activationAllowed && comfortOnly.length && overBudget.length ? (
            <div className="optimize-actions">
              <button
                className="setup-primary"
                disabled={acceptAll.isPending}
                onClick={() => acceptAll.mutate(overBudget)}
                type="button"
              >
                {acceptAll.isPending
                  ? copy("loading", language)
                  : copyFormat("accept_measured_and_continue", language, {
                      measured: overBudget.map((rule) => String(rule.measured)).join(", "),
                    })}
              </button>
            </div>
          ) : null}
          {/* Not offered when the blocker is a comfort budget: fetching more routes
              cannot move a walking threshold, so this button promised work that could not
              possibly help — and being the only control near the failure, it was pressed.
              Reported as "why does this appear again". */}
          {!activationAllowed && !evidence.data?.needing_hours && !comfortOnly.length ? (
            <div className="optimize-resolve">
              <button
                className="setup-primary auto-resolve-retry-btn"
                disabled={autoResolveAndGenerate.isPending}
                onClick={() => autoResolveAndGenerate.mutate()}
                type="button"
              >
                {autoResolveAndGenerate.isPending ? copy("loading", language) : autoResolveLabel}
              </button>
              <small className="setup-hint">{copy("auto_resolve_note", language)}</small>
              {autoResolveAndGenerate.isPending ? <BuildProgress language={language} /> : null}
            </div>
          ) : null}

          {/* Every place that did not make it, with the way out beside it. The table
              below says *what* happened; this says what to do about it, which is what
              was missing — a row reading "cannot currently fit" and nothing to press. */}
          {(() => {
            const unfit = (variant.reconciliation ?? []).filter(
              (item) => item.status === "cannot_currently_fit",
            );
            if (!unfit.length) return null;
            const needsRoutes = unfit.some((item) => item.reason === "ROUTE_UNVERIFIED");
            // "The trip has no remaining time capacity" is the honest residual: these
            // places fit nothing that is wrong, there are simply more of them than the
            // days hold. The optimizer cannot invent a day — the dates are the owner's —
            // so the only useful thing to say is how short the trip is and where to
            // lengthen it. Saying it without that link was the dead end reported.
            const needsDays = unfit.filter((item) => item.reason === "NO_TIME_CAPACITY");
            return (
              <section className="optimize-unfit">
                <h2 className="money-eyebrow">{copy("unfit_title", language)}</h2>
                <p className="setup-hint">{copy("unfit_help", language)}</p>
                {needsDays.length ? (
                  <p className="setup-hint">
                    {copyFormat("unfit_needs_days", language, {
                      count: needsDays.length,
                      days: variant.days.length,
                    })}{" "}
                    <Link className="primary-link" to={`/trips/${tripId}/setup`}>
                      {copy("unfit_change_dates", language)}
                    </Link>
                  </p>
                ) : null}
                {/* The other way past a route nothing will measure. "Fix routes" asks
                    the routers again, which is right when they were merely busy and
                    useless when they will not answer this pair at all — and then the only
                    remaining control was "drop the place". This accepts a deliberately
                    **over-stated** straight line instead: the plan gains slack rather
                    than losing a place, and the estimate is marked so nothing downstream
                    can mistake it for something a router said. */}
                {/* The same mutation the primary control runs, so it now carries the
                    same label and the same note. It used to say "Measure the missing
                    routes and rebuild", which named one of the three things it does and
                    read as a second, different action -- two buttons for one behaviour,
                    reported as redundant and confusing. */}
                {needsRoutes ? (
                  <>
                    <button
                      className="setup-primary"
                      disabled={autoResolveAndGenerate.isPending}
                      onClick={() => autoResolveAndGenerate.mutate()}
                      type="button"
                    >
                      {autoResolveAndGenerate.isPending
                        ? copy("loading", language)
                        : autoResolveLabel}
                    </button>
                    <small className="setup-hint">{copy("auto_resolve_note", language)}</small>
                  </>
                ) : null}
                {needsRoutes && autoResolveAndGenerate.isPending ? (
                  <BuildProgress language={language} />
                ) : null}
                <ul className="optimize-unfit-list">
                  {unfit.map((item) => (
                    <li key={item.place_id}>
                      <span className="optimize-unfit-name">
                        {placeName(item, language, item.name)}
                      </span>
                      <small>{copyFrom("OPTIMIZER_CODE_TEXT", item.reason, language)}</small>
                      <button
                        disabled={dropAndRebuild.isPending}
                        onClick={() => dropAndRebuild.mutate(item.place_id)}
                        type="button"
                      >
                        {copy("unfit_drop", language)}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })()}

          {/* Only once the draft is usable. Before the evidence is settled every row
              said "cannot currently fit" about a plan that had not really been attempted
              yet — a wall of failure describing a state the owner had not reached, and
              read as the app having decided against their places. The button above is
              the thing to look at until then. */}
          {activationAllowed ? (
          <>
          <h2 className="money-eyebrow">{copy("optimizer_reconciliation", language)}</h2>
          <div className="money-table-scroll">
            <table className="money-table">
              <thead>
                <tr>
                  <th>{copy("name", language)}</th>
                  <th>{copy("choice", language)}</th>
                  <th>{copy("feasibility", language)}</th>
                  <th>{copy("reason", language)}</th>
                  <th>{copy("consequence", language)}</th>
                </tr>
              </thead>
              <tbody>
                {variant.reconciliation.map((item, index) => (
                  <tr key={`${item.name}-${index}`}>
                    <td>{placeName(item, language, item.name)}</td>
                    <td>{copy(item.priority, language)}</td>
                    <td>{copy(item.status, language)}</td>
                    <td>{copyFrom("OPTIMIZER_CODE_TEXT", item.reason, language)}</td>
                    <td>{copyFrom("OPTIMIZER_CODE_TEXT", item.consequence, language)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
          ) : null}

          {variant.days.some((day) => day.items.length > 0) ? (
            <>
              <h2 className="money-eyebrow">{copy("timeline", language)}</h2>
              <div className="money-table-scroll">
                <table className="money-table">
                  <thead>
                    <tr>
                      <th>{copy("days", language)}</th>
                      <th>{copy("start", language)}</th>
                      <th>{copy("end", language)}</th>
                      <th>{copy("item_type", language)}</th>
                      <th>{copy("place_or_leg", language)}</th>
                      <th>{copy("duration", language)}</th>
                    </tr>
                  </thead>
                  {/* Sixty identical grey rows repeating the same date twenty times was
                      the "hard to read and distinguish" report. Three changes, no new
                      data: the date is printed once per day and a rule marks where the
                      day turns over, the kind is a coloured chip in the same five
                      families the itinerary's own rows use, and the kind is finally
                      translated — it was the raw `visit` / `buffer` code in both
                      languages. */}
                  <tbody>
                    {variant.days.flatMap((day) =>
                      day.items.map((item, index) => (
                        <tr
                          className={index === 0 ? "timeline-day-start" : undefined}
                          key={`${day.date}-${index}`}
                        >
                          <td>{index === 0 ? day.date : ""}</td>
                          <td className="money-num">{item.start}</td>
                          <td className="money-num">{item.end}</td>
                          <td>
                            <span className={`plan-row-kind ${item.type}`}>
                              {item.type === "buffer" &&
                              (item.reason === "free_time_or_rest" || item.reason === "day_ends_free")
                                ? copyFrom("OPTIMIZER_CODE_TEXT", item.reason, language)
                                : copy(`type_${item.type}`, language)}
                            </span>
                          </td>
                          {/* Empty rather than the raw `buffer` / `travel` code it used
                              to repeat: the chip beside it already says which it is. */}
                          <td>{item.name ? placeName(item, language, item.name) : ""}</td>
                          <td className="money-num">
                            {item.duration_minutes} {copy("minutes", language)}
                          </td>
                        </tr>
                      )),
                    )}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="money-note money-note-warn">
              <b aria-hidden="true">⚠</b>
              <span>{copy("no_schedule", language)}</span>
            </p>
          )}

          {provisionalAllowed ? (
            <p className="money-note money-note-info">
              <b aria-hidden="true">ⓘ</b>
              <span>{copy("provisional_activation_help", language)}</span>
            </p>
          ) : null}
          {/* The screen used to end at a disabled button with one line of refusal
              code, so a draft that could not be activated was a dead end rather than
              a next step. Both branches now say what to do, not only what is wrong. */}
          <h2 className="money-eyebrow">{copy("what_next", language)}</h2>
          {activationAllowed ? (
            <p className="setup-hint">{copy("next_activate", language)}</p>
          ) : (
            <>
              <p className="setup-hint">{copy("activation_disabled", language)}</p>
              <p className="setup-hint">{copy("next_fix_first", language)}</p>
            </>
          )}
          <div className="optimize-actions">
            <button
              className="setup-primary"
              disabled={!activationAllowed || activate.isPending}
              onClick={() => activate.mutate(variant.variant_id)}
              type="button"
            >
              {copy(provisionalAllowed ? "use_provisional_plan" : "activate_plan", language)}
            </button>
            <Link className="primary-link" to={`/trips/${tripId}/places`}>
              {copy("stage_places", language)}
            </Link>
          </div>
        </>
      ) : null}
    </section>
  );
}
