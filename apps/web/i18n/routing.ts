import { defineRouting } from "next-intl/routing";

export const LOCALES = ["en", "vi"] as const;
export type Locale = (typeof LOCALES)[number];

export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  vi: "Tiếng Việt",
};

/**
 * Locale lives in the URL segment, and there is deliberately NO middleware.
 *
 * next-intl's automatic locale negotiation runs in middleware, which does not
 * exist under `output: "export"`. Packaging this as a single-process local app
 * is still on the table, so detection is an explicit switcher instead of a
 * redirect the static build would silently drop.
 */
export const routing = defineRouting({
  locales: LOCALES,
  // The operator who uses this daily is Vietnamese; English is here for
  // non-Vietnamese stakeholders, not the other way round.
  defaultLocale: "vi",
  localePrefix: "always",
});
