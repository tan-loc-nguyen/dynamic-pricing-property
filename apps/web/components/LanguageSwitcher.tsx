"use client";

import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { LOCALES, LOCALE_LABELS, type Locale } from "@/i18n/routing";

/**
 * An explicit switcher rather than automatic negotiation.
 *
 * next-intl detects the browser's language in middleware, which does not exist
 * under `output: "export"` — and packaging this as a single-process local app
 * is still open. A switcher works identically in both builds.
 *
 * Collapsed, it becomes one button naming the language it will switch TO
 * rather than disappearing. Vietnamese is the default locale and the operator
 * who uses this daily reads Vietnamese — losing the language control as a side
 * effect of narrowing the rail would be a regression, not a simplification.
 */
export function LanguageSwitcher({ collapsed = false }: { collapsed?: boolean }) {
  const locale = useLocale() as Locale;
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations("nav");

  if (collapsed) {
    // Exactly two locales, so "the other one" is unambiguous. Written to
    // survive a third: it steps to the next and wraps.
    const next = LOCALES[(LOCALES.indexOf(locale) + 1) % LOCALES.length];
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            onClick={() => router.replace(pathname, { locale: next })}
            aria-label={t("switchTo", { language: LOCALE_LABELS[next] })}
            tooltip={t("switchTo", { language: LOCALE_LABELS[next] })}
          >
            {/* The CODE, not the language's own name: "Tiếng Việt" is ten
                characters and the rail is about three. The full name is in the
                tooltip and the accessible name, where there is room for it. */}
            <span className="w-full text-center text-[11px] font-medium uppercase">
              {next}
            </span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    );
  }

  return (
    <div className="rounded-lg border border-ink-200 px-2.5 py-2">
      <div className="text-[11px] font-medium text-ink-400 mb-1.5">{t("language")}</div>
      <div className="flex gap-1">
        {LOCALES.map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => router.replace(pathname, { locale: code })}
            aria-current={code === locale ? "true" : undefined}
            className={`flex-1 rounded-md px-2 py-1 text-[11px] font-medium transition-colors ${
              code === locale
                ? "bg-brand-50 text-brand-700"
                : "text-ink-500 hover:bg-ink-50 hover:text-ink-900"
            }`}
          >
            {LOCALE_LABELS[code]}
          </button>
        ))}
      </div>
    </div>
  );
}
