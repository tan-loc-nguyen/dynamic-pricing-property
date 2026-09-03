"use client";

import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { LOCALES, LOCALE_LABELS, type Locale } from "@/i18n/routing";

/**
 * An explicit switcher rather than automatic negotiation.
 *
 * next-intl detects the browser's language in middleware, which does not exist
 * under `output: "export"` — and packaging this as a single-process local app
 * is still open. A switcher works identically in both builds.
 */
export function LanguageSwitcher() {
  const locale = useLocale() as Locale;
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations("nav");

  return (
    <div className="rounded-lg border border-ink-200 px-2.5 py-2">
      <div className="text-[10.5px] font-medium uppercase tracking-wide text-ink-400 mb-1.5">
        {t("language")}
      </div>
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
