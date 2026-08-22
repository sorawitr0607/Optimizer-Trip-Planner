/* eslint-disable react-refresh/only-export-components */
import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useMemo, useState } from "react";

/**
 * Which theme is on, remembered, and answering to the system when nothing is.
 *
 * The toggle used to write `data-theme` straight onto the root element and stop
 * there, so the choice lasted exactly as long as the tab: a reload put a dark-mode
 * owner back into a bright page. It also lived only in the sidebar, which does not
 * exist until a trip does — and it announced itself as "Theme", which tells a
 * screen-reader user neither what is on now nor what pressing it will do.
 *
 * Three rules. **A stamped root wins**: `main.tsx` sets `data-theme` from the
 * capture seam before React mounts, and a stored preference from an earlier run
 * must not repaint a baseline. **A stored choice beats everything else**, because
 * the owner said so. **With neither, the answer is light** — at the owner's asking,
 * and regardless of what the device prefers.
 *
 * That last rule used to read the device: `prefers-color-scheme` decided for anyone
 * who had never touched the toggle. It was the only path by which the device reached
 * the theme at all — neither `tokens.css` nor `shell.css` contains a
 * `prefers-color-scheme` block, so dark is applied exclusively through
 * `[data-theme="dark"]` — which is why removing one branch here is the whole change
 * and there is no flash of the wrong palette before React mounts.
 *
 * Note what this does *not* do: it is a default, not a lock. Someone on a dark phone
 * who presses the toggle still gets dark, and still gets it on their next visit.
 */

export type Theme = "light" | "dark";

const THEME_KEY = "tourist.theme";

function stampedTheme(): Theme | null {
  const held = document.documentElement.dataset.theme;
  return held === "dark" || held === "light" ? held : null;
}

function storedTheme(): Theme | null {
  try {
    const held = window.localStorage.getItem(THEME_KEY);
    return held === "dark" || held === "light" ? held : null;
  } catch {
    // A profile that refuses storage simply follows the system every time.
    return null;
  }
}

function initialTheme(): Theme {
  // The Vitest suite renders these components with `renderToStaticMarkup` in the
  // node environment, where there is no document to read a preference from and no
  // effect will run to write one back.
  if (typeof document === "undefined") return "light";
  // Light unless something explicitly says otherwise. The device is deliberately not
  // consulted -- see the note above.
  return stampedTheme() ?? storedTheme() ?? "light";
}

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

export function ThemeProvider({ children }: PropsWithChildren) {
  const [theme, setThemeState] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    // A stored choice has to reach the root before anything reads it, and the
    // capture seam stamps the root itself — so this writes, and never reads back.
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      /* Unstorable: the choice still holds for this tab. */
    }
  }, []);

  const value = useMemo<ThemeState>(
    () => ({ theme, setTheme, toggleTheme: () => setTheme(theme === "dark" ? "light" : "dark") }),
    [theme, setTheme],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be inside ThemeProvider");
  return value;
}
