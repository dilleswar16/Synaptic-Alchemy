import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { PageLoadingFallback } from "@/app/RouteFallbacks";
import { Outlet, useLocation } from "react-router";
import { useTranslation } from "react-i18next";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/utils/cn";
import { CommandPalette } from "./CommandPalette";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

const collapsedStorageKey = "keigan.sidebarCollapsed";

function readCollapsedPreference(): boolean {
  try {
    return window.localStorage.getItem(collapsedStorageKey) === "true";
  } catch {
    return false;
  }
}

/**
 * Authenticated layout: sidebar (264 / 72 px, overlay below 900 px), glass top bar, content up to 1440 px with
 * the page-enter motion, skip link and the Ctrl/⌘ + K command palette. Pages render through `<Outlet />`.
 */
export function AppShell() {
  const { t } = useTranslation("navigation");
  const location = useLocation();
  const isDesktop = useMediaQuery("(min-width: 900px)");
  const [isCollapsed, setIsCollapsed] = useState(readCollapsedPreference);
  const [isOverlayOpen, setIsOverlayOpen] = useState(false);
  const [isPaletteOpen, setIsPaletteOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);
  const mainContentRef = useRef<HTMLDivElement>(null);

  const toggleCollapsed = useCallback(() => {
    setIsCollapsed((previousValue) => {
      try {
        window.localStorage.setItem(collapsedStorageKey, String(!previousValue));
      } catch {
        // Preference is optional.
      }
      return !previousValue;
    });
  }, []);

  useEffect(() => {
    function handleShortcut(keyEvent: KeyboardEvent): void {
      if ((keyEvent.metaKey || keyEvent.ctrlKey) && keyEvent.key.toLowerCase() === "k") {
        keyEvent.preventDefault();
        setIsPaletteOpen((previousValue) => !previousValue);
      }
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  useEffect(() => {
    if (!isOverlayOpen) return;
    function handleEscape(keyEvent: KeyboardEvent): void {
      if (keyEvent.key === "Escape") setIsOverlayOpen(false);
    }
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOverlayOpen]);

  useEffect(() => {
    if (isDesktop) setIsOverlayOpen(false);
  }, [isDesktop]);

  // The phone navigation is a modal: focus moves into it, the page behind cannot be tabbed to or read, and focus returns to the menu button on close.
  useEffect(() => {
    if (!isOverlayOpen) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const mainContent = mainContentRef.current;
    mainContent?.setAttribute("inert", "");
    drawerRef.current?.focus();
    return () => {
      mainContent?.removeAttribute("inert");
      previouslyFocused?.focus();
    };
  }, [isOverlayOpen]);

  return (
    <div className="min-h-dvh bg-canvas">
      <a
        href="#main-content"
        className="sr-only z-[100] rounded-sm bg-action px-4 py-2 text-body font-semibold text-on-action focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        {t("skipToContent")}
      </a>

      {isDesktop ? (
        <div className={cn("fixed inset-y-0 left-0 z-40 transition-[width] duration-200", isCollapsed ? "w-[72px]" : "w-[264px]")}>
          <Sidebar isCollapsed={isCollapsed} onToggleCollapsed={toggleCollapsed} />
        </div>
      ) : isOverlayOpen ? (
        <>
          <div className="fixed inset-0 z-40 animate-fade-in bg-overlay" onClick={() => setIsOverlayOpen(false)} aria-hidden="true" />
          <div ref={drawerRef} role="dialog" aria-modal="true" aria-label={t("mainNavigation")} tabIndex={-1} className="fixed inset-y-0 left-0 z-50 w-[264px] max-w-[85vw] animate-drawer-left-in shadow-lg outline-none">
            <Sidebar isCollapsed={false} isOverlay onToggleCollapsed={toggleCollapsed} onNavigate={() => setIsOverlayOpen(false)} onClose={() => setIsOverlayOpen(false)} />
          </div>
        </>
      ) : null}

      <div ref={mainContentRef} className={cn("flex min-h-dvh min-w-0 flex-col transition-[padding] duration-200", isDesktop && (isCollapsed ? "pl-[72px]" : "pl-[264px]"))}>
        <TopBar onOpenNavigation={() => setIsOverlayOpen(true)} onOpenCommandPalette={() => setIsPaletteOpen(true)} />
        <main id="main-content" tabIndex={-1} className="flex-1 px-4 pt-6 pb-20 outline-none sm:px-5 md:px-8 md:pt-8">
          <div key={location.pathname.split("/")[1] ?? ""} className="mx-auto w-full max-w-[1440px] animate-page-enter">
            <Suspense fallback={<PageLoadingFallback />}>
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>

      <CommandPalette open={isPaletteOpen} onOpenChange={setIsPaletteOpen} />
    </div>
  );
}
