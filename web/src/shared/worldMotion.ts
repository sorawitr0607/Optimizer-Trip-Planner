/**
 * Scroll-linked depth, and the order a scene arrives in.
 *
 * The brief asks for GSAP and ScrollTrigger. `WF-026` fixes this app's web
 * runtime at six dependencies and a scroll library would be a seventh, so both
 * behaviours are built on platform APIs instead — which for these two is not a
 * compromise: one passive scroll listener and one IntersectionObserver do
 * exactly this job, and the animation itself stays in CSS where the compositor
 * can run it.
 *
 * Nothing here reads layout in the scroll handler. `scrollY` is the one value
 * sampled, written to a custom property once per frame, and every layer derives
 * its own travel from that with its own `--depth`. Reading each element's
 * position per frame is what turns a parallax into a jank machine.
 */

/** Depth layers translate by this many pixels per viewport of scroll, times depth. */
const TRAVEL_PX = 90;

export function startWorldMotion(root: HTMLElement): () => void {
  const reduced = !window.matchMedia("(prefers-reduced-motion: no-preference)").matches;
  // A capture photographs the page; a scene mid-parallax is a different image on
  // every run for no code reason, which is the drift bug this repo has fixed
  // twice already.
  const capturing = document.documentElement.dataset.capture === "1";
  if (reduced || capturing) return () => {};

  let frame = 0;
  const onScroll = () => {
    if (frame) return;
    frame = window.requestAnimationFrame(() => {
      frame = 0;
      root.style.setProperty("--scroll-y", String(window.scrollY / window.innerHeight));
    });
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  // Reveal order: the scene arrives, then its landmarks, then the words, then the
  // small things. Each section gets the class once and keeps it — a reveal that
  // replays every time it scrolls back into view reads as a glitch, not a story.
  // The reveal's hidden state is scoped to this class, which only this function
  // adds. Written the other way round — hidden by default in CSS, revealed by
  // script — a page whose JavaScript failed would render permanently blank, and
  // so would every screen baseline, since a capture leaves motion preferences
  // alone. Content is visible unless something is definitely running to reveal it.
  root.classList.add("motion-ready");

  const seen = new WeakSet<Element>();
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting || seen.has(entry.target)) continue;
        seen.add(entry.target);
        entry.target.classList.add("in-view");
        observer.unobserve(entry.target);
      }
    },
    { rootMargin: "0px 0px -12% 0px", threshold: 0.12 },
  );
  root.querySelectorAll(".landing-section, .landing-world").forEach((el) => observer.observe(el));

  return () => {
    window.removeEventListener("scroll", onScroll);
    observer.disconnect();
    if (frame) window.cancelAnimationFrame(frame);
  };
}

export { TRAVEL_PX };
