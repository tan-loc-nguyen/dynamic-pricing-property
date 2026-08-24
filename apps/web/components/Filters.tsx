"use client";

import { useTranslations } from "next-intl";

import { inputClass } from "./ui";
import type { Property } from "@/lib/types";

export interface FilterState {
  roomTypeId: number | null;
  startDate: string;
  endDate: string;
  status: string;
  search: string;
}

export function Filters({
  properties,
  value,
  onChange,
}: {
  properties: Property[];
  value: FilterState;
  onChange: (next: FilterState) => void;
}) {
  const t = useTranslations("filters");
  const tv = useTranslations("vocab");
  const ts = useTranslations("status");
  const roomTypes = properties.flatMap((p) => p.room_types);
  const set = (patch: Partial<FilterState>) => onChange({ ...value, ...patch });

  return (
    <div className="flex flex-wrap items-end gap-2.5">
      {/* Binds room TYPE, not category. Luminous has one room type per category,
          so the label is the honest thing to show the operator. The API also
          accepts room_category for clients that need it. */}
      <div className="w-56">
        <div className="text-[11px] font-medium text-ink-500 mb-1">{t("roomCategory")}</div>
        <select
          className={inputClass}
          value={value.roomTypeId ?? ""}
          onChange={(e) => set({ roomTypeId: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">{t("allRoomCategories")}</option>
          {roomTypes.map((rt) => (
            <option key={rt.id} value={rt.id}>
              {t("categoryOption", {
                category: tv(`roomCategories.${rt.category}`),
                units: rt.units_total,
              })}
            </option>
          ))}
        </select>
      </div>

      <div className="w-36">
        <div className="text-[11px] font-medium text-ink-500 mb-1">{t("from")}</div>
        <input type="date" className={inputClass} value={value.startDate} onChange={(e) => set({ startDate: e.target.value })} />
      </div>
      <div className="w-36">
        <div className="text-[11px] font-medium text-ink-500 mb-1">{t("to")}</div>
        <input type="date" className={inputClass} value={value.endDate} onChange={(e) => set({ endDate: e.target.value })} />
      </div>

      <div className="w-40">
        <div className="text-[11px] font-medium text-ink-500 mb-1">{t("status")}</div>
        <select className={inputClass} value={value.status} onChange={(e) => set({ status: e.target.value })}>
          <option value="all">{t("allStatuses")}</option>
          <option value="pending">{ts("pending")}</option>
          <option value="accepted">{ts("accepted")}</option>
          <option value="overridden">{ts("overridden")}</option>
          <option value="error">{ts("error")}</option>
        </select>
      </div>

      <div className="flex-1 min-w-40">
        <div className="text-[11px] font-medium text-ink-500 mb-1">{t("search")}</div>
        <input
          className={inputClass}
          placeholder={t("searchPlaceholder")}
          value={value.search}
          onChange={(e) => set({ search: e.target.value })}
        />
      </div>
    </div>
  );
}
