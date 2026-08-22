"use client";

import { useCallback, useEffect, useState } from "react";
import { Button, Card, Chip, Empty, Field, PageHeader, Spinner, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, formatStayDate, formatVND, todayISO } from "@/lib/format";
import type { MarketObservation, Property } from "@/lib/types";

interface ProviderInfo {
  key: string;
  name: string;
  healthy: boolean;
  mode: string;
  detail: string;
  remediation: string;
}

export default function MarketPage() {
  const [observations, setObservations] = useState<MarketObservation[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [sourceFilter, setSourceFilter] = useState("all");

  const [form, setForm] = useState({
    room_id: "",
    stay_date: todayISO(),
    competitor_name: "",
    observed_price: "",
    notes: "",
    source_url: "",
  });

  const rooms = properties.flatMap((p) => p.rooms.map((r) => ({ ...r, propertyName: p.name })));

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setObservations(await api.observations({ source: sourceFilter, }));
    } finally {
      setLoading(false);
    }
  }, [sourceFilter]);

  useEffect(() => {
    api.properties().then(setProperties).catch(() => setProperties([]));
    api.marketProviders().then(setProviders).catch(() => setProviders([]));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    if (!form.competitor_name || !form.observed_price) return;
    setBusy(true);
    setMessage(null);
    try {
      await api.addObservation({
        stay_date: form.stay_date,
        competitor_name: form.competitor_name,
        observed_price: Number(form.observed_price),
        room_id: form.room_id ? Number(form.room_id) : null,
        source: "manual",
        source_url: form.source_url || null,
        notes: form.notes || null,
      });
      setForm({ ...form, competitor_name: "", observed_price: "", notes: "", source_url: "" });
      setMessage({ ok: true, text: "Observation saved. Recalculate on the dashboard to fold it into pricing." });
      await load();
    } catch (e: any) {
      setMessage({ ok: false, text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const runCollector = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.collectMarket(form.stay_date, form.room_id ? Number(form.room_id) : null);
      setMessage({
        ok: result.ok,
        text: result.ok ? result.message : `${result.message} ${result.remediation}`,
      });
      if (result.ok) await load();
    } catch (e: any) {
      setMessage({ ok: false, text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    await api.deleteObservation(id);
    await load();
  };

  return (
    <div className="px-7 py-6 space-y-5 max-w-[1500px]">
      <PageHeader
        title="Market data"
        subtitle="Reference prices from competitors. The engine turns these into a market signal — and applies a neutral factor whenever they are missing."
      />

      <div className="flex flex-wrap gap-2">
        {providers.map((p) => (
          <Chip key={p.key} tone={p.healthy ? "up" : "warn"} title={p.detail + (p.remediation ? ` — ${p.remediation}` : "")}>
            {p.name.replace("MarketDataProvider", "")}: {p.healthy ? "available" : "unavailable"}
          </Chip>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-5 items-start">
        <Card className="p-5">
          <h2 className="text-[14px] font-semibold text-ink-900">Add an observation</h2>
          <p className="text-[12px] text-ink-500 mt-0.5 leading-snug">
            Manual entry is always available — it is the fallback when automated collection is not.
          </p>

          <div className="mt-4 space-y-3">
            <Field label="Room" hint="Leave blank to apply to the whole property">
              <select
                className={inputClass}
                value={form.room_id}
                onChange={(e) => setForm({ ...form, room_id: e.target.value })}
              >
                <option value="">— select a room —</option>
                {rooms.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.propertyName} · {r.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Stay date">
              <input
                type="date"
                className={inputClass}
                value={form.stay_date}
                onChange={(e) => setForm({ ...form, stay_date: e.target.value })}
              />
            </Field>
            <Field label="Competitor / reference name">
              <input
                className={inputClass}
                placeholder="e.g. Saigon Sky Apartments"
                value={form.competitor_name}
                onChange={(e) => setForm({ ...form, competitor_name: e.target.value })}
              />
            </Field>
            <Field label="Observed price (VND)">
              <input
                type="number"
                step={10000}
                className={inputClass}
                placeholder="1500000"
                value={form.observed_price}
                onChange={(e) => setForm({ ...form, observed_price: e.target.value })}
              />
            </Field>
            <Field label="Source URL (optional)">
              <input
                className={inputClass}
                placeholder="https://…"
                value={form.source_url}
                onChange={(e) => setForm({ ...form, source_url: e.target.value })}
              />
            </Field>
            <Field label="Notes (optional)">
              <input
                className={inputClass}
                placeholder="Comparable size, includes breakfast…"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </Field>

            <div className="flex items-center gap-2 pt-1">
              <Button variant="primary" onClick={submit} disabled={busy || !form.competitor_name || !form.observed_price}>
                Save observation
              </Button>
              <Button onClick={runCollector} disabled={busy} >
                Try public collector
              </Button>
            </div>

            {message && (
              <div
                className={`rounded-lg border px-3 py-2 text-[11.5px] ${
                  message.ok
                    ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                    : "bg-amber-50 border-amber-200 text-amber-800"
                }`}
              >
                {message.text}
              </div>
            )}
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between px-4 py-3 border-b border-ink-200">
            <div className="text-[13px] font-semibold text-ink-900">
              Observations <span className="text-ink-400 font-normal">({observations.length})</span>
            </div>
            <select
              className={`${inputClass} w-40`}
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
            >
              <option value="all">All sources</option>
              <option value="mock">Mock</option>
              <option value="manual">Manual</option>
              <option value="public_web">Public web</option>
            </select>
          </div>

          {loading ? (
            <Spinner label="Loading observations…" />
          ) : observations.length === 0 ? (
            <Empty title="No observations for this filter" hint="Add one on the left, or switch source." />
          ) : (
            <div className="overflow-x-auto max-h-[640px] overflow-y-auto">
              <table className="w-full text-[13px]">
                <thead className="sticky top-0 bg-ink-50">
                  <tr className="border-b border-ink-200">
                    {["Stay date", "Competitor", "Room", "Price", "Source", "Collected", ""].map((h) => (
                      <th
                        key={h}
                        className={`px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-500 ${
                          h === "Price" ? "text-right" : "text-left"
                        }`}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {observations.map((o) => (
                    <tr key={o.id} className="border-b border-ink-100 hover:bg-ink-50">
                      <td className="px-3 py-2 text-ink-700 whitespace-nowrap">{formatStayDate(o.stay_date)}</td>
                      <td className="px-3 py-2">
                        <div className="text-ink-900">{o.competitor_name}</div>
                        {o.notes && <div className="text-[11px] text-ink-400 italic">{o.notes}</div>}
                      </td>
                      <td className="px-3 py-2 text-[12px] text-ink-500">{o.room_name || o.property_name || "—"}</td>
                      <td className="px-3 py-2 text-right tnum font-medium text-ink-900 whitespace-nowrap">
                        {formatVND(o.observed_price)}
                      </td>
                      <td className="px-3 py-2">
                        <Chip tone={o.source === "manual" ? "info" : "neutral"}>{o.source}</Chip>
                      </td>
                      <td className="px-3 py-2 text-[11px] text-ink-400 whitespace-nowrap">
                        {formatDateTime(o.collected_at)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          onClick={() => remove(o.id)}
                          className="text-[11px] text-ink-400 hover:text-rose-600 transition-colors"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
