import { Bell, LogOut, Menu, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { highestRoleOf } from "@/auth/accessControl";
import { useAuth } from "@/auth/authContext";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { DropdownMenu } from "@/components/ui/DropdownMenu";
import { EmptyState } from "@/components/ui/EmptyState";
import { IconButton } from "@/components/ui/IconButton";
import { Kbd } from "@/components/ui/Kbd";
import { Popover } from "@/components/ui/Popover";
import { ApplicationScopeSwitcher } from "./ApplicationScopeSwitcher";
import { DesignLabMenu } from "@/design-lab/DesignLabMenu";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { ThemeToggle } from "./ThemeToggle";

export interface TopBarProps {
  onOpenNavigation: () => void;
  onOpenCommandPalette: () => void;
}

const isApplePlatform = typeof navigator !== "undefined" && /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent);

/** Sticky 64 px glass bar: menu, application scope, search, language, theme, notifications, user menu. */
export function TopBar({ onOpenNavigation, onOpenCommandPalette }: TopBarProps) {
  const { t } = useTranslation("navigation");
  const { user, signOut } = useAuth();
  const roleKey = user ? highestRoleOf(user) : "noAccess";

  return (
    <header className="glass-surface sticky top-0 z-30 flex h-[var(--layout-top-bar-height,4rem)] shrink-0 items-center gap-1 border-b border-hairline px-3 sm:gap-2 sm:px-6">
      <IconButton icon={Menu} label={t("sidebar.open")} onClick={onOpenNavigation} className="md:hidden" />
      <ApplicationScopeSwitcher />
      <div className="flex-1" />
      <button
        type="button"
        onClick={onOpenCommandPalette}
        aria-label={t("commandPalette.open")}
        className="hidden h-9 min-w-56 items-center gap-2 rounded-sm border border-control bg-surface px-3 text-body-sm text-muted shadow-xs transition-colors hover:bg-surface-hover lg:inline-flex"
      >
        <Search aria-hidden="true" size={16} />
        <span className="flex-1 text-left">{t("commandPalette.trigger")}</span>
        <Kbd>{isApplePlatform ? "⌘" : "Ctrl"}</Kbd>
        <Kbd>K</Kbd>
      </button>
      <IconButton icon={Search} label={t("commandPalette.open")} onClick={onOpenCommandPalette} className="lg:hidden" />
      <LanguageSwitcher />
      <DesignLabMenu />
      <ThemeToggle />
      <Popover
        align="end"
        width="md"
        aria-label={t("notifications.title")}
        trigger={<IconButton icon={Bell} label={t("notifications.open")} />}
      >
        <h2 className="mb-2 font-display text-h4 text-default">{t("notifications.title")}</h2>
        <EmptyState size="sm" title={t("notifications.emptyTitle")} description={t("notifications.emptyDescription")} icon={Bell} />
      </Popover>
      {user ? (
        <DropdownMenu
          header={
            <div className="flex items-center gap-3">
              <Avatar name={user.displayName} size="lg" />
              <div className="min-w-0">
                <p className="truncate text-body font-semibold text-default">{user.displayName}</p>
                {user.email ? <p className="truncate text-caption text-muted">{user.email}</p> : null}
                <Badge tone={roleKey === "keiganAdmin" ? "brand" : roleKey === "applicationAdmin" ? "info" : "neutral"} className="mt-1.5">
                  {t(`roles.${roleKey}`)}
                </Badge>
              </div>
            </div>
          }
          entries={[{ key: "signOut", label: t("userMenu.signOut"), icon: LogOut, onSelect: () => void signOut() }]}
          trigger={
            <button type="button" aria-label={t("userMenu.open")} className="ml-1 rounded-full p-0.5 transition-shadow hover:shadow-md">
              <Avatar name={user.displayName} />
            </button>
          }
        />
      ) : null}
    </header>
  );
}
