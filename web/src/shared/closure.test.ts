import { describe, expect, it } from "vitest";

import { closedYear, looksClosed } from "./closure";

describe("closedYear", () => {
  it("reads the year from Wikidata's own precision", () => {
    // `2020-00-00` is how Wikidata says "2020, month and day unknown", and it is exactly
    // what `NHK Studio Park` carries.
    expect(closedYear({ closed_on: "2020-00-00" })).toBe("2020");
    expect(closedYear({ closed_on: "2025-03-31" })).toBe("2025");
  });

  it("is null when the source records nothing", () => {
    // The ordinary case, and the one that must stay silent: Edo Castle, Tokyo Skytree and
    // the NHK Museum of Broadcasting all come back with no closure claim.
    expect(closedYear({})).toBeNull();
    expect(closedYear({ closed_on: null })).toBeNull();
    expect(closedYear({ closed_on: "" })).toBeNull();
    expect(closedYear(undefined)).toBeNull();
  });

  it("refuses a stamp it cannot read rather than inventing a year", () => {
    expect(closedYear({ closed_on: "unknown" })).toBeNull();
    expect(closedYear({ closed_on: "  " })).toBeNull();
  });

  it("agrees with looksClosed", () => {
    for (const stamp of ["2020-00-00", "", "unknown", "1869-01-01"]) {
      expect(looksClosed({ closed_on: stamp })).toBe(closedYear({ closed_on: stamp }) !== null);
    }
  });
});
