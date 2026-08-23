import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { collectRouteEvidence } from "./routeEvidence";

/**
 * `refresh_routes` fetches at most sixty **new** pairs a pass, and eleven selected
 * places need 110 ordered pairs. Auto-resolve called it once, so the remainder stayed
 * unmeasured and `ROUTE_UNVERIFIED` — which is fatal — left those places reading
 * "Cannot currently fit · collect a verified route" with no control that would collect
 * one. Measured on the owner's Osaka trip: one pass left 30 pairs missing, and the
 * second fetched all 30.
 *
 * **The passes moved to the server.** They used to be a loop here, and on the hosted
 * deployment every turn of that loop was a queued job: enqueue, poll at 1.5s, wait to
 * be claimed, poll again. Twelve of those is minutes of round-trip before a single
 * route is fetched, which was most of what a ten-minute build spent. `max_passes`
 * asks for the whole sweep in one request; the passes themselves are unchanged, and
 * so is the per-route spend check. What these tests pin now is that this asks **once**
 * and still reports what it stored.
 */

afterEach(() => vi.restoreAllMocks());

describe("collectRouteEvidence", () => {
  it("asks for the whole sweep in one request, not one request per pass", async () => {
    const rpc = vi.spyOn(client, "rpc").mockResolvedValue({ pairs_needed: 110, fetched: 110 });

    await collectRouteEvidence("trip_1");

    // One walking request, then transit — which is asked for once whatever walking did.
    // Twelve round-trips became one, and that is the whole point of the change.
    expect(rpc).toHaveBeenCalledTimes(2);
    expect(rpc.mock.calls[0][0]).toBe("refresh_routes");
    expect(rpc.mock.calls[0][1]).toEqual({ trip_id: "trip_1", max_passes: 12 });
    expect(rpc).toHaveBeenLastCalledWith("refresh_transit_routes", { trip_id: "trip_1" });
  });

  it("passes the worker's running count straight through", async () => {
    // The routes stage prints this number. It used to be inferred from one reply per
    // pass; it now arrives from the job row as the sweep proceeds, so the count still
    // ticks rather than jumping once at the end.
    const seen: number[] = [];
    vi.spyOn(client, "rpc").mockImplementation((async (
      _method: string,
      _payload?: Record<string, unknown>,
      onProgress?: (n: number) => void,
    ) => {
      onProgress?.(60);
      onProgress?.(110);
      return { pairs_needed: 110, fetched: 110 };
    }) as unknown as typeof client.rpc);

    await collectRouteEvidence("trip_1", (n) => seen.push(n));

    // Mid-sweep and end-of-sweep both reach the caller. The transit leg that follows
    // adds to the same running total, so the final value is past the walking count.
    expect(seen).toContain(60);
    expect(seen).toContain(110);
  });

  it("never throws, so a failed sweep keeps whatever it stored", async () => {
    vi.spyOn(client, "rpc")
      .mockRejectedValueOnce(new Error("Provider HTTP 504"))
      .mockRejectedValueOnce(new Error("Provider HTTP 504"));

    // Both halves failed and the caller still gets a number rather than a throw.
    await expect(collectRouteEvidence("trip_1")).resolves.toBe(0);
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
