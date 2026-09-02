import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { Thinking } from "../shared/Thinking";
import { ComfortTradeoffs } from "./ComfortTradeoffs";
import { BuildStages } from "./BuildStages";
import { BUILD_STAGES, PREVIEW_STAGES } from "../shared/buildStages";
import { StayPlanner } from "./StayPlanner";
import { addDays } from "../shared/dates";
import { wholeDraftWithDates } from "../shared/setupDraft";
import { planDecisions } from "../shared/planDecisions";
import { placesDaysWereAddedFor, rememberDaysAddedFor } from "../shared/dayExtension";

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
  type SetupDraft,
} from "../api/client";
import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";
import { Loading } from "../shared/Loading";
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
/**
 * The wait, and how much of it can honestly be described.
 *
 * `stage` is supplied only by `autoResolveAndGenerate`, which awaits four separate calls
 * and therefore *knows* where it is -- each one returning is a fact, not an estimate. The
 * other two build paths are a single `generate_plan_preview` (plus, on the paid one, a
 * purchase), so they have no milestones to report and keep the rotating lines alone.
 * `Thinking` sits inside whichever stage is active, because the long stage really does
 * have nothing to say beyond "still running" and its realistic time range.
 */
export function BuildProgress({
  language,
  stage,
  previewStage,
  routesMeasured,
}: {
  language: Language;
  stage?: number;
  previewStage?: number;
  routesMeasured?: number;
}) {
  const thinking = (
    <Thinking
      expectSeconds={210}
      language={language}
      lines={BUILD_LINES}
    />
  );
  return (
    <div className="optimize-working" aria-busy="true">
      {stage !== undefined ? (
        <BuildStages language={language} reached={stage} routesMeasured={routesMeasured}>
          {thinking}
        </BuildStages>
      ) : (
        /* The plain and paid builds are a single `generate_plan_preview`, so they have
           no calls of their own to count -- but the optimizer now says which of its
           three variants it has finished, which is the same kind of fact. Start at
           zero rather than falling back to a spinner while the job is still queued:
           the first dot is active immediately, and no dot is marked done until the
           worker reports it. */
        <BuildStages language={language} reached={previewStage ?? 0} stages={PREVIEW_STAGES}>
          {thinking}
        </BuildStages>
      )}
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
  // Once a draft exists the build controls are done asking. Leaving "Before you build"
  // and "Build three plan options" above a finished proposal put the question and its
  // answer on screen together, so the screen read as still waiting for a press that had
  // already happened — and re-pressing throws away the draft below it. They come back on
  // a deliberate "Build them again", which is the only moment they mean anything.
  const [rebuilding, setRebuilding] = useState(false);
  // How to fill the missing opening hours, asked only on the **first** build. Once a
  // plan exists the question is no longer "how should this be paid for" but "will you
  // take this plan with the gaps it has", which is one button and not a choice.
  const [hoursChoice, setHoursChoice] = useState<"assume" | "verified">("assume");
  const [excludedComfort, setExcludedComfort] = useState<Set<string>>(() => new Set());

  const trips = useQuery({ queryKey: ["trips"], queryFn: () => rpc<Trip[]>("list_trips") });
  const choices = useQuery({
    queryKey: ["candidate_choices", tripId],
    queryFn: () => rpc<CandidateChoice[]>("list_candidate_choices", { trip_id: tripId }),
  });
  // The stored setup draft, read for "add a day and rebuild": lengthening the trip
  // here is a date write plus the usual build, not a round trip through the wizard.
  const stored = useQuery({
    queryKey: ["setup", tripId],
    queryFn: () => rpc<SetupDraft | null>("get_setup", { trip_id: tripId }),
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
  /* The variant this screen is actually drawing, which is not always the one selected.
   *
   * `variantId` is null until the owner picks from the plan-option list, and the screen
   * falls back to `variants[0]` — so the report below was asked about `variant_id: null`,
   * which the server answers from the **active plan**, while the figures on screen came
   * from the first draft variant. That is the whole of the wasted rebuild the owner
   * reported: `comfortOnly` (from the drawn variant's own violations) said a comfort
   * budget was the only problem, `overBudget` (from the report) had nothing to accept
   * because it described a different plan, and the screen fell through to a bare "build
   * them again" — which changed nothing except that the second pass happened to line the
   * two up. Asking about the variant being drawn removes the step entirely.
   */
  const shownVariantId =
    variantId ?? preview.data?.proposal.data.variants?.[0]?.variant_id ?? null;
  // Same key the tradeoff panel uses — it takes `shownVariantId` too — so TanStack
  // serves both from one response and the two cannot disagree about which budget is
  // exceeded. They previously shared a key only by both omitting the variant.
  const tradeoffs = useQuery({
    queryKey: ["comfort_tradeoffs", tripId, shownVariantId],
    queryFn: () => rpc<ComfortTradeoffReport>("comfort_tradeoffs", {
      trip_id: tripId,
      variant_id: shownVariantId,
    }),
    // Nothing to ask about until a draft exists; without this the first fetch goes out
    // against a null variant and its answer is cached under a key the screen then uses.
    enabled: Boolean(shownVariantId) || !preview.isPending,
  });

  /**
   * The plan changed, so everything derived from the plan is stale.
   *
   * **`comfort_tradeoffs` is derived from the plan and only the comfort-acceptance path
   * was refreshing it.** Every build path invalidated `plan_preview` and left the report
   * alone (that path is `resolveAllAndRebuild` now), so after
   * a build the cache still held whatever it said *before* the plan existed — usually
   * nothing exceeding. Two things vanish together when that happens: `ComfortTradeoffs`
   * filters to zero rules and renders nothing, and `overBudget` is empty so the accept
   * control never appears. The screen is then a refusal saying a comfort budget is the
   * only problem, a panel that has disappeared, and no button — which is exactly what the
   * owner reported and could not act on.
   *
   * Invalidated together from here so a new build path cannot refresh one and forget the
   * other; that asymmetry is the whole bug.
   */
  const invalidatePlan = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["plan_preview", tripId] }),
      queryClient.invalidateQueries({ queryKey: ["comfort_tradeoffs", tripId] }),
    ]);
  const resolveTerminal = () =>
    rpc("resolve_default_terminal", { trip_id: tripId }).catch(() => null);
  const acceptRoutes = useMutation({
    mutationFn: async () => {
      setPreviewStage(undefined);
      await rpc("accept_route_estimates", { trip_id: tripId });
      // Rebuilt straight away: the estimates only reach the plan through a new
      // `_optimizer_input`, so accepting without rebuilding would look like nothing.
      return rpc<PlanPreview>(
        "generate_plan_preview",
        { trip_id: tripId },
        setPreviewStage,
      );
    },
    onSuccess: async () => {
      setRefusal(null);
      await invalidatePlan();
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
      setPreviewStage(undefined);
      await Promise.all([
        rpc<unknown>("refresh_opening_hours", { trip_id: tripId }),
        resolveTerminal(),
      ]);
      await queryClient.invalidateQueries({ queryKey: ["opening_options", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["paid_usage"] });
      return rpc<PlanPreview>(
        "generate_plan_preview",
        { trip_id: tripId },
        setPreviewStage,
      );
    },
    onSuccess: async () => {
      setRefusal(null);
      await invalidatePlan();
    },
    onError: (error) => setRefusal(error instanceof ApiError ? error.code : String(error)),
    onSettled: () => {
      buildingRef.current = false;
    },
  });

  const generate = useMutation({
    mutationFn: async () => {
      setPreviewStage(undefined);
      await resolveTerminal();
      return rpc<PlanPreview>(
        "generate_plan_preview",
        { trip_id: tripId },
        setPreviewStage,
      );
    },
    onSuccess: async () => {
      setRefusal(null);
      await invalidatePlan();
    },
    onError: (error) =>
      setRefusal(error instanceof ApiError ? error.code : String(error)),
  });

  // `isPending` flips on the *next* render, so two clicks inside one frame both pass the
  // disabled check and start two 52-second optimizes — which is what "loading is stuck"
  // looked like: the second run's result replacing the first's, twice as slowly. A ref
  // is set synchronously, so the second click has nothing to do.
  const buildingRef = useRef(false);
  // How many of the free build's four calls have returned, and the server's own count of
  // route pairs measured. Both are facts the page already had and was discarding.
  const [buildStage, setBuildStage] = useState(0);
  const [routesMeasured, setRoutesMeasured] = useState(0);
  /** Which of `generate_plan_preview`'s four the worker has reported, or undefined
   *  when nothing has -- still queued, or the local server, which runs it inline. */
  const [previewStage, setPreviewStage] = useState<number | undefined>(undefined);
  const autoResolveAndGenerate = useMutation({
    mutationFn: async () => {
      if (buildingRef.current) return null;
      buildingRef.current = true;
      setBuildStage(0);
      setRoutesMeasured(0);
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
      await Promise.allSettled([
        rpc("refresh_timezone", { trip_id: tripId }),
        resolveTerminal(),
      ]);
      // Marked done even when it threw: the stage is "we asked", and the catch above is
      // there because an unreachable clock is not a reason to abandon the build. Claiming
      // it succeeded would be the dishonest version.
      setBuildStage(1);
      await rpc("confirm_default_opening_windows", { trip_id: tripId, start: "09:00", end: "18:00" });
      setBuildStage(2);
      // Until every pair is measured, not once: one call covers sixty new pairs and
      // eleven places need 110, so a single pass left the rest fatally unverified.
      await collectRouteEvidence(tripId, setRoutesMeasured);
      setBuildStage(3);
      return rpc<PlanPreview>("generate_plan_preview", { trip_id: tripId });
    },
    onSuccess: async () => {
      setRefusal(null);
      setBuildStage(BUILD_STAGES.length);
      await invalidatePlan();
      await queryClient.invalidateQueries({ queryKey: ["opening_options", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["journey", tripId] });
    },
    onError: (error) => setRefusal(error instanceof ApiError ? error.code : String(error)),
    onSettled: () => {
      buildingRef.current = false;
    },
  });

  // Drop one place and rebuild without it. `save_candidate_choice` with `not_for_trip`
  // is the same write the deck makes, so this is the owner changing their mind rather
  // than a new kind of state — and the plan is regenerated immediately, because a
  // reconciliation table describing a plan that no longer exists is worse than none.
  const dropAndRebuild = useMutation({
    mutationFn: async (placeId: string) => {
      setPreviewStage(undefined);
      await rpc("save_candidate_choice", {
        trip_id: tripId,
        place_id: placeId,
        action: "not_for_trip",
        reason: null,
      });
      return rpc<PlanPreview>(
        "generate_plan_preview",
        { trip_id: tripId },
        setPreviewStage,
      );
    },
    onSuccess: async () => {
      setRefusal(null);
      await Promise.all([
        invalidatePlan(),
        queryClient.invalidateQueries({ queryKey: ["candidate_choices", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["journey", tripId] }),
      ]);
    },
    onError: (error) => setRefusal(error instanceof ApiError ? error.code : String(error)),
  });

  // "The trip has no remaining time capacity" has two ways out that do not involve
  // leaving this screen, and both end in the same rebuild the big button runs:
  //
  // - **Add a day.** The dates are the owner's, so the optimizer cannot invent one —
  //   but extending the range here is a date write plus that same rebuild, not a
  //   round trip through the setup wizard that threw away everything on screen.
  //   `wholeDraftWithDates` rebuilds the whole payload by hand because `save_setup`
  //   defaults what it is not sent; see its own docstring.
  // - **Cut the places that do not fit.** The same `not_for_trip` write the deck
  //   makes, for every place the refusal listed, then the same rebuild. This is the
  //   "variant that cuts some" the owner asked for: the plan that fits, without the
  //   places that could not.
  const cutUnfitAndRebuild = useMutation({
    mutationFn: async (placeIds: string[]) => {
      setPreviewStage(undefined);
      for (const placeId of placeIds) {
        await rpc("save_candidate_choice", {
          trip_id: tripId,
          place_id: placeId,
          action: "not_for_trip",
          reason: null,
        });
      }
      await queryClient.invalidateQueries({ queryKey: ["candidate_choices", tripId] });
      /* Just the solve, not the whole evidence preamble.
       *
       * This called `autoResolveAndGenerate`, which re-runs the timezone lookup, the
       * assumed terminal, the default opening windows and `collectRouteEvidence` — and
       * that last one loops queued route passes until coverage, which on a real trip is
       * minutes. **Removing a place cannot invalidate any of it.** The timezone and the
       * terminal belong to the destination, the windows to the dates, and a route
       * snapshot to a *pair* — every remaining pair is measured exactly as it was, and
       * the pairs that are gone are the ones nothing will ask about again.
       *
       * Reported as "why the remove after adding days took a long time cause it just
       * removes the place, not build the whole new plan". `dropAndRebuild` beside it has
       * always gone straight to the solve; this was the odd one out. */
      return rpc<PlanPreview>(
        "generate_plan_preview",
        { trip_id: tripId },
        setPreviewStage,
      );
    },
    onSuccess: async () => {
      setRefusal(null);
      await Promise.all([
        invalidatePlan(),
        queryClient.invalidateQueries({ queryKey: ["journey", tripId] }),
      ]);
    },
    onError: (error) => setRefusal(error instanceof ApiError ? error.code : String(error)),
  });

  /**
   * Every outstanding decision applied, then **one** rebuild.
   *
   * The reported journey was "build them again -> accept the criteria -> add the day ->
   * add the day". Each of those was a separate control that wrote its own change and
   * then rebuilt, so the owner paid a full build to discover each next condition -- even
   * though every one of them is already derivable from the draft in hand. `outstanding`
   * above lists them; this applies them in order and builds once at the end.
   *
   * Order is deliberate. The two acceptances are plain per-trip writes
   * (`comfort_acceptances` and a `trip_evidence` row), so neither is disturbed by the
   * date write that follows. The dates go last because writing them moves the setup hash
   * and discovery stores the hash it ran against -- so the catalogue has to be re-keyed
   * before anything will build, which is what `addDayAndRebuild` learned the hard way
   * and why `force_refresh` stays false: `discover_places` keys the provider cache on
   * the destination alone, so this rebuilds the run from disk with no network call.
   *
   * `autoResolveAndGenerate` does the building, unchanged, so the routes-and-hours
   * preamble and the stage reporting are not duplicated here.
   */
  const resolveAllAndRebuild = useMutation({
    mutationFn: async () => {
      for (const rule of selectedComfort) {
        await rpc("accept_comfort_tradeoff", {
          trip_id: tripId,
          code: rule.code,
          value: rule.measured,
        });
      }
      if (needsRoutes) await rpc("accept_route_estimates", { trip_id: tripId });
      if (needsDays.length) {
        const basics = stored.data?.snapshot.data.trip_basics;
        const start = basics?.start_date;
        const end = basics?.end_date;
        if (!start || !end) throw new ApiError("setup_missing", {});
        // Written before the rebuild, so a place that comes back unplaced is known to
        // have had its day already and is recommended for removal rather than offered
        // the same button again. See `shared/dayExtension`.
        rememberDaysAddedFor(tripId, needsDays.map((item) => item.place_id));
        await rpc<SetupDraft>("save_setup", {
          trip_id: tripId,
          ...wholeDraftWithDates(stored.data ?? null, start, addDays(end, extraDays)),
        });
        await rpc("discover_places", { trip_id: tripId, force_refresh: false });
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["setup", tripId] }),
          queryClient.invalidateQueries({ queryKey: ["discovery", tripId] }),
        ]);
      }
      return autoResolveAndGenerate.mutateAsync();
    },
    onSuccess: async () => {
      setRefusal(null);
      await Promise.all(
        ["comfort_tradeoffs", "plan_preview", "journey", "candidate_choices"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key, tripId] }),
        ),
      );
    },
    onError: (error) => setRefusal(error instanceof ApiError ? error.code : String(error)),
  });

  const building =
    generate.isPending ||
    resolveAllAndRebuild.isPending ||
    autoResolveAndGenerate.isPending ||
    buyThenGenerate.isPending ||
    cutUnfitAndRebuild.isPending ||
    acceptRoutes.isPending ||
    dropAndRebuild.isPending;

  const activate = useMutation({
    mutationFn: (variant: string) =>
      rpc<unknown>("activate_plan_preview", { trip_id: tripId, variant_id: variant }),
    onSuccess: async () => {
      setRefusal(null);
      navigate(`/trips/${tripId}/itinerary`);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["journey", tripId] }),
        invalidatePlan(),
      ]);
    },
    // A stale input hash or an unready variant refuses with a stable code. It
    // has to be shown: activation is the one action that writes an immutable
    // plan version, so a silent failure would read as success.
    onError: (error) =>
      setRefusal(error instanceof ApiError ? error.code : String(error)),
  });

  if (choices.isPending || preview.isPending) return <Loading language={language} />;
  if (choices.isError) return <p className="field-error">⚠ {choices.error.message}</p>;
  if (preview.isError) return <p className="field-error">⚠ {preview.error.message}</p>;

  const trip = trips.data?.find((item) => item.trip_id === tripId);
  const considered = choices.data.filter((choice) => CONSIDERED.has(choice.action));
  const proposal = preview.data?.proposal.data ?? null;
  const optimizerInput = preview.data?.optimizer_input.data ?? null;
  const variants = proposal?.variants ?? [];
  const variant: PlanVariant | undefined =
    variants.find((item) => item.variant_id === variantId) ?? variants[0];
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
    (rule) => rule.exceeds && rule.measured !== null && !rule.covered,
  );

  /* Everything standing between this draft and a plan, derived in one place.
   *
   * It was derived in three, at three different depths of the tree, and each one had its
   * own button that rebuilt on its own. So the owner walked the refusals in series --
   * reported as "it went through like build them again -> accept the criteria -> add the
   * day -> add the day" -- paying a full rebuild for each, and only learning the next
   * condition after the last one had been applied. Four builds to answer four questions
   * that were all already known after the first. See `shared/planDecisions`. */
  const {
    unfit, impossible, selectedComfort, needsRoutes, needsDays, extraDays, outstanding,
  } = planDecisions(
    variant,
    tradeoffs.data?.rules ?? [],
    excludedComfort,
    optimizerInput?.candidates,
    // Read on every render rather than held in state: `resolveAllAndRebuild` writes it
    // and the rebuild that follows re-renders this, so a ref would have to be kept in
    // step by hand. `localStorage` also survives the reload a long build invites.
    placesDaysWereAddedFor(tripId),
  );

  const area = optimizerInput?.candidates?.find(
    (candidate) => candidate.id === variant?.hotel_recommendation?.default_area_id,
  );
  const assumptions = assumptionsOf(preview.data ?? null, proposal);
  const showBuildControls = !proposal || rebuilding;
  // A timetable exists and has not been activated yet, which is the only state where
  // the owner's next move is to confirm rather than to build.
  const timetableAwaitingConfirmation =
    Boolean(proposal) && proposal?.mode !== "stay_recommendation" && !rebuilding;
  const gaps = optimizerInput?.capability_gaps ?? [];
  // One label, two dead ends — the refusal card and an unusable variant's warnings.
  // It says "free" because it now is, and says what it assumes, because a button that
  // fills a gap has to name the value it filled it with.
  const autoResolveLabel = copy("auto_resolve_free", language);

  return (
    <section className="stage-card optimize-screen">
      {/* Once a timetable is on screen the page is no longer asking to build one, it is
          asking to accept one -- and the heading said "build" either way, so the activate
          button at the bottom read as optional and the plan was left un-activated. The
          `stay_recommendation` branch is excluded: that mode has no timetable to confirm,
          it has dates to choose. */}
      <header className="money-head">
        <h1>{copy(timetableAwaitingConfirmation ? "confirm_title" : "optimizer_title", language)}</h1>
        <p>{copy(timetableAwaitingConfirmation ? "confirm_help" : "optimizer_help", language)}</p>
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
          {/* One control, and the warning beside it rather than a choice above it.

              The history here is three shapes. Two buttons were two labels for one
              action. A radio group made the *payment* the question, which read as
              though building were blocked on answering it -- and the free option was
              preselected anyway, so the group asked a question whose answer never
              changed. Now the button says what pressing it accepts, and the gap it
              accepts is stated next to it.

              Buying verified hours has not gone anywhere; it lives on Check trip
              facts, which is the screen about evidence. It was never this screen's
              question. */}
          {/* Two different questions, and they were being asked with one control.

              Landing here for the first time, the question is how to fill the missing
              hours -- assume them free, or buy them confirmed. That is a real choice
              with a price attached and it belongs here, as a choice.

              Coming back with a plan already built, it is not. The question then is
              whether to accept the plan with the gaps it has, which is one button and a
              statement of what those gaps are. Collapsing the first case into the
              second removed a decision the owner wanted; that was my misreading. */}
          {/* Whenever the build controls are up -- a first build *or* a rebuild. Gated
              on `!proposal` this disappeared the moment a plan existed, so pressing
              "build again" offered the button and not the choice, which is the missing
              assume-free reported after the last change. "Before building the three
              variants" includes building them a second time. */}
          {evidence.data.needing_hours && showBuildControls ? (
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
          {/* Rebuilding an existing plan: the gap is stated, not re-negotiated. */}
          {evidence.data.needing_hours && proposal && !rebuilding ? (
            <p className="field-error" role="status">
              ⚠ {copyFormat("missing_criteria_warning", language, {
                needing: evidence.data.needing_hours,
                places: evidence.data.places,
              })}
            </p>
          ) : null}
        </section>
      ) : showBuildControls && considered.length && !building ? (
        <section aria-busy={evidence.isPending} className="evidence-verdict">
          <h2>{copy("before_you_build", language)}</h2>
          <p className={evidence.isError ? "field-error" : "setup-hint"}>
            {evidence.isError ? `⚠ ${evidence.error.message}` : copy("loading_build_options", language)}
          </p>
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
          disabled={considered.length === 0 || building || !evidence.data}
          onClick={() => {
            if (!evidence.data) return;
            if (!evidence.data.needing_hours) return generate.mutate();
            // The paid route only on a first build, where it was offered.
            if (!proposal && hoursChoice === "verified") return buyThenGenerate.mutate();
            return autoResolveAndGenerate.mutate();
          }}
          type="button"
        >
          {/* Always "build". This borrowed the accept label when a plan existed, which
              put "Accept all criteria and build the plan — free" here and "Accept
              criteria and rebuild" in the unfit section below -- the same mutation under
              two names, on screen together, which is the duplicate that keeps being
              reported. Accepting belongs where the failure is described; this button
              only ever builds. */}
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
      {building ? (
        <div aria-busy="true">
          <BuildProgress
            language={language}
            routesMeasured={routesMeasured}
            stage={autoResolveAndGenerate.isPending ? buildStage : undefined}
            previewStage={previewStage}
          />
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

      {/* A trip with no dates used to end here, at a table of how many days its places
          want and no way to act on it. The recommendation is now the input to choosing
          dates, which is the one thing that unlocks a timetable. */}
      {proposal?.mode === "stay_recommendation" ? (
        <StayPlanner language={language} proposal={proposal} tripId={tripId} />
      ) : null}

      {/* `WF-039`. Above the variant picker, because an overage is the reason a variant
          is unactivatable and the owner needs the choice before, not after, the button
          that refuses. Renders nothing when no budget is exceeded or agreed. */}
      {/* The same variant the accept control asks about, so the panel and the button
          cannot describe different plans. See the prop's own note. */}
      <ComfortTradeoffs language={language} tripId={tripId} variantId={shownVariantId} />

        <div hidden={building}>
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
            {/* Seven of the eight are sums of `duration_minutes` in
                `_schedule_metrics`; only `scheduled_visits` is a count, so it
                alone carries no unit -- the same shape the itinerary dayhead
                already renders. */}
            {METRICS.map((metric) => (
              <div className="money-tile" key={metric}>
                <span className="money-tile-label">{copy(metric, language)}</span>
                <strong className="money-tile-value">
                  {variant.metrics[metric] ?? 0}
                  {metric === "scheduled_visits" ? null : (
                    <small> {copy("minutes", language)}</small>
                  )}
                </strong>
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
          {/* **The message and a control render on the same condition.** They did not:
              the note above needed `comfortOnly`, the button needed `comfortOnly` *and*
              `overBudget`, and the two come from different places — `comfortOnly` from
              the stored variant's violations, `overBudget` from the live tradeoff report.
              They diverge whenever the report has no unaccepted figure to offer: the
              figure was already agreed and the plan not yet rebuilt, or the report is
              still arriving. The owner met the gap exactly as it reads — "I don't know
              what to do next, cause it no button anywhere".

              So when there is a figure to agree to, agreeing is the way out; when there
              is not, the stored variant is simply behind the agreement and rebuilding is.
              One of the two always renders. */}
          {!activationAllowed && comfortOnly.length ? (
            <div className="optimize-actions comfort-acceptance">
              {overBudget.length ? (
                <>
                  {overBudget.length > 1 ? (
                    <fieldset>
                      <legend>{copy("accept_criteria_choose", language)}</legend>
                      {overBudget.map((rule) => (
                        <label key={rule.code}>
                          <input
                            checked={!excludedComfort.has(rule.code)}
                            onChange={(event) => setExcludedComfort((current) => {
                              const next = new Set(current);
                              if (event.target.checked) next.delete(rule.code);
                              else next.add(rule.code);
                              return next;
                            })}
                            type="checkbox"
                          />
                          {copyFormat("accept_criterion", language, {
                            criterion: copyFrom("OPTIMIZER_CODE_TEXT", rule.code, language),
                            measured: rule.measured ?? "—",
                            threshold: rule.threshold ?? "—",
                          })}
                        </label>
                      ))}
                    </fieldset>
                  ) : null}
                  {/* One press, everything outstanding. This used to be `acceptAll`,
                      which agreed to the figures and rebuilt — and then the rebuild
                      surfaced the *next* condition, which had its own button and its own
                      rebuild. `resolveAllAndRebuild` applies the acceptance together with
                      whatever else this draft is waiting for and builds once; when the
                      figures are the only thing outstanding it does exactly what
                      `acceptAll` did. The steps are listed above the button when there is
                      more than one, so the press is never larger than it looks. */}
                  {outstanding.length > 1 ? (
                    <p className="setup-hint">
                      {outstanding
                        .map((item) => copy(`resolve_step_${item}`, language))
                        .join(" · ")}
                    </p>
                  ) : null}
                  <button
                    className="setup-primary"
                    disabled={building || selectedComfort.length === 0}
                    onClick={() => resolveAllAndRebuild.mutate()}
                    type="button"
                  >
                    {building
                      ? copy("loading", language)
                      : outstanding.length > 1
                        ? copy("resolve_all_and_continue", language)
                        : overBudget.length > 1
                          ? copy("accept_selected_and_continue", language)
                          : copyFormat("accept_measured_and_continue", language, {
                              measured: String(overBudget[0].measured),
                            })}
                  </button>
                </>
              ) : tradeoffs.isPending ? (
                /* Waiting, not a button. The report was still arriving and the screen
                   offered a bare "build them again" — a whole rebuild whose only effect
                   was that the second pass happened to have the figures loaded. The
                   owner reported it as the first of three presses to get one plan. */
                <p aria-busy="true" className="setup-hint">
                  {copy("loading", language)}
                </p>
              ) : (
                /* The report has loaded with nothing to agree to, while the drawn
                   variant still carries an `UNAPPROVED_` violation: the figures were
                   already accepted and this draft predates the acceptance. One rebuild
                   is the way out, and it goes through the same control as everything
                   else so there is one path that applies whatever is outstanding. */
                <button
                  className="setup-primary"
                  disabled={building}
                  onClick={() => resolveAllAndRebuild.mutate()}
                  type="button"
                >
                  {building
                    ? copy("loading", language)
                    : copy("resolve_all_and_continue", language)}
                </button>
              )}
            </div>
          ) : null}

          {/* Every place that did not make it, with the way out beside it. The table
              below says *what* happened; this says what to do about it, which is what
              was missing — a row reading "cannot currently fit" and nothing to press. */}
          {(() => {
            // `unfit`, `needsRoutes`, `needsDays` and `extraDays` are derived once at the
            // top of the component now: `resolveAllAndRebuild` needs the same four facts
            // to apply every outstanding decision in one pass, and deriving them twice is
            // how the button and the sentence beside it come to disagree.
            //
            // "The trip has no remaining time capacity" is the honest residual: these
            // places fit nothing that is wrong, there are simply more of them than the
            // days hold. The optimizer cannot invent a day — the dates are the owner's —
            // so the only useful thing to say is how short the trip is and where to
            // lengthen it. Saying it without that link was the dead end reported.
            if (!unfit.length) return null;
            return (
              <section className="optimize-unfit">
                <h2 className="money-eyebrow">{copy("unfit_title", language)}</h2>
                <p className="setup-hint">{copy("unfit_help", language)}</p>
                {needsDays.length ? (
                  <>
                    <p className="setup-hint">
                      {copyFormat("unfit_needs_days", language, {
                        count: needsDays.length,
                        days: variant.days.length,
                      })}
                    </p>
                    {/* Both ways out run the same rebuild as the big button, so both
                        hide the old draft while it runs. The wizard link is gone on
                        purpose: it threw away this screen — the refusal, the reasons,
                        the plan so far — to change one date, and coming back meant
                        building again from the top.

                        The primary control is `resolveAllAndRebuild`, not the
                        day-extension on its own: whatever else this draft is waiting for
                        — an unapproved comfort figure, an unrouted pair — is applied in
                        the same pass, so the owner is not walked through the refusals one
                        rebuild at a time. When days are the only thing outstanding the
                        two are the same action; `outstanding` says which. */}
                    {outstanding.length > 1 ? (
                      <p className="setup-hint">
                        {outstanding
                          .map((item) => copy(`resolve_step_${item}`, language))
                          .join(" · ")}
                      </p>
                    ) : null}
                    <div className="optimize-actions">
                      <button
                        className="setup-primary"
                        disabled={building || cutUnfitAndRebuild.isPending}
                        onClick={() => resolveAllAndRebuild.mutate()}
                        type="button"
                      >
                        {copyFormat("unfit_add_days", language, { count: extraDays })}
                      </button>
                      <button
                        disabled={building || cutUnfitAndRebuild.isPending}
                        onClick={() =>
                          cutUnfitAndRebuild.mutate(needsDays.map((item) => item.place_id ?? ""))
                        }
                        type="button"
                      >
                        {copyFormat("unfit_cut_places", language, {
                          count: needsDays.length,
                        })}
                      </button>
                    </div>
                  </>
                ) : null}
                {/* Places no length of trip will hold, and so the one case where "add a
                    day" must not be offered.

                    Reported as: press "add 3 days and rebuild once", get another plan
                    still showing the same button. It was not a UI bug — `_skip_reason`
                    answered `NO_TIME_CAPACITY` for anything unplaced that was not in
                    `skipped`, and a `must_do` place is never in `skipped`, so a place
                    that could not fit *for any reason* was reported as the trip being
                    short of time. Measured on a place whose own visit exceeds a
                    09:00-21:00 window: the same refusal at 3, 4, 6, 9 and 14 days.

                    `NO_DAY_LONG_ENOUGH` is the optimizer's answer to "could this fit an
                    empty day", so removing the place really is the only way forward and
                    that is what this offers. `cutUnfitAndRebuild` is the same mutation
                    the capacity branch uses; only the reason and the wording differ. */}
                {impossible.length ? (
                  <>
                    <p className="field-error" role="status">
                      {/* Two ways to reach this list and they are not the same claim,
                          so they do not share a sentence. `NO_DAY_LONG_ENOUGH` is
                          proved — no day of any length holds the place. The other is
                          experience: days were added for it and it still did not fit.
                          Saying the first about the second would assert something
                          stronger than what happened. */}
                      ⚠ {impossible.every((item) => item.reason === "NO_DAY_LONG_ENOUGH")
                        ? copyFormat("unfit_impossible", language, {
                            count: impossible.length,
                          })
                        : copyFormat("unfit_days_did_not_help", language, {
                            count: impossible.length,
                          })}
                    </p>
                    <div className="optimize-actions">
                      <button
                        className="setup-primary"
                        disabled={building || cutUnfitAndRebuild.isPending}
                        onClick={() =>
                          cutUnfitAndRebuild.mutate(
                            impossible.map((item) => item.place_id ?? ""),
                          )
                        }
                        type="button"
                      >
                        {copyFormat("unfit_drop_impossible", language, {
                          count: impossible.length,
                        })}
                      </button>
                    </div>
                  </>
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
                {/* This screen's own words, not the general free-build label. Routes are
                    *measured*, not assumed -- a router is asked, and when it refuses the
                    leg stays unverified however the hours were filled. That is why "the
                    route is not verified" can follow choosing "assume free": the free
                    choice covers hours, and this covers what the measuring could not
                    reach. Replacing the label rather than adding a second control, so
                    one action is never two buttons on one screen. */}
                {/* The only control that runs this mutation, and it lives here because
                    here is where the failure is described. It fixes every listed place
                    at once; the per-place drop below it stays, for the one place that
                    will not come good however the legs are estimated. */}
                {needsRoutes && !acceptRoutes.isPending ? (
                  <>
                    <p className="field-error" role="status">
                      ⚠ {copy("routes_unverified_warning", language)}
                    </p>
                    <button
                      className="setup-primary"
                      onClick={() => acceptRoutes.mutate()}
                      type="button"
                    >
                      {copy("accept_criteria_rebuild", language)}
                    </button>
                  </>
                ) : null}
                <ul className="optimize-unfit-list" hidden={acceptRoutes.isPending}>
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

          {/* "What happened to each place you kept" removed at the owner's asking.
              Every row it could carry is now said where it is actionable: a place that
              fits is on the timeline below, and a place that does not is in the
              `optimize-unfit` list above with the way out beside it. The table was the
              third place the same facts appeared and the only one with nothing to press.
              `reason` and `consequence` stay on the wire — `/itinerary` still lists the
              unscheduled ones — so nothing about the payload changed. */}

          {variant.days.some((day) => day.items.length > 0) ? (
            <>
              <h2 className="money-eyebrow">{copy("timeline", language)}</h2>
              {/* One collapsible group per day, at the owner's asking.
                  It was a single flat table of every item on every day — on a real trip
                  sixty-odd rows, and the date printed once per day with a rule under it
                  was as far as a flat table could go towards being readable. Grouping is
                  what it wanted: a day is the unit a reader scans by.

                  Collapsed by default, so the **summary line has to be worth reading on
                  its own** — the date, how many places, and the hours the day actually
                  runs. Otherwise collapsing would just hide the timeline. `<details>`
                  rather than a click handler and state: the platform gives the toggle,
                  the keyboard behaviour and the open/closed semantics for a screen
                  reader, and none of it has to be right forever in our own code. */}
              {variant.days
                .filter((day) => day.items.length > 0)
                .map((day) => {
                  const visits = day.items.filter((item) => item.type === "visit").length;
                  const from = day.items[0].start;
                  const to = day.items[day.items.length - 1].end;
                  return (
                    <details className="timeline-day" key={day.date}>
                      <summary>
                        <span className="timeline-day-date">{day.date}</span>
                        <span className="timeline-day-facts">
                          {copyFormat("timeline_day_summary", language, {
                            places: visits,
                            start: from,
                            end: to,
                          })}
                        </span>
                      </summary>
                      <div className="money-table-scroll">
                        <table className="money-table timeline-table">
                          <thead>
                            <tr>
                              <th>{copy("start", language)}</th>
                              <th>{copy("end", language)}</th>
                              <th>{copy("item_type", language)}</th>
                              <th>{copy("place_or_leg", language)}</th>
                              <th>{copy("duration", language)}</th>
                            </tr>
                          </thead>
                          {/* The kind is a coloured chip in the same five families the
                              itinerary's own rows use, and it is translated — it was the
                              raw `visit` / `buffer` code in both languages. */}
                          <tbody>
                            {day.items.map((item, index) => (
                              <tr key={`${day.date}-${index}`}>
                                <td className="money-num">
                                  {item.start}
                                </td>
                                <td className="money-num">
                                  {item.end}
                                </td>
                                <td>
                                  <span className={`plan-row-kind ${item.type}`}>
                                    {item.type === "buffer" &&
                                    (item.reason === "free_time_or_rest" || item.reason === "day_ends_free")
                                      ? copyFrom("OPTIMIZER_CODE_TEXT", item.reason, language)
                                      : copy(`type_${item.type}`, language)}
                                  </span>
                                </td>
                                {/* Empty rather than the raw `buffer` / `travel` code it
                                    used to repeat: the chip beside it already says
                                    which it is. */}
                                <td>
                                  {item.name ? placeName(item, language, item.name) : ""}
                                </td>
                                <td className="money-num">
                                  {item.duration_minutes} {copy("minutes", language)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  );
                })}
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
            {/* One label for both cases, and `optimize-activate` to give it the weight
                of a terminal action.

                It read "Use and export this provisional itinerary" — a sentence, on a
                control the size of the "Places" link beside it, at the end of the
                longest screen in the app. The provisional caveat is already on screen
                immediately above in `provisional_activation_help`, which says it stays
                Provisional and must be optimized again after a change, so the button
                does not have to carry it a second time. `activate_plan` is "Use this
                itinerary" and has always been the non-provisional label; the two cases
                differ in what is true of the plan, not in what the press does. */}
            <button
              className="setup-primary optimize-activate"
              disabled={!activationAllowed || activate.isPending}
              onClick={() => activate.mutate(variant.variant_id)}
              type="button"
            >
              {activate.isPending
                ? copy("opening_itinerary", language)
                : copy("activate_plan", language)}
            </button>
            <Link className="primary-link" to={`/trips/${tripId}/places`}>
              {copy("stage_places", language)}
            </Link>
          </div>
        </>
      ) : null}
        </div>
    </section>
  );
}
