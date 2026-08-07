import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, rpc, type PlanProposal, type SetupDraft } from "../api/client";
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

  const stored = useQuery({
    queryKey: ["setup", tripId],
    queryFn: () => rpc<SetupDraft | null>("get_setup", { trip_id: tripId }),
  });

  const chosen = options.find((item) => item.id === pace) ?? options[0];
  const start = firstOfMonth(month, today);
  const end = chosen ? addDays(start, Math.max(chosen.days - 1, 0)) : start;

  const save = useMutation({
    mutationFn: () =>
      rpc<SetupDraft>("save_setup", {
        trip_id: tripId,
        ...wholeDraftWithDates(stored.data ?? null, start, end),
      }),
    onSuccess: async () => {
      setSaved(true);
      await queryClient.invalidateQueries({ queryKey: ["setup", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["journey", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["discovery", tripId] });
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
            onClick={() => { setPace(item.id); setSaved(false); }}
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
      <div className="stay-months" role="group" aria-label={copy("pick_month", language)}>
        {Array.from({ length: MONTH_COUNT }, (_, index) => index + 1).map((value) => (
          <button
            aria-pressed={value === month}
            className={`stay-month${value === month ? " active" : ""}`}
            key={value}
            onClick={() => { setMonth(value); setSaved(false); }}
            type="button"
          >
            {copy(`month_${value}`, language)}
          </button>
        ))}
      </div>
      <p className="setup-hint">{copy("pick_month_help", language)}</p>

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
