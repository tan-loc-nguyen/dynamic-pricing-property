"use client";

import * as Tabs from "@radix-ui/react-tabs";
import { useTranslations } from "next-intl";
import { MarketOverview } from "@/components/market/MarketOverview";
import { CompetitorList } from "@/components/market/CompetitorList";
import { EventsPanel } from "@/components/market/EventsPanel";
import { RawObservations } from "@/components/market/RawObservations";

const TABS = ["overview", "competitors", "events", "data"] as const;

/**
 * Market and events, in one place, insight first.
 *
 * The previous Market page opened on a table of raw observations — price
 * basis, tax inclusion, refundability — which is the collector's data model
 * rather than an answer. That table still exists, one tab away, because it is
 * genuinely useful for verifying the pipeline. It is just no longer the first
 * thing an owner meets.
 */
export default function MarketPage() {
  const t = useTranslations("marketPage");

  return (
    <div className="flex h-full flex-col gap-3">
      <div>
        <h1 className="text-[19px] font-semibold text-ink-900">{t("title")}</h1>
        <p className="text-[12px] text-ink-500">{t("subtitle")}</p>
      </div>

      <Tabs.Root defaultValue="overview" className="flex min-h-0 flex-1 flex-col">
        <Tabs.List
          className="flex shrink-0 gap-1 border-b border-ink-200"
          aria-label={t("title")}
        >
          {TABS.map((key) => (
            <Tabs.Trigger
              key={key}
              value={key}
              className="-mb-px border-b-2 border-transparent px-3 py-2 text-[12.5px] text-ink-500
                hover:text-ink-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500
                data-[state=active]:border-brand-600 data-[state=active]:font-medium
                data-[state=active]:text-brand-700"
            >
              {t(`tabs.${key}`)}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        {TABS.map((key) => (
          <Tabs.Content
            key={key}
            value={key}
            className="min-h-0 flex-1 overflow-y-auto pt-4 focus:outline-none"
          >
            {key === "overview" && <MarketOverview />}
            {key === "competitors" && <CompetitorList />}
            {key === "events" && <EventsPanel />}
            {key === "data" && <RawObservations />}
          </Tabs.Content>
        ))}
      </Tabs.Root>
    </div>
  );
}
