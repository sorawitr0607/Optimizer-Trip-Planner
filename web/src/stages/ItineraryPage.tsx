/* eslint-disable react-refresh/only-export-components */
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import {
  ApiError,
  rpc,
  type Basemap,
  type CountryOutline,
  type ExportFallback,
  type ExportSnapshot,
  type ChecklistItem,
  type ExportStop,
  type Frozen,
  type PlanDrift,
  type RouteShapes,
  type TripForecast,
} from "../api/client";
import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { mapsLink, type MapPlace } from "../shared/map";
import { DayStops } from "./DayStops";
import { PlanReady } from "./PlanReady";
import { TripNow } from "./TripNow";
import { isOutstanding, taskTitle } from "../shared/checklistText";
import { doneCount, useTicks } from "../shared/ticks";
import { flattenDays, type TimedItem } from "../shared/tripClock";
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
/** Mean Earth radius, in kilometres. Only used to give a scale to a projection that has
 *  no extent to fit — see `projectionOf`. */
const EARTH_RADIUS_KM = 6371;
/** How much ground the frame covers when every point is in the same place. A
 *  neighbourhood, so a lone pin reads as a street corner rather than as a continent or a
 *  doorstep; callers still zoom on top of it. */
const DEGENERATE_SPAN_KM = 2;

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
  // One point has no extent, so there is no scale to *fit* — and falling back to 1 made
  // the unit a radian. Measured in Nara: a kilometre became **0.00019 units** against
  // 139 for the same points plus one more, a factor of 730,000. Everything downstream
  // reasons in real distance — `FOCUS_KM`, `MIN_VIEW_KM`, the detail-fetch gate, the
  // "about N km across" note, the tile zoom — so all of it was computed against a scale
  // with no geographic meaning. That is the first swipe card, whose shortlist is still
  // empty, and an itinerary day with a single stop: the two maps reported as bugged.
  //
  // So where there is nothing to fit, the scale comes from the geography instead: make
  // the frame span `DEGENERATE_SPAN_KM` of real ground. Mercator is conformal, so one
  // scale serves both axes, and `cos(latitude)` is the only correction it needs.
  const finiteScale = Number.isFinite(scale)
    ? scale
    : (availableWidth * EARTH_RADIUS_KM * Math.cos((points[0].latitude * Math.PI) / 180)) /
      DEGENERATE_SPAN_KM;
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

function stateText(status: string, language: Language): string {
  return copy(`state_${status}`, language);
}

function codeText(code: string | null | undefined, language: Language): string {
  return copyFrom("OPTIMIZER_CODE_TEXT", code || "unknown", language);
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
  autoTraceKey,
  anchor,
  stops,
  accommodationStatus,
  language,
  tripId,
  basemap = null,
  outline = null,
  shapes = [],
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
  shapes?: RouteShapes["shapes"];
  /** Changing this replays the day's trace: the itinerary passes the day's own date. */
  autoTraceKey?: string;
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
  // Only the legs this day actually walks, in the order it walks them — the trip holds a
  // shape for every pair the router was asked about, most of which belong to other days.
  const walked: { points: [number, number][]; exact: boolean }[] = [];
  // The day is a **round trip**: it starts at the accommodation and ends back there. The
  // loop below joined `points` in order and stopped at the last stop, so the walk home
  // was missing from the line and from the trace — the day appeared to end wherever the
  // last museum was. Closing the ring only where there is an anchor to close it to: a
  // trip with no accommodation base has no home leg to draw.
  const homeward = points.length > 1 && points[0].place_id === "hotel" ? [points[0]] : [];
  const route = [...points, ...homeward];
  for (let at = 1; at < route.length; at += 1) {
    const from = route[at - 1];
    const to = route[at];
    // A route is stored once per ordered pair the router was asked about, so the shape
    // for B→A is reused when the day walks A→B. **Its points then have to be reversed.**
    // Without that the leg was drawn from its stored end to its stored start — the line
    // ran backwards, the next leg began where this one should have ended, and the day
    // came out as a zig-zag between places that are next door to each other. That is the
    // "back and forth route" report, and it is a drawing fault rather than a planning
    // one: measured, the visit order these days are given is already within 20 m of the
    // shortest possible round of their own stops.
    const forward = shapes.find(
      (shape) => shape.origin_id === from.place_id && shape.destination_id === to.place_id,
    );
    const backward = forward
      ? undefined
      : shapes.find(
          (shape) => shape.origin_id === to.place_id && shape.destination_id === from.place_id,
        );
    const leg = forward
      ? { ...forward, points: forward.points }
      : backward
        ? { ...backward, points: [...backward.points].reverse() }
        : undefined;
    // Every leg is drawn, whether or not a path is held: a day with one routed leg and
    // one unrouted one used to show a single line and no hint that anything was missing.
    walked.push(
      leg
        ? { points: leg.points, exact: true }
        : {
            points: [
              [from.latitude, from.longitude],
              [to.latitude, to.longitude],
            ],
            exact: false,
          },
    );
  }

  return (
    // derives-from: A1 numbered map; the list below repeats every pin and every colour.
    <section className="plan-map">
      {/* The section's own `<h2>` used to sit directly above a map that prints the
          same word as its caption, so the outline carried "Map" twice at two levels.
          The map's caption is the `<h2>` now and there is one of it. */}
      {points.length ? (
        <PlaceMap
          autoTraceKey={autoTraceKey}
          basemap={basemap}
          headingLevel={2}
          language={language}
          outline={outline}
          paths={walked}
          places={points}
          route
          title={copy("tab_map", language)}
          tripId={tripId}
          withKey={false}
        />
      ) : (
        <>
          <h2 className="money-eyebrow">{copy("tab_map", language)}</h2>
          <p>{copy("map_no_coordinates", language)}</p>
        </>
      )}
      <ul className="plan-stops">
        {anchor ? (
          <li>
            <i className={`recheck ${accommodationStatus === "booked" ? "confirmed" : ""}`} /><b>H</b>
            <span>{copy("hotel_anchor", language)} · {anchor.display_name}</span>
            {anchor.latitude != null && anchor.longitude != null ? (
              <a className="plan-stop-maps" href={mapsLink(anchor.latitude, anchor.longitude)}>
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
                <a className="plan-stop-maps" href={mapsLink(stop.latitude, stop.longitude)}>
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
  // Not during a capture, for the reason the basemap and the summaries prefetch are
  // not: it fetches and it *writes*, storing the forecast for six hours. Found on
  // 2026-08-10 by diffing the database across a capture run — one `open_meteo:forecast`
  // row and one `provider_cache` row per run, free but still the app being operated
  // rather than observed. It costs the baselines nothing: beyond Open-Meteo's 16-day
  // horizon the answer is `covered: false` and the day header renders no weather at
  // all, so the images are identical either way.
  const forecast = useQuery({
    queryKey: ["trip_forecast", tripId],
    queryFn: () => rpc<TripForecast>("trip_forecast", { trip_id: tripId }),
    enabled: Boolean(tripId) && !(typeof document !== "undefined" && document.documentElement.dataset.capture),
    retry: false,
  });
  // The walking paths, so the day's line follows the streets rather than cutting across
  // the river. Free: the shape arrived in the routing response the trip already paid for.
  const shapes = useQuery({
    queryKey: ["route_shapes", tripId],
    queryFn: () => rpc<RouteShapes>("route_shapes", { trip_id: tripId }),
    enabled: Boolean(tripId),
    staleTime: Infinity,
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
  // **The map opens first as of 2026-08-10**, and which tab is open lives in the URL.
  //
  // It was the timeline, from when the map was a strip of dots on grey and there was
  // nothing to open onto. Now that it draws the streets, the day's walk and the stops in
  // order, it is the faster answer to the question this screen is opened with — *where
  // am I going today* — and the timeline is one click away for the question that
  // follows, which is *when*.
  //
  // In the URL rather than in state, for the reason `/places` puts its own view there: a
  // reload should not throw away the tab being read, a link can point at either, and the
  // timeline stays addressable now that it is no longer what opens by default. That last
  // part is not a convenience — two tests assert the timeline's rows, and a default that
  // silently hid them from the suite would have been a default that hid them from the
  // owner too.
  const [params, setParams] = useSearchParams();
  const tab: "timeline" | "map" = params.get("view") === "timeline" ? "timeline" : "map";
  const setTab = (next: "timeline" | "map") => {
    const updated = new URLSearchParams(params);
    updated.set("view", next);
    setParams(updated, { replace: true });
  };
  const snapshot = useQuery({
    queryKey: ["export_snapshot", tripId, language],
    queryFn: () => rpc<Frozen<ExportSnapshot>>("build_export_snapshot", { trip_id: tripId, language }),
    // One retry, not the default three. Each attempt is a full snapshot build, so
    // three failures with backoff kept the screen on "Loading…" for about a minute
    // before saying anything -- and the error it eventually shows is the useful part.
    retry: 1,
  });
  // `WF-045`. The stored plan cannot notice that its own evidence moved, so the screen
  // asks. Its own query rather than part of the snapshot: a plan that no longer holds
  // must still render, or the owner loses the itinerary they came to read.
  const drift = useQuery({
    queryKey: ["plan_drift", tripId],
    queryFn: () => rpc<PlanDrift>("active_plan_drift", { trip_id: tripId }),
    retry: false,
  });

  /** null follows the real clock. See `TripNow`: the timeline is the time control. */
  const [pinned, setPinned] = useState<Date | null>(null);
  /** Searches every day, not the one on screen -- "where was that noodle place" is not
   *  a question you can ask of a single day, because not knowing the day is the point. */
  const [query, setQuery] = useState("");
  const ticks = useTicks(tripId);

  // Nullable and read before the early returns, because the hooks below cannot sit
  // after them. `plan` is non-null everywhere past the guards.
  const loaded = snapshot.data?.data ?? null;
  const allItems = useMemo(() => (loaded ? flattenDays(loaded.days) : []), [loaded]);

  if (snapshot.isPending) {
    // A bare word on an empty page, for a call that took **10.9 seconds** measured
    // against the deployment, was reported as "blank". The snapshot is the whole
    // screen, so there is nothing else to show while it arrives -- but a shape that
    // says "an itinerary is coming" is not the same picture as a page that failed.
    return (
      <section aria-busy="true" className="stage-card">
        <p aria-live="polite" className="thinking">
          <span className="thinking-dot" />
          <span>{copy("loading", language)}</span>
        </p>
        <div className="skeleton-card">
          <span className="skeleton skeleton-line wide" />
          <span className="skeleton skeleton-line" />
          <span className="skeleton skeleton-photo short" />
          <span className="skeleton skeleton-line" />
        </div>
      </section>
    );
  }
  if (snapshot.isError) {
    const message = snapshot.error instanceof ApiError
      ? copyFrom("OPTIMIZER_CODE_TEXT", snapshot.error.code, language)
      : snapshot.error.message;
    return <p className="field-error">⚠ {message}</p>;
  }

  const plan = snapshot.data.data;
  const moment = pinned ?? new Date();
  const needle = query.trim().toLowerCase();
  /** Matches across the whole trip, or the chosen day when nothing is being searched. */
  const matches = needle
    ? allItems.filter((item) =>
        [item.display_name, item.address, item.notes, item.origin_name, item.destination_name]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(needle))
    : [];
  /** What to call a row.
   *
   *  A visit leads with its stop number, because the map pins are numbered and the row
   *  and the pin have to be matchable by eye -- that correspondence is the reason the
   *  number is on the row at all. A leg is its two ends. A buffer says what it is waiting
   *  for where the optimizer named a reason, since "buffer" alone is the one row that
   *  tells you nothing. Everything else is its own kind, which is all `preparation` and
   *  `logistics` ever had. */
  const nameOf = (item: TimedItem) => {
    if (item.type === "visit" && item.stop_number != null) {
      return `${copy("stop", language)} ${item.stop_number} · ${item.display_name}`;
    }
    if (item.type === "buffer") {
      return item.reason ? codeText(item.reason, language) : copy("buffer_minutes", language);
    }
    return (
      item.display_name
      ?? (item.origin_name && item.destination_name
        ? `${item.origin_name} → ${item.destination_name}`
        : copy(`type_${item.type}`, language))
    );
  };

  const day = plan.days.find((item) => item.date === chosenDate) ?? plan.days[0];
  const dayIndex = plan.days.indexOf(day);
  const dayItems = allItems.filter((item) => item.dayDate === day.date);
  // The evening before departure is a real day in the plan — pack, documents, alarm — but
  // it is not a day *of the trip*, and numbering it "Day 1 of 6" on a trip the owner knows
  // runs the 10th to the 14th reads as an off-by-one. Measured on a fresh Porto trip:
  // dates stored 2027-04-10 → 04-14, plan days 04-09 → 04-14, and the first carried only
  // `pack_bags`, `documents_and_tickets` and `charge_and_alarm`. It is named instead of
  // numbered, and the numbering that remains counts the trip's own days.
  const prepFirst = (plan.days[0]?.items ?? []).every((item) => item.type === "preparation");
  const tripDayCount = plan.days.length - (prepFirst ? 1 : 0);
  const dayLabel =
    prepFirst && dayIndex === 0
      ? copy("day_before_you_go", language)
      : copy("day_of", language)
          .replace("{current}", String(dayIndex + (prepFirst ? 0 : 1)))
          .replace("{total}", String(tripDayCount));
  if (!day) return <p>{copy("no_schedule", language)}</p>;
  const totals = day.totals;
  const versionTag = plan.stamp.plan_version_id.replace(/^plan_/, "").slice(0, 12);
  // Query form, not path form. A hosted deployment routes every /api/* through
  // one function with a rewrite, and a rewrite replaces the path -- so a download
  // whose path carried the trip and the format would arrive asking for nothing.
  // The query survives it. Both spellings work; the local server serves either.
  const workbook = `/api/export?trip=${encodeURIComponent(tripId)}&kind=workbook.xlsx`;
  const calendar = `/api/export?trip=${encodeURIComponent(tripId)}&kind=checklist.ics`;

  return (
    <section className="stage-card itinerary-screen">
      {/* Said once per activated plan, and only where a plan actually is active. */}
      {plan.stamp.is_active_plan ? (
        <PlanReady
          gaps={plan.readiness.capability_gaps}
          language={language}
          versionId={plan.stamp.plan_version_id}
        />
      ) : null}
      <header className="money-head">
        <h1>{copy("use_title", language)}</h1>
        <p>{copy("use_help", language)}</p>
      </header>

      {/* The answer to the question this screen is opened with, before anything that
          describes the plan as a whole. */}
      <TripNow
        currentDayDate={day.date}
        dayLabelOf={(date) => {
          const index = plan.days.findIndex((entry) => entry.date === date);
          return prepFirst && index === 0
            ? copy("day_before_you_go", language)
            : copy("day_of", language)
                .replace("{current}", String(index + (prepFirst ? 0 : 1)))
                .replace("{total}", String(tripDayCount));
        }}
        items={allItems}
        language={language}
        nameOf={nameOf}
        onPin={setPinned}
        onSelectDay={setChosenDate}
        pinned={pinned}
      />
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
            {/* Its own line, and a styled one. JSX drops the whitespace between two
                expressions on separate lines, so with no violations to list this
                rendered as `...Rebuild to use it.Rebuild the plan` -- the sentence
                and its action run together in the one banner that has to be
                believed. A block element cannot do that whatever is above it. */}
            <Link className="plan-drift-action" to={`/trips/${tripId}/optimize`}>
              {copy("rebuild_the_plan", language)}
            </Link>
          </span>
        </div>
      ) : null}
      {plan.readiness.capability_gaps.length ? <details className="optimize-warnings"><summary>{copy("capability_gaps", language)}</summary><ul>{plan.readiness.capability_gaps.map((gap) => <li key={gap}>{codeText(gap, language)}</li>)}</ul></details> : null}

      {/* derives-from: element 12 .hero-banner-image-wrapper as .dayhead, at aspect-ratio
          3/1 rather than the donor's locked 260px. That is deviation D10: it
          follows the donor's README over the donor's CSS, at the owner's
          request, and keeps the column rule unchanged. The ratio is dropped
          below 720px, where a fixed ratio would crush both columns. */}
      <div className="dayhead">
        <div className="dayhead-left">
          <span className="dayhead-num">
            {dayLabel}
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

      {/* Two buttons with `aria-pressed`, not an ARIA tablist. `role="tab"` is a
          contract: it promises the reader ids and `aria-controls` linking each tab to
          a `tabpanel`, one tab stop for the set with a roving `tabIndex`, and arrow
          keys to move between them. None of that was here — the role was doing the
          styling's job — so a screen reader announced "tab 1 of 2" and then behaved
          like nothing of the sort. Implementing the full pattern is the other way to
          fix it, but these two are not really tabs: the state lives in the query
          string, each is independently linkable, and a toggle pair is what that is. */}
      {/* Tabs rather than the prev/next pair, which itself replaced a dropdown.
          The complaint about the dropdown was that it took "open, find, aim, click" and
          never showed which day you were about to get -- and tabs answer that more
          directly than a stepper does: every day is one tap, its date is on the control,
          and the ticked-through days carry a dot, so the row doubles as trip progress.
          The stepper's own reason for existing was that "the next day" is the move you
          make ninety-nine times in a hundred; that move is still one tap here. */}
      <div className="day-tabs">
        {plan.days.map((entry, index) => {
          const entryItems = allItems.filter((item) => item.dayDate === entry.date);
          const complete = entryItems.length > 0
            && entryItems.every((item) => ticks.isDone(item.key));
          return (
            <button
              aria-pressed={entry.date === day.date}
              className="day-tab"
              key={entry.date}
              onClick={() => setChosenDate(entry.date)}
              type="button"
            >
              <span className="day-tab-name">
                {prepFirst && index === 0
                  ? copy("day_before_you_go", language)
                  : copy("day_of", language)
                      .replace("{current}", String(index + (prepFirst ? 0 : 1)))
                      .replace("{total}", String(tripDayCount))}
              </span>
              <span className="day-tab-date">{entry.date.slice(5)}</span>
              {complete ? <span aria-hidden="true" className="day-tab-dot" /> : null}
            </button>
          );
        })}
      </div>

      <p className="day-meta">
        {day.date} · {dayItems.length} · {copyFormat("stops_done", language, {
          done: doneCount(dayItems, ticks.isDone),
          total: dayItems.length,
        })}
      </p>

      {/* Searches every day. "Where was that noodle place" is not a question you can ask
          of one day, because not knowing which day is the whole reason for asking. */}
      <div className="day-find">
        <input
          aria-label={copy("find_stop", language)}
          autoComplete="off"
          onChange={(event) => setQuery(event.target.value)}
          placeholder={copy("find_stop", language)}
          type="search"
          value={query}
        />
        {query.trim() ? (
          <>
            <span aria-live="polite" className="day-find-count">
              {copyFormat("find_across_days", language, { n: matches.length })}
            </span>
            <button onClick={() => setQuery("")} type="button">
              {copy("clear_search", language)}
            </button>
          </>
        ) : null}
      </div>

      <div className="plan-tabs">
        <button aria-pressed={tab === "timeline"} onClick={() => setTab("timeline")} type="button">{copy("timeline", language)}</button>
        <button aria-pressed={tab === "map"} onClick={() => setTab("map")} type="button">{copy("tab_map", language)}</button>
      </div>
      {tab === "timeline" ? (
        <DayStops
          coordsOf={(subjectId) => {
            const stop = day.stops.find((entry) => entry.subject_id === subjectId);
            return stop && stop.latitude != null && stop.longitude != null
              ? { latitude: stop.latitude, longitude: stop.longitude }
              : null;
          }}
          emptyText={copy(needle ? "find_nothing" : "no_schedule_day", language)}
          isDone={ticks.isDone}
          items={needle ? matches : dayItems}
          language={language}
          moment={moment}
          nameOf={nameOf}
          onPin={setPinned}
          onToggle={ticks.toggle}
          pinned={pinned}
        />
      ) : (
        <CoordinateMap
          accommodationStatus={plan.accommodation.status}
          autoTraceKey={day.date}
          anchor={plan.accommodation.anchor}
          basemap={basemap.data ?? null}
          language={language}
          outline={outline.data ?? null}
          shapes={shapes.data?.shapes ?? []}
          stops={day.stops}
          tripId={tripId}
        />
      )}

      {/* The day's contingencies. `Timeline` carried these and the dashboard replaced it,
          so they are rendered here rather than lost -- what to drop when the day runs
          late is exactly the thing wanted while the day is running late. */}
      {tab === "timeline" && !needle && day.fallbacks.length ? (
        <div className="day-fallbacks">
          {day.fallbacks.map((item) => (
            <FallbackRow
              fallback={item}
              key={`${item.primary_id}-${item.fallback_id}`}
              language={language}
            />
          ))}
        </div>
      ) : null}

      {/* What is still outstanding before departure.
          Deliberately a summary and not the board: `/readiness` already renders every
          item with its authority, evidence state and deadline, and a second full copy
          here would be two places to tick the same thing off. What the itinerary owes is
          the count and the soonest few, so the board is a decision rather than a
          discovery. Ordered by date with undated items last. */}
      {(() => {
        const outstanding = (plan.checklist.items as ChecklistItem[]).filter(isOutstanding);
        return (
          <details className="plan-checklist" open={outstanding.length > 0}>
            <summary>
              {copy("before_you_go", language)} ({outstanding.length})
            </summary>
            {outstanding.length ? (
              <ul className="plan-checklist-list">
                {outstanding
                  .slice()
                  .sort((left, right) =>
                    (left.due_date ?? "9999").localeCompare(right.due_date ?? "9999"))
                  .slice(0, 5)
                  .map((item) => (
                    <li key={item.item_id}>
                      <span className="plan-checklist-title">{taskTitle(item, language)}</span>
                      <span className="plan-checklist-when">
                        {/* A dash rather than `⚠ undefined`: `timing` is optional on the
                            wire, and an item with neither a date nor a bucket is simply
                            undated. */}
                        {item.due_date ?? (item.timing ? copy(item.timing, language) : "—")}
                      </span>
                    </li>
                  ))}
              </ul>
            ) : (
              <p className="setup-hint">{copy("checklist_all_clear", language)}</p>
            )}
            <Link className="primary-link" to={`/trips/${tripId}/readiness`}>
              {copy("open_full_checklist", language)} →
            </Link>
          </details>
        );
      })()}

      {/* Where to go next, said in words. The sidebar names these six but never says
          what any of them is for, so from the finished itinerary — the screen an owner
          lands on for the rest of the trip — they read as six more places to check
          rather than as six answers to questions they will actually have. */}
      <h2 className="money-eyebrow">{copy("what_next", language)}</h2>
      <ul className="plan-next-links">
        {(
          [
            ["costs", "next_costs"],
            ["split", "next_split"],
            ["evidence", "next_evidence"],
            ["readiness", "next_readiness"],
            ["revise", "next_revise"],
          ] as const
        ).map(([route, blurb]) => (
          // The sentence leads and the control follows, at the owner's asking: a link
          // above its own explanation makes the reader decide before they have read why,
          // so the explanation only ever gets read by someone who already pressed.
          <li key={route}>
            <p className="plan-next-blurb">{copy(blurb, language)}</p>
            <Link className="plan-next-action" to={`/trips/${tripId}/${route}`}>
              {copy(`stage_${route}`, language)} →
            </Link>
          </li>
        ))}
      </ul>

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
