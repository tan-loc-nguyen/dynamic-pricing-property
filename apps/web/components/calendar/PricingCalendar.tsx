"use client";

import { Fragment, useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import { monthLabel, nightsBetween } from "@/lib/dates";
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
  onSelect,
  onDrillDown,
}: {
  cell: Cell | undefined;
  column: Column;
  selected: boolean;
  dimmed: boolean;
  onSelect: (rec: Recommendation) => void;
  onDrillDown: (column: Column) => void;
}) {
  const locale = useLocale() as FormatLocale;
  const t = useTranslations("calendar");
  const { formatVND } = useFormat();

  // No recommendation for this column at all. Past the engine's horizon this
  // is the normal case, and saying so is better than an empty box that looks
  // like a rendering bug.
  if (!cell) {
    return (
      <div
        className="border-r border-b border-ink-100 bg-[repeating-linear-gradient(135deg,transparent,transparent_5px,rgba(0,0,0,0.025)_5px,rgba(0,0,0,0.025)_10px)]"
        title={t("noPricingYet")}
        aria-label={t("noPricingYet")}
      />
    );
  }

  const soldOut = column.nights === 1 ? cell.soldOutNights > 0 : cell.soldOutNights === column.nights;
  const fill = cell.total > 0 ? Math.min(1, cell.sold / cell.total) : 0;

  // Direction, not magnitude: the exact percentage lives in the drawer.
  const arrow = cell.changePct > 0.5 ? "↑" : cell.changePct < -0.5 ? "↓" : "≈";
  const arrowTone =
    cell.changePct > 0.5
      ? "text-emerald-600"
      : cell.changePct < -0.5
        ? "text-amber-600"
        : "text-ink-300";

  const isWeek = column.nights > 1;
  const title = [
    isWeek ? t("weekAverage", { rate: formatVND(cell.rate) }) : formatVND(cell.rate),
    t("occupancyOf", { sold: cell.sold, total: cell.total }),
    cell.isEvent ? "★" : "",
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
      aria-label={`${column.startISO} · ${formatVND(cell.rate)}`}
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
          {soldOut ? t("full") : cell.total - cell.sold}
        </span>
      </div>
    </button>
  );
}

/**
 * Booking lanes for an expanded room type.
 *
 * Bars are NOT labelled with an apartment number: no booking in this system is
 * assigned to one (`physical_room_id` is null on every row — ASSUMPTIONS U11).
 * Lanes are a packing of overlapping stays, not a unit list, and the row head
 * says so.
 */
function BookingLanes({
  bookings,
  dates,
  onSelectBooking,
}: {
  bookings: Booking[];
  dates: string[];
  onSelectBooking: (b: Booking) => void;
}) {
  const t = useTranslations("calendar");
  const { formatVND } = useFormat();
  const first = dates[0];

  // Greedy interval packing: each bar takes the first lane it does not clash in.
  const lanes = useMemo(() => {
    const packed: Booking[][] = [];
    for (const b of [...bookings].sort((a, b) => a.stay_date.localeCompare(b.stay_date))) {
      const lane = packed.find(
        (row) => !row.some((x) => x.stay_date <= b.last_night && b.stay_date <= x.last_night),
      );
      if (lane) lane.push(b);
      else packed.push([b]);
    }
    return packed.slice(0, 8); // deep stacks add height, not understanding
  }, [bookings]);

  if (lanes.length === 0) {
    return (
      <div className="border-b border-ink-100 px-3 py-2 text-[11.5px] text-ink-400">
        {t("noBookingsInRange")}
      </div>
    );
  }

  return (
    <div className="border-b border-ink-100 py-0.5">
      {lanes.map((lane, i) => (
        <div
          key={i}
          className="grid h-6 items-center"
          style={{ gridTemplateColumns: templateFor(dates.length, false) }}
        >
          {lane.map((b) => {
            const offset = nightsBetween(first, b.stay_date);
            const nights = nightsBetween(b.stay_date, b.last_night) + 1;
            // Clip a stay that began before the window instead of dropping it.
            const startCol = Math.max(0, offset) + 1;
            const span = Math.min(
              offset < 0 ? nights + offset : nights,
              dates.length - startCol + 1,
            );
            if (span <= 0) return null;
            return (
              <button
                key={b.id}
                type="button"
                onClick={() => onSelectBooking(b)}
                title={`${b.channel} · ${t("nightCount", { count: b.nights })} · ${formatVND(b.net_rate)}`}
                style={{ gridColumn: `${startCol} / span ${span}` }}
                className="mx-0.5 h-5 truncate rounded-md border border-sky-300 bg-sky-100/90 px-1.5
                  text-left text-[10px] leading-5 text-sky-900
                  hover:bg-sky-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
              >
                {b.channel}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function PricingCalendar({
  rows,
  columns,
  dates,
  bookingsByRoomType,
  expanded,
  onToggleExpand,
  selectedId,
  onSelect,
  onSelectBooking,
  onDrillDown,
  attentionOnly,
}: {
  rows: CalendarRow[];
  columns: Column[];
  /** Every DAY in range. Booking bars keep daily resolution at every zoom. */
  dates: string[];
  bookingsByRoomType: Map<number, Booking[]>;
  expanded: Set<number>;
  onToggleExpand: (roomTypeId: number) => void;
  selectedId: number | null;
  onSelect: (rec: Recommendation) => void;
  onSelectBooking: (b: Booking) => void;
  onDrillDown: (column: Column) => void;
  attentionOnly: boolean;
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
                  {/* Spans every date column, then lays its own grid on the same
                      track sizes so bars line up with the dates above. */}
                  <div className="min-w-0 bg-ink-50/30" style={{ gridColumn: "2 / -1" }}>
                    <BookingLanes
                      bookings={bookings}
                      dates={dates}
                      onSelectBooking={onSelectBooking}
                    />
                  </div>
                </>
              )}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
