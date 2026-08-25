"use client";

import { useCallback } from "react";
import { useMessages } from "next-intl";

/**
 * Resolves what the operator typed into the CODES it names, in their language.
 *
 * The API stores English — `room_category_label` is "2BR Regular" whichever
 * locale is being viewed — so matching the search term against those columns
 * meant a Vietnamese operator searching for "phòng ngủ", the words printed on
 * every row in front of them, got nothing back.
 *
 * The translations live here, not on the server (D30), so the resolution
 * happens here too: the term is matched against the message catalogue and the
 * resulting codes are sent. The API never learns a second language, and paging
 * stays server-side.
 *
 * Real-world names — the property, a competitor — have no code to resolve to
 * and keep travelling as free text, which is correct: they are never
 * translated either.
 */
export function useSearchCodes() {
  const messages = useMessages() as Record<string, unknown>;

  return useCallback(
    (term: string): string[] => {
      const needle = term.trim().toLowerCase();
      if (!needle) return [];

      const vocab = (messages?.vocab ?? {}) as Record<string, unknown>;
      // seasonsShort carries the SAME keys as seasons, so an operator who types
      // the short form finds the same rows. A Set collapses the overlap.
      const buckets = ["roomCategories", "seasons", "seasonsShort"];

      const codes = new Set<string>();
      for (const name of buckets) {
        const bucket = vocab[name];
        if (!bucket || typeof bucket !== "object") continue;
        for (const [code, label] of Object.entries(bucket as Record<string, unknown>)) {
          if (typeof label === "string" && label.toLowerCase().includes(needle)) {
            codes.add(code);
          }
        }
      }
      return [...codes];
    },
    [messages],
  );
}
