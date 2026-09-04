import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

describe("vitest + react-testing-library harness", () => {
  it("renders a component and queries it via jsdom", () => {
    render(<div>harness ok</div>);
    expect(screen.getByText("harness ok")).toBeInTheDocument();
  });
});
