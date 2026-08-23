import { describe, expect, it } from "vitest";

import catalogue from "../../../i18n/copy.json";
import { TAG_ICONS, tagIcon } from "./tagIcons";

/**
 * The table has to stay exhaustive, because the failure is silent.
 *
 * `tagIcon` falls back to a neutral glyph, which is right at runtime and useless
 * as a signal: a tag added to `TAG_TEXT` without an icon renders as a chip that
 * looks finished. This is what makes the fallback a safety net rather than the
 * answer.
 */
const CODES = Object.keys((catalogue as { TAG_TEXT: { en: Record<string, string> } }).TAG_TEXT.en);

describe("tag icons", () => {
  it("covers every tag the catalogue can render", () => {
    const missing = CODES.filter((code) => !(code in TAG_ICONS));

    expect(missing).toEqual([]);
  });

  it("carries no icon for a tag that does not exist", () => {
    const spare = Object.keys(TAG_ICONS).filter((code) => !CODES.includes(code));

    expect(spare).toEqual([]);
  });

  it("answers for an unknown code rather than throwing", () => {
    expect(tagIcon("a_tag_from_the_future")).toBeTruthy();
  });
});
