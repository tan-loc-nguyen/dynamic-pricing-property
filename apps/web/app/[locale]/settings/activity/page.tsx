"use client";

import { useTranslations } from "next-intl";

import { useCallback, useEffect, useState } from "react";
import { Card, Empty, PageHeader, Spinner, StatusBadge, inputClass } from "@/components/ui";
import { api } from "@/lib/api";

import { useFormat } from "@/lib/useFormat";
import type { HistoryEntry, Property } from "@/lib/types";

export default function HistoryPage() {
  const t = useTranslations("history");
  const tv = useTranslations("vocab");
  const tc = useTranslations("common");
  const tf = useTranslations("filters");
  const tst = useTranslations("status");
  const { formatDateTime, formatPct, formatSignedVND, formatStayDate, formatVND } = useFormat();
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [decision, setDecision] = useState("all");
  const [roomTypeId, setRoomTypeId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEntries(await api.history({ decision, room_type_id: roomTypeId }));
    } finally {
      setLoading(false);
    }
  }, [decision, roomTypeId]);

  useEffect(() => {
    api.properties().then(setProperties).catch(() => setProperties([]));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="px-7 py-6 space-y-5 max-w-[1500px]">
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle")}
      />

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-2.5">
          <div className="w-48">
            <div className="text-[11px] font-medium text-ink-500 mb-1">{tf("decision")}</div>
            <select className={inputClass} value={decision} onChange={(e) => setDecision(e.target.value)}>
              <option value="all">{tf("allDecisions")}</option>
              <option value="accepted">{tst("accepted")}</option>
              <option value="overridden">{tst("overridden")}</option>
            </select>
          </div>
          <div className="w-56">
            <div className="text-[11px] font-medium text-ink-500 mb-1">{tf("roomCategory")}</div>
            <select
              className={inputClass}
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

      <Card>
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
                {entries.map((e) => (
                  <tr key={e.id} className="border-b border-ink-100 hover:bg-ink-50">
                    <td className="px-3 py-2.5 text-ink-500 text-[12px] whitespace-nowrap">
                      {formatDateTime(e.created_at)}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="font-medium text-ink-900 leading-tight">{tv(`roomCategories.${e.room_category}`)}</div>
                      <div className="text-[11px] text-ink-400 leading-tight mt-0.5">{e.season_key ? tv(`seasonsShort.${e.season_key}`) : ""}</div>
                    </td>
                    <td className="px-3 py-2.5 text-ink-700">{formatStayDate(e.stay_date)}</td>
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
