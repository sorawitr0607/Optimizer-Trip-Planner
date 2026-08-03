import catalogue from "../../../i18n/copy.json";

export type Language = "en" | "th";

const textTable = catalogue.TEXT as Record<Language, Record<string, string>>;

/** The seven catalogue tables beside TEXT. The core emits codes; these render them. */
export type CopyTable =
  | "ACCOMMODATION_TEXT"
  | "CATEGORY_TEXT"
  | "DIMENSION_TEXT"
  | "EXPLANATION_TEXT"
  | "OPTIMIZER_CODE_TEXT"
  | "REJECTION_TEXT"
  | "TAG_TEXT";

const tables = catalogue as unknown as Record<
  CopyTable,
  Record<Language, Record<string, string>>
>;

/** An unknown code renders visibly as machine output, never as copy-looking prose. */
export function copyFrom(table: CopyTable, code: string, language: Language): string {
  return tables[table]?.[language]?.[code] ?? `⚠ ${code}`;
}

export function copy(code: string, language: Language): string {
  return textTable[language][code] ?? `⚠ ${code}`;
}

/** Fill a catalogue string's `{name}` placeholders, as Python's format() does. */
export function copyFormat(
  code: string,
  language: Language,
  values: Record<string, string | number>,
): string {
  return Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    copy(code, language),
  );
}
