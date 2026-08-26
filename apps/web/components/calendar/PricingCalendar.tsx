"use client";

import { Fragment, useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import { addDaysISO, monthLabel } from "@/lib/dates";
import type { CalendarRow, Cell, Column } from "@/lib/calendarModel";
import { useFormat } from "@/lib/useFormat";
import type { FormatLocale } from "@/lib/format";
import type { Booking, Recommendation } from "@/lib/types";

/**
 * The grid is CSS, not arithmetic.
 *
 * `minmax(3.5rem, 1fr)` states the whole layout in one line: never narrower
 * than a column that can hold "2,35tr", otherwise share the space equally.
 * Fourteen days fill a wide screen; sixty days hit the floor and scroll. No
 * measurement, no ResizeObserver, no re-render on resize — the browser was
 * always going to do this better than a `useEffect`.
 *
 * Booking bars are placed with `grid-column: start / span nights`, so a stay
 * lands on its dates by definition rather than by multiplying a column width.
 * That is what makes fluid columns possible at all: pixel-positioned bars are
 * the thing that forces a fixed column width in the first place.
 */
// The floor is set by the widest thing a cell must hold: "2,88tr" plus a
// direction arrow is ~50px, and the cell has 8px of padding. 3.5rem left the
// price truncating to "2,8…" at 30 days, which defeats the point of the cell.
const GRID_MIN_COL = "4rem";
const ROW_HEAD = "11.5rem";
/** Height of the month band, so the day header can stick directly beneath it. */
const MONTH_BAND = "1.6rem";

function templateFor(columns: number, includeRowHead = true) {
  const dates = `repeat(${columns}, minmax(${GRID_MIN_COL}, 1fr))`;
  return includeRowHead ? `${ROW_HEAD} ${dates}` : dates;
}

/** Compact money for a cell: 2.350.000 -> "2,35tr" (vi) / "2.35m" (en). */
function compactRate(value: number | null | undefined, locale: FormatLocale): string {
  if (value === null || value === undefined) return "—";
  const millions = value / 1_000_000;
  const digits = millions >= 10 ? 1 : 2;
  const n = millions.toFixed(digits).replace(/\.?0+$/, "");
  return locale === "vi" ? `${n.replace(".", ",")}tr` : `${n}m`;
}

/** The frozen first column. Sticky is a property of the cell, not the row. */
function RowHead({ children, tone = "bg-white" }: { children: React.ReactNode; tone?: string }) {
  return (
    <div className={`sticky left-0 z-10 border-r border-b border-ink-200 px-2 py-1.5 ${tone}`}>
      {children}
    </div>
  );
}

/**
 * One night for one room type.
 *
 * Deliberately NOT a metrics panel. Price is the answer the operator came for;
 * everything else is a hint that there is more behind a click.
 */
function PricingDateCell({
  cell,
  column,
  selected,
  dimmed,
  filtering,
  onSelect,
  onDrillDown,
}: {
  cell: Cell | undefined;
  column: Column;
  selected: boolean;
  dimmed: boolean;
  /** A search is active, so an empty cell means "no match", not "no data". */
  filtering: boolean;
  onSelect: (rec: Recommendation) => void;
  onDrillDown: (column: Column) => void;
}) {
  const locale = useLocale() as FormatLocale;
  const t = useTranslations("calendar");
  const { formatVND } = useFormat();

  // No recommendation for this column. Two different reasons, and they must
  // not look alike: past the engine's horizon nothing was ever priced, but
  // under an active search the night exists and simply did not match. Showing
  // "no prices yet" for a filtered night would be a lie the operator cannot
  // see through.
  if (!cell) {
    const why = filtering ? t("filteredOut") : t("noPricingYet");
    return (
      <div
        className="border-r border-b border-ink-100 bg-[repeating-linear-gradient(135deg,transparent,transparent_5px,rgba(0,0,0,0.025)_5px,rgba(0,0,0,0.025)_10px)]"
        title={why}
        aria-label={why}
      />
    );
  }

  const isWeek = column.nights > 1;
  const soldOut = isWeek ? cell.soldOutNights === column.nights : cell.soldOutNights > 0;
  const fill = cell.total > 0 ? Math.min(1, cell.sold / cell.total) : 0;

  // Direction, not magnitude: the exact percentage lives in the drawer.
  const arrow = cell.changePct > 0.5 ? "↑" : cell.changePct < -0.5 ? "↓" : "≈";
  const arrowTone =
    cell.changePct > 0.5
      ? "text-emerald-600"
      : cell.changePct < -0.5
        ? "text-amber-600"
        : "text-ink-300";

  const title = [
    isWeek ? t("weekAverage", { rate: formatVND(cell.rate) }) : formatVND(cell.rate),
    isWeek
      ? t("occupancyOfWeek", { pct: Math.round(fill * 100), nights: column.nights })
      : t("occupancyOf", { sold: cell.sold, total: cell.total }),
    // The word, not the glyph: this string is now the accessible name, and a
    // screen reader announces "★" as "star" or skips it entirely.
    cell.isEvent ? t("legend.event") : "",
    cell.attention ? t("needsReview") : "",
    isWeek ? t("clickToOpenWeek") : "",
  ]
    .filter(Boolean)
    .join(" · ");

  // A week has no single recommendation to explain, so it drills in rather
  // than opening one of its seven arbitrarily.
  const activate = () => {
    if (cell.single) onSelect(cell.single);
    else onDrillDown(column);
  };

  return (
    <button
      type="button"
      onClick={activate}
      title={title}
      // The same sentence as the tooltip. `title` becomes the accessible
      // DESCRIPTION when aria-label is present, and descriptions are commonly
      // not announced — so a screen-reader user heard only date and rate, and a
      // keyboard user could not hover for the rest. The attention dot in
      // particular was colour-only for sighted users and absent for everyone
      // else.
      aria-label={title}
      className={`group relative min-w-0 border-r border-b border-ink-100 px-1 py-1.5 text-left transition-colors
        focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-inset
        ${dimmed ? "opacity-30" : ""}
        ${selected ? "bg-brand-50" : soldOut ? "bg-ink-100/70 hover:bg-ink-100" : "hover:bg-brand-50/50"}`}
    >
      {/* At most two marks, both in the corner. The price stays loudest. */}
      <span className="absolute top-0.5 right-0.5 flex items-center gap-0.5">
        {cell.isEvent && (
          <span className="text-[8px] leading-none text-violet-500" aria-hidden>
            ★
          </span>
        )}
        {cell.attention && <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />}
      </span>

      <div className="flex items-baseline gap-0.5">
        <span
          className={`tnum truncate text-[12px] font-semibold leading-none ${
            soldOut ? "text-ink-400" : "text-ink-900"
          }`}
        >
          {compactRate(cell.rate, locale)}
        </span>
        <span className={`text-[10px] leading-none ${arrowTone}`} aria-hidden>
          {arrow}
        </span>
      </div>

      {/* Availability as a shape first, digits second. */}
      <div className="mt-1.5 flex items-center gap-1">
        <div className="h-1 min-w-0 flex-1 rounded-full bg-ink-150 overflow-hidden">
          <div
            className={`h-full ${soldOut ? "bg-ink-400" : "bg-brand-400"}`}
            style={{ width: `${fill * 100}%` }}
          />
        </div>
        <span className="tnum shrink-0 text-[9.5px] leading-none text-ink-400">
          {/* A day column counts APARTMENTS left. A week's totals are sums over
              seven nights, so the same slot would print room-nights in the same
              styling — a 4-apartment category showing "23". Weeks show how full
              they are instead; the number and the bar then mean one thing. */}
          {soldOut ? t("full") : isWeek ? `${Math.round(fill * 100)}%` : cell.total - cell.sold}
        </span>
      </div>
    </button>
  );
}

/** Distinct, stable colours per channel. Order matters only for consistency. */
const CHANNEL_TONE: Record<string, string> = {
  "Booking.com": "bg-sky-400",
  Airbnb: "bg-rose-400",
  Agoda: "bg-violet-400",
  "Trip.com": "bg-amber-400",
  Expedia: "bg-emerald-400",
  Direct: "bg-ink-400",
};

/**
 * Occupied unit-nights per column, split by channel.
 *
 * This was a stay timeline with bars spanning several days. It was fiction: a
 * booking row is ONE OCCUPIED UNIT-NIGHT, not a stay — the provider emits
 * exactly `units_sold` rows per night and `nights` is random decoration nothing
 * had ever read. Spanning them drew ~3.5x the occupancy that exists, and the
 * eight-lane cap hid the overdraw, so it looked plausible while contradicting
 * the occupancy bar in the cell directly above.
 *
 * What the rows genuinely support is this: how many rooms sold on each night,
 * and through which channel. Real stay ranges need Blue Jay (U16), like unit
 * assignment.
 */
function OccupancyByChannel({
  bookings,
  columns,
}: {
  bookings: Booking[];
  columns: Column[];
}) {
  const t = useTranslations("calendar");

  const byColumn = useMemo(() => {
    const index = new Map<string, string>();
    for (const c of columns) {
      // Every date the column covers maps back to that column's key.
      for (let i = 0; i < c.nights; i += 1) {
        index.set(addDaysISO(c.startISO, i), c.key);
      }
    }
    const out = new Map<string, Map<string, number>>();
    for (const b of bookings) {
      const key = index.get(b.stay_date);
      if (!key) continue;
      const channels = out.get(key) ?? new Map<string, number>();
      channels.set(b.channel, (channels.get(b.channel) ?? 0) + 1);
      out.set(key, channels);
    }
    return out;
  }, [bookings, columns]);

  const busiest = useMemo(
    () =>
      Math.max(
        1,
        ...[...byColumn.values()].map((m) => [...m.values()].reduce((s, v) => s + v, 0)),
      ),
    [byColumn],
  );

  return (
    <>
      {columns.map((c) => {
        const channels = byColumn.get(c.key);
        const total = channels ? [...channels.values()].reduce((s, v) => s + v, 0) : 0;
        const label = channels
          ? [...channels.entries()]
              .sort((a, b) => b[1] - a[1])
              .map(([name, n]) => `${name} ${n}`)
              .join(" · ")
          : t("noBookingsInRange");
        return (
          <div
            key={c.key}
            title={`${t("roomNights", { count: total })}${channels ? ` — ${label}` : ""}`}
            aria-label={`${c.startISO}: ${t("roomNights", { count: total })}`}
            className="flex h-12 items-end gap-px border-r border-b border-ink-100 px-1 pb-1"
          >
            {channels
              ? [...channels.entries()]
                  .sort((a, b) => a[0].localeCompare(b[0]))
                  .map(([name, n]) => (
                    <div
                      key={name}
                      className={`min-w-0 flex-1 rounded-sm ${CHANNEL_TONE[name] ?? "bg-ink-300"}`}
                      style={{ height: `${Math.max(8, (n / busiest) * 100)}%` }}
                    />
                  ))
              : null}
          </div>
        );
      })}
    </>
  );
}

export function PricingCalendar({
  rows,
  columns,
  bookingsByRoomType,
  expanded,
  onToggleExpand,
  selectedId,
  onSelect,
  onDrillDown,
  attentionOnly,
  filtering,
}: {
  rows: CalendarRow[];
  columns: Column[];
  bookingsByRoomType: Map<number, Booking[]>;
  expanded: Set<number>;
  onToggleExpand: (roomTypeId: number) => void;
  selectedId: number | null;
  onSelect: (rec: Recommendation) => void;
  onDrillDown: (column: Column) => void;
  attentionOnly: boolean;
  /** A search is active, so an empty cell means "no match", not "no data". */
  filtering: boolean;
}) {
  const locale = useLocale() as FormatLocale;
  const t = useTranslations("calendar");
  const tv = useTranslations("vocab");

  // Month bands above the columns, so a long range still reads.
  const months = useMemo(() => {
    const out: { label: string; span: number }[] = [];
    for (const c of columns) {
      const label = monthLabel(c.startISO, locale);
      const last = out[out.length - 1];
      if (last && last.label === label) last.span += 1;
      else out.push({ label, span: 1 });
    }
    return out;
  }, [columns, locale]);

  return (
    <div className="h-full overflow-auto">
      <div className="grid" style={{ gridTemplateColumns: templateFor(columns.length) }}>
        {/* ------------------------------------------------ month band */}
        <div className="sticky left-0 top-0 z-30 border-r border-b border-ink-100 bg-white" />
        {months.map((m) => (
          <div
            key={m.label}
            style={{ gridColumn: `span ${m.span}` }}
            className="sticky top-0 z-20 truncate border-r border-b border-ink-100 bg-white px-2 py-1
              text-[10.5px] font-medium uppercase tracking-wide text-ink-400"
          >
            {m.label}
          </div>
        ))}

        {/* ------------------------------------------------- day header */}
        <div
          className="sticky left-0 z-30 flex items-end border-r border-b border-ink-200 bg-white px-3 pb-1.5"
          style={{ top: MONTH_BAND }}
        >
          <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
            {t("roomType")}
          </span>
        </div>
        {columns.map((c) => (
          <div
            key={c.key}
            style={{ top: MONTH_BAND }}
            className={`sticky z-20 border-r border-b border-ink-200 px-1 py-1 text-center ${
              c.isToday ? "bg-brand-50" : c.isWeekend ? "bg-ink-50" : "bg-white"
            }`}
          >
            <div
              className={`truncate text-[9.5px] font-medium uppercase leading-tight ${
                c.isToday ? "text-brand-700" : "text-ink-400"
              }`}
            >
              {c.top}
            </div>
            <div
              className={`tnum truncate text-[11.5px] leading-tight ${
                c.isToday ? "font-bold text-brand-700" : "font-medium text-ink-700"
              }`}
            >
              {c.bottom}
            </div>
          </div>
        ))}

        {/* -------------------------------------------------------- rows */}
        {rows.map((row) => {
          const isOpen = expanded.has(row.roomTypeId);
          const bookings = bookingsByRoomType.get(row.roomTypeId) ?? [];
          return (
            <Fragment key={row.roomTypeId}>
              <RowHead>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => onToggleExpand(row.roomTypeId)}
                    aria-expanded={isOpen}
                    aria-label={t(isOpen ? "collapseRow" : "expandRow")}
                    className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-ink-400
                      hover:bg-ink-100 hover:text-ink-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                  >
                    <span className="text-[10px]" aria-hidden>
                      {isOpen ? "▼" : "▶"}
                    </span>
                  </button>
                  <div className="min-w-0">
                    <div className="truncate text-[12.5px] font-medium text-ink-900">
                      {tv(`roomCategories.${row.category}`)}
                    </div>
                    <div className="text-[10.5px] text-ink-400">
                      {t("unitCount", { count: row.unitsTotal })}
                    </div>
                  </div>
                </div>
              </RowHead>

              {columns.map((c) => {
                const cell = row.byColumn.get(c.key);
                return (
                  <PricingDateCell
                    key={c.key}
                    cell={cell}
                    column={c}
                    selected={!!cell?.single && cell.single.id === selectedId}
                    dimmed={attentionOnly && !!cell && !cell.attention}
                    filtering={filtering}
                    onSelect={onSelect}
                    onDrillDown={onDrillDown}
                  />
                );
              })}

              {isOpen && (
                <>
                  <RowHead tone="bg-ink-50">
                    <div className="text-[11px] font-medium text-ink-600">{t("bookings")}</div>
                    <div className="text-[10px] text-ink-400">{t("unitUnassigned")}</div>
                  </RowHead>
                  {/* Cells of the SAME grid, so they align with the columns
                      above by construction. The previous version nested its own
                      grid sized from the daily date list, which overflowed and
                      misaligned in every week view. */}
                  <OccupancyByChannel bookings={bookings} columns={columns} />
                </>
              )}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
