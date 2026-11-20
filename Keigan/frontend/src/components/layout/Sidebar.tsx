import { NavLink } from "react-router";
import { PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAccessControl } from "@/auth/accessControl";
import { isDeveloperEnvironment, isProductionEnvironment, useRuntimeConfiguration } from "@/config/runtimeConfiguration";
import { cn } from "@/utils/cn";
import { IconButton } from "@/components/ui/IconButton";
import { Tooltip } from "@/components/ui/Tooltip";
import { StatusChip } from "@/components/ui/StatusChip";
import { KeiganLogo } from "./KeiganLogo";
import { visibleNavigationSections } from "./navigationItems";

export interface SidebarProps {
  /** Icons only (72 px). Ignored in overlay mode. */
  isCollapsed: boolean;
  onToggleCollapsed: () => void;
  /** Overlay drawer below 900 px: always expanded, with a close button. */
  isOverlay?: boolean;
  onNavigate?: () => void;
  onClose?: () => void;
}

const environmentTones = { local: "neutral", dev: "info", test: "warning", prod: "danger" } as const;

/** Navigation sections per spec §4; the Administration section appears for Keigan admins only. */
export function Sidebar({ isCollapsed, onToggleCollapsed, isOverlay = false, onNavigate, onClose }: SidebarProps) {
  const { t } = useTranslation("navigation");
  const { t: translateCommon } = useTranslation("common");
  const { isKeiganAdmin } = useAccessControl();
  const runtimeConfiguration = useRuntimeConfiguration();
  const isCompact = isCollapsed && !isOverlay;
  const sections = visibleNavigationSections({
    isKeiganAdmin,
    isProduction: isProductionEnvironment(runtimeConfiguration),
    isDeveloperEnvironment: isDeveloperEnvironment(runtimeConfiguration),
  });
  const environmentKey = (["local", "dev", "test", "prod"] as const).find((key) => key === runtimeConfiguration.environmentName) ?? (isProductionEnvironment(runtimeConfiguration) ? "prod" : "test");

  return (
    <aside className="flex h-full flex-col border-r border-hairline bg-surface" aria-label={t("mainNavigation")}>
      <div className={cn("flex h-16 shrink-0 items-center", isCompact ? "justify-center" : "justify-between px-5")}>
        <KeiganLogo variant={isCompact ? "mark" : "full"} size={isCompact ? 30 : 30} showKanji={!isCompact} />
        {isOverlay ? <IconButton icon={X} label={t("sidebar.close")} onClick={onClose} /> : null}
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pt-2 pb-4" aria-label={t("mainNavigation")}>
        {sections.map((section) => (
          <div key={section.key} className="mb-4">
            {isCompact ? <div className="mx-3 mb-2 h-px bg-hairline" /> : <p className="eyebrow px-3 pb-1.5">{t(section.labelKey)}</p>}
            <ul className="flex flex-col gap-0.5">
              {section.items.map((item) => {
                const ItemIcon = item.icon;
                return (
                  <li key={item.key}>
                    <Tooltip content={t(item.labelKey)} side="right" disabled={!isCompact}>
                      <NavLink
                        to={item.to}
                        end={item.end}
                        onClick={onNavigate}
                        aria-label={isCompact ? t(item.labelKey) : undefined}
                        className={({ isActive }) =>
                          cn(
                            "relative flex h-10 items-center gap-3 rounded-md text-body font-medium transition-colors",
                            isCompact ? "justify-center px-0" : "px-3",
                            isActive ? "bg-surface-selected text-heading-accent" : "text-default hover:bg-surface-hover",
                          )
                        }
                      >
                        {({ isActive }) => (
                          <>
                            {isActive ? <span aria-hidden="true" className="absolute top-2 bottom-2 left-0 w-[3px] rounded-full bg-gradient-brand" /> : null}
                            <ItemIcon aria-hidden="true" size={18} strokeWidth={1.75} className="shrink-0" />
                            {isCompact ? null : <span className="truncate">{t(item.labelKey)}</span>}
                          </>
                        )}
                      </NavLink>
                    </Tooltip>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className={cn("flex shrink-0 items-center gap-2 border-t border-hairline p-3", isCompact ? "flex-col" : "justify-between")}>
        <div className={cn("flex min-w-0 items-center gap-2", isCompact && "flex-col")}>
          <StatusChip tone={environmentTones[environmentKey]} size="sm" icon={false} title={translateCommon("environment.badgeLabel", { environment: translateCommon(`environment.${environmentKey}`) })}>
            {translateCommon(`environment.${environmentKey}`).toUpperCase()}
          </StatusChip>
          {runtimeConfiguration.productVersion && !isCompact ? <span className="truncate font-mono text-caption text-subtle">v{runtimeConfiguration.productVersion}</span> : null}
        </div>
        {isOverlay ? null : (
          <IconButton
            icon={isCollapsed ? PanelLeftOpen : PanelLeftClose}
            label={isCollapsed ? t("sidebar.expand") : t("sidebar.collapse")}
            tooltipSide="right"
            size="sm"
            onClick={onToggleCollapsed}
          />
        )}
      </div>
    </aside>
  );
}
