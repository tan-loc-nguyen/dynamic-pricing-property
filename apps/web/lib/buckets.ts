import {
  addDays,
  differenceInCalendarDays,
  eachWeekOfInterval,
  endOfWeek,
  format,
  startOfDay,
  startOfWeek,
} from "date-fns";
import { columnHeader, parseStayDate, toISODate } from "./dates";
import type { FormatLocale } from "./format";

/**
 * Bucketing a date range into day or week periods.
 *
 * Extracted from the deleted calendar model: the grid is gone, but the market
 * report still offers the same day/week granularity and must bucket dates
 * exactly the way the range picker does. Two views of the same period that
 * disagreed about where a week starts would be worse than either being wrong
 * alone.
 *
 * Day columns and week columns are the same shape, so a caller only knows one.
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
