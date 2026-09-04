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

  // The old StatusBadge was a compact, free-height pill (text-[11px]); shadcn's
  // Badge defaults to a fixed h-5/text-xs, which reads visibly larger in the
  // decision tables StatusBadge is used in.
  it("renders at the compact size, not shadcn Badge's default size", () => {
    renderWithIntl(<StatusBadge status="pending" />);
    const el = screen.getByText("Pending");
    expect(el.className).toContain("text-[11px]");
    expect(el.className).not.toMatch(/(^|\s)h-5(\s|$)/);
  });
});
