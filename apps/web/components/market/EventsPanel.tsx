"use client";

import { useTranslations } from "next-intl";

import { useCallback, useEffect, useState } from "react";
import { Button, Card, Chip, Empty, Field, PageHeader, Spinner, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { todayISO } from "@/lib/format";
import { useFormat } from "@/lib/useFormat";
import type { EventItem } from "@/lib/types";

export function EventsPanel() {
  const t = useTranslations("events");
  const tc = useTranslations("common");
  const tv = useTranslations("vocab");
  const { formatStayDate } = useFormat();
  const [events, setEvents] = useState<EventItem[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [form, setForm] = useState({
    name: "",
    start_date: todayISO(),
    end_date: todayISO(),
    impact_level: "medium",
    event_type: "other",
    adjustment_pct: "",
    notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [e, m] = await Promise.all([api.events(true), api.eventMeta()]);
      setEvents(e);
      setMeta(m);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    if (!form.name) return;
    setBusy(true);
    setMessage(null);
    try {
      await api.addEvent({
        ...form,
        adjustment_pct: form.adjustment_pct === "" ? null : Number(form.adjustment_pct),
        notes: form.notes || null,
      });
      setForm({ ...form, name: "", adjustment_pct: "", notes: "" });
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
      await api.deleteEvent(id);
      await load();
    } catch {
      setMessage(tc("apiUnreachable"));
    }
  };

  const impactTone = (level: string) =>
    level === "high" ? "down" : level === "medium" ? "warn" : "neutral";

  return (
    <div className="px-7 py-6 space-y-5 max-w-[1400px]">
      <PageHeader
        title={t("title")}
        subtitle={t("subtitleLong")}
      />

      <div className="flex flex-wrap gap-2">
        <Chip tone="info">{t("subtitle")}</Chip>
        <Chip tone="warn">{t("unvalidated")}</Chip>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-5 items-start">
        <Card className="p-5">
          <h2 className="text-[14px] font-semibold text-ink-900">{t("add")}</h2>
          <p className="text-[12px] text-ink-500 mt-0.5 leading-snug">
            {t("onlyExceptional")}
          </p>

          <div className="mt-4 space-y-3">
            <Field label={t("name")}>
              <input
                className={inputClass}
                placeholder={t("namePlaceholder")}
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("starts")}>
                <input
                  type="date"
                  className={inputClass}
                  value={form.start_date}
                  onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                />
              </Field>
              <Field label={t("ends")}>
                <input
                  type="date"
                  className={inputClass}
                  value={form.end_date}
                  onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("impactLevel")}>
                <select
                  className={inputClass}
                  value={form.impact_level}
                  onChange={(e) => setForm({ ...form, impact_level: e.target.value })}
                >
                  {(meta?.impact_levels || []).map((l: any) => (
                    <option key={l.code} value={l.code}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t("type")}>
                <select
                  className={inputClass}
                  value={form.event_type}
                  onChange={(e) => setForm({ ...form, event_type: e.target.value })}
                >
                  {(meta?.event_types || []).map((t: any) => (
                    <option key={t.code} value={t.code}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field
              label={t("overridePct")}
              hint={t("overrideHint")}
            >
              <input
                type="number"
                step={0.5}
                className={inputClass}
                placeholder={t("overridePlaceholder")}
                value={form.adjustment_pct}
                onChange={(e) => setForm({ ...form, adjustment_pct: e.target.value })}
              />
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
              {t("saveEvent")}
            </Button>

            {message && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11.5px] text-emerald-800">
                {message}
              </div>
            )}
          </div>
        </Card>

        <Card>
          <div className="px-4 py-3 border-b border-ink-200 text-[13px] font-semibold text-ink-900">
            Events <span className="text-ink-400 font-normal">({events.length})</span>
          </div>
          {loading ? (
            <Spinner label={t("loading")} />
          ) : events.length === 0 ? (
            <Empty title={t("empty")} hint={t("emptyHint")} />
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-ink-200 bg-ink-50/60">
                  {[t("name"), t("dates"), t("impact"), t("type"), t("override"), tc("source"), ""].map((h) => (
                    <th
                      key={h}
                      className="px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-500 text-left"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id} className="border-b border-ink-100 hover:bg-ink-50">
                    <td className="px-3 py-2.5">
                      <div className="font-medium text-ink-900">{e.name}</div>
                      {e.notes && <div className="text-[11px] text-ink-400 italic">{e.notes}</div>}
                    </td>
                    <td className="px-3 py-2.5 text-ink-600 whitespace-nowrap">
                      {formatStayDate(e.start_date)}
                      {e.start_date !== e.end_date && <> → {formatStayDate(e.end_date)}</>}
                    </td>
                    <td className="px-3 py-2.5">
                      <Chip tone={impactTone(e.impact_level) as any}>{tv(`eventImpact.${e.impact_level}`)}</Chip>
                    </td>
                    <td className="px-3 py-2.5 text-ink-500 text-[12px]">{tv(`eventTypes.${e.event_type}`)}</td>
                    <td className="px-3 py-2.5 tnum text-ink-600">
                      {e.adjustment_pct !== null ? `${e.adjustment_pct > 0 ? "+" : ""}${e.adjustment_pct}%` : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-[11px] text-ink-400">{e.source}</td>
                    <td className="px-3 py-2.5 text-right">
                      <button
                        onClick={() => remove(e.id)}
                        className="text-[11px] text-ink-400 hover:text-rose-600 transition-colors"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  );
}
