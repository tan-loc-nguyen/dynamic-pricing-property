import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithIntl } from "./test-utils";
import { OccupancyStrip, PriceContribution } from "./viz";
import type { ExplainedStep } from "@/lib/types";

const night = (day: number, over: Partial<any> = {}) => ({
  stay_date: `2026-09-0${day}`,
  units_sold: 4,
  units_total: 8,
  priced: true,
  decision: null,
  delta_vs_average_pct: 0,
  ...over,
});

describe("OccupancyStrip", () => {
  it("is inert when no selection handler is given", () => {
    renderWithIntl(<OccupancyStrip nights={[night(1), night(2)]} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("becomes a list of buttons when a night can be picked", async () => {
    const onSelect = vi.fn();
    renderWithIntl(
      <OccupancyStrip
        nights={[night(1), night(2)]}
        selected="2026-09-01"
        onSelect={onSelect}
      />,
    );
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2);
    await userEvent.click(buttons[1]);
    expect(onSelect).toHaveBeenCalledWith("2026-09-02");
  });

  it("marks the selected night without changing the bar it draws", () => {
    const { container } = renderWithIntl(
      <OccupancyStrip
        nights={[night(1, { units_sold: 4 }), night(2, { units_sold: 4 })]}
        selected="2026-09-01"
        onSelect={() => {}}
      />,
    );
    // Both nights sold the same, so both bars must still be the same height:
    // selection is an outline, never a change to the data encoding.
    const bars = Array.from(
      container.querySelectorAll<HTMLElement>("[data-bar]"),
    );
    expect(bars[0].style.height).toBe(bars[1].style.height);
    expect(bars[0].className).toBe(bars[1].className);
  });

  it("marks a hand-tuned night so a bulk accept is not a surprise", () => {
    const { container } = renderWithIntl(
      <OccupancyStrip
        nights={[night(1, { decision: "overridden" }), night(2)]}
        onSelect={() => {}}
      />,
    );
    expect(container.querySelectorAll("[data-hand-tuned]")).toHaveLength(1);
  });

  it("shows how far each night sits from the range average", () => {
    renderWithIntl(
      <OccupancyStrip
        nights={[
          night(1, { delta_vs_average_pct: 10.4 }),
          night(2, { delta_vs_average_pct: -8.7 }),
        ]}
        showDeltas
      />,
    );
    // Matched loosely on purpose: formatAdjPct owns the sign, separator and
    // precision, and this test is about the delta being SHOWN, not about how
    // that helper formats. Asserting the exact string here would make a
    // formatting change look like a regression in the strip.
    expect(screen.getByText(/10[.,]4/)).toBeTruthy();
    expect(screen.getByText(/8[.,]7/)).toBeTruthy();
  });
});

const step = (over: Partial<ExplainedStep> = {}): ExplainedStep => ({
  code: "pace",
  label: "Pace",
  label_key: "adjustments.pace.behind",
  delta: -1000,
  params: {},
  is_neutral: false,
  is_ignored: false,
  nights_covered: 1,
  ...over,
});

describe("PriceContribution", () => {
  const render = (a: ExplainedStep) => ({ label: a.label, reason: "" });

  it("badges a row that does not describe the whole range", () => {
    renderWithIntl(
      <PriceContribution
        adjustments={[step({ nights_covered: 2, label: "Behind" })]}
        render={render}
        totalNights={7}
      />,
    );
    expect(screen.getByText("2 nights")).toBeTruthy();
  });

  it("badges a row that covers every night too", () => {
    // Every row carries its own count so none has to be inferred from the
    // absence of one, and so the counts visibly add up across the rows a
    // single factor was split into.
    renderWithIntl(
      <PriceContribution
        adjustments={[step({ nights_covered: 7, label: "Market" })]}
        render={render}
        totalNights={7}
      />,
    );
    expect(screen.getByText("7 nights")).toBeTruthy();
  });

  it("badges nothing when the scope is a single night", () => {
    renderWithIntl(
      <PriceContribution
        adjustments={[step({ nights_covered: 1 })]}
        render={render}
        totalNights={1}
      />,
    );
    expect(screen.queryByText(/night/)).toBeNull();
  });
});
