"use client";

import { useTranslations } from "next-intl";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Card, Chip, Field, PageHeader, Spinner, inputClass } from "@/components/ui";
import { api } from "@/lib/api";

import { useFormat } from "@/lib/useFormat";
import { useAdjustmentText, useBandLabel } from "@/lib/adjustments";
import type { PricingConfig, Preview } from "@/lib/types";

const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

/** Immutable deep-set by path, so React sees a new object every edit. */
function setPath(obj: any, path: (string | number)[], value: any): any {
  if (path.length === 0) return value;
  const [head, ...rest] = path;
  const clone = Array.isArray(obj) ? [...obj] : { ...obj };
  clone[head as any] = setPath(clone[head as any] ?? {}, rest, value);
  return clone;
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-5">
      <div className="mb-4">
        <h2 className="text-[14px] font-semibold text-ink-900">{title}</h2>
        <p className="text-[12px] text-ink-500 mt-0.5 leading-snug">{description}</p>
      </div>
      {children}
    </Card>
  );
}

function NumberInput({
  value,
  onChange,
  step = 0.5,
  suffix,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  step?: number;
  suffix?: string;
}) {
  return (
    <div className="h-full overflow-y-auto relative">
      <input
        type="number"
        step={step}
        className={`${inputClass} tnum ${suffix ? "pr-7" : ""}`}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
      {suffix && (
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] text-ink-400">
          {suffix}
        </span>
      )}
    </div>
  );
}

/** Threshold + percentage-point adjustment band editor. */
function BandEditor({
  bands,
  section,
  thresholdKey,
  thresholdLabel,
  thresholdStep = 0.01,
  onChange,
}: {
  bands: any[];
  section: string;
  thresholdKey: string;
  thresholdLabel: string;
  thresholdStep?: number;
  onChange: (bands: any[]) => void;
}) {
  const t = useTranslations("settings");
  const bandLabel = useBandLabel();
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_130px_130px] gap-2 text-[11px] font-medium text-ink-400 px-1">
        <span>{t("band")}</span>
        <span>{thresholdLabel}</span>
        <span>{t("adjustment")}</span>
      </div>
      {bands.map((band, i) => (
        <div key={i} className="grid grid-cols-[1fr_130px_130px] gap-2 items-center">
          <input
            className={inputClass}
            // A shipped band is named by its KEY, so it reads in the operator's
            // language here exactly as it does in the preview beside it and in
            // the Rate Review table. Showing the raw config label left the two
            // halves of this page disagreeing about what the same band is called.
            value={bandLabel(band.key ? `adjustments.${section}.${band.key}` : null, band.label ?? "")}
            onChange={(e) =>
              onChange(
                bands.map((b, j) =>
                  i === j
                    ? // Retyping the name makes the band THEIRS: dropping the key
                      // is what stops the engine translating over their wording
                      // (D30). Keeping it would silently discard the edit.
                      { ...b, key: null, label: e.target.value }
                    : b,
                ),
              )
            }
          />
          <input
            type="number"
            step={thresholdStep}
            className={`${inputClass} tnum`}
            value={band[thresholdKey] ?? ""}
            onChange={(e) =>
              // Empty must NOT collapse to 0 -- a 0 threshold silently strands every
              // band above it. Mirrors NumberInput: cleared -> null -> default on merge.
              onChange(
                bands.map((b, j) =>
                  i === j
                    ? { ...b, [thresholdKey]: e.target.value === "" ? null : Number(e.target.value) }
                    : b,
                ),
              )
            }
          />
          <div className="relative">
            <input
              type="number"
              step={0.5}
              className={`${inputClass} tnum pr-7`}
              value={band.adjustment_pct ?? ""}
              onChange={(e) =>
                onChange(
                  bands.map((b, j) =>
                    i === j
                      ? { ...b, adjustment_pct: e.target.value === "" ? null : Number(e.target.value) }
                      : b,
                  ),
                )
              }
            />
            <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] text-ink-400">%</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function StrategyPanel({ onOpenSeasonal }: { onOpenSeasonal: () => void }) {
  const t = useTranslations("settings");
  const tval = useTranslations("validation");
  const tv = useTranslations("vocab");
  const tc = useTranslations("common");
  const adjustmentText = useAdjustmentText();
  const { formatAdjPct, formatSignedVND, formatStayDate, formatVND } = useFormat();
  const [config, setConfig] = useState<PricingConfig | null>(null);
  const [draft, setDraft] = useState<any>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [baseline, setBaseline] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dirty = useMemo(
    () => !!draft && !!config && JSON.stringify(draft) !== JSON.stringify(config.payload),
    [draft, config],
  );

  const load = useCallback(async () => {
    try {
      const c = await api.config();
      setConfig(c);
      setDraft(structuredClone(c.payload));
      setBaseline(await api.preview(c.payload));
    } catch {
      // setLoading(false) has to happen either way, or an unreachable API
      // leaves the page on its spinner for ever with nothing said.
      setMessage(tc("apiUnreachable"));
    } finally {
      setLoading(false);
    }
  }, [tc]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!draft) return;
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      api
        .preview(draft)
        .then((result) => {
          setPreview(result);
          setPreviewError(null);
        })
        .catch((e: any) => {
          // Swallowing this blanked the panel with no explanation while Save
          // went on succeeding — preview and save disagreeing, invisibly.
          setPreview(null);
          setPreviewError(e?.message || t("previewFailed"));
        });
    }, 350);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [draft]);

  const update = (path: (string | number)[], value: any) => setDraft((d: any) => setPath(d, path, value));

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const saved = await api.saveConfig(draft);
      setConfig(saved);
      setDraft(structuredClone(saved.payload));
      setBaseline(await api.preview(saved.payload));
      setMessage(`Saved as rules v${saved.version}. All recommendations were recalculated.`);
    } catch (e: any) {
      setMessage(t("saveFailed", { reason: e.message }));
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const c = await api.resetConfig();
      setConfig(c);
      setDraft(structuredClone(c.payload));
      setBaseline(await api.preview(c.payload));
      setMessage(`Reset to demo defaults (rules v${c.version}). Recommendations recalculated.`);
    } catch (e: any) {
      // /api/settings/reset can now 422. Without this the spinner clears and
      // nothing is shown -- the same silent-no-op shape as save() and
      // regenerate(), both already fixed. Third call site of the same class.
      setMessage(t("resetFailed", { reason: e?.message || tc("unknownError") }));
    } finally {
      setSaving(false);
    }
  };

  if (loading || !draft) return <div className="px-7 py-6"><Spinner label={t("loading")} /></div>;

  const delta = preview && baseline ? preview.recommended_net_rate - baseline.recommended_net_rate : 0;

  return (
    <div className="max-w-[1500px]">
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle")}
        actions={
          <>
            <Button onClick={reset} disabled={saving}>{t("reset")}</Button>
            <Button variant="primary" onClick={save} disabled={saving || !dirty}>
              {saving ? t("saving") : dirty ? t("save") : t("noChanges")}
            </Button>
          </>
        }
      />

      <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 flex items-start justify-between gap-4">
        <div>
          <div className="text-[12.5px] font-semibold text-emerald-900">
            {t("rateBookNoticeTitle")}
          </div>
          <p className="text-[11.5px] text-emerald-800 mt-1 leading-snug max-w-2xl">
            {t("rateBookNoticeBody")}
          </p>
        </div>
        <button
          type="button"
          onClick={onOpenSeasonal}
          className="shrink-0 text-[12px] font-medium text-emerald-700 hover:text-emerald-900 whitespace-nowrap"
        >
          {t("openRateBook")}
        </button>
      </div>

      {message && (
        <div className="mt-4 rounded-lg bg-brand-50 border border-brand-200 px-4 py-2.5 text-[12.5px] text-brand-700">
          {message}
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-5 items-start">
        <div className="space-y-4">
          <Section
            title={t("pace")}
            description={t("paceDesc")}
          >
            <BandEditor
              bands={draft.pace.bands}
              section="pace"
              thresholdKey="max_gap"
              thresholdLabel={t("upToGap")}
              onChange={(b) => update(["pace", "bands"], b)}
            />
          </Section>

          <Section
            title={t("recentPickup")}
            description={t("pickupDesc")}
          >
            <div className="grid grid-cols-2 gap-3 mb-4">
              <Field label={t("lookbackDays")}>
                <NumberInput
                  step={1}
                  value={draft.recent_pickup.lookback_days}
                  onChange={(v) => update(["recent_pickup", "lookback_days"], v)}
                />
              </Field>
              <Field label={t("expectedPickup")}>
                <NumberInput
                  step={0.1}
                  value={draft.recent_pickup.expected_pickup_per_week}
                  onChange={(v) => update(["recent_pickup", "expected_pickup_per_week"], v)}
                />
              </Field>
            </div>
            <BandEditor
              bands={draft.recent_pickup.bands}
              section="recent_pickup"
              thresholdKey="max_delta"
              thresholdLabel={t("upToDelta")}
              thresholdStep={0.25}
              onChange={(b) => update(["recent_pickup", "bands"], b)}
            />
          </Section>

          <Section
            title={t("events")}
            description={t("eventsDesc")}
          >
            <div className="grid grid-cols-3 gap-3">
              {["low", "medium", "high"].map((level) => (
                <Field key={level} label={`${level[0].toUpperCase()}${level.slice(1)} impact`}>
                  <NumberInput
                    suffix="%"
                    value={draft.event.impact_adjustment_pct[level]}
                    onChange={(v) => update(["event", "impact_adjustment_pct", level], v)}
                  />
                </Field>
              ))}
            </div>
          </Section>

          <Section
            title={t("marketSignal")}
            description={t("marketDesc")}
          >
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Field label={t("minConfidence")} hint={t("minConfidenceHint")}>
                <select
                  className={inputClass}
                  value={draft.market.min_confidence}
                  onChange={(e) => update(["market", "min_confidence"], e.target.value)}
                >
                  <option value="HIGH">{t("confHigh")}</option>
                  <option value="MEDIUM">{t("confMedium")}</option>
                  <option value="LOW">{t("confLow")}</option>
                </select>
              </Field>
              <Field label={t("sensitivity")} hint={t("sensitivityHint")}>
                <NumberInput
                  step={0.05}
                  value={draft.market.sensitivity}
                  onChange={(v) => update(["market", "sensitivity"], v)}
                />
              </Field>
              <Field label={t("maxAdjustment")}>
                <NumberInput
                  suffix="%"
                  value={draft.market.max_adjustment_pct}
                  onChange={(v) => update(["market", "max_adjustment_pct"], v)}
                />
              </Field>
              <Field label={t("minObservations")}>
                <NumberInput
                  step={1}
                  value={draft.market.min_observations}
                  onChange={(v) => update(["market", "min_observations"], v)}
                />
              </Field>
            </div>
          </Section>

          <Section
            title={t("dayOfWeek")}
            description={t("dowDescription")}
          >
            <label className="flex items-center gap-2 mb-3">
              <input
                type="checkbox"
                checked={draft.day_of_week.enabled}
                onChange={(e) => update(["day_of_week", "enabled"], e.target.checked)}
              />
              <span className="text-[12.5px] text-ink-700">{t("enableDow")}</span>
              {!draft.day_of_week.enabled && <Chip tone="neutral">{t("disabled")}</Chip>}
            </label>
            <div className={`grid grid-cols-4 sm:grid-cols-7 gap-2 ${draft.day_of_week.enabled ? "" : "opacity-40 pointer-events-none"}`}>
              {DAYS.map((day) => (
                <Field key={day} label={tv(`days.${day}`)}>
                  <NumberInput
                    suffix="%"
                    value={draft.day_of_week.adjustment_pct[day]}
                    onChange={(v) => update(["day_of_week", "adjustment_pct", day], v)}
                  />
                </Field>
              ))}
            </div>
          </Section>

          <Section
            title={t("boundsRounding")}
            description={t("boundsDescription")}
          >
            <div className="grid grid-cols-3 gap-3">
              <Field label={t("maxTotal")}>
                <NumberInput
                  suffix="%"
                  value={draft.dynamic.max_total_adjustment_pct}
                  onChange={(v) => update(["dynamic", "max_total_adjustment_pct"], v)}
                />
              </Field>
              <Field label={t("minTotal")}>
                <NumberInput
                  suffix="%"
                  value={draft.dynamic.min_total_adjustment_pct}
                  onChange={(v) => update(["dynamic", "min_total_adjustment_pct"], v)}
                />
              </Field>
              <Field label={t("roundingIncrement")}>
                <NumberInput
                  step={1000}
                  value={draft.rounding.increment}
                  onChange={(v) => update(["rounding", "increment"], v)}
                />
              </Field>
            </div>
          </Section>
        </div>

        {/* live preview */}
        <div className="xl:sticky xl:top-6 space-y-3">
          <Card className="p-4">
            <div className="text-[13px] font-semibold text-ink-900">{t("livePreview")}</div>
            <p className="text-[11.5px] text-ink-500 mt-0.5 leading-snug">
              {t("previewNote")}
            </p>

            {preview && preview.problems.length > 0 && (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                <div className="text-[11.5px] font-semibold text-amber-900">
                  {tval("title")}
                </div>
                <ul className="mt-1 space-y-0.5">
                  {preview.problems.map((problem, i) => (
                    <li key={`${problem.code}-${i}`} className="text-[11px] text-amber-800 leading-snug">
                      • {tval(problem.code, { ...problem.params, path: problem.path ?? "" })}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {previewError && (
              <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11.5px] text-rose-700">
                {previewError}
              </div>
            )}

            {preview ? (
              <>
                {/* Codes, not the API's *_label fields: those are English in
                    every locale, so the preview header read "2BR Regular ·
                    High Season 1" above a breakdown written in Vietnamese. */}
                <div className="mt-3 text-[12px] text-ink-600">
                  <span className="font-medium text-ink-800">
                    {preview.room_category
                      ? tv(`roomCategories.${preview.room_category}`)
                      : preview.room_category_label}
                  </span>{" "}
                  · {formatStayDate(preview.stay_date)}
                </div>
                <div className="text-[11px] text-ink-400">
                  {preview.season_key ? tv(`seasonsShort.${preview.season_key}`) : preview.season_label}
                </div>

                <div className="mt-3 rounded-lg bg-ink-50 border border-ink-200 p-3">
                  <div className="flex items-baseline justify-between text-[11px] text-ink-500">
                    <span>{t("validatedBase")}</span>
                    <span className="tnum">{formatVND(preview.band_base_net_rate)}</span>
                  </div>
                  <div className="flex items-baseline justify-between mt-1.5">
                    <span className="text-[11px] text-ink-500">{t("recommendedNet")}</span>
                    <span className="tnum text-[19px] font-bold text-brand-700">
                      {formatVND(preview.recommended_net_rate)}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between mt-1">
                    <span className="text-[11px] text-ink-400">
                      band {formatVND(preview.band_min_net_rate)} – {formatVND(preview.band_max_net_rate)}
                    </span>
                    <span className="tnum text-[12px] font-medium text-ink-600">
                      {formatAdjPct(preview.total_adjustment_pct)}
                    </span>
                  </div>
                  {dirty && baseline && (
                    <div className="mt-2 pt-2 border-t border-ink-200 flex items-baseline justify-between">
                      <span className="text-[11px] text-ink-500">{t("previewEffect")}</span>
                      <span
                        className={`tnum text-[12px] font-semibold ${
                          delta > 0 ? "text-emerald-600" : delta < 0 ? "text-rose-600" : "text-ink-400"
                        }`}
                      >
                        {delta === 0 ? t("noEffect") : formatSignedVND(delta)}
                      </span>
                    </div>
                  )}
                </div>

                <div className="mt-3 space-y-1">
                  {preview.adjustments.map((a) => (
                    <div key={a.sequence} className="flex items-center justify-between text-[11.5px]">
                      <span
                        className={
                          a.is_ignored ? "text-amber-700" : a.is_neutral ? "text-ink-300" : "text-ink-600"
                        }
                      >
                        {adjustmentText(a).label}
                      </span>
                      <span className="flex items-center gap-2 shrink-0">
                        <span className={`tnum ${a.is_neutral || a.is_ignored ? "text-ink-300" : "text-ink-500"}`}>
                          {a.code === "rate_band" ? "" : formatAdjPct(a.adjustment_pct)}
                        </span>
                        <span
                          className={`tnum w-20 text-right ${
                            a.delta > 0.5 ? "text-emerald-600" : a.delta < -0.5 ? "text-rose-600" : "text-ink-300"
                          }`}
                        >
                          {a.code === "rate_band"
                            ? formatVND(a.price_after)
                            : a.is_neutral || a.is_ignored
                              ? "—"
                              : formatSignedVND(a.delta)}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              !previewError && (
                <div className="mt-3 text-[12px] text-ink-400">{t("noSample")}</div>
              )
            )}
          </Card>

          <Card className="p-4 bg-amber-50 border-amber-200">
            <div className="text-[12px] font-semibold text-amber-900">{t("unvalidated")}</div>
            <p className="text-[11.5px] text-amber-800 mt-1 leading-snug">
              {t("unvalidatedBody")}
            </p>
            {config && (
              <div className="text-[11px] text-amber-700 mt-2">
                {t("activeConfig", { version: config.version, label: config.label })}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
