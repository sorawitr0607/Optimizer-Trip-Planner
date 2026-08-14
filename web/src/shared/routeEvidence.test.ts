import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { collectRouteEvidence } from "./routeEvidence";

/**
 * `refresh_routes` fetches at most sixty **new** pairs a call, and eleven selected
 * places need 110 ordered pairs. Auto-resolve called it once, so the remainder stayed
 * unmeasured and `ROUTE_UNVERIFIED` — which is fatal — left those places reading
 * "Cannot currently fit · collect a verified route" with no control that would collect
 * one. Measured on the owner's Osaka trip: one pass left 30 pairs missing, and the
 * second fetched all 30.
 */

afterEach(() => vi.restoreAllMocks());

describe("collectRouteEvidence", () => {
  it("keeps asking until nothing is outstanding", async () => {
    const rpc = vi
      .spyOn(client, "rpc")
      .mockResolvedValueOnce({ pairs_needed: 110, fetched: 60 })
      .mockResolvedValueOnce({ pairs_needed: 50, fetched: 50 })
      .mockResolvedValueOnce({ pairs_needed: 0, fetched: 0 });

    await collectRouteEvidence("trip_1");

    // Two walking passes, then transit — which is asked for once whatever walking did.
    expect(rpc).toHaveBeenCalledTimes(3);
    expect(rpc).toHaveBeenLastCalledWith("refresh_transit_routes", { trip_id: "trip_1" });
  });

  it("stops after one call when the first pass covered everything", async () => {
    const rpc = vi.spyOn(client, "rpc").mockResolvedValue({ pairs_needed: 12, fetched: 12 });

    await collectRouteEvidence("trip_1");

    expect(rpc).toHaveBeenCalledTimes(2);
    expect(rpc).toHaveBeenNthCalledWith(1, "refresh_routes", { trip_id: "trip_1" });
  });

  it("stops rather than looping when a pass fetches nothing", async () => {
    // The cap is per call, so a pass that fetched nothing will fetch nothing again —
    // this is the rate-limited provider, and hammering it is the burst the endpoint's
    // two concurrent slots cannot survive.
    const rpc = vi.spyOn(client, "rpc").mockResolvedValue({ pairs_needed: 90, fetched: 0 });

    await collectRouteEvidence("trip_1");

    expect(rpc).toHaveBeenCalledTimes(2);
  });

  it("never throws, so a failed pass keeps what earlier passes stored", async () => {
    vi.spyOn(client, "rpc")
      .mockResolvedValueOnce({ pairs_needed: 110, fetched: 60 })
      .mockRejectedValueOnce(new Error("Provider HTTP 504"))
      .mockRejectedValueOnce(new Error("Provider HTTP 504"));

    // Resolves with whatever was stored — 60 walking legs survive both failures.
    await expect(collectRouteEvidence("trip_1")).resolves.toBe(60);
  });
});

describe("collectRouteEvidence transit fallback", () => {
  it("rescues a trip whose walking router is unreachable", async () => {
    // OpenRouteService went down on the owner's London trip — 60 of 60 attempts — which
    // left every place ROUTE_UNVERIFIED and the plan unbuildable. Transit topology is
    // free, from a different service, and produces `estimated` routes the optimizer
    // accepts on an Explore trip. Measured: 0 walking, then 24 transit legs.
    const rpc = vi
      .spyOn(client, "rpc")
      .mockRejectedValueOnce(new Error("OpenRouteService is unreachable: URLError"))
      .mockResolvedValueOnce({ pairs_needed: 110, fetched: 24 });

    await expect(collectRouteEvidence("trip_1")).resolves.toBe(24);
    expect(rpc).toHaveBeenLastCalledWith("refresh_transit_routes", { trip_id: "trip_1" });
  });
});
