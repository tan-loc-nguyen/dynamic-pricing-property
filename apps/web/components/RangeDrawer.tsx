"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { useAdjustmentText } from "@/lib/adjustments";
import { useFormat } from "@/lib/useFormat";
import { MarketRange, OccupancyStrip, PaceChart, PriceContribution, RateBand } from "./viz";
import { Button } from "@/components/ui/button";
import type { MarketObservation, RangeDetail } from "@/lib/types";

/**
 * The answer to "what should I charge for this tier over these nights?", in
 * the order an owner asks it: what to do -> is it inside my range -> how is it
 * selling -> why did the price move -> what does the market say -> decide.
 *
 * A RANGE, not a night. Accepting writes one price to every night in the
 * selection, so the per-night strip under the pace curve is load-bearing: it
 * is the only place a range whose nights disagree with each other becomes
 * visible before the operator commits one number to all of them.
 */
export interface RangeSelection {
  roomTypeId: number;
  startDate: string;
  endDate: string;
}

export function RangeDrawer({
  selection,
  onClose,
  onChanged,
}: {
  selection: RangeSelection | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const t = useTranslations("drawer");
  const tds = useTranslations("dataSource");
  const tv = useTranslations("vocab");
  const tc = useTranslations("common");
  const { formatVND, formatAdjPct, formatLongDate } = useFormat();
  const adjustmentText = useAdjustmentText();

  const [detail, setDetail] = useState<RangeDetail | null>(null);
  const [observations, setObservations] = useState<MarketObservation[]>([]);
  const [busy, setBusy] = useState(false);
  const [overriding, setOverriding] = useState(false);
  const [overrideRate, setOverrideRate] = useState("");
  const [reasonCode, setReasonCode] = useState("my_judgment");
  const [error, setError] = useState<string | null>(null);
  const [reasonCodes, setReasonCodes] = useState<string[]>(["my_judgment"]);

  useEffect(() => {
    api
      .status()
      .then((s) => setReasonCodes(s.override_reasons.map((r) => r.code)))
      .catch(() => {
        /* keep the safe default rather than blocking the override form */
      });
  }, []);

  const key = selection
    ? `${selection.roomTypeId}:${selection.startDate}:${selection.endDate}`
    : null;

  useEffect(() => {
    if (!selection) return;
    setDetail(null);
    setObservations([]);
    setOverriding(false);
    setError(null);
    let alive = true;
    api
      .rateRange(selection.roomTypeId, selection.startDate, selection.endDate)
      .then((d) => {
        if (!alive) return;
        setDetail(d);
        setOverrideRate(String(Math.round(d.average_recommended_net_rate)));
      })
      .catch((e) => alive && setError(e?.message ?? tc("unknownError")));
    // Real observed prices across the range, so the market band is a range
    // that actually exists rather than one inferred from an index number.
    api
      .observations({
        room_type_id: selection.roomTypeId,
        start_date: selection.startDate,
        end_date: selection.endDate,
      })
      .then((o) => alive && setObservations(o))
      .catch(() => {
        /* market context is optional; the rest of the drawer still works */
      });
    return () => {
      alive = false;
    };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const market = useMemo(() => {
    const prices = observations
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
  }, [observations]);

  const act = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await fn();
        onChanged();
        onClose();
      } catch (e: any) {
        setError(e?.message ?? tc("unknownError"));
      } finally {
        setBusy(false);
      }
    },
    [onChanged, onClose, tc],
  );

  const open = selection !== null;
  // Every night failed to price. Accepting would write a number the engine
  // never calculated, so the action is withdrawn rather than left to fail.
  const allUnpriced = !!detail && detail.unpriced_nights >= detail.nights;
  const leadTimes = (detail?.nightly ?? [])
    .map((n) => n.days_to_arrival)
    .filter((d): d is number => d !== null);

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink-900/20 backdrop-blur-[1px]" />
        <Dialog.Content
          className="fixed right-0 top-0 z-50 flex h-screen w-full max-w-[560px] flex-col bg-white shadow-2xl
            focus:outline-none"
          aria-describedby={undefined}
        >
          {detail ? (
            <>
              {/* ------------------------------------------------ header */}
              <header className="shrink-0 border-b border-ink-100 px-5 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Dialog.Title className="text-[15px] font-semibold text-ink-900">
                      {tv(`roomCategories.${detail.room_category}`)}
                    </Dialog.Title>
                    <p className="mt-0.5 text-[12px] text-ink-500">
                      {detail.nights === 1
                        ? formatLongDate(detail.start_date)
                        : t("rangeNights", {
                            from: formatLongDate(detail.start_date),
                            to: formatLongDate(detail.end_date),
                            nights: detail.nights,
                          })}
                      {detail.season?.key ? ` · ${tv(`seasonsShort.${detail.season.key}`)}` : ""}
                    </p>
                  </div>
                  <Dialog.Close asChild>
                    <button
                      className="rounded-lg px-2 py-1 text-[12px] text-ink-500 hover:bg-ink-100
                        focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                    >
                      {t("close")}
                    </button>
                  </Dialog.Close>
                </div>
              </header>

              <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
                {/* --------------------------------- A. what should I do */}
                <section>
                  <div className="flex items-end justify-between gap-4">
                    <div>
                      <div className="text-[11px] uppercase tracking-wide text-ink-400">
                        {t("recommendedNet")}
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

                {/* ----------------------------- C. how is it selling? */}
                <section>
                  <h3 className="mb-1 text-[12px] font-semibold text-ink-800">{t("paceTitle")}</h3>
                  <p className="mb-2 text-[12px] text-ink-600">
                    {detail.pace_gap === null
                      ? t("paceUnknown")
                      : t("pacePlain", {
                          direction: detail.pace_gap >= 0 ? "ahead" : "behind",
                          points: Math.abs(Math.round(detail.pace_gap * 100)),
                        })}
                  </p>
                  <div className="flex flex-wrap gap-4 text-[11.5px] text-ink-500">
                    <span>
                      {t("paceOnTheBooks")}{" "}
                      <span className="tnum font-medium text-ink-800">
                        {detail.units_sold}/{detail.units_total * detail.nights}
                      </span>
                    </span>
                    {leadTimes.length > 0 && (
                      <span>
                        {t("paceLeadTime")}{" "}
                        <span className="tnum font-medium text-ink-800">
                          D-{Math.min(...leadTimes)}
                          {leadTimes.length > 1 && ` … D-${Math.max(...leadTimes)}`}
                        </span>
                      </span>
                    )}
                  </div>
                  <PaceChart peers={detail.nightly} />
                  <div className="mt-3">
                    <OccupancyStrip nights={detail.nightly} />
                  </div>
                </section>

                {/* ------------------------------ D. why did it move? */}
                <section>
                  <h3 className="mb-2 text-[12px] font-semibold text-ink-800">{t("whyTitle")}</h3>
                  <PriceContribution adjustments={detail.adjustments} render={adjustmentText} />
                  <details className="mt-3 group">
                    <summary className="cursor-pointer text-[11.5px] text-brand-600 hover:underline">
                      {t("showReasoning")}
                    </summary>
                    <ul className="mt-2 space-y-2">
                      {detail.adjustments.map((a, i) => {
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
              </div>

              {/* ------------------------------------- sticky actions */}
              <footer className="shrink-0 border-t border-ink-100 bg-white px-5 py-3">
                {error && (
                  <div className="mb-2 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[11.5px] text-rose-700">
                    {error}
                  </div>
                )}
                {/* Some nights priced, some not. Accepting still works and the
                    server skips the failures -- but silently covering fewer
                    nights than the operator selected is exactly the kind of
                    partial success that has to be said out loud. */}
                {!allUnpriced && detail.unpriced_nights > 0 && (
                  <div className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11.5px] text-amber-800">
                    {t("someUnpriced", { count: detail.unpriced_nights })}
                  </div>
                )}
                {overriding ? (
                  <div className="space-y-2">
                    <label className="block text-[11.5px] text-ink-600">
                      {t("yourNetRate")}
                      <input
                        autoFocus
                        inputMode="numeric"
                        value={overrideRate}
                        onChange={(e) => setOverrideRate(e.target.value.replace(/[^\d]/g, ""))}
                        className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 tnum text-[14px]
                          focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                      />
                    </label>
                    <label className="block text-[11.5px] text-ink-600">
                      {t("reason")}
                      <select
                        value={reasonCode}
                        onChange={(e) => setReasonCode(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-[12.5px]
                          focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                      >
                        {/* From the SERVER's whitelist, not a copy of it. */}
                        {reasonCodes.map((code) => (
                          <option key={code} value={code}>
                            {tv(`overrideReasons.${code}`)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="flex gap-2">
                      <Button
                        variant="default"
                        disabled={busy || !overrideRate}
                        onClick={() =>
                          act(() =>
                            api.overrideRange(
                              detail.room_type_id,
                              detail.start_date,
                              detail.end_date,
                              Number(overrideRate),
                              reasonCode,
                            ),
                          )
                        }
                      >
                        {tc("save")}
                      </Button>
                      <Button variant="secondary" onClick={() => setOverriding(false)} disabled={busy}>
                        {tc("cancel")}
                      </Button>
                    </div>
                  </div>
                ) : allUnpriced ? (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] text-amber-800">
                    {t("unpriced")}
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <Button
                      variant="default"
                      className="flex-1"
                      disabled={busy}
                      onClick={() =>
                        act(() =>
                          api.acceptRange(
                            detail.room_type_id,
                            detail.start_date,
                            detail.end_date,
                          ),
                        )
                      }
                    >
                      {t("acceptRate", {
                        rate: formatVND(detail.average_recommended_net_rate),
                      })}
                    </Button>
                    <Button variant="secondary" onClick={() => setOverriding(true)} disabled={busy}>
                      {t("adjust")}
                    </Button>
                  </div>
                )}
              </footer>
            </>
          ) : (
            <div className="p-6 text-[12px] text-ink-400">
              {error ? (
                <span className="text-rose-700">{error}</span>
              ) : (
                tc("loading")
              )}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
