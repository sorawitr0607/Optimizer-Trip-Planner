import { useMutation } from "@tanstack/react-query";

import { rpc, type StayAreaReport } from "../api/client";
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
}

export function StayAreas({ tripId, language }: StayAreasProps) {
  const recommend = useMutation<StayAreaReport, Error, void>({
    mutationFn: () => rpc<StayAreaReport>("recommend_areas", { trip_id: tripId }),
  });
  const report = recommend.data;

  return (
    <section className="stay-areas">
      <h3>{copy("stay_areas", language)}</h3>
      <p className="setup-hint">{copy("stay_areas_hint", language)}</p>
      <button disabled={recommend.isPending} onClick={() => recommend.mutate()} type="button">
        {copy("rank_areas", language)}
      </button>

      {recommend.isError ? (
        <p className="setup-hint">{copy("areas_amenities_unavailable", language)}</p>
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
