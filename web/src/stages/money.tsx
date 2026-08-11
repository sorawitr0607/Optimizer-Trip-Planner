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

/**
 * Spend by category, as a ring.
 *
 * Donor elements 24 and 25 were the last two of its 41 with no counterpart here,
 * and map item 5 asked whether they had any planner use at all. The answer split:
 * on `/places` there is genuinely no distribution to chart, which is what the
 * element inventory found — but the split ledger holds two real ones, money per
 * category and money per person, and they are the two questions the screen is
 * opened with.
 *
 * Drawn in SVG rather than through a library. `WF-026` fixes the web runtime at
 * six dependencies, and a ring is one `stroke-dasharray` per slice.
 *
 * **The legend carries the numbers.** A ring alone encodes by angle and colour,
 * which is unreadable to anyone who cannot separate the hues and impossible to
 * read exactly for anyone at all — the same rule the map follows, where the
 * numbered list under it repeats every pin.
 */
export function Donut({
  slices,
  total,
  label,
}: {
  slices: { key: string; name: string; value: number }[];
  total: number;
  label: string;
}) {
  const shown = slices.filter((slice) => slice.value > 0);
  if (!shown.length || total <= 0) return null;
  // Circumference of r=60. The ring is drawn as one dash per slice, offset by
  // everything before it, so no arc path maths is needed at all.
  const circumference = 2 * Math.PI * 60;
  // Offsets up front rather than accumulated inside the map: reassigning during
  // render is what `react-hooks/immutability` refuses, and rightly -- a render
  // that has run once already cannot be replayed if it mutated as it went.
  const arcs = shown.reduce<{ slice: (typeof shown)[number]; length: number; offset: number }[]>(
    (built, slice) => {
      const previous = built[built.length - 1];
      const offset = previous ? previous.offset + previous.length : 0;
      return [...built, { slice, length: (slice.value / total) * circumference, offset }];
    },
    [],
  );
  return (
    <figure className="money-chart">
      <figcaption className="money-eyebrow">{label}</figcaption>
      <div className="money-chart-body">
        <svg aria-hidden="true" className="money-donut" viewBox="0 0 160 160">
          {arcs.map(({ slice, length, offset }, index) => (
            <circle
              className={`money-slice money-slice-${index % 6}`}
              cx="80"
              cy="80"
              fill="none"
              key={slice.key}
              r="60"
              strokeDasharray={`${length} ${circumference - length}`}
              strokeDashoffset={-offset}
              strokeWidth="26"
            />
          ))}
        </svg>
        <ul className="money-legend">
          {shown.map((slice, index) => (
            <li key={slice.key}>
              <i aria-hidden="true" className={`money-swatch money-slice-${index % 6}`} />
              <span>{slice.name}</span>
              <strong className="money-num">{money(slice.value)}</strong>
            </li>
          ))}
        </ul>
      </div>
    </figure>
  );
}

/**
 * One bar per person, with the number beside it.
 *
 * Donor element 19, its person-meter row. Horizontal because the labels are
 * names: a vertical bar chart turns them sideways or truncates them, and the
 * donor's own version rotated them.
 */
export function Meters({
  rows,
  label,
}: {
  rows: { key: string; name: string; value: number }[];
  label: string;
}) {
  const most = Math.max(0, ...rows.map((row) => row.value));
  if (!rows.length || most <= 0) return null;
  return (
    <figure className="money-chart">
      <figcaption className="money-eyebrow">{label}</figcaption>
      <ul className="money-meters">
        {rows.map((row) => (
          <li key={row.key}>
            <span className="money-meter-name">{row.name}</span>
            <span className="money-meter-track">
              <i aria-hidden="true" style={{ width: `${(row.value / most) * 100}%` }} />
            </span>
            <strong className="money-num">{money(row.value)}</strong>
          </li>
        ))}
      </ul>
    </figure>
  );
}
