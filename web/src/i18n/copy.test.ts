import { describe, expect, it } from "vitest";

import copyJson from "../../../i18n/copy.json";
import { copy } from "./copy";

describe("copy", () => {
  it("reads both languages and keeps missing codes obvious", () => {
    expect(copy("stage_setup", "en")).toBe("Trip and setup");
    expect(copy("stage_setup", "th")).toBe("ทริปและการตั้งค่า");
    expect(copy("MISSING", "en")).toBe("⚠ MISSING");
  });

  it("keeps every table at en/th key parity", () => {
    // CATEGORY_TEXT once shipped 1 English key against 25 Thai, so every swipe
    // card in the default language read "⚠ museum". A missing key renders as
    // the ⚠ code, which is honest on one screen and broken on all of them.
    const keyPaths = (node: unknown, prefix = ""): string[] => {
      if (typeof node !== "object" || node === null) return [prefix];
      return Object.entries(node).flatMap(([key, value]) =>
        keyPaths(value, prefix ? `${prefix}.${key}` : key),
      );
    };
    for (const [table, languages] of Object.entries(copyJson)) {
      const en = new Set(keyPaths(languages.en as object));
      const th = new Set(keyPaths(languages.th as object));
      expect([...en].filter((key) => !th.has(key)), `${table} en-only`).toEqual([]);
      expect([...th].filter((key) => !en.has(key)), `${table} th-only`).toEqual([]);
    }
  });
});
