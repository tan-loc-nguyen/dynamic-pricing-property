import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PageHeader } from "./PageHeader";

describe("PageHeader", () => {
  it("renders the title", () => {
    render(<PageHeader title="Rate" />);
    expect(screen.getByText("Rate")).toBeInTheDocument();
  });

  it("omits the subtitle when none is given", () => {
    const { container } = render(<PageHeader title="Rate" />);
    expect(container.querySelectorAll("p").length).toBe(0);
  });

  it("renders the subtitle when given one", () => {
    render(<PageHeader title="Rate" subtitle="Pick the nights" />);
    expect(screen.getByText("Pick the nights")).toBeInTheDocument();
  });

  it("renders actions when given some", () => {
    render(<PageHeader title="Rate" actions={<button>Export</button>} />);
    expect(screen.getByRole("button", { name: "Export" })).toBeInTheDocument();
  });
});
