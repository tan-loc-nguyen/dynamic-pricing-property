"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { useFormat } from "@/lib/useFormat";
import { Card, Chip, Empty, Spinner } from "@/components/ui";
import type { Competitor, MarketObservation } from "@/lib/types";

/**
 * The comp set as a short list of properties, not a table of observation rows.
 *
 * An owner picks who they compete with and wants to know what those places are
 * charging and whether the number can be trusted. The per-observation detail
 * (tax basis, LOS, refundability) stays in Data details, where someone
 * verifying the pipeline can find it.
 */
export function CompetitorList() {
  const t = useTranslations("compSet");
  const tv = useTranslations("vocab");
  const { formatVND, formatDateTime } = useFormat();

  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [obs, setObs] = useState<MarketObservation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    Promise.all([api.competitors(), api.observations({})])
      .then(([c, o]) => {
        if (!alive) return;
        setCompetitors(c);
        setObs(o);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const summary = useMemo(() => {
    const m = new Map<
      number,
      { prices: number[]; last: string | null; confidences: Record<string, number> }
    >();
    for (const o of obs) {
      if (o.competitor_id === null) continue;
      const e = m.get(o.competitor_id) ?? { prices: [], last: null, confidences: {} };
      if (o.observed_price > 0) e.prices.push(o.observed_price);
      if (o.observed_at && (!e.last || o.observed_at > e.last)) e.last = o.observed_at;
      e.confidences[o.confidence] = (e.confidences[o.confidence] ?? 0) + 1;
      m.set(o.competitor_id, e);
    }
    return m;
  }, [obs]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-6 text-[12.5px] text-ink-400">
        <Spinner /> {t("loading")}
      </div>
    );
  }
  if (!competitors.length) {
    return <Empty title={t("empty")} hint={t("emptyHint")} />;
  }

  return (
    <div className="space-y-2">
      {competitors.map((c) => {
        const s = summary.get(c.id);
        const prices = (s?.prices ?? []).sort((a, b) => a - b);
        const best =
          Object.entries(s?.confidences ?? {}).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
        return (
          <Card key={c.id} className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
            <div className="min-w-[180px] flex-1">
              <div className="text-[13px] font-medium text-ink-900">{c.name}</div>
              <div className="text-[11px] text-ink-400">
                {c.location || "—"}
                {c.comparable_category ? ` · ${tv(`roomCategories.${c.comparable_category}`)}` : ""}
              </div>
            </div>

            <div className="min-w-[150px]">
              <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
                {t("observedRange")}
              </div>
              <div className="tnum text-[12.5px] text-ink-800">
                {prices.length
                  ? `${formatVND(prices[0], { compact: true })} – ${formatVND(prices[prices.length - 1], { compact: true })}`
                  : "—"}
              </div>
            </div>

            <div className="min-w-[110px]">
              <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
                {t("confidence")}
              </div>
              {best ? (
                <Chip tone={best === "HIGH" ? "up" : best === "MEDIUM" ? "info" : "warn"}>
                  {tv(`confidence.${best}`)}
                </Chip>
              ) : (
                <span className="text-[12px] text-ink-400">—</span>
              )}
            </div>

            <div className="min-w-[130px]">
              <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
                {t("lastSeen")}
              </div>
              <div className="text-[12px] text-ink-600">
                {s?.last ? formatDateTime(s.last) : "—"}
              </div>
            </div>

            <div className="tnum text-[11.5px] text-ink-400">
              {t("observationCount", { count: prices.length })}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
