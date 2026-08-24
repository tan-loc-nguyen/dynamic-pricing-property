"use client";

import { Card } from "./ui";
import { formatOccupancy, formatPaceGap, formatPct } from "@/lib/format";
import type { Summary } from "@/lib/types";

function Stat({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "up" | "down" | "warn";
}) {
  const tones: Record<string, string> = {
    neutral: "text-ink-900",
    up: "text-emerald-600",
    down: "text-rose-600",
    warn: "text-amber-600",
  };
  return (
    <Card className="px-4 py-3.5">
      <div className="text-[11px] font-medium uppercase tracking-wide text-ink-400">{label}</div>
      <div className={`mt-1.5 text-[24px] font-semibold leading-none tnum ${tones[tone]}`}>{value}</div>
      {sub && <div className="mt-1.5 text-[11px] text-ink-400">{sub}</div>}
    </Card>
  );
}

export function SummaryCards({ summary }: { summary: Summary | null }) {
  if (!summary) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} className="px-4 py-3.5 h-[86px] animate-pulse" />
        ))}
      </div>
    );
  }

  const gap = summary.average_pace_gap;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
      <Stat
        label="Apartments"
        value={String(summary.total_units)}
        sub={`${summary.room_types} room categories priced`}
      />
      <Stat
        label="Upcoming nights"
        value={summary.upcoming_nights.toLocaleString()}
        sub={
          summary.horizon_start && summary.horizon_end
            ? `${summary.horizon_start} → ${summary.horizon_end}`
            : undefined
        }
      />
      <Stat label="Avg occupancy" value={formatOccupancy(summary.average_occupancy)} sub="On the books" />
      <Stat
        label="Avg rate change"
        value={formatPct(summary.average_recommended_change_pct)}
        tone={
          summary.average_recommended_change_pct > 0.05
            ? "up"
            : summary.average_recommended_change_pct < -0.05
              ? "down"
              : "neutral"
        }
        sub="Recommended vs current NET"
      />
      <Stat
        label="Avg pace position"
        value={formatPaceGap(gap)}
        tone={gap === null ? "neutral" : gap < -0.03 ? "down" : gap > 0.03 ? "up" : "neutral"}
        sub="vs booking curve expectation"
      />
      <Stat
        label="Pending review"
        value={summary.pending_recommendations.toLocaleString()}
        tone={summary.pending_recommendations > 0 ? "warn" : "neutral"}
        sub={
          `${summary.accepted_recommendations} accepted · ${summary.overridden_recommendations} overridden` +
          (summary.unpriced_recommendations > 0
            ? ` · ${summary.unpriced_recommendations} could not be priced`
            : "")
        }
      />
    </div>
  );
}
