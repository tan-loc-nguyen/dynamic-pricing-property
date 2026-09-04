import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithIntl } from "./test-utils";
import { Spinner } from "./Spinner";

describe("Spinner", () => {
  it("renders the translated default loading label when no label is given", () => {
    renderWithIntl(<Spinner />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders a custom label instead of the default when given one", () => {
    renderWithIntl(<Spinner label="Fetching rates…" />);
    expect(screen.getByText("Fetching rates…")).toBeInTheDocument();
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
  });

  it("renders the spinner icon", () => {
    renderWithIntl(<Spinner />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
