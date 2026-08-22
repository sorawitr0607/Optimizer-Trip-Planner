import { rpc, type Basemap } from "../api/client";

const PREFIX = "otp:basemap:";

function read(tripId: string): Basemap | null {
  try {
    const held = JSON.parse(localStorage.getItem(PREFIX + tripId) ?? "null") as Basemap | null;
    if (held?.expires_at && Date.parse(held.expires_at) > Date.now()) return held;
    localStorage.removeItem(PREFIX + tripId);
  } catch {
    // Corrupt or blocked browser storage falls back to the authoritative server read.
  }
  return null;
}

function write(tripId: string, value: Basemap | null): void {
  if (!value?.expires_at || Date.parse(value.expires_at) <= Date.now()) return;
  try {
    localStorage.setItem(PREFIX + tripId, JSON.stringify(value));
  } catch {
    // A private window or storage quota must not break the map.
  }
}

/** Reuse the large, immutable city map until the server's own evidence expiry. */
export async function loadBasemap(tripId: string, capture: boolean): Promise<Basemap | null> {
  if (!capture && typeof localStorage !== "undefined") {
    const held = read(tripId);
    if (held) return held;
  }
  const value = await rpc<Basemap | null>(capture ? "get_basemap" : "refresh_basemap", {
    trip_id: tripId,
  });
  if (!capture && typeof localStorage !== "undefined") write(tripId, value);
  return value;
}
