"use client";

import { useTranslations } from "next-intl";

/**
 * What the marks in a cell mean.
 *
 * The calendar leans on four small signals to keep the price the loudest thing
 * in a cell, and none of them is self-explanatory the first time. A legend is
 * what buys the right to use a 6px dot instead of a labelled badge — without
 * it, the compactness is just information withheld.
 *
 * Deliberately short: only marks a reader cannot guess. "Hết" and the
 * occupancy bar carry their own words and numbers, so they are not here.
 */
export function CalendarLegend() {
  const t = useTranslations("calendar.legend");

  return (
    <ul className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-ink-500">
      <li className="flex items-center gap-1">
        <span className="text-[9px] text-violet-500" aria-hidden>
          ★
        </span>
        {t("event")}
      </li>
      <li className="flex items-center gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />
        {t("attention")}
      </li>
      <li className="flex items-center gap-1">
        <span className="text-[10px] leading-none" aria-hidden>
          <span className="text-emerald-600">↑</span>
          <span className="text-amber-600">↓</span>
        </span>
        {t("direction")}
      </li>
      <li className="flex items-center gap-1">
        <span
          className="h-2.5 w-3.5 rounded-sm border border-ink-200 bg-[repeating-linear-gradient(135deg,transparent,transparent_3px,rgba(0,0,0,0.06)_3px,rgba(0,0,0,0.06)_6px)]"
          aria-hidden
        />
        {t("noPricing")}
      </li>
    </ul>
  );
}
