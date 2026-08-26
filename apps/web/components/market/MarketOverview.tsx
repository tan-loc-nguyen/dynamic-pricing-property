"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { addDaysISO, todayISO } from "@/lib/dates";
import { useFormat } from "@/lib/useFormat";
import { Card, Spinner } from "@/components/ui";
import type { MarketObservation, Recommendation } from "@/lib/types";

const WINDOW_DAYS = 30;
/** Below this, a low/high pair is two prices, not a range worth drawing. */
const MIN_FOR_A_RANGE = 3;

/**
 * "How does my pricing compare with the market?" — asked and answered before
 * any table appears.
 *
 * The band is drawn ONLY where enough comparable observations exist for that
 * night. Where they do not, the line still runs and the band simply stops:
 * inventing a spread from one observation would be fabricating the very thing
 * the operator is here to judge (§20).
 */
export function MarketOverview() {
  const t = useTranslations("marketOverview");
  const { formatVND, formatDateTime } = useFormat();

  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [obs, setObs] = useState<MarketObservation[]>([]);
  const [loading, setLoading] = useState(true);

  const start = todayISO();
  const end = addDaysISO(start, WINDOW_DAYS - 1);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.recommendations({ start_date: start, end_date: end, limit: 5000 }),
      api.observations({}),
    ])
      .then(([r, o]) => {
        if (!alive) return;
        setRecs(r);
        setObs(o);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [start, end]);

  const { series, quality } = useMemo(() => {
    const byDate = new Map<string, { prices: number[]; rec: number[] }>();
    for (const r of recs) {
      const e = byDate.get(r.stay_date) ?? { prices: [], rec: [] };
      e.rec.push(r.recommended_net_rate);
      byDate.set(r.stay_date, e);
    }
    for (const o of obs) {
      const e = byDate.get(o.stay_date);
      if (e && o.observed_price > 0) e.prices.push(o.observed_price);
    }

    const rows = [...byDate.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, e]) => {
        const sorted = [...e.prices].sort((x, y) => x - y);
        const enough = sorted.length >= MIN_FOR_A_RANGE;
        const mine = e.rec.reduce((s, v) => s + v, 0) / Math.max(e.rec.length, 1);
        return {
          date: date.slice(5),
          mine: Math.round(mine),
          // Recharts stacks an Area from a [low, high] tuple; `undefined`
          // leaves a genuine gap rather than drawing a made-up one.
          band: enough ? [sorted[0], sorted[sorted.length - 1]] : undefined,
          median: enough ? sorted[Math.floor(sorted.length / 2)] : undefined,
        };
      });

    const withBand = rows.filter((r) => r.band).length;
    const above = rows.filter((r) => r.median && r.mine > r.median).length;
    const below = rows.filter((r) => r.median && r.mine < r.median).length;
    return {
      series: rows,
      quality: {
        nights: rows.length,
        covered: withBand,
        observations: obs.length,
        position: withBand === 0 ? null : above > below ? "above" : below > above ? "below" : "inLine",
      },
    };
  }, [recs, obs]);

  const lastUpdated = useMemo(() => {
    const stamps = obs.map((o) => o.observed_at).filter(Boolean) as string[];
    return stamps.length ? stamps.sort().slice(-1)[0] : null;
  }, [obs]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-6 text-[12.5px] text-ink-400">
        <Spinner /> {t("loading")}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Data quality in plain words, not provider classes or scores. */}
      <div className="flex flex-wrap gap-2">
        <Card className="flex-1 min-w-[140px] px-3.5 py-2.5">
          <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
            {t("position")}
          </div>
          <div
            className={`mt-0.5 text-[17px] font-semibold ${
              quality.position === "above"
                ? "text-emerald-600"
                : quality.position === "below"
                  ? "text-amber-600"
                  : "text-ink-800"
            }`}
          >
            {quality.position ? t(`positions.${quality.position}`) : t("positions.unknown")}
          </div>
        </Card>
        <Card className="flex-1 min-w-[140px] px-3.5 py-2.5">
          <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
            {t("coverage")}
          </div>
          <div className="mt-0.5 tnum text-[17px] font-semibold text-ink-900">
            {quality.covered}/{quality.nights}
          </div>
          <div className="text-[10.5px] text-ink-400">{t("coverageHint")}</div>
        </Card>
        <Card className="flex-1 min-w-[140px] px-3.5 py-2.5">
          <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
            {t("lastUpdated")}
          </div>
          <div className="mt-0.5 text-[13px] text-ink-800">
            {lastUpdated ? formatDateTime(lastUpdated) : "—"}
          </div>
        </Card>
      </div>

      <Card className="p-4">
        <h3 className="text-[12.5px] font-semibold text-ink-800">{t("chartTitle")}</h3>
        <p className="mb-3 text-[11.5px] text-ink-500">{t("chartHint")}</p>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={series} margin={{ top: 6, right: 10, bottom: 0, left: 6 }}>
              <CartesianGrid strokeDasharray="2 4" stroke="#e8e9ee" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: "#9aa0ac" }}
                tickLine={false}
                axisLine={false}
                interval={Math.max(0, Math.floor(series.length / 10))}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#9aa0ac" }}
                tickLine={false}
                axisLine={false}
                width={62}
                // Anchoring at zero squashed every line into the top third of
                // the chart: these are rates around 2-3 million, so the
                // interesting variation is a few percent, not the distance to
                // zero. Padded auto-domain keeps the differences readable.
                domain={["dataMin - 200000", "dataMax + 200000"]}
                tickFormatter={(v) => formatVND(v, { compact: true })}
              />
              <Tooltip
                contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e8e9ee" }}
                formatter={(value, name) => {
                  if (Array.isArray(value)) {
                    return [`${formatVND(value[0])} – ${formatVND(value[1])}`, t("legendBand")];
                  }
                  return [
                    formatVND(value as number),
                    name === "mine" ? t("legendMine") : t("legendMedian"),
                  ];
                }}
              />
              <Area
                dataKey="band"
                stroke="none"
                fill="#7dd3fc"
                fillOpacity={0.35}
                connectNulls={false}
                isAnimationActive={false}
              />
              <Line
                dataKey="median"
                stroke="#0284c7"
                strokeWidth={1.5}
                strokeDasharray="3 3"
                dot={false}
                connectNulls={false}
                isAnimationActive={false}
              />
              <Line
                dataKey="mine"
                stroke="#4f46e5"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-3 flex flex-wrap gap-4 text-[11px] text-ink-500">
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded bg-[#4f46e5]" aria-hidden /> {t("legendMine")}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded bg-[#0284c7]" aria-hidden /> {t("legendMedian")}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-4 rounded bg-[#7dd3fc]/60" aria-hidden /> {t("legendBand")}
          </span>
        </div>

        {quality.covered < quality.nights && (
          <p className="mt-3 rounded-md bg-ink-50 px-2.5 py-1.5 text-[11.5px] text-ink-600">
            {t("gapsExplained", { covered: quality.covered, total: quality.nights })}
          </p>
        )}
      </Card>
    </div>
  );
}
