"use client";

import { useTranslations } from "next-intl";
import { useFormat } from "@/lib/useFormat";
import { MarketRange, OccupancyStrip, PaceChart, RateBand } from "../viz";
import type { RangeDetail } from "@/lib/types";

/** The market band, low/high/median/count, computed once in the shell. */
export interface MarketBand {
  low: number;
  high: number;
  median: number;
  count: number;
}

export function RangeScopeBody({
  detail,
  market,
}: {
  detail: RangeDetail;
  market: MarketBand | null;
}) {
  const t = useTranslations("drawer");
  const tds = useTranslations("dataSource");
  const { formatVND, formatAdjPct } = useFormat();

  const leadTimes = (detail?.nightly ?? [])
    .map((n) => n.days_to_arrival)
    .filter((d): d is number => d !== null);

  return (
    <>
      {/* --------------------------------- A. what should I do */}
      <section>
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="text-[11px] text-ink-400">{t("recommendedNet")}</div>
            {/* Say that it is an average. Unlabelled, this reads as one price
                for the range rather than the mean of nights that disagree with
                each other -- and accepting it writes it to all of them. */}
            <div className="text-[11px] text-ink-500">
              {t("averageOf", { nights: detail.nights })}
            </div>
            <div className="tnum text-[30px] font-bold leading-tight text-brand-700">
              {formatVND(detail.average_recommended_net_rate)}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[11px] text-ink-400">{t("currentNet")}</div>
            <div className="tnum text-[14px] text-ink-600">
              {formatVND(detail.average_current_net_rate)}
            </div>
            {/* Blue Jay publishes no forward rate, so this figure is
                often RECONSTRUCTED from bookings. Silence here would
                let an operator read an achieved average as a list
                price, which is the whole reason the field exists. */}
            {detail.rate_provenance !== "published" && (
              <div
                className="mt-0.5 max-w-[13rem] text-[10px] leading-snug text-amber-700"
                title={tds("provenanceTitle")}
              >
                {/* "mixed" is a RANGE-level answer -- no provider
                    emits it -- so it gets its own string rather than
                    being smuggled into the provider vocabulary that
                    a guard test checks against the backend. */}
                {detail.rate_provenance === "mixed"
                  ? t("provenanceMixed")
                  : tds(`provenance.${detail.rate_provenance}`)}
              </div>
            )}
            <div
              className={`tnum text-[12.5px] font-semibold ${
                detail.average_recommended_net_rate >
                detail.average_current_net_rate * 1.005
                  ? "text-emerald-600"
                  : detail.average_recommended_net_rate <
                      detail.average_current_net_rate * 0.995
                    ? "text-amber-600"
                    : "text-ink-400"
              }`}
            >
              {formatAdjPct(
                detail.average_current_net_rate
                  ? ((detail.average_recommended_net_rate -
                      detail.average_current_net_rate) /
                      detail.average_current_net_rate) *
                      100
                  : 0,
              )}
            </div>
          </div>
        </div>
        <p className="mt-2 text-[11px] text-ink-400">{t("netRatesPlain")}</p>
      </section>

      {/* ------------------------------- B. inside my range? */}
      <section>
        <h3 className="mb-2 text-[12px] font-semibold text-ink-800">{t("bandTitle")}</h3>
        <RateBand
          min={detail.band.min}
          base={detail.band.base}
          max={detail.band.max}
          recommended={detail.average_recommended_net_rate}
          /* An AVERAGE is not itself clamped — the individual nights
             were. Claiming a clamp here would attribute one night's
             bound to the whole range. */
          clamped={null}
        />
      </section>

      {/* ----------------------------- C. how full is it? */}
      {/* Facts and the curve, no verdict. This used to open with "selling 7
          points slower than expected for this far out" -- a sentence in a
          vocabulary nobody outside revenue management reads, saying what the
          curve below it already shows. The numbers state where the range
          stands; the chart states whether that is normal. */}
      <section>
        <h3 className="mb-1 text-[12px] font-semibold text-ink-800">{t("paceTitle")}</h3>
        <div className="space-y-0.5 text-[11.5px] text-ink-600">
          <p>
            {t("roomNightsSold", {
              sold: detail.units_sold,
              total: detail.units_total * detail.nights,
            })}
          </p>
          {leadTimes.length > 0 && (
            <p>
              {Math.min(...leadTimes) === Math.max(...leadTimes)
                ? t("guestsArriveInOne", { days: Math.max(...leadTimes) })
                : t("guestsArriveInRange", {
                    min: Math.min(...leadTimes),
                    max: Math.max(...leadTimes),
                  })}
            </p>
          )}
        </div>
        {/* Actual against the booking curve the engine already computed. No
            `current`: every night in a range sits at its own lead time, so
            there is no single "you are here" to mark. */}
        <div className="mt-3">
          <PaceChart peers={detail.nightly} />
        </div>
        <div className="mt-3">
          <OccupancyStrip nights={detail.nightly} showDeltas />
        </div>
      </section>

      {/* There is no breakdown here. Averaging groups by (code, label_key),
          and `pace` alone has eight label variants -- so seven nights arrived
          as five contradictory pace rows that had to be badged with their own
          night counts just to be readable. One night explains itself cleanly;
          a range does not, so the explanation lives in the night scope. */}

      {/* ------------------------------- market context */}
      <section>
        <h3 className="mb-2 text-[12px] font-semibold text-ink-800">
          {t("marketTitle")}
        </h3>
        {market ? (
          <>
            <MarketRange
              low={market.low}
              high={market.high}
              reference={market.median}
              recommended={detail.average_recommended_net_rate}
              /* Market evidence informs; it never moves a price.
                 Everything the collector can reach is LOW confidence
                 and the engine's gate is MEDIUM. */
              applied={false}
            />
            <p className="mt-2 text-[11.5px] text-ink-500">
              {t("marketSummary", { count: market.count, confidence: "LOW" })}
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
