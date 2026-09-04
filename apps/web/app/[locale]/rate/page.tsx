"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { TrendingUp, TrendingDown, CircleAlert } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Empty } from "@/components/Empty";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
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
/** The range the page opens on, before the season is known. The server
 *  shortens it if it would cross a boundary. */
const DEFAULT_NIGHTS = 7;

export default function RatePage() {
  const t = useTranslations("rate");
  const tc = useTranslations("common");
  const tv = useTranslations("vocab");

  const [startDate, setStartDate] = useState(todayISO);
  /** The end the OPERATOR asked for, or null to let the server pick one inside
   *  the season. Null on first load and whenever the start moves, because the
   *  boundary is not known here — asking for it first left a window where an
   *  unclamped request was already in flight, and on the last day of a season
   *  that request crosses a boundary and comes back 422. */
  const [requestedEnd, setRequestedEnd] = useState<string | null>(null);
  const [endInput, setEndInput] = useState(() => addDaysISO(todayISO(), 6));
  const [data, setData] = useState<RateTiles | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<RangeSelection | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await api.rateTiles(startDate, requestedEnd, DEFAULT_NIGHTS);
      setData(next);
      // The server may have shortened the range at the season boundary; the
      // input shows what was actually priced, not what was asked for.
      setEndInput(next.end_date);
    } catch (e: any) {
      // An empty result and an unreachable API must not render alike: one of
      // them means "nothing is priced", which is a claim, not a blank screen.
      setError(e?.message ?? tc("apiUnreachable"));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [startDate, requestedEnd, tc]);

  useEffect(() => {
    load();
  }, [load]);

  const nights = data?.nights ?? 0;
  const seasonEnd = data?.season.end ?? null;

  return (
    <div className="h-full overflow-y-auto px-7 py-6 space-y-5 max-w-[1500px]">
      <PageHeader title={t("title")} subtitle={t("subtitle")} />

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <div className="mb-1 text-[11px] font-medium text-ink-500">{t("from")}</div>
            <Input
              type="date"
              value={startDate}
              onChange={(e) => {
                if (!e.target.value) return;
                setStartDate(e.target.value);
                // A new start may sit in a different season, so hand the end
                // back to the server rather than carrying over one that may
                // now cross a boundary.
                setRequestedEnd(null);
              }}
            />
          </label>
          <div aria-hidden className="pb-2 text-ink-300">
            →
          </div>
          <label className="block">
            <div className="mb-1 text-[11px] font-medium text-ink-500">{t("to")}</div>
            <Input
              type="date"
              value={endInput}
              min={startDate}
              // Capped at the season boundary rather than validated after the
              // fact, so the control cannot offer a range the server refuses.
              max={seasonEnd ?? undefined}
              onChange={(e) => {
                if (!e.target.value) return;
                setEndInput(e.target.value);
                setRequestedEnd(e.target.value);
              }}
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
        {seasonEnd && endInput === seasonEnd && (
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
        <TileGrid data={data} onOpen={(tile) => setSelection({
          roomTypeId: tile.room_type_id,
          startDate: data.start_date,
          endDate: data.end_date,
        })} />
      )}

      <RangeDrawer
        selection={selection}
        onClose={() => setSelection(null)}
        onChanged={load}
      />
    </div>
  );
}

/**
 * The tile grid is a comparison surface — regular and calm, on purpose. The
 * one exception is data-driven, not decorative: whichever tier has the most
 * unpriced nights is the one that actually needs the operator's attention
 * right now, so it leads the grid and carries more visual weight than its
 * neighbors. Nothing is emphasized when every tier is fully priced.
 */
function TileGrid({
  data,
  onOpen,
}: {
  data: RateTiles;
  onOpen: (tile: RateTile) => void;
}) {
  const mostUrgent = data.tiles.reduce<RateTile | null>((worst, tile) => {
    if (tile.unpriced_nights <= 0) return worst;
    if (!worst || tile.unpriced_nights > worst.unpriced_nights) return tile;
    return worst;
  }, null);

  const rest = mostUrgent
    ? data.tiles.filter((t) => t.room_type_id !== mostUrgent.room_type_id)
    : data.tiles;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {mostUrgent && (
        <TileCard
          tile={mostUrgent}
          emphasized
          onOpen={() => onOpen(mostUrgent)}
        />
      )}
      {rest.map((tile) => (
        <TileCard key={tile.room_type_id} tile={tile} onOpen={() => onOpen(tile)} />
      ))}
    </div>
  );
}

function TileCard({
  tile,
  onOpen,
  emphasized = false,
}: {
  tile: RateTile;
  onOpen: () => void;
  emphasized?: boolean;
}) {
  const t = useTranslations("rate");
  const tv = useTranslations("vocab");
  const { formatVND, formatAdjPct } = useFormat();
  const up = tile.change_pct > 0.5;
  const down = tile.change_pct < -0.5;

  return (
    <button
      onClick={onOpen}
      className={`rounded-xl border p-4 text-left transition-colors focus:outline-none
        focus-visible:ring-2 focus-visible:ring-brand-500 ${
          emphasized
            ? "sm:col-span-2 border-amber-200 bg-amber-50/40 hover:bg-amber-50"
            : "border-ink-200 bg-white hover:border-brand-300 hover:bg-brand-50/40"
        }`}
    >
      <div className="text-[13.5px] font-semibold text-ink-900">
        {tv(`roomCategories.${tile.room_category}`)}
      </div>

      <div className="mt-3 text-[11px] text-ink-400">{t("averageSuggested")}</div>
      <div className="tnum text-[24px] font-bold leading-tight text-brand-700">
        {formatVND(tile.average_recommended_net_rate)}
      </div>
      <div
        className={`flex items-center gap-1 tnum text-[12px] font-medium ${
          up ? "text-emerald-600" : down ? "text-amber-600" : "text-ink-400"
        }`}
      >
        {up && <TrendingUp aria-hidden size={13} strokeWidth={2} />}
        {down && <TrendingDown aria-hidden size={13} strokeWidth={2} />}
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
        <div className="mt-1.5 flex items-center gap-1 text-[11px] text-amber-700">
          <CircleAlert aria-hidden size={12} strokeWidth={2} />
          {t("unpricedNights", { count: tile.unpriced_nights })}
        </div>
      )}
    </button>
  );
}
