"use client";

import { useCallback, useEffect, useState } from "react";
import { Button, Card, Chip, Empty, PageHeader, Spinner, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { formatVND } from "@/lib/format";
import type { RateBand } from "@/lib/types";

const MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function RateBookPage() {
  const [bands, setBands] = useState<RateBand[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<number, { min: string; base: string; max: string }>>({});

  const load = useCallback(async () => {
    const [b, m] = await Promise.all([api.rateBook(), api.rateBookMeta()]);
    setBands(b);
    setMeta(m);
    setDrafts(
      Object.fromEntries(
        b.map((x) => [x.id, { min: String(x.min_net_rate), base: String(x.base_net_rate), max: String(x.max_net_rate) }]),
      ),
    );
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async (band: RateBand) => {
    const d = drafts[band.id];
    setSaving(true);
    setMessage(null);
    try {
      await api.updateRateBand(band.id, {
        min_net_rate: Number(d.min),
        base_net_rate: Number(d.base),
        max_net_rate: Number(d.max),
      });
      await load();
      setMessage(`Updated ${band.season_label} · ${band.room_category_label}. Recalculate to apply.`);
    } catch (e: any) {
      setMessage(`Could not save: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setSaving(true);
    try {
      await api.resetRateBook();
      await load();
      setMessage("Restored every band to the client-validated values and recalculated.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="px-7 py-6"><Spinner label="Loading rate book…" /></div>;

  const seasons = Array.from(new Set(bands.map((b) => b.season_key)));
  const edited = bands.filter((b) => b.source !== "CLIENT_VALIDATED").length;

  return (
    <div className="px-7 py-6 space-y-5 max-w-[1400px]">
      <PageHeader
        title="Seasonal rate book"
        subtitle="Luminous' own MIN / BASE / MAX NET rates by season and room category. This is validated business data — the pricing engine anchors on it rather than modelling seasonality itself."
        actions={
          <Button onClick={reset} disabled={saving || edited === 0}>
            Restore client values
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="up">Client-validated</Chip>
        <Chip tone="neutral">NET rates — what Luminous receives</Chip>
        <Chip tone="neutral">{bands.length} bands</Chip>
        {edited > 0 && <Chip tone="warn">{edited} band(s) edited from the client values</Chip>}
      </div>

      {meta?.statement && (
        <Card className="p-4 bg-emerald-50 border-emerald-200">
          <p className="text-[12.5px] text-emerald-900 leading-relaxed">{meta.statement}</p>
        </Card>
      )}

      {message && (
        <div className="rounded-lg bg-brand-50 border border-brand-200 px-4 py-2.5 text-[12.5px] text-brand-700">
          {message}
        </div>
      )}

      {bands.length === 0 ? (
        <Empty title="No rate bands loaded" />
      ) : (
        seasons.map((seasonKey) => {
          const seasonBands = bands.filter((b) => b.season_key === seasonKey);
          const first = seasonBands[0];
          return (
            <Card key={seasonKey} className="overflow-hidden">
              <div className="px-4 py-3 border-b border-ink-200 bg-ink-50/60 flex items-center justify-between">
                <div>
                  <div className="text-[13px] font-semibold text-ink-900">{first.season_label}</div>
                  <div className="text-[11px] text-ink-500 mt-0.5">
                    {first.months.map((m) => MONTH_NAMES[m]).join(" · ")}
                    {first.note && <span className="ml-2 italic">{first.note}</span>}
                  </div>
                </div>
              </div>
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-ink-100">
                    {["Room category", "MIN NET", "BASE NET", "MAX NET", "Source", ""].map((h) => (
                      <th
                        key={h}
                        className="px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-ink-400 text-left"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {seasonBands.map((band) => {
                    const d = drafts[band.id] || { min: "", base: "", max: "" };
                    const dirty =
                      Number(d.min) !== band.min_net_rate ||
                      Number(d.base) !== band.base_net_rate ||
                      Number(d.max) !== band.max_net_rate;
                    return (
                      <tr key={band.id} className="border-b border-ink-100 last:border-0">
                        <td className="px-4 py-2.5 font-medium text-ink-900">
                          {band.room_category_label}
                        </td>
                        {(["min", "base", "max"] as const).map((field) => (
                          <td key={field} className="px-4 py-2.5">
                            <input
                              type="number"
                              step={50000}
                              className={`${inputClass} tnum w-36`}
                              value={d[field]}
                              onChange={(e) =>
                                setDrafts((prev) => ({
                                  ...prev,
                                  [band.id]: { ...prev[band.id], [field]: e.target.value },
                                }))
                              }
                            />
                            <div className="text-[10px] text-ink-400 mt-0.5 tnum">
                              {formatVND(Number(d[field]))}
                            </div>
                          </td>
                        ))}
                        <td className="px-4 py-2.5">
                          <Chip tone={band.source === "CLIENT_VALIDATED" ? "up" : "warn"}>
                            {band.source === "CLIENT_VALIDATED" ? "Client" : "Edited"}
                          </Chip>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <Button size="sm" disabled={!dirty || saving} onClick={() => save(band)}>
                            Save
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>
          );
        })
      )}
    </div>
  );
}
