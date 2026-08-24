import { rpc } from "../api/client";

/** What one `refresh_routes` call reports. `pairs_needed` is what that call had left to
 *  ask for after the cache was subtracted, so `pairs_needed - fetched` is the remainder. */
interface RouteRefreshReply {
  pairs_needed: number;
  fetched: number;
  /** The sweep stopped on its own clock with pairs still outstanding, so asking
   *  again continues rather than repeats. Absent on an older server. */
  more_pairs?: boolean;
}

/** A ceiling on passes, not on the trip — and it lives on the server now, as
 *  `actions.MAX_ROUTE_PASSES`. The number is unchanged; only the side of the wire it
 *  runs on moved, because each pass used to cost a whole queued job. */
const MAX_PASSES = 12;

/**
 * Ask for walking routes until every pair has one, or until asking stops helping.
 *
 * `refresh_routes` fetches at most `MAX_ROUTE_REQUESTS` — sixty — **new** pairs per
 * call, and eleven selected places already need 110 ordered pairs. Auto-resolve called
 * it once, so every pair past the cap stayed unmeasured; `ROUTE_UNVERIFIED` is fatal for
 * a trip that is not exploring, so those places came back `cannot_currently_fit` with
 * `collect_a_verified_route` beside them and no control that would collect one. That is
 * the "even I assume all of evidence, I can't continue" report.
 *
 * Measured on the owner's Osaka trip: after one pass **30 pairs were still missing**; a
 * second pass fetched all 30, and the plan then scheduled 10 of 10 places.
 *
 * Never throws. A failed or rate-limited pass keeps whatever the earlier passes stored,
 * which is strictly better than the state the trip was already in.
 */
export async function collectRouteEvidence(
  tripId: string,
  /** Called with the running total after each pass, so a caller can say how many routes
   *  have actually been measured. The server's own count -- this reports it, it does not
   *  estimate progress. */
  onProgress?: (stored: number) => void,
): Promise<number> {
  let stored = 0;
  try {
    // Several passes per request, and several requests if the trip needs them.
    //
    // This was one request for the whole sweep, which removed eleven queue round-trips
    // and replaced them with a job that held the single worker for **843 seconds** —
    // starving a three-second plan build behind it until the browser gave up on a
    // build that had not started. `ROUTE_SWEEP_SECONDS` bounds one job at sixty now, so
    // the loop is back, but each turn does as many capped passes as fit in a minute
    // rather than exactly one. Fewer round-trips than the original, and none of them
    // long enough to block the queue.
    for (let call = 0; call < MAX_PASSES; call += 1) {
      const base = stored;
      const reply = await rpc<RouteRefreshReply>(
        "refresh_routes",
        { trip_id: tripId, max_passes: MAX_PASSES },
        // Each job counts from zero, so the running total is the caller's, not the
        // job's — without the base the routes stage would restart at every request.
        (measured) => onProgress?.(base + measured),
      );
      stored = base + reply.fetched;
      onProgress?.(stored);
      // Nothing came back, or nothing is outstanding. Either way asking again is a
      // request that buys nothing.
      if (!reply.fetched || !reply.more_pairs) break;
    }
  } catch {
    /* whatever earlier passes stored still stands */
  }

  // Walking is the *preferred* evidence, not the only kind. OpenRouteService went
  // unreachable on the owner's London trip — 60 of 60 attempts — which left every place
  // ROUTE_UNVERIFIED and the plan unbuildable, with nothing on screen to press. Transit
  // topology is free, comes from a different service, and produces `estimated` routes
  // the optimizer accepts on an Explore trip. Asking for it costs one request when
  // walking already succeeded and rescues the trip when it did not.
  //
  // Measured on London: 0 walking routes, then 24 transit legs, and the plan went from
  // `unavailable` with 0 visits to `provisional` with 5.
  try {
    const transit = await rpc<RouteRefreshReply>("refresh_transit_routes", { trip_id: tripId });
    stored += transit.fetched;
    onProgress?.(stored);
  } catch {
    /* the walking routes, if any, still stand */
  }
  return stored;
}
