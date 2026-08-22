"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Card, Field, PageHeader, Spinner, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { formatFactor, formatPct, formatSignedVND, formatVND } from "@/lib/format";
import type { PricingConfig, Preview } from "@/lib/types";

const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

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
  step = 0.01,
  placeholder,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  step?: number;
  placeholder?: string;
}) {
  return (
    <input
      type="number"
      step={step}
      className={inputClass}
      placeholder={placeholder}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
    />
  );
}

/** Threshold/multiplier band editor, used for occupancy, pace and lead time. */
function BandEditor({
  bands,
  thresholdKey,
  thresholdLabel,
  onChange,
  thresholdStep = 0.01,
}: {
  bands: any[];
  thresholdKey: string;
  thresholdLabel: string;
  onChange: (bands: any[]) => void;
  thresholdStep?: number;
}) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_110px_110px] gap-2 text-[11px] font-medium text-ink-400 px-1">
        <span>Band</span>
        <span>{thresholdLabel}</span>
        <span>Multiplier</span>
      </div>
      {bands.map((band, i) => (
        <div key={i} className="grid grid-cols-[1fr_110px_110px] gap-2 items-center">
          <input
            className={inputClass}
            value={band.label ?? ""}
            onChange={(e) => onChange(bands.map((b, j) => (i === j ? { ...b, label: e.target.value } : b)))}
          />
          <input
            type="number"
            step={thresholdStep}
            className={`${inputClass} tnum`}
            value={band[thresholdKey] ?? ""}
            onChange={(e) =>
              onChange(bands.map((b, j) => (i === j ? { ...b, [thresholdKey]: Number(e.target.value) } : b)))
            }
          />
          <input
            type="number"
            step={0.01}
            className={`${inputClass} tnum`}
            value={band.multiplier ?? 1}
            onChange={(e) =>
              onChange(bands.map((b, j) => (i === j ? { ...b, multiplier: Number(e.target.value) } : b)))
            }
          />
        </div>
      ))}
    </div>
  );
}

export default function SettingsPage() {
  const [config, setConfig] = useState<PricingConfig | null>(null);
  const [draft, setDraft] = useState<any>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
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
    const c = await api.config();
    setConfig(c);
    setDraft(structuredClone(c.payload));
    setBaseline(await api.preview(c.payload));
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Live preview: re-price a sample stay date against the UNSAVED draft.
  useEffect(() => {
    if (!draft) return;
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      api.preview(draft).then(setPreview).catch(() => setPreview(null));
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
      const saved = await api.saveConfig(draft, "operator-edit");
      setConfig(saved);
      setDraft(structuredClone(saved.payload));
      setBaseline(await api.preview(saved.payload));
      setMessage(`Saved as rules v${saved.version}. All recommendations were recalculated.`);
    } catch (e: any) {
      setMessage(`Save failed: ${e.message}`);
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
    } finally {
      setSaving(false);
    }
  };

  if (loading || !draft) return <div className="px-7 py-6"><Spinner label="Loading pricing rules…" /></div>;

  const delta = preview && baseline ? preview.recommended_price - baseline.recommended_price : 0;

  return (
    <div className="px-7 py-6 max-w-[1500px]">
      <PageHeader
        title="Pricing rules"
        subtitle="These are the assumptions Pricing Engine V1 uses. None have been validated with Luminous yet — change them freely and watch the sample recommendation react."
        actions={
          <>
            <Button onClick={reset} disabled={saving}>Reset to demo defaults</Button>
            <Button variant="primary" onClick={save} disabled={saving || !dirty}>
              {saving ? "Saving…" : dirty ? "Save & recalculate" : "No changes"}
            </Button>
          </>
        }
      />

      {message && (
        <div className="mt-4 rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-2.5 text-[12.5px] text-emerald-800">
          {message}
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-5 items-start">
        <div className="space-y-4">
          <Section
            title="Price bounds & rounding"
            description="Global guardrails applied after every factor. Per-room min/max come from the PMS unless overridden here."
          >
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <Field label="Base price override (VND)" hint="Blank = use each room's own base price">
                <NumberInput step={10000} placeholder="Per room" value={draft.pricing.base_price_override}
                  onChange={(v) => update(["pricing", "base_price_override"], v)} />
              </Field>
              <Field label="Min price override (VND)" hint="Blank = use each room's floor">
                <NumberInput step={10000} placeholder="Per room" value={draft.pricing.min_price_override}
                  onChange={(v) => update(["pricing", "min_price_override"], v)} />
              </Field>
              <Field label="Max price override (VND)" hint="Blank = use each room's ceiling">
                <NumberInput step={10000} placeholder="Per room" value={draft.pricing.max_price_override}
                  onChange={(v) => update(["pricing", "max_price_override"], v)} />
              </Field>
              <Field label="Rounding increment (VND)">
                <NumberInput step={1000} value={draft.pricing.rounding_increment}
                  onChange={(v) => update(["pricing", "rounding_increment"], v)} />
              </Field>
              <Field label="Lowest allowed multiplier" hint="Stops factors compounding downward">
                <NumberInput value={draft.pricing.global_multiplier_min}
                  onChange={(v) => update(["pricing", "global_multiplier_min"], v)} />
              </Field>
              <Field label="Highest allowed multiplier" hint="Stops factors compounding upward">
                <NumberInput value={draft.pricing.global_multiplier_max}
                  onChange={(v) => update(["pricing", "global_multiplier_max"], v)} />
              </Field>
            </div>
          </Section>

          <Section title="Day of week" description="How much each weekday moves the price relative to base.">
            <div className="grid grid-cols-4 sm:grid-cols-7 gap-2">
              {DAYS.map((day) => (
                <Field key={day} label={day.slice(0, 3).replace(/^./, (c) => c.toUpperCase())}>
                  <NumberInput value={draft.day_of_week.multipliers[day]}
                    onChange={(v) => update(["day_of_week", "multipliers", day], v)} />
                </Field>
              ))}
            </div>
          </Section>

          <Section title="Occupancy" description="Higher occupancy usually justifies a higher price. Thresholds are fractions (0.85 = 85%).">
            <BandEditor bands={draft.occupancy.bands} thresholdKey="max" thresholdLabel="Up to (occupancy)"
              onChange={(b) => update(["occupancy", "bands"], b)} />
          </Section>

          <Section title="Booking pace" description="Pace index compares recent pickup against expected pickup. 1.0 = exactly on pace.">
            <div className="grid grid-cols-2 gap-3 mb-4">
              <Field label="Lookback window (days)">
                <NumberInput step={1} value={draft.booking_pace.lookback_days}
                  onChange={(v) => update(["booking_pace", "lookback_days"], v)} />
              </Field>
              <Field label="Expected pickup per week (units)">
                <NumberInput step={0.1} value={draft.booking_pace.expected_pickup_per_week}
                  onChange={(v) => update(["booking_pace", "expected_pickup_per_week"], v)} />
              </Field>
            </div>
            <BandEditor bands={draft.booking_pace.bands} thresholdKey="max" thresholdLabel="Up to (index)"
              onChange={(b) => update(["booking_pace", "bands"], b)} />
          </Section>

          <Section title="Lead time" description="How far out the stay date is. Thresholds are in days until check-in.">
            <BandEditor bands={draft.lead_time.bands} thresholdKey="max_days" thresholdLabel="Up to (days)"
              thresholdStep={1} onChange={(b) => update(["lead_time", "bands"], b)} />
            <div className="mt-4 pt-4 border-t border-ink-100">
              <div className="text-[12px] font-semibold text-ink-700 mb-2">
                Unsold inventory close to check-in
              </div>
              <p className="text-[11.5px] text-ink-500 mb-3">
                An extra discount when a stay date is both near and still largely empty.
              </p>
              <div className="grid grid-cols-3 gap-3">
                <Field label="Within (days)">
                  <NumberInput step={1} value={draft.lead_time.urgency_discount.within_days}
                    onChange={(v) => update(["lead_time", "urgency_discount", "within_days"], v)} />
                </Field>
                <Field label="Occupancy below">
                  <NumberInput value={draft.lead_time.urgency_discount.occupancy_below}
                    onChange={(v) => update(["lead_time", "urgency_discount", "occupancy_below"], v)} />
                </Field>
                <Field label="Multiplier">
                  <NumberInput value={draft.lead_time.urgency_discount.multiplier}
                    onChange={(v) => update(["lead_time", "urgency_discount", "multiplier"], v)} />
                </Field>
              </div>
            </div>
          </Section>

          <Section title="Season & events" description="Monthly seasonality and the uplift applied on flagged event dates.">
            <div className="grid grid-cols-4 sm:grid-cols-6 gap-2">
              {MONTHS.map((month, i) => (
                <Field key={month} label={month.slice(0, 3)}>
                  <NumberInput value={draft.season.month_multipliers[String(i + 1)]}
                    onChange={(v) => update(["season", "month_multipliers", String(i + 1)], v)} />
                </Field>
              ))}
            </div>
            <div className="mt-4 pt-4 border-t border-ink-100 w-48">
              <Field label="Event multiplier">
                <NumberInput value={draft.event.multiplier} onChange={(v) => update(["event", "multiplier"], v)} />
              </Field>
            </div>
          </Section>

          <Section title="Market signal" description="How strongly competitor prices pull our price. Sensitivity 0 ignores the market; 1 tracks it one-for-one.">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Field label="Sensitivity">
                <NumberInput value={draft.market.sensitivity} onChange={(v) => update(["market", "sensitivity"], v)} />
              </Field>
              <Field label="Min multiplier">
                <NumberInput value={draft.market.min_multiplier} onChange={(v) => update(["market", "min_multiplier"], v)} />
              </Field>
              <Field label="Max multiplier">
                <NumberInput value={draft.market.max_multiplier} onChange={(v) => update(["market", "max_multiplier"], v)} />
              </Field>
              <Field label="Min observations" hint="Below this the signal is ignored">
                <NumberInput step={1} value={draft.market.min_observations}
                  onChange={(v) => update(["market", "min_observations"], v)} />
              </Field>
            </div>
          </Section>
        </div>

        {/* live preview */}
        <div className="xl:sticky xl:top-6 space-y-3">
          <Card className="p-4">
            <div className="text-[13px] font-semibold text-ink-900">Live preview</div>
            <p className="text-[11.5px] text-ink-500 mt-0.5 leading-snug">
              A sample stay date priced with your unsaved changes.
            </p>

            {preview ? (
              <>
                <div className="mt-3 text-[12px] text-ink-600">
                  <span className="font-medium text-ink-800">{preview.room_name}</span> · {preview.stay_date}
                </div>

                <div className="mt-3 rounded-lg bg-ink-50 border border-ink-200 p-3">
                  <div className="flex items-baseline justify-between">
                    <span className="text-[11px] text-ink-500">Recommended</span>
                    <span className="tnum text-[19px] font-bold text-brand-700">
                      {formatVND(preview.recommended_price)}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between mt-1">
                    <span className="text-[11px] text-ink-400">vs current {formatVND(preview.current_price)}</span>
                    <span className="tnum text-[12px] font-medium text-ink-600">{formatPct(preview.change_pct)}</span>
                  </div>
                  {dirty && baseline && (
                    <div className="mt-2 pt-2 border-t border-ink-200 flex items-baseline justify-between">
                      <span className="text-[11px] text-ink-500">Effect of your edits</span>
                      <span
                        className={`tnum text-[12px] font-semibold ${
                          delta > 0 ? "text-emerald-600" : delta < 0 ? "text-rose-600" : "text-ink-400"
                        }`}
                      >
                        {delta === 0 ? "no change" : formatSignedVND(delta)}
                      </span>
                    </div>
                  )}
                </div>

                <div className="mt-3 space-y-1">
                  {preview.adjustments.map((a) => (
                    <div key={a.sequence} className="flex items-center justify-between text-[11.5px]">
                      <span className={a.is_neutral ? "text-ink-300" : "text-ink-600"}>{a.label}</span>
                      <span className="flex items-center gap-2 shrink-0">
                        <span className={`tnum ${a.is_neutral ? "text-ink-300" : "text-ink-500"}`}>
                          {formatFactor(a.factor)}
                        </span>
                        <span
                          className={`tnum w-20 text-right ${
                            a.delta > 0.5 ? "text-emerald-600" : a.delta < -0.5 ? "text-rose-600" : "text-ink-300"
                          }`}
                        >
                          {a.is_neutral ? "—" : formatSignedVND(a.delta)}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="mt-3 text-[12px] text-ink-400">No sample stay date available.</div>
            )}
          </Card>

          <Card className="p-4 bg-amber-50 border-amber-200">
            <div className="text-[12px] font-semibold text-amber-900">These values are placeholders</div>
            <p className="text-[11.5px] text-amber-800 mt-1 leading-snug">
              Every multiplier and threshold here was chosen by the engineering team to make the demo legible.
              They are marked UNVALIDATED in ASSUMPTIONS.md and need to be confirmed with the Luminous operator.
            </p>
            {config && (
              <div className="text-[11px] text-amber-700 mt-2">
                Active: rules v{config.version} ({config.label})
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
