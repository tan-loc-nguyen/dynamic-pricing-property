"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { DataSourceStatus } from "./DataSourceStatus";

/**
 * Two places to work, and one place where complexity lives.
 *
 * The previous nav gave equal billing to four configuration screens (rate
 * book, dynamic rules, history, raw market) that an owner touches rarely, and
 * to the one screen they use daily. Everything infrequent now sits behind
 * Settings; the calendar is the default route.
 */
const PRIMARY = [
  { href: "/calendar", key: "calendar" },
  { href: "/market", key: "market" },
] as const;

export function Nav() {
  const ta = useTranslations("app");
  const pathname = usePathname();
  const locale = useLocale();
  const t = useTranslations("nav");

  const path = pathname.replace(`/${locale}`, "") || "/calendar";
  const isActive = (href: string) => path === href || path.startsWith(`${href}/`);

  return (
    <aside className="flex h-screen w-[212px] shrink-0 flex-col border-r border-ink-200 bg-white">
      <div className="flex items-center gap-2.5 px-4 py-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-[13px] font-bold text-white">
          D
        </div>
        <div className="min-w-0">
          <div className="truncate text-[12.5px] font-semibold text-ink-900">{ta("shortName")}</div>
          <div className="truncate text-[10.5px] text-ink-400">{ta("propertyName")}</div>
        </div>
      </div>

      <nav className="flex flex-col gap-0.5 px-2" aria-label={t("primary")}>
      {PRIMARY.map((item) => {
        const active = isActive(item.href);
        return (
          <Link
            key={item.href}
            href={`/${locale}${item.href}`}
            aria-current={active ? "page" : undefined}
            className={`rounded-lg px-3 py-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
              active ? "bg-brand-50 text-brand-800" : "text-ink-700 hover:bg-ink-100"
            }`}
          >
            <div className="text-[13px] font-medium">{t(`${item.key}.label`)}</div>
            <div className={`text-[11px] ${active ? "text-brand-600" : "text-ink-400"}`}>
              {t(`${item.key}.hint`)}
            </div>
          </Link>
        );
      })}

      <div className="my-2 border-t border-ink-100" />

      <Link
        href={`/${locale}/settings`}
        aria-current={isActive("/settings") ? "page" : undefined}
        className={`flex items-center gap-2 rounded-lg px-3 py-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
          isActive("/settings") ? "bg-brand-50 text-brand-800" : "text-ink-600 hover:bg-ink-100"
        }`}
      >
        <span aria-hidden className="text-[13px]">
          ⚙
        </span>
        <span className="text-[13px] font-medium">{t("settings.label")}</span>
      </Link>
      </nav>

      <div className="mt-auto border-t border-ink-100 p-2">
        <LanguageSwitcher />
        <DataSourceStatus />
      </div>
    </aside>
  );
}
