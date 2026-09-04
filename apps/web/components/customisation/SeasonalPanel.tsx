"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Chip } from "@/components/Chip";
import { Spinner } from "@/components/Spinner";
import { selectClass } from "@/lib/formControls";
import { api } from "@/lib/api";
import type { RateBand, SeasonDef } from "@/lib/types";

/** Month abbreviations from Intl, so they follow the locale. */
const monthName = (locale: string, month: number) =>
  new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-US", { month: "short" }).format(
    new Date(2026, month - 1, 1),
  );

const QUARTER_STARTS = [1, 4, 7, 10];

/**
 * Seasons as an ordered list of START months.
 *
 * Each season runs from its start up to the month before the next one begins,
 * wrapping past December. Expressed this way a gap is UNREPRESENTABLE — there
 * is nowhere for one to live — which is the partition rule from the design
 * enforced by the shape of the control rather than by validation after the
 * fact. The server still checks, because a UI guard is a convenience and this
 * is an invariant.
 */
function monthsFromStarts(starts: number[]): number[][] {
  const ordered = [...starts];
  return ordered.map((start, i) => {
    const next = ordered[(i + 1) % ordered.length];
    const months: number[] = [];
    let m = start;
    // `next === start` only when there is a single season, which covers the
    // whole year; the length guard below stops the walk either way.
    do {
      months.push(m);
      m = (m % 12) + 1;
    } while (m !== next && months.length < 12);
    return months;
  });
}

/**
 * Re-derive the whole calendar from each season's start month.
 *
 * Seasons are SORTED by start before the runs are walked, and each season
 * keeps its own start through the sort. Without that, moving one season's
 * start past another's leaves the array in an order the walk cannot use --
 * measured at 24 month-slots across 12 months, i.e. every season overlapping
 * its neighbour. The server rejects that, but the operator only did something
 * reasonable, so the control should not be able to produce it.
 */
function repartition(seasons: SeasonDef[], starts: number[]): SeasonDef[] {
  const paired = seasons
    .map((season, i) => ({ season, start: starts[i] }))
    .sort((a, b) => a.start - b.start);
  const months = monthsFromStarts(paired.map((p) => p.start));
  return paired.map((p, i) => ({ ...p.season, months: months[i] }));
}

export function SeasonalPanel() {
  const t = useTranslations("rateBook");
  const tc = useTranslations("common");
  const tv = useTranslations("vocab");
  const locale = useLocale();

  const [seasons, setSeasons] = useState<SeasonDef[]>([]);
  const [bands, setBands] = useState<RateBand[]>([]);
  const [granularity, setGranularity] = useState<"month" | "quarter">("month");
  const [drafts, setDrafts] = useState<Record<number, { min: string; base: string; max: string }>>(
    {},
  );
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, b] = await Promise.all([api.seasons(), api.rateBook()]);
      setSeasons(s.seasons);
      setBands(b);
      setDrafts(
        Object.fromEntries(
          b.map((band) => [
            band.id,
            {
              min: String(Math.round(band.min_net_rate)),
              base: String(Math.round(band.base_net_rate)),
              // An absent ceiling stays an EMPTY field, never a 0 — a zero
              // ceiling would clamp every recommendation to nothing.
              max: band.max_net_rate === null ? "" : String(Math.round(band.max_net_rate)),
            },
          ]),
        ),
      );
    } catch (e: any) {
      setError(e?.message ?? tc("apiUnreachable"));
    } finally {
      setLoading(false);
    }
  }, [tc]);

  useEffect(() => {
    load();
  }, [load]);

  const bandsBySeason = useMemo(() => {
    const out: Record<string, RateBand[]> = {};
    for (const band of bands) (out[band.season_key] ||= []).push(band);
    return out;
  }, [bands]);

  const saveCalendar = useCallback(
    async (next: SeasonDef[]) => {
      setError(null);
      setMessage(null);
      try {
        setSeasons((await api.saveSeasons(next)).seasons);
        setMessage(t("calendarSaved"));
        await load();
      } catch (e: any) {
        // The server's message names the offending months, which is exactly
        // what the operator needs to fix it.
        setError(e?.message ?? tc("unknownError"));
      }
    },
    [load, t, tc],
  );

  const moveStart = (index: number, month: number) => {
    const starts = seasons.map((s) => s.months[0]);
    starts[index] = month;
    if (new Set(starts).size !== starts.length) {
      setError(t("duplicateStart"));
      return;
    }
    saveCalendar(repartition(seasons, starts));
  };

  const addSeason = () => {
    // Split the LONGEST season, so a new one always has somewhere to come
    // from. Adding a floating range instead would open a gap.
    const longest = seasons.reduce((a, b) => (b.months.length > a.months.length ? b : a));
    if (longest.months.length < 2) {
      setError(t("cannotSplit"));
      return;
    }
    // Split at the midpoint of the longest season, so the new one always has
    // months to take. Adding a floating range instead would open a gap.
    const at = longest.months[Math.floor(longest.months.length / 2)];
    const next = [...seasons, { key: `season_${Date.now().toString(36)}`, label: t("newSeason"), months: [at] }];
    saveCalendar(repartition(next, next.map((s) => s.months[0])));
  };

  const removeSeason = (key: string) => {
    if (seasons.length < 2) {
      setError(t("cannotRemoveLast"));
      return;
    }
    // The removed season's months are absorbed by whichever season now
    // precedes them -- the walk closes the gap automatically.
    const kept = seasons.filter((s) => s.key !== key);
    saveCalendar(repartition(kept, kept.map((s) => s.months[0])));
  };

  const saveBand = async (band: RateBand) => {
    const draft = drafts[band.id];
    setError(null);
    setMessage(null);
    try {
      await api.updateRateBand(band.id, {
        min_net_rate: Number(draft.min),
        base_net_rate: Number(draft.base),
        // Empty means NO CEILING, not zero.
        max_net_rate: draft.max.trim() === "" ? null : Number(draft.max),
      });
      setMessage(t("saved"));
      await load();
    } catch (e: any) {
      setError(e?.message ?? tc("unknownError"));
    }
  };

  const resetBook = async () => {
    setError(null);
    setMessage(null);
    try {
      await api.resetRateBook();
      setMessage(t("resetDone"));
      await load();
    } catch (e: any) {
      setError(e?.message ?? tc("unknownError"));
    }
  };

  const editedCount = bands.filter((b) => b.source !== "CLIENT_VALIDATED").length;

  if (loading) return <Spinner label={t("loading")} />;

  const startOptions = granularity === "quarter" ? QUARTER_STARTS : Array.from({ length: 12 }, (_, i) => i + 1);

  return (
    <div className="max-w-[1100px] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[62ch] text-[12px] leading-snug text-ink-500">{t("subtitleLong")}</p>
        <div className="flex items-center gap-2">
          <Chip tone={editedCount ? "warn" : "up"}>
            {editedCount ? t("editedCount", { count: editedCount }) : t("clientValidated")}
          </Chip>
          <Button variant="secondary" onClick={resetBook} disabled={!editedCount} title={editedCount ? t("resetEnabled", { count: bands.length }) : t("resetDisabled")}>
            {t("reset")}
          </Button>
        </div>
        <label className="flex items-center gap-2 text-[11.5px] text-ink-600">
          {t("granularity")}
          <select
            className={selectClass}
            value={granularity}
            onChange={(e) => setGranularity(e.target.value as "month" | "quarter")}
          >
            <option value="month">{t("byMonths")}</option>
            <option value="quarter">{t("byQuarters")}</option>
          </select>
        </label>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11.5px] text-rose-700">
          {error}
        </div>
      )}
      {message && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11.5px] text-emerald-700">
          {message}
        </div>
      )}

      {seasons.length === 0 && (
        <p className="text-[12px] text-ink-400">{t("empty")}</p>
      )}

      {seasons.map((season, index) => (
        <Card key={season.key} className="p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-[13.5px] font-semibold text-ink-900">
                {tv.has(`seasonsShort.${season.key}`)
                  ? tv(`seasonsShort.${season.key}`)
                  : season.label}
              </span>
              <Chip tone="neutral">
                {season.months.map((m) => monthName(locale, m)).join(" · ")}
              </Chip>
            </div>
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 text-[11.5px] text-ink-600">
                {t("startsIn")}
                <select
                  className={selectClass}
                  value={season.months[0]}
                  onChange={(e) => moveStart(index, Number(e.target.value))}
                >
                  {startOptions.map((m) => (
                    <option key={m} value={m}>
                      {monthName(locale, m)}
                    </option>
                  ))}
                </select>
              </label>
              <Button variant="secondary" onClick={() => removeSeason(season.key)}>{t("removeSeason")}</Button>
            </div>
          </div>

          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-ink-200 text-[11px] uppercase tracking-wide text-ink-500">
                <th className="py-2 text-left font-semibold">{tc("roomCategory")}</th>
                <th className="py-2 text-right font-semibold">{t("minNet")}</th>
                <th className="py-2 text-right font-semibold">{t("baseNet")}</th>
                <th className="py-2 text-right font-semibold">{t("maxOptional")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(bandsBySeason[season.key] ?? []).map((band) => {
                const draft = drafts[band.id];
                if (!draft) return null;
                return (
                  <tr key={band.id} className="border-b border-ink-100">
                    <td className="py-2 pr-3 text-ink-800">
                      <div>{tv(`roomCategories.${band.room_category}`)}</div>
                      {/* Provenance per band: validated client fact and an
                          operator edit must never look the same. */}
                      <div className="text-[10.5px] text-ink-400">
                        {band.source === "CLIENT_VALIDATED"
                          ? t("sourceClient")
                          : t("sourceEdited")}
                      </div>
                    </td>
                    {(["min", "base", "max"] as const).map((field) => (
                      <td key={field} className="py-2 pl-3">
                        <Input
                          inputMode="numeric"
                          className="tnum text-right"
                          placeholder={field === "max" ? t("noCeiling") : t("required")}
                          value={draft[field]}
                          onChange={(e) =>
                            setDrafts((d) => ({
                              ...d,
                              [band.id]: { ...d[band.id], [field]: e.target.value.replace(/[^\d]/g, "") },
                            }))
                          }
                        />
                      </td>
                    ))}
                    <td className="py-2 pl-3 text-right">
                      <Button variant="secondary" onClick={() => saveBand(band)}>{tc("save")}</Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {(bandsBySeason[season.key] ?? []).some((b) => b.max_net_rate === null) && (
            <p className="mt-2 text-[11px] text-ink-400">{t("noCeilingNote")}</p>
          )}
        </Card>
      ))}

      <button
        onClick={addSeason}
        className="w-full rounded-xl border border-dashed border-ink-300 py-3 text-[13px] text-ink-500
          transition-colors hover:border-brand-400 hover:text-brand-700 focus:outline-none
          focus-visible:ring-2 focus-visible:ring-brand-500"
      >
        + {t("addSeason")}
      </button>

      <p className="text-[11px] text-ink-400">{t("bandCount", { count: bands.length })}</p>
    </div>
  );
}
