import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { NextIntlClientProvider, hasLocale } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Fraunces, Karla } from "next/font/google";
import "../globals.css";
import { Nav } from "@/components/Nav";
import { TooltipProvider } from "@/components/ui/tooltip";
import { routing } from "@/i18n/routing";

const karla = Karla({ subsets: ["latin"], variable: "--font-karla" });
const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  // The "soft" optical size gives Fraunces its warm, almost hand-set
  // quality at display sizes -- the whole reason it was chosen over a
  // more clinical serif like Playfair.
  axes: ["opsz", "SOFT"],
});

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
    <html lang={locale} className={`${karla.variable} ${fraunces.variable}`}>
      {/* suppressHydrationWarning: browser extensions commonly inject attributes
          onto <body> before React hydrates, which is harmless but noisy. */}
      <body className="h-screen overflow-hidden" suppressHydrationWarning>
        <NextIntlClientProvider>
          <TooltipProvider delayDuration={200}>
            {/* The shell is exactly one viewport tall and never scrolls itself.
                A long table used to grow the document, and the sidebar — a flex
                sibling — grew with it, so its footer notices ended up thousands of
                pixels below the fold. Each pane scrolls inside its own box now. */}
            <div className="flex h-screen overflow-hidden">
              <Nav />
              <main className="flex-1 min-w-0 overflow-hidden p-4">{children}</main>
            </div>
          </TooltipProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
