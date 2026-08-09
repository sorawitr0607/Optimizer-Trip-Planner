import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  ApiError,
  rpc,
  type MonthGuide,
  type PlanProposal,
  type SetupDraft,
} from "../api/client";
import { copy, copyFormat, type Language } from "../i18n/copy";

/**
 * The way out of a trip with no dates.
 *
 * Without them `optimize_trip` returns `mode: "stay_recommendation"` — how many days the
 * chosen places want, at three paces — and that was the end of the road: a table, no
 * next step, and the itinerary permanently out of reach. The owner's report was "without
 * time date I can not go on into itinerary", which was accurate.
 *
 * So the recommendation becomes a choice. Pick a pace, pick a rough month, and the app
 * writes provisional dates into setup — which is the one thing that unlocks a real
 * timetable, because a schedule needs days to put visits on.
 *
 * Two things this deliberately does not do. It does not invent a *precise* departure: the
 * dates land on the first of the chosen month and are described as provisional, because
 * the owner edits them in setup and only they know the real flight. And it does not
 * pretend the rest of the pipeline is unaffected — changing setup changes its hash, so
 * any discovery already run for the old setup is stale and the screen says so rather than
 * letting the next stage refuse with a code.
 */

const MONTH_COUNT = 12;

/** `save_setup` defaults every field to empty, so a partial payload erases what it
 *  omits. The whole draft is read back and resent with only the dates changed. */
function wholeDraftWithDates(
  stored: SetupDraft | null,
  start: string,
  end: string,
): Record<string, unknown> {
  const payload = stored?.snapshot.data ?? {};
  const owner = payload.owner ?? {};
  const basics = payload.trip_basics ?? {};
  return {
    start_date: start,
    end_date: end,
    arrival_time: basics.arrival_time ?? null,
    departure_time: basics.departure_time ?? null,
    accommodation_status: basics.accommodation_status ?? "unknown",
    owner_age: owner.age ?? null,
    main_style: owner.main_style ?? [],
    also_enjoy: owner.also_enjoy ?? [],
    avoid: owner.avoid ?? [],
    comfort: owner.comfort ?? [],
    owner_description: owner.description ?? "",
    owner_must_respect: (owner.must_respect ?? []).join("\n"),
    owner_nationality: owner.nationality ?? null,
    travellers: (payload.travellers ?? []).map((member) => ({
      ...member,
      age: member.age ?? 0,
    })),
    confirmed: true,
  };
}

/** The next occurrence of a month, so a chosen month is never already past. */
function firstOfMonth(month: number, today: Date): string {
  const year = month <= today.getMonth() + 1 ? today.getFullYear() + 1 : today.getFullYear();
  return `${year}-${String(month).padStart(2, "0")}-01`;
}

/** Date arithmetic in UTC, formatted from UTC parts.
 *
 *  Built on a local `new Date(...)` and `toISOString()` this was a day short east of
 *  Greenwich: local midnight on the 5th is 17:00 on the 4th in UTC+7, so a five-day
 *  trip rendered as 1st to 4th. Caught by the test, not by reading it. */
function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export interface StayPlannerProps {
  tripId: string;
  language: Language;
  proposal: PlanProposal;
  today?: Date;
}

export function StayPlanner({ tripId, language, proposal, today = new Date() }: StayPlannerProps) {
  const queryClient = useQueryClient();
  const options = proposal.stay_recommendations ?? [];
  const [pace, setPace] = useState<string>(options[1]?.id ?? options[0]?.id ?? "");
  // Two months out: near enough to plan for, far enough to still book. `getMonth()` is
  // zero-based, so +2 on it is already "two months ahead" once the +1 makes it a number.
  const [month, setMonth] = useState<number>(((today.getMonth() + 2) % MONTH_COUNT) + 1);
  const [saved, setSaved] = useState(false);
  // The recommended range, once accepted. Held rather than applied immediately so the
  // dates below stay the single thing that gets saved.
  const [windowChosen, setWindowChosen] = useState<{ start: string; end: string } | null>(null);

  const chosen = options.find((item) => item.id === pace) ?? options[0];

  const stored = useQuery({
    queryKey: ["setup", tripId],
    queryFn: () => rpc<SetupDraft | null>("get_setup", { trip_id: tripId }),
  });
  // Owner-triggered, like every other network read on this app: free, but it is two
  // requests to public services and this screen is reached by anyone with no dates.
  const guide = useQuery({
    queryKey: ["month_guide", tripId, chosen?.days ?? 0],
    queryFn: () =>
      rpc<MonthGuide>("travel_month_guide", { trip_id: tripId, days: chosen?.days ?? null }),
    enabled: false,
    staleTime: Infinity,
  });

  const chosenMonth = guide.data?.months.find((item) => item.month === month);
  const defaultStart = firstOfMonth(month, today);
  const start = windowChosen?.start ?? defaultStart;
  const end = windowChosen?.end ?? (chosen ? addDays(start, Math.max(chosen.days - 1, 0)) : start);

  const save = useMutation({
    mutationFn: async () => {
      const draft = await rpc<SetupDraft>("save_setup", {
        trip_id: tripId,
        ...wholeDraftWithDates(stored.data ?? null, start, end),
      });
      // Re-link discovery to the setup it now belongs to.
      //
      // Saving dates moves the setup hash, and discovery stores the hash it was run
      // against — so the places already found went stale and the planner refused to
      // schedule them. Telling the owner to "run discovery again" was a dead end
      // dressed as advice: this screen exists *because* they have places and no dates.
      //
      // It costs nothing to do for them. `discover_places` keys the provider cache on
      // the destination alone, so with a 7-day-fresh entry this rebuilds the run from
      // disk with no network call — measured at 0.05s on a 715-place Seoul catalogue —
      // and `place_id` is a hash of name, coordinates and category, so every existing
      // choice still points at the same place. Not forced: a forced refresh would go
      // back to Overpass and undo the whole point.
      await rpc("discover_places", { trip_id: tripId, force_refresh: false });
      return draft;
    },
    onSuccess: async () => {
      setSaved(true);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["setup", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["journey", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["discovery", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["ranking", tripId] }),
      ]);
    },
  });

  if (!options.length) return null;

  return (
    // derives-from: element 36 .currency-info-box as .stay-planner
    <section className="stay-planner">
      <h2 className="money-eyebrow">{copy("stay_pace_title", language)}</h2>
      <p className="setup-hint">{copy("stay_pace_help", language)}</p>

      <div className="stay-pace-options" role="group" aria-label={copy("stay_pace_title", language)}>
        {options.map((item) => (
          <button
            aria-pressed={item.id === chosen?.id}
            className={`stay-pace${item.id === chosen?.id ? " active" : ""}`}
            key={item.id}
            onClick={() => { setPace(item.id); setSaved(false); setWindowChosen(null); }}
            type="button"
          >
            <strong>{copy(item.id, language)}</strong>
            <span>{copyFormat("stay_pace_days", language, { days: item.days })}</span>
            <small>
              {copyFormat("stay_pace_capacity", language, {
                hours: Math.round(item.daily_capacity_minutes / 6) / 10,
              })}
            </small>
          </button>
        ))}
      </div>

      <h3 className="money-eyebrow">{copy("pick_month", language)}</h3>
      {/* Banded from recorded weather and published holidays, never from recall — a
          model will happily invent a season for a city it has never checked, which is
          the failure `WF-046` measured. Every month stays pressable: this reports what
          the numbers say and the owner may be travelling on dates a school decides. */}
      {guide.data ? (
        <p className="setup-hint">
          {copyFormat("month_guide_help", language, { years: `${guide.data.observed_from.slice(0, 4)}–${guide.data.observed_to.slice(0, 4)}` })}
        </p>
      ) : (
        <div className="optimize-actions">
          <button
            disabled={guide.isFetching}
            onClick={() => guide.refetch()}
            type="button"
          >
            {guide.isFetching ? copy("loading", language) : copy("load_month_guide", language)}
          </button>
          <span className="setup-hint">{copy("month_guide_free", language)}</span>
        </div>
      )}
      <div className="stay-months" role="group" aria-label={copy("pick_month", language)}>
        {Array.from({ length: MONTH_COUNT }, (_, index) => index + 1).map((value) => {
          const rated = guide.data?.months.find((item) => item.month === value);
          return (
            <button
              aria-pressed={value === month}
              className={`stay-month${value === month ? " active" : ""}${rated ? ` band-${rated.band}` : ""}`}
              key={value}
              onClick={() => { setMonth(value); setSaved(false); setWindowChosen(null); }}
              type="button"
            >
              {copy(`month_${value}`, language)}
              {rated ? <small>{copy(`band_${rated.band}`, language)}</small> : null}
            </button>
          );
        })}
      </div>
      {chosenMonth ? (
        <div className={`month-verdict band-${chosenMonth.band}`}>
          <p className="month-verdict-head">
            <strong>{copy(`month_${chosenMonth.month}`, language)}</strong>
            <span>{copy(`band_${chosenMonth.band}`, language)}</span>
          </p>
          {chosenMonth.pros.length ? (
            <div className="month-column">
              <h4>{copy("month_pros", language)}</h4>
              <ul>
                {chosenMonth.pros.map((item) => (
                  <li key={item.code}>{copyFormat(item.code, language, item.args)}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {chosenMonth.cons.length ? (
            <div className="month-column">
              <h4>{copy("month_cons", language)}</h4>
              <ul>
                {chosenMonth.cons.map((item) => (
                  <li key={item.code}>{copyFormat(item.code, language, item.args)}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {chosenMonth.advice.length ? (
            <div className="month-column">
              <h4>{copy("month_advice", language)}</h4>
              <ul>
                {chosenMonth.advice.map((item) => (
                  <li key={item.code}>{copyFormat(item.code, language, item.args)}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
      {guide.data ? (
        <p className="setup-hint">
          {copyFormat("month_guide_source", language, {
            from: guide.data.observed_from,
            to: guide.data.observed_to,
            year: guide.data.holiday_year,
            source: guide.data.holiday_source ?? "—",
          })}
          {guide.data.holiday_source ? null : (
            <>
              {" "}
              {copyFormat("month_guide_no_holidays", language, { country: guide.data.country })}
            </>
          )}
        </p>
      ) : null}
      <p className="setup-hint">{copy("pick_month_help", language)}</p>

      {/* The month says roughly when; this says which days. Same holiday data, no
          further request — the quietest run that fits, weekends counted at half a
          holiday because both fill the same trains. */}
      {chosenMonth?.best_window ? (
        <div className="stay-window">
          <h4>{copy("best_dates", language)}</h4>
          <p className="stay-window-dates">
            <strong>{chosenMonth.best_window.start}</strong> →{" "}
            <strong>{chosenMonth.best_window.end}</strong>
          </p>
          <ul>
            {chosenMonth.best_window.reasons.map((item) => (
              <li key={item.code}>{copyFormat(item.code, language, item.args)}</li>
            ))}
          </ul>
          <button
            className="stay-window-use"
            onClick={() => setWindowChosen(chosenMonth.best_window ?? null)}
            type="button"
          >
            {copy("use_best_dates", language)}
          </button>
        </div>
      ) : null}
      <p className="stay-dates">
        <strong>{start}</strong> → <strong>{end}</strong>
      </p>
      {save.error ? (
        <p className="field-error">
          ⚠ {save.error instanceof ApiError ? save.error.code : String(save.error)}
        </p>
      ) : null}
      {saved ? (
        <p className="money-note money-note-warn">
          <b aria-hidden="true">⚠</b>
          <span>{copy("provisional_dates_set", language)}</span>
        </p>
      ) : null}
      <div className="optimize-actions">
        <button
          className="setup-primary"
          disabled={save.isPending || stored.isPending}
          onClick={() => save.mutate()}
          type="button"
        >
          {copy("use_these_dates", language)}
        </button>
      </div>
    </section>
  );
}
