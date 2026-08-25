import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarRange } from "lucide-react";
import { useMemo, useState } from "react";

import {
  ApiError,
  rpc,
  type MonthGuide,
  type PlanProposal,
  type SetupDraft,
} from "../api/client";
import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";
import { addDays, daysInMonth, spanDays } from "../shared/dates";
import { PLAN_STAGES } from "../shared/buildStages";
import { Thinking } from "../shared/Thinking";
import { BuildStages } from "./BuildStages";

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
    // Carried explicitly, because this function's own docstring is the reason: a field
    // omitted here is a field `save_setup` resets to its default. Adding one to the draft
    // without adding it to this list silently erases the owner's answer the moment they
    // pick dates from the stay planner.
    active_start: basics.active_start ?? null,
    active_end: basics.active_end ?? null,
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
  /** The owner is typing their own range rather than taking one of the offered ones. */
  const [custom, setCustom] = useState(false);
  /** How many of the three calls below have returned. Advanced on each `await`,
   *  never on a timer — see `PLAN_STAGES` and the rule in `CLAUDE.md`. */
  const [built, setBuilt] = useState(0);

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
    enabled: Boolean(tripId),
    staleTime: Infinity,
  });

  const chosenMonth = guide.data?.months.find((item) => item.month === month);
  const defaultStart = firstOfMonth(month, today);
  const defaultSpan = chosen ? Math.max(chosen.days - 1, 0) : 0;
  
  const dateOptions = useMemo(() => {
    const year = month <= today.getMonth() + 1 ? today.getFullYear() + 1 : today.getFullYear();
    const mm = String(month).padStart(2, "0");
    const optionsList: { key: string; label: string; start: string; end: string; desc?: string }[] = [];
    
    if (chosenMonth?.best_window) {
      optionsList.push({
        key: "best_window",
        label: copy("best_dates", language),
        start: chosenMonth.best_window.start,
        end: chosenMonth.best_window.end,
        desc: chosenMonth.best_window.reasons.map((r) => copyFormat(r.code, language, r.args)).join(" · "),
      });
    }
    
    const earlyStart = `${year}-${mm}-01`;
    optionsList.push({
      key: "early",
      label: copy("dates_early_month", language),
      start: earlyStart,
      end: addDays(earlyStart, defaultSpan),
    });
    
    const midStart = `${year}-${mm}-15`;
    optionsList.push({
      key: "mid",
      label: copy("dates_mid_month", language),
      start: midStart,
      end: addDays(midStart, defaultSpan),
    });

    // Late month, placed so the trip *ends* on the last day rather than starting on a
    // fixed date and running past it — a 9-day pace from the 22nd would have spilled
    // into the next month and quietly stopped being "late April".
    const last = daysInMonth(year, month);
    const lateDay = Math.max(1, last - defaultSpan);
    if (lateDay > 15) {
      const lateStart = `${year}-${mm}-${String(lateDay).padStart(2, "0")}`;
      optionsList.push({
        key: "late",
        label: copy("dates_late_month", language),
        start: lateStart,
        end: addDays(lateStart, defaultSpan),
      });
    }

    // The first Saturday, because a trip that starts on one costs fewer days off and
    // that is a real constraint the app otherwise ignores. Offered only when it does
    // not duplicate a range already listed.
    const firstOfM = new Date(Date.UTC(year, month - 1, 1));
    const toSaturday = (6 - firstOfM.getUTCDay() + 7) % 7;
    const satDay = 1 + toSaturday;
    if (satDay + defaultSpan <= last) {
      const satStart = `${year}-${mm}-${String(satDay).padStart(2, "0")}`;
      if (!optionsList.some((item) => item.start === satStart)) {
        optionsList.push({
          key: "weekend",
          label: copy("dates_weekend", language),
          start: satStart,
          end: addDays(satStart, defaultSpan),
        });
      }
    }

    return optionsList;
  }, [chosenMonth, month, today, defaultSpan, language]);

  const start = windowChosen?.start ?? defaultStart;
  const end = windowChosen?.end ?? (chosen ? addDays(start, defaultSpan) : start);

  /**
   * A custom range may not be longer than the pace the owner picked above.
   *
   * The pace *is* the number of days the chosen places want — `chosen.days` — so a
   * longer range is not a preference, it is a plan the optimizer was never asked to
   * build: the extra days arrive empty and read as the app having run out of ideas.
   * The cap is therefore the pace, and the message names the pace rather than quoting
   * a bare number the owner would have to go back up the screen to identify.
   *
   * Shorter is allowed and deliberately so — someone may want two of the three days
   * the places want, and the optimizer drops what does not fit rather than failing.
   */
  const allowedDays = chosen?.days ?? 0;
  const usedDays = spanDays(start, end);
  const endsBeforeStart = usedDays <= 0;
  const spanTooLong = allowedDays > 0 && usedDays > allowedDays;
  const rangeInvalid = endsBeforeStart || spanTooLong;
  /** The latest end the pace allows, so the picker refuses before the message has to. */
  const latestEnd = allowedDays > 0 ? addDays(start, allowedDays - 1) : undefined;

  const save = useMutation({
    mutationFn: async () => {
      setBuilt(0);
      const draft = await rpc<SetupDraft>("save_setup", {
        trip_id: tripId,
        ...wholeDraftWithDates(stored.data ?? null, start, end),
      });
      setBuilt(1);
      await rpc("discover_places", { trip_id: tripId, force_refresh: false });
      setBuilt(2);
      // And build a plan against them, which is the only thing that takes this screen
      // off the screen. Writing the dates alone left the stored preview as the dateless
      // `stay_recommendation` it already was, so `/optimize` re-rendered this very date
      // picker — pressing the button appeared to do nothing, and a manual reload did not
      // help either, because the preview it re-read was the same stale one.
      await rpc("generate_plan_preview", { trip_id: tripId });
      setBuilt(3);
      return draft;
    },
    onSuccess: async () => {
      setSaved(true);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["setup", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["journey", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["discovery", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["ranking", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["plan_preview", tripId] }),
      ]);
    },
  });

  if (!options.length) return null;

  return (
    // derives-from: element 36 .currency-info-box as .stay-planner
    <section className="stay-planner">
      {/* The whole picker goes while the build runs, at the owner's asking. Pace, month
          grid, month guide and the chosen window are all inputs to a decision that has
          already been taken and sent — leaving them up during the ~1 minute wait invites
          changing an answer nothing is reading any more, and buries the progress line
          under a screen of controls. `hidden` rather than unmounting, so the picker comes
          back exactly as it was if the build fails. */}
      <div hidden={save.isPending}>
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
      {guide.data ? (
        <p className="setup-hint">
          {copyFormat("month_guide_help", language, { years: `${guide.data.observed_from.slice(0, 4)}–${guide.data.observed_to.slice(0, 4)}` })}
        </p>
      ) : guide.isFetching ? (
        <p className="setup-hint">{copy("loading", language)}</p>
      ) : null}
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

      <div className="stay-options-group">
        <h4 className="money-eyebrow">{copy("recommend_dates", language)}</h4>
        <div className="stay-window-options">
          {dateOptions.map((opt) => {
            const isSelected = start === opt.start && end === opt.end;
            return (
              <button
                key={opt.key}
                type="button"
                className={`stay-window-card${isSelected ? " active" : ""}`}
                onClick={() => {
                  setWindowChosen({ start: opt.start, end: opt.end });
                  setSaved(false);
                }}
              >
                <div className="stay-window-card-head">
                  <strong>{opt.label}</strong>
                  <span>{opt.start} → {opt.end}</span>
                </div>
                {opt.desc ? <small className="setup-hint">{opt.desc}</small> : null}
              </button>
            );
          })}
          {/* Pick your own. A card in the same row rather than a link somewhere else,
              because it is the fifth answer to the same question. */}
          <button
            aria-expanded={custom}
            className={`stay-window-card${custom ? " active" : ""}`}
            onClick={() => {
              setCustom((open) => !open);
              setSaved(false);
            }}
            type="button"
          >
            <div className="stay-window-card-head">
              <strong>
                <CalendarRange aria-hidden="true" size={14} /> {copy("dates_custom", language)}
              </strong>
            </div>
          </button>
        </div>
        {custom ? (
          <div className="stay-custom">
            <label>
              {copy("dates_custom_start", language)}
              <input
                onChange={(event) => {
                  const next = event.target.value;
                  if (!next) return;
                  // Moving the start drags the end with it when the end would otherwise
                  // fall behind, so the pair is never briefly invalid while typing.
                  const keep = spanDays(next, end);
                  setWindowChosen({
                    start: next,
                    end: keep > 0 && keep <= allowedDays ? end : addDays(next, defaultSpan),
                  });
                  setSaved(false);
                }}
                type="date"
                value={start}
              />
            </label>
            <label>
              {copy("dates_custom_end", language)}
              <input
                aria-describedby="stay-span-note"
                aria-invalid={rangeInvalid || undefined}
                // The browser refuses the over-long range before the message has to
                // explain it; the message stays for a typed date, which `max` cannot stop.
                max={latestEnd}
                min={start}
                onChange={(event) => {
                  if (!event.target.value) return;
                  setWindowChosen({ start, end: event.target.value });
                  setSaved(false);
                }}
                type="date"
                value={end}
              />
            </label>
            <p
              className={rangeInvalid ? "setup-field-error stay-span-note" : "setup-hint stay-span-note"}
              id="stay-span-note"
              role={rangeInvalid ? "alert" : undefined}
            >
              {endsBeforeStart
                ? `⚠ ${copy("dates_end_before", language)}`
                : spanTooLong
                  ? `⚠ ${copyFormat("dates_span_over", language, {
                      days: usedDays,
                      // The pace id *is* its copy key — see the label above, which is
                      // `copy(item.id, …)`. A `pace_` prefix would have rendered the
                      // visible `⚠ pace_relaxed` that unknown codes are designed to show.
                      pace: chosen ? copy(chosen.id, language) : "",
                      allowed: allowedDays,
                    })}`
                  : copyFormat("dates_span_ok", language, { days: usedDays, allowed: allowedDays })}
            </p>
          </div>
        ) : null}
      </div>

      <p className="stay-dates">
        <strong>{start}</strong> → <strong>{end}</strong>
      </p>
      </div>
      {save.error ? (
        <p className="field-error">
          ⚠{" "}
          {save.error instanceof ApiError
            ? copyFrom("OPTIMIZER_CODE_TEXT", save.error.code, language)
            : String(save.error)}
        </p>
      ) : null}
      {saved ? (
        <p className="money-note money-note-warn">
          <b aria-hidden="true">⚠</b>
          <span>{copy("provisional_dates_set", language)}</span>
        </p>
      ) : null}
      {/* The button now builds a plan as well as writing the dates, which is about a
          minute of work — the same silence that had `/optimize` reported as broken. */}
      {save.isPending ? (
        <div className="optimize-working" aria-busy="true">
          {/* The same checklist `/optimize` shows, on the same terms: a stage is
              ticked when its call returns. This press does three things and takes
              about a minute, and it used to report that with one rotating line —
              which cannot say which of the three it is on, so a slow discovery and
              a slow proposal looked identical, and both looked like a hang.
              `Thinking` stays *inside* the last stage, where the long
              `generate_plan_preview` genuinely has no milestones and an elapsed
              counter is the honest thing to show. */}
          <BuildStages language={language} reached={built} stages={PLAN_STAGES}>
            <Thinking
              expectSeconds={90}
              language={language}
              lines={["think_windows", "think_routes", "think_packing", "think_variants", "think_checking", "think_almost"]}
            />
          </BuildStages>
          <p className="setup-hint">{copy("optimizing_note", language)}</p>
        </div>
      ) : null}
      <div className="optimize-actions">
        <button
          className="setup-primary"
          disabled={save.isPending || stored.isPending || rangeInvalid}
          onClick={() => save.mutate()}
          type="button"
        >
          {copy("use_these_dates", language)}
        </button>
        {/* The press does three things and takes about a minute, and the label named only
            the first — so it read as saving a date and then appeared to hang. Naming all
            three is what makes the wait legible as work rather than as a fault. */}
        <p className="setup-hint">{copy("use_these_dates_hint", language)}</p>
      </div>
    </section>
  );
}
