/** Presentation helpers. VND is rendered without decimals — nobody prices in xu.
 *
 * Every formatter takes a locale, because the same rate is not written the same
 * way in both: 2,300,000 ₫ in English, 2.300.000 ₫ in Vietnamese. Dates go
 * through Intl rather than hardcoded month arrays for the same reason.
 */

export type FormatLocale = "en" | "vi";

const intlLocale = (locale: FormatLocale) => (locale === "vi" ? "vi-VN" : "en-US");

export function formatVND(
  value: number | null | undefined,
  locale: FormatLocale,
  opts: { compact?: boolean } = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (opts.compact && Math.abs(value) >= 1_000_000) {
    // "tr" (triệu) in Vietnamese, "m" in English. The calendar cells and the
    // rate band both use this, so a mismatch here showed the same rate as
    // "2,3tr" in one place and "2,3M" in the other on the same screen.
    const sign = value < 0 ? "−" : "";
    const unit = locale === "vi" ? "tr" : "m";
    return `${sign}${decimal(value / 1_000_000, locale, 1)}${unit} ₫`;
  }
  return `${Math.round(value).toLocaleString(intlLocale(locale))} ₫`;
}

export function formatSignedVND(value: number | null | undefined, locale: FormatLocale): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(Math.round(value)).toLocaleString(intlLocale(locale))} ₫`;
}

function decimal(value: number, locale: FormatLocale, digits: number): string {
  return Math.abs(value).toLocaleString(intlLocale(locale), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPct(
  value: number | null | undefined,
  locale: FormatLocale,
  digits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${decimal(value, locale, digits)}%`;
}

function parseISODate(iso: string): Date {
  // Parse as LOCAL time. `new Date("2026-08-22")` is parsed as UTC and can
  // render as the previous day in negative-offset timezones.
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

export function formatStayDate(iso: string, locale: FormatLocale): string {
  return new Intl.DateTimeFormat(intlLocale(locale), {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(parseISODate(iso));
}

export function formatLongDate(iso: string, locale: FormatLocale): string {
  return new Intl.DateTimeFormat(intlLocale(locale), {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(parseISODate(iso));
}

export function formatDateTime(iso: string, locale: FormatLocale): string {
  const date = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return new Intl.DateTimeFormat(intlLocale(locale), {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function isWeekend(iso: string): boolean {
  const day = parseISODate(iso).getDay();
  return day === 0 || day === 5 || day === 6;
}

export function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function addDaysISO(iso: string, days: number): string {
  const d = parseISODate(iso);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function confidenceTone(c: string | null | undefined): "up" | "info" | "warn" | "neutral" {
  if (c === "HIGH") return "up";
  if (c === "MEDIUM") return "info";
  if (c === "LOW") return "warn";
  return "neutral";
}

/** Additive percentage-point adjustment, e.g. "+4.0%". */
export function formatAdjPct(value: number | null | undefined, locale: FormatLocale): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (Math.abs(value) < 0.05) return decimal(0, locale, 1) + "%";
  return `${value > 0 ? "+" : "−"}${decimal(value, locale, 1)}%`;
}
