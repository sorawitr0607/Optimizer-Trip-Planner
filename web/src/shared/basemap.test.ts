import { afterEach, describe, expect, it, vi } from "vitest";

import { rpc, type Basemap } from "../api/client";
import { loadBasemap } from "./basemap";

vi.mock("../api/client", () => ({ rpc: vi.fn() }));

const MAP = {
  roads: [[[25, 121], [25.1, 121.1]]],
  water: [], green: [], attribution: "OpenStreetMap", license: "ODbL",
  expires_at: "2099-01-01T00:00:00+00:00",
} satisfies Basemap;

function storage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
    clear: () => values.clear(),
    key: (index: number) => [...values.keys()][index] ?? null,
    get length() { return values.size; },
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("loadBasemap", () => {
  it("reuses an unexpired map without another server download", async () => {
    vi.stubGlobal("localStorage", storage());
    vi.mocked(rpc).mockResolvedValue(MAP);

    expect(await loadBasemap("taipei", false)).toEqual(MAP);
    expect(await loadBasemap("taipei", false)).toEqual(MAP);
    expect(rpc).toHaveBeenCalledTimes(1);
    expect(rpc).toHaveBeenCalledWith("refresh_basemap", { trip_id: "taipei" });
  });

  it("bypasses browser state during a baseline capture", async () => {
    vi.stubGlobal("localStorage", storage());
    vi.mocked(rpc).mockResolvedValue(MAP);
    await loadBasemap("taipei", false);
    vi.mocked(rpc).mockClear();

    await loadBasemap("taipei", true);
    expect(rpc).toHaveBeenCalledWith("get_basemap", { trip_id: "taipei" });
  });
});
