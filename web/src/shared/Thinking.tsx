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
}

export function Thinking({ expectSeconds, language, lines }: ThinkingProps) {
  const [index, setIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);

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
    // A real measurement, not an estimate of progress — the server reports no milestones,
    // so this counts the one thing actually known. It can never freeze, which is the
    // whole point: a number that ticks says "running" where held text says "hung".
    const timer = window.setInterval(() => setElapsed((seconds) => seconds + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    // derives-from: element 36 .currency-info-box as .thinking
    <p aria-live="polite" className="thinking">
      <span className="thinking-dot" />
      <span key={index}>{copy(lines[index % lines.length], language)}</span>
      <span className="thinking-elapsed">{copyFormat("thinking_elapsed", language, { seconds: String(elapsed) })}</span>
    </p>
  );
}
