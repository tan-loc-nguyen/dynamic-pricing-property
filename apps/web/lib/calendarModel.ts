import { addDays, eachWeekOfInterval, endOfWeek, format, startOfWeek } from "date-fns";
import { attentionReasons } from "./attention";
import { columnHeader, dfnsLocale, parseStayDate, toISODate } from "./dates";
import type { FormatLocale } from "./format";
import type { Recommendation } from "./types";

/**
 * Day columns and week columns are the same shape, so the grid only knows one.
 *
 * Beyond about a month, per-night columns stop being useful and start being a
 * wall: nobody prices a specific Tuesday eighty days out, and at 180 columns
 * nothing is legible anyway. Collapsing to weeks answers the question actually
 * being asked at that horizon — which periods are filling up.
 *
 * Merging equal-price runs was the other candidate and does not work here: the
 * average run is 1.8 nights, so 180 days collapse to ~100 tiles. Prices are
 * recomputed nightly and legitimately differ; bookings are what genuinely span,
 * and those keep true daily resolution in their own lane at every range.
 */
export type Granularity = "day" | "week";

export type Column = {
  key: string;
  startISO: string;
  endISO: string;
  /** Two-line header: weekday over date, or week number over its date span. */
  top: string;
  bottom: string;
  isToday: boolean;
  isWeekend: boolean;
  /** Days covered — 1 for a day column, up to 7 for a week. */
  nights: number;
};

/**
 * One cell's worth of pricing, whether that is one night or a week of them.
 *
 * `single` is set only when the cell IS one recommendation, which is what makes
 * it openable in the drawer. A week has no single recommendation to explain, so
 * clicking it drills down instead of opening one arbitrarily.
 */
export type Cell = {
  rate: number | null;
  changePct: number;
  sold: number;
  total: number;
  soldOutNights: number;
  isEvent: boolean;
  attention: boolean;
  single: Recommendation | null;
  count: number;
};

export type CalendarRow = {
  roomTypeId: number;
  category: string;
  unitsTotal: number;
  byColumn: Map<string, Cell>;
};

export function buildColumns(
  startISO: string,
  endISO: string,
  granularity: Granularity,
  locale: FormatLocale,
): Column[] {
  const today = toISODate(new Date());
  const start = parseStayDate(startISO);
  const end = parseStayDate(endISO);

  if (granularity === "day") {
    const out: Column[] = [];
    for (let d = start; d <= end; d = addDays(d, 1)) {
      const iso = toISODate(d);
      const { weekday, day } = columnHeader(iso, locale);
      const dow = d.getDay();
      out.push({
        key: iso,
        startISO: iso,
        endISO: iso,
        top: weekday,
        bottom: day,
        isToday: iso === today,
        isWeekend: dow === 0 || dow === 5 || dow === 6,
        nights: 1,
      });
    }
    return out;
  }

  // Weeks start Monday: a Vietnamese week does, and a Mon-Sun block keeps the
  // weekend together, which is the part an accommodation business reads.
  const opts = { weekStartsOn: 1 as const, locale: dfnsLocale(locale) };
  return eachWeekOfInterval({ start, end }, opts).map((weekStart) => {
    const from = weekStart < start ? start : weekStart;
    const to = endOfWeek(weekStart, opts) > end ? end : endOfWeek(weekStart, opts);
    const fromISO = toISODate(from);
    const toISO = toISODate(to);
    return {
      key: fromISO,
      startISO: fromISO,
      endISO: toISO,
      top: `${format(from, "d/M")}`,
      bottom: `→ ${format(to, "d/M")}`,
      isToday: today >= fromISO && today <= toISO,
      isWeekend: false, // a week contains one; highlighting it says nothing
      nights: Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1,
    };
  });
}

/** Which column a stay date belongs to, without scanning the column list. */
function columnKeyFor(stayISO: string, granularity: Granularity, locale: FormatLocale): string {
  if (granularity === "day") return stayISO;
  return toISODate(
    startOfWeek(parseStayDate(stayISO), { weekStartsOn: 1, locale: dfnsLocale(locale) }),
  );
}

export function buildRows(
  recs: Recommendation[],
  granularity: Granularity,
  locale: FormatLocale,
  columns: Column[],
): CalendarRow[] {
  const firstColumn = columns[0]?.startISO;
  const byType = new Map<number, { row: CalendarRow; buckets: Map<string, Recommendation[]> }>();

  for (const r of recs) {
    let entry = byType.get(r.room_type_id);
    if (!entry) {
      entry = {
        row: {
          roomTypeId: r.room_type_id,
          category: r.room_category,
          unitsTotal: r.units_total ?? 0,
          byColumn: new Map(),
        },
        buckets: new Map(),
      };
      byType.set(r.room_type_id, entry);
    }
    let key = columnKeyFor(r.stay_date, granularity, locale);
    // A week clipped by the range start is keyed by the range start, not by the
    // Monday before it — otherwise the first partial week has no column.
    if (firstColumn && key < firstColumn) key = firstColumn;
    const bucket = entry.buckets.get(key);
    if (bucket) bucket.push(r);
    else entry.buckets.set(key, [r]);
  }

  for (const { row, buckets } of byType.values()) {
    for (const [key, group] of buckets) {
      row.byColumn.set(key, summarise(group));
    }
  }

  return [...byType.values()]
    .map((e) => e.row)
    .sort((a, b) => a.category.localeCompare(b.category));
}

function summarise(group: Recommendation[]): Cell {
  const rates = group.map((r) => r.recommended_net_rate).filter((v) => typeof v === "number");
  const sold = group.reduce((s, r) => s + (r.units_sold ?? 0), 0);
  const total = group.reduce((s, r) => s + (r.units_total ?? 0), 0);
  return {
    // The mean, not the first: a week's headline rate has to describe the week.
    rate: rates.length ? rates.reduce((s, v) => s + v, 0) / rates.length : null,
    changePct: group.reduce((s, r) => s + (r.change_pct ?? 0), 0) / Math.max(group.length, 1),
    sold,
    total,
    soldOutNights: group.filter(
      (r) => (r.units_total ?? 0) > 0 && (r.units_sold ?? 0) >= (r.units_total ?? 0),
    ).length,
    isEvent: group.some((r) => r.is_event),
    attention: group.some((r) => attentionReasons(r).length > 0),
    single: group.length === 1 ? group[0] : null,
    count: group.length,
  };
}
