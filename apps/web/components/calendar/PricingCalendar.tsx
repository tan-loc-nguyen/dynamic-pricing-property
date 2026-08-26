"use client";

import { useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import { columnHeader, isToday, isWeekend, monthLabel, nightsBetween } from "@/lib/dates";
import { attentionReasons } from "@/lib/attention";
import { useFormat } from "@/lib/useFormat";
import type { FormatLocale } from "@/lib/format";
import type { Booking, Recommendation } from "@/lib/types";

/** Width of one date column. Wide enough for "2,35tr" without wrapping. */
const COL = 58;
/** Width of the frozen room-type column. */
const ROW_HEAD = 190;

export type CalendarRow = {
  roomTypeId: number;
  category: string;
  unitsTotal: number;
  byDate: Map<string, Recommendation>;
};

/** Compact money for a cell: 2.350.000 -> "2,35tr" (vi) / "2.35m" (en). */
function compactRate(value: number | null | undefined, locale: FormatLocale): string {
  if (value === null || value === undefined) return "—";
  const millions = value / 1_000_000;
  const digits = millions >= 10 ? 1 : 2;
  const n = millions.toFixed(digits).replace(/\.?0+$/, "");
  return locale === "vi" ? `${n.replace(".", ",")}tr` : `${n}m`;
}

/**
 * One night for one room type.
 *
 * Deliberately NOT a metrics panel. Price is the answer the operator came for;
 * everything else is a hint that there is more behind a click. The previous
 * table put ten numbers on this row and made the price compete with them.
 */
function PricingDateCell({
  rec,
  dateISO,
  selected,
  onSelect,
}: {
  rec: Recommendation | undefined;
  dateISO: string;
  selected: boolean;
  onSelect: (rec: Recommendation) => void;
}) {
  const locale = useLocale() as FormatLocale;
  const t = useTranslations("calendar");
  const { formatVND } = useFormat();

  if (!rec) {
    return (
      <div
        className="border-r border-b border-ink-100 bg-ink-50/40"
        style={{ width: COL }}
        aria-hidden
      />
    );
  }

  const reasons = attentionReasons(rec);
  const change = rec.change_pct ?? 0;
  const sold = rec.units_sold ?? 0;
  const total = rec.units_total ?? 0;
  const soldOut = total > 0 && sold >= total;
  const fill = total > 0 ? Math.min(1, sold / total) : 0;

  // Direction, not magnitude: the exact percentage lives in the drawer. An
  // arrow reads at a glance where "+4,2%" has to be parsed.
  const arrow = change > 0.5 ? "↑" : change < -0.5 ? "↓" : "≈";
  const arrowTone =
    change > 0.5 ? "text-emerald-600" : change < -0.5 ? "text-amber-600" : "text-ink-300";

  const title = [
    `${formatVND(rec.recommended_net_rate)}`,
    `${t("occupancyOf", { sold, total })}`,
    rec.is_event && rec.event_name ? `★ ${rec.event_name}` : "",
    reasons.length ? t("needsReview") : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      type="button"
      onClick={() => onSelect(rec)}
      title={title}
      aria-label={`${dateISO} ${formatVND(rec.recommended_net_rate)}`}
      className={`group relative border-r border-b border-ink-100 px-1 py-1.5 text-left transition-colors
        focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-inset
        ${selected ? "bg-brand-50" : soldOut ? "bg-ink-100/70 hover:bg-ink-100" : "hover:bg-brand-50/50"}`}
      style={{ width: COL }}
    >
      {/* At most two marks, both in the corner: something to review, and an
          event. Not a row of badges — the price has to stay the loudest thing
          in the cell. */}
      <span className="absolute top-0.5 right-0.5 flex items-center gap-0.5">
        {rec.is_event && (
          <span className="text-[8px] leading-none text-violet-500" aria-hidden>
            ★
          </span>
        )}
        {reasons.length > 0 && (
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />
        )}
      </span>

      <div className="flex items-baseline gap-0.5">
        <span
          className={`tnum text-[12px] font-semibold leading-none ${
            soldOut ? "text-ink-400" : "text-ink-900"
          }`}
        >
          {compactRate(rec.recommended_net_rate, locale)}
        </span>
        <span className={`text-[10px] leading-none ${arrowTone}`} aria-hidden>
          {arrow}
        </span>
      </div>

      {/* Availability as a shape first, digits second. */}
      <div className="mt-1.5 flex items-center gap-1">
        <div className="h-1 flex-1 rounded-full bg-ink-150 overflow-hidden">
          <div
            className={`h-full ${soldOut ? "bg-ink-400" : "bg-brand-400"}`}
            style={{ width: `${fill * 100}%` }}
          />
        </div>
        <span className="tnum text-[9.5px] leading-none text-ink-400">
          {soldOut ? t("full") : total - sold}
        </span>
      </div>
    </button>
  );
}

/**
 * Booking lanes for an expanded room type.
 *
 * Bars are positioned by their real check-in and length. They are NOT labelled
 * with an apartment number, because no booking in this system is assigned to
 * one — `physical_room_id` is null on every row (ASSUMPTIONS U11). Lanes are a
 * packing of overlapping stays, not a unit list, and the empty state says so.
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
    const sorted = [...bookings].sort((a, b) => a.stay_date.localeCompare(b.stay_date));
    for (const b of sorted) {
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
      <div
        className="border-b border-ink-100 px-3 py-2 text-[11.5px] text-ink-400"
        style={{ width: dates.length * COL }}
      >
        {t("noBookingsInRange")}
      </div>
    );
  }

  return (
    <div className="relative border-b border-ink-100" style={{ width: dates.length * COL }}>
      {lanes.map((lane, i) => (
        <div key={i} className="relative h-6">
          {lane.map((b) => {
            const offset = nightsBetween(first, b.stay_date);
            const span = nightsBetween(b.stay_date, b.last_night) + 1;
            const left = Math.max(0, offset) * COL;
            // Clip a stay that began before the window rather than dropping it.
            const clipped = offset < 0 ? span + offset : span;
            const width = Math.max(1, Math.min(clipped, dates.length - Math.max(0, offset))) * COL;
            if (width <= 0) return null;
            return (
              <button
                key={b.id}
                type="button"
                onClick={() => onSelectBooking(b)}
                title={`${b.channel} · ${b.nights}đ · ${formatVND(b.net_rate)}`}
                className="absolute top-0.5 h-5 rounded-md border border-sky-300 bg-sky-100/90 px-1.5
                  text-left text-[10px] leading-5 text-sky-900 truncate
                  hover:bg-sky-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
                style={{ left: left + 2, width: width - 4 }}
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
  dates,
  bookingsByRoomType,
  expanded,
  onToggleExpand,
  selectedId,
  onSelect,
  onSelectBooking,
  attentionOnly,
}: {
  rows: CalendarRow[];
  dates: string[];
  bookingsByRoomType: Map<number, Booking[]>;
  expanded: Set<number>;
  onToggleExpand: (roomTypeId: number) => void;
  selectedId: number | null;
  onSelect: (rec: Recommendation) => void;
  onSelectBooking: (b: Booking) => void;
  attentionOnly: boolean;
}) {
  const locale = useLocale() as FormatLocale;
  const t = useTranslations("calendar");
  const tv = useTranslations("vocab");

  // Month bands above the day columns, so a 60-day range still reads.
  const months = useMemo(() => {
    const out: { label: string; span: number }[] = [];
    for (const iso of dates) {
      const label = monthLabel(iso, locale);
      const last = out[out.length - 1];
      if (last && last.label === label) last.span += 1;
      else out.push({ label, span: 1 });
    }
    return out;
  }, [dates, locale]);

  return (
    <div className="overflow-auto h-full">
      <div style={{ width: ROW_HEAD + dates.length * COL }}>
        {/* ---------------------------------------------------- header */}
        <div className="sticky top-0 z-20 bg-white">
          <div className="flex border-b border-ink-100">
            <div
              className="sticky left-0 z-10 bg-white border-r border-ink-200"
              style={{ width: ROW_HEAD }}
            />
            {months.map((m) => (
              <div
                key={m.label}
                className="border-r border-ink-100 px-2 py-1 text-[10.5px] font-medium uppercase tracking-wide text-ink-400"
                style={{ width: m.span * COL }}
              >
                {m.label}
              </div>
            ))}
          </div>

          <div className="flex border-b border-ink-200">
            <div
              className="sticky left-0 z-10 flex items-end bg-white border-r border-ink-200 px-3 pb-1.5"
              style={{ width: ROW_HEAD }}
            >
              <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                {t("roomType")}
              </span>
            </div>
            {dates.map((iso) => {
              const { weekday, day } = columnHeader(iso, locale);
              const today = isToday(iso);
              const weekend = isWeekend(iso);
              return (
                <div
                  key={iso}
                  className={`border-r border-ink-100 px-1 py-1 text-center ${
                    today ? "bg-brand-50" : weekend ? "bg-ink-50/60" : "bg-white"
                  }`}
                  style={{ width: COL }}
                >
                  <div
                    className={`text-[9.5px] font-medium uppercase leading-tight ${
                      today ? "text-brand-700" : "text-ink-400"
                    }`}
                  >
                    {weekday}
                  </div>
                  <div
                    className={`tnum text-[11.5px] leading-tight ${
                      today ? "font-bold text-brand-700" : "font-medium text-ink-700"
                    }`}
                  >
                    {day}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ------------------------------------------------------ rows */}
        {rows.map((row) => {
          const isOpen = expanded.has(row.roomTypeId);
          const bookings = bookingsByRoomType.get(row.roomTypeId) ?? [];
          return (
            <div key={row.roomTypeId}>
              <div className="flex">
                <div
                  className="sticky left-0 z-10 flex items-center gap-1.5 bg-white border-r border-b border-ink-200 px-2"
                  style={{ width: ROW_HEAD }}
                >
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

                {dates.map((iso) => {
                  const rec = row.byDate.get(iso);
                  const dim = attentionOnly && rec && attentionReasons(rec).length === 0;
                  return (
                    <div key={iso} className={dim ? "opacity-30" : undefined}>
                      <PricingDateCell
                        rec={rec}
                        dateISO={iso}
                        selected={!!rec && rec.id === selectedId}
                        onSelect={onSelect}
                      />
                    </div>
                  );
                })}
              </div>

              {isOpen && (
                <div className="flex bg-ink-50/30">
                  <div
                    className="sticky left-0 z-10 bg-ink-50 border-r border-b border-ink-200 px-2 py-2"
                    style={{ width: ROW_HEAD }}
                  >
                    <div className="text-[11px] font-medium text-ink-600">{t("bookings")}</div>
                    <div className="text-[10px] text-ink-400">{t("unitUnassigned")}</div>
                  </div>
                  <BookingLanes
                    bookings={bookings}
                    dates={dates}
                    onSelectBooking={onSelectBooking}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
