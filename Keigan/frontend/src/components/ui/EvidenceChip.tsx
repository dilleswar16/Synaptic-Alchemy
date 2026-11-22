import { cn } from "@/utils/cn";
import { Tooltip } from "./Tooltip";

export interface EvidenceChipProps {
  /** Evidence code, e.g. "E3". */
  code: string;
  /** Evidence title shown in the tooltip. */
  title?: string;
  /** `supporting` (green outline), `contradicting` (grey, struck through) or plain. */
  relation?: "plain" | "supporting" | "contradicting";
  /** Scroll to / open the evidence. */
  onSelect?: (code: string) => void;
  className?: string;
}

const relationClasses = {
  plain: "border-hairline bg-surface-sunken text-default",
  supporting: "border-success/50 bg-success-soft text-success",
  contradicting: "border-hairline bg-neutral-soft text-muted line-through",
} as const;

/** Mono pill `E3`; hover/focus shows the evidence title, click selects it. */
export function EvidenceChip({ code, title, relation = "plain", onSelect, className }: EvidenceChipProps) {
  const chipClassName = cn("inline-flex h-6 items-center rounded-xs border px-2 font-mono text-caption font-medium", relationClasses[relation], className);
  const chip = onSelect ? (
    // A button grows to a 44 px target on a phone or a touch screen (spec 8.8); the chip's look is the same, the box around it is larger.
    <button type="button" onClick={() => onSelect(code)} className={cn(chipClassName, "cursor-pointer justify-center hover:brightness-95 max-sm:min-h-11 max-sm:min-w-11 pointer-coarse:min-h-11 pointer-coarse:min-w-11")}>
      {code}
    </button>
  ) : (
    <span className={chipClassName} tabIndex={title ? 0 : undefined}>
      {code}
    </span>
  );
  return title ? <Tooltip content={title}>{chip}</Tooltip> : chip;
}
