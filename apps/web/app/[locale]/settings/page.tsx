"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/PageHeader";

/**
 * Plumbing, and the only place an owner has to be deliberate to reach.
 *
 * The pricing inputs an operator tunes -- seasonal bands, strategy, events --
 * moved to Customisation. What is left here is setup: which data source, which
 * competitors the market report watches, and what has been decided so far.
 * Each entry says what it is FOR, not what it contains.
 */
const SECTIONS = [
  { href: "/settings/data", key: "data", validated: false },
  { href: "/settings/market-sources", key: "marketSources", validated: false },
  { href: "/settings/activity", key: "activity", validated: false },
] as const;

export default function SettingsPage() {
  const t = useTranslations("settingsHub");
  const locale = useLocale();

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl">
        <PageHeader title={t("title")} subtitle={t("subtitle")} />

        <div className="mt-4 space-y-2">
          {SECTIONS.map((s) => (
            <Link
              key={s.href}
              href={`/${locale}${s.href}`}
              className="block rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              <Card className="px-4 py-3 transition-colors hover:bg-ink-50">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[13.5px] font-medium text-ink-900">
                      {t(`${s.key}.title`)}
                    </div>
                    <div className="mt-0.5 text-[11.5px] text-ink-500">
                      {t(`${s.key}.hint`)}
                    </div>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10.5px] font-medium ${
                      s.validated
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-amber-50 text-amber-700"
                    }`}
                  >
                    {t(s.validated ? "validated" : "experimental")}
                  </span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
