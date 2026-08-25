import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router";

import {
  ApiError,
  rpc,
  type CostItem,
  type CostTotals,
  type ExportSnapshot,
  type Frozen,
  type SetupDraft,
} from "../api/client";
import { copy, copyFormat } from "../i18n/copy";
import { Loading } from "../shared/Loading";
import { costIcon } from "../shared/tagIcons";
import { spanDays } from "../shared/dates";
import { useLanguage } from "../i18n/LanguageProvider";
import { categoryName, money, Note, Required, signed, Tag, Tile, type CostCategory } from "./money";

const COST_TIERS = {
  budget: { accommodation: 1000, food: 150, fees: 150, transport: 100 },
  value: { accommodation: 2000, food: 250, fees: 300, transport: 180 },
  standard: { accommodation: 3500, food: 450, fees: 600, transport: 300 },
  premium: { accommodation: 7000, food: 900, fees: 1200, transport: 600 },
  luxury: { accommodation: 15000, food: 1800, fees: 2500, transport: 1200 },
} as const;

type CostTier = keyof typeof COST_TIERS;
type EstimatedCategory = keyof (typeof COST_TIERS)[CostTier];

/** Rough editable totals: lodging per two people; the other units per person. */
function suggestedPlanCost(
  tier: CostTier,
  category: EstimatedCategory,
  count: number,
  headcount: number,
): number {
  const people = Math.max(1, Math.floor(headcount));
  const units = category === "accommodation" ? Math.ceil(people / 2) : people;
  return Math.round(Math.max(0, count) * units * COST_TIERS[tier][category]);
}

/**
 * The overview screen, and the one place the two ledgers are read together.
 * It is therefore the screen that misreports if the claim relation is wrong,
 * which is the accepted price of the comparison living somewhere useful.
 */
export function CostsPage() {
  const { tripId = "" } = useParams();
  const { language } = useLanguage();
  const totals = useQuery({
    queryKey: ["cost_totals", tripId],
    queryFn: () => rpc<CostTotals>("cost_totals", { trip_id: tripId }),
  });
  const items = useQuery({
    queryKey: ["cost_items", tripId],
    queryFn: () => rpc<CostItem[]>("list_cost_items", { trip_id: tripId }),
  });
  const setup = useQuery({
    queryKey: ["setup", tripId],
    queryFn: () => rpc<SetupDraft | null>("get_setup", { trip_id: tripId }),
  });
  const rate = useQuery({
    queryKey: ["rate_snapshot", tripId],
    queryFn: () => rpc<{ rates?: Record<string, number> } | null>("get_rate_snapshot", { trip_id: tripId }),
  });
  const categoryList = useQuery({
    queryKey: ["cost_categories", tripId],
    queryFn: () => rpc<CostCategory[]>("cost_categories", { trip_id: tripId }),
  });
  // The activated plan, read through the same snapshot the itinerary and both workbooks
  // read. Nothing new is exposed for this: `build_export_snapshot` is already the one
  // shared derivation, and a second opinion about the same plan is how a screen starts
  // disagreeing with the file it exports.
  const plan = useQuery({
    queryKey: ["export_snapshot", tripId],
    // Wrapped in the `Frozen` envelope every snapshot crosses the boundary in — the
    // hash travels beside the payload. The itinerary unwraps the same way.
    queryFn: () =>
      rpc<Frozen<ExportSnapshot> | null>("build_export_snapshot", { trip_id: tripId }),
    retry: false,
  });
  const [newCategory, setNewCategory] = useState("");
  // This screen had no mutation at all: it told the owner to "add estimates" and gave
  // them no way to. save_cost_item was allowlisted the whole time and unreachable, so
  // the planned-versus-actual comparison could only ever compare nothing.
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState({
    label: "",
    amount: "",
    currency: "THB",
    category: "other",
    paid: false,
  });
  const [flash, setFlash] = useState("");
  const [costTier, setCostTier] = useState<CostTier>("standard");
  const [seedAmounts, setSeedAmounts] = useState<Record<string, string>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);
  const saveCategories = useMutation({
    mutationFn: (categories: CostCategory[]) =>
      rpc<CostCategory[]>("set_cost_categories", {
        trip_id: tripId,
        // Only the custom ones are the trip's to keep; the server ignores a
        // built-in arriving here, so sending the whole list back is harmless and
        // keeps the screen from having to know which is which.
        categories: categories.map((entry) => ({ code: entry.code, label: entry.label })),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["cost_categories", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["cost_totals", tripId] });
    },
  });

  const saveCost = useMutation({
    mutationFn: () =>
      rpc<CostItem>("save_cost_item", {
        trip_id: tripId,
        cost_id: editingId,
        item: {
          label: draft.label,
          category: draft.category,
          original_amount: Number(draft.amount || 0),
          original_currency: draft.currency,
          payment_state: draft.paid ? "paid" : "estimate",
        },
      }),
    onSuccess: async () => {
      setFlash("estimate_saved");
      setEditingId(null);
      setDraft((current) => ({ ...current, label: "", amount: "" }));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["cost_items", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["cost_totals", tripId] }),
      ]);
    },
  });

  const headcount = 1 + (setup.data?.snapshot.data.travellers?.length ?? 0);
  // What the plan commits you to paying for. Tiers provide an editable starting point;
  // the owner still presses Save before any figure becomes part of the ledger.
  const shape = (() => {
    const days = plan.data?.data?.days ?? [];
    if (!days.length) return null;
    const rows = days.flatMap((day) => day.items ?? []);
    const basics = setup.data?.snapshot.data.trip_basics;
    const datedDays = basics?.start_date && basics.end_date
      ? spanDays(basics.start_date, basics.end_date)
      : days.length;
    return {
      nights: Math.max(0, datedDays - 1),
      meals: rows.filter((row) => row.type === "meal").length,
      visits: rows.filter((row) => row.type === "visit").length,
      legs: rows.filter((row) => row.type === "travel").length,
    };
  })();
  const makeSeed = (key: string, category: EstimatedCategory, count: number) => {
    const description = copy(key, language);
    return {
      label: `${description} (${count})`,
      description,
      category,
      count,
      relatedItemId: `plan-estimate:${category}`,
    };
  };
  const planSeeds = shape
    ? [
        makeSeed("plan_shape_nights", "accommodation", shape.nights),
        makeSeed("plan_shape_meals", "food", shape.meals),
        makeSeed("plan_shape_visits", "fees", shape.visits),
        makeSeed("plan_shape_legs", "transport", shape.legs),
      ].filter((seed) => seed.count > 0)
    : [];
  const existingSeed = (seed: (typeof planSeeds)[number]) =>
    (items.data ?? []).find(
      (item) => item.related_item_id === seed.relatedItemId
        || (item.label === seed.label && item.category === seed.category),
    );
  const seedAmount = (seed: (typeof planSeeds)[number]) =>
    seedAmounts[seed.category]
      ?? String(
        existingSeed(seed)?.original_amount
        || suggestedPlanCost(costTier, seed.category, seed.count, headcount),
      );
  const seedsReady = Boolean(
    planSeeds.length && planSeeds.every((seed) => Number(seedAmount(seed)) > 0),
  );

  const seedRows = useMutation({
    mutationFn: async () => {
      return Promise.all(
        planSeeds.map((seed) => {
          const existing = existingSeed(seed);
          return (
            rpc<CostItem>("save_cost_item", {
              trip_id: tripId,
              cost_id: existing?.cost_id ?? null,
              item: {
                label: seed.label,
                category: seed.category,
                // The tier is only a starting value, kept editable and saved explicitly.
                original_amount: Number(seedAmount(seed)),
                original_currency: "THB",
                payment_state: "estimate",
                related_item_id: seed.relatedItemId,
              },
            })
          );
        }),
      );
    },
    onSuccess: async () => {
      setFlash("plan_shape_seeded");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["cost_items", tripId] }),
        queryClient.invalidateQueries({ queryKey: ["cost_totals", tripId] }),
      ]);
    },
    // Silence was the whole bug report. Without this a refusal left the button looking
    // exactly like a button that does nothing — pressed, no error, no rows.
    onError: (error) => setFlash(error instanceof ApiError ? error.code : String(error)),
  });

  if (totals.isPending || items.isPending) return <Loading language={language} />;
  if (totals.isError) return <p className="field-error">⚠ {totals.error.message}</p>;
  if (items.isError) return <p className="field-error">⚠ {items.error.message}</p>;

  const figures = totals.data;
  const claimed = new Set(figures.claimed_cost_ids);
  const categories = Object.entries(figures.by_category_comparison);
  const vocabulary = categoryList.data;
  const spentPercent =
    figures.planned_thb > 0 ? (figures.actual_thb / figures.planned_thb) * 100 : 0;

  return (
    <section className="stage-card money-screen">
      <header className="money-head">
        <h1>{copy("costs_planned_title", language)}</h1>
        <p>{copy("costs_planned_help", language)}</p>
      </header>

      {/* The plan supplies counts; the owner supplies the price. */}
      <section className="money-plan-shape">
        <h2 className="money-eyebrow">{copy("plan_shape_title", language)}</h2>
        {shape ? (
          <>
            <ul className="money-shape-list">
              {planSeeds.map((seed) => (
                <li key={seed.category}>
                  <strong>{seed.count}</strong> {seed.description}
                </li>
              ))}
            </ul>
            <p className="setup-hint" id="plan-shape-help">
              {copyFormat("plan_shape_help", language, { headcount })}
            </p>
            <label className="money-shape-tier">
              {copy("plan_shape_tier", language)}
              <select
                onChange={(event) => {
                  const next = event.target.value as CostTier;
                  setCostTier(next);
                  setSeedAmounts(Object.fromEntries(planSeeds.map((seed) => [
                    seed.category,
                    String(suggestedPlanCost(next, seed.category, seed.count, headcount)),
                  ])));
                }}
                value={costTier}
              >
                {(Object.keys(COST_TIERS) as CostTier[]).map((tier) => (
                  <option key={tier} value={tier}>{copy(`cost_tier_${tier}`, language)}</option>
                ))}
              </select>
            </label>
            <div className="money-shape-estimates">
              {planSeeds.map((seed) => (
                <label key={seed.category}>
                  {copyFormat("plan_shape_amount", language, {
                    category: categoryName(seed.category, categoryList.data, language),
                  })}
                  <input
                    inputMode="decimal"
                    min="0.01"
                    onChange={(event) => setSeedAmounts((current) => ({
                      ...current,
                      [seed.category]: event.target.value,
                    }))}
                    step="0.01"
                    type="number"
                    value={seedAmount(seed)}
                  />
                </label>
              ))}
            </div>
            <button
              aria-describedby="plan-shape-help"
              className="setup-primary"
              disabled={seedRows.isPending || !seedsReady}
              onClick={() => seedRows.mutate()}
              type="button"
            >
              {seedRows.isPending ? copy("loading", language) : copy("plan_shape_seed", language)}
            </button>
            {/* Beside the button, not only in the flash further down. The rows this adds
                land below the fold, so the page changed and nothing near the press did —
                which reads as a button that did nothing. */}
            {seedRows.isSuccess ? (
              <p className="setup-hint" aria-live="polite">
                ✓ {copy("plan_shape_seeded", language)}
              </p>
            ) : null}
          </>
        ) : (
          <p className="setup-hint">{copy("plan_shape_none", language)}</p>
        )}
      </section>

      {/* Donor "Expense Categories". Artifact 023 fixed this vocabulary at seven,
          shared by both ledgers and both workbooks; a trip that hires skis had
          nowhere to put it but `other`, which is the category meaning
          "unclassified" -- so using it for a real recurring expense loses the
          grouping the table above exists for. The seven are not removable: they
          are what an unrecognised tag falls back to and what the four reference
          workbooks are matched against. */}
      <details className="money-categories">
        <summary>{copy("costs_categories_edit", language)}</summary>
        <p className="setup-hint" id="categories-help">
          {copy("costs_categories_help", language)}
        </p>
        <ul className="money-category-list">
          {(categoryList.data ?? []).map((entry) => (
            <li key={entry.code}>
              <span>{categoryName(entry.code, categoryList.data, language)}</span>
              {entry.built_in ? (
                <small className="setup-hint">{copy("costs_categories_built_in", language)}</small>
              ) : (
                <button
                  disabled={saveCategories.isPending}
                  onClick={() =>
                    saveCategories.mutate(
                      (categoryList.data ?? []).filter(
                        (item) => !item.built_in && item.code !== entry.code,
                      ),
                    )
                  }
                  type="button"
                >
                  {copy("split_void", language)}
                </button>
              )}
            </li>
          ))}
        </ul>
        <div className="money-category-add">
          <label>
            {copy("costs_categories_new", language)}
            <input
              aria-describedby="categories-help"
              autoComplete="off"
              onChange={(event) => setNewCategory(event.target.value)}
              type="text"
              value={newCategory}
            />
          </label>
          <button
            disabled={saveCategories.isPending || !newCategory.trim()}
            onClick={() => {
              saveCategories.mutate([
                ...(categoryList.data ?? []).filter((entry) => !entry.built_in),
                { code: newCategory, label: newCategory.trim(), built_in: false },
              ]);
              setNewCategory("");
            }}
            type="button"
          >
            {copy("split_save", language)}
          </button>
        </div>
        {saveCategories.error ? (
          <p className="field-error">⚠ {saveCategories.error.message}</p>
        ) : null}
      </details>

      <h2 className="money-eyebrow">{copy("costs_by_category", language)}</h2>
      <div className="money-table-scroll">
        {/* derives-from: element 27 .transactions-table as .money-table */}
        <table className="money-table">
          <thead>
            <tr>
              <th>{copy("category", language)}</th>
              <th>{copy("costs_planned", language)}</th>
              <th>{copy("costs_actual", language)}</th>
              <th>{copy("costs_difference", language)}</th>
            </tr>
          </thead>
          <tbody>
            {categories.map(([key, entry]) => (
              <tr key={key}>
                <td>{categoryName(key, categoryList.data, language)}</td>
                {/* A category with a plan and no spend is not the same as one
                    with spend and no plan; a zero would claim it was. */}
                <td className="money-num">{entry.planned ? money(entry.planned_thb) : "—"}</td>
                <td className="money-num">{entry.actual ? money(entry.actual_thb) : "—"}</td>
                <td
                  className={`money-num ${
                    entry.planned && entry.actual && entry.difference_thb !== 0
                      ? entry.difference_thb > 0
                        ? "money-over"
                        : "money-under"
                      : ""
                  }`}
                >
                  {entry.planned && entry.actual ? signed(entry.difference_thb) : "—"}
                </td>
              </tr>
            ))}
            {categories.length === 0 ? (
              <tr>
                <td colSpan={4}>{copy("costs_no_rows", language)}</td>
              </tr>
            ) : null}
          </tbody>
          <tfoot>
            <tr>
              <td>{copy("costs_total", language)}</td>
              <td className="money-num">{money(figures.planned_thb)}</td>
              <td className="money-num">{money(figures.actual_thb)}</td>
              <td className="money-num">
                {signed(Number((figures.actual_thb - figures.planned_thb).toFixed(2)))}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="money-tiles">
        <Tile
          hint={`${money(figures.planned_thb)} ÷ ${headcount}`}
          label={copy("costs_planned_per_person", language)}
          value={money(figures.planned_per_person_thb)}
        />
        <Tile
          hint={`${Math.round(spentPercent)}% ${copy("costs_of_plan", language)}`}
          label={copy("costs_spent_so_far", language)}
          meter={spentPercent}
          value={money(figures.actual_thb)}
        />
      </div>

      {figures.unclaimed_paid_rows > 0 ? (
        <Note mark="⚠" tone="warn">
          <b>
            {copy("costs_unclaimed_paid", language)} {figures.unclaimed_paid_rows}
          </b>{" "}
          {copy("costs_unclaimed_paid_help", language)}
        </Note>
      ) : null}

      {figures.missing_rates.length > 0 ? (
        <Note mark="⚠" tone="warn">
          <b>
            {copy("costs_missing_rate", language)} {figures.missing_rates.join(", ")}
          </b>{" "}
          {copy("costs_missing_rate_help", language)}
        </Note>
      ) : null}

      {figures.categories_without_plan.length > 0 ? (
        <Note mark="⚠" tone="warn">
          {copy("costs_without_plan", language)}{" "}
          {figures.categories_without_plan
            .map((key) => categoryName(key, categoryList.data, language))
            .join(", ")}
        </Note>
      ) : null}

      {/* Mid-trip every difference flatters reality, so the wording must not
          read as a final verdict. */}
      <Note mark="ⓘ" tone="info">
        {copy("costs_mid_trip", language)}
      </Note>

      <h2 className="money-eyebrow">{copy("costs_rows", language)}</h2>
      <ul className="money-rows">
        {items.data.map((item) => {
          const isClaimed = claimed.has(item.cost_id);
          const paid = item.payment_state === "paid";
          return (
            // derives-from: element 26 .recent-row-item as .money-row
            <li className="money-row" key={item.cost_id}>
              <span className="money-row-main">
                <strong>{item.label}</strong>
                <span className="money-row-meta">
                  {/* The same glyph the `/split` filter chips carry, on the same
                      vocabulary — a cost row and its filter should not name the
                      category two different ways. Table cells are deliberately left
                      plain: an icon on every row of a dense table is weight, not help. */}
                  <Tag icon={costIcon(item.category)}>
                    {categoryName(item.category, categoryList.data, language)}
                  </Tag>{" "}
                  {copy(item.payment_state, language)}
                  {isClaimed ? ` · ${copy("costs_claimed", language)}` : ""}
                </span>
                {isClaimed && paid ? (
                  <span className="money-row-note">{copy("costs_claimed_inert", language)}</span>
                ) : null}
              </span>
              <span className="money-row-amounts">
                <strong className="money-num">{money(item.reported_thb)}</strong>
                {paid && item.converted_thb !== null && item.converted_thb !== item.reported_thb ? (
                  <s className="money-num money-was">{money(item.converted_thb)}</s>
                ) : null}
                {item.payment_state === "estimate" ? (
                  <button
                    onClick={() => {
                      setEditingId(item.cost_id);
                      setDraft({
                        label: item.label,
                        amount: String(item.original_amount),
                        currency: item.original_currency,
                        category: item.category,
                        paid: false,
                      });
                      requestAnimationFrame(() =>
                        formRef.current?.scrollIntoView({ behavior: "smooth" }),
                      );
                    }}
                    type="button"
                  >
                    {copy("edit", language)}
                  </button>
                ) : null}
              </span>
            </li>
          );
        })}
        {items.data.length === 0 ? <li className="money-row">{copy("costs_no_rows", language)}</li> : null}
      </ul>

      {/* derives-from: element 36 .currency-info-box as .cost-record */}
      <form
        className="cost-record"
        ref={formRef}
        onSubmit={(event) => {
          event.preventDefault();
          saveCost.mutate();
        }}
      >
        <h2 className="money-eyebrow">
          {editingId ? copy("edit", language) : copy("record_estimate", language)}
        </h2>
        {flash ? <p className="setup-flash" aria-live="polite">{copy(flash, language)}</p> : null}
        {saveCost.isError ? (
          <p className="field-error" aria-live="polite">⚠ {saveCost.error.message}</p>
        ) : null}
        {!rate.data && draft.currency !== "THB" ? (
          <p className="money-note money-note-warn">
            <b aria-hidden="true">⚠</b>
            <span>{copy("no_rate_yet", language)}</span>
          </p>
        ) : null}
        <div className="setup-fields">
          <label>
            {copy("what_for", language)}
            <Required language={language} />
            <input
              autoComplete="off"
              onChange={(event) => setDraft({ ...draft, label: event.target.value })}
              required
              type="text"
              value={draft.label}
            />
          </label>
          <label>
            {copy("split_amount", language)}
            <Required language={language} />
            <input
              autoComplete="off"
              inputMode="decimal"
              min="0"
              onChange={(event) => setDraft({ ...draft, amount: event.target.value })}
              required
              step="0.01"
              type="number"
              value={draft.amount}
            />
          </label>
          <label>
            {copy("split_currency", language)}
            <select
              onChange={(event) => setDraft({ ...draft, currency: event.target.value })}
              value={draft.currency}
            >
              {["THB", "TWD", "JPY", "KRW", "CNY", "HKD", "SGD", "MYR"].map((code) => (
                <option key={code} value={code}>{code}</option>
              ))}
            </select>
          </label>
          <label>
            {copy("category", language)}
            <select
              onChange={(event) => setDraft({ ...draft, category: event.target.value })}
              value={draft.category}
            >
              {(vocabulary ?? []).map((entry) => (
                <option key={entry.code} value={entry.code}>
                  {categoryName(entry.code, vocabulary, language)}
                </option>
              ))}
            </select>
          </label>
          <label className="setup-check">
            <input
              checked={draft.paid}
              onChange={(event) => setDraft({ ...draft, paid: event.target.checked })}
              type="checkbox"
            />
            {copy("paid", language)}
          </label>
        </div>
        <div className="setup-actions">
          <button className="setup-primary" disabled={saveCost.isPending} type="submit">
            {editingId ? copy("split_save", language) : copy("record_estimate", language)}
          </button>
          {editingId ? (
            <button
              onClick={() => {
                setEditingId(null);
                setDraft((current) => ({ ...current, label: "", amount: "" }));
              }}
              type="button"
            >
              {copy("cancel", language)}
            </button>
          ) : null}
        </div>
      </form>

      <Link className="primary-link" to={`/trips/${tripId}/split`}>
        {copy("costs_open_split", language)}
      </Link>
    </section>
  );
}
