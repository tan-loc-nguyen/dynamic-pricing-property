import Link from "next/link";
import { LOCALE_LABELS, LOCALES, routing } from "@/i18n/routing";
import { LocaleRedirect } from "@/components/LocaleRedirect";
import "./globals.css";

/**
 * Bare "/" has no locale segment, so it forwards to the default one.
 *
 * This used to call `redirect()`. That is a SERVER redirect, and there is no
 * server in a static export — Next exports the route as an error document, so
 * the packaged app rendered a blank page for anyone who typed the address
 * without a locale. `LocaleRedirect` does the same job on the client, and the
 * markup below is what a viewer sees for the one frame before it runs, or
 * forever if they have JavaScript disabled.
 *
 * Like `not-found.tsx`, this carries its own <html>: the root layout is a
 * pass-through because `lang` belongs to the locale segment.
 */
export default function RootPage() {
  return (
    <html lang={routing.defaultLocale}>
      <body className="min-h-screen grid place-items-center p-8" suppressHydrationWarning>
        <LocaleRedirect />
        <div className="text-center max-w-md">
          <div className="text-[13px] font-semibold text-ink-900">Dynamic Pricing Property</div>
          <p className="text-[13px] text-ink-500 mt-3">Đang mở… · Opening…</p>
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
