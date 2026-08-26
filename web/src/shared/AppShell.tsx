import { useQuery } from "@tanstack/react-query";
import { Check, Compass, Languages, Lock, Plus, SunMoon, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router";

import { rpc, type Journey, type Trip } from "../api/client";
import { copy, copyFormat } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { StageTabs } from "./StageTabs";
import { useTheme } from "./ThemeProvider";
import { PHONE, useMediaQuery } from "./useMediaQuery";
import { DeleteTrip } from "./DeleteTrip";
import { Recovery } from "./Recovery";
import { stageStatus, type StageRoute } from "./stages";

/**
 * Three sections, not two.
 *
 * `evidence` and `revise` are not steps you walk through — they are things you go and
 * check or change when something is wrong — and `readiness` is a board you keep rather
 * than a stage you finish. Sitting them in "Build" and "Use" put a detour in the middle
 * of the path and a to-do list among the outputs, so the sidebar read as nine sequential
 * stages when only six are. The order within each section is unchanged.
 */
const sections = [
  { key: "section_build", stages: ["setup", "places", "stay", "optimize"], completable: true },
  { key: "section_use", stages: ["itinerary", "costs", "split"], completable: true },
  // `completable: false`, so no tick. These three are not steps you finish — evidence is
  // checked when something looks wrong, the readiness board is kept rather than
  // completed, and a revision is made whenever the plan needs one. A tick on any of them
  // claims a thing is behind you that you may well come back to twice more, which is the
  // same reason they were moved out of "Build" and "Use" in the first place.
  { key: "section_check", stages: ["evidence", "readiness", "revise"], completable: false },
] as const;

/**
 * The destination drives the accent (deviation D6). `tokens.css` already carries
 * the country-to-accent mapping; nothing set the attribute until now. An unknown
 * country simply matches no rule and keeps the house red, which is D3, so this
 * needs no validation against the mapping.
 */
function countrySlug(destination: string | undefined): string {
  const country = (destination ?? "").split(",").pop()?.trim() ?? "";
  return country.toLowerCase().replace(/\s+/g, "-");
}

export function AppShell() {
  const { tripId = "" } = useParams();
  const { language, setLanguage } = useLanguage();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const sheetDialog = useRef<HTMLDialogElement>(null);
  // Which navigation surface exists at all -- see `useMediaQuery`.
  const phone = useMediaQuery(PHONE);

  // The sheet is a native dialog, so the browser owns the hard parts: focus moves
  // into it on open and back to the More button on close, and Escape fires
  // `cancel`, which the dialog element handles below. React only states intent.
  useEffect(() => {
    const node = sheetDialog.current;
    if (!node) return;
    if (navOpen && !node.open) node.showModal();
    if (!navOpen && node.open) node.close();
  }, [navOpen]);

  // Every route change starts at the top.
  //
  // The browser keeps the scroll offset across a client-side navigation, because as far
  // as it is concerned nothing was navigated — so leaving a long itinerary half way down
  // and pressing "Costs" opened Costs half way down too, at whatever the previous screen
  // happened to be tall enough to allow. On the stage screens, which run to several
  // thousand pixels, that lands on the middle of a page whose heading was never seen.
  //
  // Keyed on `pathname` only, deliberately: `/itinerary?view=timeline` and the day
  // stepper both change the search string many times on one screen, and yanking the page
  // to the top under someone reading a timetable is worse than the problem being fixed.
  // An in-page `#anchor` is left alone for the same reason.
  useEffect(() => {
    if (location.hash) return;
    window.scrollTo({ top: 0, left: 0 });
  }, [location.pathname, location.hash]);

  const trips = useQuery({ queryKey: ["trips"], queryFn: () => rpc<Trip[]>("list_trips") });
  const trip = trips.data?.find((item) => item.trip_id === tripId);

  // The same read `<StageGate>` makes, under the same key, so TanStack serves both
  // from one response and the sidebar cannot describe a different journey from the
  // one the gate is enforcing.
  const journey = useQuery({
    queryKey: ["journey", tripId],
    queryFn: () => rpc<Journey>("journey", { trip_id: tripId }),
    enabled: Boolean(tripId),
  });

  useEffect(() => {
    const root = document.documentElement;
    const slug = countrySlug(trip?.destination);
    if (slug) root.dataset.country = slug;
    else delete root.dataset.country;
  }, [trip?.destination]);

  // A route-specific title, because every tab and every history entry used to read
  // "Optimizer Trip Planner" — nine screens across however many trips, all spelled
  // the same, so neither the tab strip nor a back-button long-press could tell them
  // apart. Most specific first: the stage names the screen, the trip names which one.
  const stage = location.pathname.split("/").pop() ?? "";
  useEffect(() => {
    const parts = [
      stage ? copy(`stage_${stage}`, language) : "",
      trip?.destination ?? trip?.name ?? "",
      copy("app_name", language),
    ].filter(Boolean);
    document.title = parts.join(" · ");
  }, [stage, trip?.destination, trip?.name, language]);

  // Switching trips resumes each at its own stage, so the selector reads the
  // journey rather than guessing a route.
  async function switchTrip(nextId: string) {
    setNavOpen(false);
    if (!nextId) return;
    try {
      const next = await rpc<Journey>("journey", { trip_id: nextId });
      navigate(`/trips/${nextId}/${next.next}`);
    } catch {
      navigate(`/trips/${nextId}/setup`);
    }
  }

  // The trip is checked before its stages are drawn. A deleted, mistyped or stale-bookmark
  // id rendered the whole setup wizard and only admitted `unknown_trip` after the owner
  // had re-entered their answers into a trip that does not exist. `trips` is already
  // fetched here for the switcher, so this costs no request.
  if (trips.data && tripId && !trip) {
    return (
      <Recovery
        body={copy("unknown_trip_body", language)}
        detail={tripId}
        title={copy("unknown_trip_title", language)}
      />
    );
  }

  // The one navigation body, drawn twice: as the desktop sidebar and as the
  // phone sheet. Extracted so the two surfaces cannot drift — they are the
  // same stages, the same states, the same controls by construction.
  const sidebarBody = (
    <>
        {/* `end`, or `/trips` matches every `/trips/:id/*` descendant and both of these
            links claim `aria-current="page"` on every stage screen. Three elements
            claiming to be the current page is three contradictory answers to a screen
            reader's only question about where it is. */}
        <NavLink className="brand" end to="/trips">
          <Compass aria-hidden="true" size={22} />
          <span>{copy("app_name", language)}</span>
        </NavLink>
        {sections.map((section) => (
          <nav aria-label={copy(section.key, language)} key={section.key}>
            {/* Styled like a heading, and deliberately not one. These sat on every
                screen *before* the page's own `<h1>`, so a screen reader walking the
                outline met "Build the trip" and "Use the trip" as top-level sections
                of a document whose real title it had not reached yet. The `<nav>`
                already carries the same words as its accessible name, so nothing is
                lost by demoting the visible copy. */}
            <p className="nav-section">{copy(section.key, language)}</p>
            {section.stages.map((stageRoute) => {
              const status = stageStatus(journey.data, stageRoute as StageRoute);
              const name = copy(`stage_${stageRoute}`, language);
              // The state is a word before it is a mark. A tick and a padlock are
              // decoration that a screen reader would read as nothing at all, and
              // colour alone cannot carry a state — so the sentence goes in the
              // accessible name and the glyph is `aria-hidden`.
              const complete = status.state === "complete" && section.completable;
              const spoken =
                status.state === "locked"
                  ? copyFormat("stage_state_locked", language, {
                      stage: copy(`stage_${status.blockedBy}`, language),
                    })
                  : status.state === "available" || (status.state === "complete" && !complete)
                    ? ""
                    : copy(`stage_state_${status.state}`, language);
              // A locked stage is not a link. It pointed at `#`, which resolves to
              // whatever page you are on — so it was announced as a link to the page
              // already open *and* claimed `aria-current="page"` alongside the real
              // one. Eight elements claimed to be current on a fresh Places route.
              // `<span>` states the prerequisite instead of offering a destination.
              const body = (
                <>
                  <span className="stage-link-name">{name}</span>
                  {complete ? <Check aria-hidden="true" size={14} /> : null}
                  {status.state === "locked" ? <Lock aria-hidden="true" size={13} /> : null}
                  {status.state === "next" ? (
                    <span className="stage-link-badge">{copy("stage_state_next", language)}</span>
                  ) : null}
                  {/* Named before navigation rather than after it. */}
                  {status.state === "locked" ? (
                    <small className="stage-link-blocker">
                      {copyFormat("stage_state_locked", language, {
                        stage: copy(`stage_${status.blockedBy}`, language),
                      })}
                    </small>
                  ) : null}
                </>
              );
              if (status.state === "locked") {
                return (
                  <span
                    aria-disabled="true"
                    aria-label={spoken ? `${name} — ${spoken}` : undefined}
                    className="stage-link"
                    data-state="locked"
                    key={stageRoute}
                  >
                    {body}
                  </span>
                );
              }
              return (
                <NavLink
                  aria-label={spoken ? `${name} — ${spoken}` : undefined}
                  className={({ isActive }) => `stage-link${isActive ? " active" : ""}`}
                  data-state={status.state}
                  key={stageRoute}
                  onClick={() => setNavOpen(false)}
                  to={`/trips/${tripId}/${stageRoute}`}
                >
                  {body}
                </NavLink>
              );
            })}
          </nav>
        ))}

        {/* The trip context sits directly under the stages and the language
            control at the foot -- today's exact information architecture. */}
        <div className="trip-context">
          <label>
            {copy("resume", language)}
            <select onChange={(event) => switchTrip(event.target.value)} value={tripId}>
              {(trips.data ?? []).map((item) => (
                <option key={item.trip_id} value={item.trip_id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          {trip ? <span className="trip-destination">{trip.destination}</span> : null}
          <NavLink className="trip-new" end onClick={() => setNavOpen(false)} to="/trips">
            <Plus aria-hidden="true" size={15} /> {copy("new_trip_slot", language)}
          </NavLink>
          {/* The active slot, deletable from wherever you are. It first landed only on
              the landing page and the report was that the slot in front of you all day
              still could not be removed. Deleting the trip being looked at cannot
              re-render this page, so it leaves for the slot list. */}
          {trip ? (
            <DeleteTrip compact onDeleted={() => navigate("/trips")} trip={trip} />
          ) : null}
        </div>

        {/* Which build is on screen. See the note in `vite.config.ts`: six rounds of
            testing were spent on fixes that were already shipped and simply not loaded,
            and nothing about behaviour is worth discussing until this matches the build
            that was just made. */}
        <p className="build-stamp" data-volatile="build" title="Build">
          build {__BUILD_ID__}
        </p>
        <div className="sidebar-controls">
          {/* Named for what it switches to. "EN / ไทย" states the pair and not the
              action, so neither the current language nor the outcome was announced. */}
          <button
            aria-label={copy("switch_language", language)}
            onClick={() => setLanguage(language === "en" ? "th" : "en")}
            type="button"
          >
            <Languages aria-hidden="true" size={17} /> {language === "en" ? "ไทย" : "English"}
          </button>
          {/* Says what pressing it does, not what is currently on. "Theme" left a
              screen-reader user with no way to know either the state or the outcome. */}
          <button onClick={toggleTheme} type="button">
            <SunMoon aria-hidden="true" size={17} />{" "}
            {copy(theme === "dark" ? "theme_to_light" : "theme_to_dark", language)}
          </button>
        </div>
    </>
  );

  return (
    <div className="app-shell">
      {/* Context, in the top zone where a phone expects to find it — which trip is
          open and where it goes. It replaced a hamburger that carried the trip name:
          the name was the only thing that button said, while what it actually did was
          navigate, so it answered "which trip" in the place a reader looks for "where
          am I" and hid all ten destinations behind itself. Navigation now lives in
          `<StageTabs>` at the bottom, and this states the trip and nothing else.
          derives-from: element 17 .sidebar-title as .trip-bar */}
      {phone ? (
        <header className="trip-bar">
          <Compass aria-hidden="true" size={17} />
          <span className="trip-bar-name">{trip?.name || copy("app_name", language)}</span>
          {trip ? <span className="trip-bar-where">{trip.destination}</span> : null}
        </header>
      ) : null}
      {/* On a phone the sidebar *is* the More sheet, opened as a native `<dialog>` —
          so the tab bar and the full stage list are never both claiming the page, and
          the sheet gets for free what the hand-rolled fixed panel never had: focus
          moved in on open, returned to the More button on close, and Escape. */}
      {/* derives-from: element 17 .sidebar as .sidebar. The citation used to sit on the
          phone hamburger, which this change deleted — taking the sidebar's parity pair
          with it. It belongs on the sidebar itself. */}
      {phone ? null : (
        <aside className="sidebar" id="stage-nav">
          {sidebarBody}
        </aside>
      )}
      {phone ? (
        <dialog
          aria-label={copy("tab_more", language)}
          className="sidebar sheet-dialog"
          id="stage-nav"
          onCancel={(event) => {
            // Chrome closes on Escape before React sees a usable transition, so
            // the same state-led path serves Escape, the close button and a
            // stage link.
            event.preventDefault();
            setNavOpen(false);
          }}
          onClose={() => setNavOpen(false)}
          ref={sheetDialog}
        >
          <button className="sheet-close" onClick={() => setNavOpen(false)} type="button">
            <X aria-hidden="true" size={18} /> {copy("nav_close", language)}
          </button>
          {sidebarBody}
        </dialog>
      ) : null}
      <main className="stage-main">
        <Outlet />
      </main>
      {/* Mounted while the sheet is open too: the More button keeps its DOM
          identity, which is what the dialog returns focus to on close. The
          sheet covers it, so nothing double-taps through the backdrop. */}
      {phone ? (
        <StageTabs
          journey={journey.data}
          language={language}
          navOpen={navOpen}
          onMore={() => setNavOpen(true)}
          stage={stage}
          tripId={tripId}
        />
      ) : null}
    </div>
  );
}
