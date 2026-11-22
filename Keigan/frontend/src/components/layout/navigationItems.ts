import { Bell, ChartColumn, Gauge, House, LayoutGrid, ListChecks, Mail, Palette, Radar, Settings, Siren, Sparkles, TrendingUp, type LucideIcon } from "lucide-react";

/** Sidebar and command-palette destinations (doc 01 §4). Labels live in the `navigation` namespace. */

export interface NavigationItem {
  key: string;
  /** i18n key in the `navigation` namespace, e.g. `items.home`. */
  labelKey: string;
  to: string;
  icon: LucideIcon;
  /** Match only the exact path (Home). */
  end?: boolean;
  /** Hide the item in production (Outbox is local/test only). */
  hiddenInProduction?: boolean;
  /** Only offered in local/dev environments (design-system showcase). */
  developerOnly?: boolean;
}

export interface NavigationSection {
  key: string;
  labelKey: string;
  /** Only Keigan admins see this section. */
  adminOnly?: boolean;
  items: NavigationItem[];
}

export const navigationSections: NavigationSection[] = [
  {
    key: "operate",
    labelKey: "sections.operate",
    items: [
      { key: "home", labelKey: "items.home", to: "/", icon: House, end: true },
      { key: "incidents", labelKey: "items.incidents", to: "/incidents", icon: Siren },
      { key: "alerts", labelKey: "items.alerts", to: "/alerts", icon: Bell },
      { key: "actionItems", labelKey: "items.actionItems", to: "/action-items", icon: ListChecks },
    ],
  },
  {
    key: "reliability",
    labelKey: "sections.reliability",
    items: [
      { key: "slo", labelKey: "items.slo", to: "/slo", icon: Gauge },
      { key: "intelligence", labelKey: "items.intelligence", to: "/intelligence", icon: TrendingUp },
      { key: "metrics", labelKey: "items.metrics", to: "/metrics", icon: ChartColumn },
    ],
  },
  {
    key: "assist",
    labelKey: "sections.assist",
    items: [{ key: "chat", labelKey: "items.chat", to: "/chat", icon: Sparkles }],
  },
  {
    key: "prepare",
    labelKey: "sections.prepare",
    items: [{ key: "applications", labelKey: "items.applications", to: "/applications", icon: LayoutGrid }],
  },
  {
    key: "administration",
    labelKey: "sections.administration",
    adminOnly: true,
    items: [
      { key: "platformSettings", labelKey: "items.platformSettings", to: "/administration/settings", icon: Settings },
      { key: "usageAndAudit", labelKey: "items.usageAndAudit", to: "/administration/usage", icon: Radar },
      { key: "outbox", labelKey: "items.outbox", to: "/administration/outbox", icon: Mail, hiddenInProduction: true },
      { key: "designSystem", labelKey: "items.designSystem", to: "/design-system", icon: Palette, developerOnly: true },
    ],
  },
];

/** Sections and items visible for the user and environment. */
export function visibleNavigationSections(options: { isKeiganAdmin: boolean; isProduction: boolean; isDeveloperEnvironment: boolean }): NavigationSection[] {
  return navigationSections
    .filter((section) => !section.adminOnly || options.isKeiganAdmin)
    .map((section) => ({
      ...section,
      items: section.items.filter(
        (item) => !(item.hiddenInProduction && options.isProduction) && !(item.developerOnly && !options.isDeveloperEnvironment),
      ),
    }))
    .filter((section) => section.items.length > 0);
}
