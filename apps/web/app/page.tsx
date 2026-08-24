"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Filters, type FilterState } from "@/components/Filters";
import { RecommendationDrawer } from "@/components/RecommendationDrawer";
import { RecommendationTable } from "@/components/RecommendationTable";
import { StatusBanner } from "@/components/StatusBanner";
import { SummaryCards } from "@/components/SummaryCards";
import { Button, Card, Empty, PageHeader, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { addDaysISO, todayISO } from "@/lib/format";
import type { Property, Recommendation, Summary, SystemStatus } from "@/lib/types";

const PAGE_SIZE = 45;

export default function RateReviewPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [busy, setBusy] = useState(false);

  const [filters, setFilters] = useState<FilterState>(() => ({
    roomTypeId: null,
    roomCategory: "all",
    startDate: todayISO(),
    endDate: addDaysISO(todayISO(), 30),
    status: "all",
    search: "",
  }));

  // Debounced separately from the rest of the filters: dropdowns and dates
  // should apply immediately, but free-text search should not fire a request
  // per keystroke.
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setDebouncedSearch(filters.search), 300);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [filters.search]);

  const query = useMemo(
    () => ({
      room_type_id: filters.roomTypeId,
      start_date: filters.startDate || null,
      end_date: filters.endDate || null,
      status: filters.status,
      search: debouncedSearch || null,
    }),
    [filters.roomTypeId, filters.startDate, filters.endDate, filters.status, debouncedSearch],
  );

  const load = useCallback(async () => {
    setError(null);
    try {
      const [recs, sum] = await Promise.all([api.recommendations(query), api.summary(query)]);
      setRecommendations(recs);
      setSummary(sum);
    } catch (e: any) {
      setError(
        e?.message?.includes("fetch")
          ? "Cannot reach the pricing API. Is the backend running on port 8000?"
          : e.message,
      );
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
    api.properties().then(setProperties).catch(() => setProperties([]));
  }, []);

  useEffect(() => {
    setVisible(PAGE_SIZE);
    load();
  }, [load]);

  const regenerate = async () => {
    setBusy(true);
    try {
      await api.generate();
      await load();
      setStatus(await api.status());
    } finally {
      setBusy(false);
    }
  };

  const shown = recommendations.slice(0, visible);

  return (
    <div className="px-7 py-6 space-y-5 max-w-[1700px]">
      <PageHeader
        title="Rate review"
        subtitle="Recommended NET rates by room category and stay date, anchored to Luminous' validated seasonal rate book. Review the reasoning, then accept or set your own."
        actions={
          <Button variant="secondary" onClick={regenerate} disabled={busy}>
            {busy ? "Recalculating…" : "Recalculate"}
          </Button>
        }
      />

      <StatusBanner status={status} />
      <SummaryCards summary={summary} />

      <Card className="p-4">
        <Filters properties={properties} value={filters} onChange={setFilters} />
      </Card>

      <Card>
        {loading ? (
          <Spinner label="Loading recommendations…" />
        ) : error ? (
          <div className="p-6">
            <div className="rounded-lg bg-rose-50 border border-rose-200 px-4 py-3 text-[13px] text-rose-700">
              {error}
            </div>
          </div>
        ) : recommendations.length === 0 ? (
          <Empty
            title="No recommendations match these filters"
            hint="Try widening the date range or clearing the room category filter."
          />
        ) : (
          <>
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-ink-200">
              <div className="text-[12px] text-ink-500">
                Showing <span className="font-medium text-ink-700">{shown.length}</span> of{" "}
                <span className="font-medium text-ink-700">{recommendations.length}</span> room-type
                nights
              </div>
            </div>
            <RecommendationTable
              recommendations={shown}
              onSelect={(r) => setSelectedId(r.id)}
              selectedId={selectedId}
            />
            {visible < recommendations.length && (
              <div className="p-3 text-center border-t border-ink-100">
                <Button size="sm" onClick={() => setVisible((v) => v + PAGE_SIZE)}>
                  Show {Math.min(PAGE_SIZE, recommendations.length - visible)} more
                </Button>
              </div>
            )}
          </>
        )}
      </Card>

      <RecommendationDrawer
        recommendationId={selectedId}
        status={status}
        onClose={() => setSelectedId(null)}
        onChanged={load}
      />
    </div>
  );
}
