import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router";

import {
  ApiError,
  rpc,
  type AccommodationBase,
  type CandidateChoice,
  type Journey,
  type OpeningIntervals,
  type PaidUsageStatus,
  type RouteRecord,
  type TimezoneEvidence,
  type Trip,
  type VenueNotice,
} from "../api/client";
import { copy, copyFrom, type Language } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { placeNameFrom } from "../shared/names";

const code = (value: string, language: Language) =>
  copyFrom("OPTIMIZER_CODE_TEXT", value, language);

/** Reasons the owner can resolve by confirming a window themselves. */
const OWNER_FIXABLE = new Set([
  "OPENING_NOT_FETCHED",
  "NO_PUBLISHED_HOURS",
  "EVIDENCE_EXPIRED",
  "EVIDENCE_NORMALIZER_OUTDATED",
]);

const SETUP_GAPS = new Set([
  "ACCOMMODATION_BASE_UNCONFIRMED",
  "FREE_TEXT_HARD_CONSTRAINT_NEEDS_STRUCTURED_CONFIRMATION",
]);

/**
 * Gaps grouped by what closes them.
 *
 * They used to arrive as one flat ⚠ list, so `ACCOMMODATION_BASE_UNCONFIRMED` and
 * `OPENING_EVIDENCE_MISSING` sat side by side as though they were the same kind of
 * problem. They are not: one wants an address typed into setup, the other wants a
 * button pressed on this screen. Reading the list gave no clue which.
 *
 * A gap absent from every group falls through to `owner`, so a code added to the
 * core later still lands somewhere with a heading rather than vanishing.
 */
const GAP_GROUPS = [
  { key: "gaps_grouped_setup", gaps: SETUP_GAPS },
  {
    key: "gaps_grouped_evidence",
    gaps: new Set([
      "OPENING_EVIDENCE_MISSING",
      "ROUTE_SNAPSHOT_MISSING",
      "DESTINATION_TIMEZONE_UNVERIFIED",
    ]),
  },
] as const;

/**
 * Provenance and paid usage.
 *
 * Each paid enrichment is **its own card: state first, then its cost, then the
 * one button that spends money.** Stacked full-width buttons with the costs in
 * between read as a single wall in which nothing said what it would charge for.
 * Route fetching is priced at zero on the free tier, so it states no cost —
 * that absence is correct rather than an omission.
 *
 * This is also the screen a newly created trip needs before optimization: route
 * and opening evidence are hard constraints, and until this existed only the
 * Streamlit POC could satisfy them.
 */
export function EvidencePage() {
  const { tripId = "" } = useParams();
  const { language } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState<string | null>(null);
  const [windows, setWindows] = useState<Record<string, { start: string; end: string }>>({});
  const [flash, setFlash] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [cap, setCap] = useState<string | null>(null);

  const base = useQuery({
    queryKey: ["accommodation_base", tripId],
    queryFn: () => rpc<AccommodationBase | null>("get_accommodation_base", { trip_id: tripId }),
  });
  const zone = useQuery({
    queryKey: ["timezone_evidence", tripId],
    queryFn: () => rpc<TimezoneEvidence | null>("get_timezone_evidence", { trip_id: tripId }),
  });
  const usage = useQuery({
    queryKey: ["paid_usage"],
    queryFn: () => rpc<PaidUsageStatus>("paid_usage_status"),
  });
  const intervals = useQuery({
    queryKey: ["opening_intervals", tripId],
    queryFn: () => rpc<OpeningIntervals>("opening_intervals", { trip_id: tripId }),
  });
  const routes = useQuery({
    queryKey: ["routes", tripId],
    queryFn: () => rpc<RouteRecord[]>("list_routes", { trip_id: tripId }),
  });
  const choices = useQuery({
    queryKey: ["candidate_choices", tripId],
    queryFn: () => rpc<CandidateChoice[]>("list_candidate_choices", { trip_id: tripId }),
  });
  const journey = useQuery({
    queryKey: ["journey", tripId],
    queryFn: () => rpc<Journey>("journey", { trip_id: tripId }),
  });
  const trips = useQuery({ queryKey: ["trips"], queryFn: () => rpc<Trip[]>("list_trips") });

  async function refresh() {
    await Promise.all(
      ["accommodation_base", "timezone_evidence", "opening_intervals", "routes", "journey"].map(
        (key) => queryClient.invalidateQueries({ queryKey: [key, tripId] }),
      ),
    );
    await queryClient.invalidateQueries({ queryKey: ["paid_usage"] });
  }

  const fail = (error: unknown) =>
    setFlash({ tone: "bad", text: error instanceof ApiError ? code(error.code, language) : String(error) });
  const done = (text: string) => async () => {
    setFlash({ tone: "ok", text });
    await refresh();
  };

  const saveBase = useMutation({
    mutationFn: () =>
      rpc<AccommodationBase>("confirm_accommodation_base", {
        trip_id: tripId,
        query: query ?? base.data?.name ?? "",
      }),
    onSuccess: done(copy("accommodation_base_saved", language)),
    onError: fail,
  });
  const fetchZone = useMutation({
    mutationFn: () => rpc<{ timezone: string }>("refresh_timezone", { trip_id: tripId }),
    onSuccess: async (result) => {
      setFlash({ tone: "ok", text: `${copy("timezone_fetched", language)} ${result.timezone}` });
      await refresh();
    },
    onError: fail,
  });
  const fetchHours = useMutation({
    mutationFn: () =>
      rpc<{ usable_intervals: number; places: number; provider_errors: string[] }>(
        "refresh_opening_hours",
        { trip_id: tripId },
      ),
    onSuccess: async (report) => {
      const parts = [
        copy("hours_fetched", language),
        `${copy("hours_usable", language)} ${report.usable_intervals} / ${report.places}`,
      ];
      if (report.provider_errors.length) parts.push(report.provider_errors.join(" · "));
      setFlash({ tone: report.provider_errors.length ? "bad" : "ok", text: parts.join(" · ") });
      await refresh();
    },
    onError: fail,
  });
  const fetchRoutes = useMutation({
    mutationFn: () =>
      rpc<{ routes_available: number; pairs_needed: number; skipped_over_cap: number; failed: number }>(
        "refresh_routes",
        { trip_id: tripId },
      ),
    onSuccess: async (report) => {
      const parts = [
        copy("routes_fetched", language),
        `${copy("routes_available", language)} ${report.routes_available} / ${copy("routes_needed", language)} ${report.pairs_needed}`,
      ];
      if (report.skipped_over_cap) parts.push(`${copy("routes_skipped", language)} ${report.skipped_over_cap}`);
      if (report.failed) parts.push(`${copy("routes_failed", language)} ${report.failed}`);
      setFlash({ tone: "ok", text: parts.join(" · ") });
      await refresh();
    },
    onError: fail,
  });
  // `WF-044`. Advisory only: a notice is stored under a kind `_optimizer_input` does not
  // read, so nothing here can move a scheduled minute. The screen has to say that.
  const notices = useQuery({
    queryKey: ["venue_notices", tripId],
    queryFn: () => rpc<Record<string, VenueNotice>>("list_venue_notices", { trip_id: tripId }),
  });
  const scanNotices = useMutation({
    mutationFn: () =>
      rpc<{ checked: number; notices_found: number; failed: number; provider_errors: string[] }>(
        "scan_venue_notices",
        { trip_id: tripId },
      ),
    onSuccess: async (report) => {
      const parts = [`${copy("venue_notices", language)}: ${report.notices_found} / ${report.checked}`];
      if (report.failed) parts.push(report.provider_errors.join(" · "));
      setFlash({ tone: report.failed ? "bad" : "ok", text: parts.join(" · ") });
      await queryClient.invalidateQueries({ queryKey: ["venue_notices", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["paid_usage"] });
    },
    onError: fail,
  });
  const confirmWindow = useMutation({
    mutationFn: (input: { place_id: string; start: string; end: string }) =>
      rpc<unknown>("confirm_opening_window", { trip_id: tripId, ...input }),
    onSuccess: done(copy("hours_confirmed", language)),
    onError: fail,
  });
  const saveCap = useMutation({
    mutationFn: () => rpc<number>("set_paid_cap", { cap_usd: Number(cap ?? 0) }),
    onSuccess: done(copy("cap_saved", language)),
    onError: fail,
  });

  if (intervals.isPending || usage.isPending) return <p>{copy("loading", language)}</p>;
  if (intervals.isError) return <p className="field-error">⚠ {intervals.error.message}</p>;

  const spend = usage.data;
  const windowsByPlace = intervals.data ?? {};
  const usable = Object.values(windowsByPlace).filter((item) => item.interval);
  const unusable = Object.entries(windowsByPlace).filter(([, item]) => !item.interval);
  const verifiedRoutes = (routes.data ?? []).filter((item) => item.status === "verified");
  const names = new Map(
    (choices.data ?? []).map((choice) => [
      choice.place_id,
      placeNameFrom(choice.candidate?.data, language, choice.place_id),
    ]),
  );
  const gaps = journey.data?.capability_gaps ?? [];
  const trip = trips.data?.find((item) => item.trip_id === tripId);
  const exploreFirst = trip?.planning_mode === "explore_first";

  return (
    <section className="stage-card evidence-screen">
      <header className="money-head">
        <h1>{copy("stage_evidence", language)}</h1>
        <p>{copy("evidence_help", language)}</p>
      </header>

      {flash ? (
        <p className={flash.tone === "ok" ? "setup-flash" : "field-error"} aria-live="polite">
          {flash.text}
        </p>
      ) : null}

      {/* The spend meter sits above the paid cards, so the cap is known before
          any of them is pressed. */}
      {spend ? (
        <p
          className={`money-note ${
            spend.state === "stopped"
              ? "money-note-warn"
              : spend.state === "warning"
                ? "money-note-warn"
                : "money-note-plain"
          }`}
        >
          <b aria-hidden="true">◇</b>
          <span>
            {copy("paid_usage", language)}:{" "}
            {/* Moves with the ledger, not the code: any paid call anywhere changes both
                numbers, so this screen drifted past the gate's tolerance on its own. */}
            <span data-volatile="ledger">
              US${spend.estimated_usd.toFixed(4)} / US${spend.cap_usd.toFixed(2)}
            </span>{" "}
            {copy("paid_cap", language)} ·{" "}
            <span data-volatile="ledger">{spend.requests}</span>{" "}
            {copy("paid_requests", language)}
            {spend.state === "stopped" ? ` — ${copy("paid_stopped", language)}` : ""}
            {spend.state === "warning" ? ` — ${copy("paid_warning", language)}` : ""}
          </span>
        </p>
      ) : null}

      {/* Card 1 — accommodation base. Free: it geocodes through OpenStreetMap.
          derives-from: element 36 .currency-info-box as .evidence-card, one card per action. */}
      <div className="evidence-card">
        <strong>{copy("accommodation_base_title", language)}</strong>
        <span className="setup-hint">{copy("accommodation_base_help", language)}</span>
        {base.data ? (
          <span className="evidence-value">
            {base.data.name}
            {base.data.address ? ` · ${base.data.address}` : ""}
          </span>
        ) : null}
        <label>
          {copy("accommodation_query", language)}
          <input
            onChange={(event) => setQuery(event.target.value)}
            value={query ?? base.data?.name ?? ""}
          />
        </label>
        <button disabled={saveBase.isPending} onClick={() => saveBase.mutate()} type="button">
          {copy("save_accommodation_base", language)}
        </button>
      </div>

      {/* Card 2 — time zone. Paid, and it says so immediately before the button. */}
      <div className="evidence-card">
        <strong>{copy("timezone_evidence", language)}</strong>
        {zone.data?.status === "verified" ? (
          <span className="evidence-value">
            {zone.data.timezone} · {zone.data.retrieved_at?.slice(0, 10)}
          </span>
        ) : (
          <>
            <span className="setup-hint">{copy("no_timezone", language)}</span>
            <span className="evidence-cost">{copy("timezone_cost", language)}</span>
            <button
              disabled={fetchZone.isPending || spend?.state === "stopped"}
              onClick={() => fetchZone.mutate()}
              type="button"
            >
              {copy("fetch_timezone", language)}
            </button>
          </>
        )}
      </div>

      {/* Card 3 — opening hours. Paid per selected place. */}
      <div className="evidence-card">
        <strong>
          {copy("opening_hours", language)} · {copy("hours_usable", language)}: {usable.length}
        </strong>
        {unusable.length ? (
          <span className="setup-hint">
            {copy("hours_unusable", language)}:{" "}
            {[...new Set(unusable.map(([, item]) => item.reason))]
              .sort()
              .map((reason) => code(reason, language))
              .join(", ")}
          </span>
        ) : null}
        <span className="evidence-cost">{copy("hours_cost", language)}</span>
        <button
          disabled={fetchHours.isPending || spend?.state === "stopped"}
          onClick={() => fetchHours.mutate()}
          type="button"
        >
          {copy("fetch_hours", language)}
        </button>

        {/* The owner can confirm a window themselves rather than pay, which is
            the free path out of a missing-hours gap. */}
        {unusable
          .filter(([, item]) => OWNER_FIXABLE.has(item.reason))
          .map(([placeId, item]) => {
            const draft = windows[placeId] ?? { start: "08:00", end: "18:00" };
            return (
              <details className="evidence-owner-hours" key={placeId}>
                <summary>
                  {names.get(placeId) ?? placeId} · {code(item.reason, language)}
                </summary>
                <span className="setup-hint">{copy("hours_owner_help", language)}</span>
                <div className="evidence-window">
                  <label>
                    {copy("start", language)}
                    <input
                      onChange={(event) =>
                        setWindows((current) => ({
                          ...current,
                          [placeId]: { ...draft, start: event.target.value },
                        }))
                      }
                      type="time"
                      value={draft.start}
                    />
                  </label>
                  <label>
                    {copy("end", language)}
                    <input
                      onChange={(event) =>
                        setWindows((current) => ({
                          ...current,
                          [placeId]: { ...draft, end: event.target.value },
                        }))
                      }
                      type="time"
                      value={draft.end}
                    />
                  </label>
                  <button
                    disabled={confirmWindow.isPending}
                    onClick={() =>
                      confirmWindow.mutate({ place_id: placeId, start: draft.start, end: draft.end })
                    }
                    type="button"
                  >
                    {copy("confirm_hours", language)}
                  </button>
                </div>
              </details>
            );
          })}
      </div>

      {/* Card 4 — routes. Priced at zero on the free tier, so it states no cost. */}
      <div className="evidence-card">
        <strong>{copy("venue_notices", language)}</strong>
        <span className="setup-hint">{copy("venue_notices_hint", language)}</span>
        <button
          disabled={scanNotices.isPending}
          onClick={() => scanNotices.mutate()}
          type="button"
        >
          {copy("scan_venue_notices", language)}
        </button>
        {Object.keys(notices.data ?? {}).length === 0 ? (
          <span className="setup-hint">{copy("venue_notices_none", language)}</span>
        ) : (
          <>
            <p className="setup-hint">{copy("venue_notices_advisory", language)}</p>
            <ul className="venue-notices">
              {Object.values(notices.data ?? {}).map((notice) => (
                <li key={notice.place_id}>
                  <strong>{notice.name}</strong>
                  {/* The quote is the product. It is verified to appear verbatim on the
                      page, so the owner can judge it against the source themselves. */}
                  <blockquote>{notice.quote}</blockquote>
                  <a href={notice.source_url} rel="noreferrer" target="_blank">
                    {copy("venue_notice_quote", language)}
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="evidence-card">
        <strong>
          {verifiedRoutes.length
            ? `${copy("routes_available", language)}: ${verifiedRoutes.length}`
            : copy("routes", language)}
        </strong>
        {verifiedRoutes.length === 0 ? (
          <span className="setup-hint">{copy("no_routes", language)}</span>
        ) : null}
        <button
          disabled={fetchRoutes.isPending}
          onClick={() => fetchRoutes.mutate()}
          type="button"
        >
          {copy("fetch_routes", language)}
        </button>
      </div>

      <details className="evidence-cap">
        <summary>{copy("raise_cap", language)}</summary>
        <label>
          {copy("cap_amount", language)}
          <input
            min="0"
            onChange={(event) => setCap(event.target.value)}
            step="1"
            type="number"
            value={cap ?? String(spend?.cap_usd ?? 10)}
          />
        </label>
        <button disabled={saveCap.isPending} onClick={() => saveCap.mutate()} type="button">
          {copy("save_cap", language)}
        </button>
      </details>

      {gaps.length ? (
        <>
          <p className="money-note money-note-warn">
            <b aria-hidden="true">⚠</b>
            <span>{copy("evidence_blockers", language)}</span>
          </p>
          <p className="setup-hint">{copy("gap_action_hint", language)}</p>
          {(() => {
            const grouped = GAP_GROUPS.map((group) => ({
              key: group.key,
              items: gaps.filter((gap) => group.gaps.has(gap)),
            }));
            const claimed = new Set(grouped.flatMap((group) => group.items));
            const rest = gaps.filter((gap) => !claimed.has(gap));
            return [...grouped, { key: "gaps_grouped_owner", items: rest }]
              .filter((group) => group.items.length)
              .map((group) => (
                // derives-from: element 26 .recent-row-item as .evidence-gap-group
                <div className="evidence-gap-group" key={group.key}>
                  <h3 className="money-eyebrow">{copy(group.key, language)}</h3>
                  <ul className="revise-list">
                    {group.items.map((gap) => (
                      <li key={gap}>{code(gap, language)}</li>
                    ))}
                  </ul>
                </div>
              ));
          })()}
          <div className="setup-actions">
            {gaps.some((gap) => SETUP_GAPS.has(gap)) ? (
              <button onClick={() => navigate(`/trips/${tripId}/setup`)} type="button">
                {copy("next_step", language)}: {copy("stage_setup", language)}
              </button>
            ) : null}
            {/* Explore mode may continue with a Provisional result that cannot be
                mistaken for a validated plan. */}
            {exploreFirst ? (
              <button
                className="setup-primary"
                onClick={() => navigate(`/trips/${tripId}/optimize`)}
                type="button"
              >
                {copy("continue_provisional", language)}
              </button>
            ) : null}
          </div>
          {exploreFirst ? (
            <p className="setup-hint">{copy("provisional_evidence_help", language)}</p>
          ) : null}
        </>
      ) : (
        <div className="setup-actions">
          <button
            className="setup-primary"
            onClick={() => navigate(`/trips/${tripId}/optimize`)}
            type="button"
          >
            {copy("next_step", language)}: {copy("stage_optimize", language)}
          </button>
        </div>
      )}
    </section>
  );
}
