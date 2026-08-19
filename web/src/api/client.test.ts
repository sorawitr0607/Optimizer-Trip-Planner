import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, rpc } from "./client";

/** Queue of replies, consumed one per fetch, so a polling sequence can be scripted. */
function stubFetch(replies: { status: number; body: string }[]) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      const next = replies.shift() ?? { status: 500, body: '{"code":"ran_out"}' };
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
