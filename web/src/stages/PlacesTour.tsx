import { HelpCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { copy, type Language } from "../i18n/copy";

/**
 * What this screen is, shown once, the first time an owner reaches it.
 *
 * `/places` is the densest screen in the app — a deck you can throw four ways, a lane
 * picker, a detail panel, a drawer — and every one of those was learned by the owner
 * reporting that it did not work. A first-time visitor has no such channel.
 *
 * Three rules it follows. It **shows once per trip**: remembered, because a tour that
 * reappears every visit is an obstacle — but keyed to the trip rather than the browser,
 * because it was reported as "didn't auto show" by an owner who had simply dismissed it
 * on a different trip weeks earlier, and a new trip is a new context. It is
 * **reopenable** from the screen, and that control is a labelled button rather than the
 * grey whisper it started as. And it **never appears in a capture**: a fresh Chrome
 * profile is always a first visit, so without the seam every screen baseline would
 * photograph this overlay instead of the screen it is watching.
 *
 * **It is a native `<dialog>` as of 2026-08-10, and that is the whole accessibility
 * fix.** It used to be a `<div role="dialog" aria-modal="true">`, which says a thing is
 * modal without making it one: a UX audit found focus still on `<body>` after it
 * opened, the first Tab landing on the navigation *behind* the scrim, focus escaping to
 * "Discover attractions", and Escape doing nothing — so a keyboard or screen-reader user
 * was operating controls they could not see, on the densest screen in the app.
 * `showModal()` gives all four back from the platform: focus moves inside, everything
 * else goes inert, Tab is contained, and Escape closes. Writing that by hand is fifty
 * lines of listeners that would have to be right about focus order forever. The one
 * thing the platform does not do here is choose *where* focus lands afterwards — it
 * restores to whatever was focused before, and on a first visit that is `<body>` — so
 * the reopen button is always rendered and explicitly refocused on close.
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
function alreadySeen(tripId: string): boolean {
  const root = typeof document === "undefined" ? null : document.documentElement;
  // `?baseline_tour=open` — the phone baseline set photographs this overlay, which
  // the capture flag otherwise exists to hide. Checked first, so asking for it wins.
  if (root?.dataset.captureTour) return false;
  if (root?.dataset.capture) return true;
  try {
    return window.localStorage.getItem(`${SEEN_KEY}.${tripId}`) === "1";
  } catch {
    return true;
  }
}

function remember(tripId: string): void {
  try {
    window.localStorage.setItem(`${SEEN_KEY}.${tripId}`, "1");
  } catch {
    /* A profile that refuses storage simply sees the tour again. */
  }
}

export interface PlacesTourProps {
  language: Language;
  tripId: string;
}

export function PlacesTour({ language, tripId }: PlacesTourProps) {
  const [open, setOpen] = useState(() => !alreadySeen(tripId));
  const [step, setStep] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const reopen = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);

  // `showModal()` is what makes the element modal; rendering it is not. Every close,
  // including Escape's `cancel` event, updates state first so React and the platform
  // cannot disagree about whether the card is open.
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !node.open) node.showModal();
    if (!open && node.open) node.close();
    if (!open && returnFocus.current) {
      returnFocus.current = false;
      reopen.current?.focus();
    }
  }, [open]);

  function close() {
    remember(tripId);
    returnFocus.current = true;
    setOpen(false);
    setStep(0);
  }

  const current = STEPS[step];
  const last = step === STEPS.length - 1;

  return (
    <>
      <button className="tour-reopen" onClick={() => setOpen(true)} ref={reopen} type="button">
        <HelpCircle aria-hidden="true" size={14} /> {copy("tour_reopen", language)}
      </button>
      {/* derives-from: element 38 .modal-card as .tour-card */}
      <dialog
        aria-label={copy("tour_title", language)}
        className="tour-backdrop"
        onCancel={(event) => {
          // Chrome closes a native dialog on Escape before React's `onClose` sees a
          // usable state transition. Preventing that default lets the same state-led
          // close path serve Escape and both visible buttons, including focus return.
          event.preventDefault();
          close();
        }}
        onClose={() => {
          if (open) close();
        }}
        ref={dialog}
      >
      {open ? (
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
      ) : null}
      </dialog>
    </>
  );
}
