import { useState } from "react";

import { copy, type Language } from "../i18n/copy";

/**
 * What this screen is, shown once, the first time an owner reaches it.
 *
 * `/places` is the densest screen in the app — a deck you can throw four ways, a lane
 * picker, a detail panel, a drawer — and every one of those was learned by the owner
 * reporting that it did not work. A first-time visitor has no such channel.
 *
 * Three rules it follows. It **shows once**: the dismissal is remembered, and a tour
 * that reappears is an obstacle rather than help. It is **reopenable** from the screen,
 * because "once" is wrong for anyone who comes back a month later. And it **never
 * appears in a capture**: a fresh Chrome profile is always a first visit, so without
 * the seam every screen baseline would photograph this overlay instead of the screen
 * it is supposed to be watching.
 */

const SEEN_KEY = "tourist.places_tour_seen";

const STEPS = [
  { title: "tour_step_discover", body: "tour_step_discover_body", art: "discover" },
  { title: "tour_step_swipe", body: "tour_step_swipe_body", art: "swipe" },
  { title: "tour_step_lanes", body: "tour_step_lanes_body", art: "lanes" },
  { title: "tour_step_shortlist", body: "tour_step_shortlist_body", art: "shortlist" },
] as const;

/** Remembered per browser. `localStorage` can throw in a locked-down profile, and a
 *  tour is not worth a blank screen, so every access is guarded. */
function alreadySeen(): boolean {
  if (typeof document !== "undefined" && document.documentElement.dataset.capture) {
    return true;
  }
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return true;
  }
}

function remember(): void {
  try {
    window.localStorage.setItem(SEEN_KEY, "1");
  } catch {
    /* A profile that refuses storage simply sees the tour again. */
  }
}

export interface PlacesTourProps {
  language: Language;
}

export function PlacesTour({ language }: PlacesTourProps) {
  const [open, setOpen] = useState(() => !alreadySeen());
  const [step, setStep] = useState(0);

  function close() {
    remember();
    setOpen(false);
    setStep(0);
  }

  if (!open) {
    return (
      <button className="tour-reopen" onClick={() => setOpen(true)} type="button">
        {copy("tour_reopen", language)}
      </button>
    );
  }

  const current = STEPS[step];
  const last = step === STEPS.length - 1;

  return (
    // derives-from: element 38 .modal-card as .tour-card
    <div className="tour-backdrop" role="dialog" aria-modal="true" aria-label={copy("tour_title", language)}>
      <div className="tour-card">
        <p className="money-eyebrow">{copy("tour_title", language)}</p>

        {/* The art moves, because every one of these is a movement. A still diagram of
            a gesture is a diagram of the thing it is not. */}
        <div className={`tour-art tour-art-${current.art}`} aria-hidden="true">
          {current.art === "swipe" ? (
            <>
              <span className="tour-ghost" />
              <span className="tour-arrow tour-arrow-left">←</span>
              <span className="tour-arrow tour-arrow-right">→</span>
              <span className="tour-arrow tour-arrow-up">↑</span>
              <span className="tour-arrow tour-arrow-down">↓</span>
            </>
          ) : null}
          {current.art === "discover" ? <span className="tour-pulse" /> : null}
          {current.art === "lanes" ? (
            <>
              <span className="tour-tab" />
              <span className="tour-tab tour-tab-on" />
              <span className="tour-tab" />
            </>
          ) : null}
          {current.art === "shortlist" ? <span className="tour-drawer" /> : null}
        </div>

        <h3>{copy(current.title, language)}</h3>
        <p>{copy(current.body, language)}</p>

        <ol className="tour-dots" aria-hidden="true">
          {STEPS.map((item, index) => (
            <li className={index === step ? "current" : undefined} key={item.title} />
          ))}
        </ol>

        <div className="tour-actions">
          <button onClick={close} type="button">
            {copy(last ? "tour_start" : "tour_skip", language)}
          </button>
          {last ? null : (
            <button className="tour-next" onClick={() => setStep(step + 1)} type="button">
              {copy("tour_next", language)}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
