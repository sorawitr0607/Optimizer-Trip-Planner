/* eslint-disable react-refresh/only-export-components */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";

import {
  ApiError,
  rpc,
  type ExportDay,
  type ExportFallback,
  type ExportPlanItem,
  type ExportSnapshot,
  type ExportStop,
  type Frozen,
} from "../api/client";
import { copy, copyFrom, type Language } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";

const MAP_WIDTH = 420;
const MAP_HEIGHT = 120;
const MAP_PAD = 14;

interface CoordinatePoint {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
  status: string;
}

export interface PlottedPoint extends CoordinatePoint {
  x: number;
  y: number;
}

/** Preserve relative distance on both axes instead of stretching a bounding box to fit. */
export function plotCoordinates(points: CoordinatePoint[]): PlottedPoint[] {
  if (!points.length) return [];
  const latitude = points.reduce((total, point) => total + point.latitude, 0) / points.length;
  const longitudeScale = Math.cos((latitude * Math.PI) / 180);
  const raw = points.map((point) => ({
    ...point,
    rawX: point.longitude * longitudeScale,
    rawY: -point.latitude,
  }));
  const xs = raw.map((point) => point.rawX);
  const ys = raw.map((point) => point.rawY);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = maxX - minX;
  const spanY = maxY - minY;
  const availableWidth = MAP_WIDTH - MAP_PAD * 2;
  const availableHeight = MAP_HEIGHT - MAP_PAD * 2;
  const scale = Math.min(
    spanX ? availableWidth / spanX : Number.POSITIVE_INFINITY,
    spanY ? availableHeight / spanY : Number.POSITIVE_INFINITY,
  );
  const finiteScale = Number.isFinite(scale) ? scale : 1;
  const usedWidth = spanX * finiteScale;
  const usedHeight = spanY * finiteScale;
  return raw.map(({ rawX, rawY, ...point }) => ({
    ...point,
    x: MAP_PAD + (availableWidth - usedWidth) / 2 + (rawX - minX) * finiteScale,
    y: MAP_PAD + (availableHeight - usedHeight) / 2 + (rawY - minY) * finiteScale,
  }));
}

function halfDay(start: string): "morning" | "afternoon" {
  return start < "12:00" ? "morning" : "afternoon";
}

function stateText(status: string, language: Language): string {
  return copy(`state_${status}`, language);
}

function codeText(code: string | null | undefined, language: Language): string {
  return copyFrom("OPTIMIZER_CODE_TEXT", code || "unknown", language);
}

function PlanRow({ item, language }: { item: ExportPlanItem; language: Language }) {
  const clock = `${item.start}–${item.end}`;
  const length = `${item.duration_minutes} ${copy("minutes", language)}`;
  if (item.type === "buffer") {
    return (
      <article className="plan-row buffer">
        <time>{clock}<small>{length}</small></time>
        <div><span className="plan-row-kind">{copy("buffer_minutes", language)}</span><p>{codeText(item.reason, language)}</p></div>
      </article>
    );
  }

  let title = item.display_name ?? item.type;
  let kind = copy(`type_${item.type}`, language);
  let meta = stateText(item.status, language);
  let details: React.ReactNode;
  if (item.type === "visit") {
    title = `${copy("stop", language)} ${item.stop_number} · ${item.display_name}`;
    kind = copy("stop", language);
    meta += item.local_name ? ` · ${item.local_name}` : "";
    details = (
      <ul>
        <li>{copy("choice", language)}: {copy(item.priority ?? "maybe", language)}</li>
        {item.address ? <li>{item.address}</li> : null}
        {!item.opening_verified ? <li>{copy("opening_unverified", language)}</li> : null}
      </ul>
    );
  } else if (item.type === "travel") {
    title = `${item.origin_name ?? "?"} → ${item.destination_name ?? "?"}`;
    kind = copy("travel_minutes", language);
    meta += ` · ${copy("travel_mode", language)} ${item.mode ?? "?"} · ${copy("walk_portion", language)} ${item.walking_minutes ?? 0} ${copy("minutes", language)}`;
    details = (
      <ul>
        <li>{copy(item.sightseeing_walk ? "sightseeing_walk" : "plain_transfer", language)}</li>
        {item.distance_m != null ? <li>{copy("distance", language)}: {item.distance_m} m</li> : null}
        {item.transfers != null ? <li>{copy("transfers", language)}: {item.transfers}</li> : null}
        {item.boarding_buffer_minutes ? <li>{copy("boarding_buffer", language)}: {item.boarding_buffer_minutes} {copy("minutes", language)}</li> : null}
      </ul>
    );
  } else {
    details = (
      <ul>
        {item.from_name || item.to_name ? <li>{item.from_name ?? "?"} → {item.to_name ?? "?"}</li> : null}
        {item.mode ? <li>{copy("travel_mode", language)}: {item.mode}</li> : null}
        {item.notes ? <li>{item.notes}</li> : null}
        <li>{copy("confirmation_needed", language)}</li>
      </ul>
    );
  }

  return (
    // derives-from: A2 day timeline, with the three operational variants the accepted prototype added.
    <article className={`plan-row ${item.type}`}>
      <time>{clock}<small>{length}</small></time>
      <div className="plan-row-body">
        <span className="plan-row-kind">{kind}</span>
        <h3>{title}</h3>
        <p>{meta}</p>
        <details><summary>{copy("row_details", language)}</summary>{details}</details>
      </div>
    </article>
  );
}

function FallbackRow({ fallback, language }: { fallback: ExportFallback; language: Language }) {
  return (
    <aside className="plan-fallback">
      <strong>{copy("fallback", language)}</strong>
      <span>{copy("fallback_trigger", language)}: {codeText(fallback.trigger, language)}</span>
      <span>{fallback.primary_name} → {fallback.replacement_name}{fallback.replacement_start ? ` · ${fallback.replacement_start}` : ""}</span>
      {fallback.displaced_consequence ? <span>{copy("consequence", language)}: {codeText(fallback.displaced_consequence, language)}</span> : null}
    </aside>
  );
}

export function CoordinateMap({
  anchor,
  stops,
  accommodationStatus,
  language,
}: {
  anchor: ExportSnapshot["accommodation"]["anchor"];
  stops: ExportStop[];
  accommodationStatus: string;
  language: Language;
}) {
  const rawPoints: CoordinatePoint[] = [];
  if (anchor?.latitude != null && anchor.longitude != null) {
    rawPoints.push({
      id: "hotel",
      label: "H",
      latitude: anchor.latitude,
      longitude: anchor.longitude,
      status: accommodationStatus === "booked" ? "confirmed" : "recheck",
    });
  }
  for (const stop of stops) {
    if (stop.latitude != null && stop.longitude != null) {
      rawPoints.push({
        id: stop.subject_id,
        label: String(stop.stop_number),
        latitude: stop.latitude,
        longitude: stop.longitude,
        status: stop.status,
      });
    }
  }
  const points = plotCoordinates(rawPoints);
  return (
    // derives-from: A1 numbered map; no tiles or network, and the list repeats every colour meaning.
    <section className="plan-map">
      <h2 className="money-eyebrow">{copy("tab_map", language)}</h2>
      {points.length ? (
        <svg aria-label={copy("tab_map", language)} role="img" viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}>
          {points.length > 1 ? <polyline className="plan-map-route" points={points.map((point) => `${point.x},${point.y}`).join(" ")} /> : null}
          {points.map((point) => (
            <g className={`plan-map-point ${point.status}`} key={point.id}>
              <circle cx={point.x} cy={point.y} r={point.label === "H" ? 9 : 8} />
              <text textAnchor="middle" x={point.x} y={point.y + 3}>{point.label}</text>
            </g>
          ))}
        </svg>
      ) : <p>{copy("map_no_coordinates", language)}</p>}
      <ul className="plan-stops">
        {anchor ? (
          <li><i className={`recheck ${accommodationStatus === "booked" ? "confirmed" : ""}`} /><b>H</b><span>{copy("hotel_anchor", language)} · {anchor.display_name}</span>{anchor.latitude != null && anchor.longitude != null ? <code>{anchor.latitude.toFixed(5)}, {anchor.longitude.toFixed(5)}</code> : null}</li>
        ) : null}
        {stops.map((stop) => (
          <li key={stop.subject_id}><i className={stop.status} /><b>{stop.stop_number}</b><span>{stop.display_name} · {stateText(stop.status, language)}</span>{stop.latitude != null && stop.longitude != null ? <code>{stop.latitude.toFixed(5)}, {stop.longitude.toFixed(5)}</code> : null}</li>
        ))}
      </ul>
    </section>
  );
}

export function ItineraryPage() {
  const { tripId = "" } = useParams();
  const { language } = useLanguage();
  const [chosenDate, setChosenDate] = useState("");
  const [tab, setTab] = useState<"timeline" | "map">("timeline");
  const snapshot = useQuery({
    queryKey: ["export_snapshot", tripId, language],
    queryFn: () => rpc<Frozen<ExportSnapshot>>("build_export_snapshot", { trip_id: tripId, language }),
  });

  if (snapshot.isPending) return <p>{copy("loading", language)}</p>;
  if (snapshot.isError) {
    const message = snapshot.error instanceof ApiError
      ? copyFrom("OPTIMIZER_CODE_TEXT", snapshot.error.code, language)
      : snapshot.error.message;
    return <p className="field-error">⚠ {message}</p>;
  }

  const plan = snapshot.data.data;
  const day = plan.days.find((item) => item.date === chosenDate) ?? plan.days[0];
  if (!day) return <p>{copy("no_schedule", language)}</p>;
  const totals = day.totals;
  const versionTag = plan.stamp.plan_version_id.replace(/^plan_/, "").slice(0, 12);
  const workbook = `/api/export/${encodeURIComponent(tripId)}/workbook.xlsx`;
  const calendar = `/api/export/${encodeURIComponent(tripId)}/checklist.ics`;

  return (
    <section className="stage-card itinerary-screen">
      <header className="money-head">
        <h1>{copy("use_title", language)}</h1>
        <p>{copy("use_help", language)}</p>
      </header>
      <div className="plan-stamp">
        <strong>{copy(plan.stamp.variant_id, language)} · {copy("readiness", language)}: {copy(plan.readiness.state, language)}</strong>
        <span>{copy("active_plan", language)} <code>{versionTag}</code> · {copy("exported_at", language)} {plan.stamp.exported_at.slice(0, 16)} · {plan.stamp.base_currency} · {plan.stamp.language.toUpperCase()}</span>
      </div>
      {!plan.stamp.is_active_plan ? <p className="money-note money-note-warn"><b aria-hidden="true">⚠</b>{copy("superseded_plan", language)}</p> : null}
      {plan.readiness.capability_gaps.length ? <details className="optimize-warnings"><summary>{copy("capability_gaps", language)}</summary><ul>{plan.readiness.capability_gaps.map((gap) => <li key={gap}>{codeText(gap, language)}</li>)}</ul></details> : null}

      <label className="optimize-variant">
        {copy("days", language)}
        <select value={day.date} onChange={(event) => setChosenDate(event.target.value)}>{plan.days.map((item) => <option key={item.date} value={item.date}>{item.date}</option>)}</select>
      </label>
      <div className="plan-day-summary">
        <strong>{day.start}–{day.end}</strong>
        <span>{copy("scheduled_visits", language)} {totals.scheduled_visits ?? 0} · {copy("visit_minutes", language)} {totals.visit_minutes ?? 0} {copy("minutes", language)} · {copy("travel_minutes", language)} {totals.travel_minutes ?? 0} {copy("minutes", language)}</span>
        <span>{copy("walking_minutes", language)} {totals.walking_minutes ?? 0} ({copy("rewarding_walking_minutes", language)} {totals.rewarding_walking_minutes ?? 0} · {copy("plain_walking_minutes", language)} {totals.plain_walking_minutes ?? 0}) · {copy("buffer_minutes", language)} {totals.buffer_minutes ?? 0}</span>
        <span>{copy("meal_minutes", language)} {totals.meal_minutes ?? 0} · {copy("preparation_minutes", language)} {totals.preparation_minutes ?? 0} · {copy("logistics_minutes", language)} {totals.logistics_minutes ?? 0}</span>
      </div>
      {day.highest_risk ? <p className="money-note money-note-warn"><b aria-hidden="true">⚠</b>{copy("highest_risk", language)}: {stateText(day.highest_risk.status, language)}</p> : null}

      <div className="plan-tabs" role="tablist">
        <button aria-selected={tab === "timeline"} onClick={() => setTab("timeline")} role="tab" type="button">{copy("timeline", language)}</button>
        <button aria-selected={tab === "map"} onClick={() => setTab("map")} role="tab" type="button">{copy("tab_map", language)}</button>
      </div>
      {tab === "timeline" ? <Timeline day={day} language={language} /> : (
        <CoordinateMap anchor={plan.accommodation.anchor} stops={day.stops} accommodationStatus={plan.accommodation.status} language={language} />
      )}

      <h2 className="money-eyebrow">{copy("downloads", language)}</h2>
      <div className="plan-downloads">
        <a className="primary-link" download href={workbook}>{copy("excel", language)}</a>
        {plan.checklist.items.length ? <a className="primary-link" download href={calendar}>{copy("calendar", language)}</a> : <span className="setup-hint">{copy("checklist_pending", language)}</span>}
      </div>

      {plan.unscheduled.length ? (
        <details className="plan-unscheduled" open={!day.items.length}>
          <summary>{copy("unscheduled_choices", language)} ({plan.unscheduled.length})</summary>
          <div className="money-table-scroll"><table className="money-table"><thead><tr><th>{copy("name", language)}</th><th>{copy("choice", language)}</th><th>{copy("reason", language)}</th><th>{copy("consequence", language)}</th></tr></thead><tbody>{plan.unscheduled.map((item) => <tr key={item.place_id}><td>{item.display_name}</td><td>{copy(item.priority, language)}</td><td>{codeText(item.reason, language)}</td><td>{codeText(item.consequence, language)}</td></tr>)}</tbody></table></div>
        </details>
      ) : null}
    </section>
  );
}

function Timeline({ day, language }: { day: ExportDay; language: Language }) {
  if (!day.items.length) return <p>{copy("no_schedule_day", language)}</p>;
  return (
    <div className="plan-timeline">
      {(["morning", "afternoon"] as const).map((part) => {
        const items = day.items.filter((item) => halfDay(item.start) === part);
        const fallbacks = day.fallbacks.filter((item) => item.half_day === part);
        if (!items.length && !fallbacks.length) return null;
        return <section key={part}><h2 className="money-eyebrow">{copy(part, language)}</h2>{items.map((item) => <PlanRow item={item} key={item.item_id} language={language} />)}{fallbacks.map((item) => <FallbackRow fallback={item} key={`${item.primary_id}-${item.fallback_id}`} language={language} />)}</section>;
      })}
      {day.fallbacks.filter((item) => item.half_day == null).map((item) => <FallbackRow fallback={item} key={`${item.primary_id}-${item.fallback_id}`} language={language} />)}
    </div>
  );
}
