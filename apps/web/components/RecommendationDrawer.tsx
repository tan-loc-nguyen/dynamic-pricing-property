"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { confidenceTone, formatOccupancy, formatPaceGap, marketBucket } from "@/lib/format";
import { useFormat } from "@/lib/useFormat";
import { useAdjustmentText, useBandLabel } from "@/lib/adjustments";
import { useTranslations } from "next-intl";
import type { RecommendationDetail, SystemStatus } from "@/lib/types";
import { Button, Chip, Field, StatusBadge, inputClass } from "./ui";

function SignalTile({
  label,
  value,
  hint,
  muted,
}: {
  label: string;
  value: string;
  hint?: string;
  muted?: boolean;
}) {
  return (
    <div className="rounded-lg border border-ink-200 px-3 py-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-ink-400">{label}</div>
      <div className={`text-[14px] font-semibold mt-0.5 tnum ${muted ? "text-ink-300" : "text-ink-900"}`}>
        {value}
      </div>
      {hint && <div className="text-[10px] text-ink-400 mt-0.5 leading-tight">{hint}</div>}
    </div>
  );
}

/** The validated seasonal band, and where the recommendation sits inside it. */
function RateBandStrip({ detail }: { detail: RecommendationDetail }) {
  const { formatVND } = useFormat();
  const t = useTranslations("drawer");
  const tv = useTranslations("vocab");
  const lo = detail.band_min_net_rate;
  const hi = detail.band_max_net_rate;
  const base = detail.band_base_net_rate;
  if (lo === null || hi === null || base === null || hi <= lo) return null;

  const pos = (v: number) => Math.min(100, Math.max(0, ((v - lo) / (hi - lo)) * 100));

  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 px-3.5 py-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[11.5px] font-semibold text-emerald-900">
          {detail.season_key ? tv(`seasons.${detail.season_key}`) : "—"}
          <span className="font-normal text-emerald-700"> · {detail.room_category ? tv(`roomCategories.${detail.room_category}`) : detail.room_type_name}</span>
        </div>
        <Chip tone="up">{t("clientValidated")}</Chip>
      </div>

      <div className="relative h-8 mt-3 mb-1">
        <div className="absolute top-3.5 left-0 right-0 h-1.5 rounded-full bg-emerald-200" />
        <div
          className="absolute top-2.5 h-3.5 w-0.5 bg-emerald-500"
          style={{ left: `${pos(base)}%` }}
          title={`${t("band.base")} ${formatVND(base)}`}
        />
        <div
          className="absolute top-1.5 -translate-x-1/2 h-5 w-5 rounded-full border-2 border-white bg-brand-600 shadow"
          style={{ left: `${pos(detail.recommended_net_rate)}%` }}
          title={`${t("recommendedNet")} ${formatVND(detail.recommended_net_rate)}`}
        />
      </div>

      <div className="flex justify-between text-[10.5px] tnum text-emerald-800">
        <span>{t("band.min")} {formatVND(lo)}</span>
        <span className="text-emerald-600">{t("band.base")} {formatVND(base)}</span>
        <span>{t("band.max")} {formatVND(hi)}</span>
      </div>
      <div className="text-[10.5px] text-emerald-700 mt-1.5">
        {t("band.note")}
      </div>
    </div>
  );
}

/** The calculation: validated band -> dynamic layer -> clamp -> rounding. */
function Breakdown({ detail }: { detail: RecommendationDetail }) {
  const { formatVND, formatSignedVND, formatAdjPct } = useFormat();
  const t = useTranslations("drawer");
  const adjustmentText = useAdjustmentText();
  return (
    <div className="rounded-xl border border-ink-200 overflow-hidden">
      <div className="divide-y divide-ink-100">
        {detail.adjustments.map((adj) => {
          const up = adj.delta > 0.5;
          const down = adj.delta < -0.5;
          const isBand = adj.code === "rate_band";
          const isClamp = adj.code === "band_min_clamp" || adj.code === "band_max_clamp";
          const isBound = adj.code === "dynamic_bound";
          const text = adjustmentText(adj);

          return (
            <div
              key={adj.sequence}
              className={`px-3.5 py-2.5 ${isBand ? "bg-ink-50" : adj.is_ignored ? "bg-amber-50/40" : ""}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className={`text-[12.5px] font-medium ${
                        adj.is_ignored
                          ? "text-amber-800"
                          : adj.is_neutral
                            ? "text-ink-400"
                            : "text-ink-900"
                      }`}
                    >
                      {text.label}
                    </span>
                    {isBand && <Chip tone="up">{t("chip.validated")}</Chip>}
                    {isClamp && <Chip tone="warn">{t("chip.bandLimit")}</Chip>}
                    {isBound && <Chip tone="warn">{t("chip.bounded")}</Chip>}
                    {adj.is_ignored && <Chip tone="warn">{t("chip.ignored")}</Chip>}
                    {adj.is_neutral && !adj.is_ignored && !isBand && (
                      <Chip tone="neutral">{t("chip.noEffect")}</Chip>
                    )}
                  </div>
                  {text.reason && (
                    <div className="text-[11px] text-ink-500 mt-1 leading-snug">{text.reason}</div>
                  )}
                </div>

                <div className="text-right shrink-0">
                  {!isBand && (
                    <div
                      className={`tnum text-[12px] font-semibold ${
                        adj.is_ignored || adj.is_neutral ? "text-ink-300" : "text-ink-600"
                      }`}
                    >
                      {adj.adjustment_pct !== 0 ? formatAdjPct(adj.adjustment_pct) : ""}
                    </div>
                  )}
                  <div
                    className={`tnum text-[12px] font-medium ${
                      up ? "text-emerald-600" : down ? "text-rose-600" : "text-ink-300"
                    }`}
                  >
                    {isBand
                      ? formatVND(adj.price_after)
                      : adj.is_ignored || adj.is_neutral
                        ? "—"
                        : formatSignedVND(adj.delta)}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between px-3.5 py-3 bg-brand-50 border-t border-brand-200">
        <span className="text-[12px] font-semibold text-brand-700">{t("recommendedNet")}</span>
        <span className="tnum text-[16px] font-bold text-brand-700">
          {formatVND(detail.recommended_net_rate)}
        </span>
      </div>
    </div>
  );
}

export function RecommendationDrawer({
  recommendationId,
  status,
  onClose,
  onChanged,
}: {
  recommendationId: number | null;
  status: SystemStatus | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { formatLongDate, formatSignedVND, formatVND, formatPct } = useFormat();
  const t = useTranslations("drawer");
  const tv = useTranslations("vocab");
  const bandLabel = useBandLabel();
  const [detail, setDetail] = useState<RecommendationDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"view" | "override">("view");
  const [overrideRate, setOverrideRate] = useState("");
  const [reasonCode, setReasonCode] = useState("my_judgment");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!recommendationId) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setError(null);
    setMode("view");
    setNote("");
    api
      .recommendation(recommendationId)
      .then((d) => {
        setDetail(d);
        setOverrideRate(String(Math.round(d.recommended_net_rate)));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [recommendationId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!recommendationId) return null;

  const act = async (fn: () => Promise<RecommendationDetail>) => {
    setBusy(true);
    setError(null);
    try {
      setDetail(await fn());
      setMode("view");
      onChanged();
    } catch (e: any) {
      setError(e.message || t("actionFailed"));
    } finally {
      setBusy(false);
    }
  };

  const reasons = status?.override_reasons || [{ code: "my_judgment", label: "" }];
  const outOfBand =
    detail && detail.band_min_net_rate !== null && detail.band_max_net_rate !== null
      ? Number(overrideRate) < detail.band_min_net_rate ||
        Number(overrideRate) > detail.band_max_net_rate
      : false;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink-950/25" onClick={onClose} />
      <div className="relative w-full max-w-xl bg-white shadow-2xl overflow-y-auto animate-slide-in">
        {loading && <div className="p-6 text-[13px] text-ink-400">{t("loading")}</div>}

        {detail && (
          <>
            <div className="sticky top-0 bg-white border-b border-ink-200 px-5 py-4 z-10">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h2 className="text-[16px] font-semibold text-ink-900 leading-tight">
                      {detail.room_category ? tv(`roomCategories.${detail.room_category}`) : detail.room_type_name}
                    </h2>
                    <StatusBadge status={detail.status} />
                    <Chip tone="up">{t("shadow")}</Chip>
                  </div>
                  <div className="text-[12px] text-ink-500 mt-1">
                    {formatLongDate(detail.stay_date)}
                    {detail.is_event && detail.event_name && (
                      <span className="text-amber-600 font-medium"> · {detail.event_name}</span>
                    )}
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={onClose}>
                  {t("close")}
                </Button>
              </div>
            </div>

            <div className="p-5 space-y-5">
              {/* headline */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-xl border border-ink-200 px-3.5 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-ink-400 font-medium">{t("currentNet")}</div>
                  <div className="text-[17px] font-semibold text-ink-700 tnum mt-1">
                    {formatVND(detail.current_net_rate)}
                  </div>
                </div>
                <div className="rounded-xl border-2 border-brand-300 bg-brand-50 px-3.5 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-brand-500 font-medium">
                    {t("recommendedNet")}
                  </div>
                  <div className="text-[17px] font-bold text-brand-700 tnum mt-1">
                    {formatVND(detail.recommended_net_rate)}
                  </div>
                </div>
                <div className="rounded-xl border border-ink-200 px-3.5 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-ink-400 font-medium">{t("change")}</div>
                  <div
                    className={`text-[17px] font-semibold tnum mt-1 ${
                      detail.change_pct > 0 ? "text-emerald-600" : detail.change_pct < 0 ? "text-rose-600" : "text-ink-400"
                    }`}
                  >
                    {formatPct(detail.change_pct)}
                  </div>
                  <div className="text-[11px] text-ink-400 tnum mt-0.5">
                    {formatSignedVND(detail.change_abs)}
                  </div>
                </div>
              </div>

              <div className="rounded-lg bg-ink-50 border border-ink-200 px-3 py-2 text-[11px] text-ink-600">
                {t.rich("netRatesNote", {
                  term: (chunks) => <span className="font-semibold">{chunks}</span>,
                })}
                {detail.current_ota_price !== null &&
                  t("otaOnFile", { price: formatVND(detail.current_ota_price) })}
              </div>

              {/* 1-2. which band, and why the base is what it is */}
              <RateBandStrip detail={detail} />

              {/* 3-6. the demand signals */}
              <div>
                <div className="text-[12px] font-semibold text-ink-700 mb-2">{t("demandSignals")}</div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <SignalTile
                    label={t("signal.occupancy")}
                    value={formatOccupancy(detail.occupancy)}
                    hint={
                      detail.units_sold !== null
                        ? t("unitsSold", {
                            sold: detail.units_sold ?? 0,
                            total: detail.units_total ?? 0,
                            left: detail.units_available ?? 0,
                          })
                        : undefined
                    }
                    muted={detail.occupancy === null}
                  />
                  <SignalTile
                    label={t("signal.daysToArrival")}
                    value={detail.days_to_arrival !== null ? `D-${detail.days_to_arrival}` : "—"}
                    hint={
                      detail.expected_occupancy !== null
                        ? t("signal.curveExpects", { value: formatOccupancy(detail.expected_occupancy) })
                        : t("signal.noCurve")
                    }
                    muted={detail.days_to_arrival === null}
                  />
                  <SignalTile
                    label={t("signal.pace")}
                    value={bandLabel(detail.pace_label_key, detail.pace_label || t("signal.noData"))}
                    hint={detail.pace_gap !== null ? formatPaceGap(detail.pace_gap) : t("signal.noData")}
                    muted={detail.pace_gap === null}
                  />
                  <SignalTile
                    label={t("signal.pickup")}
                    value={bandLabel(detail.pickup_label_key, detail.pickup_label || t("signal.noData"))}
                    hint={
                      detail.recent_pickup !== null
                        ? t("signal.bookingsInWindow", { count: detail.recent_pickup ?? 0 })
                        : t("signal.noBookingData")
                    }
                    muted={detail.pickup_delta === null}
                  />
                </div>

                <div className="mt-2 flex flex-wrap gap-2">
                  {detail.market_qualified_count > 0 ? (
                    <Chip tone={confidenceTone(detail.market_confidence)}>
                      {t("market.label")} {t(`market.bucket.${marketBucket(detail.market_price_index)}`)} ·{" "}
                      {t("market.observations", {
                        count: detail.market_qualified_count,
                        confidence: tv(`confidence.${detail.market_confidence ?? "UNUSABLE"}`),
                      })}
                    </Chip>
                  ) : detail.market_ignored_count > 0 ? (
                    <Chip tone="warn">
                      {t("market.ignored", { count: detail.market_ignored_count })}
                    </Chip>
                  ) : (
                    <Chip tone="neutral">{t("market.none")}</Chip>
                  )}
                  {detail.is_event && (
                    <Chip tone="warn">
                      Event: {detail.event_name} ({detail.event_impact_level} impact)
                    </Chip>
                  )}
                </div>

                {detail.missing_signals.length > 0 && (
                  <div className="mt-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[11px] text-amber-800">
                    <span className="font-semibold">{t("blindSpots")}</span>{" "}
                    {detail.missing_signals.join(", ")} — {t("blindSpotsBody")}.
                  </div>
                )}
              </div>

              {/* 3-9. the full calculation */}
              <div>
                <div className="text-[12px] font-semibold text-ink-700 mb-2">
                  {t("calculation")}
                </div>
                {detail.unpriced ? (
                  <div className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2.5 text-[12px] text-rose-900">
                    <div className="font-semibold">{t("unpriced")}</div>
                    {detail.unpriced_reason && (
                      <div className="mt-1 font-mono text-[11px] text-rose-700 break-all">
                        {detail.unpriced_reason}
                      </div>
                    )}
                  </div>
                ) : (
                  <Breakdown detail={detail} />
                )}
                <div className="text-[10.5px] text-ink-400 mt-2">
                  {t("engineLine", {
                    engine: detail.engine_version,
                    config: detail.config_version,
                  })}{" "}
                  <span className="text-emerald-600 font-medium">{t("validatedTag")}</span> · {t("dynamicLayer")}{" "}
                  <span className="text-amber-600 font-medium">{t("unvalidatedTag")}</span>
                </div>
              </div>

              {/* outcomes */}
              {detail.outcomes.length > 0 && (
                <div>
                  <div className="text-[12px] font-semibold text-ink-700 mb-2">{t("outcome")}</div>
                  {detail.outcomes.map((o) => (
                    <div
                      key={o.id}
                      className="rounded-lg border border-ink-200 px-3 py-2 text-[11.5px] flex items-center justify-between"
                    >
                      <span className="text-ink-600">
                        {o.units_booked} booked · realised {formatVND(o.realized_net_rate)}
                      </span>
                      {o.is_synthetic && <Chip tone="warn">{t("synthetic")}</Chip>}
                    </div>
                  ))}
                </div>
              )}

              {/* decisions */}
              {detail.decisions.length > 0 && (
                <div>
                  <div className="text-[12px] font-semibold text-ink-700 mb-2">{t("decisionsOnDate")}</div>
                  <div className="space-y-1.5">
                    {detail.decisions.map((d) => (
                      <div key={d.id} className="rounded-lg border border-ink-200 px-3 py-2 text-[11.5px]">
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-ink-800 capitalize">{d.decision}</span>
                          <span className="tnum text-ink-600">{formatVND(d.final_net_rate)}</span>
                        </div>
                        {d.reason_label && <div className="text-ink-500 mt-0.5">Reason: {d.reason_label}</div>}
                        {d.note && <div className="text-ink-500 mt-0.5 italic">“{d.note}”</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {error && (
                <div className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-[12px] text-rose-700">
                  {error}
                </div>
              )}
            </div>

            {/* actions */}
            <div className="sticky bottom-0 bg-white border-t border-ink-200 px-5 py-3.5">
              {mode === "view" ? (
                <div className="flex items-center gap-2">
                  <Button
                    variant="primary"
                    disabled={busy}
                    onClick={() => act(() => api.accept(detail.id, note || undefined))}
                  >
                    {t("acceptRate", { rate: formatVND(detail.recommended_net_rate) })}
                  </Button>
                  <Button disabled={busy} onClick={() => setMode("override")}>
                    {t("overrideEllipsis")}
                  </Button>
                  {detail.status !== "pending" && (
                    <Button variant="ghost" size="sm" disabled={busy} onClick={() => act(() => api.resetDecision(detail.id))}>
                      Reset to pending
                    </Button>
                  )}
                </div>
              ) : (
                <div className="space-y-2.5">
                  <div className="grid grid-cols-2 gap-2.5">
                    <Field label={t("yourNetRate")}>
                      <input
                        className={inputClass}
                        type="number"
                        step={10000}
                        value={overrideRate}
                        onChange={(e) => setOverrideRate(e.target.value)}
                      />
                    </Field>
                    <Field label={t("reason")}>
                      <select className={inputClass} value={reasonCode} onChange={(e) => setReasonCode(e.target.value)}>
                        {reasons.map((r) => (
                          <option key={r.code} value={r.code}>
                            {tv(`overrideReasons.${r.code}`)}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </div>
                  {outOfBand && (
                    <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[11px] text-amber-800">
                      This rate sits outside the validated seasonal band (
                      {formatVND(detail.band_min_net_rate)} – {formatVND(detail.band_max_net_rate)}).
                      That is allowed — the override is recorded as-is.
                    </div>
                  )}
                  <Field label={t("note")}>
                    <input
                      className={inputClass}
                      placeholder={t("notePlaceholder")}
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                    />
                  </Field>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="primary"
                      disabled={busy || !Number(overrideRate)}
                      onClick={() =>
                        act(() => api.override(detail.id, Number(overrideRate), reasonCode, note || undefined))
                      }
                    >
                      Save override
                    </Button>
                    <Button variant="ghost" onClick={() => setMode("view")}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
