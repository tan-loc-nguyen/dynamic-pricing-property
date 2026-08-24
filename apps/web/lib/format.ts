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

/** Pace gap (fraction) -> operator-readable label. Mirrors the engine's bands. */
export function paceLabel(gap: number | null | undefined): string {
  if (gap === null || gap === undefined) return "No data";
  if (gap < -0.2) return "Well behind";
  if (gap < -0.08) return "Behind";
  if (gap <= 0.08) return "On pace";
  if (gap <= 0.2) return "Ahead";
  return "Well ahead";
}

export function paceTone(gap: number | null | undefined): "up" | "down" | "info" | "neutral" {
  if (gap === null || gap === undefined) return "neutral";
  if (gap < -0.08) return "down";
  if (gap > 0.08) return "up";
  return "info";
}

/** Pace gap rendered in percentage points, e.g. "+14pp". */
export function formatPaceGap(gap: number | null | undefined): string {
  if (gap === null || gap === undefined) return "—";
  const pts = Math.round(gap * 100);
  return `${pts > 0 ? "+" : pts < 0 ? "−" : ""}${Math.abs(pts)}pp`;
}

/** Recent pickup delta -> label. */
export function pickupLabel(delta: number | null | undefined): string {
  if (delta === null || delta === undefined) return "No data";
  if (delta < -1.0) return "Stalled";
  if (delta < -0.25) return "Slowing";
  if (delta <= 0.5) return "As expected";
  if (delta <= 2.0) return "Accelerating";
  return "Surging";
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

export function confidenceTone(c: string | null | undefined): "up" | "info" | "warn" | "neutral" {
  if (c === "HIGH") return "up";
  if (c === "MEDIUM") return "info";
  if (c === "LOW") return "warn";
  return "neutral";
}

/** Additive percentage-point adjustment, e.g. "+4.0%". */
export function formatAdjPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (Math.abs(value) < 0.05) return "0.0%";
  return `${value > 0 ? "+" : "−"}${Math.abs(value).toFixed(1)}%`;
}
