"use client";

import { useTranslations } from "next-intl";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Chip } from "@/components/Chip";
import { Empty } from "@/components/Empty";
import { Field } from "@/components/Field";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { selectClass } from "@/lib/formControls";
import { api } from "@/lib/api";
import { confidenceTone, todayISO } from "@/lib/format";
import { useFormat } from "@/lib/useFormat";
import type { Competitor, MarketObservation, Property } from "@/lib/types";

interface ProviderInfo {
  key: string;
  name: string;
  healthy: boolean;
  mode: string;
  detail: string;
  remediation: string;
  max_confidence: string;
}

export function RawObservations() {
  const t = useTranslations("market");
  const tc = useTranslations("common");
  const tv = useTranslations("vocab");
  const tcr = useTranslations("confidenceReason");
  const tcg = useTranslations("confidenceGap");

  /** Why an observation scored as it did, composed in the viewer's language.
   *  `confidence_reason` is the English fallback kept for rows written before
   *  the codes existed. */
  const confidenceText = (o: MarketObservation) => {
    if (!o.confidence_code) return o.confidence_reason || "";
    const head = tcr(o.confidence_code);
    if (!o.confidence_gaps?.length) return head;
    const gaps = o.confidence_gaps.map((g) => tcg(g)).join(", ");
    const key = o.confidence === "MEDIUM" ? "minorGaps" : "gapsIntro";
    return `${head} ${tcr(key, { gaps })}`;
  };
  const { formatDateTime, formatStayDate, formatVND } = useFormat();
  const [observations, setObservations] = useState<MarketObservation[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [tab, setTab] = useState<"observations" | "compset">("observations");
  const [confidenceFilter, setConfidenceFilter] = useState("all");

  const [form, setForm] = useState({
    room_type_id: "",
    stay_date: todayISO(),
    competitor_name: "",
    observed_price: "",
    length_of_stay: "1",
    guests: "2",
    price_basis: "NET",
    tax_inclusion: "EXCLUSIVE",
    fee_inclusion: "EXCLUSIVE",
    promotion_status: "NONE",
    source_url: "",
    notes: "",
  });

  const [compForm, setCompForm] = useState({ name: "", location: "", comparable_category: "" });

  const roomTypes = properties.flatMap((p) => p.room_types);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [obs, comps] = await Promise.all([
        api.observations({ confidence: confidenceFilter }),
        api.competitors(),
      ]);
      setObservations(obs);
      setCompetitors(comps);
    } finally {
      setLoading(false);
    }
  }, [confidenceFilter]);

  useEffect(() => {
    api.properties().then(setProperties).catch(() => setProperties([]));
    api.marketProviders().then(setProviders).catch(() => setProviders([]));
    api.marketMeta().then(setMeta).catch(() => setMeta(null));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    if (!form.competitor_name || !form.observed_price) return;
    setBusy(true);
    setMessage(null);
    try {
      const created = await api.addObservation({
        stay_date: form.stay_date,
        competitor_name: form.competitor_name,
        observed_price: Number(form.observed_price),
        room_type_id: form.room_type_id ? Number(form.room_type_id) : null,
        length_of_stay: form.length_of_stay ? Number(form.length_of_stay) : null,
        guests: form.guests ? Number(form.guests) : null,
        price_basis: form.price_basis,
        tax_inclusion: form.tax_inclusion,
        fee_inclusion: form.fee_inclusion,
        promotion_status: form.promotion_status,
        source: "manual",
        source_url: form.source_url || null,
        notes: form.notes || null,
      });
      setForm({ ...form, competitor_name: "", observed_price: "", source_url: "", notes: "" });
      setMessage({
        ok: true,
        text: `Saved at ${created.confidence} confidence. ${
          created.confidence === "HIGH" || created.confidence === "MEDIUM"
            ? t("willInfluence")
            : t("willNotInfluence")
        }`,
      });
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
      const result = await api.collectMarket(
        form.stay_date,
        form.room_type_id ? Number(form.room_type_id) : null,
      );
      setMessage({ ok: result.ok, text: result.ok ? result.message : `${result.message} ${result.remediation}` });
      if (result.ok) await load();
    } catch (e: any) {
      setMessage({ ok: false, text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const addCompetitor = async () => {
    if (!compForm.name) return;
    setBusy(true);
    try {
      await api.addCompetitor({
        ...compForm,
        comparable_category: compForm.comparable_category || null,
      });
      setCompForm({ name: "", location: "", comparable_category: "" });
      await load();
    } catch {
      setMessage({ ok: false, text: tc("apiUnreachable") });
    } finally {
      setBusy(false);
    }
  };

  const options = (list: any[] | undefined, namespace: string) =>
    (list || []).map((o: any) => (
      <option key={o.code} value={o.code}>
        {tv(`${namespace}.${o.code}`)}
      </option>
    ));

  return (
    <div className="px-7 py-6 space-y-5 max-w-[1600px]">
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle")}
      />

      <div className="flex flex-wrap gap-2">
        {providers.map((p) => (
          <Chip
            key={p.key}
            tone={p.healthy ? "up" : "warn"}
            title={p.detail + (p.remediation ? ` — ${p.remediation}` : "")}
          >
            {p.name.replace("MarketDataProvider", "")}: max {p.max_confidence}
          </Chip>
        ))}
      </div>

      <Card className="p-4 bg-amber-50 border border-amber-200">
        <p className="text-[12px] text-amber-900 leading-relaxed">
          <span className="font-semibold">{t("uninterpretable")}</span> {t("uninterpretableBody")}
        </p>
      </Card>

      <div className="flex gap-1 border-b border-ink-200">
        {(["observations", "compset"] as const).map((tabKey) => (
          <button
            key={tabKey}
            onClick={() => setTab(tabKey)}
            className={`px-4 py-2 text-[13px] font-medium border-b-2 -mb-px transition-colors ${
              tab === tabKey
                ? "border-brand-500 text-brand-700"
                : "border-transparent text-ink-500 hover:text-ink-800"
            }`}
          >
            {tabKey === "observations"
              ? t("tabObservations", { count: observations.length })
              : t("tabCompset", { count: competitors.length })}
          </button>
        ))}
      </div>

      {tab === "compset" ? (
        <div className="grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-5 items-start">
          <Card className="p-5">
            <h2 className="text-[14px] font-semibold text-ink-900">{t("addCompetitor")}</h2>
            <p className="text-[12px] text-ink-500 mt-0.5 leading-snug">
              A comp set is a deliberate choice, not a search result. Pick properties a Luminous guest
              would genuinely consider instead.
            </p>
            <div className="mt-4 space-y-3">
              <Field label={t("propertyName")}>
                <Input
                  value={compForm.name}
                  onChange={(e) => setCompForm({ ...compForm, name: e.target.value })}
                />
              </Field>
              <Field label={t("location")}>
                <Input
                  placeholder={t("locationPlaceholder")}
                  value={compForm.location}
                  onChange={(e) => setCompForm({ ...compForm, location: e.target.value })}
                />
              </Field>
              <Field label={t("comparableToHint")}>
                <select
                  className={selectClass}
                  value={compForm.comparable_category}
                  onChange={(e) => setCompForm({ ...compForm, comparable_category: e.target.value })}
                >
                  <option value="">— any —</option>
                  {roomTypes.map((rt) => (
                    <option key={rt.category} value={rt.category}>
                      {rt.category_label}
                    </option>
                  ))}
                </select>
              </Field>
              <Button variant="default" onClick={addCompetitor} disabled={busy || !compForm.name}>
                Add to comp set
              </Button>
            </div>
          </Card>

          <Card className="py-0">
            {competitors.length === 0 ? (
              <Empty title={t("noCompetitors")} />
            ) : (
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-ink-200 bg-ink-50/60">
                    {[t("property"), t("location"), t("comparableTo"), t("observations"), tc("source"), ""].map((h) => (
                      <th key={h} className="px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-500 text-left">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {competitors.map((c) => (
                    <tr key={c.id} className="border-b border-ink-100 hover:bg-ink-50">
                      <td className="px-3 py-2.5 font-medium text-ink-900">{c.name}</td>
                      <td className="px-3 py-2.5 text-ink-600">{c.location || "—"}</td>
                      <td className="px-3 py-2.5 text-ink-600">{c.comparable_category || "any"}</td>
                      <td className="px-3 py-2.5 tnum text-ink-600">{c.observation_count}</td>
                      <td className="px-3 py-2.5 text-[11px] text-ink-400">{c.source}</td>
                      <td className="px-3 py-2.5 text-right">
                        <button
                          onClick={() => api.deleteCompetitor(c.id).then(load)}
                          className="text-[11px] text-ink-400 hover:text-rose-600"
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-5 items-start">
          <Card className="p-5">
            <h2 className="text-[14px] font-semibold text-ink-900">{t("record")}</h2>
            <p className="text-[12px] text-ink-500 mt-0.5 leading-snug">
              {t("basisNote")}
            </p>

            <div className="mt-4 space-y-3">
              <Field label={tc("roomCategory")}>
                <select
                  className={selectClass}
                  value={form.room_type_id}
                  onChange={(e) => setForm({ ...form, room_type_id: e.target.value })}
                >
                  <option value="">— select —</option>
                  {roomTypes.map((rt) => (
                    <option key={rt.id} value={rt.id}>
                      {rt.category_label}
                    </option>
                  ))}
                </select>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label={tc("stayDate")}>
                  <Input
                    type="date"
                    value={form.stay_date}
                    onChange={(e) => setForm({ ...form, stay_date: e.target.value })}
                  />
                </Field>
                <Field label={t("observedPrice")}>
                  <Input
                    type="number"
                    step={10000}
                    value={form.observed_price}
                    onChange={(e) => setForm({ ...form, observed_price: e.target.value })}
                  />
                </Field>
              </div>
              <Field label={t("competitor")}>
                <Input
                  placeholder={t("propertyPlaceholder")}
                  value={form.competitor_name}
                  onChange={(e) => setForm({ ...form, competitor_name: e.target.value })}
                  list="comp-list"
                />
                <datalist id="comp-list">
                  {competitors.map((c) => (
                    <option key={c.id} value={c.name} />
                  ))}
                </datalist>
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label={t("priceBasis")}>
                  <select
                    className={selectClass}
                    value={form.price_basis}
                    onChange={(e) => setForm({ ...form, price_basis: e.target.value })}
                  >
                    {options(meta?.price_bases, "priceBasis")}
                  </select>
                </Field>
                <Field label={t("promotion")}>
                  <select
                    className={selectClass}
                    value={form.promotion_status}
                    onChange={(e) => setForm({ ...form, promotion_status: e.target.value })}
                  >
                    {options(meta?.promotion_options, "promotion")}
                  </select>
                </Field>
                <Field label={t("taxes")}>
                  <select
                    className={selectClass}
                    value={form.tax_inclusion}
                    onChange={(e) => setForm({ ...form, tax_inclusion: e.target.value })}
                  >
                    {options(meta?.inclusion_options, "inclusion")}
                  </select>
                </Field>
                <Field label={t("fees")}>
                  <select
                    className={selectClass}
                    value={form.fee_inclusion}
                    onChange={(e) => setForm({ ...form, fee_inclusion: e.target.value })}
                  >
                    {options(meta?.inclusion_options, "inclusion")}
                  </select>
                </Field>
                <Field label={t("lengthOfStay")}>
                  <Input
                    type="number"
                    value={form.length_of_stay}
                    onChange={(e) => setForm({ ...form, length_of_stay: e.target.value })}
                  />
                </Field>
                <Field label={t("guests")}>
                  <Input
                    type="number"
                    value={form.guests}
                    onChange={(e) => setForm({ ...form, guests: e.target.value })}
                  />
                </Field>
              </div>

              <Field label={tc("notesOptional")}>
                <Input
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                />
              </Field>

              <div className="flex items-center gap-2 pt-1">
                <Button
                  variant="default"
                  onClick={submit}
                  disabled={busy || !form.competitor_name || !form.observed_price}
                >
                  {t("saveObservation")}
                </Button>
                <Button variant="secondary" onClick={runCollector} disabled={busy}>
                  {t("tryPublicCollector")}
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

          <Card className="py-0">
            <div className="flex items-center justify-between px-4 py-3 border-b border-ink-200">
              <div className="text-[13px] font-semibold text-ink-900">
                {t("observationsHeading")}{" "}
                <span className="text-ink-400 font-normal">({observations.length})</span>
              </div>
              <select
                className={`${selectClass} w-44`}
                value={confidenceFilter}
                onChange={(e) => setConfidenceFilter(e.target.value)}
              >
                <option value="all">{t("allConfidence")}</option>
                <option value="HIGH">{t("highOnly")}</option>
                <option value="MEDIUM">{t("mediumUp")}</option>
                <option value="LOW">{t("lowUp")}</option>
              </select>
            </div>

            {loading ? (
              <Spinner label={t("loading")} />
            ) : observations.length === 0 ? (
              <Empty title={t("noObservations")} />
            ) : (
              <div className="overflow-x-auto max-h-[640px] overflow-y-auto">
                <table className="w-full text-[13px]">
                  <thead className="sticky top-0 bg-ink-50">
                    <tr className="border-b border-ink-200">
                      {[tc("stayDate"), t("competitor"), t("category"), t("price"), t("basis"), t("confidence"), tc("source"), ""].map((h) => (
                        <th
                          key={h}
                          className={`px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-500 ${
                            h === t("price") ? "text-right" : "text-left"
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
                        <td className="px-3 py-2 text-[12px] text-ink-500">{o.room_category || "—"}</td>
                        <td className="px-3 py-2 text-right tnum font-medium text-ink-900 whitespace-nowrap">
                          {formatVND(o.observed_price)}
                        </td>
                        <td className="px-3 py-2 text-[11px] text-ink-500">{tv(`priceBasis.${o.price_basis}`)}</td>
                        <td className="px-3 py-2">
                          <Chip tone={confidenceTone(o.confidence)} title={confidenceText(o)}>
                            {o.confidence}
                          </Chip>
                        </td>
                        <td className="px-3 py-2 text-[11px] text-ink-400 whitespace-nowrap">
                          {o.source}
                          <div>{formatDateTime(o.observed_at)}</div>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button
                            onClick={() => api.deleteObservation(o.id).then(load)}
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
      )}
    </div>
  );
}
