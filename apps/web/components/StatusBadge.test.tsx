import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithIntl } from "./test-utils";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the translated label for a known status", () => {
    renderWithIntl(<StatusBadge status="pending" />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  // Regression guard: "error" was once missing from the Status union, which made
  // TypeScript treat this branch as dead code and silently dropped the "Unpriced"
  // label. See lib/types.ts Status.
  it("renders the translated label for the error status", () => {
    renderWithIntl(<StatusBadge status="error" />);
    expect(screen.getByText("Unpriced")).toBeInTheDocument();
  });

  it("falls back to the raw status text for an unrecognized status", () => {
    renderWithIntl(<StatusBadge status="mystery" />);
    expect(screen.getByText("mystery")).toBeInTheDocument();
  });
});
