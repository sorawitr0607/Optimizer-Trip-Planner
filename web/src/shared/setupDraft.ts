import type { SetupDraft } from "../api/client";

/**
 * The whole setup payload, rebuilt by hand with new dates in it.
 *
 * `save_setup` defaults every field it is not sent, so a field missing from this
 * list is silently reset the moment new dates are saved from anywhere — the stay
 * planner, or the optimize screen's "add a day". Adding a field to the setup draft
 * means adding it here; its own history is why `active_start` / `active_end` are
 * carried explicitly.
 */
export function wholeDraftWithDates(
  stored: SetupDraft | null,
  start: string,
  end: string,
): Record<string, unknown> {
  const payload = stored?.snapshot.data ?? {};
  const owner = payload.owner ?? {};
  const basics = payload.trip_basics ?? {};
  return {
    start_date: start,
    end_date: end,
    arrival_time: basics.arrival_time ?? null,
    // Carried explicitly, because this function's own docstring is the reason: a field
    // omitted here is a field `save_setup` resets to its default. Adding one to the draft
    // without adding it to this list silently erases the owner's answer the moment they
    // pick dates from the stay planner.
    active_start: basics.active_start ?? null,
    active_end: basics.active_end ?? null,
    departure_time: basics.departure_time ?? null,
    accommodation_status: basics.accommodation_status ?? "unknown",
    owner_age: owner.age ?? null,
    main_style: owner.main_style ?? [],
    also_enjoy: owner.also_enjoy ?? [],
    avoid: owner.avoid ?? [],
    comfort: owner.comfort ?? [],
    owner_description: owner.description ?? "",
    owner_must_respect: (owner.must_respect ?? []).join("\n"),
    owner_nationality: owner.nationality ?? null,
    travellers: (payload.travellers ?? []).map((member) => ({
      ...member,
      age: member.age ?? 0,
    })),
    confirmed: true,
  };
}
