import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { NextIntlClientProvider, hasLocale } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import "../globals.css";
import { Nav } from "@/components/Nav";
import { routing } from "@/i18n/routing";

export function generateStaticParams() {
  // Both locales are prerendered, which is what lets this work without the
  // middleware a static export cannot run.
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "app" });
  return { title: t("name"), description: t("tagline") };
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);

  return (
    <html lang={locale}>
      {/* suppressHydrationWarning: browser extensions commonly inject attributes
          onto <body> before React hydrates, which is harmless but noisy. */}
      <body className="h-screen overflow-hidden" suppressHydrationWarning>
        <NextIntlClientProvider>
          {/* The shell is exactly one viewport tall and never scrolls itself.
              A long table used to grow the document, and the sidebar — a flex
              sibling — grew with it, so its footer notices ended up thousands of
              pixels below the fold. Each pane scrolls inside its own box now. */}
          <div className="flex h-screen overflow-hidden">
            <Nav />
            <main className="flex-1 min-w-0 overflow-y-auto">{children}</main>
          </div>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
