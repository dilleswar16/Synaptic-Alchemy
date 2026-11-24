import { useEffect, useRef, useState, type FocusEvent } from "react";
import { NavLink } from "react-router";
import { motion, useReducedMotion } from "motion/react";
import { PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAccessControl } from "@/auth/accessControl";
import { isDeveloperEnvironment, isProductionEnvironment, useRuntimeConfiguration } from "@/config/runtimeConfiguration";
import { IconButton } from "@/components/ui/IconButton";
import { KeiganLogo } from "@/components/layout/KeiganLogo";
import { visibleNavigationSections } from "@/components/layout/navigationItems";
import type { SidebarProps } from "@/components/layout/Sidebar";
import { cn } from "@/utils/cn";
import { NavIcon } from "./NavIcons";

/**
 * Navigation rail for the Mono design, used instead of the original sidebar.
 * A slim icon rail that opens over the page when you point at it or tab into it and closes again; the pin button keeps it open.
 * The active page is a pill that slides between items. Same destinations, labels and access rules as `Sidebar`.
 */

const peekDelayMilliseconds = 110;
const environmentDotClasses = { local: "bg-neutral-fill", dev: "bg-info-fill", test: "bg-warning-fill", prod: "bg-danger-fill" } as const;

export function MonoSidebar({ isCollapsed, onToggleCollapsed, isOverlay = false, onNavigate, onClose }: SidebarProps) {
  const { t } = useTranslation("navigation");
  const { t: translateCommon } = useTranslation("common");
  const { isKeiganAdmin } = useAccessControl();
  const runtimeConfiguration = useRuntimeConfiguration();
  const prefersReducedMotion = useReducedMotion();
  const [isPeeking, setIsPeeking] = useState(false);
  const peekTimer = useRef<number | null>(null);

  const isRail = isCollapsed && !isOverlay;
  const isOpen = !isRail || isPeeking;
  const sections = visibleNavigationSections({
    isKeiganAdmin,
    isProduction: isProductionEnvironment(runtimeConfiguration),
    isDeveloperEnvironment: isDeveloperEnvironment(runtimeConfiguration),
  });
  const environmentKey = (["local", "dev", "test", "prod"] as const).find((key) => key === runtimeConfiguration.environmentName) ?? (isProductionEnvironment(runtimeConfiguration) ? "prod" : "test");

  useEffect(() => () => {
    if (peekTimer.current !== null) window.clearTimeout(peekTimer.current);
  }, []);

  const startPeek = () => {
    if (!isRail) return;
    if (peekTimer.current !== null) window.clearTimeout(peekTimer.current);
    peekTimer.current = window.setTimeout(() => setIsPeeking(true), peekDelayMilliseconds);
  };
  const endPeek = () => {
    if (peekTimer.current !== null) window.clearTimeout(peekTimer.current);
    peekTimer.current = null;
    setIsPeeking(false);
  };
  const handleBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget)) endPeek();
  };

  return (
    <div className="relative h-full" onMouseEnter={startPeek} onMouseLeave={endPeek} onFocusCapture={startPeek} onBlurCapture={handleBlur}>
      <aside
        data-rail-open={isOpen}
        aria-label={t("mainNavigation")}
        className={cn(
          "absolute inset-y-0 left-0 flex flex-col overflow-hidden border-r border-hairline bg-surface transition-[width,box-shadow] duration-200 ease-out motion-reduce:transition-none",
          isOverlay ? "w-full" : isOpen ? "w-[var(--layout-sidebar-width)]" : "w-[var(--layout-sidebar-collapsed-width)]",
          isRail && isPeeking && "shadow-md",
        )}
      >
        <div className="flex h-[var(--layout-top-bar-height)] shrink-0 items-center justify-between pr-3 pl-3.5">
          <span className={cn("block overflow-hidden transition-[width] duration-200 ease-out motion-reduce:transition-none", isOpen ? "w-44" : "w-7")}>
            <KeiganLogo variant="full" size={28} showKanji />
          </span>
          {isOverlay ? <IconButton icon={X} label={t("sidebar.close")} onClick={onClose} /> : null}
        </div>

        <nav className="flex-1 overflow-x-hidden overflow-y-auto px-2 pt-1 pb-3" aria-label={t("mainNavigation")}>
          {sections.map((section) => (
            <div key={section.key} className="mb-1.5">
              <div className="relative h-7">
                <p className="rail-reveal absolute inset-y-0 left-3 flex items-center text-caption font-medium whitespace-nowrap text-subtle">{t(section.labelKey)}</p>
                <span aria-hidden="true" className={cn("absolute inset-x-2 top-1/2 h-px bg-hairline transition-opacity duration-200", isOpen ? "opacity-0" : "opacity-100")} />
              </div>
              <ul className="flex flex-col gap-0.5">
                {section.items.map((item) => {
                  const FallbackIcon = item.icon;
                  const customIcon = <NavIcon name={item.key} />;
                  return (
                    <li key={item.key}>
                      <NavLink
                        to={item.to}
                        end={item.end}
                        onClick={onNavigate}
                        aria-label={isOpen ? undefined : t(item.labelKey)}
                        className="rail-link group relative flex h-9 items-center rounded-md text-body-sm font-medium text-muted transition-colors duration-150 hover:bg-surface-hover hover:text-default aria-[current=page]:text-default"
                      >
                        {({ isActive }) => (
                          <>
                            {isActive ? (
                              <motion.span
                                layoutId="mono-nav-pill"
                                aria-hidden="true"
                                className="absolute inset-0 rounded-md bg-surface-selected"
                                transition={prefersReducedMotion ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 38 }}
                              >
                                <span className="absolute top-2.5 bottom-2.5 left-0 w-0.5 rounded-full bg-brand-fill" />
                              </motion.span>
                            ) : null}
                            <span className="relative grid size-10 shrink-0 place-items-center">
                              {customIcon ?? <FallbackIcon aria-hidden="true" size={20} strokeWidth={1.6} />}
                            </span>
                            <span className="rail-reveal relative truncate pr-3">{t(item.labelKey)}</span>
                          </>
                        )}
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="flex h-12 shrink-0 items-center border-t border-hairline pr-2 pl-3.5">
          <span
            aria-hidden="true"
            title={translateCommon("environment.badgeLabel", { environment: translateCommon(`environment.${environmentKey}`) })}
            className={cn("size-2 shrink-0 rounded-full", environmentDotClasses[environmentKey])}
          />
          <span className="rail-reveal ml-2 flex-1 truncate text-caption text-subtle">
            {translateCommon(`environment.${environmentKey}`)}
            {runtimeConfiguration.productVersion ? <span className="font-mono"> v{runtimeConfiguration.productVersion}</span> : null}
          </span>
          {isOverlay ? null : (
            <span className="rail-reveal">
              <IconButton
                icon={isCollapsed ? PanelLeftOpen : PanelLeftClose}
                label={isCollapsed ? t("sidebar.expand") : t("sidebar.collapse")}
                tooltipSide="right"
                size="sm"
                onClick={onToggleCollapsed}
              />
            </span>
          )}
        </div>
      </aside>
    </div>
  );
}
