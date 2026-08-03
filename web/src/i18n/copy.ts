import catalogue from "../../../i18n/copy.json";

export type Language = "en" | "th";

const textTable = catalogue.TEXT as Record<Language, Record<string, string>>;

export function copy(code: string, language: Language): string {
  return textTable[language][code] ?? `⚠ ${code}`;
}
