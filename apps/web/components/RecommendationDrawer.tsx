"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  formatFactor,
  formatLongDate,
  formatOccupancy,
  formatPct,
  formatSignedVND,
  formatVND,
  marketLabel,
  paceLabel,
} from "@/lib/format";
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
      <div className={`text-[15px] font-semibold mt-0.5 tnum ${muted ? "text-ink-300" : "text-ink-900"}`}>
        {value}
      </div>
      {hint && <div className="text-[10px] text-ink-400 mt-0.5 leading-tight">{hint}</div>}
    </div>
  );
}

/** The price breakdown: base -> each factor -> final. */
function Breakdown({ detail }: { detail: RecommendationDetail }) {
  return (
    <div className="rounded-xl border border-ink-200 overflow-hidden">
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-ink-50 border-b border-ink-200">
        <span className="text-[12px] font-semibold text-ink-700">Base price</span>
        <span className="tnum text-[13px] font-semibold text-ink-900">{formatVND(detail.base_price)}</span>
      </div>

      <div className="divide-y divide-ink-100">
        {detail.adjustments.map((adj) => {
          const up = adj.delta > 0.5;
          const down = adj.delta < -0.5;
          const isBound = adj.code === "min_price_floor" || adj.code === "max_price_cap";
          const isGuard = adj.code === "compounding_guardrail";
          return (
            <div key={adj.sequence} className="px-3.5 py-2.5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className={`text-[12.5px] font-medium ${
                        adj.is_neutral ? "text-ink-400" : "text-ink-900"
                      }`}
                    >
                      {adj.label}
                    </span>
                    {isBound && <Chip tone="warn">Constraint</Chip>}
                    {isGuard && <Chip tone="warn">Guardrail</Chip>}
                    {adj.is_neutral && <Chip tone="neutral">No effect</Chip>}
                  </div>
                  {adj.reason && (
                    <div className="text-[11px] text-ink-500 mt-1 leading-snug">{adj.reason}</div>
                  )}
                </div>
                <div className="text-right shrink-0">
                  <div
                    className={`tnum text-[12px] font-semibold ${
                      adj.is_neutral ? "text-ink-300" : "text-ink-600"
                    }`}
                  >
                    {formatFactor(adj.factor)}
                  </div>
                  <div
                    className={`tnum text-[12px] font-medium ${
                      up ? "text-emerald-600" : down ? "text-rose-600" : "text-ink-300"
                    }`}
                  >
                    {adj.is_neutral ? "—" : formatSignedVND(adj.delta)}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between px-3.5 py-3 bg-brand-50 border-t border-brand-200">
        <span className="text-[12px] font-semibold text-brand-700">Final recommendation</span>
        <span className="tnum text-[16px] font-bold text-brand-700">
          {formatVND(detail.recommended_price)}
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
  const [overridePrice, setOverridePrice] = useState("");
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
        setOverridePrice(String(Math.round(d.recommended_price)));
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
                      {detail.room_name}
                    </h2>
                    <StatusBadge status={detail.status} />
                  </div>
                  <div className="text-[12px] text-ink-500 mt-1">
                    {detail.property_name} · {formatLongDate(detail.stay_date)}
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
              {/* headline price comparison */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-xl border border-ink-200 px-3.5 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-ink-400 font-medium">Current</div>
                  <div className="text-[17px] font-semibold text-ink-700 tnum mt-1">
                    {formatVND(detail.current_price)}
                  </div>
                </div>
                <div className="rounded-xl border-2 border-brand-300 bg-brand-50 px-3.5 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-brand-500 font-medium">
                    Recommended
                  </div>
                  <div className="text-[17px] font-bold text-brand-700 tnum mt-1">
                    {formatVND(detail.recommended_price)}
                  </div>
                </div>
                <div className="rounded-xl border border-ink-200 px-3.5 py-3">
                  <div className="text-[10px] uppercase tracking-wide text-ink-400 font-medium">Difference</div>
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

              {/* the signals that drove it */}
              <div>
                <div className="text-[12px] font-semibold text-ink-700 mb-2">Signals</div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <SignalTile
                    label="Occupancy"
                    value={formatOccupancy(detail.occupancy)}
                    hint={
                      detail.units_sold !== null ? `${detail.units_sold}/${detail.units_total} units sold` : undefined
                    }
                    muted={detail.occupancy === null}
                  />
                  <SignalTile
                    label="Days to check-in"
                    value={detail.days_to_checkin !== null ? `D-${detail.days_to_checkin}` : "—"}
                    muted={detail.days_to_checkin === null}
                  />
                  <SignalTile
                    label="Booking pace"
                    value={paceLabel(detail.booking_pace_index)}
                    hint={
                      detail.booking_pace_index !== null
                        ? `index ${detail.booking_pace_index.toFixed(2)}`
                        : "no bookings data"
                    }
                    muted={detail.booking_pace_index === null}
                  />
                  <SignalTile
                    label="Market"
                    value={marketLabel(detail.market_price_index)}
                    hint={
                      detail.market_reference_price
                        ? `${formatVND(detail.market_reference_price, { compact: true })} · ${detail.market_observation_count} obs`
                        : "no observations"
                    }
                    muted={detail.market_price_index === null}
                  />
                </div>
                {detail.missing_signals.length > 0 && (
                  <div className="mt-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[11px] text-amber-800">
                    <span className="font-semibold">Blind spots:</span>{" "}
                    {detail.missing_signals.join(", ")} — a neutral factor (×1.00) was applied for these.
                  </div>
                )}
              </div>

              {/* full calculation */}
              <div>
                <div className="text-[12px] font-semibold text-ink-700 mb-2">How this price was calculated</div>
                <Breakdown detail={detail} />
                <p className="text-[11.5px] text-ink-500 mt-2.5 leading-relaxed">{detail.explanation}</p>
                <div className="text-[10.5px] text-ink-400 mt-2">
                  Engine {detail.engine_version} · pricing rules v{detail.config_version} ·
                  <span className="text-amber-600 font-medium"> assumptions UNVALIDATED</span>
                </div>
              </div>

              {/* decision history for this stay date */}
              {detail.decisions.length > 0 && (
                <div>
                  <div className="text-[12px] font-semibold text-ink-700 mb-2">Decisions on this date</div>
                  <div className="space-y-1.5">
                    {detail.decisions.map((d) => (
                      <div key={d.id} className="rounded-lg border border-ink-200 px-3 py-2 text-[11.5px]">
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-ink-800 capitalize">{d.decision}</span>
                          <span className="tnum text-ink-600">{formatVND(d.final_price)}</span>
                        </div>
                        {d.reason_label && (
                          <div className="text-ink-500 mt-0.5">Reason: {d.reason_label}</div>
                        )}
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

            {/* action bar */}
            <div className="sticky bottom-0 bg-white border-t border-ink-200 px-5 py-3.5">
              {mode === "view" ? (
                <div className="flex items-center gap-2">
                  <Button
                    variant="primary"
                    disabled={busy}
                    onClick={() => act(() => api.accept(detail.id, note || undefined))}
                  >
                    Accept {formatVND(detail.recommended_price)}
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
                    <Field label="Your price (VND)">
                      <input
                        className={inputClass}
                        type="number"
                        step={10000}
                        value={overridePrice}
                        onChange={(e) => setOverridePrice(e.target.value)}
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
                      disabled={busy || !Number(overridePrice)}
                      onClick={() =>
                        act(() => api.override(detail.id, Number(overridePrice), reasonCode, note || undefined))
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
