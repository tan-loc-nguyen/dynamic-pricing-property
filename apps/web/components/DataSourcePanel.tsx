"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/Chip";
import type { PmsSource, PmsSourceInfo } from "@/lib/types";

/**
 * Which PMS data the app is running on, and whether Blue Jay is reachable.
 *
 * This lives in Settings rather than on the calendar because it is a setup
 * decision, not a daily one — but it is NOT hidden, because "which data am I
 * looking at" is the one question a demo must never leave ambiguous. An
 * operator who cannot tell demo data from their own is being misled.
 *
 * Every t() call here is a STATIC literal on purpose. Building the key from
 * the API's `label_key` would be a dynamic lookup, and the dead-key guard
 * treats a dynamic t() as "the whole namespace is used" — which would blind it
 * to this entire namespace.
 */
export function DataSourcePanel({ onChanged }: { onChanged?: () => void } = {}) {
  const t = useTranslations("dataSource");
  const [info, setInfo] = useState<PmsSourceInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .pmsSource()
      .then((body) => {
        setInfo(body);
        setError(null);
      })
      // Returning null on failure DELETED the whole "which data am I looking
      // at" section. This file's own comment says a demo must never leave that
      // ambiguous, and an absent panel is more ambiguous than an error.
      .catch(() => setError(t("saveFailed")));
  }, [t]);

  if (!info) {
    return error ? (
      <Card className="border-amber-200 bg-amber-50 p-4">
        <p className="text-[11.5px] text-amber-900">{error}</p>
      </Card>
    ) : null;
  }

  const copy: Record<string, { label: string; hint: string }> = {
    mock: { label: t("mock.label"), hint: t("mock.hint") },
    snapshot: { label: t("snapshot.label"), hint: t("snapshot.hint") },
    bluejay: { label: t("bluejay.label"), hint: t("bluejay.hint") },
  };
  // Fall back to the raw key rather than dropping the row: a provider
  // registered server-side but unknown here would otherwise silently never
  // appear as a choice, and if it were the ACTIVE one no row would highlight.
  const describe = (key: string) => copy[key] ?? { label: key, hint: "" };

  const choose = async (key: PmsSource) => {
    if (key === info.active || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.setPmsSource(key);
      setInfo(await api.pmsSource());
      // The REST of the page (provider health, data warnings, last-sync
      // findings) and the sidebar's demo dot were fetched once on mount.
      // Without this they keep asserting the previous source while every
      // number on screen comes from the new one.
      onChanged?.();
    } catch {
      // try/finally with no catch left `busy` cleared and the OLD source
      // rendered, so a failed switch looked exactly like no click at all.
      setError(t("saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  // NOT `window`: that shadows the global for the whole component, and the
  // next person reaching for localStorage or matchMedia in here would get a
  // baffling failure.
  const bjWindow = info.bluejay_window;

  return (
    <>
      <Card className="p-4">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-[12.5px] font-semibold text-ink-800">{t("title")}</h2>
          {busy && <span className="text-[11px] text-ink-400">{t("switching")}</span>}
        {error && !busy && <span className="text-[11px] text-amber-700">{error}</span>}
        </div>
        <p className="mt-1 text-[11.5px] text-ink-500">{t("subtitle")}</p>
        <p className="mt-2 text-[11px] uppercase tracking-wide text-ink-400">
          {t("active")}: <span className="text-ink-700">{describe(info.active).label}</span>
        </p>

        <div className="mt-3 space-y-2">
          {info.sources.map((source: { key: PmsSource }) => {
            const isActive = source.key === info.active;
            const text = describe(source.key);
            return (
              <button
                key={source.key}
                type="button"
                onClick={() => choose(source.key)}
                aria-pressed={isActive}
                disabled={busy}
                className={`flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition ${
                  isActive
                    ? "border-ink-900 bg-ink-50"
                    : "border-ink-200 hover:border-ink-300 disabled:opacity-60"
                }`}
              >
                <span
                  aria-hidden
                  className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${
                    isActive ? "bg-emerald-500" : "bg-ink-200"
                  }`}
                />
                <span>
                  <span className="block text-[12.5px] font-medium text-ink-900">{text.label}</span>
                  <span className="block text-[11px] leading-relaxed text-ink-500">{text.hint}</span>
                </span>
              </button>
            );
          })}
        </div>

        {/* Switching does NOT resync — whether it should is a product decision.
            Until it is made, the copy has to state what actually happens, or
            the panel asserts an active source over numbers the previous one
            produced. */}
        <p className="mt-3 border-t border-ink-100 pt-2.5 text-[11px] text-ink-500">
          {t("appliesNextSync")}
        </p>
        {/* Shadow Mode is stated elsewhere; this says the narrower, harder thing:
            no write path to Blue Jay exists at all. */}
        <p className="mt-1.5 text-[11px] text-ink-500">{t("readOnly")}</p>
      </Card>

      <Card className="p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-[12.5px] font-semibold text-ink-800">{t("windowTitle")}</h2>
          <Chip tone={bjWindow.is_open ? "up" : "warn"}>
            {bjWindow.is_open ? t("windowOpen") : t("windowClosed")}
          </Chip>
        </div>
        <ul className="mt-2 space-y-1">
          {bjWindow.windows.map((w) => (
            <li key={w.text} className="flex items-center gap-2 text-[11.5px] text-ink-600">
              <code className="rounded bg-ink-50 px-1.5 py-0.5 text-[11px]">{w.text}</code>
              {!w.confirmed && (
                <span className="text-[10.5px] text-amber-700">{t("windowUnconfirmed")}</span>
              )}
            </li>
          ))}
        </ul>
        {!bjWindow.is_open && bjWindow.next_open_at && (
          <p className="mt-2 text-[11.5px] text-ink-500">
            {t("windowNext", { time: bjWindow.next_open_at.slice(11, 16) })}
          </p>
        )}
      </Card>
    </>
  );
}
