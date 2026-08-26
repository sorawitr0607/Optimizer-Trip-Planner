import { CalendarDays, ClipboardCheck, Hammer, Lock, MoreHorizontal, Wallet } from "lucide-react";
import { Link } from "react-router";

import type { Journey } from "../api/client";
import { copy } from "../i18n/copy";
import type { Language } from "../i18n/copy";
import { stageStatus, type StageRoute } from "./stages";

/**
 * The phone's navigation, and the reason the sidebar is not it.
 *
 * Ten stage links in three sections is a fine desktop sidebar and a poor phone
 * menu: collapsed behind a hamburger at the top of the screen, every destination
 * in the app was two taps away, both of them out of thumb reach, and nothing on
 * screen answered "where can I go next" until you opened it. This puts the four
 * places worth reaching directly into the thumb zone and leaves the full ten —
 * with their locks, ticks and next-badge — one tap away under More.
 *
 * Four, not ten, because a tab bar is read at a glance rather than studied. The
 * grouping is the app's own: Build is the sequence you walk once, Itinerary is
 * what it produces, Money is what it costs and what was actually paid, and Checks
 * is the board you keep. Nothing here invents a route — every tab lands on one of
 * the ten, and the sheet still lists all of them.
 */

/** The stages of the Build section, in the order the sidebar shows them. */
const BUILD: readonly StageRoute[] = ["setup", "places", "stay", "optimize"];

/**
 * Where Build points today.
 *
 * `journey.next` is the app's own answer to "resume here" — the same one `/`
 * redirects to — so the tab uses it rather than deriving a second opinion that
 * could disagree with the sidebar's NEXT badge.
 *
 * It is only usable while it names a build stage. Once everything is finished
 * `next` falls back to `itinerary`, which would make the Build tab quietly stop
 * being about building, so that case lands on `optimize`: the build screen you
 * return to in order to rebuild.
 *
 * Not "the first stage that is not `complete`" — the shape this started as. Only
 * the five gate keys report `done`, and `stay` is not one of them, so it is never
 * `complete` and the tab pinned itself to `/stay` forever once setup and places
 * were behind it. `stages.ts` says as much; the test now says it too.
 */
function buildTarget(journey: Journey | undefined): StageRoute {
  if (!journey) return "setup";
  const next = journey.next as StageRoute;
  return BUILD.includes(next) ? next : "optimize";
}

interface Tab {
  readonly route: StageRoute;
  readonly label: string;
  readonly Icon: typeof Hammer;
  /** Routes this tab is considered active for, beyond its own. */
  readonly covers: readonly StageRoute[];
}

export function StageTabs({
  journey,
  language,
  navOpen = false,
  onMore,
  stage,
  tripId,
}: {
  journey: Journey | undefined;
  language: Language;
  /** Whether the More sheet this bar opens is currently showing. The button
   *  stays mounted underneath the sheet so the dialog has a focused element to
   *  return to on close; these attributes keep that invisible button honest. */
  navOpen?: boolean;
  onMore: () => void;
  /** The route segment currently open, so a tab can own a screen it does not link to. */
  stage: string;
  tripId: string;
}) {
  const tabs: readonly Tab[] = [
    {
      route: buildTarget(journey),
      label: copy("tab_build", language),
      Icon: Hammer,
      covers: BUILD,
    },
    { route: "itinerary", label: copy("tab_itinerary", language), Icon: CalendarDays, covers: [] },
    // Costs and Split are one question with two halves — what it should cost and
    // what it did — so they share a tab and Split is reached from the sheet.
    { route: "costs", label: copy("tab_money", language), Icon: Wallet, covers: ["split"] },
    {
      route: "readiness",
      label: copy("tab_checks", language),
      Icon: ClipboardCheck,
      covers: ["evidence", "revise"],
    },
  ];

  return (
    /* derives-from: element 22 .workspace-tabs as .stage-tabs. The donor's tab strip
       sat at the top of a two-screen app; this one is pinned to the bottom, because a
       phone's primary navigation belongs in the thumb zone and Auto-Bill had no phone
       precedent to preserve. No deviation number: the register D1–D10 is full and the
       parity diff compares radius, shadow, weight, transform and letter-spacing, none
       of which this moves. */
    <nav aria-label={copy("nav_all_screens", language)} className="stage-tabs">
      {tabs.map(({ route, label, Icon, covers }) => {
        const status = stageStatus(journey, route);
        // A tab is current when its own route is open or when one of the routes it
        // stands in for is. `NavLink`'s own matching cannot know that Split belongs
        // to Money, so the state is computed here and `aria-current` set explicitly
        // — still exactly one on the page, since the four sets do not overlap.
        const current = stage === route || covers.includes(stage as StageRoute);
        if (status.state === "locked") {
          return (
            /* derives-from: element 22 .tab-link as .stage-tab. A locked tab is not a
               link, for the reason the sidebar's locked stages are not either: an
               anchor to `#` resolves to the page already open and is announced as a
               link to it. */
            <span
              aria-disabled="true"
              className="stage-tab"
              data-state="locked"
              key={label}
            >
              <Lock aria-hidden="true" size={19} />
              <span className="stage-tab-label">{label}</span>
            </span>
          );
        }
        return (
          /* `Link`, not `NavLink`. NavLink derives `aria-current` from its own
             route match and overrides the prop, so the Money tab went silent on
             `/split` — the one case a tab has to speak for a route it does not
             link to. The state is computed above; this just renders it. */
          <Link
            aria-current={current ? "page" : undefined}
            className="stage-tab"
            data-state={status.state}
            key={label}
            to={`/trips/${tripId}/${route}`}
          >
            <Icon aria-hidden="true" size={19} />
            <span className="stage-tab-label">{label}</span>
            {/* The sidebar's next-badge, shrunk to a dot: a tab bar has no room for a
                word, and the word is in the sheet. Never on the tab you are already
                looking at, where "next" would be pointing at the present. */}
            {status.state === "next" && !current ? (
              <span aria-hidden="true" className="stage-tab-dot" />
            ) : null}
          </Link>
        );
      })}
      <button
        aria-controls="stage-nav"
        aria-expanded={navOpen}
        aria-haspopup="dialog"
        className="stage-tab"
        onClick={onMore}
        type="button"
      >
        <MoreHorizontal aria-hidden="true" size={19} />
        <span className="stage-tab-label">{copy("tab_more", language)}</span>
      </button>
    </nav>
  );
}
