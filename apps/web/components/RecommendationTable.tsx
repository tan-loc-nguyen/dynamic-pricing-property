"use client";

import { Chip, StatusBadge } from "./ui";
import {
  confidenceTone,
  formatAdjPct,
  formatOccupancy,
  formatPaceGap,
  formatStayDate,
  formatVND,
  isWeekend,
  marketLabel,
  paceLabel,
  paceTone,
  pickupLabel,
} from "@/lib/format";
import type { Recommendation } from "@/lib/types";

/** Where the recommended NET rate sits inside the validated MIN–MAX band. */
function BandPosition({ rec }: { rec: Recommendation }) {
  const { band_min_net_rate: lo, band_max_net_rate: hi, recommended_net_rate: rate } = rec;
  if (lo === null || hi === null || hi <= lo) return <span className="text-ink-300">—</span>;
  const pct = Math.min(100, Math.max(0, ((rate - lo) / (hi - lo)) * 100));
  const clamped = rec.clamp_applied;
  return (
    <div className="flex items-center gap-2" title={`MIN ${lo.toLocaleString()} · MAX ${hi.toLocaleString()} VND NET`}>
      <div className="relative h-1.5 w-16 rounded-full bg-ink-100">
        <div
          className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-2.5 w-2.5 rounded-full ${
            clamped ? "bg-amber-500" : "bg-brand-500"
          }`}
          style={{ left: `${pct}%` }}
        />
      </div>
      {clamped && (
        <span className="text-[10px] font-medium text-amber-600 uppercase">{clamped}</span>
      )}
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
              ["Stay date", "left"],
              ["Room category", "left"],
              ["Avail", "right"],
              ["OTB occ", "left"],
              ["D-", "right"],
              ["Pace", "left"],
              ["Pickup", "left"],
              ["Current NET", "right"],
              ["Recommended NET", "right"],
              ["Dynamic", "right"],
              ["In band", "left"],
              ["Market", "left"],
              ["Status", "left"],
              ["", "right"],
            ].map(([h, align], i) => (
              <th
                key={String(h) + i}
                className={`px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-500 ${
                  align === "right" ? "text-right" : "text-left"
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
                <td className="px-3 py-2.5 whitespace-nowrap">
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
                  <div className="text-[10.5px] text-ink-400 mt-0.5">{(rec.season_label || "").replace(/\s*\(.*\)$/, "")}</div>
                </td>

                <td className="px-3 py-2.5 whitespace-nowrap">
                  <div className="font-medium text-ink-900 leading-tight">{rec.room_category_label}</div>
                </td>

                <td className="px-3 py-2.5 text-right tnum text-ink-600">
                  {rec.units_available ?? "—"}
                  <span className="text-ink-300">/{rec.units_total ?? "—"}</span>
                </td>

                <td className="px-3 py-2.5 whitespace-nowrap">
                  <span className="tnum text-ink-700">{formatOccupancy(rec.occupancy)}</span>
                  <span className="text-[10.5px] text-ink-400 ml-1">
                    exp {formatOccupancy(rec.expected_occupancy)}
                  </span>
                </td>

                <td className="px-3 py-2.5 text-right tnum text-ink-600">{rec.days_to_arrival ?? "—"}</td>

                <td className="px-3 py-2.5 whitespace-nowrap">
                  <Chip tone={paceTone(rec.pace_gap)} title={`Pace gap ${formatPaceGap(rec.pace_gap)}`}>
                    {paceLabel(rec.pace_gap)} {rec.pace_gap !== null && formatPaceGap(rec.pace_gap)}
                  </Chip>
                </td>

                <td className="px-3 py-2.5">
                  <span className="text-[11.5px] text-ink-500">{pickupLabel(rec.pickup_delta)}</span>
                </td>

                <td className="px-3 py-2.5 text-right tnum text-ink-500 whitespace-nowrap">
                  {formatVND(rec.current_net_rate)}
                </td>

                <td className="px-3 py-2.5 text-right tnum font-semibold text-ink-900 whitespace-nowrap">
                  {formatVND(rec.recommended_net_rate)}
                </td>

                <td className="px-3 py-2.5 text-right">
                  <span
                    className={`tnum font-semibold text-[13px] ${
                      rec.total_adjustment_pct > 0.05
                        ? "text-emerald-600"
                        : rec.total_adjustment_pct < -0.05
                          ? "text-rose-600"
                          : "text-ink-400"
                    }`}
                  >
                    {formatAdjPct(rec.total_adjustment_pct)}
                  </span>
                </td>

                <td className="px-3 py-2.5">
                  <BandPosition rec={rec} />
                </td>

                <td className="px-3 py-2.5 whitespace-nowrap">
                  {rec.market_qualified_count > 0 ? (
                    <Chip
                      tone={confidenceTone(rec.market_confidence)}
                      title={`${rec.market_qualified_count} qualified observation(s) at ${rec.market_confidence} confidence`}
                    >
                      {marketLabel(rec.market_price_index)}
                    </Chip>
                  ) : rec.market_ignored_count > 0 ? (
                    <Chip
                      tone="warn"
                      title={`${rec.market_ignored_count} observation(s) below the confidence bar — shown, not applied`}
                    >
                      Low conf · ignored
                    </Chip>
                  ) : (
                    <Chip tone="neutral" title="No market observations for this date">
                      No data
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
