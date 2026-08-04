import { useQuery } from "@tanstack/react-query";
import { Compass, Languages, Menu, Plus, SunMoon } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router";

import { rpc, type Journey, type Trip } from "../api/client";
import { copy } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";

const sections = [
  { key: "section_build", stages: ["setup", "places", "evidence", "optimize"] },
  { key: "section_use", stages: ["itinerary", "readiness", "costs", "split", "revise"] },
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
  const navigate = useNavigate();
  const [navOpen, setNavOpen] = useState(false);

  const trips = useQuery({ queryKey: ["trips"], queryFn: () => rpc<Trip[]>("list_trips") });
  const trip = trips.data?.find((item) => item.trip_id === tripId);

  useEffect(() => {
    const root = document.documentElement;
    const slug = countrySlug(trip?.destination);
    if (slug) root.dataset.country = slug;
    else delete root.dataset.country;
  }, [trip?.destination]);

  function toggleTheme() {
    const root = document.documentElement;
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
  }

  // Switching trips resumes each at its own stage, so the selector reads the
  // journey rather than guessing a route.
  async function switchTrip(nextId: string) {
    setNavOpen(false);
    if (!nextId) return;
    try {
      const journey = await rpc<Journey>("journey", { trip_id: nextId });
      navigate(`/trips/${nextId}/${journey.next}`);
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
          <span>Optimizer Trip Planner</span>
        </NavLink>
        {sections.map((section) => (
          <nav aria-label={copy(section.key, language)} key={section.key}>
            <h2>{copy(section.key, language)}</h2>
            {section.stages.map((stage) => (
              <NavLink
                className={({ isActive }) => `stage-link${isActive ? " active" : ""}`}
                key={stage}
                onClick={() => setNavOpen(false)}
                to={`/trips/${tripId}/${stage}`}
              >
                {copy(`stage_${stage}`, language)}
              </NavLink>
            ))}
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
        </div>

        <div className="sidebar-controls">
          <button onClick={() => setLanguage(language === "en" ? "th" : "en")} type="button">
            <Languages aria-hidden="true" size={17} /> EN / ไทย
          </button>
          <button onClick={toggleTheme} type="button">
            <SunMoon aria-hidden="true" size={17} /> {copy("theme", language)}
          </button>
        </div>
      </aside>
      <main className="stage-main">
        <Outlet />
      </main>
    </div>
  );
}
