import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithIntl } from "../test-utils";
import { RangeDrawer } from "./RangeDrawerShell";
import type { RangeDetail, RangeNight } from "@/lib/types";

const nightAt = (day: number, over: Partial<RangeNight> = {}): RangeNight => ({
  stay_date: `2026-09-0${day}`,
  units_sold: 4,
  units_total: 8,
  recommended_net_rate: 2_000_000 + day * 10_000,
  current_net_rate: 2_100_000,
  base_net_rate: 2_000_000,
  priced: true,
  days_to_arrival: day,
  expected_occupancy: 0.6,
  occupancy: 0.5,
  band: { min: 1_800_000, base: 2_000_000, max: 2_300_000 },
  rate_provenance: "published",
  decision: null,
  clamped: null,
  delta_vs_average_pct: day,
  adjustments: [
    {
      code: "pace",
      label: "Pace",
      label_key: "adjustments.pace.behind",
      delta: -10_000,
      // The full set the sentence interpolates, not just nights_covered. ICU
      // refuses a message with an argument missing and lib/adjustments.ts
      // catches that by dropping the whole sentence -- so a thinner fixture
      // silently exercises the failure path and buries the run in stack
      // traces instead of rendering what the drawer really shows.
      params: {
        nights_covered: 1,
        occupancy: 0.5,
        expected_occupancy: 0.6,
        days_to_arrival: day,
        gap_pp: 10,
        direction: "behind",
      },
      is_neutral: false,
      is_ignored: false,
      nights_covered: 1,
    },
  ],
  ...over,
});

const detail = (over: Partial<RangeDetail> = {}): RangeDetail =>
  ({
    room_type_id: 2,
    room_type_name: "2BR Premium",
    room_category: "2br_premium",
    room_category_label: "2BR Premium",
    start_date: "2026-09-01",
    end_date: "2026-09-03",
    nights: 3,
    season: { key: "low_2", label: "Low 2", start: "2026-09-01", end: "2026-10-31" },
    base_net_rate: 2_000_000,
    average_recommended_net_rate: 2_020_000,
    average_current_net_rate: 2_100_000,
    band: { min: 1_800_000, base: 2_000_000, max: 2_300_000 },
    adjustments: [],
    nightly: [nightAt(1), nightAt(2), nightAt(3)],
    pace_gap: -0.1,
    units_sold: 12,
    units_total: 8,
    available_units: 4,
    availability_is_exact: true,
    unpriced_nights: 0,
    rate_provenance: "published",
    ...over,
  }) as RangeDetail;

const acceptRange = vi.fn().mockResolvedValue({});
const overrideRange = vi.fn().mockResolvedValue({});
let payload: RangeDetail;

vi.mock("@/lib/api", () => ({
  api: {
    status: () => Promise.resolve({ override_reasons: [{ code: "my_judgment" }] }),
    rateRange: () => Promise.resolve(payload),
    observations: () => Promise.resolve([]),
    acceptRange: (...a: unknown[]) => acceptRange(...a),
    overrideRange: (...a: unknown[]) => overrideRange(...a),
  },
}));

const selection = { roomTypeId: 2, startDate: "2026-09-01", endDate: "2026-09-03" };

describe("RangeDrawer", () => {
  beforeEach(() => {
    payload = detail();
    acceptRange.mockClear();
    overrideRange.mockClear();
  });

  it("opens on the range scope and accepts every night", async () => {
    renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    const button = await screen.findByRole("button", { name: /3 nights/i });
    await userEvent.click(button);
    expect(acceptRange).toHaveBeenCalledWith(2, "2026-09-01", "2026-09-03", true);
  });

  it("does not explain the price in the range scope", async () => {
    // The averaged breakdown fragmented one factor into a row per label
    // variant -- five pace rows for seven nights. The explanation lives in
    // the night scope, where every row describes exactly one night.
    renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    await screen.findByText("2BR Premium");
    expect(screen.queryByText("Why the price moved")).toBeNull();
    expect(screen.queryByText(/show the reasoning/i)).toBeNull();
  });

  it("explains the price in the night scope", async () => {
    renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    await userEvent.click(await screen.findByRole("tab", { name: /night by night/i }));
    expect(screen.getByText("Why the price moved")).toBeTruthy();
    expect(screen.getByText(/show the reasoning/i)).toBeTruthy();
  });

  it("draws the booking curve in both scopes", async () => {
    renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    // Range: peers only, so the caption must not promise a marker.
    expect(await screen.findByText(/each point is a different night/i)).toBeTruthy();
    expect(screen.queryByText(/with the dot marking this one/i)).toBeNull();

    await userEvent.click(screen.getByRole("tab", { name: /night by night/i }));
    // Night: the selected night is marked, which the caption may now promise.
    expect(screen.getByText(/with the dot marking this one/i)).toBeTruthy();
  });

  it("hides the scope switch when the range is a single night", async () => {
    payload = detail({ nights: 1, end_date: "2026-09-01", nightly: [nightAt(1)] });
    renderWithIntl(
      <RangeDrawer
        selection={{ ...selection, endDate: "2026-09-01" }}
        onClose={() => {}}
        onChanged={() => {}}
      />,
    );
    await screen.findByText("2BR Premium");
    expect(screen.queryByRole("tab", { name: /night by night/i })).toBeNull();
  });

  // NightPicker's chips are the only elements carrying aria-pressed, which
  // makes them addressable without depending on how a date is formatted.
  const nightChips = (c: HTMLElement) =>
    Array.from(c.querySelectorAll<HTMLElement>("[aria-pressed]"));

  it("accepts only the selected night in the night scope", async () => {
    const { container } = renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    await userEvent.click(await screen.findByRole("tab", { name: /night by night/i }));
    await userEvent.click(nightChips(container)[1]);
    await userEvent.click(
      await screen.findByRole("button", { name: /accept .* for/i }),
    );
    expect(acceptRange).toHaveBeenCalledWith(2, "2026-09-02", "2026-09-02", true);
  });

  it("withdraws the accept action on an unpriced night", async () => {
    payload = detail({
      nightly: [nightAt(1), nightAt(2, { priced: false }), nightAt(3)],
      unpriced_nights: 1,
    });
    const { container } = renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    await userEvent.click(await screen.findByRole("tab", { name: /night by night/i }));
    await userEvent.click(nightChips(container)[1]);
    expect(screen.queryByRole("button", { name: /accept .* for/i })).toBeNull();
  });

  it("warns before a bulk accept would replace a hand-tuned night", async () => {
    payload = detail({
      nightly: [nightAt(1), nightAt(2, { decision: "overridden" }), nightAt(3)],
    });
    renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    expect(await screen.findByText(/priced by hand will be kept/i)).toBeTruthy();
    // The button names what it will actually write, not what was selected.
    expect(screen.getByRole("button", { name: /2 nights/i })).toBeTruthy();
  });

  it("lets the operator overwrite hand-tuned nights on purpose", async () => {
    payload = detail({
      nightly: [nightAt(1), nightAt(2, { decision: "overridden" }), nightAt(3)],
    });
    renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: /overwrite them too/i }),
    );
    await userEvent.click(screen.getByRole("button", { name: /3 nights/i }));
    expect(acceptRange).toHaveBeenCalledWith(2, "2026-09-01", "2026-09-03", false);
  });

  it("does not warn when nothing was priced by hand", async () => {
    renderWithIntl(
      <RangeDrawer selection={selection} onClose={() => {}} onChanged={() => {}} />,
    );
    await screen.findByText("2BR Premium");
    expect(screen.queryByText(/priced by hand/i)).toBeNull();
  });
});
