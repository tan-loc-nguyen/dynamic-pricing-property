import Link from "next/link";
import { LOCALE_LABELS, LOCALES, routing } from "@/i18n/routing";
import { LocaleRedirect } from "@/components/LocaleRedirect";
import "./globals.css";

/**
 * The root layout is a pass-through, so this page carries its own document.
 * Without it an unmatched URL rendered an empty body — no nav, no way back.
 */
export default function NotFound() {
  return (
    <html lang={routing.defaultLocale}>
      <body className="min-h-screen grid place-items-center p-8" suppressHydrationWarning>
        <LocaleRedirect />
        <div className="text-center max-w-md">
          <div className="text-[13px] font-semibold text-ink-900">Dynamic Pricing Property</div>
          <p className="text-[13px] text-ink-500 mt-3">
            Trang này không tồn tại. · This page does not exist.
          </p>
          <div className="mt-5 flex gap-2 justify-center">
            {LOCALES.map((locale) => (
              <Link
                key={locale}
                href={`/${locale}`}
                className="rounded-lg border border-ink-200 px-3 py-1.5 text-[12px] font-medium text-ink-700 hover:bg-ink-50"
              >
                {LOCALE_LABELS[locale]}
              </Link>
            ))}
          </div>
        </div>
      </body>
    </html>
  );
}
