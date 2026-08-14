/**
 * The kept card flies to the shortlist tab, the way a product flies to a cart.
 *
 * A swipe already wrote the choice; what it did not do was *say where the place went*.
 * The card simply vanished and a number in the corner changed, and those two events are
 * only connected if you happen to be looking at both — so the deck read as cards
 * disappearing rather than as a shortlist being built. This draws the connection.
 *
 * It is decoration and behaves like it: it never blocks, never delays the decision, and
 * never fails loudly. If anything it needs is missing — the tab is off screen, the card
 * has no photograph, the browser has no Web Animations API — it does nothing at all and
 * the swipe is exactly as it was.
 *
 * Two suppressions, both this repo's standing rules rather than taste. Motion sits behind
 * `prefers-reduced-motion: no-preference`, like every other animation here. And a capture
 * runs with none of it: the screen baselines photograph the app, and an element mid-flight
 * is a different image on every run for no code reason — that is the drift bug the
 * summaries prefetch and the first-visit tour were already fixed for.
 */

/** Long enough to follow with your eye, short enough not to be in the way of the next card. */
const FLIGHT_MS = 520;

/** How small the ghost has ended up by the time it reaches the tab. */
const LANDING_SCALE = 0.16;

/** The counter's own acknowledgement, started as the ghost lands. */
const BUMP_MS = 260;

function suppressed(): boolean {
  if (typeof document === "undefined" || typeof window === "undefined") return true;
  if (document.documentElement.dataset.capture) return true;
  return !window.matchMedia("(prefers-reduced-motion: no-preference)").matches;
}

/**
 * @param card   The element being decided — the ghost is cut from its photograph.
 * @param target The shortlist tab. Nothing happens without it.
 */
export function flyToShortlist(card: Element | null, target: Element | null): void {
  if (suppressed() || !card || !target) return;

  const photo = card.querySelector("img");
  const from = (photo ?? card).getBoundingClientRect();
  const to = target.getBoundingClientRect();
  // A zero-sized rect means the element is not laid out — `display: none` at this
  // breakpoint, or a card that has already left. There is nothing to fly.
  if (!from.width || !from.height || !to.width || !to.height) return;

  const ghost = document.createElement("div");
  ghost.setAttribute("aria-hidden", "true");
  ghost.className = "shortlist-flight";
  if (photo instanceof HTMLImageElement && photo.currentSrc) {
    ghost.style.backgroundImage = `url("${photo.currentSrc}")`;
  }
  ghost.style.left = `${from.left}px`;
  ghost.style.top = `${from.top}px`;
  ghost.style.width = `${from.width}px`;
  ghost.style.height = `${from.height}px`;
  document.body.append(ghost);

  // Centre-to-centre, so the ghost lands *on* the tab rather than beside it — the
  // scale happens about the ghost's own middle, so its corners are not the thing
  // travelling.
  const dx = to.left + to.width / 2 - (from.left + from.width / 2);
  const dy = to.top + to.height / 2 - (from.top + from.height / 2);

  const done = () => {
    ghost.remove();
    target.classList.add("shortlist-handle-bumped");
    window.setTimeout(() => target.classList.remove("shortlist-handle-bumped"), BUMP_MS);
  };

  // No Web Animations API is not an error; it is a browser that gets the plain swipe.
  if (typeof ghost.animate !== "function") {
    done();
    return;
  }

  const flight = ghost.animate(
    [
      { opacity: 1, transform: "translate(0, 0) scale(1)" },
      // Rises before it falls, so the path is an arc rather than a straight line
      // across the screen. A straight line reads as a UI element being moved; an arc
      // reads as something being tossed into a container.
      {
        offset: 0.35,
        opacity: 0.95,
        transform: `translate(${dx * 0.35}px, ${dy * 0.35 - 40}px) scale(0.6)`,
      },
      { opacity: 0.2, transform: `translate(${dx}px, ${dy}px) scale(${LANDING_SCALE})` },
    ],
    { duration: FLIGHT_MS, easing: "cubic-bezier(0.32, 0, 0.28, 1)", fill: "forwards" },
  );
  flight.addEventListener("finish", done);
  // A cancelled animation still has to clean up after itself, or a navigation
  // mid-flight leaves an orphan pinned over the next screen.
  flight.addEventListener("cancel", () => ghost.remove());
}
