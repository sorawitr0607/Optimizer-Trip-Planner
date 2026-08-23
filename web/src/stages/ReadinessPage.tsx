import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";

import {
  ApiError,
  rpc,
  type ChecklistItem,
  type ChecklistProposal,
  type ChecklistReadiness,
  type ChecklistVocabulary,
} from "../api/client";
import { copy, type Language } from "../i18n/copy";
import { checklistIcon } from "../shared/tagIcons";
import { useLanguage } from "../i18n/LanguageProvider";
import { localizedTask, taskTitle } from "../shared/checklistText";

/**
 * `expected_authority` and `authority_type` hold stable codes, but the field also
 * accepts owner-entered text, so an unknown value keeps its literal rather than
 * rendering as machine output.
 */
function codeOrLiteral(value: string, language: Language): string {
  const text = copy(value, language);
  return text.startsWith("⚠ ") ? value : text;
}

const title = (item: ChecklistItem, language: Language) =>
  taskTitle(item, language);

const consequence = (item: ChecklistItem, language: Language) =>
  localizedTask(
    item,
    "why_",
    item.consequence_code ?? item.template_id,
    item.consequence ?? "",
    language,
  );

// The decision-relevant counts. `total` and `dismissed` are derivable from the
// board itself, so the summary line does not repeat them.
const SUMMARY_COUNTS = ["open", "required_open", "unverified_required", "overdue", "due_soon"];

export function ReadinessPage() {
  const { tripId = "" } = useParams();
  const { language } = useLanguage();
  const queryClient = useQueryClient();
  const [categories, setCategories] = useState<string[]>([]);
  const [drafts, setDrafts] = useState<Record<string, { progress: string; note: string }>>({});
  const [flash, setFlash] = useState<string | null>(null);

  const words = useQuery({
    queryKey: ["checklist_vocabulary"],
    queryFn: () => rpc<ChecklistVocabulary>("checklist_vocabulary"),
    staleTime: Infinity,
  });
  const proposal = useQuery({
    queryKey: ["checklist_proposal", tripId],
    queryFn: () => rpc<ChecklistProposal>("propose_checklist", { trip_id: tripId }),
  });
  const items = useQuery({
    queryKey: ["checklist_items", tripId],
    queryFn: () => rpc<ChecklistItem[]>("list_checklist_items", { trip_id: tripId }),
  });
  const readiness = useQuery({
    queryKey: ["checklist_readiness", tripId],
    queryFn: () => rpc<ChecklistReadiness>("checklist_readiness", { trip_id: tripId }),
  });

  async function refresh() {
    setDrafts({});
    await Promise.all(
      ["checklist_proposal", "checklist_items", "checklist_readiness"].map((key) =>
        queryClient.invalidateQueries({ queryKey: [key, tripId] }),
      ),
    );
  }

  const apply = useMutation({
    mutationFn: () =>
      rpc<{ added: number; deadlines_changed: number; dismissed: number }>(
        "apply_checklist_proposal",
        { trip_id: tripId },
      ),
    onSuccess: async (result) => {
      setFlash(
        `${copy("checklist_applied", language)} +${result.added} / ~${result.deadlines_changed} / -${result.dismissed}`,
      );
      await refresh();
    },
    onError: (error) => setFlash(error instanceof ApiError ? error.code : String(error)),
  });

  const setProgress = useMutation({
    mutationFn: (input: { item_id: string; progress: string; note: string | null }) =>
      rpc<ChecklistItem>("set_checklist_progress", { trip_id: tripId, ...input }),
    onSuccess: async () => {
      setFlash(copy("task_saved", language));
      await refresh();
    },
    onError: (error) => setFlash(error instanceof ApiError ? error.code : String(error)),
  });

  const setDismissed = useMutation({
    mutationFn: (input: { item_id: string; dismissed: boolean }) =>
      rpc<ChecklistItem>("set_checklist_dismissed", { trip_id: tripId, ...input }),
    onSuccess: async () => {
      setFlash(copy("task_restored", language));
      await refresh();
    },
  });

  if (items.isPending || words.isPending) return <p>{copy("loading", language)}</p>;
  if (items.isError) return <p className="field-error">⚠ {items.error.message}</p>;
  if (words.isError) return <p className="field-error">⚠ {words.error.message}</p>;

  const vocabulary = words.data;
  const preview = proposal.data;
  const pending =
    (preview?.additions.length ?? 0) +
    (preview?.removals.length ?? 0) +
    (preview?.deadline_changes.length ?? 0);

  const active = items.data.filter((item) => !item.dismissed);
  const dismissed = items.data.filter((item) => item.dismissed);
  const shown = categories.length
    ? active.filter((item) => categories.includes(item.category))
    : active;

  return (
    <section className="stage-card readiness-screen">
      <header className="money-head">
        <h1>{copy("checklist", language)}</h1>
        <p>{copy("checklist_help", language)}</p>
      </header>

      {flash ? (
        <p className="setup-flash" aria-live="polite">
          {flash}
        </p>
      ) : null}

      {readiness.data ? (
        <p className="money-note money-note-plain">
          <b aria-hidden="true">◇</b>
          <span>
            {copy("readiness", language)}: {copy(readiness.data.state, language)}
            {SUMMARY_COUNTS.filter((key) => readiness.data.counts[key] !== undefined).map((key) => (
              <span key={key}>
                {" "}
                · {copy(key, language)} {readiness.data.counts[key]}
              </span>
            ))}
          </span>
        </p>
      ) : null}

      {/* Nothing is applied silently: additions, removals and deadline moves are
          previewed first, and the panel opens when there is anything to see. */}
      {pending > 0 ? (
        <details className="readiness-preview" open>
          <summary>
            {copy("checklist_preview", language)} ({pending})
          </summary>
          <ul>
            {preview?.additions.map((item) => (
              <li key={`add-${item.generated_key ?? item.title}`}>
                ➕ {title(item, language)} · {copy(item.timing, language)}
              </li>
            ))}
            {preview?.removals.map((item) => (
              <li key={`remove-${item.generated_key ?? item.title}`}>
                ➖ {title(item, language)} · {copy("will_be_dismissed", language)}
              </li>
            ))}
            {preview?.deadline_changes.map((change) => (
              <li key={`due-${change.title}`}>
                📅 {change.title} · {change.from.due_date || "—"} → {change.to.due_date || "—"}
              </li>
            ))}
          </ul>
          <button
            className="setup-primary"
            disabled={apply.isPending}
            onClick={() => apply.mutate()}
            type="button"
          >
            {copy("apply_checklist", language)}
          </button>
        </details>
      ) : (
        <p className="setup-hint">{copy("checklist_current", language)}</p>
      )}

      <div className="money-filters">
        <span className="money-filter-label">{copy("category", language)}</span>
        {[...new Set(active.map((item) => item.category))].map((category) => (
          <button
            aria-pressed={categories.includes(category)}
            className="money-chip"
            key={category}
            onClick={() =>
              setCategories((current) =>
                current.includes(category)
                  ? current.filter((value) => value !== category)
                  : [...current, category],
              )
            }
            type="button"
          >
            {/* Same second channel as the setup chips: the word stays, the glyph is
                `aria-hidden`, and the row becomes scannable. See `shared/tagIcons`. */}
            {(() => {
              const Icon = checklistIcon(category);
              return <Icon aria-hidden="true" className="money-chip-icon" size={14} />;
            })()}
            {copy(category, language)}
          </button>
        ))}
      </div>

      {vocabulary.timing_buckets.map((bucket) => {
        const bucketItems = shown
          .filter((item) => item.timing === bucket)
          .sort((left, right) => title(left, language).localeCompare(title(right, language)));
        if (!bucketItems.length) return null;
        return (
          <section key={bucket}>
            <h2 className="money-eyebrow">{copy(bucket, language)}</h2>
            <ul className="readiness-items">
              {bucketItems.map((item) => {
                const draft = drafts[item.item_id] ?? {
                  progress: item.progress,
                  note: item.note ?? "",
                };
                const moved =
                  draft.progress !== item.progress || draft.note !== (item.note ?? "");
                const why = consequence(item, language);
                return (
                  // derives-from: element 26 .recent-row-item as .readiness-item
                  <li className="readiness-item" key={item.item_id}>
                    <div className="readiness-item-head">
                      <strong>{title(item, language)}</strong>
                      <span className="money-row-meta">
                        {copy(item.requirement_level, language)} ·{" "}
                        {copy(`progress_${item.progress}`, language)} ·{" "}
                        {copy(`evidence_${item.evidence_state}`, language)}
                        {item.due_date ? ` · ${copy("due", language)} ${item.due_date}` : ""}
                      </span>
                      {why ? (
                        <span className="money-row-note">
                          {copy("consequence", language)}: {why}
                        </span>
                      ) : null}
                      {item.expected_authority ? (
                        <span className="money-row-note">
                          {copy("expected_authority", language)}:{" "}
                          {codeOrLiteral(item.expected_authority, language)}
                          {item.authority_type
                            ? ` · ${codeOrLiteral(item.authority_type, language)}`
                            : ""}
                        </span>
                      ) : null}
                      {item.source_url ? (
                        <a href={item.source_url} rel="noreferrer" target="_blank">
                          {copy("source", language)}
                        </a>
                      ) : null}
                    </div>
                    <div className="readiness-item-controls">
                      <label>
                        {copy("progress", language)}
                        <select
                          onChange={(event) =>
                            setDrafts((current) => ({
                              ...current,
                              [item.item_id]: { ...draft, progress: event.target.value },
                            }))
                          }
                          value={draft.progress}
                        >
                          {vocabulary.progress_states.map((state) => (
                            <option key={state} value={state}>
                              {copy(`progress_${state}`, language)}
                            </option>
                          ))}
                        </select>
                      </label>
                      {draft.progress === "not_applicable" ? (
                        <label>
                          {copy("not_applicable_reason", language)}
                          <input
                            autoComplete="off"
                            onChange={(event) =>
                              setDrafts((current) => ({
                                ...current,
                                [item.item_id]: { ...draft, note: event.target.value },
                              }))
                            }
                            type="text"
                            value={draft.note}
                          />
                        </label>
                      ) : null}
                      {moved ? (
                        <button
                          disabled={setProgress.isPending}
                          onClick={() =>
                            setProgress.mutate({
                              item_id: item.item_id,
                              progress: draft.progress,
                              note: draft.note || null,
                            })
                          }
                          type="button"
                        >
                          {copy("save_task", language)}
                        </button>
                      ) : null}
                      {/* Dismiss rather than delete, so nothing silently disappears. */}
                      <button
                        onClick={() =>
                          setDismissed.mutate({ item_id: item.item_id, dismissed: true })
                        }
                        type="button"
                      >
                        {copy("dismiss_task", language)}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}

      {dismissed.length ? (
        <details className="readiness-dismissed">
          <summary>
            {copy("dismissed_history", language)} ({dismissed.length})
          </summary>
          <ul>
            {dismissed.map((item) => (
              <li key={item.item_id}>
                {title(item, language)} · {copy(item.timing, language)}{" "}
                <button
                  onClick={() =>
                    setDismissed.mutate({ item_id: item.item_id, dismissed: false })
                  }
                  type="button"
                >
                  {copy("restore_task", language)}
                </button>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {active.length === 0 ? (
        <p className="setup-hint">{copy("checklist_needs_setup", language)}</p>
      ) : null}
    </section>
  );
}
