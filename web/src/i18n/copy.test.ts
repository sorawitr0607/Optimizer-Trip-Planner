import { describe, expect, it } from "vitest";

import { copy } from "./copy";

describe("copy", () => {
  it("reads both languages and keeps missing codes obvious", () => {
    expect(copy("stage_setup", "en")).toBe("Trip and setup");
    expect(copy("stage_setup", "th")).toBe("ทริปและการตั้งค่า");
    expect(copy("MISSING", "en")).toBe("⚠ MISSING");
  });
});
