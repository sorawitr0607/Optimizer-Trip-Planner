import type { ChecklistItem } from "../api/client";
import { copy, type Language } from "../i18n/copy";

/**
 * Checklist wording, in the reader's language.
 *
 * Mirror of `checklist._localized`: a generated task carries a stable code plus format
 * arguments, so it reads in the selected language everywhere. A missing template or a
 * mistyped placeholder falls back to the stored literal rather than losing the wording or
 * rendering `⚠ code`.
 *
 * Extracted from `ReadinessPage` when `/itinerary` needed the same titles. Two copies of
 * this would be two ways to name the same task on two screens.
 */
export function localizedTask(
  item: ChecklistItem,
  prefix: string,
  code: string | null | undefined,
  fallback: string,
  language: Language,
): string {
  if (!code) return fallback;
  const template = copy(`${prefix}${code}`, language);
  if (template.startsWith("⚠ ")) return fallback;
  const filled = template.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const value = item.title_args?.[name];
    return value === undefined ? whole : String(value);
  });
  return /\{\w+\}/.test(filled) ? fallback : filled;
}

export function taskTitle(item: ChecklistItem, language: Language): string {
  return localizedTask(item, "task_", item.template_id, item.title, language);
}

/** States that need nothing further — `checklist.py`'s own `CLOSED_STATES`. */
const CLOSED = new Set(["done", "not_applicable"]);

/** Whether an item is still asking for something. */
export function isOutstanding(item: ChecklistItem): boolean {
  return !item.dismissed && !CLOSED.has(item.progress);
}
