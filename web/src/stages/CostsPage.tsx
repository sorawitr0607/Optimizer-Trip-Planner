import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { rpc, type CostItem, type CostTotals, type SetupDraft } from "../api/client";
import { copy } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";
import { money, Note, signed, Tag, Tile } from "./money";

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

  if (totals.isPending || items.isPending) return <p>{copy("loading", language)}</p>;
  if (totals.isError) return <p className="field-error">⚠ {totals.error.message}</p>;
  if (items.isError) return <p className="field-error">⚠ {items.error.message}</p>;

  const figures = totals.data;
  const headcount = 1 + (setup.data?.snapshot.data.travellers?.length ?? 0);
  const claimed = new Set(figures.claimed_cost_ids);
  const categories = Object.entries(figures.by_category_comparison);
  const spentPercent =
    figures.planned_thb > 0 ? (figures.actual_thb / figures.planned_thb) * 100 : 0;

  return (
    <section className="stage-card money-screen">
      <header className="money-head">
        <h1>{copy("costs_planned_title", language)}</h1>
        <p>{copy("costs_planned_help", language)}</p>
      </header>

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
                <td>{copy(key, language)}</td>
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
          {figures.categories_without_plan.map((key) => copy(key, language)).join(", ")}
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
                  <Tag>{copy(item.category, language)}</Tag>{" "}
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
              </span>
            </li>
          );
        })}
        {items.data.length === 0 ? <li className="money-row">{copy("costs_no_rows", language)}</li> : null}
      </ul>

      <Link className="primary-link" to={`/trips/${tripId}/split`}>
        {copy("costs_open_split", language)}
      </Link>
    </section>
  );
}
