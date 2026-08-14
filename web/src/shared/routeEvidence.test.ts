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
      .mockResolvedValueOnce({ pairs_needed: 50, fetched: 50 });

    await collectRouteEvidence("trip_1");

    expect(rpc).toHaveBeenCalledTimes(2);
    expect(rpc).toHaveBeenLastCalledWith("refresh_routes", { trip_id: "trip_1" });
  });

  it("stops after one call when the first pass covered everything", async () => {
    const rpc = vi.spyOn(client, "rpc").mockResolvedValue({ pairs_needed: 12, fetched: 12 });

    await collectRouteEvidence("trip_1");

    expect(rpc).toHaveBeenCalledTimes(1);
  });

  it("stops rather than looping when a pass fetches nothing", async () => {
    // The cap is per call, so a pass that fetched nothing will fetch nothing again —
    // this is the rate-limited provider, and hammering it is the burst the endpoint's
    // two concurrent slots cannot survive.
    const rpc = vi.spyOn(client, "rpc").mockResolvedValue({ pairs_needed: 90, fetched: 0 });

    await collectRouteEvidence("trip_1");

    expect(rpc).toHaveBeenCalledTimes(1);
  });

  it("never throws, so a failed pass keeps what earlier passes stored", async () => {
    vi.spyOn(client, "rpc")
      .mockResolvedValueOnce({ pairs_needed: 110, fetched: 60 })
      .mockRejectedValueOnce(new Error("Provider HTTP 504"));

    await expect(collectRouteEvidence("trip_1")).resolves.toBeUndefined();
  });
});
