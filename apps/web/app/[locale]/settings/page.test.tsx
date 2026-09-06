import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithIntl } from "@/components/test-utils";
import SettingsPage from "./page";

let devMode: boolean;

vi.mock("@/lib/api", () => ({
  api: {
    status: () => Promise.resolve({ dev_mode: devMode, override_reasons: [] }),
  },
}));

describe("SettingsPage", () => {
  beforeEach(() => {
    devMode = false;
  });

  it("shows the operator's own settings", async () => {
    renderWithIntl(<SettingsPage />);
    expect(await screen.findByText("Activity log")).toBeTruthy();
  });

  it("hides connections and data outside developer mode", async () => {
    // Provider wiring and raw connection state are ours, not the operator's.
    renderWithIntl(<SettingsPage />);
    await screen.findByText("Activity log");
    expect(screen.queryByText("Connections & data")).toBeNull();
  });

  it("shows connections and data when the server says developer mode is on", async () => {
    devMode = true;
    renderWithIntl(<SettingsPage />);
    await waitFor(() => expect(screen.getByText("Connections & data")).toBeTruthy());
  });

  it("no longer offers market sources", async () => {
    // Competitors will be collected by scraping. Until then, asking the
    // operator to type them in is asking for work we will throw away.
    devMode = true;
    renderWithIntl(<SettingsPage />);
    await screen.findByText("Activity log");
    expect(screen.queryByText(/market sources/i)).toBeNull();
  });
});
