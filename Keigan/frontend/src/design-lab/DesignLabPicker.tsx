import { useEffect } from "react";
import { Check } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/utils/cn";
import { labThemes, type LabId } from "./themes";
import { loadLabFonts, useDesignLab } from "./useDesignLab";

/**
 * Chooser for the design lab, shown on the Design system page (developer environments only, English-only copy).
 * Each company has two preview halves, Light and Dark, drawn in that company's own tokens; clicking one applies the
 * company and the mode together. The first tile switches the lab off.
 */

type PreviewMode = "light" | "dark";

function Preview({ labId, previewMode }: { labId: LabId; previewMode: PreviewMode }) {
  return (
    <span
      data-lab={labId}
      data-theme={previewMode}
      aria-hidden
      className="block bg-canvas p-3 text-default"
      style={{ fontFamily: "var(--font-family-body)" }}
    >
      <span className="block rounded-md border border-hairline bg-surface p-3 shadow-sm">
        <span className="block font-display text-h3 text-default">Aa Heading</span>
        <span className="block text-caption text-muted">Body text sample.</span>
        <span className="mt-2.5 flex items-center gap-2">
          <span className="rounded-[var(--radius-button,var(--radius-sm))] bg-action px-3 py-1 text-caption font-semibold text-on-action">Primary</span>
          <span className="rounded-full bg-brand-soft px-2 py-0.5 text-micro font-semibold text-brand">Chip</span>
          <span className="ml-auto flex items-end gap-0.5">
            <span className="h-2 w-1.5 rounded-xs bg-brand-fill" />
            <span className="h-3.5 w-1.5 rounded-xs bg-brand-fill" />
            <span className="h-4 w-1.5 rounded-xs bg-action" />
          </span>
        </span>
      </span>
    </span>
  );
}

function ModeButton({ labId, previewMode, isSelected, onChoose }: { labId: LabId; previewMode: PreviewMode; isSelected: boolean; onChoose: () => void }) {
  const company = labThemes.find((theme) => theme.id === labId)?.company ?? labId;
  return (
    <button
      type="button"
      role="radio"
      aria-checked={isSelected}
      aria-label={`${company}, ${previewMode} mode`}
      onClick={onChoose}
      className={cn("overflow-hidden rounded-md border text-left", isSelected ? "border-action ring-2 ring-action" : "border-hairline hover:shadow-sm")}
    >
      <Preview labId={labId} previewMode={previewMode} />
      <span className="flex items-center justify-between bg-surface px-3 py-1.5 text-caption font-medium text-default">
        {previewMode === "light" ? "Light" : "Dark"}
        {isSelected ? <Check size={14} className="text-action" aria-hidden /> : null}
      </span>
    </button>
  );
}

export function DesignLabPicker() {
  const { labId, setLab } = useDesignLab();
  const { resolvedTheme, setPreference } = useTheme();

  useEffect(() => {
    labThemes.forEach((theme) => loadLabFonts(theme.id));
  }, []);

  const choose = (nextLab: LabId, previewMode: PreviewMode) => {
    setLab(nextLab);
    setPreference(previewMode);
  };

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-3xl text-body-sm text-muted">
        Seven real design systems, built from the DESIGN.md files in the design folder: their colours, type scale, corners and shadows. Pick a company in Light
        or Dark and the whole app follows. Fonts that the companies license are replaced by the closest free font, named under each company.
      </p>
      <button
        type="button"
        onClick={() => setLab(null)}
        aria-pressed={labId === null}
        className={cn("flex w-fit items-center gap-2 rounded-md border bg-surface px-3 py-2 text-body-sm font-semibold text-default", labId === null ? "border-action ring-2 ring-action" : "border-hairline hover:shadow-sm")}
      >
        {labId === null ? <Check size={14} className="text-action" aria-hidden /> : null}
        Keigan's own design (lab off)
      </button>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
        {labThemes.map((theme) => (
          <div key={theme.id} role="radiogroup" aria-label={theme.company} className="rounded-lg border border-hairline bg-surface p-3">
            <div className="mb-2 flex items-baseline justify-between gap-2">
              <span className="text-h3 font-semibold text-default">{theme.company}</span>
              <span className="text-caption text-muted">{theme.nativeMode === "both" ? "Light and dark in the file" : `Written for ${theme.nativeMode}`}</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <ModeButton labId={theme.id} previewMode="light" isSelected={labId === theme.id && resolvedTheme === "light"} onChoose={() => choose(theme.id, "light")} />
              <ModeButton labId={theme.id} previewMode="dark" isSelected={labId === theme.id && resolvedTheme === "dark"} onChoose={() => choose(theme.id, "dark")} />
            </div>
            <p className="mt-2 text-caption text-muted">{theme.fontNote}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
