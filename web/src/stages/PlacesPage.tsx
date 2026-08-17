import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { PlaceDeck } from "./PlaceDeck";
import { Thinking } from "../shared/Thinking";
import { PlacesTour } from "./PlacesTour";
import { useNavigate, useParams, useSearchParams } from "react-router";

import {
  ApiError,
  type Basemap,
  type CandidateChoice,
  type CountryOutline,
  type DiscoveryRun,
  type PaidCallCheck,
  type PlaceInsight,
  type PlaceSummary,
  type Ranking,
  type RankingLaneEntry,
  rpc,
  type SetupDraft,
} from "../api/client";
import { copy, copyFormat, copyFrom, type Language } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { mergeNames, placeAltName, placeName } from "../shared/names";
import { galleryFor } from "../shared/photos";
import { mapPlaces } from "../shared/map";
import { PlaceMap } from "./PlaceMap";

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
/** How far ahead of the deck to fetch free descriptions. Wikidata and Wikipedia are
 *  free and uncapped, but each place is several requests, so this stays a window
 *  that slides rather than a sweep of all 832 candidates. */
const PREFETCH_AHEAD = 6;
/** How much of a lane the deck offers before asking whether you want more.
 *
 *  Twenty is about a sitting: enough that the strongest of a lane are all in reach, few
 *  enough that finishing it is a real event rather than a horizon. The lanes are score
 *  ordered, so the first twenty of City Icons are its twenty best — on the owner's Hong
 *  Kong catalogue that lane holds **431**, which is a catalogue, not a shortlist. */
const LANE_PAGE = 20;
/** How many audit rows to build at a time. The Taipei catalogue is 849 places, and
 *  the table listing them sits inside a `<details>` that is closed on arrival —
 *  which hides it without costing any less: React builds every row, the browser
 *  lays out 4245 cells, and none of them are on screen. Nobody reads 849 rows in
 *  order anyway; this is the provenance table, opened to check one place. */
const CATALOG_PAGE = 50;

type Lane = (typeof LANES)[number];

/** Whole days between two ISO dates, inclusive, or null when either is missing. */
function daysBetween(start: string | null | undefined, end: string | null | undefined): number | null {
  if (!start || !end) return null;
  const from = Date.parse(`${start}T00:00:00`);
  const to = Date.parse(`${end}T00:00:00`);
  if (Number.isNaN(from) || Number.isNaN(to) || to < from) return null;
  return Math.round((to - from) / 86_400_000) + 1;
}

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
  /** How many of the current lane the deck may deal. Reset whenever the lane changes. */
  const [shown, setShown] = useState(LANE_PAGE);
  const pickLane = (next: Lane) => {
    setLane(next);
    setShown(LANE_PAGE);
    setDecidedHere(0);
    setCardId("");
  };
  // Deck first, because WF-005 designed this stage as a swipe queue and the list is
  // the fallback for comparing two places side by side. The list is one button away.
  //
  // In the URL rather than in state, so a reload does not throw an owner comparing two
  // places back into the deck — and so the two views are separately linkable.
  const [params, setParams] = useSearchParams();
  const mode: "deck" | "list" = params.get("view") === "list" ? "list" : "deck";
  // In the URL like the view mode, for the same reason: a reload should not close the
  // drawer an owner was reading, and it makes the open state reachable without a click.
  const shortlistOpen = params.get("shortlist") === "open";
  const setShortlistOpen = (open: boolean) => {
    const updated = new URLSearchParams(params);
    if (open) updated.set("shortlist", "open");
    else updated.delete("shortlist");
    setParams(updated, { replace: true });
  };
  const setMode = (next: "deck" | "list") => {
    const updated = new URLSearchParams(params);
    if (next === "list") updated.set("view", "list");
    else updated.delete("view");
    setParams(updated, { replace: true });
  };
  // Free descriptions and photos: Wikidata plus Wikipedia, no key and no charge.
  // This is what answers "the summary tells me nothing about the place" -- the
  // templated sentence below is built from the same codes for every card.
  const fetchSummary = useMutation({
    mutationFn: (placeIds: string[]) =>
      rpc("refresh_place_summaries", { trip_id: tripId, place_ids: placeIds }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["place_summaries", tripId] }),
  });
  // Which places have already been asked for, so the effect below cannot re-fire on
  // a place Wikidata genuinely has nothing for.
  const asked = useRef(new Set<string>());
  const summaries = useQuery({
    queryKey: ["place_summaries", tripId],
    queryFn: () => rpc<Record<string, PlaceSummary>>("list_place_summaries", { trip_id: tripId }),
    enabled: Boolean(tripId),
  });
  const [cardId, setCardId] = useState("");
  /** Reported by the deck: the card in front has not finished arriving. */
  const [cardPending, setCardPending] = useState(false);
  /** Decisions taken out of the current page, which is what makes the page end. */
  const [decidedHere, setDecidedHere] = useState(0);
  // The coverage report is collapsed on arrival and holds the audit table and the
  // raw provider JSON. `<details>` hides its contents; it does not avoid building
  // them, so both were mounted on every visit to this screen. Rendering them on
  // first open is the whole fix, and closing it again keeps them — reopening
  // something you just read should not rebuild it.
  const [coverageOpened, setCoverageOpened] = useState(false);
  const [catalogShown, setCatalogShown] = useState(CATALOG_PAGE);
  const [rejectionReason, setRejectionReason] = useState("null");
  const [flash, setFlash] = useState<string | null>(null);
  const [insights, setInsights] = useState<Record<string, PlaceInsight>>({});

  const [photoIndexes, setPhotoIndexes] = useState<Record<string, number>>({});

  // Fetched once per trip and stored for a month: roads and coastlines do not move.
  // Never during a capture — it writes, and a capture must observe the app, not
  // operate it, which is the lesson the summaries prefetch taught the hard way.
  // The country's own shape, fetched once per trip and cached for a quarter, so both
  // maps can be zoomed out to it. Read-only under a capture, like the basemap.
  const outline = useQuery({
    queryKey: ["country_outline", tripId],
    queryFn: () =>
      rpc<CountryOutline | null>(
        typeof document !== "undefined" && document.documentElement.dataset.capture
          ? "country_outline"
          : "refresh_country_outline",
        { trip_id: tripId },
      ),
  });
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
  const byId = Object.fromEntries(catalog.map((item) => [item.place_id, item]));
  const ranking = useQuery({
    queryKey: ["ranking", tripId],
    queryFn: () => rpc<Ranking>("rank_candidates", { trip_id: tripId }),
    enabled: catalog.length > 0,
  });

  // The lane, capped. A 431-card City Icons list and a 662-card "For your trip" are not
  // a shortlist to work through, they are a catalogue — and the deck deals them in score
  // order, so the strongest are all at the front and everything after about the first
  // page is diminishing returns. The cap is a *view* over the lane, never a filter on
  // the ranking: nothing is dropped, and pressing for more is one press.
  // A page of twenty that can actually be finished.
  //
  // "I think the deck shows more than 20" was real. `main_queue` excludes decided places
  // *server-side*, every decision invalidates the ranking, and so each refetch shifted
  // the list up — `slice(0, shown)` then handed back twenty fresh cards, forever. The
  // page could never end, which is also why the end-of-deck panel offering the other
  // lanes was effectively unreachable.
  //
  // The window therefore shrinks by what has been decided out of it. Derived rather than
  // held in an effect, so the very first render already deals a full page: seeding the
  // page from `useEffect` left the first paint — and every static render — with no cards
  // at all, which six tests caught immediately.
  const allEntries = ranking.data ? laneEntries(ranking.data, lane) : [];
  const entries = allEntries.slice(0, Math.max(0, shown - decidedHere));
  const laneRemaining = allEntries.length - entries.length;
  const dealMore = () => {
    setShown(LANE_PAGE);
    setDecidedHere(0);
  };
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
      // "Discovery result saved" beside "No places came back" is the app congratulating
      // itself for storing a failure. A run that found nothing is reported by the empty
      // state below and nowhere else.
      const found = (value.candidates?.data?.candidates ?? []).length;
      setFlash(found ? "discovery_saved" : "");
      setCardId("");
      await refreshReads();
    },
  });
  // "Build the plan" is the only moment the app is told the choosing is over, so it is
  // what unlocks Check trip facts and Build the plan in the sidebar. Recorded server-side
  // rather than in `localStorage`: a journey stage that relocks on another machine is not
  // a journey stage. Navigation happens either way — a trip that cannot record the mark
  // must not be trapped on this screen by it.
  const finishChoosing = useMutation({
    mutationFn: () => rpc<unknown>("confirm_places_selection", { trip_id: tripId }),
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: ["journey", tripId] });
      navigate(`/trips/${tripId}/optimize`);
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
    mutationFn: (placeId?: string) =>
      rpc<null>("clear_candidate_choice", { trip_id: tripId, place_id: placeId ?? selectedId }),
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

  // "Image loading very slow" was mostly not the network: a card showed a button
  // asking the owner to fetch its own description, one place at a time, and the
  // photo could not start until they pressed it. The queue is known in advance, so
  // the window ahead of the deck is fetched in one call while the current card is
  // being read. Free — Wikidata and Wikipedia, no key and no charge.
  const decided = new Set((choices.data ?? []).map((item) => item.place_id));
  // The selected lane, not `main_queue`: the deck deals from whichever lane is picked,
  // so prefetching the other one would warm cards nobody is about to see.
  const upcoming = [
    // The card being looked at right now comes first. Prefetching only the head of the
    // lane left the list view blank for any card chosen further down a 500-entry
    // select, which read as "the Wikipedia pictures do not work".
    ...(selectedId ? [selectedId] : []),
    ...entries
      .filter((item) => !decided.has(item.place_id))
      .slice(0, PREFETCH_AHEAD)
      .map((item) => item.place_id),
  ];
  useEffect(() => {
    // Never during a capture. The prefetch *writes* — it stores a summary per place —
    // so photographing this screen changed what the next photograph would show, and the
    // baseline gate reported 13% drift on a page nobody had edited. A capture has to
    // observe the app, not operate it.
    if (typeof document !== "undefined" && document.documentElement.dataset.capture) return;
    if (!summaries.data || fetchSummary.isPending) return;
    const wanted = upcoming.filter(
      (placeId) => !(placeId in summaries.data) && !asked.current.has(placeId),
    );
    if (!wanted.length) return;
    for (const placeId of wanted) asked.current.add(placeId);
    // Released again once the request settles. `asked` exists to stop the same place
    // being requested twice at once — it was doing double duty as a permanent tombstone,
    // so a place whose fetch **failed** was never asked for again and the only way to
    // get its picture was the manual button. Wikimedia answers HTTP 429 on a burst and
    // this screen prefetches in bursts, so that was not rare. A place that genuinely has
    // nothing still gets an empty record stored, which `summaries.data` then filters on,
    // so this retries real failures and not empty answers.
    fetchSummary.mutate(wanted, {
      onSettled: () => {
        for (const placeId of wanted) asked.current.delete(placeId);
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [upcoming.join(","), summaries.data, fetchSummary.isPending]);

  if (setup.isPending || discovery.isPending || choices.isPending) {
    return <p>{copy("loading", language)}</p>;
  }
  const readError = setup.error ?? discovery.error ?? choices.error;
  if (readError) return <p className="field-error">⚠ {errorText(readError, language)}</p>;

  const report = discovery.data?.report.data;
  const selectedChoices = (choices.data ?? []).filter((item) => CONSIDERED.has(item.action));
  // The card's own estimate, summed. It excludes travel, meals and rest by
  // definition, which is why the caption below says the planner adds those.
  const keptMinutes = selectedChoices.reduce(
    (total, item) => {
      const estimate = ranking.data?.cards[item.place_id]?.duration_estimate;
      return {
        min: total.min + (estimate?.minimum_minutes ?? 0),
        max: total.max + (estimate?.maximum_minutes ?? 0),
      };
    },
    { min: 0, max: 0 },
  );
  const shortestHours = Math.round(keptMinutes.min / 6) / 10;
  const longestHours = Math.round(keptMinutes.max / 6) / 10;
  // "Everything loaded", not "the request returned": discovery is followed by ranking,
  // and showing the deck between the two rearranged the screen twice.
  // Everything, not just the request that was pressed. Discovery is followed by
  // ranking and then by the free descriptions the cards are made of, and revealing the
  // screen between those stages showed a deck with no photographs that then rearranged
  // itself twice. The skeleton stood inside the `ranking.data` branch, so on a first
  // Discover -- no ranking yet -- it never rendered at all, which is exactly when it
  // was wanted.
  //
  // **It blanks only when there is nothing to show, and `fetchSummary` is not part of
  // it.** That prefetch fetches photographs for cards *further down the deck*; every
  // swipe invalidates the ranking, the new order changes which cards are coming up, and
  // so every swipe started one. Gating on it emptied the whole workspace -- deck, detail
  // panel and lane picker -- after each card, for work on places the owner had not
  // reached. Reported as the deck being broken, and it may as well have been: nobody can
  // work through 300 cards on a screen that clears itself between them. A photograph
  // arriving late lands in a fixed-size box and moves nothing, which is why it can be
  // allowed to arrive late.
  const busy =
    discover.isPending || (catalog.length > 0 && (!ranking.data || summaries.isPending));
  const basics = setup.data?.snapshot.data.trip_basics;
  const tripDays = daysBetween(basics?.start_date, basics?.end_date);
  // Numbered in the order they were kept, so the map's label and the list's label are
  // the same string and neither has to be read to understand the other. A place with no
  // coordinates simply has no pin — it is still on the shortlist.
  const nameFor = (found: (typeof catalog)[number]) =>
    placeName(mergeNames(found, summaries.data?.[found.place_id]?.names), language, found.name);
  const shortlistPlaces = mapPlaces(selectedChoices, catalog, nameFor);
  // The shortlist plus the card in front, so the focused pin always has one.
  const cardMapPlaces = shortlistPlaces.some((place) => place.place_id === selectedId)
    ? shortlistPlaces
    : [...shortlistPlaces, ...mapPlaces([{ place_id: selectedId }], catalog, nameFor)];
  // Is the free summary for *this* place still coming?
  //
  // Gating on the bare `fetchSummary.isPending` gated on the **prefetch**, which fetches
  // summaries for cards further down the deck — so while any batch was in flight, the
  // paid button on the open card was replaced by "Loading…" and could not be pressed.
  // Worse, it never recovered for a place the summaries query holds nothing for:
  // `!summaries.data?.[selectedId]` stays true forever, so every future prefetch hid the
  // button again. Reported as "some places can't click Load live gallery" — measured on
  // Sapporo City Museum, which has both a summary row and a photograph.
  //
  // This is the second time the shared prefetch has been mistaken for the card's own
  // request; the first blanked the whole workspace on every swipe.
  const summaryPendingForCard =
    fetchSummary.isPending &&
    (fetchSummary.variables ?? []).includes(selectedId) &&
    !summaries.data?.[selectedId];
  const paidAllowed = Boolean(detailsCost.data?.allowed && photosCost.data?.allowed);
  const paidEstimate = (detailsCost.data?.estimate_usd ?? 0) + (photosCost.data?.estimate_usd ?? 0);
  const paidCaption = copy("live_details_cost", language)
    .replace("{cost:.3f}", paidEstimate.toFixed(3))
    .replace("{count}", String(PHOTO_LIMIT));
  const mutationError = detailsCost.error ?? photosCost.error
    ?? discover.error ?? saveChoice.error ?? clearChoice.error ?? enrich.error;

  return (
    <section className="stage-card places-screen">
      {/* The shortlist tab floats, because it is a drawer you want to reach while
          swiping. "How this works" does not: it is read once, at the start, and pinning
          it to the same corner meant two unrelated controls fighting for one spot — the
          drawer sat on the tour button and its focus ring at 390px. Grouping them fixed
          the overlap and kept the wrong idea; the tour now sits with the page's own
          heading, which is where it is looked for. */}
      <button
        aria-controls="shortlist-pane"
        aria-expanded={shortlistOpen}
        className="shortlist-handle"
        onClick={() => setShortlistOpen(!shortlistOpen)}
        type="button"
      >
        {copy("your_shortlist", language)}
        <span className="shortlist-handle-count">{selectedChoices.length}</span>
      </button>
      <header className="money-head places-head">
        <div>
          <h1>{copy("discover_title", language)}</h1>
          <p>{copy("discover_help", language)}</p>
        </div>
        <PlacesTour language={language} tripId={tripId} />
      </header>
      <p className="setup-hint">{copy("osm_notice", language)}</p>
      {flash ? <p className="setup-flash" aria-live="polite">{copy(flash, language)}</p> : null}
      {mutationError ? (
        <p className="field-error" aria-live="polite">⚠ {errorText(mutationError, language)}</p>
      ) : null}

      {/* Find places is a *first* search, and pressing it again once places are found
          buys nothing: `discover_places` keys its cache on the destination, so the repeat
          either rebuilds the same catalogue from disk or spends another 30-90s of a free
          public service's Overpass budget on an answer already held. "Search again" is
          the deliberate re-run and stays. */}
      <div className="optimize-actions">
        <button
          className="setup-primary"
          disabled={Boolean(discovery.data) || discover.isPending}
          onClick={() => discover.mutate(false)}
          type="button"
        >
          {discover.isPending ? copy("discovering", language) : copy("discover", language)}
        </button>
        <button disabled={!discovery.data || discover.isPending} onClick={() => discover.mutate(true)} type="button">
          {copy("refresh", language)}
        </button>
      </div>
      {discovery.data && !discover.isPending ? (
        <p className="setup-hint">{copy("discover_done", language)}</p>
      ) : null}
      {!discovery.data ? <p className="setup-hint">{copy("ranking_wait", language)}</p> : null}

      {discovery.data && report ? (
        <>
          {setup.data && discovery.data.setup_sha256 !== setup.data.snapshot.sha256 ? (
            // A dead end until now: the warning said "discover again" and the only
            // button for it is labelled as a fresh search, which on a dense city is a
            // minute of Overpass and reads as losing your work. Nothing needs
            // re-searching — the provider cache is keyed on the destination alone, so
            // this rebuilds the run from disk in milliseconds and every `place_id`,
            // being a hash of name, coordinates and category, still matches the choices
            // already made. Without it a stale trip cannot even record a choice: the
            // server refuses with 409.
            <div className="money-note money-note-warn stale-setup">
              <b aria-hidden="true">⚠</b>
              <div>
                <p>{copy("stale_setup", language)}</p>
                <button
                  disabled={discover.isPending}
                  onClick={() => discover.mutate(false)}
                  type="button"
                >
                  {discover.isPending ? copy("relinking", language) : copy("relink_places", language)}
                </button>
              </div>
            </div>
          ) : null}
          {new Set(["unavailable", "error", "stale"]).has(discovery.data.status) ? (
            <p className="money-note money-note-warn"><b aria-hidden="true">⚠</b>{copy("provider_gap", language)}</p>
          ) : null}
          {/* The empty case had only that one warning to show for itself: the sentence
              explaining it sits inside the coverage report, which is collapsed, so a run
              that returned nothing looked like a screen with nothing on it. The map
              service's own words go here too — a transient gateway 504 and a genuinely
              unknown city need different reactions from the owner. */}
          {!catalog.length ? (
            <div className="catalog-empty">
              {/* `h2`: this sits directly under the page's `h1`, and an `h3` here made
                  the empty state look nested inside a section that does not exist. */}
              <h2>{copy("catalog_empty_title", language)}</h2>
              <p>{copy("catalog_empty_help", language)}</p>
              {/* One sentence in the app's voice, and the provider's own words folded
                  away behind it. `<urlopen error [Errno 61] Connection refused>` as the
                  headline makes the product look unfinished at its main conversion
                  point — but it is the thing worth quoting in a bug report, so it is
                  kept rather than swallowed. */}
              {report?.provider_error ? (
                <>
                  <p>{copy("discovery_unreachable", language)}</p>
                  <details className="catalog-empty-detail">
                    <summary>{copy("discovery_technical", language)}</summary>
                    <p className="setup-hint">{String(report.provider_error)}</p>
                  </details>
                </>
              ) : null}
              <button
                className="setup-primary"
                disabled={discover.isPending}
                onClick={() => discover.mutate(true)}
                type="button"
              >
                {discover.isPending ? copy("discovering", language) : copy("discover", language)}
              </button>
            </div>
          ) : null}
          <details
            className="places-coverage"
            onToggle={(event) => {
              if (event.currentTarget.open) setCoverageOpened(true);
            }}
          >
          <summary><h2 className="money-eyebrow">{copy("coverage", language)}</h2></summary>
          {coverageOpened ? (
          <>
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
                    {catalog.slice(0, catalogShown).map((item) => {
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
              {/* A native button and a slice, not a virtualiser. The count is always
                  on screen, so a truncated table can never be mistaken for the whole
                  catalogue — which is the only thing paging can get wrong here. */}
              {catalogShown < catalog.length ? (
                <div className="places-catalog-more">
                  <span className="setup-hint">
                    {copyFormat("showing_of", language, { shown: catalogShown, total: catalog.length })}
                  </span>
                  <button onClick={() => setCatalogShown((shown) => shown + CATALOG_PAGE)} type="button">
                    {copy("load_more", language)}
                  </button>
                </div>
              ) : null}
            </details>
          ) : <p>{copy("no_candidates", language)}</p>}
          {report.attribution && report.license_url ? (
            <a href={report.license_url} rel="noreferrer" target="_blank">{report.attribution} · {report.license}</a>
          ) : null}
          <details><summary>{copy("details", language)}</summary><pre className="places-json">{JSON.stringify(report, null, 2)}</pre></details>
          </>
          ) : null}
          </details>
        </>
      ) : null}

      {busy ? (
            <>
            <Thinking
              /* Discovery is two Overpass blocks and runs 30-90s; paced at the low end so
                 the lines are not still arriving after the places are. */
              expectSeconds={40}
              language={language}
              lines={["think_reading_setup", "think_searching", "think_dedup", "think_scoring", "think_lanes", "think_photos", "think_almost"]}
            />
            <div className="places-workspace" aria-busy="true">
              <div className="skeleton-card">
                <span className="skeleton skeleton-photo" />
                <span className="skeleton skeleton-line wide" />
                <span className="skeleton skeleton-line" />
                <span className="skeleton skeleton-line" />
                <span className="skeleton skeleton-line short" />
              </div>
              <div className="skeleton-card">
                <span className="skeleton skeleton-line wide" />
                <span className="skeleton skeleton-line" />
                <span className="skeleton skeleton-line" />
                <span className="skeleton skeleton-photo short" />
                <span className="skeleton skeleton-line" />
              </div>
            </div>
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
          {/* The lane picker drives both modes now. In deck mode it was hidden, so the
              deck always dealt from `main_queue` while the list opened on City Icons —
              and the queue's top 20 have no Wikidata id, so the deck showed twenty
              photo-less cards and the fix for that was a control you could not see.
              Buttons rather than a select: five lanes is a small enough set to show at
              once, and which lane you are in is then readable without opening anything. */}
          <div className="places-pickers">
            <div className="lane-tabs" role="group" aria-label={copy("lane", language)}>
              {LANES.map((value) => (
                <button
                  aria-pressed={lane === value}
                  className={`lane-tab${lane === value ? " active" : ""}`}
                  key={value}
                  onClick={() => pickLane(value)}
                  type="button"
                >
                  {copy(value, language)}
                  <span className="lane-tab-count">{laneEntries(ranking.data!, value).length}</span>
                </button>
              ))}
            </div>
            {mode === "list" && entries.length ? (
              <label className="optimize-variant">
                {copy("select_card", language)}
                <select value={selectedId} onChange={(event) => setCardId(event.target.value)}>
                  {entries.map((entry) => {
                    const item = catalog.find((value) => value.place_id === entry.place_id);
                    return <option key={entry.place_id} value={entry.place_id}>{item ? placeName(item, language, item.name) : entry.place_id} · {ranking.data!.cards[entry.place_id]?.total_score.toFixed(1)}/100</option>;
                  })}
                </select>
              </label>
            ) : null}
          </div>

          {/* A skeleton while anything is still arriving, rather than a half-built
              screen. Discovery is ~30-90s and ranking follows it, so the page used to
              sit with a stale deck under a spinning button and then rearrange itself
              twice as each query landed. It waits for both. */}
          {/* Deck left, detail right. The detail used to be a whole other mode reached
              from a button at the top, so reading about the card in front of you meant
              leaving the deck and finding it again. It follows the deck's own card now
              and owns no decision buttons — the deck is where deciding happens, and two
              sets of them under one card was the duplication reported earlier. */}
          <div className={mode === "deck" ? "places-workspace" : undefined} hidden={busy}>
          {mode === "deck" ? (
            <>
              <p className="setup-hint">{copy("deck_help", language)}</p>
              {/* The tab counts the whole lane and the deck deals a page of it, so
                  without this the two numbers look like a bug. */}
              {laneRemaining > 0 ? (
                <p className="setup-hint">
                  {copyFormat("lane_capped", language, {
                    shown: entries.length,
                    total: allEntries.length,
                  })}
                </p>
              ) : null}
              <PlaceDeck
                candidates={byId}
                choices={choices.data ?? []}
                entries={entries}
                language={language}
                onPendingChange={setCardPending}
                altNameOf={(placeId) => {
                  const found = catalog.find((item) => item.place_id === placeId);
                  if (!found) return null;
                  return placeAltName(
                    mergeNames(found, summaries.data?.[placeId]?.names),
                    language,
                  );
                }}
                nameOf={(placeId) => {
                  // `catalog` is already the normalized candidate list on this page.
                  // Merged with the Wikidata label, which is the only English name most
                  // of this catalogue has -- and which arrives only once descriptions
                  // have been loaded, so the heading gains it then rather than never.
                  const found = catalog.find((item) => item.place_id === placeId);
                  if (!found) return placeId;
                  return placeName(
                    mergeNames(found, summaries.data?.[placeId]?.names),
                    language,
                    found.name,
                  );
                }}
                onDecide={(placeId, action, reason) => {
                  // Counted here rather than derived from `choices`, because a decision
                  // made on the list view or on an earlier page is not a card taken out
                  // of *this* one.
                  setDecidedHere((current) => current + 1);
                  saveChoice.mutate({ action, reason, placeId });
                }}
                onCardChange={setCardId}
                onWantSummary={(placeId) => fetchSummary.mutate([placeId])}
                summaryLoading={fetchSummary.isPending && !summaries.data?.[selectedId]}
                lane={lane}
                laneRemaining={laneRemaining}
                lanes={LANES}
                onPickLane={(next) => pickLane(next as Lane)}
                onShowMore={dealMore}
                ranking={ranking.data}
                summaries={summaries.data ?? {}}
              />
            </>
          ) : null}
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
                const article = about?.text?.[language] ?? about?.text?.en ?? "";
                // A place with a QID but no article is the common case, not the edge —
                // Wikidata's own one-liner is what it has, and a phrase saying what the
                // place *is* beats the mechanism sentence the card falls back to.
                const shortDescription = about?.description?.[language] ?? about?.description?.en ?? "";
                const prose = article || shortDescription;
                const fromWikidata = !article && Boolean(shortDescription);
                const onlyEnglish = language === "th" && !about?.text?.th && Boolean(about?.text?.en);
                const asking = fetchSummary.isPending;
                // OpenStreetMap's own tag counts as a picture: a place with no article
                // still often carries one, and it costs no extra request.
                const photo = galleryFor(about, candidate)[0] ?? null;
                if (!prose && !photo) {
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
                          <button disabled={asking} onClick={() => fetchSummary.mutate([selectedId])} type="button">
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
                    {photo ? (
                      <img
                        alt={placeName(candidate, language, candidate.name)}
                        className="place-about-photo"
                        decoding="async"
                        loading="lazy"
                        src={photo}
                      />
                    ) : null}
                    <div className="place-about-text">
                      <h4>{copy("about_this_place", language)}</h4>
                      {prose ? <p>{prose}</p> : null}
                      {onlyEnglish ? <p className="setup-hint">{copy("description_thai_missing", language)}</p> : null}
                      <p className="setup-hint">
                        {fromWikidata
                          ? copy("wikidata_credit", language)
                          : about?.photos_are_nearby
                            ? copy("photo_is_nearby", language)
                            : copy("wikipedia_credit", language)}
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
              {/* Where *this* card is. Drawn against the rest of the shortlist, dimmed,
                  because a lone pin on an empty box has nowhere to be. */}
              {/* Gated on the shortlist before, so the very first card — when nothing
                  is kept yet — had no map at all, and one appeared only from the second
                  choice onward. The card's own place is enough to draw. */}
              <PlaceMap
                basemap={basemap.data ?? null}
                focusId={selectedId}
                headingLevel={4}
                outline={outline.data ?? null}
                tripId={tripId}
                language={language}
                places={cardMapPlaces}
                title={copy("card_map", language)}
                withKey={false}
              />
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
                  {/* Every review that came back, not the first two: the call is paid
                      for whether or not they are rendered, and five short opinions are
                      what the owner asked the money for. */}
                  {insight.reviews?.map((review, index) => <blockquote key={`${review.author}-${index}`}><p>{review.text}</p><footer>{review.author ?? copy("google_reviewer", language)}{review.rating != null ? ` · ${review.rating.toFixed(0)}/5` : ""}{review.published ? ` · ${review.published}` : ""}</footer></blockquote>)}
                  <p className="setup-hint">{copy("live_details_session_only", language)}</p>
                </div>
              ) : (
                // Held back while the *free* summary is still arriving: offering to spend
                // money on better pictures before the free ones have landed asks the owner
                // to pay for something they cannot yet see they already have.
                summaryPendingForCard ? (
                <div aria-busy="true" className="place-paid-action">
                  <p className="setup-hint">{copy("loading", language)}</p>
                </div>
              ) : (
                <div className="place-paid-action">
                  <p className="setup-hint">{detailsCost.isPending || photosCost.isPending ? copy("loading", language) : paidCaption}</p>
                  <button disabled={!paidAllowed || enrich.isPending} onClick={() => enrich.mutate()} type="button">{copy("load_live_details", language)}</button>
                </div>
              ))}

              {choice ? <p className="setup-hint">{copy("current_choice", language)}: {copy(choice.action, language)}{choice.reason ? ` · ${copyFrom("REJECTION_TEXT", choice.reason, language)}` : ""}</p> : null}
              <div className="place-choice-actions" hidden={mode === "deck"}>
                {CHOICES.map((action) => <button className={`choice-${action}`} key={action} onClick={() => saveChoice.mutate({ action })} type="button">{copy(action, language)}</button>)}
                <details><summary>{copy("not_for_trip", language)}</summary><label>{copy("rejection_reason", language)}<select value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value)}>{REJECTION_REASONS.map((reason) => <option key={reason} value={reason}>{copyFrom("REJECTION_TEXT", reason, language)}</option>)}</select></label><button onClick={() => saveChoice.mutate({ action: "not_for_trip", reason: rejectionReason === "null" ? null : rejectionReason })} type="button">{copy("not_for_trip", language)}</button></details>
                {choice ? <button onClick={() => clearChoice.mutate(undefined)} type="button">{copy("clear_choice", language)}</button> : null}
              </div>

              {/* Hidden while the card in front is still arriving. The panel describes
                  *that* card, so showing it first is the "decide on half the evidence"
                  problem the card gate exists to prevent, one element over. */}
              <details className="place-explanations" hidden={cardPending && mode === "deck"}>
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
          </div>
          {/* `WF-040`, placed here by the owner: the ranking depends on the places
              chosen above, so it belongs under the deck rather than beside the
              timetable on `/optimize`. Below the whole row, not inside it. */}
          {/* "Where to stay" moved to its own route, 2026-08-14. Under the deck it
              competed with several hundred cards and was reported as a section with no
              visible output. */}
        </>
      ) : null}

      {/* derives-from: element 18 .trip-summary-box as .shortlist. Deciding place after
          place with no running record of what had been kept was the reported gap: the
          deck consumed the queue and showed nothing for it.
          A drawer rather than a block at the foot of the page: while swiping, what you
          have kept is the thing you want to glance at without losing your place, and at
          the bottom of a long screen it was neither visible nor reachable. */}
      <section
        className={`shortlist${shortlistOpen ? " open" : ""}`}
        id="shortlist-pane"
        hidden={!shortlistOpen}
      >
        <div className="shortlist-head">
          <h2 className="money-eyebrow">{copy("your_shortlist", language)}</h2>
          <div className="shortlist-head-actions">
            <button
              className="setup-primary shortlist-build-btn"
              disabled={!selectedChoices.length || finishChoosing.isPending}
              onClick={() => finishChoosing.mutate()}
              type="button"
            >
              {copy("stage_optimize", language)} →
            </button>
            <button onClick={() => setShortlistOpen(false)} type="button">
              {copy("close", language)}
            </button>
          </div>
        </div>
        <p className="setup-hint">{copy("shortlist_help", language)}</p>
        {selectedChoices.length ? (
          <>
            {CHOICES.map((action) => {
              const kept = selectedChoices.filter((item) => item.action === action);
              if (!kept.length) return null;
              return (
                <div className="shortlist-group" key={action}>
                  <span className={`money-tag choice-${action}`}>
                    {copy(action, language)} · {kept.length}
                  </span>
                  <ul>
                    {kept.map((item) => {
                      const found = catalog.find((value) => value.place_id === item.place_id);
                      return (
                        <li key={item.place_id}>
                          <span>
                            {found
                              ? placeName(
                                  mergeNames(found, summaries.data?.[item.place_id]?.names),
                                  language,
                                  found.name,
                                )
                              : item.place_id}
                          </span>
                          {/* Changing your mind was impossible: the list was read-only,
                              and the only way to move a place was to find its card
                              again in a lane of hundreds. */}
                          <span className="shortlist-edit">
                            <select
                              aria-label={copy("change_choice", language)}
                              onChange={(event) =>
                                saveChoice.mutate({
                                  action: event.target.value,
                                  placeId: item.place_id,
                                })
                              }
                              value={item.action}
                            >
                              {CHOICES.map((value) => (
                                <option key={value} value={value}>
                                  {copy(value, language)}
                                </option>
                              ))}
                            </select>
                            <button
                              onClick={() => clearChoice.mutate(item.place_id)}
                              title={copy("clear_choice", language)}
                              type="button"
                            >
                              ×
                            </button>
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}

            {/* Totals only, and labelled an estimate. Dividing them into days would
                mean holding a copy of the optimizer's pacing constants here, and two
                copies of a number is how the screen and the workbook start
                disagreeing. */}
            <PlaceMap
              basemap={basemap.data ?? null}
              language={language}
              outline={outline.data ?? null}
              places={shortlistPlaces}
              tripId={tripId}
              title={copy("shortlist_map", language)}
            />
            <h3>{copy("draft_shape", language)}</h3>
            <div className="money-tiles">
              <div className="money-tile">
                <span className="money-tile-label">{copy("kept_places", language)}</span>
                <strong className="money-tile-value">{selectedChoices.length}</strong>
              </div>
              <div className="money-tile">
                <span className="money-tile-label">{copy("visiting_time", language)}</span>
                <strong className="money-tile-value">
                  {shortestHours}–{longestHours} {copy("hours_short", language)}
                </strong>
              </div>
              <div className="money-tile">
                <span className="money-tile-label">{copy("days_available", language)}</span>
                <strong className="money-tile-value">
                  {tripDays ?? "—"}
                </strong>
                {tripDays === null ? (
                  <span className="money-tile-hint">{copy("days_unknown", language)}</span>
                ) : null}
              </div>
            </div>
            <p className="setup-hint">{copy("draft_shape_help", language)}</p>
          </>
        ) : (
          <p className="setup-hint">{copy("shortlist_empty", language)}</p>
        )}
      </section>

      <div className="optimize-actions">
        <button className="setup-primary" disabled={!selectedChoices.length || finishChoosing.isPending} onClick={() => finishChoosing.mutate()} type="button">{copy("stage_optimize", language)}</button>
      </div>
      {!selectedChoices.length ? <p className="setup-hint">{copyFrom("OPTIMIZER_CODE_TEXT", "no_places_chosen", language)}</p> : null}
    </section>
  );
}
