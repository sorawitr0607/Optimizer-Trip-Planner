/* eslint-disable react-refresh/only-export-components */
import { createContext, type PropsWithChildren, useContext, useEffect, useMemo, useState } from "react";

import type { Language } from "./copy";

interface LanguageState {
  language: Language;
  setLanguage: (language: Language) => void;
}

const LanguageContext = createContext<LanguageState | null>(null);

export function LanguageProvider({ children }: PropsWithChildren) {
  const [language, setLanguage] = useState<Language>("en");
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);
  const value = useMemo(() => ({ language, setLanguage }), [language]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageState {
  const value = useContext(LanguageContext);
  if (!value) throw new Error("useLanguage must be inside LanguageProvider");
  return value;
}
