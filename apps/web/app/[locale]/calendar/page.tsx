"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { addDaysISO, dateRange, todayISO } from "@/lib/dates";
import { attentionScore, needsAttention } from "@/lib/attention";
import { PricingCalendar, type CalendarRow } from "@/components/calendar/PricingCalendar";
import { RecommendationDrawer } from "@/components/RecommendationDrawer";
import { Button, Card, Spinner } from "@/components/ui";
import type { Booking, Recommendation } from "@/lib/types";

const RANGES = [14, 30, 60] as const;

/**
 * A compact answer to "how is the next month going?".
 *
 * Three numbers that change and can be acted on, replacing six equally
 * weighted cards — one of which reported a constant (22 apartments).
 */
function DecisionSummary({
  recs,
  attention,
  onShowAttention,
  attentionOnly,
}: {
  recs: Recommendation[];
  attention: number;
  onShowAttention: () => void;
  attentionOnly: boolean;
}) {
  const t = useTranslations("calendar");

  const occupancy = useMemo(() => {
    const withOcc = recs.filter((r) => r.occupancy !== null);
    if (!withOcc.length) return null;
    return withOcc.reduce((s, r) => s + (r.occupancy ?? 0), 0) / withOcc.length;
  }, [recs]);

  const pending = recs.filter((r) => r.status === "pending").length;

  return (
    <div className="flex flex-wrap items-stretch gap-2">
      <Card className="flex-1 min-w-[150px] px-3.5 py-2.5">
        <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
          {t("summary.occupancy")}
        </div>
        <div className="mt-0.5 flex items-baseline gap-2">
          <span className="tnum text-[20px] font-semibold text-ink-900">
            {occupancy === null ? "—" : `${Math.round(occupancy * 100)}%`}
          </span>
          <div className="h-1.5 flex-1 rounded-full bg-ink-150 overflow-hidden">
            <div
              className="h-full bg-brand-500"
              style={{ width: `${Math.round((occupancy ?? 0) * 100)}%` }}
            />
          </div>
        </div>
      </Card>

      <button
        type="button"
        onClick={onShowAttention}
        aria-pressed={attentionOnly}
        className={`flex-1 min-w-[150px] rounded-xl border px-3.5 py-2.5 text-left transition-colors
          focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500
          ${attentionOnly ? "border-amber-400 bg-amber-50" : "border-ink-200 bg-white hover:bg-amber-50/50"}`}
      >
        <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
          {t("summary.attention")}
        </div>
        <div className="mt-0.5 flex items-baseline gap-1.5">
          <span className="tnum text-[20px] font-semibold text-amber-600">{attention}</span>
          <span className="text-[11px] text-ink-400">
            {attentionOnly ? t("summary.showingOnly") : t("summary.tapToFilter")}
          </span>
        </div>
      </button>

      <Card className="flex-1 min-w-[150px] px-3.5 py-2.5">
        <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
          {t("summary.pending")}
        </div>
        <div className="mt-0.5 tnum text-[20px] font-semibold text-ink-900">{pending}</div>
      </Card>
    </div>
  );
}

export default function CalendarPage() {
  const t = useTranslations("calendar");
  const tc = useTranslations("common");

  const [start, setStart] = useState(todayISO);
  const [days, setDays] = useState<number>(30);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [selected, setSelected] = useState<Recommendation | null>(null);
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const end = useMemo(() => addDaysISO(start, days - 1), [start, days]);
  const dates = useMemo(() => dateRange(start, end), [start, end]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [r, b] = await Promise.all([
        api.recommendations({ start_date: start, end_date: end, limit: 5000 }),
        api.bookings({ start_date: start, end_date: end }),
      ]);
      setRecs(r);
      setBookings(b);
    } catch (e: any) {
      setError(e?.message ?? tc("unknownError"));
    } finally {
      setLoading(false);
    }
  }, [start, end, tc]);

  useEffect(() => {
    load();
  }, [load]);

  const rows: CalendarRow[] = useMemo(() => {
    const byType = new Map<number, CalendarRow>();
    for (const r of recs) {
      let row = byType.get(r.room_type_id);
      if (!row) {
        row = {
          roomTypeId: r.room_type_id,
          category: r.room_category,
          unitsTotal: r.units_total ?? 0,
          byDate: new Map(),
        };
        byType.set(r.room_type_id, row);
      }
      row.byDate.set(r.stay_date, r);
    }
    return [...byType.values()].sort((a, b) => a.category.localeCompare(b.category));
  }, [recs]);

  const bookingsByRoomType = useMemo(() => {
    const m = new Map<number, Booking[]>();
    for (const b of bookings) {
      const list = m.get(b.room_type_id);
      if (list) list.push(b);
      else m.set(b.room_type_id, [b]);
    }
    return m;
  }, [bookings]);

  const attention = useMemo(() => recs.filter(needsAttention).length, [recs]);

  // Peers for the pace curve: the same room type across the whole window, which
  // is where expected-occupancy-by-lead-time actually comes from.
  const peers = useMemo(
    () => (selected ? recs.filter((r) => r.room_type_id === selected.room_type_id) : []),
    [recs, selected],
  );

  const openMostUrgent = () => {
    const ranked = [...recs].filter(needsAttention).sort((a, b) => attentionScore(b) - attentionScore(a));
    if (ranked[0]) setSelected(ranked[0]);
  };

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[19px] font-semibold text-ink-900">{t("title")}</h1>
          <p className="text-[12px] text-ink-500">{t("subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => setStart(todayISO())}>{t("today")}</Button>
          <div className="flex items-center rounded-lg border border-ink-200">
            <button
              onClick={() => setStart(addDaysISO(start, -days))}
              aria-label={t("previousPeriod")}
              className="px-2.5 py-1.5 text-[13px] text-ink-600 hover:bg-ink-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              ←
            </button>
            <button
              onClick={() => setStart(addDaysISO(start, days))}
              aria-label={t("nextPeriod")}
              className="border-l border-ink-200 px-2.5 py-1.5 text-[13px] text-ink-600 hover:bg-ink-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              →
            </button>
          </div>
          <div className="flex rounded-lg border border-ink-200 overflow-hidden">
            {RANGES.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                aria-pressed={days === d}
                className={`px-2.5 py-1.5 text-[12px] focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
                  days === d ? "bg-brand-600 text-white" : "text-ink-600 hover:bg-ink-50"
                }`}
              >
                {t("dayCount", { count: d })}
              </button>
            ))}
          </div>
        </div>
      </div>

      <DecisionSummary
        recs={recs}
        attention={attention}
        attentionOnly={attentionOnly}
        onShowAttention={() => setAttentionOnly((v) => !v)}
      />

      {attentionOnly && attention > 0 && (
        <div className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          <span className="text-[12px] text-amber-900">{t("attentionHint")}</span>
          <Button size="sm" onClick={openMostUrgent}>
            {t("openMostUrgent")}
          </Button>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
          {error}
        </div>
      )}

      <Card className="min-h-0 max-h-full overflow-hidden p-0">
        {loading ? (
          <div className="flex h-full items-center justify-center gap-2 text-[12.5px] text-ink-400">
            <Spinner /> {tc("loading")}
          </div>
        ) : rows.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[12.5px] text-ink-400">
            {t("empty")}
          </div>
        ) : (
          <PricingCalendar
            rows={rows}
            dates={dates}
            bookingsByRoomType={bookingsByRoomType}
            expanded={expanded}
            onToggleExpand={(id) =>
              setExpanded((prev) => {
                const next = new Set(prev);
                if (next.has(id)) next.delete(id);
                else next.add(id);
                return next;
              })
            }
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
            onSelectBooking={() => {
              /* booking detail is a later step; the bar already carries a tooltip */
            }}
            attentionOnly={attentionOnly}
          />
        )}
      </Card>

      <RecommendationDrawer
        recommendation={selected}
        peers={peers}
        onClose={() => setSelected(null)}
        onChanged={load}
      />
    </div>
  );
}
