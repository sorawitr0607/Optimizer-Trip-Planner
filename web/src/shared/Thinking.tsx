import { useEffect, useState } from "react";

import { copy, copyFormat, type Language } from "../i18n/copy";

/**
 * What the app is doing, while it does it.
 *
 * Discovery runs 30-90s and a full optimize about 52s, and both used to show a
 * disabled button and nothing else. The owner's report was "I still can't build a
 * plan" — the work was succeeding every time; the screen simply never said so, and a
 * dead-looking button for a minute is indistinguishable from a broken one.
 *
 * The lines are the real stages in the real order, not decoration: a reader who
 * watches "measuring walking and transit" go by learns what the wait is buying. They
 * advance on a timer rather than on progress events, which is honest about what it is
 * — the server reports no milestones, so this claims none.
 */

/** Slow enough to read, quick enough to look alive. */
const EVERY_MS = 2600;

/** Whole seconds since `origin`, never negative. */
function since(origin: number): number {
  return Math.max(0, Math.round((Date.now() - origin) / 1000));
}

export interface ThinkingProps {
  language: Language;
  /** Copy codes, in the order the work actually happens. */
  lines: readonly string[];
  /**
   * Roughly how long this work takes, so the lines are paced across it.
   *
   * Three lines at `EVERY_MS` cover **eight seconds** of an optimize that measures about
   * **52** — so the text finished, held, and then sat unchanged for the remaining 44,
   * which is what "the loading text is stuck" was reporting. It was not stuck; it had
   * simply run out of things to say five sixths of the way from the end.
   */
  expectSeconds?: number;
  /**
   * When the wait began, as `Date.now()`. Defaults to this element's own mount.
   *
   * Supplied where the element is remounted part-way through the wait it is
   * describing. `/places` does exactly that: the moment the worker reports its
   * first stage, this moves from standing alone to sitting inside the active row
   * of `BuildStages`, which is a different position in the tree and therefore a
   * new mount. A counter that restarted at zero there would read as the work
   * having started over -- the precise impression it was added to prevent.
   */
  startedAt?: number;
}

export function Thinking({ expectSeconds, language, lines, startedAt }: ThinkingProps) {
  const [index, setIndex] = useState(0);
  const [mountedAt] = useState(() => Date.now());
  const origin = startedAt ?? mountedAt;
  // Correct on the first paint, not one tick later. A remount that renders `0s`
  // and fixes itself a second afterwards is a visible flinch, and it is the same
  // wrong number the effect below exists to avoid.
  const [elapsed, setElapsed] = useState(() => since(origin));

  useEffect(() => {
    const step = expectSeconds ? Math.max(EVERY_MS, (expectSeconds * 1000) / lines.length) : EVERY_MS;
    const timer = window.setInterval(
      // Wraps rather than holding on the last line, at the owner's asking. It used to
      // hold, so that a long wait would not look like it had restarted — but the elapsed
      // counter beside it now carries that job honestly, and with it there, coming back
      // round reads as variety rather than as a reset. Holding read as frozen, which is
      // the exact impression the counter was added to prevent.
      () => setIndex((current) => current + 1),
      step,
    );
    return () => window.clearInterval(timer);
  }, [expectSeconds, lines.length]);

  useEffect(() => {
    // A real measurement, not an estimate of progress — for the paths where the server
    // reports no milestones this is the one thing actually known, and where it does
    // report them it is still the only thing that can be said *inside* a stage. It can
    // never freeze, which is the whole point: a number that ticks says "running" where
    // held text says "hung".
    //
    // Read off the clock rather than counted in ticks, so it survives a remount and
    // does not drift with a throttled `setInterval` in a background tab. Both are the
    // same failure: a wait that has run for a minute claiming it has run for ten
    // seconds.
    const tick = () => setElapsed(since(origin));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [origin]);

  return (
    // derives-from: element 36 .currency-info-box as .thinking
    <p aria-live="polite" className="thinking">
      <span className="thinking-dot" />
      <span key={index}>{copy(lines[index % lines.length], language)}</span>
      <span className="thinking-elapsed">{copyFormat("thinking_elapsed", language, { seconds: String(elapsed) })}</span>
    </p>
  );
}
