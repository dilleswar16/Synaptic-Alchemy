import { useEffect } from "react";
import { Check } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/utils/cn";
import { designOptions, loadMonoFont, useDesign } from "./useDesign";

/** Chooser for Keigan's own design (Mono or Classic) on the Design system page. Developer environments only, English-only copy. */
export function DesignChoice() {
  const { designId, setDesign } = useDesign();
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    loadMonoFont();
  }, []);

  return (
    <div role="radiogroup" aria-label="Keigan design" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:max-w-3xl">
      {designOptions.map((option) => {
        const isSelected = option.id === designId;
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={isSelected}
            aria-label={`${option.name}. ${option.description}`}
            onClick={() => setDesign(option.id)}
            className={cn("overflow-hidden rounded-lg border bg-surface text-left", isSelected ? "border-action ring-2 ring-action" : "border-hairline hover:shadow-sm")}
          >
            <span data-design={option.id} data-theme={resolvedTheme} aria-hidden className="block bg-canvas p-3 text-default" style={{ fontFamily: "var(--font-family-body)" }}>
              <span className="block rounded-md border border-hairline bg-surface p-3 shadow-sm">
                <span className="block font-display text-h3 text-default">Aa Heading</span>
                <span className="block text-caption text-muted">Body text sample.</span>
                <span className="mt-2.5 flex items-center gap-2">
                  <span className="rounded-[var(--radius-button,var(--radius-sm))] bg-action px-3 py-1 text-caption font-semibold text-on-action">Primary</span>
                  <span className="rounded-full bg-brand-soft px-2 py-0.5 text-micro font-semibold text-brand">Chip</span>
                </span>
              </span>
            </span>
            <span className="flex items-start gap-2 p-3">
              <span className="min-w-0 flex-1">
                <span className="block text-body-sm font-semibold text-default">{option.name}</span>
                <span className="block text-caption text-muted">{option.description}</span>
              </span>
              {isSelected ? <Check size={16} className="mt-0.5 text-action" aria-hidden /> : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}
