import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithIntl } from "./test-utils";
import { NavShell } from "./NavShell";
import { TooltipProvider } from "@/components/ui/tooltip";

vi.mock("next/navigation", () => ({ usePathname: () => "/en/rate" }));
vi.mock("@/i18n/navigation", () => ({
  usePathname: () => "/rate",
  useRouter: () => ({ replace: vi.fn() }),
}));
vi.mock("@/lib/api", () => ({
  api: { status: () => Promise.resolve({ demo_mode: true }) },
}));

const render = () =>
  renderWithIntl(
    <TooltipProvider>
      <NavShell>
        <p>page</p>
      </NavShell>
    </TooltipProvider>,
  );

const toggle = () => screen.getByRole("button", { name: /collapse|expand/i });

afterEach(() => {
  document.cookie = "sidebar_state=; path=/; max-age=0";
});

describe("NavShell", () => {
  it("opens the rail when nothing has been chosen yet", () => {
    render();
    expect(toggle().getAttribute("aria-expanded")).toBe("true");
  });

  it("restores a collapsed rail on the next load", async () => {
    // The gap this wrapper exists for: SidebarProvider writes the cookie, and
    // a normal Next app reads it back in the server layout. This app is
    // exported statically, so there is no server render to read it in -- the
    // state was written and never restored.
    document.cookie = "sidebar_state=false; path=/";
    render();
    await waitFor(() => expect(toggle().getAttribute("aria-expanded")).toBe("false"));
  });

  it("round-trips a collapse through the cookie", async () => {
    render();
    await userEvent.click(toggle());
    expect(document.cookie).toContain("sidebar_state=false");
  });

  it("opens the rail when the cookie cannot be read", async () => {
    // Locked-down installs throw on document.cookie rather than returning "".
    // The rail is chrome; failing to read a preference must not take the app
    // down, and open is the state that hides nothing.
    const spy = vi.spyOn(document, "cookie", "get").mockImplementation(() => {
      throw new Error("denied");
    });
    try {
      render();
      expect(toggle().getAttribute("aria-expanded")).toBe("true");
      expect(screen.getByText("page")).toBeTruthy();
    } finally {
      spy.mockRestore();
    }
  });
});
