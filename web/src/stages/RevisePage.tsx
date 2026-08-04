import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";

import {
  ApiError,
  rpc,
  type CandidateChoice,
  type PlanVersionRecord,
  type QuickAction,
  type RevisionDraft,
  type RevisionRecord,
} from "../api/client";
import { copy, copyFrom, type Language } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { placeNameFrom } from "../shared/names";

const code = (value: string, language: Language) =>
  copyFrom("OPTIMIZER_CODE_TEXT", value, language);

/** Operation labels fall back to the raw name rather than to `⚠ op_x`. */
function operationLabel(operation: string, language: Language): string {
  const label = copy(`op_${operation}`, language);
  return label.startsWith("⚠ ") ? operation : label;
}

/**
 * The revise screen. Free-text GenAI revision is deliberately absent: artifact
 * 033 defers it past the pilot, and `interpret_revision` stays unreferenced here
 * even though the transport allows it. The non-AI quick actions are local, free
 * and deterministic, which is why they stayed in scope.
 */
export function RevisePage() {
  const { tripId = "" } = useParams();
  const { language } = useLanguage();
  const queryClient = useQueryClient();
  const [chosen, setChosen] = useState(0);
  const [flash, setFlash] = useState<string | null>(null);

  const offered = useQuery({
    queryKey: ["quick_actions", tripId],
    queryFn: () => rpc<QuickAction[]>("quick_actions", { trip_id: tripId }),
  });
  const draft = useQuery({
    queryKey: ["revision_draft", tripId],
    queryFn: () => rpc<RevisionDraft | null>("get_revision_draft", { trip_id: tripId }),
  });
  const history = useQuery({
    queryKey: ["revisions", tripId],
    queryFn: () => rpc<RevisionRecord[]>("list_revisions", { trip_id: tripId }),
  });
  const versions = useQuery({
    queryKey: ["plan_versions", tripId],
    queryFn: () => rpc<PlanVersionRecord[]>("list_plan_versions", { trip_id: tripId }),
  });
  // Consequences must name places. Every one of these used to read a truncated
  // place_id, so the owner saw "node_240157284…" where the plan shows a place.
  const choices = useQuery({
    queryKey: ["candidate_choices", tripId],
    queryFn: () => rpc<CandidateChoice[]>("list_candidate_choices", { trip_id: tripId }),
  });

  async function refresh() {
    await Promise.all(
      ["revision_draft", "revisions", "plan_versions", "quick_actions"].map((key) =>
        queryClient.invalidateQueries({ queryKey: [key, tripId] }),
      ),
    );
    await queryClient.invalidateQueries({ queryKey: ["journey", tripId] });
  }

  const fail = (error: unknown) =>
    setFlash(error instanceof ApiError ? code(error.code, language) : String(error));

  const propose = useMutation({
    mutationFn: (operation: QuickAction) =>
      rpc<RevisionDraft>("propose_revision", {
        trip_id: tripId,
        operation,
        replace_pending: true,
      }),
    onSuccess: async () => {
      setFlash(null);
      await refresh();
    },
    onError: fail,
  });

  const applyRevision = useMutation({
    mutationFn: () => rpc<unknown>("apply_revision", { trip_id: tripId }),
    onSuccess: async () => {
      setFlash(copy("revision_applied", language));
      await refresh();
    },
    onError: fail,
  });

  const discard = useMutation({
    mutationFn: () => rpc<unknown>("discard_revision_draft", { trip_id: tripId }),
    onSuccess: async () => {
      setFlash(copy("revision_discarded", language));
      await refresh();
    },
    onError: fail,
  });

  const restore = useMutation({
    mutationFn: (version_id: string) =>
      rpc<unknown>("restore_plan_version", { trip_id: tripId, version_id }),
    onSuccess: async () => {
      setFlash(copy("version_restored", language));
      await refresh();
    },
    onError: fail,
  });

  if (offered.isPending || draft.isPending) return <p>{copy("loading", language)}</p>;
  if (offered.isError) return <p className="field-error">⚠ {offered.error.message}</p>;

  const names = new Map(
    (choices.data ?? []).map((choice) => [
      choice.place_id,
      placeNameFrom(choice.candidate?.data, language, choice.place_id),
    ]),
  );
  const place = (placeId: string) => names.get(placeId) ?? placeId.slice(0, 16);

  const actions = offered.data;
  const pending = draft.data;
  const consequences = pending?.consequences ?? null;
  const canApply = Boolean(pending?.can_apply ?? consequences?.can_apply);

  const groups: [string, string[]][] = consequences
    ? [
        [
          copy("moved_items", language),
          consequences.moved.map(
            (move) =>
              `${place(move.place_id)} ${move.from.date} ${move.from.start} → ${move.to.date} ${move.to.start}`,
          ),
        ],
        [copy("added_items", language), consequences.added.map(place)],
        [copy("removed_items", language), consequences.removed.map(place)],
        [
          copy("shortened_items", language),
          consequences.shortened.map(
            (item) =>
              `${place(item.place_id)} ${item.from_minutes}→${item.to_minutes} ${copy("minutes", language)}`,
          ),
        ],
        [
          copy("lengthened_items", language),
          consequences.lengthened.map(
            (item) =>
              `${place(item.place_id)} ${item.from_minutes}→${item.to_minutes} ${copy("minutes", language)}`,
          ),
        ],
        [
          copy("displaced_items", language),
          consequences.displaced.map(
            (item) => `${place(item.place_id)} · ${code(item.reason, language)}`,
          ),
        ],
        [
          copy("new_warnings", language),
          consequences.warnings.new.map((value) => code(value, language)),
        ],
        [
          copy("cleared_warnings", language),
          consequences.warnings.cleared.map((value) => code(value, language)),
        ],
      ]
    : [];

  return (
    <section className="stage-card revise-screen">
      <header className="money-head">
        <h1>{copy("revision", language)}</h1>
        <p>{copy("revision_help", language)}</p>
      </header>

      {flash ? (
        <p className="setup-flash" aria-live="polite">
          {flash}
        </p>
      ) : null}

      <div className="revise-pick">
        <label>
          {copy("quick_action", language)}
          <select onChange={(event) => setChosen(Number(event.target.value))} value={chosen}>
            {actions.map((item, index) => (
              <option key={`${item.operation}-${index}`} value={index}>
                {operationLabel(item.operation, language)}
                {item.arguments.place_id ? ` · ${place(String(item.arguments.place_id))}` : ""}
              </option>
            ))}
          </select>
        </label>
        <button
          className="setup-primary"
          disabled={!actions.length || propose.isPending}
          onClick={() => actions[chosen] && propose.mutate(actions[chosen])}
          type="button"
        >
          {copy("run_action", language)}
        </button>
      </div>
      {actions.length === 0 ? (
        <p className="setup-hint">{copy("revision_needs_plan", language)}</p>
      ) : null}

      {pending ? (
        <div className="revise-draft">
          <h2 className="money-eyebrow">
            {copy("pending_revision", language)}: {operationLabel(pending.operation, language)}
          </h2>

          {pending.assumptions?.length ? (
            <p className="setup-hint">
              {copy("revision_assumptions", language)}:{" "}
              {pending.assumptions.map((value) => code(value, language)).join(", ")}
            </p>
          ) : null}

          {pending.explanation ? (
            <>
              <p className="setup-hint">
                {copy("variant", language)}:{" "}
                {copy(pending.explanation.variant_id, language)} ·{" "}
                {copy(pending.explanation.status, language)}
              </p>
              {pending.explanation.unscheduled.length ? (
                <ul className="revise-list">
                  {pending.explanation.unscheduled.map((item) => (
                    <li key={item.place_id}>
                      {place(item.place_id)} · {code(item.reason, language)}
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : null}

          {consequences ? (
            <>
              <p className="setup-hint">
                {consequences.changed_dates.length
                  ? `${copy("changed_days", language)}: ${consequences.changed_dates.join(", ")}`
                  : copy("no_changes", language)}
              </p>
              <div className="money-table-scroll">
                {/* derives-from: element 27 .transactions-table as .money-table */}
                <table className="money-table">
                  <thead>
                    <tr>
                      <th>{copy("dimension", language)}</th>
                      <th>{copy("before", language)}</th>
                      <th>{copy("after", language)}</th>
                      <th>{copy("delta", language)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(consequences.metrics).map(([key, item]) => (
                      <tr key={key}>
                        <td>{copy(key, language)}</td>
                        <td className="money-num">{item.before}</td>
                        <td className="money-num">{item.after}</td>
                        <td
                          className={`money-num ${
                            item.delta > 0 ? "money-over" : item.delta < 0 ? "money-under" : ""
                          }`}
                        >
                          {item.delta > 0 ? `+${item.delta}` : item.delta}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {groups
                .filter(([, entries]) => entries.length)
                .map(([label, entries]) => (
                  <p className="revise-group" key={label}>
                    <strong>{label}</strong>: {entries.join(" · ")}
                  </p>
                ))}
              {/* A blocked revision says why rather than offering a dead button. */}
              {!consequences.can_apply ? (
                <p className="money-note money-note-warn">
                  <b aria-hidden="true">⚠</b>
                  <span>{copy("revision_blocked", language)}</span>
                </p>
              ) : null}
            </>
          ) : null}

          <div className="setup-actions">
            <button
              className="setup-primary"
              disabled={!canApply || applyRevision.isPending}
              onClick={() => applyRevision.mutate()}
              type="button"
            >
              {copy("apply_revision", language)}
            </button>
            <button disabled={discard.isPending} onClick={() => discard.mutate()} type="button">
              {copy("cancel_revision", language)}
            </button>
          </div>
        </div>
      ) : null}

      {history.data?.length ? (
        <details className="revise-history">
          <summary>
            {copy("revision_history", language)} ({history.data.length})
          </summary>
          <ul>
            {[...history.data].reverse().map((record) => (
              <li key={`${record.created_at}-${record.to_version_id}`}>
                {record.created_at.slice(0, 16)} ·{" "}
                {operationLabel(record.operation, language)} ·{" "}
                <code>{record.from_version_id.slice(5, 17)}</code> →{" "}
                <code>{record.to_version_id.slice(5, 17)}</code>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {/* Restoring never deletes: it writes another version pointing at the old
          snapshot, so the history stays append-only. */}
      {versions.data && versions.data.length > 1 ? (
        <details className="revise-versions">
          <summary>
            {copy("active_plan", language)} ({versions.data.length})
          </summary>
          <ul>
            {versions.data.map((version) => (
              <li key={version.version_id}>
                <code>{version.version_id.slice(5, 17)}</code> · {version.cause}{" "}
                <button
                  disabled={restore.isPending}
                  onClick={() => restore.mutate(version.version_id)}
                  type="button"
                >
                  {copy("restore_version", language)}
                </button>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
