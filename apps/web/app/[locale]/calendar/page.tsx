"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { addDaysISO, dateRange, nightsBetween, todayISO } from "@/lib/dates";
import { attentionScore, needsAttention } from "@/lib/attention";
import { PricingCalendar } from "@/components/calendar/PricingCalendar";
import { CalendarLegend } from "@/components/calendar/CalendarLegend";
import { buildColumns, buildRows, type Column, type Granularity } from "@/lib/calendarModel";
import { RecommendationDrawer } from "@/components/RecommendationDrawer";
import { Button, Card, Spinner } from "@/components/ui";
import type { FormatLocale } from "@/lib/format";
import type { Booking, Recommendation } from "@/lib/types";

/**
 * Ranges an owner actually thinks in, and the resolution each deserves.
 *
 * Past a month, per-night columns are a wall rather than information — 180
 * columns are illegible and nobody prices a specific Tuesday six months out.
 * Weeks answer the question being asked at that horizon instead.
 */
const RANGES = [
  { key: "twoWeeks", days: 14 },
  { key: "oneMonth", days: 30 },
  { key: "threeMonths", days: 91 },
  { key: "sixMonths", days: 182 },
] as const;

/** Longest span that still reads as day columns. Beyond it, weeks. */
const DAY_COLUMN_LIMIT = 35;

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

  // START and END are both state. A preset sets them together; the date inputs
  // set either one directly and flip the picker to "custom" — deriving `end`
  // from a preset would make an arbitrary range unrepresentable.
  const [start, setStart] = useState(todayISO);
  const [end, setEnd] = useState(() => addDaysISO(todayISO(), 29));
  const [rangeKey, setRangeKey] = useState<string>("oneMonth");
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [selected, setSelected] = useState<Recommendation | null>(null);
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const locale = useLocale() as FormatLocale;

  // Span drives resolution, whatever produced it. A custom eight-week range
  // gets weeks for the same reason the three-month preset does.
  const days = Math.max(1, nightsBetween(start, end) + 1);
  const granularity: Granularity = days > DAY_COLUMN_LIMIT ? "week" : "day";

  const applyPreset = (key: string) => {
    const preset = RANGES.find((r) => r.key === key);
    setRangeKey(key);
    if (preset) setEnd(addDaysISO(start, preset.days - 1));
  };

  /** Shift the whole window, keeping its length. */
  const shift = (by: number) => {
    setStart(addDaysISO(start, by));
    setEnd(addDaysISO(end, by));
  };
  // Every day in range: booking bars keep daily resolution at every zoom, which
  // is the one place a spanning tile is genuinely right.
  const dates = useMemo(() => dateRange(start, end), [start, end]);
  const columns = useMemo(
    () => buildColumns(start, end, granularity, locale),
    [start, end, granularity, locale],
  );

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

  const rows = useMemo(
    () => buildRows(recs, granularity, locale, columns),
    [recs, granularity, locale, columns],
  );

  /** Clicking a week zooms into it, since a week has no single price to explain. */
  const drillDown = (column: Column) => {
    setStart(column.startISO);
    setEnd(addDaysISO(column.startISO, 13));
    setRangeKey("twoWeeks");
  };

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

      <Card className="flex min-h-0 max-h-full flex-col overflow-hidden p-0">
        {/* The calendar's own toolbar, on the calendar — not in the page
            corner. These controls move the grid below them and nothing else. */}
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-ink-100 px-3 py-2">
          <Button
            size="sm"
            onClick={() => {
              setStart(todayISO());
              setEnd(addDaysISO(todayISO(), days - 1));
            }}
          >
            {t("today")}
          </Button>
          <div className="flex items-center rounded-lg border border-ink-200">
            <button
              onClick={() => shift(-days)}
              aria-label={t("previousPeriod")}
              className="px-2 py-1 text-[13px] text-ink-600 hover:bg-ink-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              ←
            </button>
            <button
              onClick={() => shift(days)}
              aria-label={t("nextPeriod")}
              className="border-l border-ink-200 px-2 py-1 text-[13px] text-ink-600 hover:bg-ink-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              →
            </button>
          </div>

          <label className="flex items-center gap-1.5">
            <span className="sr-only">{t("rangeLabel")}</span>
            <select
              value={rangeKey}
              onChange={(e) => applyPreset(e.target.value)}
              className="rounded-lg border border-ink-200 bg-white px-2 py-1 text-[12.5px] text-ink-700
                focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            >
              {RANGES.map((r) => (
                <option key={r.key} value={r.key}>
                  {t(`ranges.${r.key}`)}
                </option>
              ))}
              <option value="custom">{t("ranges.custom")}</option>
            </select>
          </label>

          {/* Native date inputs: they localise their own calendar and keyboard
              behaviour for free, which a hand-rolled picker would have to earn. */}
          <div className="flex items-center gap-1">
            <input
              type="date"
              aria-label={t("from")}
              value={start}
              max={end}
              onChange={(e) => {
                if (!e.target.value) return;
                setStart(e.target.value);
                setRangeKey("custom");
              }}
              className="rounded-lg border border-ink-200 px-2 py-1 text-[12px] text-ink-700
                focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
            <span className="text-[11px] text-ink-400" aria-hidden>
              →
            </span>
            <input
              type="date"
              aria-label={t("to")}
              value={end}
              min={start}
              onChange={(e) => {
                if (!e.target.value) return;
                setEnd(e.target.value);
                setRangeKey("custom");
              }}
              className="rounded-lg border border-ink-200 px-2 py-1 text-[12px] text-ink-700
                focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
          </div>

          {granularity === "week" && (
            <span className="text-[11px] text-ink-400">{t("weeklyNote")}</span>
          )}

          {/* Pushed right so it reads as a key to the grid rather than as
              another control competing with the ones on the left. */}
          <div className="ml-auto">
            <CalendarLegend />
          </div>
        </div>

        <div className="min-h-0 flex-1">
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
              columns={columns}
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
                /* booking detail is a later step; the bar carries a tooltip */
              }}
              onDrillDown={drillDown}
              attentionOnly={attentionOnly}
            />
          )}
        </div>
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
