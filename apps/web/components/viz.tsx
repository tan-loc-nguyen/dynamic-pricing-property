"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useFormat } from "@/lib/useFormat";
import type { Adjustment, Recommendation } from "@/lib/types";

/* ------------------------------------------------------------------ band */

/**
 * Where the recommendation sits between the validated MIN and MAX.
 *
 * Three disconnected numbers do not tell an owner whether a price is near the
 * ceiling. A position on a line does. Custom SVG rather than a chart: this is
 * a number line, and reaching for a plotting library would cost more than it
 * explains.
 */
export function RateBand({
  min,
  base,
  max,
  recommended,
  clamped,
}: {
  min: number | null;
  base: number | null;
  max: number | null;
  recommended: number;
  clamped: "min" | "max" | null;
}) {
  const t = useTranslations("drawer");
  const { formatVND } = useFormat();
  if (min === null || max === null || max <= min) return null;

  const pos = (v: number) => Math.min(100, Math.max(0, ((v - min) / (max - min)) * 100));

  return (
    <div>
      <div className="relative h-9">
        <div className="absolute top-4 left-0 right-0 h-1.5 rounded-full bg-ink-150" />
        {base !== null && (
          <div
            className="absolute top-3 h-3.5 w-px bg-ink-300"
            style={{ left: `${pos(base)}%` }}
            aria-hidden
          />
        )}
        <div
          className={`absolute top-2.5 -translate-x-1/2 h-4 w-4 rounded-full border-2 border-white shadow
            ${clamped ? "bg-amber-500" : "bg-brand-600"}`}
          style={{ left: `${pos(recommended)}%` }}
          aria-hidden
        />
      </div>
      <div className="flex justify-between text-[10.5px] text-ink-400">
        <span>{t("band.min")} {formatVND(min, { compact: true })}</span>
        {base !== null && <span>{t("band.base")} {formatVND(base, { compact: true })}</span>}
        <span>{t("band.max")} {formatVND(max, { compact: true })}</span>
      </div>
      {clamped && (
        <div className="mt-2 rounded-md bg-amber-50 border border-amber-200 px-2.5 py-1.5 text-[11.5px] text-amber-800">
          {t(clamped === "min" ? "bandHitMin" : "bandHitMax")}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ pace */

/**
 * Actual on-the-books occupancy against what the curve expects, by lead time.
 *
 * The curve is not fetched from anywhere — it IS `expected_occupancy` as a
 * function of `days_to_arrival`, which every recommendation already carries.
 * Plotting the room type's own rows recovers the shape honestly; nothing is
 * modelled here that the engine did not already compute.
 */
export function PaceChart({
  peers,
  current,
}: {
  peers: Recommendation[];
  current: Recommendation;
}) {
  const t = useTranslations("drawer");

  const data = useMemo(() => {
    const byDta = new Map<number, { dta: number; expected: number; actual: number }>();
    for (const r of peers) {
      if (r.days_to_arrival === null || r.expected_occupancy === null) continue;
      byDta.set(r.days_to_arrival, {
        dta: r.days_to_arrival,
        expected: Math.round((r.expected_occupancy ?? 0) * 100),
        actual: Math.round((r.occupancy ?? 0) * 100),
      });
    }
    // Lead time runs right-to-left: far out on the left, arrival on the right.
    return [...byDta.values()].sort((a, b) => b.dta - a.dta);
  }, [peers]);

  if (data.length < 3 || current.days_to_arrival === null) {
    return <div className="text-[11.5px] text-ink-400">{t("paceNoCurve")}</div>;
  }

  const here = data.find((d) => d.dta === current.days_to_arrival);

  return (
    <>
      {/* Each point is a DIFFERENT night at its own lead time, not this night
          filling up over time. That is the right comparison against a booking
          curve, and it is also exactly what an operator would misread in a
          drawer about one specific date — so the caption says which. */}
      <p className="mb-1 text-[10.5px] text-ink-400">{t("paceCrossSection")}</p>
      <div className="h-32 -ml-2">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#e8e9ee" vertical={false} />
          <XAxis
            dataKey="dta"
            reversed
            tick={{ fontSize: 10, fill: "#9aa0ac" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => `D-${v}`}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "#9aa0ac" }}
            tickLine={false}
            axisLine={false}
            // 30 was too narrow and clipped "100%" down to "00%".
            width={34}
            domain={[0, 100]}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e8e9ee" }}
            labelFormatter={(v) => `D-${v}`}
            formatter={(value, name) => [
              `${value}%`,
              name === "expected" ? t("paceExpected") : t("paceActual"),
            ]}
          />
          <Line
            type="monotone"
            dataKey="expected"
            stroke="#9aa0ac"
            strokeWidth={1.5}
            strokeDasharray="3 3"
            dot={false}
          />
          <Line type="monotone" dataKey="actual" stroke="#4f46e5" strokeWidth={2} dot={false} />
          {here && (
            <ReferenceDot
              x={here.dta}
              y={here.actual}
              r={4}
              fill="#4f46e5"
              stroke="#fff"
              strokeWidth={2}
            />
          )}
        </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

/* ---------------------------------------------------------- contribution */

/**
 * What moved the price, as widths rather than a column of signed numbers.
 *
 * The engine is additive on the BASE rate, so each step's `delta` in dong is
 * the real contribution — this is a faithful rendering of the arithmetic, not
 * a reconstruction of it. Steps that changed nothing are still listed, because
 * "measured, no effect" and "not measured" are different answers.
 */
export function PriceContribution({
  adjustments,
  render,
}: {
  adjustments: Adjustment[];
  render: (a: Adjustment) => { label: string; reason: string };
}) {
  const { formatSignedVND } = useFormat();
  const widest = Math.max(...adjustments.map((a) => Math.abs(a.delta)), 1);

  return (
    <ul className="space-y-1.5">
      {adjustments.map((a, i) => {
        const { label } = render(a);
        const pct = (Math.abs(a.delta) / widest) * 100;
        const up = a.delta > 0;
        const flat = Math.abs(a.delta) < 1;
        return (
          <li key={i} className="grid grid-cols-[1fr_64px_88px] items-center gap-2">
            <span className={`truncate text-[11.5px] ${a.is_ignored ? "text-ink-400" : "text-ink-700"}`}>
              {label}
            </span>
            {/* Centre line: gains grow right, reductions grow left. */}
            <div className="relative h-2.5" aria-hidden>
              <div className="absolute left-1/2 top-0 h-full w-px bg-ink-200" />
              {!flat && (
                <div
                  className={`absolute top-0.5 h-1.5 rounded-sm ${up ? "bg-emerald-400" : "bg-amber-400"}`}
                  style={
                    up
                      ? { left: "50%", width: `${pct / 2}%` }
                      : { right: "50%", width: `${pct / 2}%` }
                  }
                />
              )}
            </div>
            <span
              className={`tnum text-right text-[11.5px] ${
                flat ? "text-ink-300" : up ? "text-emerald-700" : "text-amber-700"
              }`}
            >
              {flat ? "—" : formatSignedVND(a.delta)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/* ---------------------------------------------------------------- market */

/**
 * Where the recommendation sits against comparable observations.
 *
 * Renders only when there is a real range to render. With one observation
 * there is no range, and drawing a band around a single point would invent a
 * spread the data does not support.
 */
export function MarketRange({
  low,
  high,
  reference,
  recommended,
  applied,
}: {
  low: number | null;
  high: number | null;
  reference: number | null;
  recommended: number;
  applied: boolean;
}) {
  const t = useTranslations("drawer");
  const { formatVND } = useFormat();
  if (low === null || high === null || high <= low) return null;

  const span = high - low;
  const pad = span * 0.15;
  const lo = Math.min(low - pad, recommended);
  const hi = Math.max(high + pad, recommended);
  const pos = (v: number) => Math.min(100, Math.max(0, ((v - lo) / (hi - lo)) * 100));

  return (
    <div>
      <div className="relative h-8">
        <div
          className="absolute top-3.5 h-2 rounded-full bg-sky-200"
          style={{ left: `${pos(low)}%`, width: `${pos(high) - pos(low)}%` }}
        />
        {reference !== null && (
          <div
            className="absolute top-3 h-3 w-px bg-sky-500"
            style={{ left: `${pos(reference)}%` }}
            aria-hidden
          />
        )}
        <div
          className={`absolute top-2 -translate-x-1/2 h-4 w-4 rounded-full border-2 border-white shadow
            ${applied ? "bg-brand-600" : "bg-ink-400"}`}
          style={{ left: `${pos(recommended)}%` }}
          aria-hidden
        />
      </div>
      <div className="flex justify-between text-[10.5px] text-ink-400">
        <span>{formatVND(low, { compact: true })}</span>
        <span className="text-brand-700 font-medium">{t("marketYou")}</span>
        <span>{formatVND(high, { compact: true })}</span>
      </div>
    </div>
  );
}
