"use client";

import { useEffect, useRef } from "react";
import { useTranslations } from "next-intl";
import { useFormat } from "@/lib/useFormat";
import type { RangeNight } from "@/lib/types";

/**
 * Choose which night the drawer is showing.
 *
 * This replaced the occupancy chart as the way to move between nights. The
 * chart could be clicked, but it did not look like it could: bars of varying
 * height read as a data visualisation, and a visualisation is not somewhere an
 * operator expects to click. It also had no hover state at all, so there was no
 * feedback until after the click had already happened.
 *
 * The hover treatment here is lifted verbatim from the Rate page's tile grid
 * -- brass border over a faint wash -- because the operator clicked one of
 * those tiles to open this drawer. Reusing it means the affordance is already
 * learned rather than introduced.
 *
 * Each chip carries the PRICE rather than the distance from the range average.
 * In this scope the average is not what is being accepted, so the price is the
 * figure the operator is actually deciding about, and it is the one that makes
 * a night worth opening.
 */
export function NightPicker({
  nights,
  selected,
  onSelect,
}: {
  nights: RangeNight[];
  selected: string;
  onSelect: (stayDate: string) => void;
}) {
  const t = useTranslations("drawer");
  const { formatVND, formatStayDate } = useFormat();
  const selectedRef = useRef<HTMLButtonElement | null>(null);

  // Keep the chosen night on screen when the range is long enough to scroll.
  // Instant for anyone who has asked for less motion -- this is navigation, so
  // it still has to move, it just must not animate.
  useEffect(() => {
    const node = selectedRef.current;
    if (!node) return;
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    node.scrollIntoView({
      behavior: reduced ? "auto" : "smooth",
      block: "nearest",
      inline: "nearest",
    });
  }, [selected]);

  return (
    <div
      role="group"
      aria-label={t("nightPickerLabel")}
      className="scrollbar-slim flex shrink-0 gap-2 overflow-x-auto border-b border-ink-100
        px-5 pb-2 pt-2.5"
    >
      {nights.map((n) => {
        const isSelected = n.stay_date === selected;
        const handTuned = n.decision === "overridden";

        return (
          <button
            key={n.stay_date}
            ref={isSelected ? selectedRef : undefined}
            type="button"
            onClick={() => onSelect(n.stay_date)}
            aria-pressed={isSelected}
            aria-label={
              n.priced
                ? t("nightPickerOption", {
                    date: formatStayDate(n.stay_date),
                    price: formatVND(n.recommended_net_rate),
                  })
                : t("nightPickerOptionUnpriced", { date: formatStayDate(n.stay_date) })
            }
            // A floor width rather than natural sizing: "Sat, Sep 12" is wider
            // than "Sun, Sep 6", and chips that each shrink to their own label
            // give the row a ragged edge that reads as sloppy rather than as a
            // calendar.
            className={`relative min-w-[4.75rem] shrink-0 rounded-lg border px-2.5 py-1.5
              text-left transition-colors focus:outline-none focus-visible:ring-2
              focus-visible:ring-brand-500 ${
                isSelected
                  ? // ring rather than a thicker border: a 2px border would
                    // shift every neighbouring chip by a pixel on selection.
                    "border-brand-600 bg-brand-50 ring-1 ring-brand-600"
                  : n.priced
                    ? "border-ink-200 bg-white hover:border-brand-300 hover:bg-brand-50/40"
                    : "border-amber-200 bg-amber-50/50 hover:border-amber-300 hover:bg-amber-50"
              }`}
          >
            <div
              className={`whitespace-nowrap text-[10.5px] leading-tight ${
                isSelected ? "text-brand-700" : "text-ink-500"
              }`}
            >
              {formatStayDate(n.stay_date)}
            </div>
            <div
              className={`tnum whitespace-nowrap text-[12.5px] font-semibold leading-tight ${
                !n.priced
                  ? "text-amber-700"
                  : isSelected
                    ? "text-brand-800"
                    : "text-ink-800"
              }`}
            >
              {n.priced ? formatVND(n.recommended_net_rate, { compact: true }) : "—"}
            </div>
            {handTuned && (
              <span
                data-hand-tuned
                aria-label={t("stripHandTuned")}
                className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-violet-500"
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
