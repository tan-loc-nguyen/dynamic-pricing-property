"use client";

import { useTranslations } from "next-intl";
import type { Adjustment } from "./types";

type IcuValues = Record<string, string | number | Date>;

/**
 * Renders an engine step into the viewer's language.
 *
 * ONE function, used by both the drawer breakdown and the table's summary
 * column. That is deliberate: D28 exists because those two surfaces each
 * derived the band label themselves and disagreed — the row read "On pace"
 * beside a drawer showing a "+4% Ahead of pace" line for the same date. The
 * engine now names the band, and both surfaces read the same name through
 * here, so there is no second derivation left to drift.
 */
export function useAdjustmentText() {
  const t = useTranslations();
  const enrich = useParamEnricher();

  return (adj: Adjustment): { label: string; reason: string } => {
    // No key means the operator wrote this wording themselves (a renamed or
    // invented band). Translating it would put words in their mouth.
    if (!adj.label_key) return { label: adj.label, reason: "" };

    const params = enrich(adj.params);
    return {
      label: t(`${adj.label_key}.label`, params),
      reason: t(`${adj.label_key}.reason`, params),
    };
  };
}

/** The band label for a row, from the key the ENGINE chose. */
export function useBandLabel() {
  const t = useTranslations();
  return (labelKey: string | null, fallback: string): string =>
    labelKey ? t(`${labelKey}.label`) : fallback;
}

/**
 * Season and room-category arrive as codes, and the shared vocabulary already
 * translates codes. Everything else — enums like `direction` and
 * `impact_level` — is resolved by ICU `select` inside the message file, which
 * is where a language's choices belong.
 */
function useParamEnricher() {
  const t = useTranslations("vocab");

  return (params: Record<string, unknown>): IcuValues => {
    const out: Record<string, unknown> = { ...params };

    if (typeof params.season_key === "string") {
      out.season = t(`seasons.${params.season_key}`);
    }
    if (typeof params.room_category === "string") {
      out.room_category = t(`roomCategories.${params.room_category}`);
    }
    if (typeof params.day === "string") {
      out.day = t(`days.${params.day}`);
    }
    if (typeof params.source === "string") {
      out.source = t(`source.${params.source}`);
    }

    // ICU throws on a null it was asked to format, which would blank the whole
    // drawer rather than one line. A signal that measured nothing renders as a
    // dash, the same as everywhere else in the UI.
    for (const [key, value] of Object.entries(out)) {
      if (value === null || value === undefined) out[key] = "—";
      else if (typeof value === "boolean") out[key] = String(value);
    }
    return out as IcuValues;
  };
}
