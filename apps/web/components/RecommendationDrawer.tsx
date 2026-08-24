"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  confidenceTone,
  formatAdjPct,
  formatLongDate,
  formatOccupancy,
  formatPaceGap,
  formatPct,
  formatSignedVND,
  formatVND,
  marketLabel,
  paceLabel,
  paceTone,
  pickupLabel,
} from "@/lib/format";
import type { RecommendationDetail, SystemStatus } from "@/lib/types";
import { Button, Chip, Field, StatusBadge, inputClass } from "./ui";

function SignalTile({
  label,
  value,
  hint,
  muted,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  muted?: boolean;
  tone?: string;
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
  const lo = detail.band_min_net_rate;
  const hi = detail.band_max_net_rate;
  const base = detail.band_base_net_rate;
  if (lo === null || hi === null || base === null || hi <= lo) return null;

  const pos = (v: number) => Math.min(100, Math.max(0, ((v - lo) / (hi - lo)) * 100));

  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 px-3.5 py-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[11.5px] font-semibold text-emerald-900">
          {detail.season_label}
          <span className="font-normal text-emerald-700"> · {detail.room_category_label}</span>
        </div>
        <Chip tone="up">Client-validated</Chip>
      </div>

      <div className="relative h-8 mt-3 mb-1">
        <div className="absolute top-3.5 left-0 right-0 h-1.5 rounded-full bg-emerald-200" />
        <div
          className="absolute top-2.5 h-3.5 w-0.5 bg-emerald-500"
          style={{ left: `${pos(base)}%` }}
          title={`BASE ${base.toLocaleString()}`}
        />
        <div
          className="absolute top-1.5 -translate-x-1/2 h-5 w-5 rounded-full border-2 border-white bg-brand-600 shadow"
          style={{ left: `${pos(detail.recommended_net_rate)}%` }}
          title={`Recommended ${detail.recommended_net_rate.toLocaleString()}`}
        />
      </div>

      <div className="flex justify-between text-[10.5px] tnum text-emerald-800">
        <span>MIN {formatVND(lo)}</span>
        <span className="text-emerald-600">BASE {formatVND(base)}</span>
        <span>MAX {formatVND(hi)}</span>
      </div>
      <div className="text-[10.5px] text-emerald-700 mt-1.5">
        NET rates supplied by Luminous. Season selects this band — no seasonality multiplier is applied on top.
      </div>
    </div>
  );
}

/** The calculation: validated band -> dynamic layer -> clamp -> rounding. */
function Breakdown({ detail }: { detail: RecommendationDetail }) {
  return (
    <div className="rounded-xl border border-ink-200 overflow-hidden">
      <div className="divide-y divide-ink-100">
        {detail.adjustments.map((adj) => {
          const up = adj.delta > 0.5;
          const down = adj.delta < -0.5;
          const isBand = adj.code === "rate_band";
          const isClamp = adj.code === "band_min_clamp" || adj.code === "band_max_clamp";
          const isBound = adj.code === "dynamic_bound";

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
                      {adj.label}
                    </span>
                    {isBand && <Chip tone="up">Validated</Chip>}
                    {isClamp && <Chip tone="warn">Band limit</Chip>}
                    {isBound && <Chip tone="warn">Bounded</Chip>}
                    {adj.is_ignored && <Chip tone="warn">Ignored</Chip>}
                    {adj.is_neutral && !adj.is_ignored && !isBand && <Chip tone="neutral">No effect</Chip>}
                  </div>
                  {adj.reason && (
                    <div className="text-[11px] text-ink-500 mt-1 leading-snug">{adj.reason}</div>
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
        <span className="text-[12px] font-semibold text-brand-700">Recommended NET rate</span>
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
      setError(e.message || "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const reasons = status?.override_reasons || [{ code: "my_judgment", label: "My judgment" }];
  const outOfBand =
    detail && detail.band_min_net_rate !== null && detail.band_max_net_rate !== null
      ? Number(overrideRate) < detail.band_min_net_rate ||
        Number(overrideRate) > detail.band_max_net_rate
      : false;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink-950/25" onClick={onClose} />
      <div className="relative w-full max-w-xl bg-white shadow-2xl overflow-y-auto animate-slide-in">
        {loading && <div className="p-6 text-[13px] text-ink-400">Loading recommendation…</div>}

        {detail && (
          <>
            <div className="sticky top-0 bg-white border-b border-ink-200 px-5 py-4 z-10">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h2 className="text-[16px] font-semibold text-ink-900 leading-tight">
                      {detail.room_category_label}
                    </h2>
                    <StatusBadge status={detail.status} />
                    <Chip tone="up">Shadow</Chip>
                  </div>
                  <div className="text-[12px] text-ink-500 mt-1">
                    {formatLongDate(detail.stay_date)}
                    {detail.is_event && detail.event_name && (
                      <span className="text-amber-600 font-medium"> · {detail.event_name}</span>
                    )}
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={onClose}>
                  Close
                </Button>
              </div>
            </div>

            <div className="p-5 space-y-5">
              {/* headline */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-xl border border-ink-200 px-3.5 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-ink-400 font-medium">Current NET</div>
                  <div className="text-[17px] font-semibold text-ink-700 tnum mt-1">
                    {formatVND(detail.current_net_rate)}
                  </div>
                </div>
                <div className="rounded-xl border-2 border-brand-300 bg-brand-50 px-3.5 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-brand-500 font-medium">
                    Recommended NET
                  </div>
                  <div className="text-[17px] font-bold text-brand-700 tnum mt-1">
                    {formatVND(detail.recommended_net_rate)}
                  </div>
                </div>
                <div className="rounded-xl border border-ink-200 px-3.5 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-ink-400 font-medium">Change</div>
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
                These are <span className="font-semibold">NET rates</span> — what Luminous receives.
                They are not guest-facing OTA prices.
                {detail.current_ota_price !== null && (
                  <> Current OTA price on file: {formatVND(detail.current_ota_price)}.</>
                )}
              </div>

              {/* 1-2. which band, and why the base is what it is */}
              <RateBandStrip detail={detail} />

              {/* 3-6. the demand signals */}
              <div>
                <div className="text-[12px] font-semibold text-ink-700 mb-2">Demand signals</div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <SignalTile
                    label="On the books"
                    value={formatOccupancy(detail.occupancy)}
                    hint={
                      detail.units_sold !== null
                        ? `${detail.units_sold}/${detail.units_total} units · ${detail.units_available} left`
                        : undefined
                    }
                    muted={detail.occupancy === null}
                  />
                  <SignalTile
                    label="Days to arrival"
                    value={detail.days_to_arrival !== null ? `D-${detail.days_to_arrival}` : "—"}
                    hint={
                      detail.expected_occupancy !== null
                        ? `curve expects ${formatOccupancy(detail.expected_occupancy)}`
                        : "no curve"
                    }
                    muted={detail.days_to_arrival === null}
                  />
                  <SignalTile
                    label="Pace position"
                    value={paceLabel(detail.pace_gap)}
                    hint={detail.pace_gap !== null ? formatPaceGap(detail.pace_gap) : "no data"}
                    muted={detail.pace_gap === null}
                  />
                  <SignalTile
                    label="Recent pickup"
                    value={pickupLabel(detail.pickup_delta)}
                    hint={
                      detail.recent_pickup !== null
                        ? `${detail.recent_pickup} booking(s) in window`
                        : "no booking data"
                    }
                    muted={detail.pickup_delta === null}
                  />
                </div>

                <div className="mt-2 flex flex-wrap gap-2">
                  {detail.market_qualified_count > 0 ? (
                    <Chip tone={confidenceTone(detail.market_confidence)}>
                      Market {marketLabel(detail.market_price_index)} ·{" "}
                      {detail.market_qualified_count} × {detail.market_confidence}
                    </Chip>
                  ) : detail.market_ignored_count > 0 ? (
                    <Chip tone="warn">
                      {detail.market_ignored_count} market observation(s) ignored — low confidence
                    </Chip>
                  ) : (
                    <Chip tone="neutral">No market evidence</Chip>
                  )}
                  {detail.is_event && (
                    <Chip tone="warn">
                      Event: {detail.event_name} ({detail.event_impact_level} impact)
                    </Chip>
                  )}
                </div>

                {detail.missing_signals.length > 0 && (
                  <div className="mt-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[11px] text-amber-800">
                    <span className="font-semibold">Blind spots:</span>{" "}
                    {detail.missing_signals.join(", ")} — no adjustment was applied for these.
                  </div>
                )}
              </div>

              {/* 3-9. the full calculation */}
              <div>
                <div className="text-[12px] font-semibold text-ink-700 mb-2">
                  How this rate was calculated
                </div>
                <Breakdown detail={detail} />
                <p className="text-[11.5px] text-ink-500 mt-2.5 leading-relaxed">{detail.explanation}</p>
                <div className="text-[10.5px] text-ink-400 mt-2">
                  Engine {detail.engine_version} · dynamic rules v{detail.config_version} · rate band{" "}
                  <span className="text-emerald-600 font-medium">CLIENT-VALIDATED</span> · dynamic layer{" "}
                  <span className="text-amber-600 font-medium">UNVALIDATED</span>
                </div>
              </div>

              {/* outcomes */}
              {detail.outcomes.length > 0 && (
                <div>
                  <div className="text-[12px] font-semibold text-ink-700 mb-2">Outcome</div>
                  {detail.outcomes.map((o) => (
                    <div
                      key={o.id}
                      className="rounded-lg border border-ink-200 px-3 py-2 text-[11.5px] flex items-center justify-between"
                    >
                      <span className="text-ink-600">
                        {o.units_booked} booked · realised {formatVND(o.realized_net_rate)}
                      </span>
                      {o.is_synthetic && <Chip tone="warn">Synthetic</Chip>}
                    </div>
                  ))}
                </div>
              )}

              {/* decisions */}
              {detail.decisions.length > 0 && (
                <div>
                  <div className="text-[12px] font-semibold text-ink-700 mb-2">Decisions on this date</div>
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
                    Accept {formatVND(detail.recommended_net_rate)}
                  </Button>
                  <Button disabled={busy} onClick={() => setMode("override")}>
                    Override…
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
                    <Field label="Your NET rate (VND)">
                      <input
                        className={inputClass}
                        type="number"
                        step={10000}
                        value={overrideRate}
                        onChange={(e) => setOverrideRate(e.target.value)}
                      />
                    </Field>
                    <Field label="Reason">
                      <select className={inputClass} value={reasonCode} onChange={(e) => setReasonCode(e.target.value)}>
                        {reasons.map((r) => (
                          <option key={r.code} value={r.code}>
                            {r.label}
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
                  <Field label="Note (optional)">
                    <input
                      className={inputClass}
                      placeholder="What does the system not know?"
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
