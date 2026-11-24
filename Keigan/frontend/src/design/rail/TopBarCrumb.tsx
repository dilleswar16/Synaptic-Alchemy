import { useLocation } from "react-router";
import { useTranslation } from "react-i18next";
import { useAccessControl } from "@/auth/accessControl";
import { isDeveloperEnvironment, isProductionEnvironment, useRuntimeConfiguration } from "@/config/runtimeConfiguration";
import { visibleNavigationSections } from "@/components/layout/navigationItems";

/** The current page's name in the top bar, after the application scope: "All my applications / Home". Pages that are not in the navigation show nothing. */
export function TopBarCrumb() {
  const { t } = useTranslation("navigation");
  const { pathname } = useLocation();
  const { isKeiganAdmin } = useAccessControl();
  const runtimeConfiguration = useRuntimeConfiguration();
  const items = visibleNavigationSections({
    isKeiganAdmin,
    isProduction: isProductionEnvironment(runtimeConfiguration),
    isDeveloperEnvironment: isDeveloperEnvironment(runtimeConfiguration),
  }).flatMap((section) => section.items);
  const current = items.find((item) => (item.end ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`)));
  if (!current) {
    return null;
  }
  return (
    <p className="hidden items-center gap-2 text-body-sm md:flex">
      <span aria-hidden="true" className="text-subtle">
        /
      </span>
      <span className="font-medium text-default">{t(current.labelKey)}</span>
    </p>
  );
}
