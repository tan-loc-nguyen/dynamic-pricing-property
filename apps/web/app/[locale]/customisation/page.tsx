"use client";

import * as Tabs from "@radix-ui/react-tabs";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { SeasonalPanel } from "@/components/customisation/SeasonalPanel";
import { StrategyPanel } from "@/components/customisation/StrategyPanel";
import { EventsPanel } from "@/components/market/EventsPanel";
import { PageHeader } from "@/components/PageHeader";

const TABS = ["seasonal", "strategy", "events"] as const;
type Tab = (typeof TABS)[number];

/**
 * The three things an operator actually tunes.
 *
 * Seasonal bands are CLIENT-VALIDATED business fact; strategy and events are
 * the experimental layer on top. They sit together because they are all
 * "change how prices are worked out", and apart from Settings because Settings
 * is plumbing — which data source, which room type maps to which tier.
 */
export default function CustomisationPage() {
  const t = useTranslations("customisation");
  const [tab, setTab] = useState<Tab>("seasonal");

  return (
    <div className="flex h-full flex-col gap-3 px-7 py-6">
      <PageHeader title={t("title")} subtitle={t("subtitle")} />

      <Tabs.Root
        value={tab}
        onValueChange={(v) => setTab(v as Tab)}
        className="flex min-h-0 flex-1 flex-col"
      >
        <Tabs.List className="flex shrink-0 gap-1 border-b border-ink-200" aria-label={t("title")}>
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
            {key === "seasonal" && <SeasonalPanel />}
            {key === "strategy" && <StrategyPanel onOpenSeasonal={() => setTab("seasonal")} />}
            {key === "events" && <EventsPanel />}
          </Tabs.Content>
        ))}
      </Tabs.Root>
    </div>
  );
}
