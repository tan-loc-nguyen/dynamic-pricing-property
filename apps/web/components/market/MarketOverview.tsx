"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
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
import { RANGES, daysFor, granularityFor } from "@/lib/ranges";
import { buildColumns, bucketKeyFor } from "@/lib/buckets";
import { useFormat } from "@/lib/useFormat";
import { Card, Spinner } from "@/components/ui";
import type { FormatLocale } from "@/lib/format";
import type { MarketObservation, Recommendation } from "@/lib/types";

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
  const tc = useTranslations("calendar");
  const { formatVND, formatDateTime } = useFormat();
  const locale = useLocale() as FormatLocale;

  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [obs, setObs] = useState<MarketObservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [rangeKey, setRangeKey] = useState<string>("oneMonth");

  const days = daysFor(rangeKey);
  // Weekly buckets past a month are not only about label density: bucketing
  // seven nights of observations together clears the three-price threshold far
  // more often than any single night does, so the band actually has coverage
  // to draw. "The range of comparable prices seen this week" is a real
  // statistic, not a smoothing trick.
  const granularity = granularityFor(days);
  const start = todayISO();
  const end = addDaysISO(start, days - 1);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.recommendations({ start_date: start, end_date: end, limit: 5000 }),
      // A window and an explicit limit. Without them this received the
      // endpoint's default 200 most-recent rows — 16% of the data — and drew
      // the band and the coverage figure from that sixth.
      api.observations({ start_date: start, end_date: end, limit: 5000 }),
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
    const cols = buildColumns(start, end, granularity, locale);
    const first = cols[0]?.key;
    const key = (stayDate: string) => bucketKeyFor(stayDate, granularity, first);

    // Seed EVERY bucket in the requested window, not only the ones that have
    // recommendations. Building the list from the data made a six-month view
    // report "13/13 weeks covered" — reading as full coverage when the chart
    // actually stopped at the pricing horizon less than halfway through.
    const byDate = new Map<string, { prices: number[]; rec: number[] }>();
    for (const c of cols) {
      byDate.set(c.key, { prices: [], rec: [] });
    }
    for (const r of recs) {
      const e = byDate.get(key(r.stay_date));
      if (e) e.rec.push(r.recommended_net_rate);
    }
    for (const o of obs) {
      // LOW-confidence evidence is excluded. The product's central claim about
      // market data is that a price you cannot interpret is not evidence and
      // may never characterise a rate (D20); drawing the band from it would
      // have this panel tell the operator where they sit using exactly the
      // observations the engine refused.
      if (o.confidence === "LOW") continue;
      // Observations outside the window have no bucket and must not create one.
      const e = byDate.get(key(o.stay_date));
      if (e && o.observed_price > 0) e.prices.push(o.observed_price);
    }

    const rows = [...byDate.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, e]) => {
        const sorted = [...e.prices].sort((x, y) => x - y);
        const enough = sorted.length >= MIN_FOR_A_RANGE;
        // `undefined`, not 0: past the pricing horizon there is no rate, and a
        // zero would draw the line to the floor.
        const mine = e.rec.length
          ? Math.round(e.rec.reduce((s, v) => s + v, 0) / e.rec.length)
          : undefined;
        return {
          date: date.slice(5),
          mine,
          // Recharts stacks an Area from a [low, high] tuple; `undefined`
          // leaves a genuine gap rather than drawing a made-up one.
          band: enough ? [sorted[0], sorted[sorted.length - 1]] : undefined,
          median: enough ? sorted[Math.floor(sorted.length / 2)] : undefined,
        };
      });

    const withBand = rows.filter((r) => r.band).length;

    // Position = our rate against the QUALIFIED comp reference.
    //
    // Not `market_price_index`: that divides the comp median for a date by the
    // comp median across the window, so it compares the market to ITSELF and
    // its window mean is pinned near 1.0 by construction. Reading it as a
    // position would have this card say "in line" essentially always.
    // `market_reference_net_rate` is already gated by confidence and minimum
    // observation count, so this also uses only evidence the engine accepted.
    const ratios = recs
      .filter((r) => r.market_reference_net_rate && r.recommended_net_rate)
      .map((r) => r.recommended_net_rate / (r.market_reference_net_rate as number));
    const meanRatio = ratios.length
      ? ratios.reduce((s, v) => s + v, 0) / ratios.length
      : null;
    const position =
      meanRatio === null
        ? null
        : meanRatio > 1.02
          ? "above"
          : meanRatio < 0.98
            ? "below"
            : "inLine";

    return {
      series: rows,
      quality: {
        buckets: rows.length,
        covered: withBand,
        observations: obs.length,
        qualified: ratios.length,
        position,
      },
    };
  }, [recs, obs, granularity, start, end, locale]);

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
            {quality.covered}/{quality.buckets}
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
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-[12.5px] font-semibold text-ink-800">
              {t("chartTitle", { count: days })}
            </h3>
            <p className="text-[11.5px] text-ink-500">{t("chartHint")}</p>
          </div>
          <label className="flex shrink-0 items-center gap-1.5">
            <span className="sr-only">{t("rangeLabel")}</span>
            <select
              value={rangeKey}
              onChange={(e) => setRangeKey(e.target.value)}
              className="rounded-lg border border-ink-200 bg-white px-2 py-1 text-[12.5px] text-ink-700
                focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            >
              {RANGES.map((r) => (
                <option key={r.key} value={r.key}>
                  {tc(`ranges.${r.key}`)}
                </option>
              ))}
            </select>
          </label>
        </div>
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
                connectNulls={false}
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

        {quality.covered < quality.buckets && (
          <p className="mt-3 rounded-md bg-ink-50 px-2.5 py-1.5 text-[11.5px] text-ink-600">
            {t(granularity === "week" ? "gapsExplainedWeeks" : "gapsExplained", { covered: quality.covered, total: quality.buckets })}
          </p>
        )}
      </Card>
    </div>
  );
}
