"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { Card, Chip, Spinner } from "@/components/ui";
import { DataSourcePanel } from "@/components/DataSourcePanel";
import { RoomTypeMapPanel } from "@/components/RoomTypeMapPanel";
import type { SystemStatus } from "@/lib/types";

/**
 * Where the numbers come from, and whether to trust them today.
 *
 * This is the home for the persistent technical notices that used to sit in
 * the sidebar on every screen. They are true and they matter; they just do not
 * need to be in front of someone pricing a Tuesday.
 */
export default function DataSettingsPage() {
  const t = useTranslations("dataSettings");
  const tds = useTranslations("dataSource");
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [providers, setProviders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    Promise.all([api.status(), api.marketProviders().catch(() => [])])
      .then(([s, p]) => {
        setStatus(s);
        setProviders(p);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-6 text-[12.5px] text-ink-400">
        <Spinner /> {t("loading")}
      </div>
    );
  }

  const rows = [
    { label: t("pms"), value: status?.pms?.name ?? "—", healthy: status?.pms?.healthy },
    { label: t("market"), value: status?.market?.name ?? "—", healthy: status?.market?.healthy },
  ];

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-4">
        <div>
          <h1 className="text-[19px] font-semibold text-ink-900">{t("title")}</h1>
          <p className="text-[12px] text-ink-500">{t("subtitle")}</p>
        </div>

        <DataSourcePanel onChanged={reload} />

        {/* Data warnings travel on their own channel and get their own
            treatment. These are the ones that mean "do not show this to a
            client yet", not "you have some configuration left to do". */}
        {(status?.pms?.warnings?.length ?? 0) > 0 && (
          <Card className="border-amber-300 bg-amber-50 p-4">
            <h2 className="text-[12.5px] font-semibold text-amber-900">
              {tds("warningsTitle")}
            </h2>
            <ul className="mt-2 list-disc space-y-1.5 pl-4">
              {status!.pms.warnings.map((warning, i) => (
                // Index, not the text: `_as_int` emits an identical string for
                // every row carrying the same bad value.
                <li key={`warn-${i}`} className="text-[11.5px] leading-relaxed text-amber-900">
                  {warning}
                </li>
              ))}
            </ul>
          </Card>
        )}
        <RoomTypeMapPanel />

        <Card className="divide-y divide-ink-100">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center justify-between gap-3 px-4 py-3">
              <div>
                <div className="text-[13px] font-medium text-ink-900">{r.label}</div>
                <div className="text-[11.5px] text-ink-500">{r.value}</div>
              </div>
              <Chip tone={r.healthy ? "up" : "warn"}>
                {t(r.healthy ? "healthy" : "notConnected")}
              </Chip>
            </div>
          ))}
        </Card>

        {/* Provider remediation text is developer-facing on purpose (D30) and
            is shown verbatim: whoever fixes it needs the variable names. */}
        {providers.filter((p) => !p.healthy && p.remediation).length > 0 && (
          <Card className="p-4">
            <h2 className="text-[12.5px] font-semibold text-ink-800">{t("toConnect")}</h2>
            <ul className="mt-2 space-y-2">
              {providers
                .filter((p) => !p.healthy && p.remediation)
                .map((p) => (
                  <li key={p.key} className="text-[11.5px] text-ink-600">
                    <span className="font-medium text-ink-800">{p.name}:</span> {p.remediation}
                  </li>
                ))}
            </ul>
          </Card>
        )}

        {/* Adapter findings from the last sync. English on purpose (D30): like
            provider remediation above, this is aimed at whoever fixes it. The
            orphan-rooms warning says occupancy is overstated and recommendations
            biased upward, which is not something to leave in a response body
            nobody reads. */}
        {((status?.last_sync_findings?.warnings?.length ?? 0) > 0 ||
          (status?.last_sync_findings?.discrepancies?.length ?? 0) > 0) && (
          <Card className="p-4">
            <h2 className="text-[12.5px] font-semibold text-ink-800">
              {tds("findingsTitle")}
            </h2>
            <ul className="mt-2 list-disc space-y-1.5 pl-4">
              {[
                ...(status?.last_sync_findings?.warnings ?? []),
                ...(status?.last_sync_findings?.discrepancies ?? []),
              ].map((finding, i) => (
                // Warnings and discrepancies are concatenated, so one string can
                // legitimately appear in both lists.
                <li key={`finding-${i}`} className="text-[11.5px] leading-relaxed text-ink-600">
                  {finding}
                </li>
              ))}
            </ul>
          </Card>
        )}

        <Card className="p-4">
          <h2 className="text-[12.5px] font-semibold text-ink-800">{t("shadowTitle")}</h2>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-600">{t("shadowBody")}</p>
        </Card>

        <Card className="border-amber-200 bg-amber-50/50 p-4">
          <h2 className="text-[12.5px] font-semibold text-amber-900">{t("unvalidatedTitle")}</h2>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-amber-800">
            {t("unvalidatedBody")}
          </p>
        </Card>

        <Card className="p-4">
          <h2 className="text-[12.5px] font-semibold text-ink-800">{t("dataset")}</h2>
          <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1.5 text-[11.5px] sm:grid-cols-3">
            {Object.entries(status?.counts ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2">
                <dt className="truncate text-ink-500">{k}</dt>
                <dd className="tnum text-ink-800">{v as number}</dd>
              </div>
            ))}
          </dl>
          {status?.last_run_id && (
            <p className="mt-3 text-[11px] text-ink-400">
              {t("lastRun", { id: status.last_run_id })}
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
