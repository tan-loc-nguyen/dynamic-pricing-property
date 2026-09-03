"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { useFormat } from "@/lib/useFormat";
import { Button, Card, Chip, Empty, Field, Spinner, inputClass } from "@/components/ui";
import type { Competitor, MarketObservation } from "@/lib/types";

/**
 * The comp set as a short list of properties, not a table of observation rows.
 *
 * An owner picks who they compete with and wants to know what those places are
 * charging and whether the number can be trusted. The per-observation detail
 * (tax basis, LOS, refundability) stays in Data details, where someone
 * verifying the pipeline can find it.
 *
 * Add/delete only, no in-place edit -- the same shape as the Events panel,
 * which manages its own comp-set-sized manual list the same way.
 */
export function CompetitorList() {
  const t = useTranslations("compSet");
  const tc = useTranslations("common");
  const tv = useTranslations("vocab");
  const { formatVND, formatDateTime } = useFormat();

  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [obs, setObs] = useState<MarketObservation[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [form, setForm] = useState({
    name: "",
    location: "",
    comparable_category: "",
    notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, o, m] = await Promise.all([
        api.competitors(),
        // Explicit limit: the endpoint defaults to the 200 most recent rows and
        // the demo holds ~1,200, so every price range, confidence and "last
        // seen" here was computed from a sixth of the data, ordered by
        // observed_at — the same truncation the overview had.
        api.observations({ limit: 5000 }),
        api.categoryMap(),
      ]);
      setCompetitors(c);
      setObs(o);
      setCategories(m.categories);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const summary = useMemo(() => {
    const m = new Map<
      number,
      { prices: number[]; last: string | null; confidences: Record<string, number> }
    >();
    for (const o of obs) {
      if (o.competitor_id === null) continue;
      const e = m.get(o.competitor_id) ?? { prices: [], last: null, confidences: {} };
      if (o.observed_price > 0) e.prices.push(o.observed_price);
      if (o.observed_at && (!e.last || o.observed_at > e.last)) e.last = o.observed_at;
      e.confidences[o.confidence] = (e.confidences[o.confidence] ?? 0) + 1;
      m.set(o.competitor_id, e);
    }
    return m;
  }, [obs]);

  const submit = async () => {
    if (!form.name) return;
    setBusy(true);
    setMessage(null);
    try {
      await api.addCompetitor({
        name: form.name,
        location: form.location,
        comparable_category: form.comparable_category || null,
        notes: form.notes || null,
        source: "manual",
      });
      setForm({ name: "", location: "", comparable_category: "", notes: "" });
      setMessage(t("saved"));
      await load();
    } catch (e: any) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    try {
      await api.deleteCompetitor(id);
      await load();
    } catch {
      setMessage(tc("apiUnreachable"));
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-5 items-start">
      <Card className="p-5">
        <h2 className="text-[14px] font-semibold text-ink-900">{t("add")}</h2>
        <div className="mt-4 space-y-3">
          <Field label={t("name")}>
            <input
              className={inputClass}
              placeholder={t("namePlaceholder")}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label={t("location")}>
            <input
              className={inputClass}
              placeholder={t("locationPlaceholder")}
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
          </Field>
          <Field label={tc("roomCategory")}>
            <select
              className={inputClass}
              value={form.comparable_category}
              onChange={(e) => setForm({ ...form, comparable_category: e.target.value })}
            >
              <option value="">{t("categoryNone")}</option>
              {categories.map((key) => (
                <option key={key} value={key}>
                  {tv(`roomCategories.${key}`)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={tc("notesOptional")}>
            <input
              className={inputClass}
              placeholder={t("notesPlaceholder")}
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </Field>

          <Button variant="primary" onClick={submit} disabled={busy || !form.name}>
            {t("saveCompetitor")}
          </Button>

          {message && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11.5px] text-emerald-800">
              {message}
            </div>
          )}
        </div>
      </Card>

      {loading ? (
        <div className="flex items-center gap-2 p-6 text-[12.5px] text-ink-400">
          <Spinner /> {t("loading")}
        </div>
      ) : !competitors.length ? (
        <Empty title={t("empty")} hint={t("emptyHint")} />
      ) : (
        <div className="space-y-2">
          {competitors.map((c) => {
            const s = summary.get(c.id);
            const prices = (s?.prices ?? []).sort((a, b) => a - b);
            const best =
              Object.entries(s?.confidences ?? {}).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
            return (
              <Card key={c.id} className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
                <div className="min-w-[180px] flex-1">
                  <div className="text-[13px] font-medium text-ink-900">{c.name}</div>
                  <div className="text-[11px] text-ink-400">
                    {c.location || "—"}
                    {c.comparable_category ? ` · ${tv(`roomCategories.${c.comparable_category}`)}` : ""}
                  </div>
                </div>

                <div className="min-w-[150px]">
                  <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
                    {t("observedRange")}
                  </div>
                  <div className="tnum text-[12.5px] text-ink-800">
                    {prices.length
                      ? `${formatVND(prices[0], { compact: true })} – ${formatVND(prices[prices.length - 1], { compact: true })}`
                      : "—"}
                  </div>
                </div>

                <div className="min-w-[110px]">
                  <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
                    {t("confidence")}
                  </div>
                  {best ? (
                    <Chip tone={best === "HIGH" ? "up" : best === "MEDIUM" ? "info" : "warn"}>
                      {tv(`confidence.${best}`)}
                    </Chip>
                  ) : (
                    <span className="text-[12px] text-ink-400">—</span>
                  )}
                </div>

                <div className="min-w-[130px]">
                  <div className="text-[10.5px] uppercase tracking-wide text-ink-400">
                    {t("lastSeen")}
                  </div>
                  <div className="text-[12px] text-ink-600">
                    {s?.last ? formatDateTime(s.last) : "—"}
                  </div>
                </div>

                <div className="tnum text-[11.5px] text-ink-400">
                  {t("observationCount", { count: prices.length })}
                </div>

                <button
                  onClick={() => remove(c.id)}
                  className="text-[11px] text-ink-400 hover:text-rose-600 transition-colors"
                >
                  {tc("delete")}
                </button>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
