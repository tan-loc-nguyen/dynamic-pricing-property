import {
  addDays,
  differenceInCalendarDays,
  eachWeekOfInterval,
  endOfWeek,
  format,
  startOfDay,
  startOfWeek,
} from "date-fns";
import { attentionReasons } from "./attention";
import { columnHeader, parseStayDate, toISODate } from "./dates";
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
  //
  // NO locale here, deliberately. bucketKeyFor passes weekStartsOn alone, and
  // the two agree only because an explicit weekStartsOn beats locale.options.
  // Passing a locale that cannot change the answer implies it could, and these
  // two disagreeing about where a week starts is the one thing that would
  // corrupt every bucket.
  const opts = { weekStartsOn: 1 as const };
  return eachWeekOfInterval({ start, end }, opts).map((weekStart) => {
    const from = weekStart < start ? start : weekStart;
    // startOfDay: endOfWeek returns Sunday 23:59:59.999, and a millisecond
    // short of seven whole days rounds UP — every full week reported 8 nights,
    // which meant `soldOutNights === column.nights` could never be true and a
    // sold-out week never rendered as sold out.
    const weekEnd = startOfDay(endOfWeek(weekStart, opts));
    const to = weekEnd > end ? end : weekEnd;
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
      // Calendar days, not elapsed milliseconds: immune to both the
      // time-of-day above and to any DST transition inside the week.
      nights: differenceInCalendarDays(to, from) + 1,
    };
  });
}

/**
 * Which bucket a stay date belongs to, without scanning the column list.
 *
 * Exported because the market overview buckets the same way: two views of the
 * same period that disagreed about where a week starts would be worse than
 * either being wrong on its own.
 */
export function bucketKeyFor(
  stayISO: string,
  granularity: Granularity,
  // REQUIRED, deliberately. As an optional parameter this said "a caller
  // cannot forget it" while `bucketKeyFor(iso, "week")` still compiled and
  // silently returned the unclamped Monday — reintroducing the exact bug the
  // clamp exists to prevent. A caller with genuinely no columns passes
  // `undefined` and has to mean it.
  firstColumnKey: string | undefined,
): string {
  if (granularity === "day") return stayISO;
  const key = toISODate(startOfWeek(parseStayDate(stayISO), { weekStartsOn: 1 }));
  // A week clipped by the range start is keyed by the range START, not by the
  // Monday before it, because that is the key buildColumns gave the column.
  // This clamp used to live in buildRows only, so the market overview bucketed
  // the same way and then did NOT clamp — silently discarding every date in
  // the first partial week. Folding it in here means a caller cannot forget it.
  return firstColumnKey && key < firstColumnKey ? firstColumnKey : key;
}

export function buildRows(
  recs: Recommendation[],
  granularity: Granularity,
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
    const key = bucketKeyFor(r.stay_date, granularity, firstColumn);
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
    // A ratio of sums, NOT a mean of ratios. The arrow has to describe the rate
    // printed above it, and mean(change_pct) is a different statistic that
    // drifts from it — measured at up to 0.39pp on this data, which is small
    // only until it straddles zero and points the wrong way. This is also
    // revenue-weighted rather than night-weighted, which is the more useful
    // reading of "how much did the week move".
    changePct: (() => {
      const before = group.reduce((s, r) => s + (r.current_net_rate ?? 0), 0);
      const after = group.reduce((s, r) => s + (r.recommended_net_rate ?? 0), 0);
      return before ? ((after - before) / before) * 100 : 0;
    })(),
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
