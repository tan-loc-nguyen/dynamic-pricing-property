import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
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
  it("is a chart, never a control", () => {
    // It used to be clickable, and that was the bug: varying bar heights read
    // as a visualisation, so the drawer's only way to change night was
    // invisible. Picking a night is NightPicker's job now.
    renderWithIntl(
      <OccupancyStrip nights={[night(1), night(2)]} selected="2026-09-01" />,
    );
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByRole("img")).toBeTruthy();
  });

  it("marks the selected night without changing the bar it draws", () => {
    const { container } = renderWithIntl(
      <OccupancyStrip
        nights={[night(1, { units_sold: 4 }), night(2, { units_sold: 4 })]}
        selected="2026-09-01"
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
      <OccupancyStrip nights={[night(1, { decision: "overridden" }), night(2)]} />,
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

  it("lists every step, including the ones that changed nothing", () => {
    // "measured, no effect" and "not measured" are different answers, so a
    // zero-delta step is still a row rather than an omission.
    renderWithIntl(
      <PriceContribution
        adjustments={[
          step({ label: "Seasonal base rate", delta: 0 }),
          step({ label: "Market signal", delta: -87_000 }),
        ]}
        render={render}
      />,
    );
    expect(screen.getByText("Seasonal base rate")).toBeTruthy();
    expect(screen.getByText("Market signal")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
  });

  it("does not badge rows with a night count", () => {
    // Badges existed only because the RANGE breakdown split one factor across
    // several rows. Only the night scope explains a price now, and every row
    // there covers exactly the one night.
    renderWithIntl(
      <PriceContribution
        adjustments={[step({ nights_covered: 1, label: "Behind" })]}
        render={render}
      />,
    );
    expect(screen.queryByText(/night/i)).toBeNull();
  });
});
