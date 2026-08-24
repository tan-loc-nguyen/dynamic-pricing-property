"use client";

import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { LanguageSwitcher } from "./LanguageSwitcher";

const LINKS = [
  { href: "/", key: "rateReview" },
  { href: "/rate-book", key: "rateBook" },
  { href: "/settings", key: "dynamicRules" },
  { href: "/market", key: "market" },
  { href: "/events", key: "events" },
  { href: "/history", key: "history" },
] as const;

export function Nav() {
  const pathname = usePathname();
  const t = useTranslations("nav");
  const tn = useTranslations("navHints");
  const ta = useTranslations("app");

  return (
    <aside className="w-60 shrink-0 border-r border-ink-200 bg-white flex flex-col">
      <div className="px-5 py-5 border-b border-ink-100">
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 grid place-items-center text-white text-sm font-semibold">
            D
          </div>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold leading-tight text-ink-900">{ta("shortName")}</div>
            {/* The operator whose portfolio is being priced. */}
            <div className="text-[11px] text-ink-500 leading-tight">Luminous Luxury Apartments</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-3 space-y-0.5">
        {LINKS.map((link) => {
          const active = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`block rounded-lg px-3 py-2 transition-colors ${
                active ? "bg-brand-50 text-brand-700" : "text-ink-600 hover:bg-ink-50 hover:text-ink-900"
              }`}
            >
              <div className="text-[13px] font-medium leading-tight">{t(link.key)}</div>
              <div className={`text-[11px] leading-tight mt-0.5 ${active ? "text-brand-500" : "text-ink-400"}`}>
                {tn(link.key)}
              </div>
            </Link>
          );
        })}
      </nav>

      <div className="p-3 border-t border-ink-100 space-y-2">
        <LanguageSwitcher />
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2.5">
          <div className="text-[11px] font-semibold text-emerald-900 leading-tight">
            {ta("shadowModeTitle")}
          </div>
          <div className="text-[11px] text-emerald-700 leading-snug mt-1">{ta("shadowModeBody")}</div>
        </div>
        <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2.5">
          <div className="text-[11px] font-semibold text-amber-900 leading-tight">
            {ta("unvalidatedTitle")}
          </div>
          <div className="text-[11px] text-amber-700 leading-snug mt-1">{ta("unvalidatedBody")}</div>
        </div>
      </div>
    </aside>
  );
}
