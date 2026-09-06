"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { useAdjustmentText } from "@/lib/adjustments";
import { useFormat } from "@/lib/useFormat";
import { MarketRange, OccupancyStrip, PriceContribution, RateBand } from "../viz";
import type { MarketObservation, RangeDetail, RangeNight } from "@/lib/types";
import type { MarketBand } from "./RangeScopeBody";

export function NightScopeBody({
  detail,
  night,
  observations,
  onSelect,
}: {
  detail: RangeDetail;
  night: RangeNight;
  market: MarketBand | null;
  observations: MarketObservation[];
  onSelect: (stayDate: string) => void;
}) {
  const t = useTranslations("drawer");
  const tds = useTranslations("dataSource");
  const { formatVND, formatLongDate } = useFormat();
  const adjustmentText = useAdjustmentText();

  const nightObservations = useMemo(
    () => observations.filter((o) => o.stay_date === night.stay_date),
    [observations, night.stay_date],
  );

  const nightMarket = useMemo(() => {
    const prices = nightObservations
      .map((o) => o.observed_price)
      .filter((p): p is number => typeof p === "number" && p > 0)
      .sort((a, b) => a - b);
    if (prices.length < 2) return null;
    return {
      low: prices[0],
      high: prices[prices.length - 1],
      median: prices[Math.floor(prices.length / 2)],
      count: prices.length,
    };
  }, [nightObservations]);

  return (
    <>
      {/* --------------------------------- A. what should I do */}
      <section>
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="text-[11px] text-ink-400">{t("recommendedNet")}</div>
            <div className="text-[11px] text-ink-500">{formatLongDate(night.stay_date)}</div>
            <div className="tnum text-[30px] font-bold leading-tight text-brand-700">
              {formatVND(night.recommended_net_rate)}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[11px] text-ink-400">{t("currentNet")}</div>
            <div className="tnum text-[14px] text-ink-600">
              {formatVND(night.current_net_rate)}
            </div>
            {/* Blue Jay publishes no forward rate, so this figure is
                often RECONSTRUCTED from bookings. Silence here would
                let an operator read an achieved average as a list
                price, which is the whole reason the field exists. */}
            {night.rate_provenance !== "published" && (
              <div
                className="mt-0.5 max-w-[13rem] text-[10px] leading-snug text-amber-700"
                title={tds("provenanceTitle")}
              >
                {/* "mixed" is a RANGE-level answer -- no provider
                    emits it -- so it gets its own string rather than
                    being smuggled into the provider vocabulary that
                    a guard test checks against the backend. */}
                {night.rate_provenance === "mixed"
                  ? t("provenanceMixed")
                  : tds(`provenance.${night.rate_provenance}`)}
              </div>
            )}
          </div>
        </div>
        <p className="mt-2 text-[11px] text-ink-400">{t("netRatesPlain")}</p>
      </section>

      {/* ------------------------------- B. inside my range? */}
      <section>
        <h3 className="mb-2 text-[12px] font-semibold text-ink-800">{t("bandTitle")}</h3>
        <RateBand
          min={night.band.min}
          base={night.band.base}
          max={night.band.max}
          recommended={night.recommended_net_rate}
          clamped={night.clamped}
        />
      </section>

      {/* ----------------------------- C. how is it selling? */}
      <section>
        <h3 className="mb-1 text-[12px] font-semibold text-ink-800">{t("paceTitle")}</h3>
        <div className="mt-1">
          <OccupancyStrip
            nights={detail.nightly}
            selected={night.stay_date}
            onSelect={onSelect}
            showDeltas
          />
        </div>
      </section>

      {/* ------------------------------ D. why did it move? */}
      <section>
        <h3 className="mb-2 text-[12px] font-semibold text-ink-800">{t("whyTitle")}</h3>
        <PriceContribution
          adjustments={night.adjustments}
          render={adjustmentText}
          totalNights={1}
        />
        <details className="mt-3 group">
          <summary className="cursor-pointer text-[11.5px] text-brand-600 hover:underline">
            {t("showReasoning")}
          </summary>
          <ul className="mt-2 space-y-2">
            {night.adjustments.map((a, i) => {
              const { label, reason } = adjustmentText(a);
              if (!reason) return null;
              return (
                <li key={i} className="text-[11.5px] leading-relaxed text-ink-600">
                  <span className="font-medium text-ink-800">{label}.</span> {reason}
                </li>
              );
            })}
          </ul>
        </details>
      </section>

      {/* ------------------------------- market context */}
      <section>
        <h3 className="mb-2 text-[12px] font-semibold text-ink-800">
          {t("marketTitle")}
        </h3>
        {nightMarket ? (
          <>
            <MarketRange
              low={nightMarket.low}
              high={nightMarket.high}
              reference={nightMarket.median}
              recommended={night.recommended_net_rate}
              /* Market evidence informs; it never moves a price.
                 Everything the collector can reach is LOW confidence
                 and the engine's gate is MEDIUM. */
              applied={false}
            />
            <p className="mt-2 text-[11.5px] text-ink-500">
              {t("marketSummary", { count: nightMarket.count, confidence: "LOW" })}
            </p>
            <p className="mt-1.5 rounded-md bg-ink-50 px-2.5 py-1.5 text-[11.5px] text-ink-600">
              {t("marketReferenceOnly")}
            </p>
          </>
        ) : (
          <p className="text-[11.5px] text-ink-400">{t("marketNone")}</p>
        )}
      </section>
    </>
  );
}
