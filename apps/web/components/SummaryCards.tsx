"use client";

import { Card } from "./ui";
import { formatOccupancy, formatPct } from "@/lib/format";
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
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card key={i} className="px-4 py-3.5 h-[86px] animate-pulse" />
        ))}
      </div>
    );
  }

  const change = summary.average_recommended_change_pct;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      <Stat label="Active rooms" value={String(summary.active_rooms)} sub="Room types being priced" />
      <Stat
        label="Upcoming nights"
        value={summary.upcoming_nights.toLocaleString()}
        sub={
          summary.horizon_start && summary.horizon_end
            ? `${summary.horizon_start} → ${summary.horizon_end}`
            : undefined
        }
      />
      <Stat label="Avg occupancy" value={formatOccupancy(summary.average_occupancy)} sub="Across the horizon" />
      <Stat
        label="Pending review"
        value={summary.pending_recommendations.toLocaleString()}
        tone={summary.pending_recommendations > 0 ? "warn" : "neutral"}
        sub={`${summary.accepted_recommendations} accepted · ${summary.overridden_recommendations} overridden`}
      />
      <Stat
        label="Avg suggested change"
        value={formatPct(change)}
        tone={change > 0.05 ? "up" : change < -0.05 ? "down" : "neutral"}
        sub="Recommended vs current price"
      />
    </div>
  );
}
