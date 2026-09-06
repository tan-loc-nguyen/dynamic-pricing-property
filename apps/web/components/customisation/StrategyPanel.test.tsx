import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithIntl } from "@/components/test-utils";

// The panel loads its own configuration and preview on mount, so both calls are
// mocked. CONFIG_PAYLOAD is a FULL config: the panel reads every section
// directly (draft.pace.bands, draft.rounding.increment, ...) and a partial
// fixture throws before anything renders.
const CONFIG_PAYLOAD = {
  schema_version: 3,
  label: "test-defaults",
  currency: "VND",
  mode: "shadow",
  rounding: { increment: 10000, mode: "nearest" },
  dynamic: { max_total_adjustment_pct: 15, min_total_adjustment_pct: -15 },
  pace: {
    enabled: true,
    bands: [{ key: "on_pace", label: "On pace", max_gap: 0.08, adjustment_pct: 0 }],
  },
  recent_pickup: {
    enabled: true,
    lookback_days: 7,
    expected_pickup_per_window: 1,
    bands: [
      { key: "as_expected", label: "Pickup as expected", max_delta: 0.5, adjustment_pct: 0 },
    ],
  },
  event: { enabled: true, impact_adjustment_pct: { low: 3, medium: 8, high: 15 } },
  market: {
    enabled: true,
    min_confidence: "MEDIUM",
    min_observations: 2,
    observation_max_age_days: 14,
    sensitivity: 0.5,
    max_adjustment_pct: 5,
  },
  day_of_week: {
    enabled: true,
    adjustment_pct: {
      monday: 0,
      tuesday: 0,
      wednesday: 0,
      thursday: 0,
      friday: 0,
      saturday: 0,
      sunday: 0,
    },
  },
  booking_curve: { provider: "demo", anchors: null, season_pace: null, category_pace: null },
};

const PREVIEW = {
  problems: [],
  room_type_id: 1,
  room_type_name: "2BR Regular",
  room_category_label: "2BR Regular",
  room_category: "2br_regular",
  stay_date: "2026-09-10",
  currency: "VND",
  season_label: "Low Season 2",
  season_key: "low_2",
  band_min_net_rate: 1800000,
  band_base_net_rate: 2100000,
  band_max_net_rate: 2300000,
  base_net_rate: 2100000,
  current_net_rate: 2100000,
  recommended_net_rate: 2100000,
  change_pct: 0,
  total_adjustment_pct: 0,
  adjustments: [],
  engine_version: "1.0.0",
};

vi.mock("@/lib/api", () => ({
  api: {
    config: () =>
      Promise.resolve({
        version: 1,
        label: "test-defaults",
        payload: CONFIG_PAYLOAD,
        is_active: true,
        created_at: "2026-09-06T00:00:00",
        note: null,
      }),
    preview: () => Promise.resolve(PREVIEW),
    saveConfig: () => Promise.resolve({}),
    resetConfig: () => Promise.resolve({}),
  },
}));

import { StrategyPanel } from "./StrategyPanel";

describe("StrategyPanel — the pickup window", () => {
  it("offers only the range the backend accepts", async () => {
    renderWithIntl(<StrategyPanel onOpenSeasonal={() => {}} />);

    const input = await screen.findByLabelText("Lookback window (days)");
    expect(input).toHaveAttribute("min", "7");
    expect(input).toHaveAttribute("max", "14");
    expect(input).toHaveAttribute("step", "1");
  });
});
