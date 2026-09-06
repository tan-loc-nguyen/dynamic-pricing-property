import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithIntl } from "./test-utils";
import { Nav } from "./Nav";
import { SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/rate",
}));

const replace = vi.fn();
vi.mock("@/i18n/navigation", () => ({
  usePathname: () => "/rate",
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/api", () => ({
  api: { status: () => Promise.resolve({ demo_mode: true }) },
}));

const toggle = () => screen.getByRole("button", { name: /collapse|expand/i });

/** The rail reads its state from SidebarProvider, so it renders inside one. */
const renderNav = (defaultOpen = true) =>
  renderWithIntl(
    <TooltipProvider>
      <SidebarProvider defaultOpen={defaultOpen}>
        <Nav />
      </SidebarProvider>
    </TooltipProvider>,
  );

describe("Nav", () => {
  beforeEach(() => {
    replace.mockClear();
  });

  it("starts expanded, with every destination named on screen", async () => {
    renderNav();
    expect(screen.getByText("Rate")).toBeTruthy();
    expect(screen.getByText("Market")).toBeTruthy();
    expect(screen.getByText("Customisation")).toBeTruthy();
    expect(toggle().getAttribute("aria-expanded")).toBe("true");
  });

  it("narrows to icons but keeps every link reachable", async () => {
    const { container } = renderNav();
    await userEvent.click(toggle());

    expect(container.querySelector('[data-state="collapsed"]')).toBeTruthy();
    // The labels stay in the DOM -- shadcn hides them with CSS rather than
    // unmounting them, which is what keeps them available to a screen reader.
    // The icon alone is not a name, so each link is named either way.
    expect(screen.getByRole("link", { name: "Rate" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Market" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Customisation" })).toBeTruthy();
    expect(toggle().getAttribute("aria-expanded")).toBe("false");
  });

  it("records the choice so it can be restored", async () => {
    // SidebarProvider writes this cookie. Reading it back is NavShell's job,
    // covered in its own test -- a static export has no server render to read
    // it in, which is the whole reason that wrapper exists.
    renderNav();
    await userEvent.click(toggle());
    expect(document.cookie).toContain("sidebar_state=false");
  });

  it("keeps language switchable when collapsed", async () => {
    // Vietnamese is the default locale and the daily operator is Vietnamese.
    // Losing the language control as a side effect of collapsing the rail
    // would be a regression, not a simplification.
    renderNav();
    await userEvent.click(toggle());

    const lang = screen.getByRole("button", { name: /tiếng việt/i });
    await userEvent.click(lang);
    expect(replace).toHaveBeenCalledWith("/rate", { locale: "vi" });
  });

  it("still says which page you are on when collapsed", async () => {
    renderNav();
    await userEvent.click(toggle());
    expect(screen.getByRole("link", { name: "Rate" }).getAttribute("aria-current")).toBe("page");
  });
});
