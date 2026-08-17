import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import { ApiError, rpc, type Trip } from "../api/client";
import { copy, copyFormat } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";

/**
 * Deleting one trip, from wherever the owner is looking at it.
 *
 * It first landed only on the landing page's slot list, and the report was that the
 * *active* slot — the one in the sidebar, on every screen — still could not be
 * deleted. So the control is one component used in both places rather than two
 * confirmations that could drift apart.
 *
 * The confirmation is type-the-name, which is the POC's own design for this action
 * (`delete_trip_confirm` was already in the catalogue): the deletion is irreversible
 * and a button you can hit twice by reflex is not a confirmation. No `confirm()`
 * dialog — a browser modal blocks the page it is asked from.
 */

export interface DeleteTripProps {
  trip: Trip;
  /** Where to go afterwards. The sidebar deletes the trip being *looked at*, so it
   *  cannot simply re-render the page it is on. */
  onDeleted?: () => void;
  /** `compact` is the sidebar: 260px, so the warning is dropped to its first clause. */
  compact?: boolean;
}

export function DeleteTrip({ trip, onDeleted, compact = false }: DeleteTripProps) {
  const { language } = useLanguage();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");

  const remove = useMutation({
    mutationFn: () => rpc<null>("delete_trip", { trip_id: trip.trip_id }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["trips"] });
      queryClient.removeQueries({ queryKey: ["journey", trip.trip_id] });
      onDeleted?.();
    },
  });

  // Whitespace only, because a name is typed by a person: "Family Trip " must count.
  const matches = typed.trim() === trip.name.trim() && trip.name.trim() !== "";
  const errorCode =
    remove.error instanceof ApiError ? remove.error.code : remove.error?.message;

  if (!confirming) {
    return (
      // derives-from: element 23 .btn-reset-trip as .trip-slot-open
      <button className="trip-slot-open" onClick={() => setConfirming(true)} type="button">
        <Trash2 aria-hidden="true" size={14} /> {copy("delete_trip", language)}
      </button>
    );
  }

  return (
    <div className="trip-slot-confirm">
      <p>
        {copyFormat("delete_trip_warning", language, {
          name: trip.name,
          destination: trip.destination,
        })}
      </p>
      <label>
        {copyFormat("delete_trip_confirm", language, { name: trip.name })}
        <input
          autoComplete="off"
          autoCorrect="off"
          autoFocus
          onChange={(event) => setTyped(event.target.value)}
          spellCheck={false}
          type="text"
          value={typed}
        />
      </label>
      {errorCode ? <p className="field-error">⚠ {errorCode}</p> : null}
      <div className={`trip-slot-actions${compact ? " compact" : ""}`}>
        <button
          className="trip-slot-delete"
          disabled={!matches || remove.isPending}
          onClick={() => remove.mutate()}
          type="button"
        >
          {remove.isPending ? copy("deleting", language) : copy("delete_trip", language)}
        </button>
        <button
          onClick={() => {
            setConfirming(false);
            setTyped("");
          }}
          type="button"
        >
          {copy("cancel", language)}
        </button>
      </div>
    </div>
  );
}
