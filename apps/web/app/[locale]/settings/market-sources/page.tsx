"use client";

import { useTranslations } from "next-intl";
import { PageHeader } from "@/components/PageHeader";
import { CompetitorList } from "@/components/market/CompetitorList";

/**
 * Which properties the market report watches.
 *
 * Setup rather than strategy: market evidence is shown on the Market page but
 * never moves a price -- everything the collector can reach is LOW confidence
 * and the engine's gate is MEDIUM -- so configuring it belongs with the other
 * plumbing rather than with the pricing inputs in Customisation.
 */
export default function MarketSourcesPage() {
  const t = useTranslations("settingsHub");

  return (
    <div className="h-full overflow-y-auto px-7 py-6 max-w-[1500px]">
      <PageHeader title={t("marketSources.title")} subtitle={t("marketSources.hint")} />
      <CompetitorList />
    </div>
  );
}
