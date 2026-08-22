"use client";

import { inputClass } from "./ui";
import type { Property } from "@/lib/types";

export interface FilterState {
  propertyId: number | null;
  roomId: number | null;
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
  const rooms = value.propertyId
    ? properties.find((p) => p.id === value.propertyId)?.rooms || []
    : properties.flatMap((p) => p.rooms);

  const set = (patch: Partial<FilterState>) => onChange({ ...value, ...patch });

  return (
    <div className="flex flex-wrap items-end gap-2.5">
      <div className="w-52">
        <div className="text-[11px] font-medium text-ink-500 mb-1">Property</div>
        <select
          className={inputClass}
          value={value.propertyId ?? ""}
          onChange={(e) =>
            set({ propertyId: e.target.value ? Number(e.target.value) : null, roomId: null })
          }
        >
          <option value="">All properties</option>
          {properties.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      <div className="w-52">
        <div className="text-[11px] font-medium text-ink-500 mb-1">Room</div>
        <select
          className={inputClass}
          value={value.roomId ?? ""}
          onChange={(e) => set({ roomId: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">All rooms</option>
          {rooms.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
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
        </select>
      </div>

      <div className="flex-1 min-w-40">
        <div className="text-[11px] font-medium text-ink-500 mb-1">Search</div>
        <input
          className={inputClass}
          placeholder="Room or property name…"
          value={value.search}
          onChange={(e) => set({ search: e.target.value })}
        />
      </div>
    </div>
  );
}
