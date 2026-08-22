"use client";

import { Chip, StatusBadge } from "./ui";
import {
  formatOccupancy,
  formatPct,
  formatStayDate,
  formatVND,
  isWeekend,
  marketLabel,
} from "@/lib/format";
import type { Recommendation } from "@/lib/types";

function ChangeCell({ rec }: { rec: Recommendation }) {
  const up = rec.change_pct > 0.05;
  const down = rec.change_pct < -0.05;
  return (
    <span
      className={`tnum font-semibold text-[13px] ${
        up ? "text-emerald-600" : down ? "text-rose-600" : "text-ink-400"
      }`}
    >
      {up ? "▲ " : down ? "▼ " : ""}
      {formatPct(rec.change_pct)}
    </span>
  );
}

function OccupancyCell({ rec }: { rec: Recommendation }) {
  if (rec.occupancy === null) return <span className="text-ink-300">—</span>;
  const pct = Math.round(rec.occupancy * 100);
  const tone = pct >= 85 ? "bg-emerald-500" : pct >= 50 ? "bg-brand-400" : "bg-amber-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-12 rounded-full bg-ink-100 overflow-hidden">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className="tnum text-[12px] text-ink-600 w-8">{formatOccupancy(rec.occupancy)}</span>
    </div>
  );
}

export function RecommendationTable({
  recommendations,
  onSelect,
  selectedId,
}: {
  recommendations: Recommendation[];
  onSelect: (rec: Recommendation) => void;
  selectedId?: number | null;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-ink-200 bg-ink-50/60">
            {[
              "Property / Room",
              "Stay date",
              "Occupancy",
              "D-",
              "Current",
              "Recommended",
              "Change",
              "Market",
              "Status",
              "",
            ].map((h, i) => (
              <th
                key={h + i}
                className={`px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-500 ${
                  ["Current", "Recommended", "Change", "D-"].includes(h) ? "text-right" : "text-left"
                }`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {recommendations.map((rec) => {
            const weekend = isWeekend(rec.stay_date);
            const selected = selectedId === rec.id;
            return (
              <tr
                key={rec.id}
                onClick={() => onSelect(rec)}
                className={`border-b border-ink-100 cursor-pointer transition-colors ${
                  selected ? "bg-brand-50" : "hover:bg-ink-50"
                }`}
              >
                <td className="px-3 py-2.5">
                  <div className="font-medium text-ink-900 leading-tight">{rec.room_name}</div>
                  <div className="text-[11px] text-ink-400 leading-tight mt-0.5">{rec.property_name}</div>
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-1.5">
                    <span className={weekend ? "font-medium text-ink-900" : "text-ink-700"}>
                      {formatStayDate(rec.stay_date)}
                    </span>
                    {rec.is_event && (
                      <Chip tone="warn" title={rec.event_name || "Event"}>
                        Event
                      </Chip>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2.5">
                  <OccupancyCell rec={rec} />
                </td>
                <td className="px-3 py-2.5 text-right tnum text-ink-600">
                  {rec.days_to_checkin ?? "—"}
                </td>
                <td className="px-3 py-2.5 text-right tnum text-ink-500">
                  {formatVND(rec.current_price)}
                </td>
                <td className="px-3 py-2.5 text-right tnum font-semibold text-ink-900">
                  {formatVND(rec.recommended_price)}
                </td>
                <td className="px-3 py-2.5 text-right">
                  <ChangeCell rec={rec} />
                </td>
                <td className="px-3 py-2.5">
                  {rec.market_price_index === null ? (
                    <Chip tone="neutral" title="No market observations for this date">
                      No data
                    </Chip>
                  ) : (
                    <Chip
                      tone={rec.market_price_index > 1.02 ? "up" : rec.market_price_index < 0.98 ? "down" : "info"}
                      title={`Market index ${rec.market_price_index.toFixed(2)} · ${rec.market_observation_count} observation(s)`}
                    >
                      {marketLabel(rec.market_price_index)}
                    </Chip>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <StatusBadge status={rec.status} />
                </td>
                <td className="px-3 py-2.5 text-right">
                  <span className="text-[12px] font-medium text-brand-600 whitespace-nowrap">Review →</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
