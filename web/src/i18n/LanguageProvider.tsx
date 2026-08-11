/* eslint-disable react-refresh/only-export-components */
import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useMemo, useState } from "react";

import type { Language } from "./copy";

interface LanguageState {
  language: Language;
  setLanguage: (language: Language) => void;
}

const LanguageContext = createContext<LanguageState | null>(null);

const LANGUAGE_KEY = "tourist.language";

function storedLanguage(): Language | null {
  try {
    const held = window.localStorage.getItem(LANGUAGE_KEY);
    return held === "en" || held === "th" ? held : null;
  } catch {
    return null;
  }
}

/**
 * `initial` is the capture seam and nothing else — `main.tsx` passes it only when
 * `?baseline_language=` is on the URL, so a stored preference can never repaint a
 * screen baseline. Everywhere else the owner's last choice wins, and it is
 * remembered: it used to reset to English on every reload, which a Thai-speaking
 * owner met on the landing page before there was any control to change it.
 */
export function LanguageProvider({
  children,
  initial,
}: PropsWithChildren<{ initial?: Language }>) {
  const [language, setLanguageState] = useState<Language>(() => initial ?? storedLanguage() ?? "en");
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);
  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    try {
      window.localStorage.setItem(LANGUAGE_KEY, next);
    } catch {
      /* Unstorable: the choice still holds for this tab. */
    }
  }, []);
  const value = useMemo(() => ({ language, setLanguage }), [language, setLanguage]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageState {
  const value = useContext(LanguageContext);
  if (!value) throw new Error("useLanguage must be inside LanguageProvider");
  return value;
}
