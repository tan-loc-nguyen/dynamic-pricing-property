import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Empty } from "./Empty";

describe("Empty", () => {
  it("renders the title", () => {
    render(<Empty title="Nothing to price for these nights" />);
    expect(screen.getByText("Nothing to price for these nights")).toBeInTheDocument();
  });

  it("omits the hint when none is given", () => {
    const { container } = render(<Empty title="No data" />);
    expect(container.querySelectorAll('[data-slot="empty-description"]').length).toBe(0);
  });

  it("renders the hint when given one", () => {
    render(<Empty title="No data" hint="Run a pricing update, or choose a different range." />);
    expect(
      screen.getByText("Run a pricing update, or choose a different range.")
    ).toBeInTheDocument();
  });

  it("renders an icon", () => {
    const { container } = render(<Empty title="No data" />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});
