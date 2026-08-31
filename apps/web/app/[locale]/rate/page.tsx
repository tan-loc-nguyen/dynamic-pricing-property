"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Card, Empty, PageHeader, Spinner, inputClass } from "@/components/ui";
import { RangeDrawer, type RangeSelection } from "@/components/RangeDrawer";
import { api } from "@/lib/api";
import { addDaysISO, todayISO } from "@/lib/format";
import { useFormat } from "@/lib/useFormat";
import type { RateTile, RateTiles } from "@/lib/types";

/**
 * Price a DATE RANGE, not a calendar.
 *
 * The old month grid asked the operator to scan 91 cells and work out which
 * ones needed attention. This asks the opposite question -- "these nights,
 * this tier, what should I charge?" -- and answers it in one number per tier.
 *
 * The range may not cross a season, because one accepted price cannot sit
 * inside two different validated bands. The `to` field is capped at the
 * season's last day rather than left free and rejected on submit: a control
 * that lets you choose something it will refuse is a worse answer than one
 * that does not offer it.
 */
export default function RatePage() {
  const t = useTranslations("rate");
  const tc = useTranslations("common");
  const tv = useTranslations("vocab");
  const { formatVND, formatAdjPct } = useFormat();

  const [startDate, setStartDate] = useState(todayISO);
  const [endDate, setEndDate] = useState(() => addDaysISO(todayISO(), 6));
  const [seasonEnd, setSeasonEnd] = useState<string | null>(null);
  const [data, setData] = useState<RateTiles | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<RangeSelection | null>(null);

  // The season containing the START date decides how far the range may run.
  useEffect(() => {
    let alive = true;
    api
      .season(startDate)
      .then((s) => {
        if (!alive) return;
        setSeasonEnd(s.end);
        setEndDate((current) =>
          current < startDate ? startDate : current > s.end ? s.end : current,
        );
      })
      .catch(() => alive && setSeasonEnd(null));
    return () => {
      alive = false;
    };
  }, [startDate]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.rateTiles(startDate, endDate));
    } catch (e: any) {
      // An empty result and an unreachable API must not render alike: one of
      // them means "nothing is priced", which is a claim, not a blank screen.
      setError(e?.message ?? tc("apiUnreachable"));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, tc]);

  useEffect(() => {
    load();
  }, [load]);

  const nights = data?.nights ?? 0;

  return (
    <div className="h-full overflow-y-auto px-7 py-6 space-y-5 max-w-[1500px]">
      <PageHeader title={t("title")} subtitle={t("subtitle")} />

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <div className="mb-1 text-[11px] font-medium text-ink-500">{t("from")}</div>
            <input
              type="date"
              className={inputClass}
              value={startDate}
              onChange={(e) => e.target.value && setStartDate(e.target.value)}
            />
          </label>
          <div aria-hidden className="pb-2 text-ink-300">
            →
          </div>
          <label className="block">
            <div className="mb-1 text-[11px] font-medium text-ink-500">{t("to")}</div>
            <input
              type="date"
              className={inputClass}
              value={endDate}
              min={startDate}
              // Capped at the season boundary rather than validated after the
              // fact, so the control cannot offer a range the server refuses.
              max={seasonEnd ?? undefined}
              onChange={(e) => e.target.value && setEndDate(e.target.value)}
            />
          </label>
          {data && (
            <div className="pb-1.5 text-[11.5px] text-ink-500">
              {t("nightsSelected", { nights })}
              {" · "}
              {tv(`seasonsShort.${data.season.key}`)}
            </div>
          )}
        </div>
        {seasonEnd && endDate === seasonEnd && (
          <p className="mt-2 text-[11px] text-ink-400">{t("seasonBoundary")}</p>
        )}
      </Card>

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] text-amber-900">
          {error}
        </div>
      )}

      {loading ? (
        <Spinner label={tc("loading")} />
      ) : !data || data.tiles.length === 0 ? (
        <Empty title={t("empty")} hint={t("emptyHint")} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data.tiles.map((tile) => (
            <TileCard
              key={tile.room_type_id}
              tile={tile}
              onOpen={() =>
                setSelection({
                  roomTypeId: tile.room_type_id,
                  startDate: data.start_date,
                  endDate: data.end_date,
                })
              }
            />
          ))}
        </div>
      )}

      <RangeDrawer
        selection={selection}
        onClose={() => setSelection(null)}
        onChanged={load}
      />
    </div>
  );

  function TileCard({ tile, onOpen }: { tile: RateTile; onOpen: () => void }) {
    return (
      <button
        onClick={onOpen}
        className="rounded-xl border border-ink-200 bg-white p-4 text-left transition-colors
          hover:border-brand-300 hover:bg-brand-50/40 focus:outline-none
          focus-visible:ring-2 focus-visible:ring-brand-500"
      >
        <div className="text-[13.5px] font-semibold text-ink-900">
          {tv(`roomCategories.${tile.room_category}`)}
        </div>

        <div className="mt-3 text-[11px] uppercase tracking-wide text-ink-400">
          {t("averageSuggested")}
        </div>
        <div className="tnum text-[24px] font-bold leading-tight text-brand-700">
          {formatVND(tile.average_recommended_net_rate)}
        </div>
        <div
          className={`tnum text-[12px] font-medium ${
            tile.change_pct > 0.5
              ? "text-emerald-600"
              : tile.change_pct < -0.5
                ? "text-amber-600"
                : "text-ink-400"
          }`}
        >
          {formatAdjPct(tile.change_pct)}
        </div>

        <div className="mt-3 border-t border-ink-100 pt-2.5 text-[11.5px] text-ink-600">
          {/* Units with at least one free night in the range -- NOT unit-nights.
              When bookings cannot be attributed to a unit the count is a
              provable floor, and it says so rather than implying precision. */}
          {tile.availability_is_exact
            ? t("inventory", { units: tile.available_units, total: tile.units_total })
            : t("inventoryAtLeast", {
                units: tile.available_units,
                total: tile.units_total,
              })}
        </div>
        {tile.unpriced_nights > 0 && (
          <div className="mt-1.5 text-[11px] text-amber-700">
            {t("unpricedNights", { count: tile.unpriced_nights })}
          </div>
        )}
      </button>
    );
  }
}
