import { useCallback, useSyncExternalStore } from "react";

/**
 * A media query as React state.
 *
 * Used to pick *which* navigation surface exists, not merely how it looks — the
 * phone gets a bottom tab bar and the desktop a sidebar, and rendering both would
 * put two `aria-current="page"` claims in one document, which is the exact defect
 * `navSemantics.test.tsx` was written to catch. CSS alone cannot express "only one
 * of these is in the DOM", so the choice is made here.
 *
 * The server snapshot is `false`, so anything without `matchMedia` — the node test
 * environment, and any future prerender — renders the desktop sidebar. That keeps
 * the static-markup tests describing the same single nav they always did.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => {};
      const list = window.matchMedia(query);
      list.addEventListener("change", onStoreChange);
      return () => list.removeEventListener("change", onStoreChange);
    },
    [query],
  );
  const snapshot = useCallback(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia(query).matches;
  }, [query]);
  return useSyncExternalStore(subscribe, snapshot, () => false);
}

/** The one phone breakpoint. Named here so the shell and the stylesheet cannot drift. */
export const PHONE = "(max-width: 860px)";
