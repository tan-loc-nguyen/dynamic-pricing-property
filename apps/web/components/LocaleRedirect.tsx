"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LOCALES, routing } from "@/i18n/routing";

const KNOWN_ROUTES = ["", "rate-book", "settings", "market", "events", "history"];

/**
 * Sends a pre-i18n URL to its localised equivalent.
 *
 * Adding the `[locale]` segment silently broke every bookmark and shared link:
 * `/settings` no longer matches a route, and with no middleware there was
 * nothing left to rewrite it. Rather than stranding those URLs on a 404, this
 * forwards the ones that used to exist.
 */
export function LocaleRedirect() {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    const segments = pathname.split("/").filter(Boolean);
    if (LOCALES.includes(segments[0] as (typeof LOCALES)[number])) return;
    if (!KNOWN_ROUTES.includes(segments[0] ?? "")) return;
    router.replace(`/${routing.defaultLocale}${pathname}`);
  }, [pathname, router]);

  return null;
}
