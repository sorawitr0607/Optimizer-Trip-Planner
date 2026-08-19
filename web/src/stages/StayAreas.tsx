import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiError, rpc, type StayAreaReport } from "../api/client";
import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";
import { placeAltName, placeName } from "../shared/names";

/**
 * Where to stay, for an owner who has not booked. `WF-040`.
 *
 * Under the deck on `/places` by the owner's own choice, so the ranking sits beside the
 * places that produce it rather than beside the timetable on `/optimize`, where
 * `hotel_recommendation` renders.
 *
 * Owner-triggered rather than automatic. It is free — one Overpass request for the whole
 * shortlist — but it is still a network call, and this app's rule is that a
 * network-requiring action says so before it is pressed.
 *
 * **The gaps are not a footnote.** `not_evaluated` renders as prominently as the scores,
 * because the owner's real constraint last week was a family room that only existed on
 * Airbnb, and nothing in OpenStreetMap could have known that. A ranking that stayed
 * quiet about price and room type would read as a recommendation to book.
 */

const FACTORS = ["travel_time", "metro_access", "food_nearby", "after_dark", "lodging_choice"] as const;

export interface StayAreasProps {
  tripId: string;
  language: Language;
  /** Told when the ranking has been attempted, and whether this destination can be
   *  ranked at all — the centre-of-my-places fallback is only an answer once the
   *  question has actually been asked. */
  onOutcome?: (outcome: "ranked" | "unrankable") => void;
  /** Called once an area has been adopted as the base, so the page can move on. */
  onChosen?: () => void;
  /** Told while the ranking runs, so the page can put away the controls that ask the
   *  same question a different way. */
  onRanking?: (busy: boolean) => void;
}

export function StayAreas({ tripId, language, onOutcome, onChosen, onRanking }: StayAreasProps) {
  const queryClient = useQueryClient();
  const recommend = useMutation<StayAreaReport, Error, void>({
    mutationFn: () => rpc<StayAreaReport>("recommend_areas", { trip_id: tripId }),
    // Ranking reads the transit graph and takes a while. The page above this is a form
    // for the *other* way of answering the same question, so leaving it up invites
    // filling in an address that the ranking is about to make irrelevant -- the same
    // reasoning `/optimize` already applies to its pace picker.
    onMutate: () => onRanking?.(true),
    onSuccess: (report) => onOutcome?.(report.areas.length ? "ranked" : "unrankable"),
    onError: () => onOutcome?.("unrankable"),
    onSettled: () => onRanking?.(false),
  });
  const chooseArea = useMutation({
    mutationFn: (area: { name: string; latitude: number; longitude: number }) =>
      rpc("confirm_accommodation_base", {
        trip_id: tripId,
        query: area.name,
        latitude: area.latitude,
        longitude: area.longitude,
      }),
    onSuccess: () => {
      // The write is complete. Cache refreshes must not hold navigation hostage.
      onChosen?.();
      void Promise.all(
        ["accommodation_base", "journey", "plan_preview"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key, tripId] }),
        ),
      );
    },
  });
  const report = recommend.data;

  return (
    <section className="stay-areas">
      <h3>{copy("stay_areas", language)}</h3>
      <p className="setup-hint">{copy("stay_areas_hint", language)}</p>
      <button
        className="setup-primary"
        disabled={recommend.isPending}
        onClick={() => recommend.mutate()}
        type="button"
      >
        {recommend.isPending ? copy("loading", language) : copy("rank_areas", language)}
      </button>
      {recommend.isPending ? (
        <p aria-live="polite" aria-busy="true" className="thinking">
          <span className="thinking-dot" />
          <span>{copy("ranking_areas", language)}</span>
        </p>
      ) : null}
      {/* Choosing an area geocodes it before it can be stored, so the tick is a network
          round trip and not a local toggle. It disabled itself and said nothing, which
          reads as a tick that did not take. */}
      {chooseArea.isPending ? (
        <p aria-live="polite" aria-busy="true" className="thinking">
          <span className="thinking-dot" />
          <span>{copy("saving_area", language)}</span>
        </p>
      ) : null}

      {/* The refusal's own words. This printed `areas_amenities_unavailable` for *every*
          failure — the message for a partial success, where travel time and metro access
          scored and only the counts were missing. So a call that died outright
          (`no_transit_graph_for_areas`, measured against the owner's New York trip when
          Overpass was unreachable) read as a call that half-worked, and the owner saw that
          sentence above an empty section with no output and no reason. */}
      {recommend.isError ? (
        <p className="setup-hint">
          {recommend.error instanceof ApiError
            ? copyFrom("OPTIMIZER_CODE_TEXT", recommend.error.code, language)
            : String(recommend.error)}
        </p>
      ) : null}
      {chooseArea.isError ? (
        <p className="field-error" aria-live="polite">
          ⚠ {chooseArea.error instanceof ApiError
            ? copyFrom("OPTIMIZER_CODE_TEXT", chooseArea.error.code, language)
            : String(chooseArea.error)}
        </p>
      ) : null}

      {report ? (
        <>
          <p className="setup-hint">
            {copyFormat("areas_considered", language, {
              shortlist: String(report.areas.length),
              considered: String(report.considered_area_count),
            })}
          </p>
          {report.amenities_counted ? null : (
            <p className="setup-hint">{copy("areas_amenities_unavailable", language)}</p>
          )}
          {report.reason ? (
            <p className="setup-hint">{copyFrom("OPTIMIZER_CODE_TEXT", report.reason, language)}</p>
          ) : null}

          {report.areas.length === 0 && !report.reason ? (
            <p className="setup-hint">{copy("areas_none_ranked", language)}</p>
          ) : null}

          <ol className="stay-area-list">
            {report.areas.map((area) => (
              // derives-from: element 26 .recent-row-item as .stay-area-row
              <li className="stay-area-row" key={area.area_id}>
                <header>
                  <strong>
                    {placeName(area, language, area.name)}
                    {placeAltName(area, language) ? (
                      // The station sign and the taxi driver both use the local name.
                      <small className="place-alt-name">{placeAltName(area, language)}</small>
                    ) : null}
                  </strong>
                  <span className="place-score">
                    {area.total_score.toFixed(1)}
                    <small>/100</small>
                  </span>
                </header>
                <p className="setup-hint">
                  {copyFormat("area_travel_summary", language, {
                    minutes: String(area.median_travel_minutes),
                    reachable: String(area.reachable_place_count),
                    total: String(report.place_count),
                  })}
                </p>
                <dl className="stay-area-factors">
                  {FACTORS.map((factor) => (
                    <div key={factor}>
                      <dt>{copyFrom("OPTIMIZER_CODE_TEXT", factor, language)}</dt>
                      <dd>
                        {area.factors[factor]?.score ?? 0}/{area.factors[factor]?.max ?? 0}
                        {factor === "food_nearby" ? ` · ${area.counts.food_count}` : null}
                        {factor === "after_dark" ? ` · ${area.counts.after_dark_count}` : null}
                        {factor === "lodging_choice" ? ` · ${area.counts.lodging_count}` : null}
                      </dd>
                    </div>
                  ))}
                </dl>
                {/* The point of ranking areas is to pick one. Without this the list was a
                    verdict with nothing to press, and the owner had to retype a station
                    name into the box above — through a geocoder, for a point already
                    known exactly here. Coordinates go straight in. */}
                {area.latitude !== null && area.longitude !== null ? (
                  <button
                    className="stay-area-pick"
                    disabled={chooseArea.isPending}
                    onClick={() =>
                      chooseArea.mutate({
                        name: placeName(area, language, area.name),
                        latitude: area.latitude as number,
                        longitude: area.longitude as number,
                      })
                    }
                    type="button"
                  >
                    {copy("use_this_area", language)}
                  </button>
                ) : null}
                {area.notes.length ? (
                  <p className="setup-hint">
                    {area.notes
                      .map((note) => copyFrom("OPTIMIZER_CODE_TEXT", note, language))
                      .join(" · ")}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>

          <h4>{copy("areas_not_evaluated", language)}</h4>
          <ul className="stay-area-gaps">
            {report.not_evaluated.map((code) => (
              <li key={code}>{copyFrom("OPTIMIZER_CODE_TEXT", code, language)}</li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
