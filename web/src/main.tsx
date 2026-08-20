import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";

import "../../tokens.css";
import "./shell.css";
import type { Language } from "./i18n/copy";
import { LanguageProvider } from "./i18n/LanguageProvider";
import { routes } from "./routes";
import { ThemeProvider } from "./shared/ThemeProvider";

const router = createBrowserRouter(routes);
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

/**
 * A capture seam for the 56 screen baselines, and nothing more.
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
  // Marks capture mode for anything that must not appear in a baseline. The places
  // tour is first-visit-only and a fresh Chrome profile is always a first visit, so
  // without this every capture would photograph the overlay instead of the screen.
  document.documentElement.dataset.capture = "1";
  // Capture mode also freezes transitions. The body fades background and colour
  // over 300ms, and a screenshot taken part-way through that fade differs from
  // one taken after it by a few shades across the whole viewport — which reads
  // as a 49% pixel change and fails the baseline gate for no real reason.
  const frozen = document.createElement("style");
  // And freezes the values that move on their own. `/itinerary` prints the export
  // timestamp and `/evidence` the running paid-usage ledger, so re-photographing an
  // unchanged app produced eight differing images -- a gate that fails without a code
  // change teaches everyone to ignore it. `font-size: 0` collapses the real value to
  // no width and `::after` supplies a fixed-width stand-in, so the layout around it is
  // still compared exactly; only the digits are held. Nothing outside capture mode is
  // affected, and every other pixel on both screens is still diffed.
  frozen.textContent =
    "*,*::before,*::after{transition:none!important;animation:none!important}" +
    "[data-volatile]{font-size:0!important}" +
    "[data-volatile]::after{content:'\\2014\\2014';font-size:1rem;font-family:var(--font-mono)}" +
    // A remote photograph is third-party pixels over a network: Wikimedia re-encodes a
    // thumbnail and the same image comes back subtly different, which failed the gate
    // at peak 28 with nothing in this repo changed. `opacity: 0` blanks the pixels and
    // keeps the element laid out at its real size, so a layout change still fails —
    // which is the part of a photograph this gate can meaningfully own.
    ".place-deck-photo img,.place-about-photo,.place-insight img{opacity:0!important}";
  document.head.append(frozen);
  // The one state the capture flag *hides*, asked for back on one screen. The tour
  // is first-visit-only and a fresh Chrome profile is always a first visit, so it
  // has to be suppressed by default or every image photographs it — which left the
  // app's one modal with no visual regression cover at all.
  if (parameters.get("baseline_tour") === "open") {
    document.documentElement.dataset.captureTour = "1";
  }
}
// Passed only when the seam asked for it. Handing `LanguageProvider` a default of
// "en" on every load would make the capture parameter indistinguishable from no
// parameter, and the owner's stored choice would lose to it on every visit.
const requested = parameters.get("baseline_language");
const language: Language | undefined =
  requested === "th" ? "th" : requested === "en" ? "en" : undefined;

// Vercel Speed Insights, without `@vercel/speed-insights`.
//
// That package is a wrapper whose whole job is to inject the one script below, and
// `WF-026` fixes the web runtime at six dependencies -- the rule GSAP was refused
// under. A seventh for a file the platform already serves from this origin is the
// cost with none of the benefit. `WF-034` is satisfied for the same reason: the
// path is same-origin, not a remote host.
//
// What the wrapper does that this does not is report the route *pattern*, so
// `/trips/:tripId/places` is one page rather than one per trip. Left as raw paths
// on purpose: this is a personal planner with a handful of trips, and the
// cardinality that would cost a real product nothing here.
//
// Production only. The script is served by the deployment, so asking for it from
// `vite dev` is a guaranteed 404 in the console. Never during a capture, for the
// reason the forecast and the summaries prefetch are also skipped: a capture
// observes the app rather than operating it, and this one reports.
if (import.meta.env.PROD && !document.documentElement.dataset.capture) {
  const insights = document.createElement("script");
  insights.src = "/_vercel/speed-insights/script.js";
  insights.defer = true;
  document.head.append(insights);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <LanguageProvider initial={language}>
          <RouterProvider router={router} />
        </LanguageProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
