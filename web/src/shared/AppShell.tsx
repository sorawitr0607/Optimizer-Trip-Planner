import { useQuery } from "@tanstack/react-query";
import { Check, Compass, Languages, Lock, Menu, Plus, SunMoon } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router";

import { rpc, type Journey, type Trip } from "../api/client";
import { copy, copyFormat } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { useTheme } from "./ThemeProvider";
import { DeleteTrip } from "./DeleteTrip";
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
  { key: "section_build", stages: ["setup", "places", "optimize"] },
  { key: "section_use", stages: ["itinerary", "costs", "split"] },
  { key: "section_check", stages: ["evidence", "readiness", "revise"] },
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

  return (
    <div className="app-shell">
      {/* derives-from: element 17 .sidebar as .sidebar. Auto-Bill has no phone precedent
          because its sidebar was informational; a nine-item nav list sitting
          above the content on every phone screen is why this collapse exists. */}
      <button
        aria-controls="stage-nav"
        aria-expanded={navOpen}
        className="nav-toggle"
        onClick={() => setNavOpen((open) => !open)}
        type="button"
      >
        <Menu aria-hidden="true" size={18} />
        {trip?.name || copy("stage_setup", language)}
      </button>
      <aside className={`sidebar${navOpen ? " open" : ""}`} id="stage-nav">
        <NavLink className="brand" to="/trips">
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
              const spoken =
                status.state === "locked"
                  ? copyFormat("stage_state_locked", language, {
                      stage: copy(`stage_${status.blockedBy}`, language),
                    })
                  : status.state === "available"
                    ? ""
                    : copy(`stage_state_${status.state}`, language);
              return (
                <NavLink
                  aria-label={spoken ? `${name} — ${spoken}` : undefined}
                  // A locked stage points at `#`, which resolves to whatever page you
                  // are on — so `isActive` was true for every locked link and they were
                  // highlighted as if they were the screen you were reading.
                  className={({ isActive }) =>
                    `stage-link${isActive && status.state !== "locked" ? " active" : ""}`
                  }
                  data-state={status.state}
                  key={stageRoute}
                  onClick={(event) => {
                    if (status.state === "locked") {
                      event.preventDefault();
                      return;
                    }
                    setNavOpen(false);
                  }}
                  aria-disabled={status.state === "locked"}
                  to={status.state === "locked" ? "#" : `/trips/${tripId}/${stageRoute}`}
                >
                  <span className="stage-link-name">{name}</span>
                  {status.state === "complete" ? <Check aria-hidden="true" size={14} /> : null}
                  {status.state === "locked" ? <Lock aria-hidden="true" size={13} /> : null}
                  {status.state === "next" ? (
                    <span className="stage-link-badge">{copy("stage_state_next", language)}</span>
                  ) : null}
                  {/* Named before navigation rather than after it. A locked stage is
                      still a link — `<StageGate>` explains in place and a completed
                      stage stays open for revision — but the prerequisite is on
                      screen now instead of being learned by clicking. */}
                  {status.state === "locked" ? (
                    <small className="stage-link-blocker">
                      {copyFormat("stage_state_locked", language, {
                        stage: copy(`stage_${status.blockedBy}`, language),
                      })}
                    </small>
                  ) : null}
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
          <NavLink className="trip-new" onClick={() => setNavOpen(false)} to="/trips">
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
      </aside>
      <main className="stage-main">
        <Outlet />
      </main>
    </div>
  );
}
