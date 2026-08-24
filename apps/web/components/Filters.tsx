"use client";

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
  const roomTypes = properties.flatMap((p) => p.room_types);
  const set = (patch: Partial<FilterState>) => onChange({ ...value, ...patch });

  return (
    <div className="flex flex-wrap items-end gap-2.5">
      {/* Binds room TYPE, not category. Luminous has one room type per category,
          so the label is the honest thing to show the operator. The API also
          accepts room_category for clients that need it. */}
      <div className="w-56">
        <div className="text-[11px] font-medium text-ink-500 mb-1">Room category</div>
        <select
          className={inputClass}
          value={value.roomTypeId ?? ""}
          onChange={(e) => set({ roomTypeId: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">All room categories</option>
          {roomTypes.map((rt) => (
            <option key={rt.id} value={rt.id}>
              {rt.category_label} ({rt.units_total} units)
            </option>
          ))}
        </select>
      </div>

      <div className="w-36">
        <div className="text-[11px] font-medium text-ink-500 mb-1">From</div>
        <input type="date" className={inputClass} value={value.startDate} onChange={(e) => set({ startDate: e.target.value })} />
      </div>
      <div className="w-36">
        <div className="text-[11px] font-medium text-ink-500 mb-1">To</div>
        <input type="date" className={inputClass} value={value.endDate} onChange={(e) => set({ endDate: e.target.value })} />
      </div>

      <div className="w-40">
        <div className="text-[11px] font-medium text-ink-500 mb-1">Status</div>
        <select className={inputClass} value={value.status} onChange={(e) => set({ status: e.target.value })}>
          <option value="all">All statuses</option>
          <option value="pending">Pending</option>
          <option value="accepted">Accepted</option>
          <option value="overridden">Overridden</option>
          <option value="error">Could not price</option>
        </select>
      </div>

      <div className="flex-1 min-w-40">
        <div className="text-[11px] font-medium text-ink-500 mb-1">Search</div>
        <input
          className={inputClass}
          placeholder="Room category or season…"
          value={value.search}
          onChange={(e) => set({ search: e.target.value })}
        />
      </div>
    </div>
  );
}
