/* eslint-disable react-refresh/only-export-components */
import type { PropsWithChildren, ReactNode } from "react";

import type { SetupDraft } from "../api/client";
import { copy, type Language } from "../i18n/copy";

// Grouping is Western in both languages: a number that changes shape with the
// language is a number the owner has to re-read.
const AMOUNT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

export function money(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : AMOUNT.format(value);
}

export function signed(value: number): string {
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${AMOUNT.format(Math.abs(value))}`;
}

/** Display names for traveller ids. The owner is "You"; members carry labels. */
export function travellerNames(
  setup: SetupDraft | null | undefined,
  language: Language,
): Record<string, string> {
  const names: Record<string, string> = { owner: copy("split_you", language) };
  for (const member of setup?.snapshot.data.travellers ?? []) {
    names[member.traveller_id] = member.label || member.traveller_id;
  }
  return names;
}

// derives-from: element 14 .stat-card as .money-tile
export function Tile({
  label,
  value,
  hint,
  meter,
}: {
  label: string;
  value: string;
  hint?: ReactNode;
  meter?: number;
}) {
  return (
    <div className="money-tile">
      <span className="money-tile-label">{label}</span>
      <strong className="money-tile-value">{value}</strong>
      {hint ? <span className="money-tile-hint">{hint}</span> : null}
      {meter === undefined ? null : (
        <span className="money-meter">
          <i style={{ width: `${Math.min(Math.max(meter, 0), 100)}%` }} />
        </span>
      )}
    </div>
  );
}

// derives-from: element 36 .currency-info-box as .money-note
export function Note({
  tone,
  mark,
  children,
}: PropsWithChildren<{ tone: "warn" | "info" | "plain"; mark: string }>) {
  return (
    <p className={`money-note money-note-${tone}`}>
      <b aria-hidden="true">{mark}</b>
      <span>{children}</span>
    </p>
  );
}

// derives-from: element 26 .category-badge as .money-tag
export function Tag({ children }: PropsWithChildren) {
  return <span className="money-tag">{children}</span>;
}
