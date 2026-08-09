import { useEffect, useState } from "react";

import { copy, type Language } from "../i18n/copy";

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
}

export function Thinking({ language, lines }: ThinkingProps) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(
      // Holds on the last line rather than looping, so a long wait does not look like
      // it has restarted.
      () => setIndex((current) => Math.min(current + 1, lines.length - 1)),
      EVERY_MS,
    );
    return () => window.clearInterval(timer);
  }, [lines.length]);

  return (
    // derives-from: element 36 .currency-info-box as .thinking
    <p aria-live="polite" className="thinking">
      <span className="thinking-dot" />
      <span key={index}>{copy(lines[index], language)}</span>
    </p>
  );
}
