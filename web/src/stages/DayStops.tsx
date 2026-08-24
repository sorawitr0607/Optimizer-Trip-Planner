import {
  Coffee,
  ListChecks,
  MapPin,
  Plane,
  Route,
  Utensils,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";
import { mapsLink } from "../shared/map";
import { osmPhotoUrl } from "../shared/photos";
import { durationText, type TimedItem } from "../shared/tripClock";

/**
 * One day's stops, as rows you can tick off and open.
 *
 * derives-from: A2 day timeline as .day-stop — the lineage `PlanRow` carried, which this
 * replaces. The accepted prototype's three operational variants survive as the type
 * badge; what is new is the tick and the tappable time, neither of which the prototype
 * had because the prototype was a printed poster.
 *
 * The table this replaces was built to be *audited* -- every column the exporter knows,
 * on every row. Standing on a corner the question is narrower: which one is this, is it
 * done, and what did I need to remember about it. So the row carries the four things
 * that answer that and hides the rest behind a chevron, and every row can be ticked.
 *
 * Ticks are per-browser, in `localStorage`. There is no server field for "I have been
 * here": the plan records what was scheduled, not what happened, and inventing one would
 * mean a write path and a migration for something only the person walking around needs.
 * The cost is that ticks do not follow you to another device, which is the same trade the
 * trip's own token already makes.
 */

/**
 * One icon per row kind, in the left gutter.
 *
 * The kind was a text badge, which reads only if you read it -- and a day is scanned, not
 * read. An icon in a fixed gutter lets "where is lunch" be answered without parsing six
 * rows of prose. The badge stays beside the name: the icon is the fast path, not the only
 * one, which is `WF-034`'s rule that a drawing is never the sole carrier.
 */
const KIND_ICON = {
  visit: MapPin,
  travel: Route,
  meal: Utensils,
  preparation: ListChecks,
  logistics: Plane,
  buffer: Coffee,
} as const;

export interface DayStopsProps {
  items: TimedItem[];
  language: Language;
  moment: Date;
  pinned: Date | null;
  onPin: (moment: Date) => void;
  isDone: (key: string) => boolean;
  onToggle: (key: string, done: boolean) => void;
  nameOf: (item: TimedItem) => string;
  /** Coordinates by `subject_id`, from the day's stops. A visit without one gets no
   *  maps link rather than a name search, which lands on the wrong Din Tai Fung. */
  coordsOf: (subjectId: string) => { latitude: number; longitude: number } | null;
  /** Empty means the day itself is empty; a search with no hits says so differently. */
  emptyText: string;
}

export function DayStops({
  items,
  language,
  moment,
  pinned,
  onPin,
  isDone,
  onToggle,
  nameOf,
  coordsOf,
  emptyText,
}: DayStopsProps) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null);
  const lightboxDialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const node = lightboxDialog.current;
    if (!node) return;
    if (lightbox && !node.open) node.showModal();
    if (!lightbox && node.open) node.close();
  }, [lightbox]);

  if (!items.length) return <p className="day-stops-empty">{emptyText}</p>;

  return (
    <>
      <ol className="day-stops">
        {items.map((item) => {
          const name = nameOf(item);
          const done = isDone(item.key);
          const isNow = moment >= item.startAt && moment < item.endAt;
          const isPinned = pinned !== null && +pinned === +item.startAt;
          const photo = osmPhotoUrl(item.photo_reference);
          const details = [
            item.address ? ["stop_address", item.address] : null,
            item.notes ? ["stop_notes", item.notes] : null,
            item.origin_name && item.destination_name
              ? ["stop_route", `${item.origin_name} → ${item.destination_name}`]
              : null,
            item.mode ? ["travel_mode", item.mode] : null,
            item.walking_minutes
              ? ["walk_portion", `${item.walking_minutes} ${copy("minutes", language)}`]
              : null,
            item.distance_m != null ? ["distance", `${item.distance_m} m`] : null,
            item.transfers != null ? ["transfers", String(item.transfers)] : null,
            item.boarding_buffer_minutes
              ? ["boarding_buffer", `${item.boarding_buffer_minutes} ${copy("minutes", language)}`]
              : null,
            item.reason ? ["reason", copyFrom("OPTIMIZER_CODE_TEXT", item.reason, language)] : null,
          ].filter(Boolean) as [string, string][];
          const expanded = Boolean(open[item.key]);

          return (
            <li
              className={
                "day-stop"
                + (done ? " done" : "")
                + (moment >= item.endAt ? " past" : "")
                + (isNow ? " live" : "")
                + (isPinned ? " pinned" : "")
                + (expanded ? " open" : "")
              }
              key={item.key}
            >
              <div className="day-stop-head">
                {(() => {
                  const Icon = KIND_ICON[item.type] ?? MapPin;
                  return (
                    <span aria-hidden="true" className={`day-stop-kind ${item.type}`}>
                      <Icon size={13} />
                    </span>
                  );
                })()}
                {/* The box is 16px and a finger is 44, so the label carries the target. */}
                <label className="day-stop-tick">
                  <input
                    aria-label={copyFormat("mark_stop_done", language, { name })}
                    checked={done}
                    onChange={(event) => onToggle(item.key, event.target.checked)}
                    type="checkbox"
                  />
                </label>
                {/* Tapping the time is how you look at another moment. It is a button
                    because it does something, and it is the time because that is the
                    thing you are pointing at when you wonder what the plan said then. */}
                <button
                  aria-label={copyFormat("pin_to_moment", language, {
                    time: item.start,
                    date: item.date,
                  })}
                  className="day-stop-when"
                  onClick={() => onPin(item.startAt)}
                  type="button"
                >
                  {item.start}
                </button>
                <button
                  aria-expanded={expanded}
                  className="day-stop-open"
                  disabled={!details.length && !photo}
                  onClick={() => setOpen((current) => ({ ...current, [item.key]: !expanded }))}
                  type="button"
                >
                  <span className="day-stop-body">
                    <span className="day-stop-name">{name}</span>
                    <span className="day-stop-meta">
                      <span className={`plan-row-kind ${item.type}`}>
                        {copy(`type_${item.type}`, language)}
                      </span>
                      <span className="day-stop-dur">
                        {durationText(item.startAt, item.endAt, language)}
                        {!item.end ? (
                          <abbr title={copy("inferred_end", language)}> *</abbr>
                        ) : null}
                      </span>
                      {item.opening_verified === false ? (
                        <span className="day-stop-warn">{copy("opening_unverified", language)}</span>
                      ) : null}
                      {/* The same number the deck showed when this place was chosen, so
                          the two screens cannot disagree about how well it fits. Only
                          where there is one: meals, buffers and logistics carry 0. */}
                      {item.score ? (
                        <span className="day-stop-match">
                          {copyFormat("match_for_group", language, {
                            percent: Math.round(item.score),
                          })}
                        </span>
                      ) : null}
                    </span>
                  </span>
                  {photo ? (
                    <img alt="" className="day-stop-thumb" loading="lazy" src={photo} />
                  ) : null}
                  {details.length || photo ? <span className="day-stop-chev">›</span> : null}
                </button>
              </div>

              {expanded ? (
                <div className="day-stop-detail">
                  {details.map(([label, value]) => (
                    <p className="day-stop-line" key={label}>
                      <span className="day-stop-k">{copy(label, language)}</span>
                      <span>{value}</span>
                    </p>
                  ))}
                  {photo ? (
                    <button
                      className="day-stop-photo"
                      onClick={() =>
                        setLightbox({
                          src: photo,
                          alt: copyFormat("stop_photo", language, { name }),
                        })
                      }
                      type="button"
                    >
                      <img alt={copyFormat("stop_photo", language, { name })} src={photo} />
                    </button>
                  ) : null}
                  {(() => {
                    const point = coordsOf(item.subject_id);
                    if (!point) return null;
                    return (
                      <a
                        className="primary-link"
                        href={mapsLink(point.latitude, point.longitude)}
                        rel="noopener"
                        target="_blank"
                      >
                        {copy("open_in_maps", language)} ↗
                      </a>
                    );
                  })()}
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>

      {/* Native modal behavior supplies Escape, focus containment and an inert page. */}
      <dialog
        className="day-stop-lightbox"
        onCancel={(event) => {
          event.preventDefault();
          setLightbox(null);
        }}
        onClick={(event) => {
          if (event.target === event.currentTarget) setLightbox(null);
        }}
        onClose={() => {
          if (lightbox) setLightbox(null);
        }}
        ref={lightboxDialog}
      >
        {lightbox ? (
          <>
          <img alt={lightbox.alt} src={lightbox.src} />
          <button onClick={() => setLightbox(null)} type="button">
            {copy("close_photo", language)}
          </button>
          </>
        ) : null}
      </dialog>
    </>
  );
}
