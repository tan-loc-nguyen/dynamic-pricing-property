"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Dialog, Tabs } from "radix-ui";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { useFormat } from "@/lib/useFormat";
import { Button } from "@/components/ui/button";
import type { MarketObservation, RangeDetail } from "@/lib/types";
import { RangeScopeBody } from "./RangeScopeBody";
import { NightScopeBody } from "./NightScopeBody";

/**
 * The answer to "what should I charge for this tier over these nights?", in
 * the order an owner asks it: what to do -> is it inside my range -> how is it
 * selling -> why did the price move -> what does the market say -> decide.
 *
 * A RANGE, not a night. Accepting writes one price to every night in the
 * selection, so the per-night strip under the pace curve is load-bearing: it
 * is the only place a range whose nights disagree with each other becomes
 * visible before the operator commits one number to all of them.
 */
export interface RangeSelection {
  roomTypeId: number;
  startDate: string;
  endDate: string;
}

export function RangeDrawer({
  selection,
  onClose,
  onChanged,
}: {
  selection: RangeSelection | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const t = useTranslations("drawer");
  const tv = useTranslations("vocab");
  const tc = useTranslations("common");
  const { formatLongDate } = useFormat();

  const [detail, setDetail] = useState<RangeDetail | null>(null);
  const [observations, setObservations] = useState<MarketObservation[]>([]);
  const [busy, setBusy] = useState(false);
  const [overriding, setOverriding] = useState(false);
  const [overrideRate, setOverrideRate] = useState("");
  const [reasonCode, setReasonCode] = useState("my_judgment");
  const [error, setError] = useState<string | null>(null);
  const [reasonCodes, setReasonCodes] = useState<string[]>(["my_judgment"]);
  const [scope, setScope] = useState<"range" | "night">("range");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  useEffect(() => {
    api
      .status()
      .then((s) => setReasonCodes(s.override_reasons.map((r) => r.code)))
      .catch(() => {
        /* keep the safe default rather than blocking the override form */
      });
  }, []);

  const key = selection
    ? `${selection.roomTypeId}:${selection.startDate}:${selection.endDate}`
    : null;

  useEffect(() => {
    if (!selection) return;
    setDetail(null);
    setObservations([]);
    setOverriding(false);
    setError(null);
    setScope("range");
    setSelectedDate(null);
    let alive = true;
    api
      .rateRange(selection.roomTypeId, selection.startDate, selection.endDate)
      .then((d) => {
        if (!alive) return;
        setDetail(d);
        setOverrideRate(String(Math.round(d.average_recommended_net_rate)));
      })
      .catch((e) => alive && setError(e?.message ?? tc("unknownError")));
    // Real observed prices across the range, so the market band is a range
    // that actually exists rather than one inferred from an index number.
    api
      .observations({
        room_type_id: selection.roomTypeId,
        start_date: selection.startDate,
        end_date: selection.endDate,
      })
      .then((o) => alive && setObservations(o))
      .catch(() => {
        /* market context is optional; the rest of the drawer still works */
      });
    return () => {
      alive = false;
    };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const market = useMemo(() => {
    const prices = observations
      .map((o) => o.observed_price)
      .filter((p): p is number => typeof p === "number" && p > 0)
      .sort((a, b) => a - b);
    if (prices.length < 2) return null;
    return {
      low: prices[0],
      high: prices[prices.length - 1],
      median: prices[Math.floor(prices.length / 2)],
      count: prices.length,
    };
  }, [observations]);

  // The night scope always has a night. Defaulting to the first PRICED night
  // rather than the first night means opening the scope never lands on a state
  // with no action available.
  const night = useMemo(() => {
    if (!detail) return null;
    const wanted = detail.nightly.find((n) => n.stay_date === selectedDate);
    return wanted ?? detail.nightly.find((n) => n.priced) ?? detail.nightly[0] ?? null;
  }, [detail, selectedDate]);

  // A single night is the same thing in both scopes, so offering a choice
  // between them would be offering a choice that changes nothing.
  const canSwitchScope = (detail?.nights ?? 0) > 1;

  const act = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await fn();
        onChanged();
        onClose();
      } catch (e: any) {
        setError(e?.message ?? tc("unknownError"));
      } finally {
        setBusy(false);
      }
    },
    [onChanged, onClose, tc],
  );

  const open = selection !== null;
  // Every night failed to price. Accepting would write a number the engine
  // never calculated, so the action is withdrawn rather than left to fail.
  const allUnpriced = !!detail && detail.unpriced_nights >= detail.nights;

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Overlay className="fixed inset-0 z-40 bg-ink-900/20 backdrop-blur-[1px]" />
        <Dialog.Content
          className="fixed right-0 top-0 z-50 flex h-screen w-full max-w-[560px] flex-col bg-white shadow-2xl
            focus:outline-none"
          aria-describedby={undefined}
        >
          {detail ? (
            <>
              {/* ------------------------------------------------ header */}
              <header className="shrink-0 border-b border-ink-100 px-5 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Dialog.Title className="text-[15px] font-semibold text-ink-900">
                      {tv(`roomCategories.${detail.room_category}`)}
                    </Dialog.Title>
                    <p className="mt-0.5 text-[12px] text-ink-500">
                      {detail.nights === 1
                        ? formatLongDate(detail.start_date)
                        : t("rangeNights", {
                            from: formatLongDate(detail.start_date),
                            to: formatLongDate(detail.end_date),
                            nights: detail.nights,
                          })}
                      {detail.season?.key ? ` · ${tv(`seasonsShort.${detail.season.key}`)}` : ""}
                    </p>
                  </div>
                  <Dialog.Close asChild>
                    <button
                      className="rounded-lg px-2 py-1 text-[12px] text-ink-500 hover:bg-ink-100
                        focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                    >
                      {t("close")}
                    </button>
                  </Dialog.Close>
                </div>
              </header>

              <Tabs.Root
                value={scope}
                onValueChange={(v) => setScope(v as "range" | "night")}
                className="flex min-h-0 flex-1 flex-col"
              >
                {canSwitchScope && (
                  <Tabs.List
                    className="flex shrink-0 gap-1 border-b border-ink-100 px-5"
                    aria-label={t("paceTitle")}
                  >
                    <Tabs.Trigger
                      value="range"
                      className="-mb-px border-b-2 border-transparent px-3 py-2 text-[12.5px] text-ink-500
                        hover:text-ink-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500
                        data-[state=active]:border-brand-600 data-[state=active]:font-medium
                        data-[state=active]:text-brand-700"
                    >
                      {t("scopeRange")}
                    </Tabs.Trigger>
                    <Tabs.Trigger
                      value="night"
                      className="-mb-px border-b-2 border-transparent px-3 py-2 text-[12.5px] text-ink-500
                        hover:text-ink-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500
                        data-[state=active]:border-brand-600 data-[state=active]:font-medium
                        data-[state=active]:text-brand-700"
                    >
                      {t("scopeNight")}
                    </Tabs.Trigger>
                  </Tabs.List>
                )}

                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
                  {scope === "night" && night ? (
                    <NightScopeBody
                      detail={detail}
                      night={night}
                      market={market}
                      observations={observations}
                      onSelect={setSelectedDate}
                    />
                  ) : (
                    <RangeScopeBody
                      detail={detail}
                      market={market}
                      observations={observations}
                    />
                  )}
                </div>
              </Tabs.Root>

              {/* ------------------------------------- sticky actions */}
              <FooterActions
                detail={detail}
                scope={scope}
                night={night}
                busy={busy}
                error={error}
                allUnpriced={allUnpriced}
                overriding={overriding}
                setOverriding={setOverriding}
                overrideRate={overrideRate}
                setOverrideRate={setOverrideRate}
                reasonCode={reasonCode}
                setReasonCode={setReasonCode}
                reasonCodes={reasonCodes}
                act={act}
              />
            </>
          ) : (
            <div className="p-6 text-[12px] text-ink-400">
              {error ? (
                <span className="text-rose-700">{error}</span>
              ) : (
                tc("loading")
              )}
            </div>
          )}
        </Dialog.Content>
    </Dialog.Root>
  );
}

function FooterActions({
  detail,
  scope,
  night,
  busy,
  error,
  allUnpriced,
  overriding,
  setOverriding,
  overrideRate,
  setOverrideRate,
  reasonCode,
  setReasonCode,
  reasonCodes,
  act,
}: {
  detail: RangeDetail;
  scope: "range" | "night";
  night: RangeDetail["nightly"][number] | null;
  busy: boolean;
  error: string | null;
  allUnpriced: boolean;
  overriding: boolean;
  setOverriding: (v: boolean) => void;
  overrideRate: string;
  setOverrideRate: (v: string) => void;
  reasonCode: string;
  setReasonCode: (v: string) => void;
  reasonCodes: string[];
  act: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const t = useTranslations("drawer");
  const tv = useTranslations("vocab");
  const tc = useTranslations("common");
  const { formatVND, formatLongDate } = useFormat();

  const target =
    scope === "night" && night
      ? { start: night.stay_date, end: night.stay_date, rate: night.recommended_net_rate }
      : {
          start: detail.start_date,
          end: detail.end_date,
          rate: detail.average_recommended_net_rate,
        };

  // What the accept button will ACTUALLY write. Unpriced nights get no decision
  // at all, so a button naming the selected span would promise more than the
  // server delivers. Phase 8 subtracts preserved hand-tuned nights from this
  // same figure.
  const nightsToWrite =
    scope === "night" ? 1 : detail.nights - detail.unpriced_nights;

  // On an unpriced night in the night scope, the engine calculated nothing to
  // accept -- the range's `allUnpriced` withdrawal, applied to the one night.
  const nightUnpriced = scope === "night" && !!night && !night.priced;

  return (
    <footer className="shrink-0 border-t border-ink-100 bg-white px-5 py-3">
      {error && (
        <div className="mb-2 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[11.5px] text-rose-700">
          {error}
        </div>
      )}
      {/* Some nights priced, some not. Accepting still works and the
          server skips the failures -- but silently covering fewer
          nights than the operator selected is exactly the kind of
          partial success that has to be said out loud. */}
      {scope === "range" && !allUnpriced && detail.unpriced_nights > 0 && (
        <div className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11.5px] text-amber-800">
          {t("someUnpriced", { count: detail.unpriced_nights })}
        </div>
      )}
      {overriding ? (
        <div className="space-y-2">
          <label className="block text-[11.5px] text-ink-600">
            {t("yourNetRate")}
            <input
              autoFocus
              inputMode="numeric"
              value={overrideRate}
              onChange={(e) => setOverrideRate(e.target.value.replace(/[^\d]/g, ""))}
              className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 tnum text-[14px]
                focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
          </label>
          <label className="block text-[11.5px] text-ink-600">
            {t("reason")}
            <select
              value={reasonCode}
              onChange={(e) => setReasonCode(e.target.value)}
              className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-[12.5px]
                focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            >
              {/* From the SERVER's whitelist, not a copy of it. */}
              {reasonCodes.map((code) => (
                <option key={code} value={code}>
                  {tv(`overrideReasons.${code}`)}
                </option>
              ))}
            </select>
          </label>
          <div className="flex gap-2">
            <Button
              variant="default"
              disabled={busy || !overrideRate}
              onClick={() =>
                act(() =>
                  api.overrideRange(
                    detail.room_type_id,
                    target.start,
                    target.end,
                    Number(overrideRate),
                    reasonCode,
                  ),
                )
              }
            >
              {tc("save")}
            </Button>
            <Button variant="secondary" onClick={() => setOverriding(false)} disabled={busy}>
              {tc("cancel")}
            </Button>
          </div>
        </div>
      ) : allUnpriced || nightUnpriced ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] text-amber-800">
          {t("unpriced")}
        </div>
      ) : (
        <div className="flex gap-2">
          <Button
            variant="default"
            className="flex-1"
            disabled={busy}
            onClick={() =>
              act(() =>
                api.acceptRange(detail.room_type_id, target.start, target.end, true),
              )
            }
          >
            {scope === "night" && night
              ? t("acceptForNight", {
                  rate: formatVND(night.recommended_net_rate),
                  date: formatLongDate(night.stay_date),
                })
              : t("acceptForRange", {
                  rate: formatVND(target.rate),
                  nights: nightsToWrite,
                })}
          </Button>
          <Button variant="secondary" onClick={() => setOverriding(true)} disabled={busy}>
            {t("adjust")}
          </Button>
        </div>
      )}
    </footer>
  );
}
