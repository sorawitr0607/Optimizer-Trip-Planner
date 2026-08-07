import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PlaceDeck } from "./PlaceDeck";
import { StayAreas } from "./StayAreas";
import { useNavigate, useParams } from "react-router";

import {
  ApiError,
  rpc,
  type CandidateChoice,
  type DiscoveryRun,
  type PaidCallCheck,
  type PlaceInsight,
  type PlaceSummary,
  type Ranking,
  type RankingLaneEntry,
  type SetupDraft,
} from "../api/client";
import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { placeAltName, placeName } from "../shared/names";

const LANES = ["main_queue", "city_icons", "worth_it_if", "local_alternatives", "browse_all"] as const;
const CHOICES = ["must_do", "interested", "maybe"] as const;
const REJECTION_REASONS = [
  "null",
  "too_crowded",
  "too_expensive",
  "too_tiring",
  "wrong_vibe",
  "weak_value",
  "already_seen",
] as const;
const CONSIDERED = new Set<string>(CHOICES);
const PHOTO_LIMIT = 5;

type Lane = (typeof LANES)[number];

function categoryName(category: string, language: Language): string {
  const translated = copyFrom("CATEGORY_TEXT", category, language);
  return language === "en" && translated.startsWith("⚠ ")
    ? category.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
    : translated;
}

function laneEntries(ranking: Ranking, lane: Lane): RankingLaneEntry[] {
  if (lane === "main_queue" || lane === "local_alternatives") return ranking.lanes[lane];
  return ranking.lanes[lane].map((place_id) => ({ place_id }));
}

function errorText(error: Error | null, language: Language): string | null {
  if (!error) return null;
  return error instanceof ApiError
    ? copyFrom("OPTIMIZER_CODE_TEXT", error.code, language)
    : error.message;
}

/** Broad discovery plus the functional ranked list; the deferred card grid is not needed for S4. */
export function PlacesPage() {
  const { tripId = "" } = useParams();
  const { language } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // Opens on City Icons, not the main queue. Measured on the real Taipei catalogue:
  // 20 of the main queue's top 20 have no Wikidata id and so no description, and the
  // lane led with an RC model airplane runway; all 20 of City Icons' top 20 have one.
  // The queue is still one select away.
  const [lane, setLane] = useState<Lane>("city_icons");
  // Deck first, because WF-005 designed this stage as a swipe queue and the list is
  // the fallback for comparing two places side by side. The list is one button away.
  const [mode, setMode] = useState<"deck" | "list">("deck");
  // Free descriptions and photos: Wikidata plus Wikipedia, no key and no charge.
  // This is what answers "the summary tells me nothing about the place" -- the
  // templated sentence below is built from the same codes for every card.
  const fetchSummary = useMutation({
    mutationFn: (placeId: string) =>
      rpc("refresh_place_summaries", { trip_id: tripId, place_ids: [placeId] }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["place_summaries", tripId] }),
  });
  const summaries = useQuery({
    queryKey: ["place_summaries", tripId],
    queryFn: () => rpc<Record<string, PlaceSummary>>("list_place_summaries", { trip_id: tripId }),
    enabled: Boolean(tripId),
  });
  const [cardId, setCardId] = useState("");
  const [rejectionReason, setRejectionReason] = useState("null");
  const [flash, setFlash] = useState<string | null>(null);
  const [insights, setInsights] = useState<Record<string, PlaceInsight>>({});
  const [photoIndexes, setPhotoIndexes] = useState<Record<string, number>>({});

  const setup = useQuery({
    queryKey: ["setup", tripId],
    queryFn: () => rpc<SetupDraft | null>("get_setup", { trip_id: tripId }),
  });
  const discovery = useQuery({
    queryKey: ["discovery", tripId],
    queryFn: () => rpc<DiscoveryRun | null>("get_latest_discovery", { trip_id: tripId }),
  });
  const choices = useQuery({
    queryKey: ["candidate_choices", tripId],
    queryFn: () => rpc<CandidateChoice[]>("list_candidate_choices", { trip_id: tripId }),
  });
  const catalog = discovery.data?.candidates.data.candidates ?? [];
  const ranking = useQuery({
    queryKey: ["ranking", tripId],
    queryFn: () => rpc<Ranking>("rank_candidates", { trip_id: tripId }),
    enabled: catalog.length > 0,
  });

  const entries = ranking.data ? laneEntries(ranking.data, lane) : [];
  const selectedId = entries.some((entry) => entry.place_id === cardId)
    ? cardId
    : (entries[0]?.place_id ?? "");
  const candidate = catalog.find((item) => item.place_id === selectedId);
  const card = selectedId ? ranking.data?.cards[selectedId] : undefined;
  const choice = choices.data?.find((item) => item.place_id === selectedId);
  const insight = selectedId ? insights[selectedId] : undefined;

  const detailsCost = useQuery({
    queryKey: ["paid_check", "google_places:card_details"],
    queryFn: () =>
      rpc<PaidCallCheck>("check_paid_call", {
        operation: "google_places:card_details",
      }),
    enabled: Boolean(candidate),
  });
  const photosCost = useQuery({
    queryKey: ["paid_check", "google_places:photo", PHOTO_LIMIT],
    queryFn: () =>
      rpc<PaidCallCheck>("check_paid_call", {
        operation: "google_places:photo",
        count: PHOTO_LIMIT,
      }),
    enabled: Boolean(candidate),
  });

  async function refreshReads() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["ranking", tripId] }),
      queryClient.invalidateQueries({ queryKey: ["candidate_choices", tripId] }),
      queryClient.invalidateQueries({ queryKey: ["journey", tripId] }),
    ]);
  }

  const discover = useMutation({
    mutationFn: (force_refresh: boolean) =>
      rpc<DiscoveryRun>("discover_places", { trip_id: tripId, force_refresh }),
    onSuccess: async (value) => {
      queryClient.setQueryData(["discovery", tripId], value);
      setFlash("discovery_saved");
      setCardId("");
      await refreshReads();
    },
  });
  const saveChoice = useMutation({
    // `placeId` defaults to the list's selection; the deck passes its own, because
    // the card in the deck is not the card in the select.
    mutationFn: ({ action, reason, placeId }: { action: string; reason?: string | null; placeId?: string }) =>
      rpc<CandidateChoice>("save_candidate_choice", {
        trip_id: tripId,
        place_id: placeId ?? selectedId,
        action,
        reason: reason ?? null,
      }),
    onSuccess: async () => {
      setFlash("choice_saved");
      await refreshReads();
    },
  });
  const clearChoice = useMutation({
    mutationFn: () => rpc<null>("clear_candidate_choice", { trip_id: tripId, place_id: selectedId }),
    onSuccess: async () => {
      setFlash("choice_cleared");
      await refreshReads();
    },
  });
  const enrich = useMutation({
    mutationFn: () =>
      rpc<PlaceInsight>("enrich_place_card", {
        trip_id: tripId,
        place_id: selectedId,
        language,
      }),
    onSuccess: (value) => setInsights((current) => ({ ...current, [selectedId]: value })),
  });

  if (setup.isPending || discovery.isPending || choices.isPending) {
    return <p>{copy("loading", language)}</p>;
  }
  const readError = setup.error ?? discovery.error ?? choices.error;
  if (readError) return <p className="field-error">⚠ {errorText(readError, language)}</p>;

  const report = discovery.data?.report.data;
  const selectedChoices = (choices.data ?? []).filter((item) => CONSIDERED.has(item.action));
  const paidAllowed = Boolean(detailsCost.data?.allowed && photosCost.data?.allowed);
  const paidEstimate = (detailsCost.data?.estimate_usd ?? 0) + (photosCost.data?.estimate_usd ?? 0);
  const paidCaption = copy("live_details_cost", language)
    .replace("{cost:.3f}", paidEstimate.toFixed(3))
    .replace("{count}", String(PHOTO_LIMIT));
  const mutationError = detailsCost.error ?? photosCost.error
    ?? discover.error ?? saveChoice.error ?? clearChoice.error ?? enrich.error;

  return (
    <section className="stage-card places-screen">
      <header className="money-head">
        <h1>{copy("discover_title", language)}</h1>
        <p>{copy("discover_help", language)}</p>
      </header>
      <p className="setup-hint">{copy("osm_notice", language)}</p>
      {flash ? <p className="setup-flash" aria-live="polite">{copy(flash, language)}</p> : null}
      {mutationError ? (
        <p className="field-error" aria-live="polite">⚠ {errorText(mutationError, language)}</p>
      ) : null}

      <div className="optimize-actions">
        <button className="setup-primary" disabled={discover.isPending} onClick={() => discover.mutate(false)} type="button">
          {discover.isPending ? copy("discovering", language) : copy("discover", language)}
        </button>
        <button disabled={!discovery.data || discover.isPending} onClick={() => discover.mutate(true)} type="button">
          {copy("refresh", language)}
        </button>
      </div>
      {!discovery.data ? <p className="setup-hint">{copy("ranking_wait", language)}</p> : null}

      {discovery.data && report ? (
        <>
          {setup.data && discovery.data.setup_sha256 !== setup.data.snapshot.sha256 ? (
            <p className="money-note money-note-warn"><b aria-hidden="true">⚠</b>{copy("stale_setup", language)}</p>
          ) : null}
          {new Set(["unavailable", "error", "stale"]).has(discovery.data.status) ? (
            <p className="money-note money-note-warn"><b aria-hidden="true">⚠</b>{copy("provider_gap", language)}</p>
          ) : null}
          <details className="places-coverage">
          <summary><h2 className="money-eyebrow">{copy("coverage", language)}</h2></summary>
          <p className="places-status">
            <strong>{copy("provider_status", language)}:</strong>{" "}
            {copy(`provider_${discovery.data.status}`, language)}
          </p>
          <div className="money-tiles">
            {([
              ["candidates", report.canonical_candidates],
              ["duplicates", report.duplicates_merged],
              ["cells", report.geographic_cells_with_candidates],
            ] as const).map(([label, value]) => (
              <div className="money-tile" key={label}>
                <span className="money-tile-label">{copy(label, language)}</span>
                <strong className="money-tile-value">{value ?? 0}</strong>
              </div>
            ))}
          </div>
          <p className="setup-hint">{copy("unranked", language)}</p>
          {catalog.length ? (
            <details>
              <summary>{copy("catalog_table", language)}</summary>
              <div className="money-table-scroll">
                <table className="money-table">
                  <thead><tr><th>{copy("name", language)}</th><th>{copy("local_name", language)}</th><th>{copy("category", language)}</th><th>{copy("opening", language)}</th><th>{copy("source", language)}</th></tr></thead>
                  <tbody>
                    {catalog.map((item) => {
                      const source = item.provider_aliases[0]?.source_url;
                      return (
                        <tr key={item.place_id}>
                          <td>{placeName(item, language, item.name)}</td>
                          <td>{item.names?.local ?? item.name}</td>
                          <td>{categoryName(item.category, language)}</td>
                          <td>{item.operational_evidence.opening_hours.state === "official_confirmed" ? copy("evidence_verified", language) : copy("opening_unverified", language)}</td>
                          <td>{source ? <a href={source} rel="noreferrer" target="_blank">{copy("source", language)}</a> : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </details>
          ) : <p>{copy("no_candidates", language)}</p>}
          {report.attribution && report.license_url ? (
            <a href={report.license_url} rel="noreferrer" target="_blank">{report.attribution} · {report.license}</a>
          ) : null}
          <details><summary>{copy("details", language)}</summary><pre className="places-json">{JSON.stringify(report, null, 2)}</pre></details>
          </details>
        </>
      ) : null}

      <h2 className="money-eyebrow">{copy("ranking_title", language)}</h2>
      <p className="setup-hint">{copy("ranking_help", language)}</p>
      <p className="setup-hint">{copy("formula_note", language)}</p>
      {catalog.length && ranking.isPending ? <p>{copy("loading", language)}</p> : null}
      {ranking.isError ? <p className="field-error">⚠ {errorText(ranking.error, language)}</p> : null}

      {ranking.data ? (
        <>
          <div className="setup-actions">
            <button onClick={() => setMode(mode === "deck" ? "list" : "deck")} type="button">
              {copy(mode === "deck" ? "list_mode" : "deck_mode", language)}
            </button>
          </div>
          {mode === "deck" ? (
            <>
              <p className="setup-hint">{copy("deck_help", language)}</p>
              <PlaceDeck
                choices={choices.data ?? []}
                language={language}
                altNameOf={(placeId) => {
                  const found = catalog.find((item) => item.place_id === placeId);
                  return found ? placeAltName(found, language) : null;
                }}
                nameOf={(placeId) => {
                  // `catalog` is already the normalized candidate list on this page.
                  const found = catalog.find((item) => item.place_id === placeId);
                  return found ? placeName(found, language, found.name) : placeId;
                }}
                onDecide={(placeId, action, reason) =>
                  saveChoice.mutate({ action, reason, placeId })
                }
                onWantSummary={(placeId) => fetchSummary.mutate(placeId)}
                ranking={ranking.data}
                summaries={summaries.data ?? {}}
              />
              {/* `WF-040`, placed here by the owner: the ranking depends on the places
                  chosen above, so it belongs under the deck rather than beside the
                  timetable on `/optimize`. */}
              <StayAreas language={language} tripId={tripId} />
            </>
          ) : null}
          <div className="places-pickers" hidden={mode === "deck"}>
            <label className="optimize-variant">
              {copy("lane", language)}
              <select value={lane} onChange={(event) => { setLane(event.target.value as Lane); setCardId(""); }}>
                {LANES.map((value) => <option key={value} value={value}>{copy(value, language)} ({laneEntries(ranking.data, value).length})</option>)}
              </select>
            </label>
            {entries.length ? (
              <label className="optimize-variant">
                {copy("select_card", language)}
                <select value={selectedId} onChange={(event) => setCardId(event.target.value)}>
                  {entries.map((entry) => {
                    const item = catalog.find((value) => value.place_id === entry.place_id);
                    return <option key={entry.place_id} value={entry.place_id}>{item ? placeName(item, language, item.name) : entry.place_id} · {ranking.data.cards[entry.place_id]?.total_score.toFixed(1)}/100</option>;
                  })}
                </select>
              </label>
            ) : null}
          </div>
          {!entries.length ? <p>{copy("no_lane_cards", language)}</p> : null}

          {candidate && card ? (
            // derives-from: A4 ranked candidate card, reduced to one functional list card for S4.
            <article className="place-card">
              <header className="place-card-head">
                <div><h3>{placeName(candidate, language, candidate.name)}</h3>{candidate.names?.local && candidate.names.local !== placeName(candidate, language, candidate.name) ? <p>{candidate.names.local}</p> : null}<span className="money-tag">{categoryName(candidate.category, language)}</span></div>
                <strong className="place-score">{card.total_score.toFixed(1)}<small>/100</small></strong>
              </header>
              {(() => {
                const about = summaries.data?.[selectedId];
                const prose = about?.text?.[language] ?? about?.text?.en ?? "";
                const onlyEnglish = language === "th" && !about?.text?.th && Boolean(about?.text?.en);
                const asking = fetchSummary.isPending;
                if (!prose && !about?.image_url) {
                  // Nothing found: say so, and keep the mechanism sentence as the
                  // fallback rather than showing an empty card.
                  return (
                    <>
                      <div className="place-paid-action">
                        <p className="setup-hint">
                          {summaries.data && selectedId in summaries.data
                            ? copy("no_description_yet", language)
                            : copy("descriptions_are_free", language)}
                        </p>
                        {summaries.data && selectedId in summaries.data ? null : (
                          <button disabled={asking} onClick={() => fetchSummary.mutate(selectedId)} type="button">
                            {copy("load_descriptions", language)}
                          </button>
                        )}
                      </div>
                      <p>{copyFormat("place_summary_template", language, {
                        name: placeName(candidate, language, candidate.name),
                        category: categoryName(candidate.category, language),
                        best_for: (card.matched_tags.length ? card.matched_tags : card.candidate_tags).slice(0, 4).map((tag) => copyFrom("TAG_TEXT", tag, language)).join(" · "),
                        reason: copyFrom("EXPLANATION_TEXT", card.why_shown[0], language),
                        caution: card.cons.slice(0, 2).map((code) => copyFrom("EXPLANATION_TEXT", code, language)).join(" · "),
                      })}</p>
                    </>
                  );
                }
                return (
                  // derives-from: element 26 .recent-row-item as .place-about
                  <div className="place-about">
                    {about?.image_url ? (
                      <img
                        alt={placeName(candidate, language, candidate.name)}
                        className="place-about-photo"
                        loading="lazy"
                        src={about.image_url}
                      />
                    ) : null}
                    <div className="place-about-text">
                      <h4>{copy("about_this_place", language)}</h4>
                      {prose ? <p>{prose}</p> : null}
                      {onlyEnglish ? <p className="setup-hint">{copy("description_thai_missing", language)}</p> : null}
                      <p className="setup-hint">
                        {copy("wikipedia_credit", language)}
                        {about?.source_urls?.[language] || about?.source_urls?.en ? (
                          <>
                            {" · "}
                            <a href={about.source_urls[language] ?? about.source_urls.en} rel="noreferrer" target="_blank">
                              {copy("read_on_wikipedia", language)}
                            </a>
                          </>
                        ) : null}
                      </p>
                    </div>
                  </div>
                );
              })()}
              <div className="place-card-facts">
                <span><b>{copy("duration", language)}:</b> {card.duration_estimate.minimum_minutes}–{card.duration_estimate.maximum_minutes} {copy("minutes", language)}</span>
                <span><b>{copy("feasibility", language)}:</b> {copy(card.feasibility.state, language)}</span>
              </div>

              {insight ? (
                <div className="place-insight">
                  {insight.photo_gallery?.length ? (() => {
                    const index = (photoIndexes[selectedId] ?? 0) % insight.photo_gallery.length;
                    const photo = insight.photo_gallery[index];
                    return <><img alt={placeName(candidate, language, candidate.name)} src={photo.uri} /><div className="setup-actions"><button onClick={() => setPhotoIndexes((current) => ({ ...current, [selectedId]: (index - 1 + insight.photo_gallery!.length) % insight.photo_gallery!.length }))} type="button">← {copy("previous_photo", language)}</button><span>{copy("photo_count", language).replace("{current}", String(index + 1)).replace("{total}", String(insight.photo_gallery.length))}</span><button onClick={() => setPhotoIndexes((current) => ({ ...current, [selectedId]: (index + 1) % insight.photo_gallery!.length }))} type="button">{copy("next_photo", language)} →</button></div></>;
                  })() : null}
                  {insight.rating != null ? <p><b>{copy("source_rating", language)}:</b> {insight.rating.toFixed(1)}/5 · {(insight.user_rating_count ?? 0).toLocaleString()} {copy("ratings", language)}</p> : null}
                  {insight.review_summary?.text ? <><h4>{copy("review_summary", language)}</h4><p>{insight.review_summary.text}</p>{insight.review_summary.disclosure ? <p className="setup-hint">{insight.review_summary.disclosure}</p> : null}</> : null}
                  {insight.reviews?.slice(0, 2).map((review, index) => <blockquote key={`${review.author}-${index}`}><p>{review.text}</p><footer>{review.author ?? copy("google_reviewer", language)}{review.rating != null ? ` · ${review.rating.toFixed(0)}/5` : ""}</footer></blockquote>)}
                  <p className="setup-hint">{copy("live_details_session_only", language)}</p>
                </div>
              ) : (
                <div className="place-paid-action">
                  <p className="setup-hint">{detailsCost.isPending || photosCost.isPending ? copy("loading", language) : paidCaption}</p>
                  <button disabled={!paidAllowed || enrich.isPending} onClick={() => enrich.mutate()} type="button">{copy("load_live_details", language)}</button>
                </div>
              )}

              {choice ? <p className="setup-hint">{copy("current_choice", language)}: {copy(choice.action, language)}{choice.reason ? ` · ${copyFrom("REJECTION_TEXT", choice.reason, language)}` : ""}</p> : null}
              <div className="place-choice-actions">
                {CHOICES.map((action) => <button key={action} onClick={() => saveChoice.mutate({ action })} type="button">{copy(action, language)}</button>)}
                <details><summary>{copy("not_for_trip", language)}</summary><label>{copy("rejection_reason", language)}<select value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value)}>{REJECTION_REASONS.map((reason) => <option key={reason} value={reason}>{copyFrom("REJECTION_TEXT", reason, language)}</option>)}</select></label><button onClick={() => saveChoice.mutate({ action: "not_for_trip", reason: rejectionReason === "null" ? null : rejectionReason })} type="button">{copy("not_for_trip", language)}</button></details>
                {choice ? <button onClick={() => clearChoice.mutate()} type="button">{copy("clear_choice", language)}</button> : null}
              </div>

              <details className="place-explanations">
                <summary>{copy("card_detail", language)}</summary>
                <div className="place-detail-grid">
                  {(["why", "pros", "cons"] as const).map((kind) => {
                    const values = kind === "why" ? card.why_shown : card[kind];
                    // "Why shown" describes the matcher, not the place: its top two
                    // codes appear on 793 of 832 cards. Titled for what it is.
                    const heading = kind === "why" ? copy("why_it_matched_you", language) : copy(kind, language);
                    return <div key={kind}><h4>{heading}</h4><ul>{values.map((code) => <li key={code}>{copyFrom("EXPLANATION_TEXT", code, language)}</li>)}</ul></div>;
                  })}
                </div>
                <h4>{copy("breakdown", language)}</h4>
                <div className="money-table-scroll"><table className="money-table"><thead><tr><th>{copy("dimension", language)}</th><th>{copy("points", language)}</th><th>{copy("maximum", language)}</th></tr></thead><tbody>{Object.entries(card.dimensions).map(([dimension, value]) => <tr key={dimension}><td>{copyFrom("DIMENSION_TEXT", dimension, language)}</td><td>{value.score}</td><td>{value.max}</td></tr>)}</tbody></table></div>
              </details>
              {candidate.provider_aliases[0]?.source_url ? <a href={candidate.provider_aliases[0].source_url ?? undefined} rel="noreferrer" target="_blank">{copy("source", language)} ↗</a> : null}
            </article>
          ) : null}
        </>
      ) : null}

      <div className="optimize-actions">
        <button className="setup-primary" disabled={!selectedChoices.length} onClick={() => navigate(`/trips/${tripId}/optimize`)} type="button">{copy("stage_optimize", language)}</button>
      </div>
      {!selectedChoices.length ? <p className="setup-hint">{copyFrom("OPTIMIZER_CODE_TEXT", "no_places_chosen", language)}</p> : null}
    </section>
  );
}
