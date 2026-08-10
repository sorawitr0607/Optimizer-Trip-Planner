/* eslint-disable react-refresh/only-export-components */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import {
  ApiError,
  rpc,
  type Basemap,
  type CountryOutline,
  type ExportDay,
  type ExportFallback,
  type ExportPlanItem,
  type ExportSnapshot,
  type ExportStop,
  type Frozen,
  type PlanDrift,
  type TripForecast,
} from "../api/client";
import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { mapsLink, type MapPlace } from "../shared/map";
import { PlaceMap } from "./PlaceMap";

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

/** Preserve relative distance on both axes instead of stretching a bounding box to fit.
 *
 *  Generic over whatever else a caller carries, because `/places` now plots the
 *  shortlist through the same projection and its points have a name and no status.
 *  Two projections would be two pictures of the same coordinates that could disagree. */
/** The transform `plotCoordinates` applies, and its inverse.
 *
 *  Exposed because `/places` can be zoomed, and knowing *which* piece of the world is
 *  on screen is what lets it ask for that window's buildings and nothing else. Derived
 *  from the same numbers rather than re-fitted, so the two directions cannot disagree. */
/**
 * Web Mercator, in radians, which is the projection the whole world's map tiles are cut
 * to.
 *
 * This was a flat `longitude x cos(latitude)` approximation until tiles arrived, and at
 * city scale the two are within a hair of each other — but a tile is a *square* in
 * Mercator and a trapezoid in anything else, so the approximation could not carry an
 * image without smearing it against the pins drawn on top. Everything here goes through
 * one transform, so changing it moved the streets, the buildings and the stops together
 * and none of them can disagree with the tiles or with each other.
 */
export function mercatorY(latitude: number): number {
  return Math.log(Math.tan(Math.PI / 4 + (latitude * Math.PI) / 360));
}

export function mercatorLatitude(y: number): number {
  return (Math.atan(Math.sinh(y)) * 180) / Math.PI;
}

export function projectionOf(
  points: { latitude: number; longitude: number }[],
  frame: { width: number; height: number } = { width: MAP_WIDTH, height: MAP_HEIGHT },
): {
  toXY: (latitude: number, longitude: number) => { x: number; y: number };
  toLatLon: (x: number, y: number) => { latitude: number; longitude: number };
} | null {
  if (!points.length) return null;
  const xs = points.map((point) => (point.longitude * Math.PI) / 180);
  const ys = points.map((point) => -mercatorY(point.latitude));
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const spanX = Math.max(...xs) - minX;
  const spanY = Math.max(...ys) - minY;
  const availableWidth = frame.width - MAP_PAD * 2;
  const availableHeight = frame.height - MAP_PAD * 2;
  const scale = Math.min(
    spanX ? availableWidth / spanX : Number.POSITIVE_INFINITY,
    spanY ? availableHeight / spanY : Number.POSITIVE_INFINITY,
  );
  const finiteScale = Number.isFinite(scale) ? scale : 1;
  const offsetX = MAP_PAD + (availableWidth - spanX * finiteScale) / 2;
  const offsetY = MAP_PAD + (availableHeight - spanY * finiteScale) / 2;
  return {
    toXY: (pointLatitude, pointLongitude) => ({
      x: offsetX + ((pointLongitude * Math.PI) / 180 - minX) * finiteScale,
      y: offsetY + (-mercatorY(pointLatitude) - minY) * finiteScale,
    }),
    toLatLon: (x, y) => ({
      longitude: (((x - offsetX) / finiteScale + minX) * 180) / Math.PI,
      latitude: mercatorLatitude(-((y - offsetY) / finiteScale + minY)),
    }),
  };
}

/**
 * The same projection, applied. One implementation of the maths with two directions:
 * these were two copies until footprints needed to be projected *through* the pins'
 * projection rather than joining the bounds it is computed from.
 */
export function plotCoordinates<T extends { latitude: number; longitude: number }>(
  points: T[],
  /** The frame to fit into. The itinerary's strip is wide and short; `/places` draws a
   *  whole city and needs height, or a roughly square town is squashed into a band and
   *  its pins pile up in the middle. */
  frame: { width: number; height: number } = { width: MAP_WIDTH, height: MAP_HEIGHT },
): (T & { x: number; y: number })[] {
  const projection = projectionOf(points, frame);
  if (!projection) return [];
  // The point is kept whole beside its projection rather than spread into it: spreading
  // and then omitting the two extras loses the generic's identity, so a caller carrying
  // its own fields got them back as `Omit<...>` instead of its own type.
  return points.map((point) => ({ ...point, ...projection.toXY(point.latitude, point.longitude) }));
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
  tripId,
  basemap = null,
  outline = null,
}: {
  anchor: ExportSnapshot["accommodation"]["anchor"];
  stops: ExportStop[];
  accommodationStatus: string;
  language: Language;
  /** Enables the tiles and the zoomed-in detail. Omit and this is still a map, just the
   *  drawn one. */
  tripId?: string;
  basemap?: Basemap | null;
  outline?: CountryOutline | null;
}) {
  // The same map `/places` draws, on the screen that is actually carried.
  //
  // This was a 420x120 strip of dots joined by straight lines, and its own comment said
  // "no tiles or network" — written when that was the policy for every map here. So the
  // screen used while *choosing* got streets, buildings and real tiles, and the screen
  // used while *standing on the corner* kept the diagram. One component draws both now,
  // which is also the only way they cannot disagree about where a place is.
  //
  // The stop list underneath stays exactly as it was: `WF-034`'s rule is that the
  // drawing is never the only carrier, and it holds the statuses and the coordinates a
  // map cannot spell out.
  const points: MapPlace[] = [];
  if (anchor?.latitude != null && anchor.longitude != null) {
    points.push({
      place_id: "hotel",
      label: "H",
      name: copy("hotel_anchor", language),
      latitude: anchor.latitude,
      longitude: anchor.longitude,
      status: accommodationStatus === "booked" ? "confirmed" : "recheck",
    });
  }
  for (const stop of stops) {
    if (stop.latitude != null && stop.longitude != null) {
      points.push({
        place_id: stop.subject_id,
        label: String(stop.stop_number),
        name: stop.display_name,
        latitude: stop.latitude,
        longitude: stop.longitude,
        status: stop.status,
      });
    }
  }
  return (
    // derives-from: A1 numbered map; the list below repeats every pin and every colour.
    <section className="plan-map">
      <h2 className="money-eyebrow">{copy("tab_map", language)}</h2>
      {points.length ? (
        <PlaceMap
          basemap={basemap}
          language={language}
          outline={outline}
          places={points}
          route
          title={copy("tab_map", language)}
          tripId={tripId}
          withKey={false}
        />
      ) : <p>{copy("map_no_coordinates", language)}</p>}
      <ul className="plan-stops">
        {anchor ? (
          <li>
            <i className={`recheck ${accommodationStatus === "booked" ? "confirmed" : ""}`} /><b>H</b>
            <span>{copy("hotel_anchor", language)} · {anchor.display_name}</span>
            {anchor.latitude != null && anchor.longitude != null ? (
              <a className="plan-stop-maps" href={mapsLink(anchor.latitude, anchor.longitude, anchor.display_name ?? "")}>
                {copy("open_in_maps", language)} ↗
              </a>
            ) : null}
          </li>
        ) : null}
        {stops.map((stop) => (
          <li key={stop.subject_id}>
            <i className={stop.status} /><b>{stop.stop_number}</b>
            <span>{stop.display_name} · {stateText(stop.status, language)}</span>
            {/* The coordinates stay: they are what the export prints and what a taxi
                driver can be shown when no phone will cooperate. */}
            {stop.latitude != null && stop.longitude != null ? (
              <>
                <a className="plan-stop-maps" href={mapsLink(stop.latitude, stop.longitude, stop.display_name)}>
                  {copy("open_in_maps", language)} ↗
                </a>
                <code>{stop.latitude.toFixed(5)}, {stop.longitude.toFixed(5)}</code>
              </>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ItineraryPage() {
  const { tripId = "" } = useParams();
  // What the map needs to still be a map with no network: the city's own roads and water
  // and the country's outline, both cached for a month or more. Tiles are the picture
  // when there is a network; these are the picture when there is not.
  const basemap = useQuery({
    queryKey: ["basemap", tripId],
    queryFn: () =>
      typeof document !== "undefined" && document.documentElement.dataset.capture
        ? rpc<Basemap | null>("get_basemap", { trip_id: tripId })
        : rpc<Basemap | null>("refresh_basemap", { trip_id: tripId }),
    enabled: Boolean(tripId),
    staleTime: Infinity,
    retry: false,
  });
  // The real weather for these dates, once they are near enough for anyone to know it.
  // Shown beside the day, never folded into the plan: a schedule that reshuffles itself
  // because a forecast twitched is worse than one that says what it knows.
  const forecast = useQuery({
    queryKey: ["trip_forecast", tripId],
    queryFn: () => rpc<TripForecast>("trip_forecast", { trip_id: tripId }),
    enabled: Boolean(tripId),
    retry: false,
  });
  const outline = useQuery({
    queryKey: ["country_outline", tripId],
    queryFn: () =>
      rpc<CountryOutline | null>(
        typeof document !== "undefined" && document.documentElement.dataset.capture
          ? "country_outline"
          : "refresh_country_outline",
        { trip_id: tripId },
      ),
    enabled: Boolean(tripId),
    staleTime: Infinity,
    retry: false,
  });
  const { language } = useLanguage();
  const [chosenDate, setChosenDate] = useState("");
  const [tab, setTab] = useState<"timeline" | "map">("timeline");
  const snapshot = useQuery({
    queryKey: ["export_snapshot", tripId, language],
    queryFn: () => rpc<Frozen<ExportSnapshot>>("build_export_snapshot", { trip_id: tripId, language }),
  });
  // `WF-045`. The stored plan cannot notice that its own evidence moved, so the screen
  // asks. Its own query rather than part of the snapshot: a plan that no longer holds
  // must still render, or the owner loses the itinerary they came to read.
  const drift = useQuery({
    queryKey: ["plan_drift", tripId],
    queryFn: () => rpc<PlanDrift>("active_plan_drift", { trip_id: tripId }),
    retry: false,
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
        <span>{copy("active_plan", language)} <code>{versionTag}</code> · {copy("exported_at", language)}{" "}
          {/* Moves with the clock, not the code: re-exporting the same plan a minute
              later changed this and failed the screen gate. Marked so capture mode can
              hold it still -- the same reason it freezes transitions. */}
          <span data-volatile="clock">{plan.stamp.exported_at.slice(0, 16)}</span> · {plan.stamp.base_currency} · {plan.stamp.language.toUpperCase()}</span>
      </div>
      {!plan.stamp.is_active_plan ? <p className="money-note money-note-warn"><b aria-hidden="true">⚠</b>{copy("superseded_plan", language)}</p> : null}
      {drift.data?.moved ? (
        <div className="money-note money-note-warn plan-drift">
          <b aria-hidden="true">⚠</b>
          <span>
            <strong>{copy("plan_evidence_moved", language)}</strong>{" "}
            {/* Two different situations, and conflating them would train the owner to
                ignore the banner: the timetable still holds, or it does not. */}
            {copy(
              drift.data.still_valid
                ? "plan_evidence_moved_still_valid"
                : "plan_evidence_moved_now_broken",
              language,
            )}
            {drift.data.violations.length ? (
              <ul>
                {drift.data.violations.map((item) => (
                  <li key={`${item.code}:${item.subject_id ?? ""}`}>{codeText(item.code, language)}</li>
                ))}
              </ul>
            ) : null}
            <Link to={`/trips/${tripId}/optimize`}>{copy("rebuild_the_plan", language)}</Link>
          </span>
        </div>
      ) : null}
      {plan.readiness.capability_gaps.length ? <details className="optimize-warnings"><summary>{copy("capability_gaps", language)}</summary><ul>{plan.readiness.capability_gaps.map((gap) => <li key={gap}>{codeText(gap, language)}</li>)}</ul></details> : null}

      <label className="optimize-variant">
        {copy("days", language)}
        <select value={day.date} onChange={(event) => setChosenDate(event.target.value)}>{plan.days.map((item) => <option key={item.date} value={item.date}>{item.date}</option>)}</select>
      </label>
      {/* derives-from: element 12 .hero-banner-image-wrapper as .dayhead, at aspect-ratio
          3/1 rather than the donor's locked 260px. That is deviation D10: it
          follows the donor's README over the donor's CSS, at the owner's
          request, and keeps the column rule unchanged. The ratio is dropped
          below 720px, where a fixed ratio would crush both columns. */}
      <div className="dayhead">
        <div className="dayhead-left">
          <span className="dayhead-num">
            {copy("day_of", language)
              .replace("{current}", String(plan.days.indexOf(day) + 1))
              .replace("{total}", String(plan.days.length))}
            {" · "}
            {copy("active_plan", language)} <code>{versionTag}</code>
          </span>
          <strong className="dayhead-date">{day.date}</strong>
          {(() => {
            const weather = forecast.data?.days.find((row) => row.date === day.date);
            if (!weather || weather.high_c === null || weather.low_c === null) return null;
            return (
              <span className="dayhead-forecast">
                {copyFormat("forecast_day", language, {
                  low: Math.round(weather.low_c),
                  high: Math.round(weather.high_c),
                  rain: Math.round(weather.rain_chance ?? 0),
                })}
              </span>
            );
          })()}
          <span className="dayhead-place">
            {copy(plan.stamp.variant_status, language)} · {plan.stamp.base_currency}
          </span>
          <span className="dayhead-window">
            {copy("variant", language)}: {copy(plan.stamp.variant_id, language)} ·{" "}
            {day.start}–{day.end}
          </span>
        </div>
        <div className="dayhead-right">
          <div className="dayhead-stats">
            {(
              [
                ["scheduled_visits", totals.scheduled_visits ?? 0, ""],
                ["walking_minutes", totals.walking_minutes ?? 0, copy("minutes", language)],
                ["travel_minutes", totals.travel_minutes ?? 0, copy("minutes", language)],
                ["unscheduled_choices", plan.unscheduled.length, ""],
              ] as const
            ).map(([label, value, unit]) => (
              <div className="dayhead-stat" key={label}>
                <span className="dayhead-stat-k">{copy(label, language)}</span>
                <strong className="dayhead-stat-v">
                  {value}
                  {unit ? <small> {unit}</small> : null}
                </strong>
              </div>
            ))}
          </div>
          {day.highest_risk ? (
            <p className="money-note money-note-warn">
              <b aria-hidden="true">⚠</b>
              <span>
                {copy("highest_risk", language)}: {stateText(day.highest_risk.status, language)}
              </span>
            </p>
          ) : null}
        </div>
      </div>

      {/* The full per-day breakdown stays available; the header carries the four
          numbers a day is actually judged on. */}
      <details className="plan-day-detail">
        <summary>{copy("day_totals", language)}</summary>
        <span>{copy("visit_minutes", language)} {totals.visit_minutes ?? 0} {copy("minutes", language)} · {copy("rewarding_walking_minutes", language)} {totals.rewarding_walking_minutes ?? 0} · {copy("plain_walking_minutes", language)} {totals.plain_walking_minutes ?? 0} · {copy("buffer_minutes", language)} {totals.buffer_minutes ?? 0}</span>
        <span>{copy("meal_minutes", language)} {totals.meal_minutes ?? 0} · {copy("preparation_minutes", language)} {totals.preparation_minutes ?? 0} · {copy("logistics_minutes", language)} {totals.logistics_minutes ?? 0}</span>
      </details>

      <div className="plan-tabs" role="tablist">
        <button aria-selected={tab === "timeline"} onClick={() => setTab("timeline")} role="tab" type="button">{copy("timeline", language)}</button>
        <button aria-selected={tab === "map"} onClick={() => setTab("map")} role="tab" type="button">{copy("tab_map", language)}</button>
      </div>
      {tab === "timeline" ? <Timeline day={day} language={language} /> : (
        <CoordinateMap
          accommodationStatus={plan.accommodation.status}
          anchor={plan.accommodation.anchor}
          basemap={basemap.data ?? null}
          language={language}
          outline={outline.data ?? null}
          stops={day.stops}
          tripId={tripId}
        />
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
