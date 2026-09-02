import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, rpc } from "./client";

/** One scripted reply: an HTTP answer, or a network-level `fetch` rejection. */
type Reply = { status: number; body: string } | { reject: string };

/** Queue of replies, consumed one per fetch, so a polling sequence can be scripted. */
function stubFetch(replies: Reply[]) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      const next = replies.shift() ?? { status: 500, body: '{"code":"ran_out"}' };
      // What a browser actually does below HTTP: a bare TypeError, no status, no body.
      if ("reject" in next) throw new TypeError(next.reject);
      return new Response(next.body, {
        status: next.status,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("rpc", () => {
  it("treats a JSON null as the answer, not as an empty response", async () => {
    // delete_trip, clear_candidate_choice, delete_cost_item and
    // discard_revision_draft all return null on success. Reading that as "empty"
    // made every one of them throw while the delete had in fact happened.
    stubFetch([{ status: 200, body: "null" }]);
    await expect(rpc("delete_trip", { trip_id: "trip_x" })).resolves.toBeNull();
  });

  it("throws when the body is genuinely empty", async () => {
    stubFetch([{ status: 200, body: "" }]);
    await expect(rpc("list_trips")).rejects.toBeInstanceOf(ApiError);
  });

  it("keeps the server's code when the error body is JSON", async () => {
    stubFetch([{ status: 402, body: '{"code":"paid_cap_reached"}' }]);
    await expect(rpc("discover_places")).rejects.toMatchObject({ code: "paid_cap_reached" });
  });

  it("survives an error body that is not JSON at all", async () => {
    // What a platform's own 500 page looks like. Parsing it as JSON throws, and
    // the throw used to escape as a TypeError instead of a usable ApiError.
    stubFetch([{ status: 500, body: "A server error has occurred" }]);
    await expect(rpc("list_trips")).rejects.toMatchObject({ code: "http_500" });
  });

  it("polls a queued job until it finishes and returns its result", async () => {
    const calls = stubFetch([
      { status: 202, body: '{"job_id":"job_1","status":"queued"}' },
      { status: 200, body: '{"job_id":"job_1","status":"running","error":null,"result":null}' },
      { status: 200, body: '{"job_id":"job_1","status":"done","error":null,"result":{"places":3}}' },
    ]);
    await expect(rpc("discover_places", { trip_id: "trip_x" })).resolves.toEqual({ places: 3 });
    expect(calls[0]).toBe("/api/discover_places");
    expect(calls[1]).toBe("/api/job_status");
  }, 20_000);

  it("keeps polling through a network failure instead of failing the build", async () => {
    /**
     * "Failed to fetch" while building the plan, reported by the owner.
     *
     * A build is 30-90 seconds against a 1.5-second poll, so one run asks about sixty
     * times, and `fetch` rejects with a bare `TypeError` for anything below HTTP -- a
     * cold start closing an idle socket, a DNS blip, a phone changing network. One
     * such rejection used to throw straight out of the loop and fail a build the
     * worker was finishing perfectly.
     */
    const calls = stubFetch([
      { status: 202, body: '{"job_id":"job_2","status":"queued"}' },
      { reject: "Failed to fetch" },
      { status: 200, body: '{"job_id":"job_2","status":"running","error":null,"result":null}' },
      { reject: "Failed to fetch" },
      { status: 200, body: '{"job_id":"job_2","status":"done","error":null,"result":{"places":7}}' },
    ]);
    await expect(rpc("generate_plan_preview", { trip_id: "trip_x" })).resolves.toEqual({
      places: 7,
    });
    // Every poll was made, including the two that never arrived.
    expect(calls.length).toBe(5);
  }, 20_000);

  it("still surfaces a refusal the server actually answered with", async () => {
    // The other side of the retry: an ApiError means the server replied, so repeating
    // the poll would bury a real 404 or 403 under a five-minute wait.
    stubFetch([
      { status: 202, body: '{"job_id":"job_9","status":"queued"}' },
      { status: 403, body: '{"code":"not_your_trip"}' },
    ]);
    await expect(
      rpc("generate_plan_preview", { trip_id: "trip_x" }),
    ).rejects.toMatchObject({ code: "not_your_trip" });
  }, 20_000);

  it("hands the caller each stage the worker reports, and nothing while it is queued", async () => {
    // `/places` is one queued job, so this callback is the only way that screen can
    // know where a 30-90s wait has got to. A queued job reports nothing at all --
    // which is the honest difference between "no worker has this" and "a worker
    // started", and the screen shows a rotating line for the first.
    const reached: number[] = [];
    stubFetch([
      { status: 202, body: '{"job_id":"job_3","status":"queued"}' },
      { status: 200, body: '{"job_id":"job_3","status":"queued","progress":null,"error":null,"result":null}' },
      { status: 200, body: '{"job_id":"job_3","status":"running","progress":0,"error":null,"result":null}' },
      { status: 200, body: '{"job_id":"job_3","status":"running","progress":2,"error":null,"result":null}' },
      { status: 200, body: '{"job_id":"job_3","status":"done","progress":4,"error":null,"result":{"places":3}}' },
    ]);
    await expect(
      rpc("discover_places", { trip_id: "trip_x" }, (n) => reached.push(n)),
    ).resolves.toEqual({ places: 3 });
    // Including the 4 that arrives with the result: the last stage is reported on
    // the same poll that ends the wait, and dropping it would leave the list one
    // short of the answer it just delivered.
    expect(reached).toEqual([0, 2, 4]);
  }, 20_000);

  it("keeps waiting while the job is still reporting, and gives up when it goes quiet", async () => {
    // The deadline used to be a ceiling on total runtime. `refresh_routes` sweeps its
    // passes in one job now, and a measured run stored 462 routes in 843 seconds --
    // finished perfectly, while the browser had already thrown `job_timeout` at 300.
    // Silence is the thing worth reporting, not slowness.
    vi.useFakeTimers();
    try {
      let polls = 0;
      vi.stubGlobal("fetch", vi.fn(async (url: string) => {
        if (url.endsWith("/api/refresh_routes")) {
          return new Response('{"job_id":"job_9","status":"queued"}', { status: 202 });
        }
        polls += 1;
        // Six minutes of work, reported every other poll, then done. Under the old
        // flat ceiling this threw before it ever finished.
        vi.setSystemTime(new Date(Date.now() + 120_000));
        const body = polls < 4
          ? `{"job_id":"job_9","status":"running","progress":${polls * 10},"error":null,"result":null}`
          : '{"job_id":"job_9","status":"done","progress":60,"error":null,"result":{"fetched":60}}';
        return new Response(body, { status: 200 });
      }));

      const call = rpc("refresh_routes", { trip_id: "t", max_passes: 12 });
      await vi.advanceTimersByTimeAsync(60_000);
      await expect(call).resolves.toEqual({ fetched: 60 });
    } finally {
      vi.useRealTimers();
    }
  }, 20_000);

  it("still gives up on a job that is claimed and then says nothing", async () => {
    vi.useFakeTimers();
    try {
      vi.stubGlobal("fetch", vi.fn(async (url: string) => {
        if (url.endsWith("/api/discover_places")) {
          return new Response('{"job_id":"job_a","status":"queued"}', { status: 202 });
        }
        // Claimed, reported 0 once, and then frozen: the count never moves again.
        vi.setSystemTime(new Date(Date.now() + 60_000));
        return new Response(
          '{"job_id":"job_a","status":"running","progress":0,"error":null,"result":null}',
          { status: 200 },
        );
      }));

      const call = rpc("discover_places", { trip_id: "t" });
      const settled = expect(call).rejects.toMatchObject({ code: "job_timeout" });
      await vi.advanceTimersByTimeAsync(60_000);
      await settled;
    } finally {
      vi.useRealTimers();
    }
  }, 20_000);

  it("raises the job's own error when it fails", async () => {
    stubFetch([
      { status: 202, body: '{"job_id":"job_2","status":"queued"}' },
      { status: 200, body: '{"job_id":"job_2","status":"failed","error":"overpass_unavailable","result":null}' },
    ]);
    await expect(rpc("refresh_routes", { trip_id: "t" })).rejects.toMatchObject({
      code: "overpass_unavailable",
    });
  }, 20_000);
});
