import { afterEach, describe, expect, it, vi } from "vitest";

import { placesDaysWereAddedFor, rememberDaysAddedFor } from "./dayExtension";

/** Enough of `localStorage` to write to and read back, plus a locked-down one. */
function storage(locked = false) {
  const held = new Map<string, string>();
  return {
    getItem: (key: string) => {
      if (locked) throw new Error("denied");
      return held.get(key) ?? null;
    },
    setItem: (key: string, value: string) => {
      if (locked) throw new Error("denied");
      held.set(key, value);
    },
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("dayExtension", () => {
  it("remembers the places a day was added for, and accumulates", () => {
    vi.stubGlobal("localStorage", storage());
    expect([...placesDaysWereAddedFor("trip_1")]).toEqual([]);

    rememberDaysAddedFor("trip_1", ["museum"]);
    expect([...placesDaysWereAddedFor("trip_1")]).toEqual(["museum"]);

    // A second extension for a different place must not forget the first.
    rememberDaysAddedFor("trip_1", ["garden"]);
    expect([...placesDaysWereAddedFor("trip_1")].sort()).toEqual(["garden", "museum"]);
  });

  it("keys on the trip", () => {
    vi.stubGlobal("localStorage", storage());
    rememberDaysAddedFor("trip_1", ["museum"]);
    expect([...placesDaysWereAddedFor("trip_2")]).toEqual([]);
  });

  it("is empty for a trip id it was never given", () => {
    vi.stubGlobal("localStorage", storage());
    expect([...placesDaysWereAddedFor("")]).toEqual([]);
    // And writing under no trip is a no-op rather than a key called ".undefined".
    expect(() => rememberDaysAddedFor("", ["museum"])).not.toThrow();
  });

  it("survives a profile that refuses storage", () => {
    // A locked-down profile gets offered the day once more, which is the old behaviour —
    // it must not cost the screen.
    vi.stubGlobal("localStorage", storage(true));
    expect([...placesDaysWereAddedFor("trip_1")]).toEqual([]);
    expect(() => rememberDaysAddedFor("trip_1", ["museum"])).not.toThrow();
  });

  it("ignores stored junk rather than trusting it", () => {
    // Browser storage is editable by anyone at the keyboard; a corrupt value must read
    // as "nothing tried" rather than throw on the render path.
    const held = new Map<string, string>([["tourist.days_added_for.trip_1", "{not json"]]);
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => held.get(key) ?? null,
      setItem: (key: string, value: string) => held.set(key, value),
    });
    expect([...placesDaysWereAddedFor("trip_1")]).toEqual([]);
  });
});
