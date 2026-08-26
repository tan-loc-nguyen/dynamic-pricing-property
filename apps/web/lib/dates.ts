import { addDays, differenceInCalendarDays, format, isSameDay, parseISO, startOfDay } from "date-fns";
import { enUS, vi } from "date-fns/locale";
import type { FormatLocale } from "./format";

/**
 * Stay-date arithmetic, in one place.
 *
 * A stay date is a CALENDAR date, not an instant. The previous hand-rolled
 * helpers split the ISO string and rebuilt a local `Date` precisely to dodge
 * `new Date("2026-08-22")` being parsed as UTC and rendering as the day before
 * in a negative-offset timezone. date-fns `parseISO` has the same local
 * semantics for a date-only string, so that behaviour is preserved — and the
 * month-boundary and DST cases the manual version never handled come with it.
 */

const locales = { vi, en: enUS } as const;

export const dfnsLocale = (locale: FormatLocale) => locales[locale] ?? enUS;

/** ISO `YYYY-MM-DD` -> a local midnight Date. */
export function parseStayDate(iso: string): Date {
  return startOfDay(parseISO(iso));
}

/** A local Date -> ISO `YYYY-MM-DD`, never shifted by a timezone. */
export function toISODate(d: Date): string {
  return format(d, "yyyy-MM-dd");
}

export function todayISO(): string {
  return toISODate(new Date());
}

export function addDaysISO(iso: string, days: number): string {
  return toISODate(addDays(parseStayDate(iso), days));
}

export function nightsBetween(startISO: string, endISO: string): number {
  return differenceInCalendarDays(parseStayDate(endISO), parseStayDate(startISO));
}

/** Every date from start to end inclusive — the calendar's column axis. */
export function dateRange(startISO: string, endISO: string): string[] {
  const total = nightsBetween(startISO, endISO);
  if (total < 0) return [];
  return Array.from({ length: total + 1 }, (_, i) => addDaysISO(startISO, i));
}

export function isToday(iso: string): boolean {
  return isSameDay(parseStayDate(iso), new Date());
}

export function isWeekend(iso: string): boolean {
  const day = parseStayDate(iso).getDay();
  // Friday counts: a Friday night is a weekend night for an accommodation
  // business even though the calendar week says otherwise.
  return day === 0 || day === 5 || day === 6;
}

/** Two-line column header: "TH 5" over "27/8". */
export function columnHeader(iso: string, locale: FormatLocale): { weekday: string; day: string } {
  const d = parseStayDate(iso);
  const opts = { locale: dfnsLocale(locale) };
  return {
    weekday: format(d, "EEEEEE", opts).toUpperCase(),
    day: locale === "vi" ? format(d, "d/M") : format(d, "d MMM", opts),
  };
}

/** "Tháng 8 2026" / "August 2026" — the span label above the columns. */
export function monthLabel(iso: string, locale: FormatLocale): string {
  return format(parseStayDate(iso), "LLLL yyyy", { locale: dfnsLocale(locale) });
}
