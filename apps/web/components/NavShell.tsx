"use client";

import { useEffect, useState } from "react";
import { SidebarProvider } from "@/components/ui/sidebar";
import { Nav } from "./Nav";

const SIDEBAR_COOKIE = "sidebar_state";

/**
 * The rail, and the one thing shadcn's Sidebar cannot do here on its own.
 *
 * `SidebarProvider` writes the collapsed state to a cookie, and a normal Next
 * app reads it back in the server layout to pick `defaultOpen`. This app is
 * exported statically (D32) — there is no render on the server to read a
 * cookie in, so the state was being written and never restored: collapse the
 * rail, reload, and it is open again.
 *
 * Reading it on the client after mount fixes that without forking the
 * component or adding a second place the preference lives. The prerendered
 * HTML necessarily shows the rail open, so a viewer who collapsed it sees one
 * frame of it expanded; that is the honest cost of having no server, and it is
 * cheaper than the alternatives.
 */
export function NavShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(true);

  useEffect(() => {
    try {
      const match = document.cookie.match(
        new RegExp(`(?:^|;\\s*)${SIDEBAR_COOKIE}=(true|false)`),
      );
      if (match) setOpen(match[1] === "true");
    } catch {
      /* the rail is chrome: if the preference cannot be read it opens. */
    }
  }, []);

  return (
    <SidebarProvider
      open={open}
      onOpenChange={setOpen}
      className="flex h-screen overflow-hidden"
      style={
        {
          // 13.25rem keeps the rail at the 212px it was designed around.
          // The icon width is NOT free: shadcn centres a 32px row inside it
          // using fixed 8px gutters, so anything but 3rem puts the slack on
          // one side and the icons stop lining up with the brand mark.
          "--sidebar-width": "13.25rem",
          "--sidebar-width-icon": "3rem",
        } as React.CSSProperties
      }
    >
      <Nav />
      <main className="flex-1 min-w-0 overflow-hidden p-4">{children}</main>
    </SidebarProvider>
  );
}
