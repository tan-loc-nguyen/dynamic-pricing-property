"use client";

import { useEffect, useState } from "react";
import * as Popover from "@radix-ui/react-popover";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import type { SystemStatus } from "@/lib/types";

/**
 * One dot instead of two permanent warning cards.
 *
 * The sidebar used to carry a Shadow Mode block and an "unvalidated layer"
 * block on every screen forever — roughly 180 px of text nobody re-reads after
 * the first day, competing with the work. The facts still matter, so they moved
 * into something that states the situation in a line and explains on demand.
 */
export function DataSourceStatus() {
  const t = useTranslations("status");
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  // `demo_mode` is the API's own answer; deriving it from a provider
  // string here would be a second source of truth for the same fact.
  const demo = status?.demo_mode !== false;
  const tone = demo ? "bg-amber-400" : "bg-emerald-500";

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[11.5px] text-ink-600
            hover:bg-ink-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          <span className={`h-2 w-2 shrink-0 rounded-full ${tone}`} aria-hidden />
          <span className="truncate">{demo ? t("demoData") : t("connected")}</span>
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          align="start"
          sideOffset={6}
          className="z-50 w-72 rounded-xl border border-ink-200 bg-white p-3.5 shadow-lg
            focus:outline-none"
        >
          <h3 className="text-[12.5px] font-semibold text-ink-900">{t("title")}</h3>

          <dl className="mt-2.5 space-y-1.5 text-[11.5px]">
            <div className="flex justify-between gap-3">
              <dt className="text-ink-500">{t("mode")}</dt>
              <dd className="text-ink-800">{t("shadowMode")}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-500">{t("pms")}</dt>
              <dd className="text-ink-800">{status?.pms?.mode ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-500">{t("marketSource")}</dt>
              <dd className="text-ink-800">{status?.market?.mode ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-500">{t("engine")}</dt>
              <dd className="tnum text-ink-800">{status?.engine?.version ?? "—"}</dd>
            </div>
          </dl>

          <p className="mt-3 border-t border-ink-100 pt-2.5 text-[11px] leading-relaxed text-ink-500">
            {t("shadowExplain")}
          </p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-amber-700">{t("unvalidated")}</p>

          <Popover.Arrow className="fill-white" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
