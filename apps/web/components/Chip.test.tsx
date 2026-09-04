import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Chip } from "./Chip";

describe("Chip", () => {
  it("renders its children as text content", () => {
    render(<Chip>+4.2%</Chip>);
    expect(screen.getByText("+4.2%")).toBeInTheDocument();
  });

  it("defaults to the neutral tone", () => {
    render(<Chip>label</Chip>);
    expect(screen.getByText("label")).toHaveAttribute("data-tone", "neutral");
  });

  it.each(["up", "down", "warn", "info"] as const)(
    "applies the %s tone via data-tone",
    (tone) => {
      render(<Chip tone={tone}>label</Chip>);
      expect(screen.getByText("label")).toHaveAttribute("data-tone", tone);
    }
  );

  it("forwards the title attribute for hover text", () => {
    render(<Chip title="why this changed">label</Chip>);
    expect(screen.getByText("label")).toHaveAttribute("title", "why this changed");
  });
});
