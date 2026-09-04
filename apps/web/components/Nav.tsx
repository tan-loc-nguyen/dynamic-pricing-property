"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Tag, Compass, SlidersHorizontal, Settings as SettingsIcon } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { DataSourceStatus } from "./DataSourceStatus";

/**
 * Three places to work; everything else is settings.
 *
 * Rate is the daily job, Market is the one report worth watching, and
 * Customisation holds the three things an operator tunes — seasonal bands,
 * strategy, events. Configuration an owner touches once a quarter (the PMS
 * connection, room-type mapping, the activity log) lives behind Settings at
 * the bottom, next to the language switch, so the top of the nav only ever
 * shows work.
 */
const PRIMARY = [
  { href: "/rate", key: "rate", icon: Tag },
  { href: "/market", key: "market", icon: Compass },
  { href: "/customisation", key: "customisation", icon: SlidersHorizontal },
] as const;

export function Nav() {
  const ta = useTranslations("app");
  const pathname = usePathname();
  const locale = useLocale();
  const t = useTranslations("nav");

  const path = pathname.replace(`/${locale}`, "") || "/rate";
  const isActive = (href: string) => path === href || path.startsWith(`${href}/`);

  return (
    <aside className="flex h-screen w-[212px] shrink-0 flex-col border-r border-ink-200 bg-white">
      <div className="flex items-center gap-2.5 px-4 py-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 font-serif text-[14px] font-medium text-white">
          D
        </div>
        <div className="min-w-0">
          <div className="truncate font-serif text-[13.5px] font-medium text-ink-900">
            {ta("shortName")}
          </div>
          <div className="truncate text-[10.5px] text-ink-400">{ta("propertyName")}</div>
        </div>
      </div>

      <div className="mx-2 border-t border-ink-100" />

      <nav className="flex flex-col gap-0.5 px-2 pt-2" aria-label={t("primary")}>
        {PRIMARY.map((item) => {
          const active = isActive(item.href);
          return (
            <Tooltip key={item.href}>
              <TooltipTrigger asChild>
                <Link
                  href={`/${locale}${item.href}`}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
                    active ? "bg-brand-50 text-brand-800" : "text-ink-700 hover:bg-ink-100"
                  }`}
                >
                  <item.icon aria-hidden size={17} strokeWidth={1.5} className="shrink-0" />
                  <span className="text-[13px] font-medium">{t(`${item.key}.label`)}</span>
                </Link>
              </TooltipTrigger>
              <TooltipContent side="right">{t(`${item.key}.hint`)}</TooltipContent>
            </Tooltip>
          );
        })}
      </nav>

      {/* Language and settings live at the bottom, away from the daily work. */}
      <div className="mt-auto space-y-1 border-t border-ink-100 p-2">
        <LanguageSwitcher />
        <Link
          href={`/${locale}/settings`}
          aria-current={isActive("/settings") ? "page" : undefined}
          className={`flex items-center gap-2.5 rounded-lg px-3 py-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
            isActive("/settings") ? "bg-brand-50 text-brand-800" : "text-ink-600 hover:bg-ink-100"
          }`}
        >
          <SettingsIcon aria-hidden size={17} strokeWidth={1.5} className="shrink-0" />
          <span className="text-[13px] font-medium">{t("settings.label")}</span>
        </Link>
        <DataSourceStatus />
      </div>
    </aside>
  );
}
