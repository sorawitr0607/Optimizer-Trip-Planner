import { rpc } from "../api/client";

/** What one `refresh_routes` call reports. `pairs_needed` is what that call had left to
 *  ask for after the cache was subtracted, so `pairs_needed - fetched` is the remainder. */
interface RouteRefreshReply {
  pairs_needed: number;
  fetched: number;
}

/** A ceiling on passes, not on the trip. Sixty new pairs a pass covers eleven places in
 *  two and forty-one places in the twenty-eight a real shortlist would need — this stops
 *  a stuck provider turning one button into an unbounded run, and the remainder is still
 *  reachable by pressing again. */
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
export async function collectRouteEvidence(tripId: string): Promise<void> {
  for (let pass = 0; pass < MAX_PASSES; pass += 1) {
    let reply: RouteRefreshReply;
    try {
      reply = await rpc<RouteRefreshReply>("refresh_routes", { trip_id: tripId });
    } catch {
      return;
    }
    // Everything that was outstanding arrived, or nothing did. Either way there is no
    // reason to ask a third time: the cap is per call, so a pass that fetched nothing
    // will fetch nothing again.
    if (reply.fetched === 0 || reply.pairs_needed <= reply.fetched) return;
  }
}
