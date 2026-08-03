import { Compass, Languages, SunMoon } from "lucide-react";
import { NavLink, Outlet, useParams } from "react-router";

import { copy } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";

const sections = [
  { key: "section_build", stages: ["setup", "places", "evidence", "optimize"] },
  { key: "section_use", stages: ["itinerary", "readiness", "costs", "split", "revise"] },
] as const;

export function AppShell() {
  const { tripId = "" } = useParams();
  const { language, setLanguage } = useLanguage();

  function toggleTheme() {
    const root = document.documentElement;
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
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
                to={`/trips/${tripId}/${stage}`}
              >
                {copy(`stage_${stage}`, language)}
              </NavLink>
            ))}
          </nav>
        ))}
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
