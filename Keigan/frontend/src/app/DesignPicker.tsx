import { useEffect, type CSSProperties } from "react";
import { Check } from "lucide-react";
import { backdropOptions, useBackdrop } from "@/hooks/useBackdrop";
import { designOptions, loadDesignFonts, useDesign } from "@/hooks/useDesign";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/utils/cn";

/**
 * Developer-only chooser on the Design system page: nine designs (each previewed in its own tokens, in the current
 * light or dark theme) and six page backgrounds. Copy is English-only, like the rest of the page.
 */

const previewBackdropStyle: CSSProperties & Record<"--backdrop-attachment", string> = { "--backdrop-attachment": "scroll" };

function ChoiceFooter({ name, description, isSelected }: { name: string; description: string; isSelected: boolean }) {
  return (
    <span className="flex items-start gap-2 p-3">
      <span className="min-w-0 flex-1">
        <span className="block text-body-sm font-semibold text-default">{name}</span>
        <span className="block text-caption text-muted">{description}</span>
      </span>
      {isSelected ? <Check size={16} className="mt-0.5 text-action" aria-hidden /> : null}
    </span>
  );
}

export function DesignPicker() {
  const { designId, setDesign } = useDesign();
  const { backdropId, setBackdrop } = useBackdrop();
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    designOptions.forEach((option) => loadDesignFonts(option.id));
  }, []);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <p className="mb-3 text-caption font-medium text-muted">Design</p>
        <div role="radiogroup" aria-label="Design" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
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
                className={cn("overflow-hidden rounded-lg border bg-surface text-left transition-shadow", isSelected ? "border-action shadow-md ring-2 ring-action" : "border-hairline hover:shadow-sm")}
              >
                <span data-design={option.id} data-theme={resolvedTheme} className="block bg-canvas p-3" aria-hidden>
                  <span className="block rounded-md border border-hairline bg-surface p-3 shadow-xs">
                    <span className="block font-display text-h3 font-semibold text-default">Aa Heading</span>
                    <span className="block text-caption text-muted">Body text sample for this design.</span>
                    <span className="mt-2.5 flex items-center gap-2">
                      <span className="rounded-sm bg-action px-2.5 py-1 text-caption font-semibold text-on-action">Primary</span>
                      <span className="rounded-full bg-brand-soft px-2 py-0.5 text-micro font-semibold text-brand">Chip</span>
                      <span className="size-3 rounded-full bg-brand-fill" aria-hidden />
                      <span className="ml-auto flex items-end gap-0.5" aria-hidden>
                        <span className="h-2 w-1.5 rounded-xs bg-brand-fill" />
                        <span className="h-3.5 w-1.5 rounded-xs bg-brand-fill" />
                        <span className="h-2.5 w-1.5 rounded-xs bg-brand-fill" />
                        <span className="h-4 w-1.5 rounded-xs bg-action" />
                      </span>
                    </span>
                  </span>
                </span>
                <ChoiceFooter name={option.name} description={option.description} isSelected={isSelected} />
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <p className="mb-3 text-caption font-medium text-muted">Page background (works with every design)</p>
        <div role="radiogroup" aria-label="Page background" className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {backdropOptions.map((option) => {
            const isSelected = option.id === backdropId;
            return (
              <button
                key={option.id}
                type="button"
                role="radio"
                aria-checked={isSelected}
                aria-label={`${option.name}. ${option.description}`}
                onClick={() => setBackdrop(option.id)}
                className={cn("overflow-hidden rounded-lg border bg-surface text-left transition-shadow", isSelected ? "border-action shadow-md ring-2 ring-action" : "border-hairline hover:shadow-sm")}
              >
                <span data-backdrop={option.id} style={previewBackdropStyle} className="app-backdrop block p-3" aria-hidden>
                  <span className="block h-14 rounded-md border border-hairline bg-surface shadow-xs" aria-hidden />
                </span>
                <ChoiceFooter name={option.name} description={option.description} isSelected={isSelected} />
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
