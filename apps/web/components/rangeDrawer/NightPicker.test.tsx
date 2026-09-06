import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithIntl } from "../test-utils";
import { NightPicker } from "./NightPicker";
import type { RangeNight } from "@/lib/types";

const night = (day: number, over: Partial<RangeNight> = {}): RangeNight =>
  ({
    stay_date: `2026-09-0${day}`,
    units_sold: 4,
    units_total: 8,
    recommended_net_rate: 2_000_000 + day * 100_000,
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
    delta_vs_average_pct: 0,
    adjustments: [],
    ...over,
  }) as RangeNight;

describe("NightPicker", () => {
  it("offers one button per night", () => {
    renderWithIntl(
      <NightPicker
        nights={[night(1), night(2), night(3)]}
        selected="2026-09-01"
        onSelect={() => {}}
      />,
    );
    expect(screen.getAllByRole("button")).toHaveLength(3);
  });

  it("reports which night is showing", () => {
    renderWithIntl(
      <NightPicker
        nights={[night(1), night(2)]}
        selected="2026-09-02"
        onSelect={() => {}}
      />,
    );
    const pressed = screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-pressed") === "true");
    expect(pressed).toHaveLength(1);
    expect(pressed[0].getAttribute("aria-label")).toContain("Sep 2");
  });

  it("hands back the night that was clicked", async () => {
    const onSelect = vi.fn();
    renderWithIntl(
      <NightPicker
        nights={[night(1), night(2)]}
        selected="2026-09-01"
        onSelect={onSelect}
      />,
    );
    await userEvent.click(screen.getAllByRole("button")[1]);
    expect(onSelect).toHaveBeenCalledWith("2026-09-02");
  });

  it("shows each night's own price, not the range average", () => {
    renderWithIntl(
      <NightPicker
        nights={[night(1), night(2)]}
        selected="2026-09-01"
        onSelect={() => {}}
      />,
    );
    // The price is what makes a night worth opening, so it has to be legible
    // without clicking. Matched loosely: formatVND owns the compact unit.
    expect(screen.getByText(/2[.,]1/)).toBeTruthy();
    expect(screen.getByText(/2[.,]2/)).toBeTruthy();
  });

  it("says a night has no price rather than showing a fabricated one", () => {
    renderWithIntl(
      <NightPicker
        nights={[night(1), night(2, { priced: false })]}
        selected="2026-09-01"
        onSelect={() => {}}
      />,
    );
    const unpriced = screen
      .getAllByRole("button")
      .find((b) => b.getAttribute("aria-label")?.includes("no price yet"));
    expect(unpriced).toBeTruthy();
    expect(unpriced!.textContent).toContain("—");
  });

  it("marks a hand-tuned night, so a night already priced by hand is visible", () => {
    const { container } = renderWithIntl(
      <NightPicker
        nights={[night(1), night(2, { decision: "overridden" })]}
        selected="2026-09-01"
        onSelect={() => {}}
      />,
    );
    expect(container.querySelectorAll("[data-hand-tuned]")).toHaveLength(1);
  });

  it("offers a hover affordance on every night it is not already showing", () => {
    renderWithIntl(
      <NightPicker
        nights={[night(1), night(2)]}
        selected="2026-09-01"
        onSelect={() => {}}
      />,
    );
    // The whole reason this component exists: the old chart had no hover state
    // at all, so nothing said it could be clicked until after the click.
    const [current, other] = screen.getAllByRole("button");
    expect(other.className).toMatch(/hover:/);
    expect(current.getAttribute("aria-pressed")).toBe("true");
  });
});
