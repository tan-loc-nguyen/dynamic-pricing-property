"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type Row = { id: string; name: string; category: string };

/**
 * Blue Jay room type -> our pricing category.
 *
 * Keyed by Blue Jay's roomtypeId, never by its display name: a reservation
 * references its room type by localised name only, and those names are
 * editable in Blue Jay's UI. Mapping on the id means a rename cannot silently
 * unmap a whole category.
 *
 * The panel shows DISCOVERED room types alongside mapped ones. Reading only
 * the persisted map meant it could show what was already done and never the
 * room type going unpriced right now — which is the only reason to open it.
 *
 * Unmapping is by OMISSION: a row with no category is left out of the payload.
 * The previous "Not mapped" option sent an empty string, which the API rejects
 * with a 422, and there was no path that removed a key at all.
 */
export function RoomTypeMapPanel() {
  const t = useTranslations("dataSource");
  const tv = useTranslations("vocab");
  const [rows, setRows] = useState<Row[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const body = await api.categoryMap();
      const mapped: Row[] = Object.entries(body.map).map(([id, category]) => ({
        id,
        name: "",
        category,
      }));
      const discovered: Row[] = (body.unmapped ?? [])
        .filter((u) => !(u.id in body.map))
        .map((u) => ({ id: u.id, name: u.name, category: "" }));
      // Unmapped first: they are the ones costing money right now.
      setRows([...discovered, ...mapped]);
      setCategories(body.categories);
      setError(null);
    } catch {
      setError(t("saveFailed"));
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const update = (index: number, category: string) => {
    setSaved(false);
    setRows((current) => current.map((r, i) => (i === index ? { ...r, category } : r)));
  };

  const save = async () => {
    if (busy) return; // a double-click used to fire two PUTs
    setBusy(true);
    setError(null);
    try {
      // Only rows WITH a category. Omission is what unmapping means.
      const payload = Object.fromEntries(
        rows.filter((r) => r.category).map((r) => [r.id, r.category]),
      );
      await api.setCategoryMap(payload);
      setSaved(true);
      await load();
    } catch {
      // Previously absent, so a 422 produced no error, no confirmation, and
      // nothing distinguishable from a button that was never wired up.
      setError(t("saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-4">
      <h2 className="text-[12.5px] font-semibold text-ink-800">{t("mapTitle")}</h2>
      <p className="mt-1 text-[11.5px] leading-relaxed text-ink-500">{t("mapIntro")}</p>

      {rows.length === 0 ? (
        <p className="mt-3 rounded-lg border border-dashed border-ink-200 px-3 py-4 text-center text-[11.5px] text-ink-500">
          {t("mapEmpty")}
        </p>
      ) : (
        <>
          <ul className="mt-3 space-y-2">
            {rows.map((row, index) => (
              <li key={row.id} className="flex items-center justify-between gap-3">
                <span className="min-w-0">
                  {/* Real-world data: a Blue Jay room-type name is never
                      translated. The id alone was unreadable, and mapping the
                      wrong one misprices a whole category. */}
                  <span className="block truncate text-[12px] text-ink-800">
                    {row.name || <code className="text-[11px]">{row.id}</code>}
                  </span>
                  {row.name && (
                    <code className="text-[10.5px] text-ink-400">{row.id}</code>
                  )}
                  {!row.category && (
                    <span className="block text-[10.5px] text-amber-700">
                      {t("mapNeedsAttention")}
                    </span>
                  )}
                </span>
                <select
                  aria-label={row.name || row.id}
                  value={row.category}
                  onChange={(e) => update(index, e.target.value)}
                  disabled={busy}
                  className="shrink-0 rounded-md border border-ink-200 px-2 py-1 text-[11.5px]"
                >
                  <option value="">{t("mapChoose")}</option>
                  {categories.map((key) => (
                    <option key={key} value={key}>
                      {tv(`roomCategories.${key}`)}
                    </option>
                  ))}
                </select>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex items-center gap-3">
            <Button variant="secondary" onClick={save} disabled={busy}>
              {t("mapSave")}
            </Button>
            {saved && !error && (
              <span className="text-[11px] text-emerald-700">{t("mapSaved")}</span>
            )}
            {error && <span className="text-[11px] text-amber-700">{error}</span>}
          </div>
        </>
      )}
    </Card>
  );
}
