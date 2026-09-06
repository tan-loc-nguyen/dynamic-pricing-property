"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import {
  Tag,
  Compass,
  SlidersHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Settings as SettingsIcon,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { DataSourceStatus } from "./DataSourceStatus";

/**
 * Three places to work; everything else is settings.
 *
 * Rate is the daily job, Market is the one report worth watching, and
 * Customisation holds the three things an operator tunes — seasonal bands,
 * strategy, events. Configuration an owner touches once a quarter (the PMS
 * connection, room-type mapping, the activity log) lives behind Settings at
 * the bottom, next to the language switch, so the top of the nav only ever
 * shows work.
 *
 * Built on shadcn's Sidebar in `collapsible="icon"` mode, which already owns
 * the parts worth not rewriting: the rail narrows to icons, `SidebarMenuButton`
 * moves each label into a tooltip only while collapsed, the choice persists,
 * and ⌘B toggles it. The `--sidebar-*` tokens were already mapped to this
 * project's ink/brand palette in `globals.css`, so nothing here restyles it.
 */
const PRIMARY = [
  { href: "/rate", key: "rate", icon: Tag },
  { href: "/market", key: "market", icon: Compass },
  { href: "/customisation", key: "customisation", icon: SlidersHorizontal },
] as const;

export function Nav() {
  const ta = useTranslations("app");
  const pathname = usePathname();
  const locale = useLocale();
  const t = useTranslations("nav");
  const { state } = useSidebar();
  const collapsed = state === "collapsed";

  const path = pathname.replace(`/${locale}`, "") || "/rate";
  const isActive = (href: string) => path === href || path.startsWith(`${href}/`);

  return (
    <Sidebar collapsible="icon" className="border-ink-200">
      <SidebarHeader>
        <div className={`flex items-center py-1 ${collapsed ? "justify-center" : "gap-2.5 px-2"}`}>
          <div
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-600
              font-serif text-[14px] font-medium text-white"
          >
            D
          </div>
          {/* The property's name is identity, not navigation: it goes when
              there is no room for it, and the mark alone anchors the rail. */}
          {!collapsed && (
            <div className="min-w-0">
              <div className="truncate font-serif text-[13.5px] font-medium text-ink-900">
                {ta("shortName")}
              </div>
              <div className="truncate text-[10.5px] text-ink-400">{ta("propertyName")}</div>
            </div>
          )}
        </div>
      </SidebarHeader>

      <SidebarSeparator className="bg-ink-100" />

      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu aria-label={t("primary")}>
          {PRIMARY.map((item) => {
            const label = t(`${item.key}.label`);
            const active = isActive(item.href);
            return (
              <SidebarMenuItem key={item.href}>
                <SidebarMenuButton
                  asChild
                  isActive={active}
                  // Collapsed, this is the only place the name appears.
                  // Expanded, SidebarMenuButton suppresses it, so the hint
                  // stays the tooltip's job and the label stays on screen.
                  tooltip={collapsed ? label : t(`${item.key}.hint`)}
                >
                  <Link
                    href={`/${locale}${item.href}`}
                    aria-current={active ? "page" : undefined}
                    // Named in both states, so the accessible name does not
                    // change as the rail opens and closes.
                    aria-label={label}
                  >
                    <item.icon aria-hidden size={17} strokeWidth={1.5} />
                    <span>{label}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            );
          })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      {/* Language and settings live at the bottom, away from the daily work. */}
      <SidebarFooter className="border-t border-ink-100">
        <LanguageSwitcher collapsed={collapsed} />
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              isActive={isActive("/settings")}
              tooltip={t("settings.label")}
            >
              <Link
                href={`/${locale}/settings`}
                aria-current={isActive("/settings") ? "page" : undefined}
                aria-label={t("settings.label")}
              >
                <SettingsIcon aria-hidden size={17} strokeWidth={1.5} />
                <span>{t("settings.label")}</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <DataSourceStatus collapsed={collapsed} />
        {/* shadcn's trigger ships without `aria-expanded`, so a screen
            reader is told there is a button but not what state it is in.
            It is a disclosure control; the state is the point. */}
        <SidebarTrigger
          className="w-full justify-start gap-2.5 px-2 text-ink-600 group-data-[collapsible=icon]:justify-center"
          aria-expanded={!collapsed}
          aria-label={collapsed ? t("expand") : t("collapse")}
        >
          {/* The icon says which way the rail will move; upstream shows the
              same one in both states. Expanded, it carries a label like every
              other row in the rail. */}
          {collapsed ? (
            <PanelLeftOpen aria-hidden size={17} strokeWidth={1.5} />
          ) : (
            <PanelLeftClose aria-hidden size={17} strokeWidth={1.5} />
          )}
          {!collapsed && <span className="text-[13px]">{t("collapse")}</span>}
        </SidebarTrigger>
      </SidebarFooter>
    </Sidebar>
  );
}
