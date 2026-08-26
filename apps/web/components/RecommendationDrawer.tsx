"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { useAdjustmentText } from "@/lib/adjustments";
import { useFormat } from "@/lib/useFormat";
import { MarketRange, PaceChart, PriceContribution, RateBand } from "./viz";
import { Button } from "./ui";
import type { MarketObservation, Recommendation, RecommendationDetail } from "@/lib/types";

/**
 * The answer to "what should I do about this night?", in the order an owner
 * asks it: what to do -> is it inside my range -> how is the date selling ->
 * why did the price move -> what does the market say -> decide.
 *
 * Radix Dialog rather than the previous hand-rolled panel: that one had no
 * focus trap, did not restore focus on close, and left the page behind it
 * reachable by Tab. §33 asks for all three and none of them are worth
 * re-implementing.
 */
export function RecommendationDrawer({
  recommendation,
  peers,
  onClose,
  onChanged,
}: {
  recommendation: Recommendation | null;
  peers: Recommendation[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const t = useTranslations("drawer");
  const tds = useTranslations("dataSource");
  const tv = useTranslations("vocab");
  const tc = useTranslations("common");
  const { formatVND, formatAdjPct, formatLongDate } = useFormat();
  const adjustmentText = useAdjustmentText();

  const [detail, setDetail] = useState<RecommendationDetail | null>(null);
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

  const id = recommendation?.id ?? null;

  useEffect(() => {
    if (id === null) return;
    setDetail(null);
    setObservations([]);
    setOverriding(false);
    setError(null);
    let alive = true;
    api
      .recommendation(id)
      .then((d) => {
        if (!alive) return;
        setDetail(d);
        setOverrideRate(String(Math.round(d.recommended_net_rate)));
      })
      .catch((e) => alive && setError(e?.message ?? tc("unknownError")));
    // Real observed prices for this night, so the market band is a range that
    // actually exists rather than one inferred from a single index number.
    if (recommendation) {
      api
        .observations({
          room_type_id: recommendation.room_type_id,
          stay_date: recommendation.stay_date,
        })
        .then((o) => alive && setObservations(o))
        .catch(() => {
          /* market context is optional; the rest of the drawer still works */
        });
    }
    return () => {
      alive = false;
    };
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

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

  const rec = detail ?? recommendation;
  // The engine publishes this directly; inferring it from `status` was how
  // the branch got lost, because the Status union omitted "error".
  const unpriced = rec?.unpriced === true;
  const open = recommendation !== null;

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink-900/20 backdrop-blur-[1px]" />
        <Dialog.Content
          className="fixed right-0 top-0 z-50 flex h-screen w-full max-w-[560px] flex-col bg-white shadow-2xl
            focus:outline-none"
          aria-describedby={undefined}
        >
          {rec ? (
            <>
              {/* ------------------------------------------------ header */}
              <header className="shrink-0 border-b border-ink-100 px-5 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Dialog.Title className="text-[15px] font-semibold text-ink-900">
                      {tv(`roomCategories.${rec.room_category}`)}
                    </Dialog.Title>
                    <p className="mt-0.5 text-[12px] text-ink-500">
                      {formatLongDate(rec.stay_date)}
                      {rec.season_key ? ` · ${tv(`seasonsShort.${rec.season_key}`)}` : ""}
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
                {rec.is_event && rec.event_name && (
                  <div className="mt-2.5 flex items-center gap-1.5 rounded-lg bg-violet-50 border border-violet-200 px-2.5 py-1.5">
                    <span aria-hidden>★</span>
                    <span className="text-[11.5px] text-violet-900">{rec.event_name}</span>
                  </div>
                )}
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
                        {formatVND(rec.recommended_net_rate)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[11px] text-ink-400">{t("currentNet")}</div>
                      <div className="tnum text-[14px] text-ink-600">
                        {formatVND(rec.current_net_rate)}
                      </div>
                      {/* Blue Jay publishes no forward rate, so this figure is
                          often RECONSTRUCTED from bookings. Silence here would
                          let an operator read an achieved average as a list
                          price, which is the whole reason the field exists.
                          Shown only when it is not a published rate — saying
                          "published" on every demo row would be noise. */}
                      {rec.rate_provenance && rec.rate_provenance !== "published" && (
                        <div
                          className="mt-0.5 max-w-[13rem] text-[10px] leading-snug text-amber-700"
                          title={tds("provenanceTitle")}
                        >
                          {rec.rate_provenance === "derived_adr" && tds("provenance.derived_adr")}
                          {rec.rate_provenance === "last_known_adr" && tds("provenance.last_known_adr")}
                          {/* seasonal_base is the MOST COMMON non-published value:
                              it catches every night with no bookings, which is most
                              of a 90-day horizon. Omitting it drew a styled, empty
                              box on exactly the dates needing the most explanation. */}
                          {rec.rate_provenance === "seasonal_base" && tds("provenance.seasonal_base")}
                          {rec.rate_provenance === "unavailable" && tds("provenance.unavailable")}
                        </div>
                      )}
                      <div
                        className={`tnum text-[12.5px] font-semibold ${
                          rec.change_pct > 0.5
                            ? "text-emerald-600"
                            : rec.change_pct < -0.5
                              ? "text-amber-600"
                              : "text-ink-400"
                        }`}
                      >
                        {formatAdjPct(rec.change_pct)}
                      </div>
                    </div>
                  </div>
                  <p className="mt-2 text-[11px] text-ink-400">{t("netRatesPlain")}</p>
                </section>

                {/* ------------------------------- B. inside my range? */}
                <section>
                  <h3 className="mb-2 text-[12px] font-semibold text-ink-800">{t("bandTitle")}</h3>
                  <RateBand
                    min={rec.band_min_net_rate}
                    base={rec.band_base_net_rate}
                    max={rec.band_max_net_rate}
                    recommended={rec.recommended_net_rate}
                    clamped={rec.clamp_applied}
                  />
                </section>

                {/* ----------------------------- C. how is it selling? */}
                <section>
                  <h3 className="mb-1 text-[12px] font-semibold text-ink-800">{t("paceTitle")}</h3>
                  <p className="mb-2 text-[12px] text-ink-600">
                    {rec.pace_gap === null
                      ? t("paceUnknown")
                      : t("pacePlain", {
                          direction: rec.pace_gap >= 0 ? "ahead" : "behind",
                          points: Math.abs(Math.round(rec.pace_gap * 100)),
                        })}
                  </p>
                  <div className="flex gap-4 text-[11.5px] text-ink-500">
                    <span>
                      {t("paceOnTheBooks")}{" "}
                      <span className="tnum font-medium text-ink-800">
                        {rec.units_sold ?? 0}/{rec.units_total ?? 0}
                      </span>
                    </span>
                    <span>
                      {t("paceLeadTime")}{" "}
                      <span className="tnum font-medium text-ink-800">
                        D-{rec.days_to_arrival ?? "—"}
                      </span>
                    </span>
                  </div>
                  <PaceChart peers={peers} current={rec} />
                </section>

                {/* ------------------------------ D. why did it move? */}
                <section>
                  <h3 className="mb-2 text-[12px] font-semibold text-ink-800">{t("whyTitle")}</h3>
                  {detail ? (
                    <>
                      <PriceContribution
                        adjustments={detail.adjustments}
                        render={adjustmentText}
                      />
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
                    </>
                  ) : (
                    <div className="text-[11.5px] text-ink-400">{tc("loading")}</div>
                  )}
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
                        recommended={rec.recommended_net_rate}
                        applied={rec.market_qualified_count > 0}
                      />
                      <p className="mt-2 text-[11.5px] text-ink-500">
                        {t("marketSummary", {
                          count: market.count,
                          confidence: rec.market_confidence ?? "—",
                        })}
                      </p>
                      {rec.market_qualified_count === 0 && (
                        <p className="mt-1.5 rounded-md bg-ink-50 px-2.5 py-1.5 text-[11.5px] text-ink-600">
                          {t("marketReferenceOnly")}
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="text-[11.5px] text-ink-400">{t("marketNone")}</p>
                  )}
                </section>

                {/* ------------------------- past decisions on this date */}
                {detail && detail.decisions.length > 0 && (
                  <section>
                    <h3 className="mb-2 text-[12px] font-semibold text-ink-800">
                      {t("decisionsOnDate")}
                    </h3>
                    <ul className="space-y-1.5">
                      {detail.decisions.map((d) => (
                        <li
                          key={d.id}
                          className="flex items-center justify-between rounded-lg bg-ink-50 px-2.5 py-1.5 text-[11.5px]"
                        >
                          <span className="text-ink-600">{tv(`status.${d.decision}`)}</span>
                          <span className="tnum text-ink-800">
                            {formatVND(d.final_net_rate)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </div>

              {/* ------------------------------------- sticky actions */}
              <footer className="shrink-0 border-t border-ink-100 bg-white px-5 py-3">
                {error && (
                  <div className="mb-2 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[11.5px] text-rose-700">
                    {error}
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
                        {/* From the SERVER's whitelist, not a copy of it. The
                            inline array had silently lost `channel_mix`, which
                            the backend still accepts and the vocabulary still
                            translates — so it was simply unselectable, and the
                            two lists could drift again without anything
                            noticing. */}
                        {reasonCodes.map((code) => (
                          <option key={code} value={code}>
                            {tv(`overrideReasons.${code}`)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="flex gap-2">
                      <Button
                        variant="primary"
                        disabled={busy || !overrideRate}
                        onClick={() =>
                          act(() => api.override(rec.id, Number(overrideRate), reasonCode))
                        }
                      >
                        {tc("save")}
                      </Button>
                      <Button onClick={() => setOverriding(false)} disabled={busy}>
                        {tc("cancel")}
                      </Button>
                    </div>
                  </div>
                ) : unpriced ? (
                  /* The engine could not price this night. Its `recommended`
                     equals `current`, so without this branch the drawer shows a
                     confident rate that was never calculated and Accept fails
                     with a 409 from the server. */
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] text-amber-800">
                    {t("unpriced")}
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <Button
                      variant="primary"
                      className="flex-1"
                      disabled={busy}
                      onClick={() => act(() => api.accept(rec.id))}
                    >
                      {t("acceptRate", { rate: formatVND(rec.recommended_net_rate) })}
                    </Button>
                    <Button onClick={() => setOverriding(true)} disabled={busy}>
                      {t("adjust")}
                    </Button>
                  </div>
                )}
              </footer>
            </>
          ) : (
            <div className="p-6 text-[12px] text-ink-400">{tc("loading")}</div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
