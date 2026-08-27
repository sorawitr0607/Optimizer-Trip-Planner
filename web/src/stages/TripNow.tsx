import { useEffect, useState } from "react";

import { copy, copyFormat, type Language } from "../i18n/copy";
import {
  durationText,
  gapText,
  indexAt,
  liveItem,
  nextItem,
  progressPercent,
  type TimedItem,
} from "../shared/tripClock";

/**
 * What is happening now, what is next, and one control for looking at another moment.
 *
 * derives-from: A2 day timeline as .trip-now — no donor or prototype counterpart exists,
 * because a poster has no "now". It is the current row of the same day timeline, lifted
 * to the top of the screen and given the clock.
 *
 * The itinerary is read while standing in the city, where the question is not "show me
 * the plan" but "where am I supposed to be". That answer was five scrolls down a table of
 * every day, so it moves to the top and follows the clock.
 *
 * **There is no scrubber.** A slider was the obvious control and is the wrong one: a trip
 * is thousands of minutes wide, so a phone-width slider gives roughly twenty minutes per
 * pixel and cannot land on anything, and it puts looking around behind a mode you have to
 * enter first. The timeline is the control instead -- tapping any stop's time pins the
 * page to that moment -- and this card carries only `‹ ›` to step stop by stop and one
 * tap back to live. The trade is that you can only stop where the plan has a stop, which
 * is every moment it actually describes.
 */

/** Ticks the clock so "now" stays true on a page left open, which is the normal case. */
function useMinuteClock(active: boolean): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    if (!active) return;
    // Aligned to the next minute boundary rather than a bare 60s interval, so the
    // displayed minute changes when the minute does.
    let timer = 0;
    const schedule = () => {
      const delay = 60_000 - (Date.now() % 60_000);
      timer = window.setTimeout(() => {
        setNow(new Date());
        schedule();
      }, delay);
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, [active]);
  return now;
}

/** `YYYY-MM-DD · HH:MM` from local parts.
 *
 *  Not `toISOString()`: that is UTC, so local midnight on the 11th is 17:00 on the 10th
 *  in UTC+7 and the pinned moment printed the day before itself. `StayPlanner` carries a
 *  comment about the same trap on its date arithmetic. */
function localStamp(moment: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())}`
    + ` · ${pad(moment.getHours())}:${pad(moment.getMinutes())}`
  );
}

export interface TripNowProps {
  items: TimedItem[];
  language: Language;
  /** null follows the real clock; a Date shows the plan as it stood at that moment. */
  pinned: Date | null;
  onPin: (moment: Date | null) => void;
  /** Which day is on screen, so the card can offer to jump to the live one. */
  currentDayDate: string;
  onSelectDay: (date: string) => void;
  dayLabelOf: (date: string) => string;
  /** A stop's own name, which the itinerary spells from the plan's names table. */
  nameOf: (item: TimedItem) => string;
  /** Exact coordinate handoff for a place stop; null for rows with nowhere to pin. */
  mapHrefOf?: (item: TimedItem) => string | null;
}

export function TripNow({
  items,
  language,
  pinned,
  onPin,
  currentDayDate,
  onSelectDay,
  dayLabelOf,
  nameOf,
  mapHrefOf,
}: TripNowProps) {
  // Only while live: a pinned moment must not move under the reader.
  const ticking = useMinuteClock(pinned === null);
  if (!items.length) return null;

  const moment = pinned ?? ticking;
  const live = liveItem(items, moment);
  const upcoming = nextItem(items, moment);
  const liveMapHref = live && mapHrefOf ? mapHrefOf(live) : null;
  const first = items[0];
  const last = items[items.length - 1];
  const before = moment < first.startAt;
  const after = moment > last.endAt;
  const isLive = pinned === null;

  const index = indexAt(items, moment);
  const stepTo = (target: number) => {
    const clamped = Math.min(items.length - 1, Math.max(0, target));
    onPin(items[clamped].startAt);
  };

  return (
    <section aria-atomic="true" aria-live="polite" className="trip-now">
      {before || after ? (
        <>
          <span className="trip-now-tag">
            {copy(after ? "trip_complete" : "trip_not_started", language)}
          </span>
          <strong className="trip-now-name">
            {after ? (
              nameOf(last)
            ) : (
              // "Departs in N days" counts down against the wall clock, so an unchanged
              // app photographs differently every day and the itinerary baselines needed
              // re-approving on a schedule -- a gate that fails without a code change
              // teaches everyone to ignore it. Frozen under capture only, exactly as the
              // export stamp and the paid ledger are; the real interface still counts.
              // The whole phrase rather than the number, because `copyFormat` returns one
              // interpolated string and splitting a sentence in two languages to freeze
              // three characters of it is worse than losing the line's width from the
              // diff -- everything around it is still compared.
              <span data-volatile="countdown">
                {copyFormat("trip_departs", language, {
                  gap: gapText(+first.startAt - +moment, language),
                })}
              </span>
            )}
          </strong>
        </>
      ) : live ? (
        <>
          <span className="trip-now-tag">{copy("now_tag", language)}</span>
          <span className="trip-now-time">
            {live.start}
            {live.end ? `–${live.end}` : ""} · {durationText(live.startAt, live.endAt, language)}
          </span>
          <strong className="trip-now-name">{nameOf(live)}</strong>
          {/* How far through the current stop you are, which is the one number a
              timetable cannot show you by being read. */}
          <div className="trip-now-bar">
            <i style={{ width: `${progressPercent(live, moment)}%` }} />
          </div>
          {liveMapHref ? (
            <a
              className="primary-link trip-now-map"
              href={liveMapHref}
              rel="noopener"
              target="_blank"
            >
              {copy("open_in_maps", language)} ↗
            </a>
          ) : null}
        </>
      ) : (
        <>
          <span className="trip-now-tag">{copy("gap_tag", language)}</span>
          <strong className="trip-now-name">{copy("nothing_scheduled", language)}</strong>
        </>
      )}

      {upcoming && !after ? (
        <p className="trip-now-next">
          <span className="trip-now-next-when">
            {copy("next_tag", language)} · {upcoming.start} ·{" "}
            {/* The second countdown on this card, and it drifts for the same reason the
                first one does — freezing only the departure line left the itinerary
                baselines still ageing daily, which the capture diff showed and the
                reasoning had not. Just the gap here: the tag and the clock time beside
                it are stable, so unlike the departure line there is nothing to gain by
                collapsing the whole phrase. */}
            <span data-volatile="countdown">
              {gapText(+upcoming.startAt - +moment, language)}
            </span>
          </span>
          <span className="trip-now-next-name">{nameOf(upcoming)}</span>
        </p>
      ) : null}

      {/* The live stop is often not on the day being read. Offering the jump is the
          difference between the card answering the question and merely stating it. */}
      {(() => {
        const target = live ?? upcoming;
        if (!target || target.dayDate === currentDayDate) return null;
        return (
          <button
            className="trip-now-jump"
            onClick={() => onSelectDay(target.dayDate)}
            type="button"
          >
            {copyFormat("jump_to_day", language, { day: dayLabelOf(target.dayDate) })}
          </button>
        );
      })()}

      <div className="trip-now-clock">
        <button
          aria-label={copy("clock_prev", language)}
          className="trip-now-step"
          disabled={index <= 0 && !isLive}
          onClick={() => stepTo(index - (isLive ? 0 : 1))}
          type="button"
        >
          ‹
        </button>
        <span className="trip-now-at">
          {isLive ? copy("clock_live", language) : localStamp(moment)}
        </span>
        <button
          aria-label={copy("clock_next", language)}
          className="trip-now-step"
          disabled={index >= items.length - 1}
          onClick={() => stepTo(index + 1)}
          type="button"
        >
          ›
        </button>
        {isLive ? null : (
          <button className="trip-now-golive" onClick={() => onPin(null)} type="button">
            {copy("clock_go_live", language)}
          </button>
        )}
      </div>
    </section>
  );
}
