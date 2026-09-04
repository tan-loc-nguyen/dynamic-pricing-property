"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { MarketOverview } from "@/components/market/MarketOverview";
import { PageHeader } from "@/components/PageHeader";
import { api } from "@/lib/api";
import { useFormat } from "@/lib/useFormat";
import type { CollectorReport } from "@/lib/types";

/**
 * One question, one answer: how do my prices compare to the market?
 *
 * The page used to carry four tabs -- overview, comp set, events, raw
 * observations. Events moved to Customisation, where the other pricing inputs
 * live, and the comp set moved to Settings because market evidence informs
 * this chart but never moves a price, which makes it plumbing rather than
 * strategy.
 */
export default function MarketPage() {
  const t = useTranslations("marketPage");
  const { formatDateTime } = useFormat();
  const [collector, setCollector] = useState<CollectorReport | null>(null);

  useEffect(() => {
    api
      .marketCollector()
      .then(setCollector)
      .catch(() => setCollector(null));
  }, []);

  return (
    <div className="flex h-full flex-col gap-3 px-7 py-6">
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <MarketOverview />

        {/* A collector that stopped extracting prices and a market with
            nothing to say both leave the band thin. This is the only thing on
            the page that can tell them apart. */}
        {collector && (
          <p className="mt-3 text-[11px] text-ink-400">
            {!collector.has_run
              ? t("collectorNeverRun")
              : t("collectorSummary", {
                  when: collector.ran_at ? formatDateTime(collector.ran_at) : "—",
                  attempted: collector.attempted,
                  found: collector.prices_found,
                })}
            {collector.truncated_nights > 0 &&
              ` ${t("collectorTruncated", { nights: collector.truncated_nights })}`}
          </p>
        )}
      </div>
    </div>
  );
}
