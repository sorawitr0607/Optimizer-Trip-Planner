import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useParams } from "react-router";

import {
  rpc,
  type CostItem,
  type CostTotals,
  type SetupDraft,
  type SplitRow,
  type SplitSummary,
} from "../api/client";
import { copy, copyFormat } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { categoryName, Donut, Meters, money, Note, Required, Tag, Tile, travellerNames, type CostCategory } from "./money";

const TAGS = ["transport", "accommodation", "activity", "food", "fees", "shopping", "other"];
const CURRENCIES = ["THB", "TWD", "JPY", "KRW", "CNY", "USD"];

/** The donor's four, in its own order. The mode used to be *inferred* from how
 *  many people were ticked -- one meant single_payer and anything else meant an
 *  equal split -- so "we split this three ways but Ake only had a drink" could
 *  not be said at all, and choosing a mode was not a thing the screen offered. */
const MODES = ["equal_all", "selected", "single_payer", "manual"] as const;
type Mode = (typeof MODES)[number];

interface Draft {
  label: string;
  original_amount: string;
  original_currency: string;
  paid_by: string;
  participants: string[];
  mode: Mode;
  /** Keyed by traveller, held as typed text so a half-entered "1" is not 1. */
  allocation: Record<string, string>;
  notes: string;
  tag: string;
  cost_id: string;
}

const EMPTY: Draft = {
  label: "",
  original_amount: "",
  original_currency: "THB",
  paid_by: "owner",
  participants: [],
  mode: "equal_all",
  allocation: {},
  notes: "",
  tag: "other",
  cost_id: "",
};

/** Transactions with the aggregates above them, as the donor arranged it. */
export function SplitPage() {
  const { tripId = "" } = useParams();
  const { language } = useLanguage();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [filters, setFilters] = useState<{ who?: string; category?: string }>({});

  const summary = useQuery({
    queryKey: ["split_summary", tripId],
    queryFn: () => rpc<SplitSummary>("split_summary", { trip_id: tripId }),
  });
  const rows = useQuery({
    queryKey: ["split_rows", tripId],
    queryFn: () => rpc<SplitRow[]>("list_split_rows", { trip_id: tripId }),
  });
  const setup = useQuery({
    queryKey: ["setup", tripId],
    queryFn: () => rpc<SetupDraft | null>("get_setup", { trip_id: tripId }),
  });
  const costs = useQuery({
    queryKey: ["cost_items", tripId],
    queryFn: () => rpc<CostItem[]>("list_cost_items", { trip_id: tripId }),
  });
  const totals = useQuery({
    queryKey: ["cost_totals", tripId],
    queryFn: () => rpc<CostTotals>("cost_totals", { trip_id: tripId }),
  });
  const categoryList = useQuery({
    queryKey: ["cost_categories", tripId],
    queryFn: () => rpc<CostCategory[]>("cost_categories", { trip_id: tripId }),
  });
  const cardholder = useQuery({
    queryKey: ["split_cardholder", tripId],
    queryFn: () => rpc<string>("get_split_cardholder", { trip_id: tripId }),
  });

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["split_summary", tripId] }),
      queryClient.invalidateQueries({ queryKey: ["split_rows", tripId] }),
      queryClient.invalidateQueries({ queryKey: ["cost_totals", tripId] }),
    ]);
  }

  const save = useMutation({
    mutationFn: () =>
      rpc<SplitRow>("save_split_row", {
        trip_id: tripId,
        row: {
          label: draft.label,
          original_amount: Number(draft.original_amount || 0),
          original_currency: draft.original_currency,
          paid_by: draft.paid_by,
          participants: draft.participants,
          mode: draft.mode,
          // Only under `manual`; `validate_row` clears it for every other mode so
          // a stale allocation cannot outweigh the mode actually chosen.
          allocation:
            draft.mode === "manual"
              ? Object.fromEntries(
                  draft.participants.map((person) => [person, Number(draft.allocation[person] || 0)]),
                )
              : {},
          notes: draft.notes || null,
          tag: draft.tag,
          cost_id: draft.cost_id || null,
        },
      }),
    onSuccess: async () => {
      setDraft({ ...EMPTY, paid_by: draft.paid_by });
      await refresh();
    },
  });

  const setVoided = useMutation({
    mutationFn: (input: { split_id: string; voided: boolean }) =>
      rpc<SplitRow>("set_split_voided", { trip_id: tripId, ...input }),
    onSuccess: refresh,
  });

  const setCardholder = useMutation({
    mutationFn: (traveller_id: string) =>
      rpc<{ traveller_id: string }>("set_split_cardholder", { trip_id: tripId, traveller_id }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["split_cardholder", tripId] });
      await refresh();
    },
  });

  const setSettled = useMutation({
    mutationFn: (input: { traveller_id: string; settled: boolean }) =>
      rpc<SplitSummary>("set_split_settled", { trip_id: tripId, ...input }),
    onSuccess: refresh,
  });

  if (summary.isPending || rows.isPending) return <p>{copy("loading", language)}</p>;
  if (summary.isError) return <p className="field-error">⚠ {summary.error.message}</p>;
  if (rows.isError) return <p className="field-error">⚠ {rows.error.message}</p>;

  const names = travellerNames(setup.data, language);
  const roster = Object.keys(names);
  const totalsData = totals.data;
  const yourShare = summary.data.balances.find((entry) => entry.traveller_id === "owner");
  const filtering = Object.keys(filters).length > 0;
  // What is still unallocated on a manual row. Positive means under-allocated.
  const allocationLeft =
    Number(draft.original_amount || 0)
    - draft.participants.reduce((total, id) => total + Number(draft.allocation[id] || 0), 0);
  const allocationOff =
    draft.mode === "manual"
    && Math.abs(allocationLeft) > 0.01 * Math.max(draft.participants.length, 1);

  function toggleFilter(key: "who" | "category", value: string) {
    setFilters((current) => (current[key] === value ? { ...current, [key]: undefined } : { ...current, [key]: value }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <section className="stage-card money-screen">
      <header className="money-head">
        <h1>{copy("split_title", language)}</h1>
        <p>{copy("split_help", language)}</p>
      </header>

      {/* `WF-030`'s second workbook, reachable from the screen whose data it
          carries. Its whole purpose is that it can be handed to someone: the plan
          file holds the itinerary, every address and the readiness evidence, so
          it is the one export that cannot be shared, and until this existed the
          split ledger only came out inside it. No active plan is needed, which is
          the point -- bills get paid before an itinerary is built. */}
      {/* Only once there is something in it. An empty workbook downloads perfectly
          well and tells you nothing, so the link was an invitation to a blank file. */}
      <div className="money-export">
        {summary.data.rows > 0 ? (
          <a className="primary-link" download href={`/api/export/${encodeURIComponent(tripId)}/money.xlsx`}>
            {copy("money_workbook", language)}
          </a>
        ) : (
          <span aria-disabled="true" className="primary-link disabled">
            {copy("money_workbook", language)}
          </span>
        )}
        <span className="setup-hint">
          {summary.data.rows > 0
            ? copy("money_workbook_help", language)
            : copy("money_workbook_empty", language)}
        </span>
      </div>

      <div className="money-tiles">
        <Tile
          hint={`${copy("split_rows_counted", language)} ${summary.data.rows} · ${copy(
            "split_voided_counted",
            language,
          )} ${summary.data.voided_rows}`}
          label={copy("split_actual_spend", language)}
          value={money(summary.data.actual_thb)}
        />
        <Tile
          hint={copy("split_from_participants", language)}
          label={copy("split_your_share", language)}
          value={money(yourShare?.shares_thb ?? 0)}
        />
      </div>

      {/* The two per-person numbers are computed by different mechanisms and
          must never be presented as the same kind of number. */}
      {totalsData?.planned_per_person_thb ? (
        <Note mark="ⓘ" tone="info">
          <b>
            {copy("costs_planned_per_person", language)}{" "}
            {money(totalsData.planned_per_person_thb)} · {copy("split_your_share", language)}{" "}
            {money(yourShare?.shares_thb ?? 0)}.
          </b>{" "}
          {copy("split_two_numbers", language)}
        </Note>
      ) : null}

      {/* Map item 5, answered where the data actually is. `/places` charts
          nothing because it has no distribution; the split ledger has two. */}
      <div className="money-charts">
        <Donut
          label={copy("costs_by_category", language)}
          slices={Object.entries(summary.data.by_category).map(([key, value]) => ({
            key,
            name: categoryName(key, categoryList.data, language),
            value,
          }))}
          total={summary.data.actual_thb}
        />
        <Meters
          label={copy("split_shares", language)}
          rows={summary.data.balances.map((entry) => ({
            key: entry.traveller_id,
            name: names[entry.traveller_id] ?? entry.traveller_id,
            value: entry.shares_thb,
          }))}
        />
      </div>

      <h2 className="money-eyebrow">{copy("split_settle_up", language)}</h2>
      {/* Wording that has to stay true after the owner has been paid back,
          because the number does not change when they are. */}
      <Note mark="◇" tone="plain">
        <b>{copy("split_suggestions", language)}</b> {copy("split_suggestions_help", language)}
      </Note>
      {/* Donor element 30. Everyone settles through one person, and until now
          that person was a constant -- so a trip where someone else's card is on
          file settled through the wrong traveller and no screen could say so. */}
      <label className="money-cardholder">
        {copy("split_cardholder", language)}
        <select
          disabled={setCardholder.isPending}
          onChange={(event) => setCardholder.mutate(event.target.value)}
          value={cardholder.data ?? "owner"}
        >
          {roster.map((id) => (
            <option key={id} value={id}>
              {names[id]}
            </option>
          ))}
        </select>
        <span className="setup-hint">{copy("split_cardholder_help", language)}</span>
      </label>
      {summary.data.settlement.length === 0 ? (
        <p className="money-empty">{copy("split_nothing_to_settle", language)}</p>
      ) : (
        <ul className="money-rows">
          {summary.data.settlement.map((entry) => {
            const owedToTraveller = entry.direction === "cardholder_pays_traveller";
            return (
              // derives-from: element 19 .person-meter-item as .money-row
              <li className="money-row" key={entry.traveller_id}>
                <span className="money-row-main">
                  <strong className={owedToTraveller ? "money-reversed" : undefined}>
                    {owedToTraveller
                      ? `${copy("split_you_pay", language)} ${names[entry.traveller_id] ?? entry.traveller_id}`
                      : `${names[entry.traveller_id] ?? entry.traveller_id} ${copy("split_pays_you", language)}`}
                  </strong>
                  <span className="money-row-meta">
                    {copy("split_shares", language)} {money(entry.shares_thb)} −{" "}
                    {copy("split_paid_out", language)} {money(entry.paid_out_thb)}
                    {owedToTraveller ? ` — ${copy("split_cardholder_owes", language)}` : ""}
                  </span>
                </span>
                <span className="money-row-amounts">
                  <strong className="money-num">{money(entry.amount_thb)}</strong>
                  <button
                    className={entry.settled ? "money-settled" : undefined}
                    disabled={setSettled.isPending}
                    onClick={() =>
                      setSettled.mutate({
                        traveller_id: entry.traveller_id,
                        settled: !entry.settled,
                      })
                    }
                    type="button"
                  >
                    {entry.settled
                      ? `✓ ${copy("split_settled", language)}`
                      : copy("split_mark_settled", language)}
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      )}

      <h2 className="money-eyebrow">{copy("split_transactions", language)}</h2>
      {/* derives-from: inline .clickable-filter-item as .money-chip, recovered from inline
          styles. Filtering dims rather than hides, so a total that moved can
          still be explained. */}
      <div className={`money-filters${filtering ? " filtering" : ""}`}>
        <span className="money-filter-label">{copy("split_filter_who", language)}</span>
        {roster.map((id) => (
          <button
            aria-pressed={filters.who === id}
            className="money-chip"
            key={id}
            onClick={() => toggleFilter("who", id)}
            type="button"
          >
            {names[id]}
          </button>
        ))}
        <span className="money-filter-label">{copy("split_filter_category", language)}</span>
        {[...new Set(rows.data.map((row) => row.category))].map((category) => (
          <button
            aria-pressed={filters.category === category}
            className="money-chip"
            key={category}
            onClick={() => toggleFilter("category", category)}
            type="button"
          >
            {categoryName(category, categoryList.data, language)}
          </button>
        ))}
        {filtering ? (
          <button className="money-chip-clear" onClick={() => setFilters({})} type="button">
            × {copy("split_filter_clear", language)}
          </button>
        ) : null}
      </div>

      <ul className="money-rows">
        {rows.data.map((row) => {
          const dimmed =
            filtering &&
            ((filters.who !== undefined && row.paid_by !== filters.who) ||
              (filters.category !== undefined && row.category !== filters.category));
          return (
            // derives-from: element 26 .recent-row-item as .money-row
            <li
              className={`money-row${row.voided ? " voided" : ""}${dimmed ? " dimmed" : ""}${
                row.cost_id ? " linked" : ""
              }`}
              key={row.split_id}
            >
              <span className="money-row-main">
                <strong>{row.label}</strong>
                <span className="money-row-meta">
                  {row.voided ? (
                    copy("split_voided_note", language)
                  ) : (
                    <>
                      {names[row.paid_by] ?? row.paid_by} {copy("split_paid", language)} ·{" "}
                      {copy("split_shared_by", language)} {row.participants.length} ·{" "}
                      <Tag>{categoryName(row.category, categoryList.data, language)}</Tag>
                      {row.cost_id ? ` · ${copy("split_linked", language)}` : ""}
                    </>
                  )}
                </span>
              </span>
              <span className="money-row-amounts">
                <strong className="money-num money-amount">{money(row.reported_thb)}</strong>
                {row.original_currency === "THB" ? null : (
                  <span className="money-num money-was">
                    {row.original_currency} {money(row.original_amount)}
                  </span>
                )}
                <button
                  disabled={setVoided.isPending}
                  onClick={() =>
                    setVoided.mutate({ split_id: row.split_id, voided: !row.voided })
                  }
                  type="button"
                >
                  {row.voided ? copy("split_restore", language) : copy("split_void", language)}
                </button>
              </span>
            </li>
          );
        })}
        {rows.data.length === 0 ? <li className="money-row">{copy("split_empty", language)}</li> : null}
      </ul>

      <h2 className="money-eyebrow">{copy("split_add", language)}</h2>
      {roster.length === 1 ? <Note mark="ⓘ" tone="info">{copy("split_no_members", language)}</Note> : null}
      <form className="money-form" onSubmit={submit}>
        {/* Both fields were `required` with nothing on screen saying so — the browser
            only mentions it after a refused submit, which is the article's "provide clear
            messaging when required fields are missed" arriving too late to prevent it. */}
        <label>
          {copy("split_label", language)}
          <Required language={language} />
          <input
            onChange={(event) => setDraft({ ...draft, label: event.target.value })}
            required
            value={draft.label}
          />
        </label>
        <label>
          {copy("split_amount", language)}
          <Required language={language} />
          <input
            // A money keyboard on a phone: digits and a separator, not the alphabet.
            inputMode="decimal"
            min="0"
            onChange={(event) => setDraft({ ...draft, original_amount: event.target.value })}
            required
            step="0.01"
            type="number"
            value={draft.original_amount}
          />
        </label>
        <label>
          {copy("split_currency", language)}
          <select
            onChange={(event) => setDraft({ ...draft, original_currency: event.target.value })}
            value={draft.original_currency}
          >
            {CURRENCIES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
        <label>
          {copy("split_payer", language)}
          <select
            onChange={(event) => setDraft({ ...draft, paid_by: event.target.value })}
            value={draft.paid_by}
          >
            {roster.map((id) => (
              <option key={id} value={id}>
                {names[id]}
              </option>
            ))}
          </select>
        </label>
        <label>
          {copy("split_tag", language)}
          <select
            onChange={(event) => setDraft({ ...draft, tag: event.target.value })}
            value={draft.tag}
          >
            {(categoryList.data ?? TAGS.map((code) => ({ code, label: null, built_in: true }))).map(
              (entry) => (
                <option key={entry.code} value={entry.code}>
                  {categoryName(entry.code, categoryList.data, language)}
                </option>
              ),
            )}
          </select>
        </label>
        <label>
          {copy("split_claim", language)}
          <select
            onChange={(event) => setDraft({ ...draft, cost_id: event.target.value })}
            value={draft.cost_id}
          >
            <option value="">{copy("split_claim_none", language)}</option>
            {(costs.data ?? []).map((item) => (
              <option key={item.cost_id} value={item.cost_id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="money-participants">
          <legend>{copy("split_participants", language)}</legend>
          {roster.map((id) => {
            const currentList = draft.participants.length ? draft.participants : roster;
            return (
              <label key={id}>
                <input
                  checked={currentList.includes(id)}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      participants: event.target.checked
                        ? [...currentList.filter((p) => p !== id), id]
                        : currentList.filter((person) => person !== id),
                    })
                  }
                  type="checkbox"
                />
                {names[id]}
              </label>
            );
          })}
        </fieldset>

        {/* The mode, chosen rather than guessed. `single_payer` splits between
            exactly one traveller, so picking it narrows the list to whoever is
            already ticked first -- refusing at save time instead would be the
            form knowing something it declined to say. */}
        <fieldset className="money-modes">
          <legend>{copy("split_shares", language)}</legend>
          <div className="money-modes-grid">
            {MODES.map((mode) => (
              <label className={`money-mode-card${draft.mode === mode ? " active" : ""}`} key={mode}>
                <input
                  checked={draft.mode === mode}
                  name="split-mode"
                  onChange={() =>
                    setDraft((current) => {
                      const curParts = current.participants.length ? current.participants : roster;
                      return {
                        ...current,
                        mode,
                        participants:
                          mode === "single_payer" && curParts.length > 1
                            ? curParts.slice(0, 1)
                            : curParts,
                      };
                    })
                  }
                  type="radio"
                />
                <span className="money-mode-title">{copy(`split_mode_${mode}`, language)}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {draft.mode === "manual" ? (
          <fieldset className="money-allocation">
            <legend>{copy("split_allocation", language)}</legend>
            <p className="setup-hint">{copy("split_allocation_help", language)}</p>
            <div className="money-allocation-list">
              {(draft.participants.length ? draft.participants : roster).map((id) => {
                const val = Number(draft.allocation[id] ?? 0);
                const total = Number(draft.original_amount || 0);
                const pct = total > 0 ? Math.round((val / total) * 100) : 0;
                return (
                  <div className="money-allocation-row" key={id}>
                    <div className="money-allocation-user">
                      <span className="money-allocation-avatar">{names[id]?.[0]?.toUpperCase() ?? "T"}</span>
                      <span className="money-allocation-name">{names[id]}</span>
                    </div>
                    <div className="money-allocation-input-wrap">
                      <span className="money-allocation-currency">{draft.original_currency}</span>
                      <input
                        min="0"
                        onChange={(event) =>
                          setDraft((current) => {
                            const curParts = current.participants.length ? current.participants : roster;
                            return {
                              ...current,
                              participants: curParts,
                              allocation: { ...current.allocation, [id]: event.target.value },
                            };
                          })
                        }
                        placeholder="0.00"
                        step="0.01"
                        type="number"
                        value={draft.allocation[id] ?? ""}
                      />
                      <span className="money-allocation-pct">{pct}%</span>
                    </div>
                  </div>
                );
              })}
            </div>
            {(draft.participants.length ? draft.participants : roster).length ? (
              <div className="money-allocation-summary">
                <div
                  className={`money-allocation-balance ${
                    Math.abs(allocationLeft) > 0.01 * (draft.participants.length ? draft.participants : roster).length
                      ? "balance-off"
                      : "balance-exact"
                  }`}
                >
                  <span className="balance-indicator">
                    {Math.abs(allocationLeft) <= 0.01 * (draft.participants.length ? draft.participants : roster).length ? "✓" : "⚠"}
                  </span>
                  <span>{copyFormat("split_allocation_left", language, { amount: money(allocationLeft) })}</span>
                </div>
              </div>
            ) : null}
          </fieldset>
        ) : null}

        <label className="money-notes">
          {copy("split_notes", language)}
          <input
            onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
            value={draft.notes}
          />
        </label>
        {save.error ? <p className="field-error">⚠ {save.error.message}</p> : null}
        <button
          disabled={save.isPending || draft.participants.length === 0 || allocationOff}
          type="submit"
        >
          {copy("split_save", language)}
        </button>
      </form>
    </section>
  );
}
