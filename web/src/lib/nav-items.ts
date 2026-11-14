import {
  Award,
  Bot,
  Calendar,
  CircleHelp,
  FileText,
  GalleryHorizontalEnd,
  Globe,
  Home,
  Monitor,
  Puzzle,
  Server,
  Settings,
  Wifi,
} from "lucide-react";

import type { PluginInfo } from "@/lib/api";

/**
 * The FiestaBoard information architecture (slice 2.1; WEB-01/02/14; Figma 07
 * `53:143037`, 07a `308:36070`). One list, read by the rail, the bottom tab
 * bar and its More drawer, so the three can never disagree on order.
 *
 *   Home · Pages (▸ Collections) · Schedule · Displays │ Integrations ·
 *   Staff Picks · Settings · Help & Docs
 *
 * The first four are the phone's tab bar; the rest are what More holds, in
 * CANON order (FLOW-DESIGNER-BRIEF "More group order").
 */

export type NavKey =
  "home" | "pages" | "collections" | "schedule" | "displays" | "integrations" | "picks" | "settings" | "helpDocs";

export interface NavItemDef {
  key: NavKey;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  external?: boolean;
  /**
   * A destination that lives inside another (Collections inside Pages). The
   * rail lists it under its parent; the tab bar has no room for it, so there
   * it is reached through the parent, and lights the parent's tab.
   */
  nestedUnder?: NavKey;
}

export const HELP_DOCS_URL = "https://fiestaboard.app/docs/intro";

export const NAV_ITEMS: readonly NavItemDef[] = [
  { key: "home", href: "/", icon: Home },
  { key: "pages", href: "/pages", icon: FileText },
  { key: "collections", href: "/collections", icon: GalleryHorizontalEnd, nestedUnder: "pages" },
  { key: "schedule", href: "/schedule", icon: Calendar },
  { key: "displays", href: "/displays", icon: Monitor },
  { key: "integrations", href: "/integrations", icon: Puzzle },
  { key: "picks", href: "/picks", icon: Award },
  { key: "settings", href: "/settings", icon: Settings },
  { key: "helpDocs", href: HELP_DOCS_URL, icon: CircleHelp, external: true },
];

/** Which chrome is drawing the list: the rail (≥768px) or the phone's tab bar. */
export type NavChrome = "rail" | "bottom-nav";

/** The items a chrome shows, in order. The tab bar drops nested destinations. */
export function navItemsFor(chrome: NavChrome): NavItemDef[] {
  return NAV_ITEMS.filter((item) => chrome === "rail" || !item.nestedUnder);
}

function ownsPath(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(href + "/");
}

/**
 * Whether `item` is where the reader is. On the tab bar a parent also lights
 * for its nested destinations (Pages on /collections), because the nested
 * one has no tab of its own to light.
 */
export function isNavItemActive(item: NavItemDef, pathname: string, chrome: NavChrome): boolean {
  if (item.external) return false;
  if (ownsPath(item.href, pathname)) return true;
  if (chrome !== "bottom-nav") return false;
  return NAV_ITEMS.some((child) => child.nestedUnder === item.key && !child.external && ownsPath(child.href, pathname));
}

/**
 * The Integrations badge (07a "ONE BADGE, ONE STORY"): installed data
 * integrations that are switched on but not set up. Outputs and transitions
 * have no setup of their own to finish, so they never count.
 */
export function integrationsNeedingAttention(plugins: readonly PluginInfo[] | undefined): number {
  if (!plugins) return 0;
  return plugins.filter((p) => (p.plugin_type ?? "data") === "data" && p.enabled && !p.configured).length;
}

/**
 * Settings › Hub group (07e §1; 07a More sheet). The settings that belong to
 * the hub rather than to you, in Figma order. `section` is the
 * `/settings/:section` slug.
 */
export interface HubSettingsLink {
  section: "network" | "ai-provider" | "system" | "language-time";
  icon: React.ComponentType<{ className?: string }>;
}

export const HUB_SETTINGS_LINKS: readonly HubSettingsLink[] = [
  { section: "network", icon: Wifi },
  { section: "ai-provider", icon: Bot },
  { section: "system", icon: Server },
  { section: "language-time", icon: Globe },
];
