"use client";

import { useEffect } from "react";
import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";

/**
 * The index route leads to Rate, which is the daily workspace.
 *
 * A client-side replace rather than `redirect()`: this app is exported
 * statically (D32), and a server redirect exports as an error document — the
 * exact bug D32 records for the bare "/" route.
 */
export default function LocaleIndex() {
  const router = useRouter();
  const locale = useLocale();
  useEffect(() => {
    router.replace(`/${locale}/rate`);
  }, [router, locale]);
  return null;
}
