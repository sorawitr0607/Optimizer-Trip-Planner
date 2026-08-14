import { useEffect, useRef, useState } from "react";

import { copy, copyFrom, type Language } from "../i18n/copy";

/**
 * The end of the journey, said out loud once.
 *
 * With every stage done, `journey.next` falls back to `itinerary` so `/` still has
 * somewhere to send a returning owner — and the screen said nothing else, so finishing
 * a trip looked exactly like being stuck on the last step. The report was not knowing
 * what to do next when in fact there was nothing left to do.
 *
 * Once per plan version, not once per visit: activating a *new* plan is a new thing to
 * be told about, and re-reading the itinerary is not. `<dialog>` and `showModal()` for
 * the same reason `PlacesTour` uses them — focus containment, inertness and Escape come
 * from the platform rather than from an `aria-modal` attribute that only claims them.
 *
 * **It celebrates and warns in the same breath.** A plan built on assumed opening hours
 * and estimated routes is a real plan and should not be presented as a problem — but the
 * assumptions are exactly what wants checking before anyone travels, so they are in the
 * card rather than a screen away.
 */

/* derives-from: element 38 .modal-card as .tour-card. This reuses the tour's shell
   outright — same `<dialog>`, same backdrop, same card — because it is the same kind of
   thing said at the other end of the journey, and two modal shapes in one app is one
   too many. Only the inner spacing and the warning block are its own. */

const SEEN_KEY = "optimizer.plan-ready";

function alreadySeen(versionId: string): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === versionId;
  } catch {
    // Private mode, or storage disabled. Showing it again is a far smaller cost than
    // failing to render the screen behind it.
    return false;
  }
}

function remember(versionId: string): void {
  try {
    window.localStorage.setItem(SEEN_KEY, versionId);
  } catch {
    /* nothing to do: the dialog simply appears again next time */
  }
}

export interface PlanReadyProps {
  language: Language;
  /** The activated plan version. Identity is what makes this once-per-plan. */
  versionId: string;
  /** `capability_gaps` from the snapshot the plan was built from — the app's own record
   *  of what it had to stand in for, never a second opinion derived beside it. */
  gaps: string[];
}

export function PlanReady({ language, versionId, gaps }: PlanReadyProps) {
  const [open, setOpen] = useState(() => Boolean(versionId) && !alreadySeen(versionId));
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !node.open) node.showModal();
    if (!open && node.open) node.close();
  }, [open]);

  function close() {
    remember(versionId);
    setOpen(false);
  }

  return (
    <dialog
      aria-label={copy("ready_title", language)}
      className="tour-backdrop"
      onCancel={(event) => {
        // Chrome closes on Escape before React sees a usable transition, so the same
        // state-led path serves Escape and the button.
        event.preventDefault();
        close();
      }}
      onClose={() => {
        if (open) close();
      }}
      ref={dialog}
    >
      {open ? (
        <div className="tour-card plan-ready">
          <h2>{copy("ready_title", language)}</h2>
          <p>{copy("ready_body", language)}</p>
          {gaps.length ? (
            <div className="plan-ready-warn">
              <p className="setup-hint">{copy("ready_warn", language)}</p>
              <ul>
                {gaps.map((gap) => (
                  <li key={gap}>{copyFrom("OPTIMIZER_CODE_TEXT", gap, language)}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <button autoFocus className="setup-primary" onClick={close} type="button">
            {copy("ready_close", language)}
          </button>
        </div>
      ) : null}
    </dialog>
  );
}
