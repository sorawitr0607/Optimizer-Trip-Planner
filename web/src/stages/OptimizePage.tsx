import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router";

import {
  ApiError,
  rpc,
  type CandidateChoice,
  type PlanPreview,
  type PlanVariant,
  type Trip,
} from "../api/client";
import { copy, copyFrom } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { placeName } from "../shared/names";

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

export function OptimizePage() {
  const { tripId = "" } = useParams();
  const { language } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [variantId, setVariantId] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);

  const trips = useQuery({ queryKey: ["trips"], queryFn: () => rpc<Trip[]>("list_trips") });
  const choices = useQuery({
    queryKey: ["candidate_choices", tripId],
    queryFn: () => rpc<CandidateChoice[]>("list_candidate_choices", { trip_id: tripId }),
  });
  const preview = useQuery({
    queryKey: ["plan_preview", tripId],
    queryFn: () => rpc<PlanPreview | null>("get_plan_preview", { trip_id: tripId }),
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

  const provisionalAllowed = Boolean(
    trip?.planning_mode === "explore_first" &&
      variant?.status === "provisional" &&
      variant?.validation?.valid,
  );
  const activationAllowed = variant?.status === "ready" || provisionalAllowed;

  const area = optimizerInput?.candidates?.find(
    (candidate) => candidate.id === variant?.hotel_recommendation?.default_area_id,
  );

  return (
    <section className="stage-card optimize-screen">
      <header className="money-head">
        <h1>{copy("optimizer_title", language)}</h1>
        <p>{copy("optimizer_help", language)}</p>
      </header>

      {refusal ? (
        <p className="field-error" aria-live="polite">
          ⚠ {copyFrom("OPTIMIZER_CODE_TEXT", refusal, language)}
        </p>
      ) : null}

      <div className="optimize-actions">
        <button
          className="setup-primary"
          disabled={considered.length === 0 || generate.isPending}
          onClick={() => generate.mutate()}
          type="button"
        >
          {generate.isPending ? copy("optimizing", language) : copy("generate_plan", language)}
        </button>
      </div>
      {/* A disabled primary action always says why. */}
      {considered.length === 0 ? (
        <p className="setup-hint">{copy("choose_before_plan", language)}</p>
      ) : null}

      {proposal?.mode === "stay_recommendation" ? (
        <>
          <h2 className="money-eyebrow">{copy("stay_recommendation", language)}</h2>
          <div className="money-table-scroll">
            <table className="money-table">
              <thead>
                <tr>
                  <th>{copy("stay_option", language)}</th>
                  <th>{copy("days", language)}</th>
                  <th>{copy("daily_capacity", language)}</th>
                </tr>
              </thead>
              <tbody>
                {(proposal.stay_recommendations ?? []).map((item) => (
                  <tr key={item.id}>
                    <td>{copy(item.id, language)}</td>
                    <td className="money-num">{item.days}</td>
                    <td className="money-num">
                      {item.daily_capacity_minutes} {copy("minutes", language)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

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

          {/* derives-from: element 14 .stat-card / .stat-cards-grid, three per
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
            </details>
          ) : null}

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
                  <tbody>
                    {variant.days.flatMap((day) =>
                      day.items.map((item, index) => (
                        <tr key={`${day.date}-${index}`}>
                          <td>{day.date}</td>
                          <td className="money-num">{item.start}</td>
                          <td className="money-num">{item.end}</td>
                          <td>{item.type}</td>
                          <td>{placeName(item, language, item.name ?? item.type)}</td>
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
          {!activationAllowed ? (
            <p className="setup-hint">{copy("activation_disabled", language)}</p>
          ) : null}
          <div className="optimize-actions">
            <button
              className="setup-primary"
              disabled={!activationAllowed || activate.isPending}
              onClick={() => activate.mutate(variant.variant_id)}
              type="button"
            >
              {copy(provisionalAllowed ? "use_provisional_plan" : "activate_plan", language)}
            </button>
          </div>
        </>
      ) : null}
    </section>
  );
}
