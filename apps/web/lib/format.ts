/** Presentation helpers. VND is rendered without decimals — nobody prices in xu. */

export function formatVND(value: number | null | undefined, opts: { compact?: boolean } = {}): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (opts.compact && Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M ₫`;
  }
  return `${Math.round(value).toLocaleString("en-US")} ₫`;
}

export function formatSignedVND(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(Math.round(value)).toLocaleString("en-US")} ₫`;
}

export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(digits)}%`;
}

export function formatOccupancy(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

export function formatFactor(value: number): string {
  return `×${value.toFixed(3).replace(/0+$/, "").replace(/\.$/, ".0")}`;
}

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parseISODate(iso: string): Date {
  // Parse as LOCAL time. `new Date("2026-08-22")` is parsed as UTC and can
  // render as the previous day in negative-offset timezones.
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

export function formatStayDate(iso: string): string {
  const date = parseISODate(iso);
  return `${DAYS[date.getDay()]} ${date.getDate()} ${MONTHS[date.getMonth()]}`;
}

export function formatLongDate(iso: string): string {
  const date = parseISODate(iso);
  return `${DAYS[date.getDay()]}, ${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}, ${String(
    date.getHours(),
  ).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
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

/** Booking pace index -> operator-readable label. */
export function paceLabel(index: number | null | undefined): string {
  if (index === null || index === undefined) return "No data";
  if (index < 0.4) return "Very weak";
  if (index < 0.8) return "Weak";
  if (index < 1.3) return "On pace";
  if (index < 2.0) return "Strong";
  return "Very strong";
}

/** Market price index -> operator-readable label. */
export function marketLabel(index: number | null | undefined): string {
  if (index === null || index === undefined) return "No data";
  if (index < 0.92) return "Soft";
  if (index < 0.98) return "Below market";
  if (index <= 1.02) return "In line";
  if (index <= 1.1) return "Above market";
  return "Strong";
}
