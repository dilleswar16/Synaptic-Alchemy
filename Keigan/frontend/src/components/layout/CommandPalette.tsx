import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { CornerDownLeft, Search, SearchCheck } from "lucide-react";
import { Dialog as RadixDialog } from "radix-ui";
import { useTranslation } from "react-i18next";
import { useAccessControl } from "@/auth/accessControl";
import { isDeveloperEnvironment, isProductionEnvironment, useRuntimeConfiguration } from "@/config/runtimeConfiguration";
import { cn } from "@/utils/cn";
import { Kbd } from "@/components/ui/Kbd";
import { visibleNavigationSections } from "./navigationItems";

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface PaletteEntry {
  key: string;
  label: string;
  icon: typeof Search;
  run: () => void;
}

/** Ctrl/⌘ + K: jump to a page, or press Enter on free text to search incidents (doc 01 §4). */
export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const { t } = useTranslation("navigation");
  const navigate = useNavigate();
  const { isKeiganAdmin } = useAccessControl();
  const runtimeConfiguration = useRuntimeConfiguration();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const pageEntries = useMemo<PaletteEntry[]>(() => {
    const sections = visibleNavigationSections({
      isKeiganAdmin,
      isProduction: isProductionEnvironment(runtimeConfiguration),
      isDeveloperEnvironment: isDeveloperEnvironment(runtimeConfiguration),
    });
    return sections.flatMap((section) =>
      section.items.map((item) => ({ key: item.key, label: t(item.labelKey), icon: item.icon as typeof Search, run: () => navigate(item.to) })),
    );
  }, [isKeiganAdmin, runtimeConfiguration, navigate, t]);

  const trimmedQuery = query.trim();
  const entries = useMemo<PaletteEntry[]>(() => {
    const matchingPages = trimmedQuery ? pageEntries.filter((entry) => entry.label.toLowerCase().includes(trimmedQuery.toLowerCase())) : pageEntries;
    const incidentSearch: PaletteEntry[] = trimmedQuery
      ? [{ key: "incident-search", label: t("commandPalette.searchIncident", { query: trimmedQuery }), icon: SearchCheck, run: () => navigate(`/incidents?search=${encodeURIComponent(trimmedQuery)}`) }]
      : [];
    return [...matchingPages, ...incidentSearch];
  }, [pageEntries, trimmedQuery, navigate, t]);

  useEffect(() => {
    if (!open) {
      setQuery("");
    }
  }, [open]);

  useEffect(() => setActiveIndex(0), [trimmedQuery]);

  function runEntry(entry: PaletteEntry | undefined): void {
    if (!entry) return;
    onOpenChange(false);
    entry.run();
  }

  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-50 bg-overlay backdrop-blur-[2px] data-[state=closed]:animate-fade-out data-[state=open]:animate-fade-in" />
        <RadixDialog.Content
          aria-describedby={undefined}
          className="fixed top-[12vh] left-1/2 z-50 w-[min(640px,calc(100vw-24px))] -translate-x-1/2 overflow-hidden rounded-lg border border-hairline bg-surface shadow-lg focus-visible:outline-none data-[state=closed]:animate-pop-out data-[state=open]:animate-pop-in"
        >
          <RadixDialog.Title className="sr-only">{t("commandPalette.title")}</RadixDialog.Title>
          <div className="flex items-center gap-3 border-b border-hairline px-4">
            <Search aria-hidden="true" size={18} className="shrink-0 text-muted" />
            <input
              autoFocus
              value={query}
              onChange={(changeEvent) => setQuery(changeEvent.target.value)}
              onKeyDown={(keyEvent) => {
                if (keyEvent.key === "ArrowDown") {
                  keyEvent.preventDefault();
                  setActiveIndex((index) => Math.min(index + 1, entries.length - 1));
                } else if (keyEvent.key === "ArrowUp") {
                  keyEvent.preventDefault();
                  setActiveIndex((index) => Math.max(index - 1, 0));
                } else if (keyEvent.key === "Enter") {
                  keyEvent.preventDefault();
                  runEntry(entries[activeIndex]);
                }
              }}
              placeholder={t("commandPalette.placeholder")}
              aria-label={t("commandPalette.placeholder")}
              role="combobox"
              aria-expanded="true"
              aria-controls="command-palette-results"
              aria-activedescendant={entries[activeIndex] ? `command-palette-${entries[activeIndex].key}` : undefined}
              className="h-14 flex-1 bg-transparent text-body-lg text-default outline-none placeholder:text-subtle"
            />
            <Kbd>Esc</Kbd>
          </div>
          <ul id="command-palette-results" role="listbox" aria-label={t("commandPalette.pages")} className="max-h-[50vh] overflow-y-auto p-2">
            {entries.length === 0 ? <li className="px-3 py-6 text-center text-body-sm text-muted">{t("commandPalette.noResults")}</li> : null}
            {entries.map((entry, entryIndex) => {
              const EntryIcon = entry.icon;
              return (
                <li
                  key={entry.key}
                  id={`command-palette-${entry.key}`}
                  role="option"
                  aria-selected={entryIndex === activeIndex}
                  onMouseMove={() => setActiveIndex(entryIndex)}
                  onClick={() => runEntry(entry)}
                  className={cn("flex cursor-pointer items-center gap-3 rounded-sm px-3 py-2.5 text-body text-default", entryIndex === activeIndex && "bg-surface-selected")}
                >
                  <EntryIcon aria-hidden="true" size={18} strokeWidth={1.75} className="shrink-0 text-muted" />
                  <span className="min-w-0 flex-1 truncate">{entry.label}</span>
                  {entryIndex === activeIndex ? <CornerDownLeft aria-hidden="true" size={14} className="text-muted" /> : null}
                </li>
              );
            })}
          </ul>
          <div className="flex items-center gap-4 border-t border-hairline px-4 py-2 text-caption text-muted">
            <span className="inline-flex items-center gap-1.5">
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> {t("commandPalette.hintNavigate")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Kbd>↵</Kbd> {t("commandPalette.hintOpen")}
            </span>
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
