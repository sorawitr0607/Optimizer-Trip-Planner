import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";

import "../../tokens.css";
import "./shell.css";
import type { Language } from "./i18n/copy";
import { LanguageProvider } from "./i18n/LanguageProvider";
import { routes } from "./routes";

const router = createBrowserRouter(routes);
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

/**
 * A capture seam for the 36 screen baselines, and nothing more.
 *
 * Headless Chrome cannot click the theme and language controls, so it needs a way
 * to load a route already in one of the four states. These two parameters set
 * only what those controls already set, read nothing, and write nothing — so the
 * baseline is a state the app can genuinely be in, which is the whole point of
 * photographing it.
 */
const parameters = new URLSearchParams(window.location.search);
const theme = parameters.get("baseline_theme");
if (theme === "dark" || theme === "light") {
  document.documentElement.dataset.theme = theme;
  // Capture mode also freezes transitions. The body fades background and colour
  // over 300ms, and a screenshot taken part-way through that fade differs from
  // one taken after it by a few shades across the whole viewport — which reads
  // as a 49% pixel change and fails the baseline gate for no real reason.
  const frozen = document.createElement("style");
  frozen.textContent =
    "*,*::before,*::after{transition:none!important;animation:none!important}";
  document.head.append(frozen);
}
const requested = parameters.get("baseline_language");
const language: Language = requested === "th" ? "th" : "en";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <LanguageProvider initial={language}>
        <RouterProvider router={router} />
      </LanguageProvider>
    </QueryClientProvider>
  </StrictMode>,
);
