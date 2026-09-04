"use client";

import { useTranslations } from "next-intl";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Empty } from "@/components/Empty";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { StatusBadge } from "@/components/StatusBadge";
import { selectClass } from "@/lib/formControls";
import { api } from "@/lib/api";

import { useFormat } from "@/lib/useFormat";
import type { HistoryEntry, Property } from "@/lib/types";

/**
 * One bulk action, one row.
 *
 * Pricing a fortnight writes fourteen decisions — that per-night record is what
 * Shadow Mode measures against, and what an outcome attaches to. But listing
 * fourteen near-identical lines every time teaches an operator to stop reading
 * the log, which is where the decisions that matter also live. Rows sharing a
 * `group_id` collapse into the range they covered.
 */
type LogRow = { lead: HistoryEntry; nights: number; from: string; to: string };

function groupBulkDecisions(entries: HistoryEntry[]): LogRow[] {
  const groups = new Map<string, HistoryEntry[]>();
  for (const e of entries) {
    if (!e.group_id) continue;
    const bucket = groups.get(e.group_id);
    if (bucket) bucket.push(e);
    else groups.set(e.group_id, [e]);
  }
  const seen = new Set<string>();
  const rows: LogRow[] = [];
  for (const e of entries) {
    if (!e.group_id) {
      rows.push({ lead: e, nights: 1, from: e.stay_date, to: e.stay_date });
      continue;
    }
    if (seen.has(e.group_id)) continue;
    seen.add(e.group_id);
    const dates = (groups.get(e.group_id) ?? [e]).map((g) => g.stay_date).sort();
    rows.push({
      lead: e,
      nights: dates.length,
      from: dates[0],
      to: dates[dates.length - 1],
    });
  }
  return rows;
}

export default function HistoryPage() {
  const t = useTranslations("history");
  const tv = useTranslations("vocab");
  const tc = useTranslations("common");
  const tf = useTranslations("filters");
  const tst = useTranslations("vocab.status");
  const { formatDateTime, formatPct, formatSignedVND, formatStayDate, formatVND } = useFormat();
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [decision, setDecision] = useState("all");
  const [roomTypeId, setRoomTypeId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEntries(await api.history({ decision, room_type_id: roomTypeId }));
    } catch {
      // An empty history and an unreachable API rendered identically, and one
      // of them means "you have made no decisions yet".
      setError(tc("apiUnreachable"));
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [decision, roomTypeId, tc]);

  useEffect(() => {
    api.properties().then(setProperties).catch(() => setProperties([]));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="h-full overflow-y-auto px-7 py-6 space-y-5 max-w-[1500px]">
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle")}
      />

      {/* An empty history and an unreachable API rendered identically, and one
          of them means "you have made no decisions yet". */}
      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] text-amber-900">
          {error}
        </div>
      )}

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-2.5">
          <div className="w-48">
            <div className="text-[11px] font-medium text-ink-500 mb-1">{tf("decision")}</div>
            <select className={selectClass} value={decision} onChange={(e) => setDecision(e.target.value)}>
              <option value="all">{tf("allDecisions")}</option>
              <option value="accepted">{tst("accepted")}</option>
              <option value="overridden">{tst("overridden")}</option>
            </select>
          </div>
          <div className="w-56">
            <div className="text-[11px] font-medium text-ink-500 mb-1">{tf("roomCategory")}</div>
            <select
              className={selectClass}
              value={roomTypeId ?? ""}
              onChange={(e) => setRoomTypeId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">{tf("allRoomCategories")}</option>
              {properties.flatMap((p) => p.room_types).map((rt) => (
                <option key={rt.id} value={rt.id}>{rt.category_label}</option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      <Card className="py-0">
        {loading ? (
          <Spinner label={t("loading")} />
        ) : entries.length === 0 ? (
          <Empty
            title={t("empty")}
            hint={t("emptyHint")}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-ink-200 bg-ink-50/60">
                  {[t("when"), tc("roomCategory"), tc("stayDate"), t("recommendedNet"), t("operatorNet"), t("difference"), t("decision"), t("reason"), t("engine")].map(
                    (h) => (
                      <th
                        key={h}
                        className={`px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-500 ${
                          [t("recommendedNet"), t("operatorNet"), t("difference")].includes(h) ? "text-right" : "text-left"
                        }`}
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {groupBulkDecisions(entries).map(({ lead: e, nights, from, to }) => (
                  <tr key={e.id} className="border-b border-ink-100 hover:bg-ink-50">
                    <td className="px-3 py-2.5 text-ink-500 text-[12px] whitespace-nowrap">
                      {formatDateTime(e.created_at)}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="font-medium text-ink-900 leading-tight">{tv(`roomCategories.${e.room_category}`)}</div>
                      <div className="text-[11px] text-ink-400 leading-tight mt-0.5">{e.season_key ? tv(`seasonsShort.${e.season_key}`) : ""}</div>
                    </td>
                    <td className="px-3 py-2.5 text-ink-700">
                      {nights > 1 ? (
                        <>
                          <div>{t("rangeDates", { from: formatStayDate(from), to: formatStayDate(to) })}</div>
                          <div className="text-[11px] text-ink-400">{t("bulkNights", { nights })}</div>
                        </>
                      ) : (
                        formatStayDate(e.stay_date)
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right tnum text-ink-500">{formatVND(e.recommended_net_rate)}</td>
                    <td className="px-3 py-2.5 text-right tnum font-semibold text-ink-900">
                      {formatVND(e.final_net_rate)}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {Math.abs(e.difference) < 1 ? (
                        <span className="text-ink-300 text-[12px]">as recommended</span>
                      ) : (
                        <div>
                          <div
                            className={`tnum text-[12.5px] font-medium ${
                              e.difference > 0 ? "text-emerald-600" : "text-rose-600"
                            }`}
                          >
                            {formatSignedVND(e.difference)}
                          </div>
                          <div className="tnum text-[11px] text-ink-400">{formatPct(e.difference_pct)}</div>
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={e.decision} />
                    </td>
                    <td className="px-3 py-2.5">
                      {e.reason_label ? (
                        <div>
                          <div className="text-[12px] text-ink-700">{e.reason_code ? tv(`overrideReasons.${e.reason_code}`) : e.reason_label}</div>
                          {e.note && <div className="text-[11px] text-ink-400 italic mt-0.5">“{e.note}”</div>}
                        </div>
                      ) : e.note ? (
                        <span className="text-[11px] text-ink-400 italic">“{e.note}”</span>
                      ) : (
                        <span className="text-ink-300">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-[11px] text-ink-400 whitespace-nowrap">
                      {e.engine_version}
                      <div>rules v{e.config_version}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
