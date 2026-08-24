"use client";

import { useLocale } from "next-intl";
import { useMemo } from "react";
import {
  formatAdjPct,
  formatDateTime,
  formatLongDate,
  formatSignedVND,
  formatPct,
  formatStayDate,
  formatVND,
  type FormatLocale,
} from "./format";

/**
 * The locale-dependent formatters, bound to the current locale.
 *
 * Destructuring this keeps the original call signatures at every site, so
 * `formatVND(rate)` still reads the same — it just now writes 2.300.000 ₫ for a
 * Vietnamese viewer and 2,300,000 ₫ for an English one.
 */
export function useFormat() {
  const locale = useLocale() as FormatLocale;

  return useMemo(
    () => ({
      formatVND: (value: number | null | undefined, opts: { compact?: boolean } = {}) =>
        formatVND(value, locale, opts),
      formatSignedVND: (value: number | null | undefined) => formatSignedVND(value, locale),
      formatStayDate: (iso: string) => formatStayDate(iso, locale),
      formatLongDate: (iso: string) => formatLongDate(iso, locale),
      formatDateTime: (iso: string) => formatDateTime(iso, locale),
      formatPct: (value: number | null | undefined, digits = 1) =>
        formatPct(value, locale, digits),
      formatAdjPct: (value: number | null | undefined) => formatAdjPct(value, locale),
    }),
    [locale],
  );
}
