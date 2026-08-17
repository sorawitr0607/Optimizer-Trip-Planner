import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { ApiError, rpc, type AccommodationBase } from "../api/client";
import { copy } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { StayAreas } from "./StayAreas";

/**
 * Where to stay. One screen, at the owner's asking, 2026-08-14.
 *
 * The question was split across two screens that are about other things. The area
 * ranking sat under the deck on `/places`, where it competed with several hundred cards
 * for attention and was reported as a section with no visible output; the accommodation
 * base sat as one card among five on `/evidence`, which is where evidence is *checked*
 * rather than where a decision is made. So the two halves of one question — which
 * neighbourhood, and then which address — were never on screen together, and neither
 * said what the planner was actually doing in the meantime.
 *
 * That last part is the reason this page exists rather than being a heading. Without a
 * confirmed base the optimizer plans from the **centre of the places you chose**, which
 * is a reasonable default and was completely invisible: an owner who had booked nothing
 * had no way to know a base was being assumed on their behalf, and an owner whose base
 * was wrong had no way to see that either — which is exactly how a hotel 286 km from the
 * trip survived to plan an itinerary around itself.
 */

export function StayPage() {
  const { tripId = "" } = useParams();
  const navigate = useNavigate();
  const { language } = useLanguage();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  /** Null until the ranking has been run at all. */
  const [outcome, setOutcome] = useState<"ranked" | "unrankable" | null>(null);

  const base = useQuery({
    queryKey: ["accommodation_base", tripId],
    queryFn: () => rpc<AccommodationBase | null>("get_accommodation_base", { trip_id: tripId }),
  });

  const saveBase = useMutation({
    // Never the empty query. `confirm_accommodation_base("")` geocodes
    // `"{destination} Station"`, which for "New York, United States" resolved 286 km
    // upstate and was then stored as a *booked* base. A base is something the owner
    // types, or it is not a base.
    mutationFn: () =>
      rpc<AccommodationBase>("confirm_accommodation_base", {
        trip_id: tripId,
        query: (query ?? base.data?.name ?? "").trim(),
      }),
    onSuccess: async () => {
      setFlash("accommodation_base_saved");
      await Promise.all(
        ["accommodation_base", "journey", "plan_preview"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key, tripId] }),
        ),
      );
      // Naming an address answers this page as completely as picking an area does, so it
      // goes the same way. Both were reported as "didn't work" for the same reason:
      // they succeeded silently and left the owner looking at the form they had just
      // finished with.
      navigate(`/trips/${tripId}/optimize`);
    },
    onError: (error) => setFlash(error instanceof ApiError ? error.code : String(error)),
  });

  const accept = useMutation({
    mutationFn: () => rpc("accept_provisional_base", { trip_id: tripId }),
    onSuccess: async () => {
      setFlash("stay_accepted");
      await queryClient.invalidateQueries({ queryKey: ["journey", tripId] });
      // On to the plan. This is the terminal answer to the question the page asks — "I
      // am not booking anything, use the middle of my places" — and leaving the owner on
      // the screen afterwards was reported as "the build plan not show": the stage was
      // complete, the sidebar had unlocked, and nothing said where that had happened.
      navigate(`/trips/${tripId}/optimize`);
    },
    onError: (error) => setFlash(error instanceof ApiError ? error.code : String(error)),
  });

  const typed = (query ?? base.data?.name ?? "").trim();

  return (
    <section className="stage-card">
      <header className="money-head">
        <h1>{copy("stay_page_title", language)}</h1>
        <p>{copy("stay_page_help", language)}</p>
      </header>

      {/* What the planner is using right now, stated before anything is offered. An
          assumption nobody is told about is indistinguishable from a fact.
          derives-from: element 36 .currency-info-box as .evidence-card — the same
          one-card-per-decision block `/evidence` uses, which is where this came from. */}
      <div className="evidence-card">
        <strong>{copy("stay_current_base", language)}</strong>
        {base.data && base.data.used_by_planner !== false ? (
          <span className="evidence-value">
            {base.data.name}
            {base.data.address ? ` · ${base.data.address}` : ""}
          </span>
        ) : (
          <span className="setup-hint">{copy("stay_using_centroid", language)}</span>
        )}
        {/* A stored base the planner has discarded. Printing it as "what the planner is
            using" would be the same untrue statement the guard exists to stop, so the
            page says both things: the address on file, and that the plan is not built
            from it. The verdict comes from the server, computed by the same helper the
            optimizer uses — a second copy of that distance rule here is how the two
            would come to disagree. */}
        {base.data?.used_by_planner === false ? (
          <p className="field-error">
            ⚠ {copy("stay_base_ignored", language)} {base.data.name}
          </p>
        ) : null}
      </div>

      <div className="evidence-card">
        <strong>{copy("accommodation_base_title", language)}</strong>
        <span className="setup-hint" id="base-help">
          {copy("accommodation_base_help", language)}
        </span>
        <label>
          {copy("accommodation_query", language)}
          <input
            aria-describedby={typed.length === 0 ? "base-help base-empty" : "base-help"}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={copy("accommodation_query_example", language)}
            value={query ?? base.data?.name ?? ""}
          />
        </label>
        {/* Disabled on an empty field rather than defaulting it: the empty query is the
            bug, so there is no harmless version of pressing this with nothing typed. */}
        <button
          disabled={saveBase.isPending || typed.length === 0}
          onClick={() => saveBase.mutate()}
          type="button"
        >
          {copy("save_accommodation_base", language)}
        </button>
        {typed.length === 0 ? (
          <span className="setup-hint" id="base-empty">
            {copy("stay_type_a_place", language)}
          </span>
        ) : null}
        {flash ? (
          <p aria-live="polite" className="setup-hint">
            {copy(flash, language)}
          </p>
        ) : null}
      </div>

      {/* The way out for a trip this cannot rank, and **only** then, at the owner's
          asking. `recommend_areas` needs a transit graph, and a city whose metro
          OpenStreetMap does not carry has none — `no_transit_graph_for_areas`. Offered
          up front it competed with the ranking for the same decision; offered after the
          ranking has been tried and come back empty, it is the answer to a question that
          was actually asked. A destination that ranks fine completes this stage by
          picking an area instead. */}
      <div className="evidence-card" hidden={outcome !== "unrankable"}>
        <strong>{copy("stay_accept_centre_title", language)}</strong>
        <span className="setup-hint">{copy("stay_accept_centre_help", language)}</span>
        <button
          className={base.data ? undefined : "setup-primary"}
          disabled={accept.isPending}
          onClick={() => accept.mutate()}
          type="button"
        >
          {copy("stay_accept_centre", language)}
        </button>
      </div>

      <StayAreas
        language={language}
        onChosen={() => navigate(`/trips/${tripId}/optimize`)}
        onOutcome={setOutcome}
        tripId={tripId}
      />

      {/* Picking an area answers this page too, but unlike accepting the centre it is not
          obviously terminal — an owner may want to compare two before moving on — so this
          waits to be pressed rather than navigating under them. */}
      {base.data ? (
        <div className="optimize-actions">
          <Link className="setup-primary" to={`/trips/${tripId}/optimize`}>
            {copy("stage_optimize", language)} →
          </Link>
        </div>
      ) : null}
    </section>
  );
}
